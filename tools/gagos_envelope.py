#!/usr/bin/env python3
"""The operator signs, reads and ends GAGOS's daily envelope.

The envelope (organ 9, ``aios/application/capabilities/envelope.py``) is his
once-a-day word: the folders and kinds of change GAGOS may take on as council
missions, how many, for how long, delivered only as a pull request. Signing it
and ending it are HIS acts, through his own routes
(``POST /api/gagos/envelope`` and ``/revoke``), which need an authenticated
operator session and a fresh re-authentication. This tool drives exactly that
path against the running backend, with ``aios.probe_session.ProbeSession``, as
``tools/activate_skills.py`` does.

The credential is the operator's:

* read from ``AIOS_OPERATOR_CREDENTIAL`` if set, or else typed at a hidden
  prompt in his own terminal;
* held in this process's memory only -- never printed, logged or written;
* never used to enroll. Without a credential the tool stops.

USAGE (one line each; PowerShell and bash)
-----
    python tools/gagos_envelope.py status
    python tools/gagos_envelope.py sign
    python tools/gagos_envelope.py sign --folders frontend/src/superbrain/ --kinds tests --missions 2 --hours 8
    python tools/gagos_envelope.py revoke

``sign`` with no flags signs the terms of 2026-11-13: the superbrain and
workbench folders, code and tests, 2 missions, 8 hours. A new signature ends
the envelope before it. The backend must be running (``AIOS_PROBE_BASE``,
default http://127.0.0.1:8000).
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: The terms the operator signed on 2026-11-13, the default for ``sign``.
DEFAULT_FOLDERS = ("frontend/src/superbrain/", "frontend/src/workbench/")
DEFAULT_KINDS = ("code", "tests")
DEFAULT_MISSIONS = 2
DEFAULT_HOURS = 8

ROUTE = "/api/gagos/envelope"


def terms(args: argparse.Namespace) -> dict[str, Any]:
    """The request body ``POST /api/gagos/envelope`` takes."""
    return {
        "folders": list(args.folders or DEFAULT_FOLDERS),
        "kinds": list(args.kinds or DEFAULT_KINDS),
        "maxMissions": int(args.missions),
        "hours": int(args.hours),
    }


def _credential() -> str:
    credential = os.environ.get("AIOS_OPERATOR_CREDENTIAL") or ""
    if not credential and sys.stdin.isatty():
        credential = getpass.getpass("operator credential (hidden, never stored): ")
    if not credential:
        raise SystemExit(
            "no operator credential: set AIOS_OPERATOR_CREDENTIAL in this shell "
            "or run in an interactive terminal. This tool never enrolls."
        )
    return credential


def session(base: str):
    from aios.probe_session import ProbeSession

    # ProbeSession reads the credential from the process environment. Put it
    # there for this process only; it is never printed or written.
    os.environ["AIOS_OPERATOR_CREDENTIAL"] = _credential()
    return ProbeSession(base).bootstrap(display_name="GAGOS envelope")


def run(args: argparse.Namespace, *, connect=session) -> int:
    from aios.probe_common import PROBE_BASE

    live = connect(args.base or PROBE_BASE)
    if args.command == "sign":
        reply = live.post_stream(ROUTE, terms(args), timeout=30)
    elif args.command == "revoke":
        reply = live.post_stream(f"{ROUTE}/revoke", {}, timeout=30)
    else:
        reply = live.get(ROUTE)
    try:
        body = reply.json()
    except ValueError:
        body = {"text": reply.text[:300]}
    print(reply.status_code, json.dumps(body, indent=2))
    return 0 if reply.status_code in (200, 201) else 1


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("command", choices=("status", "sign", "revoke"))
    p.add_argument("--folders", nargs="+", metavar="FOLDER")
    p.add_argument("--kinds", nargs="+", choices=("tests", "code"))
    p.add_argument("--missions", type=int, default=DEFAULT_MISSIONS)
    p.add_argument("--hours", type=int, default=DEFAULT_HOURS)
    p.add_argument("--base", default=None, help="the backend (AIOS_PROBE_BASE)")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    return run(parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
