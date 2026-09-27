#!/usr/bin/env python3
"""The operator activates institutional skills. An agent must not run --activate.

Activation is the operator's act (Phase 2, docs/learning/PHASE2_DESIGN.md): a
skill becomes ``active`` -- recalled into prompts in pilot mode, and after the
hard switch eligible to become a reflex -- only through the capability-backed
route ``POST /api/v1/skills/{skill_id}/versions/{version}/activate``. That route
needs an authenticated operator session, a fresh re-authentication, and the
server's own two-request capability exchange. This tool drives exactly that
path against the running backend, with ``aios.probe_session.ProbeSession``.

The credential is the operator's:

* read from ``AIOS_OPERATOR_CREDENTIAL`` in the environment if set (volatile,
  AGENTS.md VII.4), or else typed at a hidden prompt in the operator's own
  terminal;
* held in this process's memory only -- never printed, logged, or written;
* never used to enroll. Without a credential the tool stops; it will not
  create an operator.

USAGE (one line each; works in PowerShell and bash)
-----
    python tools/activate_skills.py                                   # list review-ready skills, read-only
    python tools/activate_skills.py --activate 79 41 --i-am-the-operator "Swapnil"

The backend must be running (``AIOS_PROBE_BASE``, default http://127.0.0.1:8000).
Ids are the legacy ``procedural_skills`` ids shown in the listing.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aios import config  # noqa: E402
from aios.application.memory.institutional_skills import is_review_ready  # noqa: E402
from aios.domain.learning.repository import SkillRecord, SkillRepository  # noqa: E402

#: Step tools that only read or run a check. Anything else writes.
READ_ONLY_TOOLS = frozenset({"read_file", "read_directory", "verify", "search"})


def _legacy_id(record: SkillRecord) -> int | None:
    raw = record.provenance.get("legacy_id")
    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):
        return None


def _steps(record: SkillRecord) -> list[str]:
    try:
        steps = json.loads(record.procedure)
    except (TypeError, ValueError):
        return [record.procedure]
    return [str(s) for s in steps] if isinstance(steps, list) else [record.procedure]


def describe(record: SkillRecord) -> dict[str, Any]:
    tools = sorted(set(record.allowed_tools))
    return {
        "legacy_id": _legacy_id(record),
        "skill_id": record.skill_id,
        "version": record.version,
        "state": record.state,
        "review_ready": is_review_ready(record),
        "evidence": f"{record.success_count} ok / {record.failure_count} failed",
        "confidence": record.confidence,
        "legacy_reuse": record.provenance.get("legacy_reuse", ""),
        "risk": "read-only" if set(tools) <= READ_ONLY_TOOLS else "WRITES",
        "tools": tools,
        "goal": record.problem_signature,
        "steps": _steps(record),
    }


def candidates(repository: SkillRepository) -> list[SkillRecord]:
    return sorted(
        (r for r in repository.list_skills() if r.state == "candidate"),
        key=lambda r: (_legacy_id(r) is None, _legacy_id(r) or 0, r.skill_id),
    )


def resolve(
    repository: SkillRepository, legacy_ids: Sequence[int]
) -> list[SkillRecord]:
    """The candidate record for each legacy id, or an error naming what is wrong."""
    by_legacy = {_legacy_id(r): r for r in candidates(repository)}
    missing = [i for i in legacy_ids if i not in by_legacy]
    if missing:
        raise SystemExit(
            f"not an activatable candidate: {missing}. Run with no arguments to "
            "list the candidates."
        )
    return [by_legacy[i] for i in legacy_ids]


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


def activate(records: Sequence[SkillRecord], base: str) -> list[dict[str, Any]]:
    from aios.probe_session import ProbeSession

    # ProbeSession reads the credential from the process environment. Put it
    # there for this process only; it is never printed or written.
    os.environ["AIOS_OPERATOR_CREDENTIAL"] = _credential()
    session = ProbeSession(base).bootstrap(display_name="Skill Activation")
    results = []
    for record in records:
        route = f"/api/v1/skills/{record.skill_id}/versions/{record.version}/activate"
        response = session.post_stream(route, {}, timeout=30)
        try:
            body = response.json()
        except ValueError:
            body = {"text": response.text[:300]}
        results.append(
            {
                "legacy_id": _legacy_id(record),
                "status": response.status_code,
                "response": body,
            }
        )
        if response.status_code != 200:
            break  # stop at the first refusal; the operator reads why
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--activate", nargs="+", type=int, metavar="LEGACY_ID")
    parser.add_argument("--i-am-the-operator", dest="operator", metavar="NAME")
    parser.add_argument(
        "--allow-not-review-ready",
        action="store_true",
        help="activate a candidate that has not met the old promotion rule",
    )
    parser.add_argument("--base", default=config.PROBE_BASE)
    args = parser.parse_args(argv)
    repository = SkillRepository(config.OPERATIONAL_STATE_DB_PATH)

    if not args.activate:
        rows = [describe(r) for r in candidates(repository)]
        ready = [r for r in rows if r["review_ready"]]
        print(
            json.dumps(
                {"review_ready": ready, "other_candidates": len(rows) - len(ready)},
                indent=2,
            )
        )
        return 0

    if not args.operator:
        raise SystemExit(
            "--activate is the operator's act: add --i-am-the-operator NAME"
        )
    records = resolve(repository, args.activate)
    not_ready = [_legacy_id(r) for r in records if not is_review_ready(r)]
    if not_ready and not args.allow_not_review_ready:
        raise SystemExit(
            f"not review-ready: {not_ready}; add --allow-not-review-ready to activate anyway"
        )
    for record in records:
        info = describe(record)
        print(
            f"activating legacy {info['legacy_id']} ({info['risk']}): {info['goal'][:100]}"
        )
    results = activate(records, args.base)
    print(json.dumps({"operator": args.operator, "results": results}, indent=2))
    return 0 if results and all(r["status"] == 200 for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
