"""Plan Phase 6d: the negative-transfer quarantine (threat T13).

A learned item can be signed, attributed and operator-activated, and still make
the turns that recall it worse. These tests pin the named rule
(``aios/application/learning/negative_transfer.py``) and each place it acts:

* reflexes -- first observed harm takes the reflex out of service;
* skills -- recalled outcomes against the skill's OWN record, by an exact
  binomial test, quarantined only on enough outcomes, flagged below that; the
  operator's re-activation restarts the window;
* lessons -- recalled outcomes against similar tasks' success rate; the
  quarantine is an unsigned withdrawal the recall gate refuses; re-admission
  restarts the window;
* the live turn -- a verifier-judged turn credits the verified lessons it
  recalled.
"""

from __future__ import annotations

import json
import random
import sqlite3
from fractions import Fraction
from math import comb
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from aios.application.learning import negative_transfer as ntq
from aios.memory import learning_freeze

PRINCIPAL = "principal:ntq"


def _seed() -> str:
    return (
        Ed25519PrivateKey.generate()
        .private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        .hex()
    )


@pytest.fixture
def own_latch(tmp_path, monkeypatch):
    monkeypatch.setattr(
        learning_freeze, "_latch_path", lambda: tmp_path / "emergency_stop.db"
    )
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    return tmp_path


class _Journal:
    """Captures what a module appends to the learning journal."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, str, dict]] = []

    def __call__(self, faculty, transition, *, subject_id=None, detail=None, **_):
        self.entries.append((faculty, transition, dict(detail or {})))

    def of(self, transition: str) -> list[dict]:
        return [d for _, t, d in self.entries if t == transition]


# ------------------------------------------------------------------ the rule


def _exact_tail(k: int, n: int, p: Fraction) -> Fraction:
    return sum(
        (Fraction(comb(n, i)) * p**i * (1 - p) ** (n - i) for i in range(k + 1)),
        Fraction(0),
    )


class TestTheRule:
    @pytest.mark.parametrize(
        ("k", "n", "p"),
        [
            (8, 10, "49/50"),
            (2, 10, "4/5"),
            (0, 10, "9/10"),
            (12, 15, "50/51"),
            (40, 60, "3/4"),
        ],
    )
    def test_the_binomial_tail_is_exact(self, k, n, p) -> None:
        exact = _exact_tail(k, n, Fraction(p))
        assert ntq.binomial_lower_tail(k, n, float(Fraction(p))) == pytest.approx(
            float(exact), rel=1e-9, abs=1e-15
        )

    def test_the_tail_edges(self) -> None:
        assert ntq.binomial_lower_tail(5, 5, 0.3) == 1.0
        assert ntq.binomial_lower_tail(2, 5, 0.0) == 1.0
        assert ntq.binomial_lower_tail(2, 5, 1.0) == 0.0
        with pytest.raises(ValueError):
            ntq.binomial_lower_tail(1, 5, 1.5)

    def test_the_baseline_is_smoothed_never_certain(self) -> None:
        assert ntq.smoothed_rate(3, 3) == pytest.approx(0.8)
        assert ntq.smoothed_rate(0, 0) == pytest.approx(0.5)
        assert 0 < ntq.smoothed_rate(0, 50) < ntq.smoothed_rate(50, 50) < 1

    def test_nothing_to_compare_assesses_nothing(self) -> None:
        assert ntq.assess(0, 10, None).action == "none"
        assert ntq.assess(0, 0, 0.9).action == "none"

    def test_at_or_above_the_baseline_is_never_flagged(self) -> None:
        assert ntq.assess(9, 10, 0.9).action == "none"
        assert ntq.assess(20, 20, 0.99).action == "none"

    def test_below_the_baseline_on_few_outcomes_is_flagged_for_review(self) -> None:
        verdict = ntq.assess(0, 3, 0.9, min_observations=10)
        assert verdict.action == "review"
        assert verdict.p_value is None

    def test_significant_on_enough_outcomes_is_quarantined(self) -> None:
        verdict = ntq.assess(8, 10, 0.98, min_observations=10, alpha=0.05)
        assert verdict.action == "quarantine"
        assert verdict.p_value < 0.05
        assert verdict.as_detail()["rule"] == ntq.RULE

    def test_below_but_within_noise_is_left_alone(self) -> None:
        verdict = ntq.assess(8, 10, 0.85, min_observations=10, alpha=0.05)
        assert verdict.action == "none"
        assert verdict.p_value >= 0.05

    def test_impossible_counts_and_baselines_are_refused(self) -> None:
        for args in ((5, 3, 0.5), (-1, 3, 0.5)):
            with pytest.raises(ValueError):
                ntq.assess(*args)
        for baseline in (0.0, 1.0, 1.2):
            with pytest.raises(ValueError):
                ntq.assess(1, 3, baseline)

    @pytest.mark.parametrize("seed", range(3))
    def test_quarantine_exactly_when_enough_below_and_significant(self, seed) -> None:
        rng = random.Random(seed)
        for case in range(300):
            n = rng.randint(0, 30)
            k = rng.randint(0, n)
            p0 = Fraction(rng.randint(1, 99), 100)
            floor, alpha = rng.choice((5, 10, 15)), Fraction(1, 20)
            verdict = ntq.assess(k, n, float(p0), min_observations=floor, alpha=0.05)
            below = n > 0 and Fraction(k, n) < p0
            expected = (
                "quarantine"
                if below and n >= floor and _exact_tail(k, n, p0) < alpha
                else "review"
                if below and n < floor
                else "none"
            )
            assert verdict.action == expected, (
                f"seed {seed} case {case}: {k}/{n} p0={p0}"
            )


# ---------------------------------------------------------------- the skills


def _library(root: Path):
    from aios.application.memory.institutional_skills import (
        InstitutionalSkillAdapter,
        SkillTrailIndex,
    )
    from aios.domain.learning.repository import SkillRepository

    db = root / "operational.sqlite"
    return InstitutionalSkillAdapter(SkillRepository(db), SkillTrailIndex(db))


def _active_skill(library, *, successes: int, failures: int) -> int:
    """An operator-activated skill with its own walked record; its trail id."""
    from datetime import datetime, timezone

    from aios.domain.learning.repository import SkillRecord

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    record = SkillRecord(
        skill_id="arc-ntq",
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
        success_count=successes,
        failure_count=failures,
        last_validated_versions=[],
        state="candidate",
        created_at=now,
        updated_at=now,
        provenance={"principal": PRINCIPAL},
    )
    library.repository.save(record)
    library.repository.transition_state("arc-ntq", 1, "human_reviewed")
    library.repository.transition_state("arc-ntq", 1, "active")
    return library.trails.trail_for("arc-ntq", 1)


def _reuse(library, trail: int, pattern: str) -> None:
    for outcome in pattern:
        library.record_reuse([trail], success=outcome == "S", principal=PRINCIPAL)


@pytest.fixture
def skill_journal(monkeypatch):
    from aios.application.memory import institutional_skills

    journal = _Journal()
    monkeypatch.setattr(institutional_skills, "journal", journal)
    return journal


class TestTheSkillQuarantine:
    def test_a_skill_that_helps_less_than_its_own_record_is_quarantined(
        self, own_latch, skill_journal
    ) -> None:
        """Walked directly it succeeds 98 of 100; recalled, its turns succeed
        8 of 10 -- never low enough for the confidence floor, significantly
        below its own record. Suspended, and only re-activation returns it."""
        library = _library(own_latch)
        trail = _active_skill(library, successes=98, failures=2)
        _reuse(library, trail, "SSSSFSSSSF")
        assert library.repository.get("arc-ntq", 1).state == "suspended"
        [detail] = skill_journal.of("quarantined")
        assert (detail["successes"], detail["attempts"]) == (8, 10)
        assert detail["p_value"] < 0.05
        assert trail not in library.active_procedures(principal=PRINCIPAL)

    def test_positive_control_the_confidence_floor_alone_misses_it(
        self, own_latch, skill_journal, monkeypatch
    ) -> None:
        library = _library(own_latch)
        trail = _active_skill(library, successes=98, failures=2)
        monkeypatch.setattr(
            ntq,
            "assess",
            lambda s, n, b, **k: ntq.TransferVerdict(
                "none", s, n, b, None, 10, 0.05, "off"
            ),
        )
        _reuse(library, trail, "SSSSFSSSSF")
        record = library.repository.get("arc-ntq", 1)
        assert record.state == "active"
        assert record.confidence >= 0.5

    def test_below_its_record_on_few_outcomes_is_flagged_not_suspended(
        self, own_latch, skill_journal
    ) -> None:
        library = _library(own_latch)
        trail = _active_skill(library, successes=98, failures=2)
        _reuse(library, trail, "SSF")
        assert library.repository.get("arc-ntq", 1).state == "active"
        assert skill_journal.of("review_flagged")
        assert not skill_journal.of("quarantined")

    def test_a_skill_that_holds_its_record_stays_active(
        self, own_latch, skill_journal
    ) -> None:
        library = _library(own_latch)
        trail = _active_skill(library, successes=8, failures=2)
        _reuse(library, trail, "SSSSSSSSSSSS")
        assert library.repository.get("arc-ntq", 1).state == "active"
        assert not skill_journal.entries

    def test_the_operators_reactivation_restarts_the_window(
        self, own_latch, skill_journal
    ) -> None:
        library = _library(own_latch)
        trail = _active_skill(library, successes=98, failures=2)
        _reuse(library, trail, "SSSSFSSSSF")
        assert library.repository.get("arc-ntq", 1).state == "suspended"
        library.repository.transition_state("arc-ntq", 1, "human_reviewed")
        library.repository.transition_state("arc-ntq", 1, "active")
        library.attest_activation("arc-ntq", 1, approver="operator:test")
        _reuse(library, trail, "F")
        assert library.repository.get("arc-ntq", 1).state == "active"
        assert len(skill_journal.of("quarantined")) == 1


# --------------------------------------------------------------- the lessons


@pytest.fixture
def lessons(own_latch, monkeypatch):
    """A lessons adapter signing and gating like production, and its journal."""
    from types import SimpleNamespace

    from aios.application.memory import adapters
    from aios.application.memory.adapters import MistakeMemoryAdapter
    from aios.application.memory.provenance_policy import ProvenanceWriter, RecallGate
    from aios.memory.db import init_memory_db
    from aios.memory.mistake import MistakeMemory
    from aios.memory.provenance import (
        LearningSigner,
        LearningVerifier,
        ProvenanceStore,
    )

    journal = _Journal()
    monkeypatch.setattr(adapters, "journal", journal)
    db = own_latch / "memory.sqlite"
    init_memory_db(db)
    signer = LearningSigner({"live": _seed()})
    verifier = LearningVerifier({"live": [signer.public_keys()["live"]]})
    store = ProvenanceStore(db)
    writer = ProvenanceWriter(store, signer, source_kind="live", verifier=verifier)
    adapter = MistakeMemoryAdapter(
        MistakeMemory(db_path=db),
        provenance=writer,
        gate=RecallGate(store, verifier, context="live"),
    )
    return SimpleNamespace(
        db=db, adapter=adapter, journal=journal, store=store, signer=signer
    )


def _verified_lesson(lessons, principal: str = PRINCIPAL) -> int:
    mistake_id = lessons.adapter.record(
        "task-ntq",
        "migration_skipped",
        "the migration was skipped",
        "ran the migration",
        "when the parser build breaks, rerun the parser migration first",
        0.1,
        principal=principal,
    )
    lessons.adapter.promote(mistake_id, principal=principal)
    return int(mistake_id)


def _recalled(lessons) -> list[int]:
    return [
        int(r["mistake_id"])
        for r in lessons.adapter.relevant_verified(
            "parser migration", 5, principal=PRINCIPAL
        )
    ]


def _outcomes(lessons, mistake_id, pattern, baseline=0.9) -> list[int]:
    quarantined: list[int] = []
    for outcome in pattern:
        quarantined += lessons.adapter.record_recall_outcome(
            [mistake_id],
            success=outcome == "S",
            principal=PRINCIPAL,
            baseline=lambda _text: baseline,
        )
    return quarantined


class TestTheLessonQuarantine:
    def test_a_lesson_whose_turns_fail_is_quarantined_and_no_longer_recalled(
        self, lessons
    ) -> None:
        mistake_id = _verified_lesson(lessons)
        assert _recalled(lessons) == [mistake_id]
        assert _outcomes(lessons, mistake_id, "F" * 10) == [mistake_id]
        assert _recalled(lessons) == []
        [detail] = lessons.journal.of("quarantined")
        assert detail["enforced"] is True and detail["attempts"] == 10

    def test_the_quarantine_is_a_withdrawal_no_one_signed(self, lessons) -> None:
        mistake_id = _verified_lesson(lessons)
        assert lessons.store.latest("mistake_pool", str(mistake_id)) is not None
        _outcomes(lessons, mistake_id, "F" * 10)
        assert lessons.store.latest("mistake_pool", str(mistake_id)) is None

    def test_few_bad_outcomes_flag_review_and_keep_the_lesson(self, lessons) -> None:
        mistake_id = _verified_lesson(lessons)
        assert _outcomes(lessons, mistake_id, "FF") == []
        assert _recalled(lessons) == [mistake_id]
        assert len(lessons.journal.of("review_flagged")) == 2

    def test_without_a_baseline_a_lesson_is_not_assessed(self, lessons) -> None:
        mistake_id = _verified_lesson(lessons)
        assert _outcomes(lessons, mistake_id, "F" * 12, baseline=None) == []
        assert _recalled(lessons) == [mistake_id]
        assert not lessons.journal.entries

    def test_only_the_principals_verified_lessons_are_counted(self, lessons) -> None:
        mine = _verified_lesson(lessons)
        theirs = _verified_lesson(lessons, principal="principal:other")
        pending = lessons.adapter.record(
            "task-x", "e", "c", "f", "a pending lesson", 0.1, principal=PRINCIPAL
        )
        counted = lessons.adapter.store.record_recall_outcome(
            [mine, theirs, pending], success=False, principal_id=PRINCIPAL
        )
        assert [int(c["row"]["id"]) for c in counted] == [mine]

    def test_readmission_restarts_the_window(self, lessons) -> None:
        from tools import readmit_learning

        mistake_id = _verified_lesson(lessons)
        _outcomes(lessons, mistake_id, "F" * 10)
        assert _recalled(lessons) == []
        readmit_learning.readmit(
            lessons.db,
            lessons.store,
            lessons.signer,
            table="mistake_pool",
            ids=[mistake_id],
            approver="operator:test",
            principal=PRINCIPAL,
        )
        assert _recalled(lessons) == [mistake_id]
        with sqlite3.connect(lessons.db) as conn:
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM lesson_outcomes WHERE mistake_id = ?",
                    (mistake_id,),
                ).fetchone()[0]
                == 0
            )
        assert _outcomes(lessons, mistake_id, "F") == []
        assert _recalled(lessons) == [mistake_id]


# -------------------------------------------------------------- the reflexes


def _reflex(root: Path):
    from aios.core.cerebellum import Cerebellum
    from aios.core.verification_strength import VerificationStrength
    from aios.memory.db import init_memory_db

    db = root / "memory.sqlite"
    init_memory_db(db)
    library = _library(root)
    for _ in range(3):
        library.record_attempt(
            "show the ntq notes",
            ["read_file: filepath=README.md"],
            success=True,
            strength=VerificationStrength.STRONG,
            principal=PRINCIPAL,
        )
    (record,) = library.repository.list_skills()
    library.repository.transition_state(record.skill_id, 1, "human_reviewed")
    library.repository.transition_state(record.skill_id, 1, "active")
    cerebellum = Cerebellum(db)
    cerebellum.attach_reflex_gate(library)
    assert cerebellum.try_compile_all() == 1
    [playbook] = cerebellum._cache.values()
    return cerebellum, library, playbook, record


def _dispatch(output: str, status: str, failed: bool):
    return lambda _tool, _args: (output, status, failed)


class TestTheReflexRule:
    def test_first_observed_harm_takes_a_reflex_out_of_service(self, own_latch) -> None:
        cerebellum, library, playbook, record = _reflex(own_latch)
        events = list(
            cerebellum.replay(playbook, dispatch_fn=_dispatch("boom", "ok", True))
        )
        assert events[-1]["reason"] == "execution_failed"
        assert cerebellum.compiled_count() == 0
        assert library.repository.get(record.skill_id, 1).state == "suspended"

    def test_positive_control_a_block_is_not_harm(self, own_latch) -> None:
        cerebellum, library, playbook, record = _reflex(own_latch)
        list(cerebellum.replay(playbook, dispatch_fn=_dispatch("", "blocked", False)))
        assert cerebellum.compiled_count() == 1
        assert library.repository.get(record.skill_id, 1).state == "active"


# -------------------------------------------------------------- the live turn


class TestTheLiveTurn:
    def test_a_baseline_comes_from_similar_tasks_or_not_at_all(self) -> None:
        from types import SimpleNamespace

        from aios.application.turns.generate_pipeline import _similar_task_baseline

        def authority(rate):
            return SimpleNamespace(
                development_success_rate=lambda _q: (
                    None if rate is None else SimpleNamespace(success_rate=rate)
                )
            )

        assert _similar_task_baseline(authority(0.75))("x") == 0.75
        assert _similar_task_baseline(authority(None))("x") is None
        assert _similar_task_baseline(authority(1.0))("x") is None

        def broken(_q):
            raise RuntimeError("no development history")

        assert (
            _similar_task_baseline(SimpleNamespace(development_success_rate=broken))(
                "x"
            )
            is None
        )


# The live turn, end to end: /api/generate with test_api's fixtures.
from tests.test_api import (  # noqa: E402
    FakeOllama,
    FakeOllamaVerify,
    FakeOllamaVerifySequence,
    GreenThenFlakyRunner,
    RecordingAudit,
    _cookie_session_id,
    _issue_generate_capability,
    client,  # noqa: F401 - the fixture
)


def _window(mistake_id: int) -> tuple[int, int] | None:
    from aios import config

    with sqlite3.connect(config.MEMORY_DB_PATH) as conn:
        row = conn.execute(
            "SELECT successes, failures FROM lesson_outcomes WHERE mistake_id = ?",
            (mistake_id,),
        ).fetchone()
    return None if row is None else (int(row[0]), int(row[1]))


def test_a_verified_turn_credits_the_verified_lessons_it_recalled(
    client,  # noqa: F811 - test_api's fixture
) -> None:
    """The wiring: a turn the verifier judged shares its verdict with every
    VERIFIED lesson it recalled, through the authority -- and a turn the
    verifier did not judge credits nothing."""
    from aios.api.deps import get_memory_authority
    from aios.api.main import app, get_ollama_client
    from tests.helpers import client_principal_id

    principal = client_principal_id(client)
    lessons = get_memory_authority().adapters["lessons"]
    mistake_id = int(
        lessons.record(
            "task-ntq-live",
            "verify_the_project",
            "the project was not verified",
            "verified the project",
            "to verify the project, run the project tests first",
            0.1,
            principal=principal,
        )
    )
    lessons.promote(mistake_id, principal=principal)
    app.dependency_overrides[get_ollama_client] = FakeOllamaVerify
    session_id = _cookie_session_id(client)
    token = _issue_generate_capability(client, "command", {"command": "pytest -q"})
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "verify the project"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session_id,
            "approvalTokens": [token],
        },
    )
    assert response.status_code == 200
    assert "lesson-recall" in response.text, "the lesson was recalled into the turn"
    assert _window(mistake_id) == (1, 0)

    app.dependency_overrides[get_ollama_client] = FakeOllama
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "verify the project"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session_id,
        },
    )
    assert response.status_code == 200
    assert _window(mistake_id) == (1, 0), "an unjudged turn credits nothing"

    # A turn the verifier judged a FAILURE stains it (GreenThenFlakyRunner:
    # the same target passes, then fails -- a verified_failure).
    from aios.api.main import get_executor
    from aios.core.autonomy import UNGOVERNED_FIXTURE
    from aios.core.executor import Executor
    from aios.security.gateway import RateLimiter

    app.dependency_overrides[get_ollama_client] = FakeOllamaVerifySequence
    app.dependency_overrides[get_executor] = lambda: Executor(
        runner=GreenThenFlakyRunner(),
        rate_limiter=RateLimiter(),
        audit_log=RecordingAudit(),
        emergency_stop=UNGOVERNED_FIXTURE,
    )
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "verify the project"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session_id,
            "approvalTokens": [
                _issue_generate_capability(client, "command", {"command": "pytest -q"})
            ],
        },
    )
    assert response.status_code == 200
    assert _window(mistake_id) == (1, 1), "a judged failure stains the lesson"
