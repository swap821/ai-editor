"""Phase 2 pilot: reflexes read the store recall reads.

In pilot mode recall answered only from skills the operator ACTIVATED in the
institutional library, while the cerebellum still compiled and replayed
reflexes from skills the legacy store had promoted by itself. A reflex is the
one learned behaviour that runs with no model in the loop, so that was the
wrong half to leave behind. With the gate attached, a playbook replays only if
its skill is active and its steps are exactly the activated procedure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aios import config
from aios.application.memory.adapters import SkillMemoryAdapter
from aios.application.memory.bootstrap import build_memory_authority
from aios.application.memory.institutional_skills import (
    DualWriteSkillAdapter,
    SkillTrailIndex,
    build_skills_slot,
)
from aios.core.cerebellum import Cerebellum
from aios.domain.learning.repository import SkillRepository
from aios.memory import learning_freeze
from aios.memory.db import get_connection, init_memory_db
from aios.memory.skills import SkillMemory
from tools import migrate_skills_to_institutional as mig

GOAL = "run the parser tests and report the result"
STEPS = ["verify: command=pytest tests/test_parser.py -q"]


class Bus:
    def __init__(self) -> None:
        self.events: list = []

    def append(self, event) -> None:
        self.events.append(event)

    def reasons(self) -> list[str]:
        return [e.payload.get("reason") for e in self.events]


@pytest.fixture()
def world(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        learning_freeze, "_latch_path", lambda: tmp_path / "emergency_stop.db"
    )
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    legacy_db = tmp_path / "memory.db"
    init_memory_db(legacy_db)
    cerebellum = Cerebellum(legacy_db)
    bus = Bus()
    cerebellum.attach_bus(bus)
    legacy = SkillMemoryAdapter(SkillMemory(legacy_db, cerebellum=cerebellum))
    for _ in range(3):  # legacy promotes it to 'verified' and compiles a reflex
        legacy.record_attempt(GOAL, STEPS, success=True)
    operational = tmp_path / "operational.db"
    mig.run(
        source=legacy_db,
        target=operational,
        backup_dir=tmp_path / "backups",
        do_apply=True,
    )
    repository = SkillRepository(operational)
    dual = build_skills_slot(
        legacy,
        mode="pilot",
        repository=repository,
        trails=SkillTrailIndex(operational),
    )
    assert isinstance(dual, DualWriteSkillAdapter)
    return legacy_db, cerebellum, bus, repository, dual


def _migrated(repository: SkillRepository):
    return next(
        r for r in repository.list_skills() if r.provenance.get("source") == "migrated"
    )


def _activate(repository: SkillRepository, record) -> None:
    """The operator's act, in a test. Live, only the capability route does it."""
    repository.transition_state(record.skill_id, record.version, "human_reviewed")
    repository.transition_state(record.skill_id, record.version, "active")


def _playbooks(legacy_db: Path) -> list[tuple[int, str, list]]:
    with get_connection(legacy_db) as conn:
        return [
            (int(r["skill_id"]), str(r["status"]), json.loads(r["steps_json"]))
            for r in conn.execute(
                "SELECT skill_id, status, steps_json FROM compiled_playbooks ORDER BY id"
            )
        ]


class TestWithoutTheGateNothingChanges:
    def test_a_legacy_promoted_reflex_replays(self, world) -> None:
        _, cerebellum, _, _, _ = world
        assert cerebellum.match(GOAL) is not None


class TestThePilotGate:
    def test_a_legacy_promoted_reflex_is_withheld_and_says_why(self, world) -> None:
        legacy_db, cerebellum, bus, _, dual = world
        cerebellum.attach_reflex_gate(dual.institutional)
        assert cerebellum.match(GOAL) is None
        assert "pilot: skill not operator-activated" in bus.reasons()
        # Withheld, not retired: the playbook itself is untouched.
        assert [status for _, status, _ in _playbooks(legacy_db)] == ["compiled"]

    def test_the_operators_activation_lets_it_replay(self, world) -> None:
        _, cerebellum, _, repository, dual = world
        cerebellum.attach_reflex_gate(dual.institutional)
        _activate(repository, _migrated(repository))
        assert cerebellum.match(GOAL) is not None

    def test_it_replays_only_the_steps_that_were_activated(self, world) -> None:
        legacy_db, cerebellum, bus, repository, dual = world
        cerebellum.attach_reflex_gate(dual.institutional)
        _activate(repository, _migrated(repository))
        # The legacy store refreshes a recipe in place; the compiled reflex now
        # does something the operator never activated.
        with get_connection(legacy_db) as conn:
            conn.execute(
                "UPDATE compiled_playbooks SET steps_json = ?",
                (
                    json.dumps(
                        [
                            {
                                "tool_name": "execute_terminal",
                                "args": {"command": "pytest -q"},
                            }
                        ]
                    ),
                ),
            )
        assert cerebellum.match(GOAL) is None
        assert "pilot: skill not operator-activated" in bus.reasons()

    def test_a_legacy_promotion_compiles_nothing(self, world) -> None:
        legacy_db, cerebellum, _, _, dual = world
        cerebellum.attach_reflex_gate(dual.institutional)
        dual.legacy.record_attempt(
            "list the files in the docs directory",
            ["read_directory: path=docs"],
            success=True,
        )
        for _ in range(3):
            dual.record_attempt(
                "list the files in the docs directory",
                ["read_directory: path=docs"],
                success=True,
            )
        assert cerebellum.try_compile_all() == 0
        assert len(_playbooks(legacy_db)) == 1, "only the pre-pilot reflex exists"

    def test_it_compiles_the_activated_procedure_not_the_legacy_row(
        self, world
    ) -> None:
        legacy_db, cerebellum, _, repository, dual = world
        with get_connection(legacy_db) as conn:
            conn.execute("DELETE FROM compiled_playbooks")
            conn.execute(
                "UPDATE procedural_skills SET steps_json = ?",
                (json.dumps(["read_file: filepath=other.py"]),),
            )
        cerebellum.attach_reflex_gate(dual.institutional)
        assert cerebellum.try_compile_all() == 0, "nothing is active yet"
        record = _migrated(repository)
        _activate(repository, record)
        assert cerebellum.try_compile_all() == 1
        (_, status, steps) = _playbooks(legacy_db)[0]
        assert status == "compiled"
        assert steps == [{"tool_name": "verify", "args": {"command": STEPS[0][16:]}}]
        assert cerebellum.match(GOAL) is not None

    def test_a_library_only_skill_waits_for_the_schema_change(self, world) -> None:
        legacy_db, cerebellum, _, repository, dual = world
        with get_connection(legacy_db) as conn:
            conn.execute("DELETE FROM compiled_playbooks")
        library_id = dual.institutional.record_attempt(
            "read the changelog", ["read_file: filepath=CHANGELOG.md"], success=True
        )
        live = next(
            r for r in repository.list_skills() if r.provenance.get("source") == "live"
        )
        _activate(repository, live)
        cerebellum.attach_reflex_gate(dual.institutional)
        assert library_id in dual.institutional.active_procedures()
        assert cerebellum.try_compile_all() == 0
        assert _playbooks(legacy_db) == []

    def test_an_unreadable_library_activates_nothing(self, world) -> None:
        _, cerebellum, _, repository, dual = world
        _activate(repository, _migrated(repository))

        class Broken:
            def active_procedures(self):
                raise OSError("library unreadable")

        cerebellum.attach_reflex_gate(Broken())
        assert cerebellum.match(GOAL) is None
        assert cerebellum.try_compile_all() == 0

    def test_the_gate_cannot_be_replaced_once_attached(self, world) -> None:
        _, cerebellum, _, _, dual = world
        cerebellum.attach_reflex_gate(dual.institutional)

        class Everything:
            def active_procedures(self):
                return {1: {"steps": STEPS}}

        cerebellum.attach_reflex_gate(Everything())
        assert cerebellum.match(GOAL) is None


class TestTheBootWiresItFromTheSlotActuallyBuilt:
    @pytest.fixture()
    def migrated_library(self, tmp_path: Path, monkeypatch) -> Path:
        legacy_db = tmp_path / "source.db"
        init_memory_db(legacy_db)
        memory = SkillMemory(legacy_db)
        for _ in range(3):
            memory.record_attempt(GOAL, STEPS, success=True)
        operational = tmp_path / "operational.db"
        mig.run(
            source=legacy_db,
            target=operational,
            backup_dir=tmp_path / "backups",
            do_apply=True,
        )
        monkeypatch.setattr(config, "OPERATIONAL_STATE_DB_PATH", operational)
        return operational

    def test_pilot_attaches_the_gate(self, migrated_library, monkeypatch) -> None:
        monkeypatch.setattr(config, "SKILL_STORE_MODE", "pilot")
        authority = build_memory_authority()
        skills = authority.adapters["skills"]
        assert isinstance(skills, DualWriteSkillAdapter)
        assert authority.adapters["cerebellum"].store._reflex_gate is (
            skills.institutional
        )

    def test_shadow_reads_legacy_so_no_gate(
        self, migrated_library, monkeypatch
    ) -> None:
        monkeypatch.setattr(config, "SKILL_STORE_MODE", "shadow")
        authority = build_memory_authority()
        assert authority.adapters["cerebellum"].store._reflex_gate is None

    def test_a_pilot_that_refused_to_start_gates_nothing(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setattr(config, "OPERATIONAL_STATE_DB_PATH", tmp_path / "empty.db")
        monkeypatch.setattr(config, "SKILL_STORE_MODE", "pilot")
        authority = build_memory_authority()
        assert type(authority.adapters["skills"]) is SkillMemoryAdapter
        assert authority.adapters["cerebellum"].store._reflex_gate is None

    def test_the_default_boot_gates_nothing(self) -> None:
        assert config.SKILL_STORE_MODE == "legacy"
        authority = build_memory_authority()
        assert authority.adapters["cerebellum"].store._reflex_gate is None
