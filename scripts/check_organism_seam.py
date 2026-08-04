#!/usr/bin/env python3
"""The backend must not speak an event the organism cannot feel.

Why this exists
---------------
GAGOS's two halves are joined by one idea: a backend event is simultaneously an
audit record and a gesture. ``aios/core/events.py`` maps SSE event names to an
``EventType`` and then to an ``EventPhase`` (chemotaxis / reflex / emotion /
narrative / wonder), so ``confidence.gated`` becomes ``HESITATION`` becomes the
emotion phase becomes the body tinting purple rather than orange. The governed
backend's vocabulary IS the body's physiological vocabulary.

That seam is held by hand, in two languages:

* Python  -- ``EventType`` and ``CanonicalEventType`` in ``aios/core/events.py``
* TypeScript -- ``CognitionEventType`` in
  ``frontend/src/superbrain/lib/cognitionBus.ts`` and the handler table in
  ``frontend/src/superbrain/lib/livingMirrorRegistry.ts``

Nothing failed when they drifted. A backend event with no counterpart is a state
the interface cannot represent at all -- the UI-side form of constitutional law
X ("unknown or unavailable state must never be displayed as success"). An organ
can be fully alive in the backend and completely invisible to the being, and no
test would notice.

Deliberately one-directional
----------------------------
Only backend-to-frontend coverage is enforced. Frontend-only members
(``terminal``, ``budget``, ``file_tree``, ``reflex-recall``, ``graph-recall``,
``template-plan`` ...) are legitimate: the being is allowed private sensations
that no backend event produces. The invariant is narrower and sharper -- nothing
the backend can SAY may be unhearable.

This asymmetry is a decision, not an oversight, and it is written down because
``tools/thesis_audit.py`` shipped a one-directional check by accident and that
was a defect. The difference between the two cases is this paragraph.

Check-only, on purpose
----------------------
Unlike ``scripts/build_organ_ledger_doc.py`` there is no generate mode. Teaching
the being to feel a new event is a design decision -- which phase, which
intensity, what it looks like on the body -- and a script that auto-invented
those would be exactly the kind of plausible-but-unearned output this repo's
whole evidence discipline exists to refuse.

The ratchet
-----------
Seven real gaps exist today, so enforcing outright would fail on day one. This
follows the repo's existing monotonic-budget shape (see
``.aios/state/condition_proof_budget.json`` and
``tests/test_condition_proof_ratchet.py``): known gaps are named in
``.aios/state/organism_seam_budget.json``, and that list may only SHRINK.

The check fails in BOTH directions:

* a live gap that is not in the budget -- new drift, the main job;
* a budget entry that is no longer a live gap -- a stale budget overstating the
  debt, which would let the list quietly stop meaning anything.

Usage
-----
    python scripts/check_organism_seam.py            # report the seam
    python scripts/check_organism_seam.py --check    # CI: exit 1 on drift
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COGNITION_BUS = (
    REPO_ROOT / "frontend" / "src" / "superbrain" / "lib" / "cognitionBus.ts"
)
MIRROR_REGISTRY = (
    REPO_ROOT / "frontend" / "src" / "superbrain" / "lib" / "livingMirrorRegistry.ts"
)
BUDGET_PATH = REPO_ROOT / ".aios" / "state" / "organism_seam_budget.json"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: Below these counts the TypeScript parsers are assumed to have failed rather
#: than to have found a genuinely tiny vocabulary. Without this a regex that
#: silently stops matching would report "no gaps" and pass forever -- the exact
#: vacuous-green this file exists to prevent.
_MIN_COGNITION_MEMBERS = 10
_MIN_REGISTRY_KEYS = 20


class SeamParseError(RuntimeError):
    """Raised when a frontend vocabulary cannot be read with confidence."""


def backend_cognition_events() -> set[str]:
    """Every EventType the backend can hand to the cognition bus."""
    from aios.core.events import EventType

    return {e.value for e in EventType}


def backend_canonical_events() -> set[str]:
    """Every canonical (mirror-stream) event type the backend can emit."""
    from aios.core.events import CanonicalEventType

    return {e.value for e in CanonicalEventType}


def frontend_cognition_events(path: Path = COGNITION_BUS) -> set[str]:
    """Parse the ``CognitionEventType`` union members from cognitionBus.ts.

    Only the union declaration is scanned, so the word 'telemetry' appearing in
    a JSDoc comment elsewhere in the file is not mistaken for a member -- which
    is precisely how this gap hid.
    """
    source = path.read_text(encoding="utf-8")

    # Strip comments FIRST. The union's own doc comments contain semicolons
    # ("the sovereignty row shows it; additive, ..."), and matching the
    # declaration before stripping them truncated the union at that semicolon
    # and silently returned 7 of 22 members.
    stripped = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    stripped = re.sub(r"//[^\n]*", "", stripped)

    match = re.search(r"export\s+type\s+CognitionEventType\s*=(.*?);", stripped, re.S)
    if not match:
        raise SeamParseError(f"could not locate the CognitionEventType union in {path}")

    members = set(re.findall(r"'([^']+)'", match.group(1)))

    if len(members) < _MIN_COGNITION_MEMBERS:
        raise SeamParseError(
            f"parsed only {len(members)} CognitionEventType members from {path}; "
            "the parser is probably broken rather than the union tiny"
        )
    return members


def frontend_mirror_events(path: Path = MIRROR_REGISTRY) -> set[str]:
    """Parse the handled canonical event keys from livingMirrorRegistry.ts."""
    source = path.read_text(encoding="utf-8")
    keys = set(re.findall(r"^\s*'([A-Za-z0-9_.]+)'\s*:", source, re.M))

    if len(keys) < _MIN_REGISTRY_KEYS:
        raise SeamParseError(
            f"parsed only {len(keys)} registry keys from {path}; the parser is "
            "probably broken rather than the registry tiny"
        )
    return keys


def live_gaps() -> dict[str, list[str]]:
    """Return the backend events the organism currently cannot perceive."""
    return {
        "unheard_cognition_events": sorted(
            backend_cognition_events() - frontend_cognition_events()
        ),
        "unheard_canonical_events": sorted(
            backend_canonical_events() - frontend_mirror_events()
        ),
    }


def load_budget(path: Path = BUDGET_PATH) -> dict[str, list[str]]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {
        "unheard_cognition_events": sorted(data.get("unheard_cognition_events", [])),
        "unheard_canonical_events": sorted(data.get("unheard_canonical_events", [])),
    }


def diff_against_budget(
    gaps: dict[str, list[str]], budget: dict[str, list[str]]
) -> list[str]:
    """Return human-readable problems; empty means the seam is honest."""
    problems: list[str] = []
    for key in ("unheard_cognition_events", "unheard_canonical_events"):
        live = set(gaps[key])
        allowed = set(budget[key])

        for event in sorted(live - allowed):
            problems.append(
                f"{key}: '{event}' is emitted by the backend but the organism has "
                "no way to perceive it, and it is not in the budget. Either teach "
                "the being to feel it, or add it to "
                f"{BUDGET_PATH.relative_to(REPO_ROOT).as_posix()} with a reason."
            )
        for event in sorted(allowed - live):
            problems.append(
                f"{key}: '{event}' is listed as unheard but the organism now "
                "handles it. Remove it from the budget -- the list may only "
                "shrink, and a stale entry makes the whole budget meaningless."
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the backend/organism seam.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when the seam has drifted from the recorded budget",
    )
    args = parser.parse_args(argv)

    gaps = live_gaps()
    budget = load_budget()
    problems = diff_against_budget(gaps, budget)

    if not args.check:
        print("backend -> organism seam")
        for key in ("unheard_cognition_events", "unheard_canonical_events"):
            print(f"\n  {key}: {len(gaps[key])} unheard")
            for event in gaps[key]:
                print(f"    - {event}")

    if problems:
        for problem in problems:
            print(f"organism-seam drift: {problem}")
        return 1

    if args.check:
        total = sum(len(v) for v in gaps.values())
        print(
            f"organism seam matches the recorded budget ({total} known-unheard "
            "backend event(s))"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
