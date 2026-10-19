#!/usr/bin/env python3
"""The operator resets his own credential and recovery code. An agent must not run this.

For the case where BOTH were lost (2026-10-19). Re-enrolling would mint a new
operator id, orphaning everything scoped to the old one -- re-admitted
lessons, skills, approvals. This keeps the id and replaces only the secrets:

* it refuses unless stdin and stdout are a real terminal: captured output means
  an agent is likely driving it, and the operator's secrets must not pass
  through one;
* the operator TYPES the new credential and the new recovery code, each twice,
  at hidden prompts -- this tool never generates, prints, logs or stores a
  secret (only the digests reach the identity store, as at enrollment);
* he confirms with the word `reset`;
* every existing session is revoked, and the reset is recorded as an
  authentication event and in the tamper-evident audit log.

Its proof is local access to this machine's identity store, which already lets
anyone delete that store and enroll a different operator; so it grants nothing
that access did not, and it is the only way back that loses nothing.

    python tools/operator_recover.py --reset

Run it from the checkout whose data/ holds the identity store (or set
AIOS_DATA_DIR to it). Restarting the backend is not needed.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_ALLOW_NONTTY_ENV = "AIOS_OPERATOR_RECOVER_ALLOW_NONTTY"  # the test suite only


def _interactive() -> bool:
    if os.environ.get(_ALLOW_NONTTY_ENV):
        return True
    return sys.stdin.isatty() and sys.stdout.isatty()


def _twice(prompt: Callable[[str], str], what: str) -> str:
    first = prompt(f"new {what} (hidden): ")
    second = prompt(f"new {what} again (hidden): ")
    if first != second:
        raise SystemExit(f"the two {what} entries differ; nothing was changed")
    return first


def reset(
    *,
    identity_db_path: Path,
    session_db_path: Path,
    prompt: Callable[[str], str] = getpass.getpass,
    confirm: Callable[[str], str] = input,
    audit: Callable[[str, str], None] | None = None,
) -> int:
    from aios.application.identity.service import (
        IdentityAuthority,
        IdentityError,
    )

    identity = IdentityAuthority(
        identity_db_path=identity_db_path, session_db_path=session_db_path
    )
    operator = identity.store.operator()
    if operator is None:
        print("no operator is enrolled here; enroll instead", file=sys.stderr)
        return 1
    operator_id = str(operator["operator_id"])
    print(f"Operator {operator_id[:18]}... ({operator['display_name']})")
    print("This replaces its credential and recovery code. The operator id STAYS,")
    print("so everything scoped to it is kept. Every existing session is logged out.")
    print("You type both new secrets; nothing is printed or stored except digests.")
    print()
    credential = _twice(prompt, "credential")
    recovery_code = _twice(prompt, "recovery code")
    if (
        confirm("Type the word reset to replace them, anything else to abort: ").strip()
        != "reset"
    ):
        print("aborted; nothing was changed", file=sys.stderr)
        return 1
    try:
        kept = identity.reset_secrets_locally(credential, recovery_code)
    except (ValueError, IdentityError) as exc:
        print(f"refused: {exc}; nothing was changed", file=sys.stderr)
        return 1
    if audit is not None:
        audit(
            "operator-secret-reset",
            json.dumps({"operator_id": kept, "path": "tools/operator_recover.py"}),
        )
    print(f"Done. Operator {kept[:18]}... kept its id. Log in with the new credential;")
    print("keep the recovery code somewhere safe (a password manager), apart from it.")
    return 0


def _audit(action: str, payload: str) -> None:
    from aios.security.audit_logger import log_action
    from aios.security.gateway import Zone

    log_action(action, payload, Zone.YELLOW)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reset", action="store_true", required=True)
    parser.parse_args(argv)
    if not _interactive():
        print(
            "refusing: stdin/stdout is not a terminal, so this is very likely\n"
            "running inside an agent session. Resetting the operator's secrets is\n"
            "his act -- run it in a plain terminal with no agent attached.",
            file=sys.stderr,
        )
        return 2
    from aios import config

    return reset(
        identity_db_path=config.IDENTITY_DB_PATH,
        session_db_path=config.SESSION_DB_PATH,
        audit=_audit,
    )


if __name__ == "__main__":
    raise SystemExit(main())
