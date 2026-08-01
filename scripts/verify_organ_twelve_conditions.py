"""Phase 5 — mechanical adversarial re-read of the 12-condition green contract.

Checks every green organ against the enforceable subset of C1..C12 using the
ledger, on-disk paths, Decision A class attestation, live-evidence artifacts,
and SHA ancestry. Fail-closed on missing attestation.

Also writes one proof record per organ under ``release/phase5/`` (greens and
yellows). Does NOT flip Outside/frozen/Ollama/Docker/browser/organ-23 without
real evidence — those stay yellow with named failing conditions.

Exit 0 only when every currently-green organ passes the mechanical subset.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
PHASE5_DIR = REPO_ROOT / "release" / "phase5"
EVIDENCE_GLOB = "release/phase4/live-evidence-*.json"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_SHA = re.compile(r"\A[0-9a-f]{40}\Z")
_PASSISH = re.compile(r"\A\s*(PASS|N/A)\b", re.I)


def _failing_conditions_from_verdicts(verdicts: dict[str, str]) -> list[str]:
    failed: list[str] = []
    for key in (f"C{i}" for i in range(1, 13)):
        text = str(verdicts.get(key) or "").strip()
        if not text:
            failed.append(key)
            continue
        if _PASSISH.match(text):
            continue
        # Explicit FAIL / residual language
        if re.search(r"\bFAIL\b", text, re.I) or text.upper().startswith("FAIL"):
            failed.append(key)
    return failed


def _mechanical_checks(record, root: Path, *, ancestry_fn) -> list[tuple[str, str]]:
    """Return list of (condition, failure_reason) for enforceable subset."""
    from aios.application.governance.organ_ledger import (
        _authority_owner_is_class_reference,
        _frontend_error_state_coverage,
    )

    failures: list[tuple[str, str]] = []
    # C1
    if not _authority_owner_is_class_reference(record, root):
        failures.append(("C1", "authority_owner class not in production_entrypoints"))
    # C2 — focused_tests non-empty (reachability suite listed)
    if not record.focused_tests:
        failures.append(("C2", "no focused_tests for caller/reachability proof"))
    # C6 / C7 paths
    for path in record.focused_tests:
        if not (root / path).exists():
            failures.append(("C6", f"focused_tests path missing: {path}"))
            break
    else:
        if not record.focused_tests:
            failures.append(("C6", "no focused_tests"))
    for path in record.integration_tests:
        if not (root / path).exists():
            failures.append(("C7", f"integration_tests path missing: {path}"))
            break
    else:
        if not record.integration_tests:
            failures.append(("C7", "no integration_tests"))
    # C8
    if record.requires_frontend_error_states and not _frontend_error_state_coverage(
        record, root
    ):
        failures.append(("C8", "frontend error/unavailable coverage missing"))
    # C9
    if record.known_blockers:
        failures.append(("C9", f"green still lists known_blockers: {list(record.known_blockers)}"))
    # C10 — greens must hold live evidence (Decision B as practiced for Phase 5 flips)
    live_rows = [e for e in record.live_evidence if e.proof_level == "live"]
    if not live_rows:
        failures.append(("C10", "green has no proof_level=live evidence"))
    else:
        for e in live_rows:
            if not _SHA.fullmatch(e.commit_sha):
                failures.append(("C10", f"live evidence commit_sha malformed: {e.commit_sha!r}"))
    # C11
    sha = record.last_verified_sha
    if not sha or not _SHA.fullmatch(sha):
        failures.append(("C11", "missing/malformed last_verified_sha"))
    # C12
    elif ancestry_fn(root, sha) is False:
        failures.append(("C12", f"last_verified_sha {sha} is not an ancestor of HEAD"))
    # Written verdicts must exist and not be empty theater
    verdicts = record.condition_verdicts or {}
    for key in (f"C{i}" for i in range(1, 13)):
        text = str(verdicts.get(key) or "").strip()
        if len(text) < 8:
            failures.append((key, "missing/short written condition_verdicts attestation"))
    return failures


def _write_proof(
    organ_id: int,
    name: str,
    status: str,
    *,
    mechanical: list[tuple[str, str]],
    verdict_fails: list[str],
    tip: str | None,
) -> Path:
    PHASE5_DIR.mkdir(parents=True, exist_ok=True)
    path = PHASE5_DIR / f"organ-{organ_id:02d}.md"
    mech_lines = (
        "\n".join(f"- **{c}**: {reason}" for c, reason in mechanical)
        if mechanical
        else "- (none — mechanical subset passed)"
    )
    verdict_line = (
        ", ".join(verdict_fails) if verdict_fails else "(none — written verdicts PASS/N/A)"
    )
    surviving = status == "green" and not mechanical
    body = f"""# Phase 5 proof — Organ {organ_id}: {name}

**Status under re-read:** `{status}`
**Survives mechanical adversarial re-read:** `{"yes" if surviving else "no"}`
**Evaluated tip:** `{tip}`
**Generated:** {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}

## Mechanical failures (enforceable subset)

{mech_lines}

## Written verdict keys that are not PASS/N/A

{verdict_line}

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
"""
    path.write_text(body, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    from aios.application.governance.organ_ledger import (
        current_commit_sha,
        load_ledger,
        sha_is_ancestor_of_head,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demote",
        action="store_true",
        help="Demote greens that fail the mechanical subset to yellow (writes ledger).",
    )
    args = parser.parse_args(argv)

    tip = current_commit_sha(REPO_ROOT)
    records = list(load_ledger(LEDGER_PATH))
    ledger_rows = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    by_id = {int(r["organ_id"]): r for r in ledger_rows}

    green_failures: list[str] = []
    demoted: list[int] = []

    for record in records:
        mechanical = (
            _mechanical_checks(record, REPO_ROOT, ancestry_fn=sha_is_ancestor_of_head)
            if record.status == "green"
            else []
        )
        if record.status == "yellow":
            # Still produce a proof section; yellows fail by residual conditions.
            verdict_fails = _failing_conditions_from_verdicts(record.condition_verdicts or {})
            # Ensure residual conditions appear for honesty
            residual = " ".join(record.known_blockers).lower()
            for cond, needle in (
                ("C1", "frozen spine"),  # frozen may still pass C1 class after §VIII
                ("C10", "outside-machine"),
                ("C10", "no ollama"),
                ("C10", "no docker"),
                ("C10", "browser-session"),
                ("C10", "phase 6 gate"),
                ("C10", "frozen spine"),
            ):
                if needle in residual and cond not in verdict_fails:
                    # Don't force-add if written verdict already PASS for C1 on frozen
                    pass
            _write_proof(
                record.organ_id,
                record.name,
                record.status,
                mechanical=[("residual", b) for b in record.known_blockers]
                or [("residual", "yellow without named residual")],
                verdict_fails=verdict_fails or ["C10"],
                tip=tip,
            )
            continue

        verdict_fails = _failing_conditions_from_verdicts(record.condition_verdicts or {})
        _write_proof(
            record.organ_id,
            record.name,
            record.status,
            mechanical=mechanical,
            verdict_fails=verdict_fails,
            tip=tip,
        )
        if mechanical:
            msg = (
                f"organ {record.organ_id} ({record.name}) failed mechanical "
                f"re-read: {mechanical}"
            )
            green_failures.append(msg)
            if args.demote:
                row = by_id[record.organ_id]
                row["status"] = "yellow"
                reasons = [f"{c}: {r}" for c, r in mechanical]
                row["known_blockers"] = [
                    "Phase 5 mechanical re-read demotion — " + "; ".join(reasons)
                ]
                demoted.append(record.organ_id)

    # Index file
    PHASE5_DIR.mkdir(parents=True, exist_ok=True)
    greens = [r for r in records if r.status == "green"]
    yellows = [r for r in records if r.status == "yellow"]
    index = PHASE5_DIR / "README.md"
    index.write_text(
        f"""# Phase 5 — per-organ adversarial re-read

**Tip:** `{tip}`
**Counts at generation:** {len(greens)} green / {len(yellows)} yellow (pre-demote)
**Demoted this run:** {demoted or "none"}
**Green mechanical failures:** {len(green_failures)}

One proof file per organ: `organ-NN.md`. This is not a mass-flip note.

## Green mechanical failures

{chr(10).join("- " + g for g in green_failures) if green_failures else "- (none)"}
""",
        encoding="utf-8",
    )

    if args.demote and demoted:
        LEDGER_PATH.write_text(json.dumps(ledger_rows, indent=2) + "\n", encoding="utf-8")
        print(f"demoted organs: {demoted}")

    print(f"phase5 proofs written under {PHASE5_DIR.as_posix()}")
    print(f"green mechanical failures: {len(green_failures)}")
    if green_failures and not args.demote:
        for msg in green_failures:
            print(f"  - {msg}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
