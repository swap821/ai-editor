"""Plan Phase 4c-2: skills and reflexes belong to a principal, on a signature.

Operator decisions: principal scoping covers everything, skills included
(2026-09-29); a row learned before scoping is withheld from everyone until
re-earned or re-admitted (2026-10-04).

Phase 3b deferred signing the skill library "until slice 2.4c-B landed", and
it was never built: until this slice a skill carried no signature at all, so a
database edit could activate one. Here the operator's activation is the trust
root:

* the activation route signs the skill's contract and state, naming its
  principal and the operator as approver;
* every transition journals an unsigned record, so a skill demoted after its
  activation can never be flipped back to ``active`` on the old signature;
* recall, reuse credit and reflex replay admit an active skill only on that
  signature, and only for the principal it names;
* the same arc learned by two principals is two skills.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from aios import config
from aios.application.memory.institutional_skills import (
    InstitutionalSkillAdapter,
    SkillTrailIndex,
    skill_identity,
)
from aios.application.memory.provenance_policy import ProvenanceWriter, RecallGate
from aios.application.memory.reflex_contract import stamp_for_activation
from aios.core.cerebellum import Cerebellum
from aios.core.verification_strength import VerificationStrength
from aios.domain.learning.repository import (
    SKILL_PROVENANCE_TABLE,
    SkillRecord,
    SkillRepository,
    skill_principal,
    skill_row_id,
)
from aios.memory import learning_freeze
from aios.memory.db import get_connection, init_memory_db
from aios.memory.provenance import LearningSigner, LearningVerifier, ProvenanceStore
from aios.memory.relevance import skill_signature_v2
from aios.security import scope_lock

ALICE = "principal:alice"
BOB = "principal:bob"
OPERATOR = "operator:swap"
GOAL = "show the release notes"
STEPS = ["read_file: filepath=notes.md"]


def _seed() -> str:
    return (
        Ed25519PrivateKey.generate()
        .private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        .hex()
    )


class World:
    def __init__(self, root: Path) -> None:
        self.project = root / "project"
        self.memory_db = root / "memory.sqlite"
        self.operational = root / "operational.sqlite"
        init_memory_db(self.memory_db)
        self.repository = SkillRepository(self.operational)
        signer = LearningSigner({"live": _seed()})
        verifier = LearningVerifier({"live": [signer.public_keys()["live"]]})
        self.store = ProvenanceStore(self.operational)
        self.gate = RecallGate(self.store, verifier, context="live")
        self.library = InstitutionalSkillAdapter(
            self.repository,
            SkillTrailIndex(self.operational),
            provenance=ProvenanceWriter(
                self.store, signer, source_kind="live", verifier=verifier
            ),
            gate=self.gate,
        )
        self.cerebellum = Cerebellum(self.memory_db)
        self.cerebellum.attach_reflex_gate(self.library)

    def earn(self, principal: Any, goal: str = GOAL, steps=STEPS) -> int:
        trail = 0
        for _ in range(3):
            trail = self.library.record_attempt(
                goal,
                steps,
                success=True,
                strength=VerificationStrength.STRONG,
                principal=principal,
            )
        return trail

    def record(self, principal: Any, goal: str = GOAL) -> SkillRecord:
        (record,) = [
            r
            for r in self.repository.list_skills()
            if r.problem_signature == goal and skill_principal(r) == principal
        ]
        return record

    def activate(self, principal: Any, goal: str = GOAL, *, sign: bool = True) -> bool:
        record = self.record(principal, goal)
        self.repository.transition_state(
            record.skill_id, record.version, "human_reviewed"
        )
        self.repository.transition_state(record.skill_id, record.version, "active")
        signed = (
            self.library.attest_activation(
                record.skill_id, record.version, approver=OPERATOR
            )
            if sign
            else False
        )
        self.cerebellum.try_compile_all()
        return signed

    def live(self, principal: Any, goal: str = GOAL, steps=STEPS) -> int:
        trail = self.earn(principal, goal, steps)
        assert self.activate(principal, goal), "positive control: the activation signed"
        return trail

    def recalled(self, principal: Any, goal: str = GOAL) -> list[int]:
        return [
            int(r["skill_id"])
            for r in self.library.relevant_verified(goal, 5, principal=principal)
        ]

    def edit_payload(self, record: SkillRecord, **changes: Any) -> None:
        """A database-level edit, outside every store (threat T11)."""
        payload = record.model_dump(mode="json") | changes
        with sqlite3.connect(self.operational) as conn:
            conn.execute(
                "UPDATE institutional_skills SET payload_json = ? "
                "WHERE skill_id = ? AND version = ?",
                (json.dumps(payload, sort_keys=True), record.skill_id, record.version),
            )

    def compiled(self) -> int:
        with get_connection(self.memory_db) as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM compiled_playbooks WHERE status = 'compiled'"
                ).fetchone()[0]
            )


@pytest.fixture
def world(tmp_path, monkeypatch) -> World:
    monkeypatch.setattr(
        learning_freeze, "_latch_path", lambda: tmp_path / "emergency_stop.db"
    )
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    project = tmp_path / "project"
    (project / "training_ground").mkdir(parents=True)
    monkeypatch.setattr(config, "PROJECT_ROOT", project)
    original = scope_lock.get_scope_roots()
    scope_lock.set_scope_roots([project / "training_ground"])
    w = World(tmp_path)
    (project / "notes.md").write_text("release notes v1\n", encoding="utf-8")
    try:
        yield w
    finally:
        scope_lock.set_scope_roots(list(original))


# ------------------------------------------------------------ recall


class TestASkillIsRecalledForItsPrincipalOnly:
    def test_an_activated_skill_reaches_its_principal_and_no_one_else(
        self, world
    ) -> None:
        trail = world.live(ALICE)
        assert world.recalled(ALICE) == [trail], "positive control"
        assert world.recalled(BOB) == []
        assert world.gate.refused.get("another principal", 0) >= 1

    def test_a_recall_naming_no_one_recalls_no_skill(self, world) -> None:
        world.live(ALICE)
        assert world.recalled(None) == []
        assert world.gate.refused.get("no principal", 0) >= 1

    def test_a_skill_learned_before_scoping_is_withheld_from_everyone(
        self, world
    ) -> None:
        """Signed, active, and naming no one: only the missing name refuses it."""
        world.earn(None)
        assert world.activate(None)
        assert world.recalled(ALICE) == [] and world.recalled(None) == []
        assert world.gate.refused.get("unattributed", 0) >= 1


class TestTheSameArcFromTwoPrincipalsIsTwoSkills:
    def test_two_records_each_with_its_own_evidence(self, world) -> None:
        a = world.earn(ALICE)
        b = world.earn(BOB)
        assert a != b
        alice, bob = world.record(ALICE), world.record(BOB)
        assert alice.skill_id != bob.skill_id
        assert (alice.success_count, bob.success_count) == (3, 3)

    def test_the_identity_hashes_the_principal_in(self) -> None:
        signature = skill_signature_v2(GOAL, STEPS)
        assert skill_identity(signature, None) == f"arc-{signature}"
        assert skill_identity(signature, ALICE) != skill_identity(signature, BOB)
        assert skill_identity(signature, ALICE).startswith("arc-")
        assert ALICE not in skill_identity(signature, ALICE)

    def test_another_principals_turn_never_credits_or_stains_a_skill(
        self, world
    ) -> None:
        trail = world.live(ALICE)
        before = world.record(ALICE)
        for _ in range(6):
            assert (
                world.library.record_reuse([trail], success=False, principal=BOB) == []
            )
        after = world.record(ALICE)
        assert (after.state, after.failure_count) == ("active", before.failure_count)
        assert world.library.record_reuse([trail], success=True, principal=ALICE) == [
            trail
        ]


# ------------------------------------------------------------ the signature


class TestOnlyTheOperatorsSignedActivationCounts:
    def test_a_skill_activated_in_the_database_is_never_recalled_or_replayed(
        self, world
    ) -> None:
        """Every transition the activation makes, with no signature: the shape
        of a database edit, or of any code path that is not the route."""
        world.earn(ALICE)
        assert world.activate(ALICE, sign=False) is False
        assert world.record(ALICE).state == "active"
        assert world.recalled(ALICE) == []
        assert world.compiled() == 0
        assert world.cerebellum.match(GOAL, principal=ALICE) is None
        assert world.gate.refused.get("unsigned", 0) >= 1

    def test_a_demoted_skill_flipped_back_in_the_database_is_refused(
        self, world
    ) -> None:
        trail = world.live(ALICE)
        assert world.library.withdraw_reflex_source(trail)
        suspended = world.record(ALICE)
        assert suspended.state == "suspended"
        world.edit_payload(suspended, state="active")
        assert world.record(ALICE).state == "active"
        assert world.recalled(ALICE) == []

    def test_a_contract_edited_in_the_database_is_refused(self, world) -> None:
        world.live(ALICE)
        world.edit_payload(
            world.record(ALICE), procedure=json.dumps(["verify: command=echo pwned"])
        )
        assert world.recalled(ALICE) == []
        assert world.gate.refused.get("content changed since it was signed", 0) >= 1

    def test_evidence_after_the_activation_keeps_the_signature(self, world) -> None:
        trail = world.live(ALICE)
        world.library.record_reuse([trail], success=True, principal=ALICE)
        assert world.record(ALICE).success_count == 4
        assert world.recalled(ALICE) == [trail]

    def test_every_transition_is_journalled(self, world) -> None:
        world.earn(ALICE)
        record = world.record(ALICE)
        row = skill_row_id(record.skill_id, record.version)

        def records() -> list[tuple[str, bool]]:
            with sqlite3.connect(world.operational) as conn:
                rows = conn.execute(
                    "SELECT provenance_json, signature FROM learning_provenance "
                    "WHERE row_table = ? AND row_id = ? ORDER BY id",
                    (SKILL_PROVENANCE_TABLE, row),
                ).fetchall()
            return [(json.loads(p)["transition"], bool(s)) for p, s in rows]

        world.activate(ALICE)
        world.repository.transition_state(record.skill_id, record.version, "suspended")
        assert records() == [
            ("state:human_reviewed", False),
            ("state:active", False),
            ("activated", True),
            ("state:suspended", False),
        ]

    def test_only_an_active_skills_activation_is_signed(self, world) -> None:
        world.earn(ALICE)
        record = world.record(ALICE)
        with pytest.raises(ValueError, match="only an active skill"):
            world.library.attest_activation(
                record.skill_id, record.version, approver=OPERATOR
            )


# ------------------------------------------------------------ reflexes


class TestAReflexReplaysForItsPrincipalOnly:
    def test_alices_reflex_never_fires_in_bobs_turn(self, world) -> None:
        world.live(ALICE)
        assert world.compiled() == 1
        assert world.cerebellum.match(GOAL, principal=ALICE) is not None, (
            "positive control"
        )
        assert world.cerebellum.match(GOAL, principal=BOB) is None
        assert world.cerebellum.match(GOAL, principal=None) is None

    def test_another_principals_reflex_never_makes_a_match_ambiguous(
        self, world
    ) -> None:
        """Both learned the same arc: two equally good reflexes. Without
        scoping that is an abstention ("ambiguous"); each principal's own is
        the only candidate in their turn."""
        alice = world.live(ALICE)
        bob = world.live(BOB)
        assert world.compiled() == 2
        assert world.cerebellum.match(GOAL, principal=ALICE).skill_id == alice
        assert world.cerebellum.match(GOAL, principal=BOB).skill_id == bob


# ------------------------------------------------------------ attribution


def _candidate(**provenance: str) -> SkillRecord:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return SkillRecord(
        skill_id="arc-migrated",
        version=1,
        problem_signature="run the parser tests",
        applicability_conditions={},
        known_exclusions=[],
        required_inputs=[],
        required_project_state={},
        procedure=json.dumps(["verify: command=pytest tests/test_parser.py -q"]),
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
        provenance={"source": "migrated", **provenance},
    )


class TestTheOperatorsActivationSaysWhoseItIs:
    def test_an_unattributed_candidate_becomes_the_activators(self) -> None:
        stamped = stamp_for_activation(_candidate(), activator=OPERATOR)
        assert skill_principal(stamped) == OPERATOR

    def test_a_skill_that_is_someones_keeps_its_principal(self) -> None:
        stamped = stamp_for_activation(_candidate(principal=ALICE), activator=OPERATOR)
        assert skill_principal(stamped) == ALICE

    def test_a_procedure_that_is_not_an_arc_is_attributed_too(self) -> None:
        candidate = _candidate().model_copy(update={"procedure": "do the thing"})
        stamped = stamp_for_activation(candidate, activator=OPERATOR)
        assert skill_principal(stamped) == OPERATOR


def test_the_activation_route_attributes_and_signs(tmp_path, monkeypatch) -> None:
    """End to end through the real action guard (session, 428 challenge,
    server-issued capability): an unattributed migrated candidate becomes the
    activating operator's, the activation is signed, and recall admits it for
    them only."""
    from fastapi.testclient import TestClient
    from types import SimpleNamespace

    from aios.api.deps import get_learning_service, get_memory_authority
    from aios.api.main import app
    from aios.application.learning.service import LearningService
    from aios.application.missions.mission_service import MissionService
    from aios.core.autonomy import UNGOVERNED_FIXTURE
    from aios.domain.learning.trajectory_repository import TrajectoryRepository
    from aios.infrastructure.missions.sqlite_mission_repository import (
        SqliteMissionRepository,
    )
    from tests.helpers import client_principal_id

    monkeypatch.setattr(
        learning_freeze, "_latch_path", lambda: tmp_path / "emergency_stop.db"
    )
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    w = World(tmp_path)
    w.repository.save(_candidate())
    service = LearningService(
        mission_service=MissionService(
            SqliteMissionRepository(tmp_path / "missions.db"),
            emergency_stop=UNGOVERNED_FIXTURE,
        ),
        trajectory_repository=TrajectoryRepository(w.operational),
        skill_repository=w.repository,
        emergency_stop=UNGOVERNED_FIXTURE,
    )
    app.dependency_overrides[get_learning_service] = lambda: service
    app.dependency_overrides[get_memory_authority] = lambda: SimpleNamespace(
        adapters={"skills": w.library}
    )
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            response = client.post(
                "/api/v1/skills/arc-migrated/versions/1/activate", json={}
            )
            caller = client_principal_id(client)
    finally:
        app.dependency_overrides.pop(get_learning_service, None)
        app.dependency_overrides.pop(get_memory_authority, None)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["state"], body["principal"], body["signed"]) == (
        "active",
        caller,
        True,
    )
    query = "run the parser tests"
    assert [
        r["institutional"]["skill_id"]
        for r in w.library.relevant_verified(query, 5, principal=caller)
    ] == ["arc-migrated"]
    assert w.library.relevant_verified(query, 5, principal=BOB) == []


def test_without_the_live_key_an_activation_is_not_signed(
    tmp_path, monkeypatch
) -> None:
    """The route reports what happened: an activation in a process that holds
    no live seed is recorded unsigned, says so, and the skill stays inert."""
    monkeypatch.setattr(
        learning_freeze, "_latch_path", lambda: tmp_path / "emergency_stop.db"
    )
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    w = World(tmp_path)
    live = LearningSigner({"live": _seed()})
    harness_only = LearningSigner({"harness": _seed()})
    verifier = LearningVerifier({"live": [live.public_keys()["live"]]})
    w.library.provenance = ProvenanceWriter(
        w.store, harness_only, source_kind="live", verifier=verifier
    )
    w.earn(ALICE)
    assert w.activate(ALICE) is False
    assert w.recalled(ALICE) == []


def test_the_legacy_history_is_never_recalled_by_anyone(tmp_path) -> None:
    """``scoped_skill_recall``: the legacy store names no principal."""
    from aios.memory.skills import SkillMemory, scoped_skill_recall

    db = tmp_path / "memory.db"
    init_memory_db(db)
    legacy = SkillMemory(db_path=db)
    for _ in range(3):
        legacy.record_attempt(
            GOAL, STEPS, success=True, strength=VerificationStrength.STRONG
        )
    assert legacy.relevant_verified(GOAL, 3), "positive control: it is verified there"
    assert scoped_skill_recall(legacy, GOAL, 3, principal=ALICE) == []


def test_without_a_gate_a_recall_naming_no_one_gets_nothing(
    tmp_path, monkeypatch
) -> None:
    """An adapter with no gate (a unit test's) still scopes on the record's
    principal: an unattributed skill asked for by no one is not "a match"."""
    monkeypatch.setattr(
        learning_freeze, "_latch_path", lambda: tmp_path / "emergency_stop.db"
    )
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    repository = SkillRepository(tmp_path / "op.sqlite")
    library = InstitutionalSkillAdapter(
        repository, SkillTrailIndex(tmp_path / "op.sqlite")
    )
    for _ in range(3):
        library.record_attempt(
            GOAL,
            STEPS,
            success=True,
            strength=VerificationStrength.STRONG,
            principal=None,
        )
    (record,) = repository.list_skills()
    repository.transition_state(record.skill_id, record.version, "human_reviewed")
    repository.transition_state(record.skill_id, record.version, "active")
    assert library.relevant_verified(GOAL, 3, principal=None) == []
    assert library.relevant_verified(GOAL, 3, principal=ALICE) == []
