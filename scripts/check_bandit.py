#!/usr/bin/env python3
"""Pattern-level security lint, ratcheted against a budget that may only shrink.

Inventory item 87 / Ultra-plan Phase 8. `pip-audit` covers third-party CVEs and
CodeQL covers semantic queries, but neither catches bandit's class: a new
`subprocess(..., shell=True)`, a hardcoded credential, weak crypto, an insecure
temp file. For a codebase whose whole thesis is a fail-closed security spine,
that gap is worth closing cheaply.

## Why a ratchet rather than a clean-slate gate

Measured on the first run: **141 findings — 0 HIGH, 34 MEDIUM, 107 LOW.**
Demanding zero would mean either a week of triage before the gate lands, or
blanket `# nosec` comments, which is how a security lint becomes decoration.

Two of the most security-relevant findings were read before accepting any of
them, because a gate that silently baselines a real vulnerability is worse than
no gate:

* `core/executor.py` B108 "insecure temp file" — the line is
  `"/tmp:rw,noexec,nosuid,nodev,size=64m"`, a Docker `--tmpfs` mount spec for
  the container's own filesystem. bandit pattern-matched the literal `/tmp`.
  It is a HARDENING line, not a temp-file bug.
* `core/autonomy.py` B608 "SQL injection" — the query is fully parameterised
  with `?` placeholders; the only concatenation is a static `", earned_at = ?"`
  fragment selected by a bool. No input reaches the query text.

Both are the false positives bandit is known for on parameterised-SQL code.

## What actually fails the build

1. **Any HIGH-severity finding — no budget, no exemption.** There are zero
   today, so this gate has real teeth from the moment it lands rather than
   being purely historical.
2. **A new (test, file) pair** that is not in the budget.
3. **More findings of a known pair** than the budget records.
4. **A budget entry that overstates** — if a pair now has fewer findings than
   budgeted, the budget is stale and must be lowered. This is the half that
   keeps a ratchet honest; without it the number never comes down and the file
   quietly becomes a permission slip.

Keyed on `(test_id, file)` rather than line number, so unrelated edits in the
same file do not churn the budget.

Usage::

    python scripts/check_bandit.py            # gate
    python scripts/check_bandit.py --write    # re-baseline (review the diff!)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUDGET_PATH = REPO_ROOT / ".aios" / "state" / "bandit_budget.json"
TARGET = "aios"


def _relative(filename: str) -> str:
    path = Path(filename)
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def run_bandit() -> list[dict]:
    """Return bandit's findings for the package, or exit non-zero on tool failure."""
    result = subprocess.run(
        [sys.executable, "-m", "bandit", "-r", TARGET, "-f", "json", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    # bandit exits 1 when it finds issues, which is normal here; only a missing
    # tool or a crash produces empty/unparseable output.
    if not result.stdout.strip():
        raise SystemExit(
            "bandit produced no output — is it installed?\n"
            + (result.stderr or "")[-500:]
        )
    try:
        return json.loads(result.stdout)["results"]
    except (ValueError, KeyError) as exc:
        raise SystemExit(f"could not parse bandit output: {exc}")


def fingerprint(finding: dict) -> str:
    return f"{finding['test_id']}:{_relative(finding['filename'])}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="rewrite the budget from the current findings (review the diff)",
    )
    args = parser.parse_args()

    findings = run_bandit()
    counts = Counter(fingerprint(f) for f in findings)
    high = [f for f in findings if f["issue_severity"] == "HIGH"]

    if args.write:
        BUDGET_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "_comment": (
                "Ratcheted bandit budget: (test_id:file) -> count. May only "
                "SHRINK. A HIGH-severity finding fails regardless of this file. "
                "Regenerate with scripts/check_bandit.py --write and review the "
                "diff -- lowering a number is progress, raising one needs a "
                "reason in the PR."
            ),
            "budget": dict(sorted(counts.items())),
        }
        BUDGET_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {BUDGET_PATH.relative_to(REPO_ROOT)}: {sum(counts.values())} findings")
        return 0

    if not BUDGET_PATH.exists():
        raise SystemExit(
            f"{BUDGET_PATH} is missing; generate it with --write and commit it"
        )
    budget: dict[str, int] = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))["budget"]

    failures: list[str] = []

    # 1. HIGH severity is never budgeted.
    for finding in high:
        failures.append(
            f"HIGH severity {finding['test_id']} at "
            f"{_relative(finding['filename'])}:{finding['line_number']} — "
            f"{finding['issue_text']}"
        )

    # 2/3. New pairs, and known pairs that grew.
    for key, count in sorted(counts.items()):
        allowed = budget.get(key, 0)
        if count > allowed:
            failures.append(
                f"{key}: {count} finding(s), budget {allowed}"
                + ("  [NEW]" if key not in budget else "  [grew]")
            )

    # 4. A budget that overstates is stale and must come down.
    stale = [
        f"{key}: budget {allowed}, actual {counts.get(key, 0)} — lower it"
        for key, allowed in sorted(budget.items())
        if counts.get(key, 0) < allowed
    ]

    print(
        f"bandit: {len(findings)} finding(s) "
        f"({len(high)} high, "
        f"{sum(1 for f in findings if f['issue_severity'] == 'MEDIUM')} medium, "
        f"{sum(1 for f in findings if f['issue_severity'] == 'LOW')} low)"
    )

    if not failures and not stale:
        print("bandit gate: ok — no new findings, budget accurate")
        return 0

    for line in failures:
        print(f"  FAIL {line}", file=sys.stderr)
    for line in stale:
        print(f"  STALE {line}", file=sys.stderr)
    if failures:
        print(
            "\nA new finding is not automatically a vulnerability — bandit has a "
            "high false-positive rate on parameterised SQL and on Docker mount "
            "specs. READ it. If it is genuine, fix it. If it is not, raise the "
            "budget in the same PR and say why in the commit message.",
            file=sys.stderr,
        )
    if stale:
        print(
            "\nA stale budget entry means findings were removed and the budget "
            "was not lowered. Re-run with --write so the ratchet keeps its teeth.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
