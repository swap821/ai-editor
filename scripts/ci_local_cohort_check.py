"""Assert the golden harness RAN. Never that the model scored well.

Every organ-44 number to date comes from one laptop. That is the honest content
of blocker 2: not that the evidence is wrong, but that nobody else can re-run
it. A cohort in CI on a local model fixes the reproducibility half without any
cloud credentials.

What this gate checks is deliberately narrow:

  * the runner reached a FINAL line -- it completed rather than died
  * at least one turn actually went to a model
  * no authentication failure, provider error, or unhandled traceback

What it does NOT check is the score. A CI-sized local model will score badly and
that is fine; `local-clerk-live` states the same rule for the same reason --
"demanding a pass would create pressure to pick a model that flatters the suite
or to loosen the suite until something passes".

The distinction is the lesson of 2026-08-18. Nine separate infrastructure
defects each produced a low cohort score that looked exactly like model quality:
a region default, a missing protocol field, an inherited token budget, a corrupt
JSON encoder, a stub conftest. A gate that fails on SCORE would have gone red
for all nine and told you nothing about which. A gate that fails on HARNESS
INTEGRITY goes red for exactly those nine and stays green when the model is
merely weak.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

#: Substrings that mean the harness itself broke, not that the model did badly.
_HARNESS_FAILURES = (
    ("ProbeAuthError", "the driver could not authenticate"),
    ("Local inference error", "the provider rejected a request"),
    ("Traceback (most recent call last)", "an unhandled exception"),
    ("Connection aborted", "the backend died mid-run"),
    ("ConnectionResetError", "the backend died mid-run"),
    ("Host header is not configured", "the driver dialled the wrong host"),
    ("an operator is already enrolled", "the instance was not fresh"),
)

_FINAL = re.compile(r"FINAL: (\d+)/(\d+) mission runs passed")


def check(text: str) -> tuple[bool, list[str]]:
    """Return ``(harness_ok, notes)``. Score is reported, never enforced."""
    notes: list[str] = []
    ok = True

    for marker, meaning in _HARNESS_FAILURES:
        hits = text.count(marker)
        if hits:
            ok = False
            notes.append(f"HARNESS FAILURE: {meaning} ({marker} x{hits})")

    final = _FINAL.search(text)
    if not final:
        ok = False
        notes.append("HARNESS FAILURE: the runner never reached a FINAL line")
    else:
        passed, total = final.group(1), final.group(2)
        notes.append(f"score {passed}/{total} (reported, NOT gated)")

    steps = text.count("step ")
    if steps == 0:
        ok = False
        notes.append("HARNESS FAILURE: no step was attempted")
    else:
        notes.append(f"{steps} step invocation(s) reached the model")

    rejected = text.count("outside allowlist")
    if rejected:
        notes.append(
            f"{rejected} command(s) refused by ALLOWED_CMD_RE (reported: a "
            "refusal is the gate working, not a harness fault)"
        )
    return ok, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="the cohort runner's captured output")
    args = parser.parse_args(argv)

    if not args.log.exists():
        print(f"HARNESS FAILURE: {args.log} does not exist", file=sys.stderr)
        return 1

    ok, notes = check(args.log.read_text(encoding="utf-8", errors="ignore"))
    for note in notes:
        print(f"  {note}")
    print("harness integrity:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
