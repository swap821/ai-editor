#!/usr/bin/env python3
"""Static type checking on the security spine, gated at ZERO.

Inventory item 86 / Ultra-plan Phase 8. The catalogue recommended starting with
the security-critical modules, and that turned out to be exactly right: the
subset had only **11 errors**, small enough to fix outright rather than budget.

A ratchet is the correct answer to 141 bandit findings. It is the wrong answer
to 11 type errors — a budget there would institutionalise a pile that could
simply be cleared, and every one of these was worth reading.

## What the first run actually found

Two live bugs, neither of which any test caught:

* **`core/executor.py` — a real Windows crash.** The subprocess-timeout path
  called `signal.SIGCONT`, `os.killpg`, `os.getpgid` and `signal.SIGKILL`,
  guarded by `except (OSError, ProcessLookupError)`. None of those four names
  EXIST on Windows, so the guard did not apply: `AttributeError` escaped
  `_bounded_run`, the `process.kill()` fallback was unreachable, and a timed-out
  child was left running while the caller saw an attribute error instead of a
  timeout. On the operator's own platform, in the component whose entire job is
  bounding what an agent may do.
* **`api/main.py` and `api/routes/skills.py` — unresolvable annotations.**
  `DevelopmentTracker` and `SkillRepository` were used in FastAPI dependency
  signatures and never imported; `typing.get_type_hints` raised `NameError`.
  Latent only because `from __future__ import annotations` keeps annotations as
  strings and FastAPI's current path never forced them. Pinned separately by
  `tests/test_route_annotations_resolve.py`.

The rest were genuine typing gaps: `Cursor.lastrowid` is `int | None` and was
passed straight to `int()`; the injection shield's embedder was typed `object`,
which claims it has NO attributes and made its own two `.encode` calls errors
while verifying nothing.

## Scope, and why it is not the whole package

`--follow-imports=silent` restricts reported errors to the named files. Checking
the same subset WITHOUT it reports 337 errors across 80 files, because mypy
follows every import. Widening the gate is a separate, larger piece of work; a
gate that covers the security spine completely is worth more than one that
covers everything approximately.

Usage::

    python scripts/check_mypy.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Gated at zero. Adding a path here is a commitment to keep it clean.
CHECKED_PATHS: tuple[str, ...] = (
    "aios/security/",
    "aios/core/executor.py",
    "aios/core/approvals.py",
)

MYPY_ARGS: tuple[str, ...] = (
    "--ignore-missing-imports",
    # Report errors for the named files only. Without this the transitive graph
    # is reported too, which is a different (and much larger) project.
    "--follow-imports=silent",
)


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "mypy", *MYPY_ARGS, *CHECKED_PATHS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode == 0:
        print(f"mypy gate: ok — 0 errors across {len(CHECKED_PATHS)} checked path(s)")
        return 0

    print(output.strip(), file=sys.stderr)
    print(
        "\nThe security spine is gated at ZERO type errors, not ratcheted.\n"
        "\nRead the error before silencing it. The first run of this gate found a\n"
        "real Windows crash in the executor's timeout-kill path and two\n"
        "unresolvable route annotations -- none of which any test caught.\n"
        "\nIf a finding is genuinely a checker limitation, narrow the type or add a\n"
        "TARGETED `# type: ignore[code]` with a comment saying why it is safe. A\n"
        "blanket ignore is how a type gate becomes decoration.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
