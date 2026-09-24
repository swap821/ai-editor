"""Architecture test: the being kernel may not invent backend event names.

THE OTHER DIRECTION. `test_canonical_event_frontend_coverage.py` asks "does every
PUBLISHED backend event have a frontend handler?" -- it catches a real event the
frontend drops. This asks the inverse: "does every event name the frontend tests
for actually EXIST in the backend's vocabulary?" -- it catches a frontend fact
that can never become true.

Found 2026-09-24 reviewing PR #363. `presentationFromStores.ts` derives the
being's narrative from `currentTurnTypes.has('<name>')` checks, and eight of the
eighteen names it tested for were not in `CanonicalEventType` at all. Five facts
were therefore permanently false no matter what the backend did:

    rollback            every literal missing -> a restored worker never shows as restored
    learning            "
    memoryPromoted      "
    curriculumMastered  "  ('skill.mastered' vs the enum's 'learning.skill.mastered')
    councilDissent      "

The near-miss is the instructive one: the backend member is
`LEARNING_SKILL_MASTERED = "learning.skill.mastered"` and the frontend tested for
`'skill.mastered'`. Nothing failed, nothing logged, the feature was simply inert.
A string that is almost right is indistinguishable from one that is right until
someone compares the two lists.

This is NOT a rule that the frontend may only reference published events. An
aspirational name is legitimate -- the backend gap is often the real defect, as
it was here. The rule is that it must be DECLARED, so "the backend does not emit
this yet" stays a visible decision instead of decaying into a silent dead branch.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from aios.core.events import CanonicalEventType

REPO_ROOT = Path(__file__).resolve().parents[2]
BEING_KERNEL = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "livingMirror"
    / "being"
    / "presentationFromStores.ts"
)

#: Names the being kernel tests for that the backend deliberately does not emit
#: yet, each with the reason it is still referenced. Shrinking this set is
#: progress; adding to it requires saying why here, which is the whole point.
DECLARED_ASPIRATIONAL: dict[str, str] = {
    "council.dissent": (
        "No CanonicalEventType member. Council dissent is recorded in the "
        "council's own store but never published to the observation bus, so the "
        "being cannot feel it. Backend gap, not a frontend typo."
    ),
    "council.dissent.recorded": "Second spelling of the above; same gap.",
    "memory.promoted": (
        "No CanonicalEventType member. Lesson promotion happens (L2 in the "
        "Learning Ledger) but is never published to the bus."
    ),
    "skill.mastered": (
        "The enum member is LEARNING_SKILL_MASTERED = 'learning.skill.mastered' "
        "-- a DIFFERENT string -- and it has no publisher either (it is in "
        "UNPUBLISHED_CANONICAL_EVENTS). Fixing the spelling alone would not make "
        "this fact reachable; the backend has to publish it first."
    ),
    "mission.rolled_back": (
        "No publisher. Referenced once as a consumer in "
        "aios/application/read_models/projection.py, never appended to the bus."
    ),
    "worker.rolled_back": "No CanonicalEventType member and no publisher.",
    "rollback": "Bare fallback spelling for the two above; same gap.",
    "mission.failed": (
        "No CanonicalEventType member, but HARMLESS: it is OR-ed with "
        "worker.failed / worker.killed / worker.work_incomplete, which are all "
        "real and published, so failure detection works today."
    ),
    "plan": (
        "Bare fallback OR-ed with the real plan.created and a phase check, so "
        "hasPlan works today."
    ),
}

_TESTED_LITERAL = re.compile(r"currentTurnTypes\.has\(\s*'([^']+)'\s*\)")


def _tested_event_names() -> set[str]:
    return set(_TESTED_LITERAL.findall(BEING_KERNEL.read_text(encoding="utf-8")))


@pytest.mark.architecture
def test_every_event_name_the_being_tests_for_is_known() -> None:
    """Either the backend defines it, or this file says why it does not."""
    known = {member.value for member in CanonicalEventType}
    undeclared = sorted(
        name
        for name in _tested_event_names()
        if name not in known and name not in DECLARED_ASPIRATIONAL
    )
    assert not undeclared, (
        "presentationFromStores.ts tests for event names that are neither in "
        f"CanonicalEventType nor declared as aspirational here: {undeclared}. "
        "A name that does not exist makes its fact permanently false and logs "
        "nothing. Either add the backend event, fix the spelling, or declare it "
        "in DECLARED_ASPIRATIONAL with the reason."
    )


@pytest.mark.architecture
def test_the_declared_list_does_not_rot() -> None:
    """A declaration for a name nobody tests for any more is stale paperwork,
    and a declaration for one the backend now DOES emit hides a real fix."""
    tested = _tested_event_names()
    known = {member.value for member in CanonicalEventType}
    unused = sorted(name for name in DECLARED_ASPIRATIONAL if name not in tested)
    assert not unused, f"declared but no longer tested for; drop them: {unused}"
    now_real = sorted(name for name in DECLARED_ASPIRATIONAL if name in known)
    assert not now_real, (
        f"the backend now defines these, so they are no longer aspirational: "
        f"{now_real}. Remove them from DECLARED_ASPIRATIONAL."
    )


@pytest.mark.architecture
def test_the_guard_can_actually_fail() -> None:
    """The negative control. A guard nobody has seen say no is not a guard."""
    known = {member.value for member in CanonicalEventType}
    invented = "totally.invented.event"
    assert invented not in known and invented not in DECLARED_ASPIRATIONAL
