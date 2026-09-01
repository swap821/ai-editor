"""Assert the endurance harness RAN. Never that the model scored well.

The sibling of `scripts/ci_local_cohort_check.py`, applying the same rule to the
nightly endurance pass. That rule is not a convenience — it is the lesson of
2026-08-18, when nine separate infrastructure defects each produced a low score
that looked exactly like model quality. A gate that fails on SCORE goes red for
all nine and tells you nothing about which; a gate that fails on HARNESS
INTEGRITY goes red for exactly those nine and stays green when the model is
merely weak.

`endurance_tester.py` prints `[endurance] GREEN` or `RED` from a success-rate
threshold of 0.80 and a latency-stability check. On the CI-sized model this
nightly uses (`qwen2.5:0.5b`, 2 cores, no accelerator) RED is the expected and
uninteresting outcome. What is NOT expected, and what this gate exists to catch:

  * the run never reached its summary — it died mid-pass
  * zero turns were attempted — the harness never talked to anything
  * it aborted on consecutive errors — the backend or provider was broken
  * an unhandled traceback, an auth failure, or a provider error

Read the log this produces before changing the thresholds here. A gate nobody
understands gets loosened the first time it is inconvenient.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

#: The summary banner the tester prints once it completes a pass.
_SUMMARY = re.compile(r"^\[endurance\] (GREEN|RED)\s*$", re.MULTILINE)
#: `  turns: N`
_TURNS = re.compile(r"^\s*turns:\s*(\d+)\s*$", re.MULTILINE)
#: The tester's own give-up path.
_ABORT = re.compile(r"^\[endurance\] ABORT:", re.MULTILINE)

#: Substrings that mean the environment failed, not the model. Matched
#: case-insensitively against the whole log.
_INFRASTRUCTURE_FAILURES = (
    "traceback (most recent call last)",
    "backend unreachable",
    "connectionerror",
    "connection refused",
    "401 unauthorized",
    "403 forbidden",
    "csrf",
    "attempt to write a readonly database",
    "no such table",
)


def check(log: str) -> list[str]:
    """Return the reasons this run proves nothing. Empty means the harness ran."""
    problems: list[str] = []

    summary = _SUMMARY.search(log)
    if summary is None:
        problems.append(
            "the endurance run never printed its summary banner — it died "
            "mid-pass rather than completing. Score is irrelevant; the harness "
            "did not finish."
        )

    if _ABORT.search(log):
        problems.append(
            "the tester ABORTED on consecutive errors, which is its own signal "
            "that the backend or provider was broken rather than the model weak"
        )

    turns = _TURNS.search(log)
    if turns is None:
        problems.append("no turn count in the summary — cannot tell if anything ran")
    elif int(turns.group(1)) == 0:
        problems.append(
            "zero turns were attempted; the harness never reached a model, so "
            "this run is evidence of nothing"
        )

    lowered = log.lower()
    for marker in _INFRASTRUCTURE_FAILURES:
        if marker in lowered:
            problems.append(f"infrastructure failure in the log: {marker!r}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="the endurance run's captured output")
    args = parser.parse_args()

    if not args.log.exists():
        print(f"endurance log not found: {args.log}", file=sys.stderr)
        return 1

    log = args.log.read_text(encoding="utf-8", errors="replace")
    problems = check(log)

    summary = _SUMMARY.search(log)
    verdict = summary.group(1) if summary else "NO-SUMMARY"
    turns = _TURNS.search(log)
    print(
        f"endurance harness: verdict={verdict} "
        f"turns={turns.group(1) if turns else '?'}"
    )

    if not problems:
        print(
            "endurance gate: ok — the harness completed a pass. The GREEN/RED "
            "verdict above is NOT gated on; a CI-sized model is expected to "
            "score badly."
        )
        return 0

    print("", file=sys.stderr)
    print("endurance gate: FAILED — this run proves nothing:", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    print(
        "\nThis gate does not check the score. It failed because the harness "
        "itself did not run cleanly, which means the nightly produced no usable "
        "evidence either way.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
