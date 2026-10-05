"""Phase 2: reflexes read the store recall reads -- the skill library, only.

A reflex is the one learned behaviour that runs with no model in the loop. It
replays only if its skill is ACTIVE in the institutional library and its steps
are exactly the activated procedure. Since slice 2.4c-B that gate is the only
source: a cerebellum without it compiles and replays nothing, and ``bootstrap.py``
always attaches it. (Before, the #395 pilot attached it only in ``pilot`` mode,
and the legacy store's self-promoted skills compiled everywhere else.)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aios import config
from aios.application.memory.bootstrap import build_memory_authority
from aios.application.memory.institutional_skills import (
    InstitutionalSkillAdapter,
    SkillTrailIndex,
    build_skills_slot,
)
from aios.core.cerebellum import Cerebellum
from aios.core.verification_strength import VerificationStrength
from aios.domain.learning.repository import SkillRepository
from aios.application.memory.reflex_contract import stamp_for_activation
from aios.memory import learning_freeze
from aios.memory.db import get_connection, init_memory_db
from aios.memory.skills import SkillMemory
from tools import migrate_skills_to_institutional as mig

GOAL = "run the parser tests and report the result"
#: A test file that exists: since plan Phase 5b a reflex's verification plan
#: must be executable, so its target must be real.
STEPS = ["verify: command=pytest tests/test_cerebellum.py -q"]


class Bus:
    def __init__(self) -> None:
        self.events: list = []

    def append(self, event) -> None:
        self.events.append(event)

    def reasons(self) -> list[str]:
        return [e.payload.get("reason") for e in self.events]


@pytest.fixture()
def world(tmp_path: Path, monkeypatch):
    return build_world(tmp_path, monkeypatch)


def _historic_reflex(legacy_db: Path, cerebellum: Cerebellum) -> None:
    """A reflex compiled BEFORE slice 2.4c-B, from a self-promoted legacy skill.

    No code path can produce one any more, so it is built with the cerebellum's
    own compile guards (`_try_compile_one`) from the legacy row, which is what
    the removed legacy sweep did. The live store still holds such reflexes
    until `tools/retire_legacy_playbooks.py --apply` retires them.
    """
    with get_connection(legacy_db) as conn:
        row = conn.execute(
            "SELECT id, goal_pattern, steps_json, consecutive_failures, signature_v2 "
            "FROM procedural_skills WHERE status = 'verified'"
        ).fetchone()
        assert cerebellum._try_compile_one(row, conn) is not None


def build_world(tmp_path: Path, monkeypatch):
    """Legacy history with a pre-2.4c-B reflex, and the migrated library slot."""
    monkeypatch.setattr(
        learning_freeze, "_latch_path", lambda: tmp_path / "emergency_stop.db"
    )
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    legacy_db = tmp_path / "memory.db"
    init_memory_db(legacy_db)
    # Writable ONLY to create the history a live store already holds.
    history_writer = SkillMemory(legacy_db)
    for _ in range(3):  # the legacy rule promoted it to 'verified'
        history_writer.record_attempt(GOAL, STEPS, success=True)
    cerebellum = Cerebellum(legacy_db)
    bus = Bus()
    cerebellum.attach_bus(bus)
    _historic_reflex(legacy_db, cerebellum)
    operational = tmp_path / "operational.db"
    mig.run(
        source=legacy_db,
        target=operational,
        backup_dir=tmp_path / "backups",
        do_apply=True,
    )
    repository = SkillRepository(operational)
    slot = build_skills_slot(
        repository=repository,
        trails=SkillTrailIndex(operational),
        history=SkillMemory(legacy_db, read_only=True),
    )
    return legacy_db, cerebellum, bus, repository, slot


def _migrated(repository: SkillRepository):
    return next(
        r for r in repository.list_skills() if r.provenance.get("source") == "migrated"
    )


def _activate(repository: SkillRepository, record) -> None:
    """The operator's act, in a test. Live, only the capability route does it,
    and it stamps the reflex contract first (plan Phase 5b), as here."""
    stamped = stamp_for_activation(
        repository.get(record.skill_id, record.version), activator="principal:test"
    )
    repository.save(stamped)
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


class TestWithoutTheLibraryNothingIsAReflex:
    """Slice 2.4c-B: there is no ungated mode left to fall back to."""

    def test_a_self_promoted_reflex_does_not_replay_without_the_gate(
        self, world
    ) -> None:
        legacy_db, cerebellum, _, _, _ = world
        assert [s for _, s, _ in _playbooks(legacy_db)] == ["compiled"]
        assert cerebellum.match(GOAL, principal="principal:test") is None

    def test_nothing_compiles_without_the_gate(self, world) -> None:
        legacy_db, cerebellum, _, _, _ = world
        with get_connection(legacy_db) as conn:
            conn.execute("DELETE FROM compiled_playbooks")
        assert cerebellum.try_compile_all() == 0, "a verified LEGACY row compiled"
        assert cerebellum.try_compile_skill(_playbooks_skill(legacy_db)) is None
        assert _playbooks(legacy_db) == []

    def test_without_the_gate_no_playbook_is_backed(self, world) -> None:
        """``activation_backs`` is what the retirement tool keeps reflexes by.
        Replay is guarded twice without a gate (``_inapplicable`` refuses
        too), so only this read sees a gate-less cerebellum vouch for a
        playbook nobody activated (learning mutation probe, Phase 7)."""
        _, cerebellum, _, _, _ = world
        cerebellum._refresh_cache()
        playbooks = list(cerebellum._cache.values())
        assert playbooks, "positive control: the legacy reflex is compiled"
        assert not any(cerebellum.activation_backs(pb) for pb in playbooks)
        assert cerebellum._activated(compiling=True) == {}
        assert cerebellum._activated(principal="principal:test") == {}


def _playbooks_skill(legacy_db: Path) -> int:
    with get_connection(legacy_db) as conn:
        return int(
            conn.execute(
                "SELECT id FROM procedural_skills WHERE status = 'verified'"
            ).fetchone()["id"]
        )


class TestTheGate:
    def test_a_self_promoted_reflex_is_withheld_and_says_why(self, world) -> None:
        legacy_db, cerebellum, bus, _, slot = world
        cerebellum.attach_reflex_gate(slot)
        assert cerebellum.match(GOAL, principal="principal:test") is None
        assert "skill not operator-activated" in bus.reasons()
        # Withheld, not retired: the playbook itself is untouched.
        assert [status for _, status, _ in _playbooks(legacy_db)] == ["compiled"]

    def test_the_operators_activation_lets_it_replay(self, world) -> None:
        _, cerebellum, _, repository, slot = world
        cerebellum.attach_reflex_gate(slot)
        _activate(repository, _migrated(repository))
        assert cerebellum.match(GOAL, principal="principal:test") is not None

    def test_it_replays_only_the_steps_that_were_activated(self, world) -> None:
        legacy_db, cerebellum, bus, repository, slot = world
        cerebellum.attach_reflex_gate(slot)
        _activate(repository, _migrated(repository))
        # The reflex row now does something the operator never activated.
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
        assert cerebellum.match(GOAL, principal="principal:test") is None
        assert "skill not operator-activated" in bus.reasons()

    def test_evidence_alone_compiles_nothing(self, world) -> None:
        legacy_db, cerebellum, _, _, slot = world
        cerebellum.attach_reflex_gate(slot)
        for _ in range(5):
            slot.record_attempt(
                "list the files in the docs directory",
                ["read_directory: path=docs"],
                success=True,
                strength=VerificationStrength.STRONG,
                principal="principal:test",
            )
        assert cerebellum.try_compile_all() == 0
        assert len(_playbooks(legacy_db)) == 1, "only the pre-2.4c-B reflex exists"

    def test_it_compiles_the_activated_procedure_not_the_legacy_row(
        self, world
    ) -> None:
        legacy_db, cerebellum, _, repository, slot = world
        with get_connection(legacy_db) as conn:
            conn.execute("DELETE FROM compiled_playbooks")
            conn.execute(
                "UPDATE procedural_skills SET steps_json = ?",
                (json.dumps(["read_file: filepath=other.py"]),),
            )
        cerebellum.attach_reflex_gate(slot)
        assert cerebellum.try_compile_all() == 0, "nothing is active yet"
        _activate(repository, _migrated(repository))
        assert cerebellum.try_compile_all() == 1
        (_, status, steps) = _playbooks(legacy_db)[0]
        assert status == "compiled"
        assert steps == [{"tool_name": "verify", "args": {"command": STEPS[0][16:]}}]
        assert cerebellum.match(GOAL, principal="principal:test") is not None

    def test_a_library_only_skill_compiles_once_activated(self, world) -> None:
        """A new arc has no legacy row at all. Before 2.4c-B it waited, first for
        the schema (slice A), then for the legacy row slice B removed the need
        for; the library alone now supplies what a reflex needs."""
        legacy_db, cerebellum, _, repository, slot = world
        with get_connection(legacy_db) as conn:
            conn.execute("DELETE FROM compiled_playbooks")
        library_id = slot.record_attempt(
            "read README.md and report it",
            ["read_file: filepath=README.md"],
            success=True,
            principal="principal:test",
        )
        live = next(
            r for r in repository.list_skills() if r.provenance.get("source") == "live"
        )
        _activate(repository, live)
        cerebellum.attach_reflex_gate(slot)
        assert library_id in slot.active_procedures(principal="principal:test")
        assert cerebellum.try_compile_all() == 1
        assert [skill for skill, _, _ in _playbooks(legacy_db)] == [library_id]
        assert (
            cerebellum.match("read README.md and report it", principal="principal:test")
            is not None
        )

    def test_an_unreadable_library_activates_nothing(self, world) -> None:
        _, cerebellum, _, repository, _ = world
        _activate(repository, _migrated(repository))

        class Broken:
            def active_procedures(self):
                raise OSError("library unreadable")

        cerebellum.attach_reflex_gate(Broken())
        assert cerebellum.match(GOAL, principal="principal:test") is None
        assert cerebellum.try_compile_all() == 0

    def test_the_gate_cannot_be_replaced_once_attached(self, world) -> None:
        _, cerebellum, _, _, slot = world
        cerebellum.attach_reflex_gate(slot)

        class Everything:
            def active_procedures(self):
                return {1: {"steps": STEPS}}

        cerebellum.attach_reflex_gate(Everything())
        assert cerebellum.match(GOAL, principal="principal:test") is None


class TestFailingSkillsAreDemotedByTheLibrary:
    """The cerebellum's own failure-streak guard is gone (slice 2.4c-B): an
    activated skill that keeps failing is demoted by the library's policy
    (organ 43), and a demoted skill's reflex is withheld and never recompiles."""

    def test_a_skill_that_keeps_failing_loses_its_reflex(self, world) -> None:
        legacy_db, cerebellum, bus, repository, slot = world
        with get_connection(legacy_db) as conn:
            conn.execute("DELETE FROM compiled_playbooks")
        cerebellum.attach_reflex_gate(slot)
        record = _migrated(repository)
        _activate(repository, record)
        assert cerebellum.try_compile_all() == 1
        assert cerebellum.match(GOAL, principal="principal:test") is not None, (
            "positive control: it replays"
        )

        trail = next(iter(slot.active_procedures(principal="principal:test")))
        for _ in range(20):
            slot.record_reuse([trail], success=False, principal="principal:test")
            if repository.get(record.skill_id, record.version).state != "active":
                break
        state = repository.get(record.skill_id, record.version).state
        assert state in {"degraded", "suspended"}, f"never demoted: {state}"

        assert cerebellum.match(GOAL, principal="principal:test") is None
        assert "skill not operator-activated" in bus.reasons()
        with get_connection(legacy_db) as conn:
            conn.execute("DELETE FROM compiled_playbooks")
        assert cerebellum.try_compile_all() == 0, "a demoted skill recompiled"


class TestARetiredReflexReturnsOnlyByReactivation:
    """A reflex the machine retires comes back ONLY when the operator
    re-activates its skill (operator decision, 2026-09-29). Retiring it
    suspends the library skill; earning more restores nothing. The library's
    count is still recorded on the row, as bookkeeping."""

    def _compiled(self, world):
        legacy_db, cerebellum, _, repository, slot = world
        with get_connection(legacy_db) as conn:
            conn.execute("DELETE FROM compiled_playbooks")
        cerebellum.attach_reflex_gate(slot)
        record = _migrated(repository)
        _activate(repository, record)
        assert cerebellum.try_compile_all() == 1
        return legacy_db, cerebellum, repository, slot, record

    def _mark(self, legacy_db: Path):
        with get_connection(legacy_db) as conn:
            return conn.execute(
                "SELECT status, decompiled_at_successes FROM compiled_playbooks"
            ).fetchone()

    def _reactivate(self, repository, record) -> None:
        """The operator's re-activation, in a test: live, only the
        capability-backed route does it (suspended -> human_reviewed -> active)."""
        repository.transition_state(record.skill_id, record.version, "human_reviewed")
        repository.transition_state(record.skill_id, record.version, "active")

    def test_decompiling_suspends_the_skill_and_retires_the_row(self, world) -> None:
        legacy_db, cerebellum, repository, slot, record = self._compiled(world)
        library_count = repository.get(record.skill_id, record.version).success_count
        [pb] = list(cerebellum._cache.values())
        cerebellum.decompile(pb.id)
        status, mark = self._mark(legacy_db)
        assert status == "retired" and mark == library_count
        assert repository.get(record.skill_id, record.version).state == "suspended"

    def test_earning_more_does_not_bring_it_back_reactivation_does(self, world) -> None:
        legacy_db, cerebellum, repository, slot, record = self._compiled(world)
        [pb] = list(cerebellum._cache.values())
        cerebellum.invalidate_for_skill(pb.skill_id)
        assert cerebellum.try_compile_all() == 0, "nothing re-activated"
        for _ in range(3):
            slot.record_attempt(
                GOAL,
                STEPS,
                success=True,
                strength=VerificationStrength.STRONG,
                principal="principal:test",
            )
        assert cerebellum.try_compile_all() == 0, "earning is not re-activation"
        self._reactivate(repository, record)
        assert cerebellum.try_compile_all() == 1
        assert [s for _, s, _ in _playbooks(legacy_db)] == ["retired", "compiled"]

    def test_two_replay_failures_also_suspend_the_skill(self, world) -> None:
        legacy_db, cerebellum, repository, _, record = self._compiled(world)
        [pb] = list(cerebellum._cache.values())
        for _ in range(cerebellum.max_consecutive_failures):
            cerebellum._record_replay_failure(pb.id)
        status, mark = self._mark(legacy_db)
        assert status == "retired"
        assert mark == repository.get(record.skill_id, record.version).success_count
        assert repository.get(record.skill_id, record.version).state == "suspended"


class TestTheBootAlwaysGates:
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

    def test_the_boot_serves_the_library_and_gates_reflexes_with_it(
        self, migrated_library
    ) -> None:
        authority = build_memory_authority()
        skills = authority.adapters["skills"]
        assert type(skills) is InstitutionalSkillAdapter
        assert authority.adapters["cerebellum"].store._reflex_gate is skills
        assert skills.store.read_only is True, "legacy history must be read-only"

    def test_a_fresh_install_is_gated_too(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(config, "OPERATIONAL_STATE_DB_PATH", tmp_path / "new.db")
        authority = build_memory_authority()
        skills = authority.adapters["skills"]
        assert type(skills) is InstitutionalSkillAdapter
        assert authority.adapters["cerebellum"].store._reflex_gate is skills

    @pytest.mark.parametrize("mode", ["legacy", "shadow"])
    def test_the_old_mode_setting_is_inert(
        self, migrated_library, monkeypatch, mode
    ) -> None:
        monkeypatch.setenv("AIOS_SKILL_STORE_MODE", mode)
        authority = build_memory_authority()
        skills = authority.adapters["skills"]
        assert type(skills) is InstitutionalSkillAdapter
        assert authority.adapters["cerebellum"].store._reflex_gate is skills
        assert not hasattr(config, "SKILL_STORE_MODE")
