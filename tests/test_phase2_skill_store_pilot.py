"""Phase 2 slice 2.4b: the skill-store pilot, off by default.

``AIOS_SKILL_STORE_MODE`` chooses what serves the live ``skills`` slot:
``legacy`` (the default, exactly as before), ``shadow`` (legacy reads, writes to
both stores) or ``pilot`` (institutional reads of ACTIVE skills, writes to both).
The legacy store stays authoritative for writes; the institutional write never
breaks a turn, and its failures are counted where the operator can see them. A
non-legacy mode refuses to start until the skill migration has been applied.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from aios import config
from aios.application.governance.emergency_stop import (
    EmergencyStopController,
    EmergencyStopError,
    EmergencyStopHooks,
)
from aios.application.memory.adapters import SkillMemoryAdapter
from aios.application.memory.bootstrap import build_memory_authority
from aios.application.memory.institutional_skills import (
    LIBRARY_ID_BASE,
    DualWriteSkillAdapter,
    SkillTrailIndex,
    build_skills_slot,
)
from aios.core.verification_strength import VerificationStrength
from aios.domain.governance.contracts import EmergencyStopRequest
from aios.domain.learning.repository import SkillRepository
from aios.memory import learning_freeze
from aios.memory.db import init_memory_db
from aios.memory.skills import SkillMemory
from tools import migrate_skills_to_institutional as mig

VERIFIED_GOAL = "run the parser tests and report the result"
VERIFIED_STEPS = ["verify: command=pytest tests/test_parser.py -q"]
NEW_GOAL = "list the files in the docs directory"
NEW_STEPS = ["read_directory: path=docs"]


def _noop(*_a, **_k):
    return None


@pytest.fixture()
def world(tmp_path: Path, monkeypatch):
    latch = tmp_path / "emergency_stop.db"
    monkeypatch.setattr(learning_freeze, "_latch_path", lambda: latch)
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    legacy_db = tmp_path / "memory.db"
    init_memory_db(legacy_db)
    legacy = SkillMemoryAdapter(SkillMemory(legacy_db))
    for _ in range(3):  # promoted to 'verified' by the legacy rule
        legacy.record_attempt(VERIFIED_GOAL, VERIFIED_STEPS, success=True)
    operational = tmp_path / "operational.db"
    repository = SkillRepository(operational)
    trails = SkillTrailIndex(operational)

    def migrate() -> None:
        mig.run(
            source=legacy_db,
            target=operational,
            backup_dir=tmp_path / "backups",
            do_apply=True,
        )

    def slot(mode: str):
        return build_skills_slot(
            legacy, mode=mode, repository=repository, trails=trails
        )

    def engage() -> None:
        EmergencyStopController(
            latch,
            hooks=EmergencyStopHooks(
                revoke_capabilities=_noop,
                cancel_queued_missions=_noop,
                kill_active_workers=_noop,
                disable_autonomy=_noop,
                preserve_evidence=_noop,
            ),
        ).engage(
            EmergencyStopRequest(
                operator_id="operator:test",
                authentication_event_id="event:engage",
                reason="skill pilot freeze test",
            )
        )

    return legacy, repository, migrate, slot, engage


def _verified_legacy_id(legacy: SkillMemoryAdapter) -> int:
    return int(legacy.list(status="verified")[0]["id"])


class TestTheDefaultChangesNothing:
    def test_the_default_mode_is_legacy(self) -> None:
        assert config.SKILL_STORE_MODE == "legacy"

    def test_the_default_boot_serves_the_legacy_adapter_itself(self) -> None:
        slot = build_memory_authority().adapters["skills"]
        assert type(slot) is SkillMemoryAdapter

    def test_legacy_mode_returns_the_same_object(self, world) -> None:
        legacy, _, _, slot, _ = world
        assert slot("legacy") is legacy


class TestItRefusesToStartWrong:
    def test_an_unknown_mode_stays_legacy_and_says_so(self, world, caplog) -> None:
        legacy, _, migrate, slot, _ = world
        migrate()
        with caplog.at_level(logging.ERROR):
            assert slot("pilott") is legacy
        assert "unknown AIOS_SKILL_STORE_MODE" in caplog.text

    @pytest.mark.parametrize("mode", ["shadow", "pilot"])
    def test_no_dual_write_before_the_migration(self, world, caplog, mode) -> None:
        legacy, _, _, slot, _ = world
        with caplog.at_level(logging.ERROR):
            assert slot(mode) is legacy
        assert "needs the skill migration applied first" in caplog.text

    @pytest.mark.parametrize("mode", ["shadow", "pilot"])
    def test_positive_control_it_starts_after_the_migration(self, world, mode) -> None:
        legacy, _, migrate, slot, _ = world
        migrate()
        dual = slot(mode)
        assert isinstance(dual, DualWriteSkillAdapter)
        assert dual.store is legacy.store, "owns_store() routing must still hold"


class TestShadow:
    def test_writes_reach_both_stores_under_one_id(self, world) -> None:
        legacy, repository, migrate, slot, _ = world
        migrate()
        dual = slot("shadow")
        # Put the two id counters out of step, as they will be once the library
        # holds skills the legacy store never issued an id for (mission
        # trajectories): agreement must come from the hand-off, not coincidence.
        dual.institutional.trails.trail_for("arc-unrelated", 1)
        new_id = dual.record_attempt(NEW_GOAL, NEW_STEPS, success=True)
        assert new_id == int(legacy.list(status="candidate")[0]["id"])
        live = [
            r for r in repository.list_skills() if r.provenance.get("source") == "live"
        ]
        assert len(live) == 1
        assert (
            dual.institutional.trails.trail_for(live[0].skill_id, live[0].version)
            == new_id
        )

    def test_a_migrated_arc_keeps_its_legacy_id_in_both(self, world) -> None:
        legacy, repository, migrate, slot, _ = world
        migrate()
        dual = slot("shadow")
        legacy_id = _verified_legacy_id(legacy)
        assert (
            dual.record_attempt(VERIFIED_GOAL, VERIFIED_STEPS, success=True)
            == legacy_id
        )
        migrated = [
            r
            for r in repository.list_skills()
            if r.provenance.get("source") == "migrated"
        ]
        assert migrated[0].success_count == 4, (
            "the institutional record got the evidence"
        )

    def test_reads_come_from_legacy(self, world) -> None:
        legacy, _, migrate, slot, _ = world
        migrate()
        dual = slot("shadow")

        # Compare WHAT is recalled, not the scores: freshness decays with the
        # clock, so two calls a moment apart can round differently.
        def recalled(rows):
            return [(r["skill_id"], r["goal_pattern"], r["steps"]) for r in rows]

        assert recalled(dual.relevant_verified(VERIFIED_GOAL, 3)) == recalled(
            legacy.relevant_verified(VERIFIED_GOAL, 3)
        )
        assert dual.relevant_verified(VERIFIED_GOAL, 3), (
            "legacy still recalls its verified arc"
        )

    def test_an_institutional_failure_never_breaks_the_turn(
        self, world, monkeypatch
    ) -> None:
        legacy, _, migrate, slot, _ = world
        migrate()
        dual = slot("shadow")

        def boom(*_a, **_k):
            raise RuntimeError("institutional store unavailable")

        monkeypatch.setattr(dual.institutional, "record_attempt", boom)
        assert isinstance(dual.record_attempt(NEW_GOAL, NEW_STEPS, success=True), int)
        pilot = dual.trail_map()["pilot"]
        assert pilot["shadow_failures"] == 1
        assert "institutional store unavailable" in pilot["last_shadow_failure"]

    def test_the_stop_refuses_the_turns_write_and_touches_neither(self, world) -> None:
        legacy, repository, migrate, slot, engage = world
        migrate()
        dual = slot("shadow")
        before = len(repository.list_skills())
        engage()
        with pytest.raises(EmergencyStopError):
            dual.record_attempt(NEW_GOAL, NEW_STEPS, success=True)
        assert len(repository.list_skills()) == before
        assert legacy.list(status="candidate") == []


class TestTheTwoIdRangesNeverMeet:
    """Reuse credit travels by integer id to BOTH stores. An id the library
    issued from the legacy range would later name a different legacy skill,
    and credit for one would land on another's row."""

    def test_a_library_issued_id_is_outside_the_legacy_range(self, world) -> None:
        _, _, migrate, slot, _ = world
        migrate()
        dual = slot("shadow")
        assert (
            dual.institutional.trails.trail_for("arc-library-only", 1)
            >= LIBRARY_ID_BASE
        )

    def test_credit_for_a_library_only_skill_touches_no_legacy_row(self, world) -> None:
        legacy, repository, migrate, slot, _ = world
        migrate()
        dual = slot("pilot")
        library_id = dual.institutional.record_attempt(
            NEW_GOAL, NEW_STEPS, success=True
        )
        record = next(
            r for r in repository.list_skills() if r.provenance.get("source") == "live"
        )
        repository.transition_state(record.skill_id, record.version, "human_reviewed")
        repository.transition_state(record.skill_id, record.version, "active")
        # A verified legacy skill created AFTER the library issued its id: with
        # one shared range it would sit at that very id.
        for _ in range(3):
            legacy.record_attempt(
                "read the changelog", ["read_file: filepath=CHANGELOG.md"], success=True
            )
        legacy_before = [(r["id"], r["reuse_success_count"]) for r in legacy.list()]
        assert dual.record_reuse([library_id], success=True) == [library_id]
        assert [
            (r["id"], r["reuse_success_count"]) for r in legacy.list()
        ] == legacy_before


class TestPilot:
    def test_recall_reads_only_what_the_operator_activated(self, world) -> None:
        legacy, repository, migrate, slot, _ = world
        migrate()
        dual = slot("pilot")
        assert legacy.relevant_verified(VERIFIED_GOAL, 3), "legacy calls it verified"
        assert dual.relevant_verified(VERIFIED_GOAL, 3) == [], (
            "institutional: a candidate"
        )
        migrated = next(
            r
            for r in repository.list_skills()
            if r.provenance.get("source") == "migrated"
        )
        repository.transition_state(
            migrated.skill_id, migrated.version, "human_reviewed"
        )
        repository.transition_state(migrated.skill_id, migrated.version, "active")
        rows = dual.relevant_verified(VERIFIED_GOAL, 3)
        assert [r["skill_id"] for r in rows] == [_verified_legacy_id(legacy)]

    def test_reuse_credits_both_and_reports_the_institutional_credit(
        self, world
    ) -> None:
        legacy, repository, migrate, slot, _ = world
        migrate()
        dual = slot("pilot")
        legacy_id = _verified_legacy_id(legacy)
        assert dual.record_reuse([legacy_id], success=True) == [], "not yet activated"
        migrated = next(
            r
            for r in repository.list_skills()
            if r.provenance.get("source") == "migrated"
        )
        repository.transition_state(
            migrated.skill_id, migrated.version, "human_reviewed"
        )
        repository.transition_state(migrated.skill_id, migrated.version, "active")
        assert dual.record_reuse([legacy_id], success=True) == [legacy_id]
        legacy_row = legacy.list(status="verified")[0]
        assert int(legacy_row["reuse_success_count"]) == 2, "legacy credited both times"

    def test_the_trail_map_says_which_store_is_speaking(self, world) -> None:
        _, _, migrate, slot, _ = world
        migrate()
        view = slot("pilot").trail_map()
        assert view["pilot"] == {
            "mode": "pilot",
            "reads": "institutional",
            "shadow_failures": 0,
            "last_shadow_failure": None,
        }
        assert view["store"] == "institutional_skills"

    def test_a_weak_success_is_not_evidence_in_either(self, world) -> None:
        legacy, repository, migrate, slot, _ = world
        migrate()
        dual = slot("pilot")
        dual.record_attempt(
            VERIFIED_GOAL,
            VERIFIED_STEPS,
            success=True,
            strength=VerificationStrength.WEAK,
        )
        migrated = next(
            r
            for r in repository.list_skills()
            if r.provenance.get("source") == "migrated"
        )
        assert migrated.success_count == 3
