"""Architecture test: every canonical backend event with a real production
publisher must have a corresponding frontend reaction handler.

This is a regression guard for the exact bug found and fixed in the
2026-07-22 frontend-review fix pass: worker.failed/worker.killed had real
backend publishers (aios/application/workers/foundry.py) but no frontend
handler in livingMirrorRegistry.ts. dispatchLivingMirrorEvent() drops any
event with no registered handler BEFORE mirrorStore.applyEvent() ever
runs, so a failed/killed worker was silently never removed from the
frontend's active-worker list.

PUBLISHED_CANONICAL_EVENTS is a hand-verified snapshot, not an automatic
derivation. Each member was confirmed by directly reading a real
`CanonicalEvent(event_type=CanonicalEventType.<MEMBER>.value, ...)`
construction followed by a real `bus.append(...)` call (not just a
symbolic reference, e.g. in a comment or docstring). PLAN_CREATED, despite
looking pre-wired in the frontend registry, was found during this
verification to have ZERO real publisher anywhere -- confirmed via both a
symbolic-reference grep and a literal-string grep for "plan.created" --
so it is correctly classified as unpublished (its frontend handler is
harmless dead code today, not a bug, since it can never actually receive
an event through dispatchLivingMirrorEvent()'s exclusively-Cortex-Bus-fed
pipeline).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aios.core.events import CanonicalEventType

REPO_ROOT = Path(__file__).resolve().parents[2]
LIVING_MIRROR_REGISTRY = (
    REPO_ROOT / "frontend" / "src" / "superbrain" / "lib" / "livingMirrorRegistry.ts"
)

# Verified 2026-07-22 via direct inspection of each real
# `CanonicalEvent(event_type=CanonicalEventType.<MEMBER>.value, ...)` +
# `bus.append(...)` call site.
PUBLISHED_CANONICAL_EVENTS: frozenset[CanonicalEventType] = frozenset(
    {
        CanonicalEventType.TURN_STARTED,  # aios/api/main.py (_sse bridge)
        CanonicalEventType.ROUTE_SELECTED,  # aios/api/main.py (_sse bridge)
        CanonicalEventType.APPROVAL_REQUIRED,  # aios/api/main.py (_sse bridge)
        CanonicalEventType.TURN_COMPLETED,  # aios/api/main.py (_sse bridge)
        CanonicalEventType.TURN_FAILED,  # aios/api/main.py (_sse bridge)
        CanonicalEventType.WORKER_REQUESTED,  # aios/application/workers/foundry.py
        CanonicalEventType.WORKER_ADMITTED,  # aios/application/workers/foundry.py
        CanonicalEventType.WORKER_STARTED,  # foundry.py + aios/runtime/spawner.py
        CanonicalEventType.WORKER_AWAITING_CAPABILITY,  # foundry.py
        CanonicalEventType.WORKER_COMPLETED,  # foundry.py + spawner.py
        CanonicalEventType.WORKER_FAILED,  # aios/application/workers/foundry.py
        CanonicalEventType.WORKER_KILLED,  # aios/application/workers/foundry.py
        CanonicalEventType.WORKER_DISSOLVED,  # foundry.py + spawner.py
        CanonicalEventType.FACTS_PROPOSED,  # conversation_pipeline.py, generate_pipeline.py
        CanonicalEventType.EDIT_PROPOSED,  # aios/api/routes/files.py
        CanonicalEventType.EDIT_BLOCKED,  # aios/api/routes/files.py
        CanonicalEventType.MEMORY_RECALLED,  # aios/api/routes/memory.py
        CanonicalEventType.MEMORY_TRUSTED_WORKFLOW_APPLIED,  # aios/api/routes/memory.py
        CanonicalEventType.TELEMETRY_AGENT_STARTED,  # aios/core/telemetry.py
    }
)

# Confirmed via the same inspection to have ZERO real publisher anywhere in
# aios/ as of 2026-07-22 (checked both symbolic `CanonicalEventType.<MEMBER>`
# references and, for PLAN_CREATED specifically, the literal string too).
# These are aspirational enum members, not yet wired to any production code
# path. A frontend handler for one of these (other than PLAN_CREATED's
# pre-existing, harmlessly-unreachable one) would be dead code, so this set
# exists to make that fact explicit and intentional rather than an
# unexplained gap.
UNPUBLISHED_CANONICAL_EVENTS: frozenset[CanonicalEventType] = frozenset(
    {
        CanonicalEventType.ALIGNMENT_DECLARED,
        CanonicalEventType.PLAN_CREATED,
        CanonicalEventType.APPROVAL_DECIDED,
        CanonicalEventType.TOOL_LIFECYCLE_CHANGED,
        CanonicalEventType.VERIFICATION_COMPLETED,
        CanonicalEventType.AUTONOMY_GRANT_CHANGED,
        CanonicalEventType.LEARNING_SKILL_MASTERED,
    }
)


def test_published_and_unpublished_sets_partition_every_canonical_event() -> None:
    """Every enum member must be classified one way or the other -- an
    unaccounted-for member means this test wasn't updated when a new
    CanonicalEventType member was added to events.py."""
    all_members = frozenset(CanonicalEventType)
    accounted = PUBLISHED_CANONICAL_EVENTS | UNPUBLISHED_CANONICAL_EVENTS
    assert accounted == all_members, (
        "CanonicalEventType members not classified as published/unpublished "
        f"in this test: {sorted(m.value for m in all_members - accounted)}"
    )
    assert not (PUBLISHED_CANONICAL_EVENTS & UNPUBLISHED_CANONICAL_EVENTS)


@pytest.mark.architecture
def test_every_published_canonical_event_has_a_frontend_reaction_handler() -> None:
    registry_source = LIVING_MIRROR_REGISTRY.read_text(encoding="utf-8")
    missing = sorted(
        member.value
        for member in PUBLISHED_CANONICAL_EVENTS
        if f"'{member.value}': {{" not in registry_source
    )
    assert not missing, (
        "livingMirrorRegistry.ts has no reaction handler for published "
        f"canonical event(s): {missing} -- dispatchLivingMirrorEvent() will "
        "silently drop these before mirrorStore.applyEvent() ever runs"
    )
