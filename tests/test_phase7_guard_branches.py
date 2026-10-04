"""Plan Phase 7: guard branches the learning mutation probe found untested.

``scripts/learning_mutation_probe.py`` forced every decision point of the
named guards both ways. Each test here exists because one of those mutations
SURVIVED the guard's whole test suite: the branch could be broken and nothing
noticed. Named after what the branch protects, not after the mutation.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from aios.application.memory.provenance_policy import ProvenanceWriter
from aios.application.memory.write_budget import (
    LearningWriteBudget,
    LearningWriteCapExceeded,
)
from aios.domain.learning.repository import SkillRecord, SkillRepository
from aios.memory import learning_freeze
from aios.memory.db import init_memory_db
from aios.memory.provenance import LearningSigner, LearningVerifier, ProvenanceStore
from tools import readmit_learning as readmit


def _seed() -> str:
    return (
        Ed25519PrivateKey.generate()
        .private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        .hex()
    )


@pytest.fixture
def frozen_latch(tmp_path, monkeypatch):
    monkeypatch.setattr(
        learning_freeze, "_latch_path", lambda: tmp_path / "emergency_stop.db"
    )
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    return tmp_path


def _record(state: str = "candidate") -> SkillRecord:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return SkillRecord(
        skill_id="arc-branch",
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
        confidence=0.5,
        success_count=1,
        failure_count=0,
        last_validated_versions=[],
        state=state,
        created_at=now,
        updated_at=now,
        provenance={},
    )


class TestTheSkillStoreRefusesHonestly:
    def test_a_new_skill_saved_straight_into_active_is_refused_and_says_so(
        self, frozen_latch
    ) -> None:
        """Threat T17 (activation by write), for a NEW record: refused, and
        the refusal says it was new -- the operator reads this message."""
        repository = SkillRepository(frozen_latch / "op.sqlite")
        with pytest.raises(ValueError, match="from a new skill"):
            repository.save(_record("active"))
        assert repository.get("arc-branch", 1) is None
        repository.save(_record())
        with pytest.raises(ValueError, match="from state 'candidate'"):
            repository.save(_record("active"))

    def test_a_transition_of_an_unknown_skill_is_a_key_error(
        self, frozen_latch
    ) -> None:
        repository = SkillRepository(frozen_latch / "op.sqlite")
        with pytest.raises(KeyError, match="not found"):
            repository.transition_state("arc-nowhere", 1, "human_reviewed")


def test_an_approval_that_names_no_approver_signs_nothing(frozen_latch) -> None:
    """Plan Phase 4c-2: the operator's activation is signed as an APPROVAL --
    with no prior signed state required -- so it must name who approved."""
    db = frozen_latch / "memory.db"
    init_memory_db(db)
    signer = LearningSigner({"live": _seed()})
    store = ProvenanceStore(db)
    writer = ProvenanceWriter(
        store,
        signer,
        source_kind="live",
        verifier=LearningVerifier({"live": [signer.public_keys()["live"]]}),
    )
    for approver in ("", "   ", None):
        with pytest.raises(ValueError, match="approver"):
            writer.attest_approval(
                "institutional_skills",
                "arc-x@1",
                "0" * 64,
                "activated",
                approver=approver,
            )
    assert store.latest("institutional_skills", "arc-x@1") is None


def test_status_names_an_unsigned_legacy_row_unsigned(frozen_latch) -> None:
    """The operator chooses what to re-admit from this listing: an unsigned
    legacy row must say ``unsigned``, not ``unattributed`` (which means signed
    by no principal, and is re-admitted differently)."""
    db = frozen_latch / "memory.db"
    init_memory_db(db)
    with sqlite3.connect(db) as conn:
        lid = conn.execute(
            "INSERT INTO mistake_pool (task_id, error_type, root_cause, fix_applied, "
            "lesson_text, confidence_delta, verification_status) "
            "VALUES ('t', 'E', 'c', 'f', 'legacy lesson', -0.1, 'verified')"
        ).lastrowid
    signer = LearningSigner({"live": _seed()})
    verifier = LearningVerifier({"live": [signer.public_keys()["live"]]})
    listed = readmit.status(db, ProvenanceStore(db), verifier)["mistake_pool"]
    assert [(r["id"], r["reason"]) for r in listed] == [(lid, "unsigned")]


def test_the_cap_logs_its_refusal_once_per_table(caplog) -> None:
    """Every refusal is counted; the operator's log says so ONCE per table,
    not once per refused write (a flood would bury everything else)."""
    budget = LearningWriteBudget(1, clock=lambda: 1000.0)
    budget.spend("mistake_pool")
    budget.spend("semantic_memory")
    with caplog.at_level(
        logging.WARNING, logger="aios.application.memory.write_budget"
    ):
        for _ in range(3):
            with pytest.raises(LearningWriteCapExceeded):
                budget.spend("mistake_pool")
        with pytest.raises(LearningWriteCapExceeded):
            budget.spend("semantic_memory")
    warnings = [
        r.getMessage() for r in caplog.records if "write cap reached" in r.getMessage()
    ]
    assert len(warnings) == 2
    assert any("mistake_pool" in w for w in warnings)
    assert any("semantic_memory" in w for w in warnings)
    assert budget.status()["refused"] == {"mistake_pool": 3, "semantic_memory": 1}


def test_the_probe_file_names_this_module() -> None:
    """Keeps the cross-reference honest: the probe's catalogue names these
    tests for the branches they cover."""
    catalogue = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "learning_mutation_catalogue.json"
        ).read_text(encoding="utf-8")
    )
    named = {t for e in catalogue["entries"] for t in e["tests"]}
    assert any("test_phase7_guard_branches.py" in t for t in named)


# ------------------------------------------------------------ facts (T16)


@pytest.fixture
def facts_store(frozen_latch):
    from aios.memory.facts import SemanticFacts

    db = frozen_latch / "memory.db"
    init_memory_db(db)
    return SemanticFacts(db)


def _fact_rows(store) -> list[tuple]:
    with sqlite3.connect(store.db_path) as conn:
        return conn.execute(
            "SELECT subject, predicate, object, approved_by, confidence FROM semantic_facts"
        ).fetchall()


class TestTheHumanApprovedFactsChannel:
    def test_an_empty_triple_is_never_written(self, facts_store) -> None:
        for triple in (
            ("", "uses", "x"),
            ("router", "", "x"),
            ("router", "uses", "   "),
        ):
            result = facts_store.add_fact(*triple, approved_by="op")
            assert (result.committed, result.reason) == (
                False,
                "empty subject/predicate/object",
            )
        assert _fact_rows(facts_store) == []

    def test_approving_a_known_fact_records_its_approver(self, facts_store) -> None:
        """Recall admits only human-approved facts: approving one that was
        learned unapproved must record WHO approved it, on the same row."""
        facts_store.add_fact("router", "uses", "FastAPI", confidence=0.3)
        again = facts_store.add_fact("router", "uses", "FastAPI", confidence=0.4)
        assert again.reason == "already present"
        assert _fact_rows(facts_store) == [("router", "uses", "FastAPI", None, 0.3)], (
            "an unapproved repeat changes nothing"
        )
        approved = facts_store.add_fact(
            "router", "uses", "FastAPI", approved_by="op", confidence=0.9
        )
        assert approved.committed
        assert _fact_rows(facts_store) == [("router", "uses", "FastAPI", "op", 0.9)]

    def test_a_proposal_needs_an_approver(self, facts_store) -> None:
        proposal = facts_store.propose("operator", "prefers", "tea")
        for nobody in ("", "   "):
            refused = facts_store.approve_proposal(
                proposal.proposal_id, approved_by=nobody
            )
            assert (refused.committed, refused.reason) == (False, "approver required")
        assert [p["status"] for p in facts_store.pending_proposals()] == ["pending"]
        assert _fact_rows(facts_store) == []

    def test_only_a_pending_proposal_can_be_approved(self, facts_store) -> None:
        proposal = facts_store.propose("operator", "prefers", "tea")
        assert facts_store.reject_proposal(proposal.proposal_id, rejected_by="op")
        late = facts_store.approve_proposal(proposal.proposal_id, approved_by="op")
        assert (late.committed, late.reason) == (False, "not pending")
        missing = facts_store.approve_proposal(99999, approved_by="op")
        assert (missing.committed, missing.reason) == (False, "not pending")
        assert _fact_rows(facts_store) == []

    def test_a_contradicting_proposal_stays_pending(self, facts_store) -> None:
        """A contradiction is returned, not committed, and the proposal waits
        for an explicit human reconcile; a committed one is marked approved."""
        facts_store.add_fact("project", "uses", "FastAPI", approved_by="op")
        clash = facts_store.propose("project", "uses", "Flask")
        result = facts_store.approve_proposal(clash.proposal_id, approved_by="op")
        assert (result.committed, result.reason) == (False, "contradiction")
        assert [p["object"] for p in facts_store.pending_proposals()] == ["Flask"]
        fine = facts_store.propose("project", "serves", "api")
        assert facts_store.approve_proposal(
            fine.proposal_id, approved_by="op"
        ).committed
        assert [p["object"] for p in facts_store.pending_proposals()] == ["Flask"]


# ------------------------------------------------------------ reflex replay


def _agent(**kwargs):
    from aios.agents.tool_agent import ToolAgent
    from aios.core.autonomy import UNGOVERNED_FIXTURE
    from aios.core.executor import Executor
    from aios.security.gateway import RateLimiter

    return ToolAgent(
        object(),
        Executor(
            runner=lambda *a, **k: ("", "", 0),
            rate_limiter=RateLimiter(),
            audit_log=lambda *a, **k: None,
            emergency_stop=UNGOVERNED_FIXTURE,
        ),
        max_iters=1,
        audit_log=lambda *a, **k: None,
        **kwargs,
    )


class TestAReplayedWriteHasOnePath:
    WRITE = {"filepath": "notes.md", "content_sha256": "0" * 64, "content": "x"}

    def test_a_replayed_write_goes_through_the_approved_bytes_check(self) -> None:
        """Not the ordinary write path, which would ask a human mid-reflex:
        a replayed write runs only on a human approval of these exact bytes."""
        output, status, _ = _agent()._dispatch_approved("create_file", dict(self.WRITE))
        assert status == "blocked" and "no human has approved" in output

    def test_a_replayed_edit_goes_through_its_own_check(self) -> None:
        """The same for an edit: the replay's own check refuses it (by name),
        not the ordinary edit path."""
        output, status, _ = _agent()._dispatch_approved(
            "edit_file", {"filepath": "notes.md", "old_string": "a", "new_string": "b"}
        )
        assert status == "blocked"
        assert "replayed edit" in output or "this exact edit" in output, output

    def test_a_role_restricted_agent_never_reaches_the_write_replay(self) -> None:
        """The replay writes through its own path, not ``_dispatch``, so the
        role's tool list must be enforced before it."""
        output, status, _ = _agent(
            allowed_tools=frozenset({"read_file"})
        )._dispatch_approved("create_file", dict(self.WRITE))
        assert status == "blocked" and "not permitted for the current role" in output


def test_after_the_composition_cap_reads_still_run() -> None:
    """Plan Phase 5c: the cap holds COMMANDS that would run unattended. A read
    runs no command and is never held, however many commands ran."""
    from aios.agents import recall_envelope

    agent = _agent()
    agent._reflex_in_turn = True
    agent._unattended_commands = recall_envelope.UNATTENDED_COMMAND_CAP
    assert agent._composition_capped("execute_terminal", {"command": "echo hi"}), (
        "positive control: a GREEN command is held at the cap"
    )
    assert not agent._composition_capped("read_file", {"filepath": "README.md"})
    assert not agent._composition_capped("read_directory", {"path": "."})


# ------------------------------------------------------------ recall adapters


@pytest.fixture
def stores(frozen_latch):
    """Real stores in one database, signing and gating like production."""
    from types import SimpleNamespace

    from aios.application.memory.adapters import (
        LegacySemanticMemoryAdapter,
        MistakeMemoryAdapter,
        SemanticFactsAdapter,
    )
    from aios.application.memory.provenance_policy import RecallGate
    from aios.memory.facts import SemanticFacts
    from aios.memory.mistake import MistakeMemory
    from aios.memory.semantic import SemanticMemory

    class Embedder:
        def encode(self, text):
            return [[0.0, 1.0]]

    class Index:
        def reload(self):
            pass

        def add(self, *a):
            pass

        def persist(self):
            pass

    db = frozen_latch / "memory.db"
    init_memory_db(db)
    signer = LearningSigner({"live": _seed()})
    verifier = LearningVerifier({"live": [signer.public_keys()["live"]]})
    store = ProvenanceStore(db)
    writer = ProvenanceWriter(store, signer, source_kind="live", verifier=verifier)
    gate = RecallGate(store, verifier, context="live")
    semantic_store = SemanticMemory(db, index=Index(), embedder=Embedder())
    return SimpleNamespace(
        db=db,
        semantic=LegacySemanticMemoryAdapter(
            semantic_store, provenance=writer, gate=gate
        ),
        ungated_semantic=LegacySemanticMemoryAdapter(semantic_store),
        lessons=MistakeMemoryAdapter(
            MistakeMemory(db_path=db), provenance=writer, gate=gate
        ),
        facts=SemanticFactsAdapter(SemanticFacts(db), provenance=writer, gate=gate),
        ungated_facts=SemanticFactsAdapter(SemanticFacts(db)),
    )


PRINCIPAL = "principal:branches"


class TestSemanticRecall:
    def _memory(self, stores, text: str) -> int:
        mem = stores.semantic.add(
            text,
            memory_type="fact",
            verification_status="verified",
            principal=PRINCIPAL,
        )
        stores.semantic.promote(mem, principal=PRINCIPAL)
        return int(mem)

    def test_an_id_less_hit_is_skipped_not_fatal(self, stores) -> None:
        """A retrieval hit with no row id cannot prove where it came from: it
        is refused -- and the rest of the recall still happens."""
        from types import SimpleNamespace

        from aios.domain.memory import MemoryRecallContext

        mem = self._memory(stores, "release notes live in docs")
        hits = stores.semantic.recall(
            "release notes",
            MemoryRecallContext(limit=5, principal_id=PRINCIPAL),
            retrieval_fn=lambda q, top_k: [
                SimpleNamespace(id=None, text="no row"),
                SimpleNamespace(id=mem, text="release notes live in docs"),
            ],
        )
        assert [h.external_id for h in hits] == [mem]

    def test_a_project_scoped_recall_returns_no_semantic_memory(self, stores) -> None:
        from types import SimpleNamespace

        from aios.domain.memory import MemoryRecallContext

        mem = self._memory(stores, "release notes live in docs")
        hits = stores.semantic.recall(
            "release notes",
            MemoryRecallContext(limit=5, principal_id=PRINCIPAL, project_id="p1"),
            retrieval_fn=lambda q, top_k: [SimpleNamespace(id=mem, text="x")],
        )
        assert hits == ()

    def test_the_gate_overfetches_and_cuts_back_to_the_limit(self, stores) -> None:
        from types import SimpleNamespace

        from aios.application.memory.adapters import _GATED_OVERFETCH
        from aios.domain.memory import MemoryRecallContext

        mems = [self._memory(stores, f"release note {i}") for i in range(5)]
        asked: list[int] = []

        def retrieval(q, top_k):
            asked.append(top_k)
            return [SimpleNamespace(id=m, text="x") for m in mems]

        context = MemoryRecallContext(limit=2, principal_id=PRINCIPAL)
        gated = stores.semantic.recall("release", context, retrieval_fn=retrieval)
        assert asked[-1] == 2 * _GATED_OVERFETCH and len(gated) == 2
        ungated = stores.ungated_semantic.recall(
            "release", context, retrieval_fn=retrieval
        )
        assert asked[-1] == 2, "no gate, no overfetch"
        assert [h.external_id for h in ungated] == mems, (
            "no gate: unfiltered, as before"
        )

    def test_a_hit_names_its_row(self, stores) -> None:
        """``content_reference`` is how a recalled line maps back to its row
        (the approval surface's provenance, T15): the row id when there is one,
        the position only when there is none."""
        from types import SimpleNamespace

        from aios.domain.memory import MemoryRecallContext

        hits = stores.ungated_semantic.recall(
            "x",
            MemoryRecallContext(limit=5),
            retrieval_fn=lambda q, top_k: [
                SimpleNamespace(id=41, text="a"),
                SimpleNamespace(id=None, text="b"),
            ],
        )
        assert [h.content_reference for h in hits] == [
            "semantic_memory:41",
            "semantic_memory:1",
        ]


def test_lesson_recall_never_returns_more_than_its_limit(stores) -> None:
    from aios.core.verification_strength import VerificationStrength

    for i in range(5):
        lid, _ = stores.lessons.record_or_increment(
            task_id="t",
            error_type=f"PinError{i}",
            root_cause="the pin missed an edge",
            fix_applied="pin the edge",
            lesson_text=f"pin the parser edge {i}",
            confidence_delta=-0.1,
            failed_command="",
            principal=PRINCIPAL,
        )
        stores.lessons.promote(
            lid, strength=VerificationStrength.STRONG, principal=PRINCIPAL
        )
    assert (
        len(
            stores.lessons.relevant_verified(
                "pin the parser edge", 2, principal=PRINCIPAL
            )
        )
        == 2
    )


class TestFactsWithoutAGate:
    """A unit test's adapter (no gate) reads as before: ungated."""

    def test_facts_for_reads_every_row(self, stores) -> None:
        stores.ungated_facts.add_fact("router", "uses", "FastAPI", principal=PRINCIPAL)
        rows = stores.ungated_facts.facts_for("router", principal=PRINCIPAL)
        assert [r["object"] for r in rows] == ["FastAPI"]

    def test_every_asked_triple_is_admitted(self, stores) -> None:
        asked = [("router", "uses", "FastAPI"), ("router", "never", "written")]
        assert stores.ungated_facts._admitted_triples(asked, PRINCIPAL) == set(asked)


# ------------------------------------------------------------ the skill library


def _library(root: Path):
    from aios.application.memory.institutional_skills import (
        InstitutionalSkillAdapter,
        SkillTrailIndex,
    )

    repository = SkillRepository(root / "op.sqlite")
    return InstitutionalSkillAdapter(repository, SkillTrailIndex(root / "op.sqlite"))


def _active_skill_without_a_trail(
    library, principal: str, skill_id: str = "arc-notrail"
) -> None:
    """An ACTIVE skill written outside the adapter (a mission-trajectory
    candidate, activated): it has no trail id until a read assigns one."""
    record = _record().model_copy(
        update={"skill_id": skill_id, "provenance": {"principal": principal}}
    )
    library.repository.save(record)
    library.repository.transition_state(skill_id, 1, "human_reviewed")
    library.repository.transition_state(skill_id, 1, "active")


class TestTheSkillLibraryReads:
    def test_a_non_positive_limit_recalls_nothing(self, frozen_latch) -> None:
        # Two skills: a negative limit sliced as ranked[:-1] would still
        # return one, so the guard (not the slice) is what this pins.
        library = _library(frozen_latch)
        _active_skill_without_a_trail(library, PRINCIPAL)
        _active_skill_without_a_trail(library, PRINCIPAL, "arc-notrail-2")
        assert (
            len(
                library.relevant_verified(
                    "run the parser tests", 3, principal=PRINCIPAL
                )
            )
            == 2
        )
        for limit in (0, -1):
            assert (
                library.relevant_verified(
                    "run the parser tests", limit, principal=PRINCIPAL
                )
                == []
            )

    def test_a_read_under_the_stop_skips_what_it_cannot_number(
        self, frozen_latch
    ) -> None:
        """Numbering a skill (its trail id) is a write, which the stop
        refuses; a READ must not fail under the stop (#375), so the skill is
        left out of this recall rather than blinding it."""
        from aios.application.governance.emergency_stop import (
            EmergencyStopController,
            EmergencyStopHooks,
        )
        from aios.domain.governance.contracts import EmergencyStopRequest

        library = _library(frozen_latch)
        _active_skill_without_a_trail(library, PRINCIPAL)

        def noop(*_a, **_k):
            return None

        stop = EmergencyStopController(
            frozen_latch / "emergency_stop.db",
            hooks=EmergencyStopHooks(
                revoke_capabilities=noop,
                cancel_queued_missions=noop,
                kill_active_workers=noop,
                disable_autonomy=noop,
                preserve_evidence=noop,
            ),
        )
        stop.engage(
            EmergencyStopRequest(
                operator_id="operator:test",
                authentication_event_id="event:engage",
                reason="a read under the stop",
            )
        )
        assert stop.is_engaged()
        assert (
            library.relevant_verified("run the parser tests", 3, principal=PRINCIPAL)
            == []
        )

    def test_positive_control_without_the_stop_it_is_recalled(
        self, frozen_latch
    ) -> None:
        library = _library(frozen_latch)
        _active_skill_without_a_trail(library, PRINCIPAL)
        assert (
            len(
                library.relevant_verified(
                    "run the parser tests", 3, principal=PRINCIPAL
                )
            )
            == 1
        )

    def test_reuse_credit_for_an_unknown_trail_is_nothing(self, frozen_latch) -> None:
        library = _library(frozen_latch)
        assert (
            library.record_reuse([123456789], success=True, principal=PRINCIPAL) == []
        )


class TestSigningAnActivation:
    def test_an_unknown_skill_is_refused_by_name(self, frozen_latch) -> None:
        library = _library(frozen_latch)
        with pytest.raises(ValueError, match=r"'arc-missing' v1 is None"):
            library.attest_activation("arc-missing", 1, approver="operator:test")

    def test_an_inactive_skill_is_refused_by_its_state(self, frozen_latch) -> None:
        library = _library(frozen_latch)
        library.repository.save(_record())
        with pytest.raises(ValueError, match=r"v1 is 'candidate'"):
            library.attest_activation("arc-branch", 1, approver="operator:test")

    def test_without_a_writer_nothing_is_signed(self, frozen_latch) -> None:
        library = _library(frozen_latch)
        assert library.provenance is None
        _active_skill_without_a_trail(library, PRINCIPAL)
        assert (
            library.attest_activation("arc-notrail", 1, approver="operator:test")
            is False
        )


class TestWithdrawingAReflexSource:
    def test_an_unknown_trail_withdraws_nothing(self, frozen_latch) -> None:
        library = _library(frozen_latch)
        assert library.withdraw_reflex_source(987654) is False

    def test_a_skill_already_out_of_active_is_left_as_it_is(self, frozen_latch) -> None:
        library = _library(frozen_latch)
        library.repository.save(_record())
        trail = library.trails.trail_for("arc-branch", 1)
        assert library.withdraw_reflex_source(trail) is True
        assert library.repository.get("arc-branch", 1).state == "candidate"

    def test_positive_control_an_active_skill_is_suspended(self, frozen_latch) -> None:
        library = _library(frozen_latch)
        _active_skill_without_a_trail(library, PRINCIPAL)
        trail = library.trails.trail_for("arc-notrail", 1)
        assert library.withdraw_reflex_source(trail) is True
        assert library.repository.get("arc-notrail", 1).state == "suspended"


# ---------------------------------------------------------------- the reflexes

REFLEX_GOAL = "show the reflex trigger notes"
#: A read-only arc on a file that exists, so its freshness plan can run.
REFLEX_STEPS = ["read_file: filepath=README.md"]


class _Bus:
    def __init__(self) -> None:
        self.events: list = []

    def append(self, event) -> int:
        self.events.append(event)
        return len(self.events)

    def decisions(self) -> list[tuple[str, str]]:
        return [(e.payload["decision"], e.payload["reason"]) for e in self.events]


def _reflex_world(root: Path, *, threshold: float = 0.5, arcs=None):
    from aios.core.cerebellum import Cerebellum
    from aios.core.verification_strength import VerificationStrength
    from aios.memory.db import init_memory_db

    db = root / "memory.sqlite"
    init_memory_db(db)
    library = _library(root)
    arcs = arcs or [(REFLEX_GOAL, REFLEX_STEPS)]
    for goal, steps in arcs:
        for _ in range(3):
            library.record_attempt(
                goal,
                steps,
                success=True,
                strength=VerificationStrength.STRONG,
                principal=PRINCIPAL,
            )
    for record in library.repository.list_skills():
        library.repository.transition_state(
            record.skill_id, record.version, "human_reviewed"
        )
        library.repository.transition_state(record.skill_id, record.version, "active")
    bus = _Bus()
    cerebellum = Cerebellum(db, match_threshold=threshold, bus=bus)
    cerebellum.attach_reflex_gate(library)
    assert cerebellum.try_compile_all() == len(arcs)
    return cerebellum, library, bus


class TestTheReflexTrigger:
    def test_a_directive_with_no_words_covers_nothing(self) -> None:
        from aios.core.cerebellum import directive_coverage

        assert directive_coverage("", REFLEX_GOAL) == 0.0
        assert directive_coverage("?! ...", REFLEX_GOAL) == 0.0

    def test_a_turn_with_no_authored_words_is_no_decision_at_any_threshold(
        self, frozen_latch
    ) -> None:
        """Only the operator's own words are considered (plan Phase 5a). A
        wholly quoted turn is not a reflex decision at all -- not even an
        abstention in the decision stream -- however low the threshold."""
        cerebellum, _, bus = _reflex_world(frozen_latch, threshold=0.0)
        assert cerebellum.match(f"> {REFLEX_GOAL}", principal=PRINCIPAL) is None
        assert bus.decisions() == []

    def test_positive_control_the_authored_goal_replays(self, frozen_latch) -> None:
        cerebellum, _, bus = _reflex_world(frozen_latch, threshold=0.0)
        assert cerebellum.match(REFLEX_GOAL, principal=PRINCIPAL) is not None
        assert bus.decisions() == [("replayed", "matched")]

    def test_a_reflex_retired_during_the_match_is_not_replayed(
        self, frozen_latch, monkeypatch
    ) -> None:
        """A retirement that lands between loading the playbooks and choosing
        one -- whose skill could not be suspended, so the library would still
        vouch for it -- is honoured: the playbook is no longer compiled."""
        cerebellum, library, _ = _reflex_world(frozen_latch)
        [playbook_id] = list(cerebellum._cache)
        monkeypatch.setattr(library, "withdraw_reflex_source", lambda _trail: False)
        loaded = cerebellum._activated

        def retired_meanwhile(**kwargs):
            activated = loaded(**kwargs)
            cerebellum.decompile(playbook_id, reason="a concurrent retirement")
            return activated

        monkeypatch.setattr(cerebellum, "_activated", retired_meanwhile)
        assert cerebellum.match(REFLEX_GOAL, principal=PRINCIPAL) is None
        assert library.repository.list_skills()[0].state == "active"

    def test_only_the_reflexes_that_tie_are_called_ambiguous(
        self, frozen_latch
    ) -> None:
        """Two reflexes fit equally and a third clearly less: none fires, and
        the decision stream names exactly the two that tied (M5 counts these)."""
        banner = "show the banner alpha beta"
        cerebellum, _, bus = _reflex_world(
            frozen_latch,
            arcs=[
                (f"{banner} north", ["read_file: filepath=README.md"]),
                (f"{banner} south", ["read_file: filepath=AGENTS.md"]),
                (f"{banner} east west river", ["read_file: filepath=CLAUDE.md"]),
            ],
        )
        assert cerebellum.match(banner, principal=PRINCIPAL) is None
        assert bus.decisions() == [("abstained", "ambiguous")] * 2


class TestWhatAnActivationBacks:
    def test_a_skill_with_a_step_no_reflex_can_replay_backs_nothing(
        self, frozen_latch
    ) -> None:
        """The retirement tool keeps a legacy playbook only if an activation
        backs exactly its steps. A skill with a step a reflex cannot replay
        (create_file) is no reflex source at all, so a playbook replaying just
        its readable half is not backed: dropping the unreplayable step would
        make it look like it is."""
        from aios.application.memory.institutional_skills import _STEPS_JSON
        from aios.core.cerebellum import Cerebellum, CompiledPlaybook, PlaybookStep
        from aios.memory.db import init_memory_db

        steps = ["read_file: filepath=README.md", "create_file: notes.md"]
        library = _library(frozen_latch)
        record = _record().model_copy(
            update={
                "skill_id": "arc-mixed",
                "provenance": {"principal": PRINCIPAL, "procedure_format": _STEPS_JSON},
                "procedure": json.dumps(steps),
            }
        )
        library.repository.save(record)
        library.repository.transition_state("arc-mixed", 1, "human_reviewed")
        library.repository.transition_state("arc-mixed", 1, "active")
        trail = library.trails.trail_for("arc-mixed", 1)
        # Not vacuous: the library does offer it, with both of its steps.
        assert library.compilable_procedures()[trail]["steps"] == steps
        init_memory_db(frozen_latch / "memory.sqlite")
        cerebellum = Cerebellum(frozen_latch / "memory.sqlite")
        cerebellum.attach_reflex_gate(library)
        legacy = CompiledPlaybook(
            id=1,
            skill_id=trail,
            goal_pattern="show the readme",
            signature_v2="",
            steps=[PlaybookStep("read_file", {"filepath": "README.md"})],
            compiled_at="",
        )
        assert cerebellum.activation_backs(legacy) is False


class TestInvalidatingASkill:
    def test_a_skill_with_no_live_reflex_invalidates_nothing(
        self, frozen_latch
    ) -> None:
        cerebellum, _, _ = _reflex_world(frozen_latch)
        assert cerebellum.invalidate_for_skill(987654) is False

    def test_positive_control_a_live_reflex_is_retired(self, frozen_latch) -> None:
        cerebellum, _, _ = _reflex_world(frozen_latch)
        [playbook] = cerebellum._cache.values()
        assert cerebellum.invalidate_for_skill(playbook.skill_id) is True
        assert cerebellum.invalidate_for_skill(playbook.skill_id) is False


def _playbook_rows(db: Path) -> list[tuple[str, object]]:
    from aios.memory.db import get_connection

    with get_connection(db) as conn:
        return [
            (str(r["status"]), r["retired_reason"])
            for r in conn.execute(
                "SELECT status, retired_reason FROM compiled_playbooks ORDER BY id"
            ).fetchall()
        ]


class TestTakingAReflexOutOfService:
    def test_a_refused_suspension_is_never_recorded_as_one(
        self, frozen_latch, monkeypatch
    ) -> None:
        """The row records what happened: if the skill could not be suspended
        it stays `decompiled` and claims no suspension."""
        cerebellum, library, _ = _reflex_world(frozen_latch)
        [playbook_id] = list(cerebellum._cache)
        monkeypatch.setattr(library, "withdraw_reflex_source", lambda _trail: False)
        cerebellum.decompile(playbook_id, reason="test")
        assert _playbook_rows(frozen_latch / "memory.sqlite") == [("decompiled", None)]

    def test_positive_control_a_recorded_suspension_says_so(self, frozen_latch) -> None:
        cerebellum, _, _ = _reflex_world(frozen_latch)
        [playbook_id] = list(cerebellum._cache)
        cerebellum.decompile(playbook_id, reason="test")
        [(status, reason)] = _playbook_rows(frozen_latch / "memory.sqlite")
        assert status == "retired"
        assert "skill suspended" in str(reason)

    def test_a_reflex_this_instance_never_loaded_can_still_be_retired(
        self, frozen_latch
    ) -> None:
        """Another process -- the retirement tool, a second worker -- retires
        a playbook it has not cached."""
        from aios.core.cerebellum import Cerebellum

        cerebellum, library, _ = _reflex_world(frozen_latch)
        [playbook_id] = list(cerebellum._cache)
        other = Cerebellum(frozen_latch / "memory.sqlite")
        other.attach_reflex_gate(library)
        assert other._cache == {}
        other.decompile(playbook_id, reason="test")
        assert _playbook_rows(frozen_latch / "memory.sqlite")[0][0] == "retired"


# --------------------------------------------------------- the reflex contract


class TestTheReflexContract:
    def test_no_plan_is_never_executable(self) -> None:
        from aios.application.memory.reflex_contract import plan_executable

        assert plan_executable(None, ["read_file: filepath=README.md"]) is False

    def test_an_activation_fills_only_what_a_candidate_lacks(self) -> None:
        """The operator reviewed this contract; activating it must not
        rewrite the parts it already has."""
        from aios.application.memory.reflex_contract import (
            REUSE_OBSERVATION,
            stamp_for_activation,
        )
        from aios.core.verification_strength import VerificationStrength
        from aios.domain.verification.contracts import SkillVerifierSpec

        plan = SkillVerifierSpec(
            target_pattern="tests/test_other.py",
            required_observations=(REUSE_OBSERVATION,),
            minimum_strength=int(VerificationStrength.STRONG),
        )
        reviewed = _record().model_copy(
            update={
                "verification_plan": plan,
                "allowed_scope_pattern": "custom/scope",
                "source_trajectory_ids": ["trajectory:reviewed"],
            }
        )
        stamped = stamp_for_activation(reviewed)
        assert stamped.verification_plan == plan
        assert stamped.allowed_scope_pattern == "custom/scope"
        assert stamped.source_trajectory_ids == ["trajectory:reviewed"]
        assert len(stamped.last_validated_versions) == 1

    def test_positive_control_a_bare_candidate_is_filled_in(self) -> None:
        from aios.application.memory.reflex_contract import stamp_for_activation

        stamped = stamp_for_activation(_record())
        assert stamped.verification_plan is not None
        assert stamped.verification_plan.target_pattern == "tests/test_parser.py"
        assert stamped.allowed_scope_pattern
        assert stamped.source_trajectory_ids

    def test_a_reviewed_skills_contract_is_not_rewritten(self) -> None:
        """Past candidate the contract is no longer writable: re-activating a
        suspended or reviewed skill appends the code state, nothing else."""
        from aios.application.memory.reflex_contract import stamp_for_activation

        for state in ("human_reviewed", "suspended"):
            stamped = stamp_for_activation(_record(state))
            assert stamped.verification_plan is None
            assert stamped.allowed_scope_pattern == ""
            assert stamped.source_trajectory_ids == []
            assert len(stamped.last_validated_versions) == 1

    def test_a_freshness_plan_is_checked_where_the_read_happens(
        self, tmp_path, monkeypatch
    ) -> None:
        """Live, commands run in the first scope root's PARENT, not in the
        project a read_file touches. A read-only arc's plan names a file
        path, so it is found under the project; a test runner's plan names a
        command token, found where the command runs."""
        from aios.application.memory import reflex_contract
        from aios.core.verification_strength import VerificationStrength
        from aios.domain.verification.contracts import SkillVerifierSpec

        monkeypatch.setattr(reflex_contract, "command_cwd", lambda: tmp_path)
        steps = ["read_file: filepath=README.md"]
        freshness = reflex_contract.verification_plan(steps)
        assert reflex_contract.FRESHNESS_OBSERVATION in freshness.required_observations
        assert reflex_contract.plan_executable(freshness, steps) is True
        runner = SkillVerifierSpec(
            target_pattern="README.md",
            required_observations=(reflex_contract.REUSE_OBSERVATION,),
            minimum_strength=int(VerificationStrength.STRONG),
        )
        assert reflex_contract.plan_executable(runner, steps) is False
