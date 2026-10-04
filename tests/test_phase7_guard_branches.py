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
