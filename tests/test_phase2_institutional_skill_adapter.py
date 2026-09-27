"""Phase 2 slice 2.4a: the institutional library can serve the live ``skills`` slot.

The adapter is built, not wired: nothing on the live path calls it yet. These
tests pin that it speaks the slot's interface in the legacy shapes, and that it
keeps the operator's rules while doing so -- nothing promotes itself, recall and
reuse credit read only what the operator activated, demotion is organ 43's, a
reviewed contract is never rewritten, and the stop freezes every write but never
blinds a read.
"""

from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aios.application.governance.emergency_stop import (
    EmergencyStopController,
    EmergencyStopError,
    EmergencyStopHooks,
)
from aios.application.memory.adapters import SkillMemoryAdapter
from aios.application.memory.institutional_skills import (
    InstitutionalSkillAdapter,
    SkillTrailIndex,
)
from aios.core.verification_strength import VerificationStrength
from aios.domain.governance.contracts import EmergencyStopRequest
from aios.domain.learning.repository import SkillRecord, SkillRepository
from aios.domain.memory.contracts import MemoryRecallContext
from aios.memory import learning_freeze
from aios.memory.db import init_memory_db
from aios.memory.skills import SkillMemory

GOAL = "run the parser tests and report the result"
STEPS = ["verify: command=pytest tests/test_parser.py -q"]


def _noop(*_a, **_k):
    return None


@pytest.fixture()
def world(tmp_path: Path, monkeypatch):
    latch = tmp_path / "emergency_stop.db"
    monkeypatch.setattr(learning_freeze, "_latch_path", lambda: latch)
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    legacy_db = tmp_path / "memory.db"
    init_memory_db(legacy_db)
    operational = tmp_path / "operational.db"
    repository = SkillRepository(operational)
    adapter = InstitutionalSkillAdapter(
        repository, SkillTrailIndex(operational), legacy=SkillMemory(legacy_db)
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
                reason="institutional adapter freeze test",
            )
        )

    return adapter, repository, engage


def _only(repository: SkillRepository) -> SkillRecord:
    records = repository.list_skills()
    assert len(records) == 1, records
    return records[0]


def _activate(repository: SkillRepository, record: SkillRecord) -> None:
    """The operator's path: reviewed, then activated -- never by the adapter."""
    repository.transition_state(record.skill_id, record.version, "human_reviewed")
    repository.transition_state(record.skill_id, record.version, "active")


class TestItSpeaksTheSlotsInterface:
    def test_every_legacy_operation_exists(self) -> None:
        legacy = {
            name
            for name, member in inspect.getmembers(
                SkillMemoryAdapter, inspect.isfunction
            )
            if not name.startswith("_")
        }
        ours = {
            name
            for name, member in inspect.getmembers(
                InstitutionalSkillAdapter, inspect.isfunction
            )
            if not name.startswith("_")
        }
        assert legacy <= ours, sorted(legacy - ours)
        assert InstitutionalSkillAdapter.memory_types == SkillMemoryAdapter.memory_types

    def test_the_legacy_store_stays_attached_for_authority_routing(self, world) -> None:
        """owns_store() routes callers through the authority only when the slot's
        store is the production SkillMemory; without it they would bypass."""
        adapter, _, _ = world
        assert isinstance(adapter.store, SkillMemory)


class TestNothingPromotesItself:
    def test_an_arc_is_born_a_candidate_with_live_provenance(self, world) -> None:
        adapter, repository, _ = world
        trail = adapter.record_attempt(GOAL, STEPS, success=True)
        assert isinstance(trail, int)
        record = _only(repository)
        assert record.state == "candidate"
        assert record.provenance["source"] == "live"
        assert json.loads(record.procedure) == STEPS

    def test_many_strong_successes_leave_it_a_review_ready_candidate(
        self, world
    ) -> None:
        adapter, repository, _ = world
        for _ in range(10):
            adapter.record_attempt(GOAL, STEPS, success=True)
        record = _only(repository)
        assert record.state == "candidate", "the adapter must never activate"
        assert record.success_count == 10
        assert adapter.relevant_verified(GOAL, 3) == []
        trails = adapter.trail_map()["trails"]
        assert trails[0]["review_ready"] is True and trails[0]["status"] == "candidate"

    def test_the_same_arc_keeps_its_trail_id(self, world) -> None:
        adapter, _, _ = world
        first = adapter.record_attempt(GOAL, STEPS, success=True)
        again = adapter.record_attempt(GOAL, STEPS, success=False)
        assert first == again

    def test_a_weak_success_is_not_evidence(self, world) -> None:
        adapter, repository, _ = world
        adapter.record_attempt(GOAL, STEPS, success=True)
        adapter.record_attempt(
            GOAL, STEPS, success=True, strength=VerificationStrength.WEAK
        )
        record = _only(repository)
        assert (record.success_count, record.failure_count) == (1, 0)

    def test_a_retired_arc_starts_a_new_version(self, world) -> None:
        adapter, repository, _ = world
        adapter.record_attempt(GOAL, STEPS, success=True)
        first = _only(repository)
        repository.transition_state(first.skill_id, first.version, "deprecated")
        adapter.record_attempt(GOAL, STEPS, success=True)
        versions = sorted(r.version for r in repository.list_skills())
        assert versions == [1, 2]


class TestIdentityStaysAnInteger:
    def test_a_legacy_id_is_honoured(self, world) -> None:
        adapter, _, _ = world
        assert adapter.record_attempt(GOAL, STEPS, success=True, legacy_id=66) == 66

    def test_a_taken_id_is_never_reused(self, world) -> None:
        adapter, _, _ = world
        first = adapter.record_attempt(GOAL, STEPS, success=True, legacy_id=66)
        other = adapter.record_attempt(
            "a different goal entirely",
            ["read_file: filepath=b.py"],
            success=True,
            legacy_id=66,
        )
        assert first == 66 and other != 66

    def test_a_fresh_id_lands_above_every_adopted_id(self, world) -> None:
        adapter, _, _ = world
        adapter.record_attempt(GOAL, STEPS, success=True, legacy_id=500)
        fresh = adapter.record_attempt(
            "another goal", ["read_file: filepath=c.py"], success=True
        )
        assert fresh > 500

    def test_migrated_skills_keep_their_legacy_ids(self, world) -> None:
        adapter, repository, _ = world
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        repository.save(
            SkillRecord(
                skill_id="arc-migrated",
                version=1,
                problem_signature="migrated goal",
                applicability_conditions={},
                known_exclusions=[],
                required_inputs=[],
                required_project_state={},
                procedure=json.dumps(STEPS),
                allowed_tools=["verify"],
                allowed_scope_pattern="",
                expected_observations=[],
                verification_plan=None,
                escalation_conditions=[],
                source_trajectory_ids=[],
                confidence=0.8,
                success_count=4,
                failure_count=0,
                last_validated_versions=[],
                state="candidate",
                created_at=now,
                updated_at=now,
                provenance={"source": "migrated", "legacy_id": "41"},
            )
        )
        assert adapter.trails.adopt_migrated(repository) == [41]
        assert adapter.trails.adopt_migrated(repository) == [41]  # idempotent


class TestRecallAndReuseReadOnlyWhatTheOperatorActivated:
    def test_an_active_skill_is_recalled_in_the_legacy_shape(self, world) -> None:
        adapter, repository, _ = world
        trail = adapter.record_attempt(GOAL, STEPS, success=True)
        _activate(repository, _only(repository))
        rows = adapter.relevant_verified("run the parser tests", 3)
        assert len(rows) == 1
        row = rows[0]
        assert row["skill_id"] == trail and isinstance(row["skill_id"], int)
        assert row["steps"] == STEPS and row["strength"] > 0 and row["relevance"] > 0
        hit = adapter.recall("run the parser tests", MemoryRecallContext(limit=3))[0]
        assert hit.external_id == trail and hit.source == "institutional_skills"

    def test_reuse_credits_active_skills_only(self, world) -> None:
        adapter, repository, _ = world
        trail = adapter.record_attempt(GOAL, STEPS, success=True)
        assert adapter.record_reuse([trail], success=True) == []  # still a candidate
        _activate(repository, _only(repository))
        assert adapter.record_reuse([trail], success=True) == [trail]
        assert adapter.trail_map()["trails"][0]["reuse_success_count"] == 1

    def test_an_active_skill_that_keeps_failing_is_demoted_by_organ_43(
        self, world
    ) -> None:
        adapter, repository, _ = world
        trail = adapter.record_attempt(GOAL, STEPS, success=True)
        _activate(repository, _only(repository))
        for _ in range(4):
            adapter.record_reuse([trail], success=False)
        record = _only(repository)
        assert record.state in {"degraded", "suspended"}
        assert adapter.relevant_verified(GOAL, 3) == [], (
            "a demoted skill is not recalled"
        )


class TestAReviewedContractIsNeverRewritten:
    """Same arc (same goal, same tool sequence), a recipe with fewer redaction
    artifacts: the legacy store refreshes it in place."""

    WORSE = ["verify: command=pytest <REDACTED:path> -q"]

    def test_a_candidate_recipe_is_still_refined(self, world) -> None:
        adapter, repository, _ = world
        adapter.record_attempt(GOAL, self.WORSE, success=True)
        adapter.record_attempt(GOAL, STEPS, success=True)
        assert json.loads(_only(repository).procedure) == STEPS

    def test_an_active_skills_procedure_is_left_alone(self, world) -> None:
        adapter, repository, _ = world
        adapter.record_attempt(GOAL, self.WORSE, success=True)
        _activate(repository, _only(repository))
        adapter.record_attempt(GOAL, STEPS, success=True)
        record = _only(repository)
        assert json.loads(record.procedure) == self.WORSE, "the approved recipe stands"
        assert record.success_count == 2, "the evidence still counts"


class TestTheStopFreezesWritesButNeverBlindsReads:
    def test_an_attempt_is_refused_and_nothing_is_written(self, world) -> None:
        adapter, repository, engage = world
        engage()
        with pytest.raises(EmergencyStopError):
            adapter.record_attempt(GOAL, STEPS, success=True)
        assert repository.list_skills() == ()
        assert adapter.trails.all() == {}

    def test_reuse_is_refused_and_the_counters_do_not_move(self, world) -> None:
        adapter, repository, engage = world
        trail = adapter.record_attempt(GOAL, STEPS, success=True)
        _activate(repository, _only(repository))
        engage()
        with pytest.raises(EmergencyStopError):
            adapter.record_reuse([trail], success=True)
        assert adapter.trail_map()["trails"][0]["reuse_success_count"] == 0

    def test_reads_still_answer_under_the_stop(self, world) -> None:
        """Including with a skill the adapter never saw (no trail yet): it is
        left out rather than written, so the read does not fail (#375)."""
        adapter, repository, engage = world
        adapter.record_attempt(GOAL, STEPS, success=True)
        tracked = _only(repository)
        repository.save(tracked.model_copy(update={"skill_id": "untracked"}))
        engage()
        view = adapter.trail_map()
        assert [t["institutional"]["skill_id"] for t in view["trails"]] == [
            tracked.skill_id
        ]
        assert adapter.relevant_verified(GOAL, 3) == []
        assert [r["institutional"]["skill_id"] for r in adapter.list()] == [
            tracked.skill_id
        ]


def _record(**overrides: object) -> SkillRecord:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    fields: dict[str, object] = dict(
        skill_id="arc-review",
        version=1,
        problem_signature="review readiness probe",
        applicability_conditions={},
        known_exclusions=[],
        required_inputs=[],
        required_project_state={},
        procedure=json.dumps(STEPS),
        allowed_tools=["verify"],
        allowed_scope_pattern="",
        expected_observations=[],
        verification_plan=None,
        escalation_conditions=[],
        source_trajectory_ids=[],
        confidence=0.8,
        success_count=3,
        failure_count=0,
        last_validated_versions=[],
        state="candidate",
        created_at=now,
        updated_at=now,
        provenance={},
    )
    fields.update(overrides)
    return SkillRecord(**fields)


class TestOneDefinitionOfReviewReady:
    """The scoreboard said 11 while the migration and the activation tool said
    8: two definitions of "ready". One derivation now serves every caller."""

    def _r(self, state="candidate", ok=3, bad=0, **prov):
        return _record(
            state=state, success_count=ok, failure_count=bad, provenance=prov
        )

    def test_a_live_candidate_meeting_the_rule_is_ready(self) -> None:
        from aios.application.memory.institutional_skills import is_review_ready

        assert is_review_ready(self._r(source="live"))
        assert not is_review_ready(self._r(ok=2, source="live"))
        assert not is_review_ready(self._r(ok=3, bad=2, source="live"))

    def test_a_quarantined_migrated_arc_is_not_ready(self) -> None:
        from aios.application.memory.institutional_skills import is_review_ready

        assert not is_review_ready(
            self._r(ok=4, source="migrated", review_ready="false")
        )
        assert is_review_ready(self._r(ok=4, source="migrated", review_ready="true"))

    def test_a_migrated_arc_that_since_failed_is_not_ready(self) -> None:
        from aios.application.memory.institutional_skills import is_review_ready

        assert not is_review_ready(
            self._r(ok=4, bad=5, source="migrated", review_ready="true")
        )

    def test_only_a_candidate_can_be_ready(self) -> None:
        from aios.application.memory.institutional_skills import is_review_ready

        assert not is_review_ready(self._r(state="active", ok=9, source="live"))

    def test_the_trail_map_uses_it(self, world) -> None:
        adapter, repository, _ = world
        repository.save(
            _record(
                skill_id="arc-quarantined",
                success_count=4,
                provenance={
                    "source": "migrated",
                    "legacy_id": "45",
                    "review_ready": "false",
                },
            )
        )
        (row,) = [
            t
            for t in adapter.trail_map()["trails"]
            if t["institutional"]["skill_id"] == "arc-quarantined"
        ]
        assert row["review_ready"] is False
