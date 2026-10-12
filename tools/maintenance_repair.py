#!/usr/bin/env python3
"""The operator runs a maintenance repair mission. An agent must not run --repair.

GAGOS maintaining itself (operator, 2026-10-12: the vulture as the apex
predator's scavenger). The pipeline is the governed one: an admitted scanner
finds, a YELLOW mission is approved by the Human Sovereign, a worker proposes a
registered operation in a staged copy, the executor applies it there, a rescan
verifies the target, promotion applies it with a checkpoint, the smoke check
(compile, import, the tests that import the file) passes or the checkpoint is
restored, and a final rescan resolves the finding.

The frontend has no repair surface yet, and approval needs a privileged
(freshly re-authenticated) operator session plus the server's two-request
capability exchange. This tool drives exactly those routes against the running
backend with ``aios.probe_session.ProbeSession`` -- the same path
``tools/activate_skills.py`` uses. The credential is the operator's:
``AIOS_OPERATOR_CREDENTIAL`` in this shell's environment, or a hidden prompt;
held in memory only, never printed, logged or written; never used to enroll.

USAGE (one line each; PowerShell and bash)
-----
    python tools/maintenance_repair.py --scan                         # vulture scan from the project root
    python tools/maintenance_repair.py --findings                     # open findings, read-only
    python tools/maintenance_repair.py --repair <FINGERPRINT> --i-am-the-operator "Swapnil"

Before --repair, the backend must run with ``AIOS_MAINTENANCE_PROJECT_ROOT``
pointing at a clean git worktree (staging the live checkout is refused), and
the executor service must be up (``AIOS_EXECUTOR_URL`` / ``AIOS_EXECUTOR_TOKEN``
shared with the backend). See docs/operations/FIRST_SELF_REPAIR.md.
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
from aios.domain.maintenance.scanners import (  # noqa: E402
    VULTURE_DEAD_IMPORT_SCANNER_ID,
    VULTURE_DEAD_IMPORT_SCANNER_VERSION,
)

#: A project-rooted scan reads the whole project; GAGOS has ~1,100 Python files.
SCAN_BOUNDS = {
    "max_files": 10_000,
    "max_total_bytes": 100_000_000,
    "max_file_bytes": 5_000_000,
    "deadline_seconds": 300,
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


def _session(base: str) -> Any:
    from aios.probe_session import ProbeSession

    os.environ["AIOS_OPERATOR_CREDENTIAL"] = _credential()
    return ProbeSession(base).bootstrap(display_name="Maintenance Repair")


def _body(response: Any) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"text": response.text[:500]}


def _post(session: Any, route: str, payload: dict[str, Any], timeout: int) -> Any:
    response = session.post_stream(route, payload, timeout=timeout)
    body = _body(response)
    if response.status_code != 200:
        raise SystemExit(
            f"{route} answered {response.status_code}: {json.dumps(body)[:800]}"
        )
    return body


def scan(session: Any) -> dict[str, Any]:
    return _post(
        session,
        "/api/v1/maintenance/scans",
        {
            "scanner_id": VULTURE_DEAD_IMPORT_SCANNER_ID,
            "scanner_version": VULTURE_DEAD_IMPORT_SCANNER_VERSION,
            "target_id": ".",
            **SCAN_BOUNDS,
        },
        timeout=SCAN_BOUNDS["deadline_seconds"] + 60,
    )


def findings(session: Any) -> list[dict[str, Any]]:
    response = session.get("/api/v1/maintenance/findings")
    body = _body(response)
    if response.status_code != 200:
        raise SystemExit(f"findings answered {response.status_code}: {body}")
    items = body.get("items", body) if isinstance(body, dict) else body
    return [
        {
            "fingerprint": f.get("fingerprint"),
            "target": f.get("target_id"),
            "status": f.get("status"),
            "evidence": f.get("deterministic_evidence"),
        }
        for f in items
        if f.get("scanner_id") == VULTURE_DEAD_IMPORT_SCANNER_ID
        and f.get("status") not in ("VERIFIED_RESOLVED", "FALSE_POSITIVE")
    ]


def repair(session: Any, fingerprint: str) -> dict[str, Any]:
    created = _post(
        session,
        "/api/v1/maintenance/repairs/missions",
        {"finding_fingerprint": fingerprint},
        timeout=60,
    )
    mission_id = created["mission_id"]
    print(f"mission {mission_id} created ({created['state']})")
    approved = _post(
        session,
        f"/api/v1/maintenance/repairs/{mission_id}/approve",
        {"contract_digest": created["contract_digest"]},
        timeout=60,
    )
    print(f"mission {mission_id} approved: {json.dumps(approved)[:200]}")
    # The smoke check runs every test file that imports the repaired file
    # (88 for aios/api/main.py); the request lasts until it ends.
    timeout = int(config.MAINTENANCE_SMOKE_TIMEOUT_S) + 900
    return _post(
        session,
        "/api/v1/maintenance/repairs/run",
        {"mission_id": mission_id},
        timeout=timeout,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--scan", action="store_true")
    action.add_argument("--findings", action="store_true")
    action.add_argument("--repair", metavar="FINGERPRINT")
    parser.add_argument("--i-am-the-operator", dest="operator", metavar="NAME")
    parser.add_argument("--base", default=config.PROBE_BASE)
    args = parser.parse_args(argv)

    if args.repair and not args.operator:
        raise SystemExit("--repair is the operator's act: add --i-am-the-operator NAME")
    session = _session(args.base)
    if args.scan:
        print(json.dumps(scan(session), indent=2))
    elif args.findings:
        print(json.dumps(findings(session), indent=2))
    else:
        result = repair(session, args.repair)
        print(json.dumps({"operator": args.operator, "result": result}, indent=2))
        return 0 if result.get("status") == "VERIFIED_RESOLVED" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
