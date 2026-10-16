"""Plan Phase 6f: the learning freeze on the bus, and forgetting what never will be used.

Freeze/thaw on the bus. The emergency stop already froze learning (the latch
in ``aios/memory/learning_freeze.py``); nothing SAID so. These hold:

* the stop's own engagement event carries ``learning``: frozen, the control,
  and every frozen family; its clear carries the thaw. Same point on the
  timeline, and no new event type -- one the organism could not perceive is
  what ``scripts/check_organism_seam.py`` refuses (its budget only goes down);
* the families it names are the families the code actually guards -- a new
  guarded write family that the event does not name fails here;
* describing the freeze can never cost the stop its own record.

GC. A pending lesson is recalled only into its own task and promoted only by
that task's success; one idle for ``MEMORY_COMPACT_PENDING_LESSON_DAYS`` never
will be either. The operator's compaction forgets it, through the lesson
store, and says how many:

* only pending lessons, only idle ones -- a lesson that recurred or was
  promoted since the cutoff is kept, although its row timestamp is old;
* verified and superseded lessons are never touched; a dry run removes
  nothing; zero days forgets nothing; unreadable provenance keeps the lesson;
* it works while the stop is engaged (forgetting is the safe direction).
"""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from aios.memory import learning_freeze

REPO = Path(__file__).resolve().parents[1]
ALICE = "principal:alice6f"
OLD = "2020-01-01 00:00:00"
OLD_ISO = "2020-01-01T00:00:00+00:00"


# --------------------------------------------------------------------------- #
# Freeze / thaw on the bus, on the stop's own events
# --------------------------------------------------------------------------- #
@pytest.fixture
def bus(tmp_path, monkeypatch):
    from aios.api.routes import governance
    from aios.runtime.cortex_bus import CortexBus

    real = CortexBus(db_path=tmp_path / "cortex.db")
    monkeypatch.setattr(governance, "get_cortex_observation_bus", lambda: real)
    return real


def _operator() -> SimpleNamespace:
    return SimpleNamespace(principal_id="operator:6f", session_id="session-6f")


def _events(bus) -> list[tuple[str, dict]]:
    return [(e.event_type, e.payload.get("payload", {})) for e in bus.fetch_since(0)]


def test_the_stops_engagement_says_learning_froze_and_what(bus) -> None:
    from aios.api.routes import governance
    from aios.memory.learning_freeze import FROZEN_BOUNDARIES, LEARNING_FREEZE

    governance._record_emergency_stop_engaged(_operator(), "drill")

    [(kind, payload)] = _events(bus)
    assert kind == "governance.emergency_stop.engaged"
    assert payload["reason"] == "drill" and payload["operator_id"] == "operator:6f"
    assert payload["learning"] == {
        "frozen": True,
        "control": LEARNING_FREEZE.control,
        "boundaries": dict(FROZEN_BOUNDARIES),
    }
    assert LEARNING_FREEZE.control == "emergency_stop"


def test_the_stops_clear_says_learning_thawed(bus) -> None:
    from aios.api.routes import governance
    from aios.memory.learning_freeze import LEARNING_FREEZE

    governance._record_emergency_stop_cleared(_operator())

    [(kind, payload)] = _events(bus)
    assert kind == "governance.emergency_stop.cleared"
    assert payload["operator_id"] == "operator:6f"
    assert payload["learning"] == {
        "frozen": False,
        "control": LEARNING_FREEZE.control,
        "boundaries": {},
    }


def test_describing_the_freeze_never_costs_the_stop_its_record(
    bus, monkeypatch, caplog
) -> None:
    """If the freeze cannot be described, the stop's event still lands --
    saying so, never silently."""
    from aios.api.routes import governance

    class _Broken:
        @property
        def control(self):
            raise RuntimeError("freeze unreadable")

    monkeypatch.setattr(learning_freeze, "LEARNING_FREEZE", _Broken())
    governance._record_emergency_stop_engaged(_operator(), "drill")
    governance._record_emergency_stop_cleared(_operator())

    events = _events(bus)
    assert [kind for kind, _ in events] == [
        "governance.emergency_stop.engaged",
        "governance.emergency_stop.cleared",
    ]
    assert events[0][1]["learning"] == {"frozen": True, "unavailable": True}
    assert events[1][1]["learning"] == {"frozen": False, "unavailable": True}
    assert "Failed to describe the learning freeze" in caplog.text


def test_the_freeze_has_no_event_type_of_its_own() -> None:
    """The freeze rides on the stop's events. A type of its own would be one
    the organism cannot perceive (tests/test_organism_seam.py guards that in
    general; this pins the two names the first design of 6f added)."""
    from aios.core.events import CanonicalEventType

    values = {e.value for e in CanonicalEventType}
    assert not values & {"learning.frozen", "learning.thawed"}


def _guarded_families() -> dict[str, set[str]]:
    """Every family the code guards, from the code: the first segment of each
    ``assert_learning_permitted("<family>.<op>")``, and each module that asks
    ``learning_permitted()`` itself."""
    asserted: set[str] = set()
    asking: set[str] = set()
    for path in sorted((REPO / "aios").rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if rel == "aios/memory/learning_freeze.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", getattr(node.func, "attr", ""))
            if name == "assert_learning_permitted":
                arg = node.args[0]
                if isinstance(arg, ast.JoinedStr):
                    arg = arg.values[0]
                assert isinstance(arg, ast.Constant), f"{rel}: unnamed boundary"
                asserted.add(str(arg.value).split(".")[0])
            elif name == "learning_permitted":
                asking.add(rel)
    return {"asserted": asserted, "asking": asking}


#: Modules that check the freeze themselves, and the family each one is.
_ASKING = {
    "aios/core/cerebellum.py": "reflexes",
    "aios/application/memory/institutional_skills.py": "institutional_skills",
}


def test_the_frozen_families_are_the_families_the_code_guards() -> None:
    from aios.memory.learning_freeze import FROZEN_BOUNDARIES

    found = _guarded_families()
    assert found["asserted"], "the scan found no guarded writes at all"
    assert found["asking"] == set(_ASKING), (
        "a module checks the freeze that the freeze event does not account for"
    )
    expected = found["asserted"] | set(_ASKING.values())
    assert set(FROZEN_BOUNDARIES) == expected
    assert all(text.strip() for text in FROZEN_BOUNDARIES.values())


# --------------------------------------------------------------------------- #
# GC: idle pending lessons
# --------------------------------------------------------------------------- #
@pytest.fixture
def world(tmp_path, monkeypatch):
    from aios.application.memory.adapters import MistakeMemoryAdapter
    from aios.application.memory.provenance_policy import ProvenanceWriter
    from aios.memory.db import init_memory_db
    from aios.memory.mistake import MistakeMemory
    from aios.memory.provenance import LearningSigner, ProvenanceStore

    monkeypatch.setattr(
        learning_freeze, "_latch_path", lambda: tmp_path / "emergency_stop.db"
    )
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    db = tmp_path / "memory.sqlite"
    init_memory_db(db)
    store = ProvenanceStore(db)
    writer = ProvenanceWriter(store, LearningSigner({}), source_kind="live")
    lessons = MistakeMemoryAdapter(MistakeMemory(db_path=db), provenance=writer)
    return SimpleNamespace(root=tmp_path, db=db, store=store, lessons=lessons)


def _lesson(world, task: str, *, command: str = "pytest -q") -> int:
    mistake_id, _ = world.lessons.record_or_increment(
        task,
        "assertion",
        "wrong fixture",
        "used the right one",
        f"lesson for {task}",
        -0.1,
        failed_command=command,
        principal=ALICE,
    )
    return int(mistake_id)


def _age(world, mistake_id: int, *, provenance: bool = True) -> None:
    """Make a lesson old: its row, and (by default) every record of it."""
    with sqlite3.connect(world.db) as conn:
        conn.execute(
            "UPDATE mistake_pool SET timestamp = ? WHERE id = ?", (OLD, mistake_id)
        )
        if provenance:
            conn.execute(
                "UPDATE learning_provenance SET created_at = ? "
                "WHERE row_table = 'mistake_pool' AND row_id = ?",
                (OLD_ISO, str(mistake_id)),
            )


def _ids(world) -> list[int]:
    with sqlite3.connect(world.db) as conn:
        return [r[0] for r in conn.execute("SELECT id FROM mistake_pool ORDER BY id")]


def _status(world, mistake_id: int) -> str:
    with sqlite3.connect(world.db) as conn:
        return conn.execute(
            "SELECT verification_status FROM mistake_pool WHERE id = ?", (mistake_id,)
        ).fetchone()[0]


def _journal(world) -> list[tuple[str, str]]:
    with sqlite3.connect(world.db) as conn:
        return conn.execute(
            "SELECT faculty, detail_json FROM learning_events "
            "WHERE transition = 'forgotten' ORDER BY id"
        ).fetchall()


def test_an_idle_pending_lesson_is_forgotten_and_a_fresh_one_kept(world) -> None:
    old, fresh = _lesson(world, "task-old"), _lesson(world, "task-fresh")
    _age(world, old)

    removed = world.lessons.forget_stale_pending(30, dry_run=False)

    assert removed == [old]
    assert _ids(world) == [fresh]
    [(faculty, detail)] = _journal(world)
    assert faculty == "L2" and f"[{old}]" in detail


def test_a_dry_run_names_them_and_removes_nothing(world) -> None:
    old = _lesson(world, "task-old")
    _age(world, old)

    assert world.lessons.forget_stale_pending(30, dry_run=True) == [old]
    assert _ids(world) == [old]
    assert _journal(world) == []


def test_verified_and_superseded_lessons_are_never_forgotten(world) -> None:
    verified, superseded = _lesson(world, "task-v"), _lesson(world, "task-s")
    world.lessons.promote(verified, principal=ALICE)
    with sqlite3.connect(world.db) as conn:
        conn.execute(
            "UPDATE mistake_pool SET verification_status = 'superseded' WHERE id = ?",
            (superseded,),
        )
    _age(world, verified)
    _age(world, superseded)

    assert world.lessons.forget_stale_pending(30, dry_run=True) == []
    assert world.lessons.forget_stale_pending(30, dry_run=False) == []
    assert _ids(world) == [verified, superseded]


def test_a_lesson_that_recurred_since_the_cutoff_is_kept(world) -> None:
    """A recurrence bumps the count, not the row's timestamp: created two
    years ago and seen again today is not idle."""
    recurring = _lesson(world, "task-r")
    _age(world, recurring)
    again, recurrence = world.lessons.record_or_increment(
        "task-r",
        "assertion",
        "wrong fixture",
        "used the right one",
        "lesson for task-r",
        -0.1,
        failed_command="pytest -q",
        principal=ALICE,
    )
    assert (again, recurrence) == (recurring, True)
    with sqlite3.connect(world.db) as conn:
        stamp = conn.execute(
            "SELECT timestamp FROM mistake_pool WHERE id = ?", (recurring,)
        ).fetchone()[0]
    assert stamp == OLD, "the premise: a recurrence leaves the timestamp alone"

    assert world.lessons.forget_stale_pending(30, dry_run=False) == []
    assert _ids(world) == [recurring]


def test_a_lesson_never_recorded_in_provenance_is_judged_by_its_row(world) -> None:
    from aios.application.memory.adapters import MistakeMemoryAdapter

    old = _lesson(world, "task-old")
    _age(world, old)
    bare = MistakeMemoryAdapter(world.lessons.store)  # no provenance writer

    assert bare.forget_stale_pending(30, dry_run=True) == [old]
    with sqlite3.connect(world.db) as conn:
        conn.execute("DELETE FROM learning_provenance")
    assert world.lessons.forget_stale_pending(30, dry_run=True) == [old]


def test_unreadable_provenance_keeps_the_lesson(world, monkeypatch) -> None:
    old = _lesson(world, "task-old")
    _age(world, old)

    def _broken(*_a, **_k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(world.store, "last_recorded_at", _broken)
    assert world.lessons.forget_stale_pending(30, dry_run=False) == []
    assert _ids(world) == [old]


def test_zero_days_forgets_nothing(world) -> None:
    old = _lesson(world, "task-old")
    _age(world, old)

    assert world.lessons.forget_stale_pending(0, dry_run=False) == []
    assert world.lessons.forget_stale_pending(-5, dry_run=False) == []
    assert _ids(world) == [old]


def test_the_cutoff_is_the_number_of_days(world) -> None:
    """A lesson three days idle is forgotten at two days, kept at five."""
    lesson = _lesson(world, "task-3d")
    with sqlite3.connect(world.db) as conn:
        conn.execute(
            "UPDATE mistake_pool SET timestamp = datetime('now', '-3 days') "
            "WHERE id = ?",
            (lesson,),
        )
        conn.execute(
            "UPDATE learning_provenance SET created_at = ? WHERE row_id = ?",
            ("2020-01-01T00:00:00+00:00", str(lesson)),
        )
    assert world.lessons.forget_stale_pending(5, dry_run=True) == []
    assert world.lessons.forget_stale_pending(2, dry_run=True) == [lesson]


def test_a_lesson_promoted_after_the_read_is_not_deleted(world) -> None:
    lesson = _lesson(world, "task-p")
    world.lessons.promote(lesson, principal=ALICE)

    assert world.lessons.store.forget_pending([lesson]) == []
    assert world.lessons.store.forget_pending([]) == []
    assert _status(world, lesson) == "verified"
    # In one batch with a lesson still pending, only that one goes.
    pending = _lesson(world, "task-q")
    assert world.lessons.store.forget_pending([lesson, pending]) == [pending]
    assert _ids(world) == [lesson]


def test_forgetting_works_while_the_stop_is_engaged(world) -> None:
    from aios.application.governance.emergency_stop import (
        EmergencyStopController,
        EmergencyStopHooks,
    )
    from aios.domain.governance.contracts import EmergencyStopRequest

    old = _lesson(world, "task-old")
    _age(world, old)

    def noop(*_a, **_k):
        return None

    EmergencyStopController(
        world.root / "emergency_stop.db",
        hooks=EmergencyStopHooks(
            revoke_capabilities=noop,
            cancel_queued_missions=noop,
            kill_active_workers=noop,
            disable_autonomy=noop,
            preserve_evidence=noop,
        ),
    ).engage(
        EmergencyStopRequest(
            operator_id="operator:test",
            authentication_event_id="event:engage",
            reason="drill",
        )
    )
    assert not learning_freeze.learning_permitted()

    assert world.lessons.forget_stale_pending(30, dry_run=False) == [old]
    assert _ids(world) == []


# --------------------------------------------------------------------------- #
# Through the authority: compaction forgets them too, and says how many
# --------------------------------------------------------------------------- #
class _Compaction:
    def compact(self, *, dry_run: bool = True) -> dict:
        return {"dry_run": dry_run, "semantic_removed": 0}


def test_compaction_through_the_authority_forgets_idle_pending_lessons(
    world, tmp_path, monkeypatch
) -> None:
    from aios import config
    from aios.application.memory.authority import MemoryAuthority
    from aios.infrastructure.memory.authority_store import MemoryAuthorityStore

    monkeypatch.setattr(config, "MEMORY_COMPACT_PENDING_LESSON_DAYS", 30.0)
    old, fresh = _lesson(world, "task-old"), _lesson(world, "task-fresh")
    _age(world, old)
    authority = MemoryAuthority(
        store=MemoryAuthorityStore(tmp_path / "authority.db"),
        adapters={"compaction": _Compaction(), "lessons": world.lessons},
    )

    preview = authority.compact_memory(dry_run=True)
    assert preview == {
        "dry_run": True,
        "semantic_removed": 0,
        "lessons_pending_removed": 1,
        "lessons_pending_ids": [old],
    }
    assert _ids(world) == [old, fresh]

    done = authority.compact_memory(dry_run=False)
    assert done["lessons_pending_removed"] == 1
    assert done["lessons_pending_ids"] == [old]
    assert _ids(world) == [fresh]


def test_the_days_come_from_config(world, tmp_path, monkeypatch) -> None:
    from aios import config
    from aios.application.memory.authority import MemoryAuthority
    from aios.infrastructure.memory.authority_store import MemoryAuthorityStore

    old = _lesson(world, "task-old")
    _age(world, old)
    authority = MemoryAuthority(
        store=MemoryAuthorityStore(tmp_path / "authority.db"),
        adapters={"compaction": _Compaction(), "lessons": world.lessons},
    )
    monkeypatch.setattr(config, "MEMORY_COMPACT_PENDING_LESSON_DAYS", 0.0)
    assert authority.compact_memory(dry_run=False)["lessons_pending_removed"] == 0
    assert _ids(world) == [old]
