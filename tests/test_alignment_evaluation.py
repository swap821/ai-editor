"""Tests for diagnostic, human-labelled alignment evaluation evidence."""
from __future__ import annotations

from pathlib import Path

import pytest

from aios.memory.alignment_evaluation import AlignmentEvaluationStore
from aios.memory.db import get_connection, init_memory_db


@pytest.fixture()
def store(tmp_path: Path) -> AlignmentEvaluationStore:
    path = tmp_path / "memory.db"
    init_memory_db(path)
    return AlignmentEvaluationStore(path)


def frame(
    *,
    intent: str = "execute",
    mode: str = "direct",
    action: str = "proceed",
    corrected: bool = False,
) -> dict:
    return {
        "intent": intent,
        "confidence": 0.8,
        "assumptions": ["Use the existing API"],
        "unknowns": ["Preferred copy"],
        "communication": {"mode": mode, "ambiguity_action": action},
        "correction": {
            "active": corrected,
            "corrected_fields": ["goal"] if corrected else [],
        },
    }


def test_records_hashed_diagnostic_observation_and_summary(
    store: AlignmentEvaluationStore,
) -> None:
    session_id = "private-alignment-session"
    observation_id = store.record(session_id, frame(action="state_assumptions"))

    summary = store.summary()

    assert observation_id == 1
    assert summary["total_turns"] == 1
    assert summary["state_assumptions_rate"] == 1.0
    assert summary["by_intent"] == {"execute": 1}
    assert summary["recent"][0]["assumptions_count"] == 1
    assert summary["automatic_policy_updates"] is False
    assert session_id.encode() not in store.db_path.read_bytes()


def test_correction_and_feedback_label_latest_observation(
    store: AlignmentEvaluationStore,
) -> None:
    store.record("sess", frame())

    assert store.mark_latest_corrected("sess", ["goal", "intent"]) is True
    observation_id = store.record_feedback(
        "sess",
        outcome="misaligned",
        issues=["wrong_goal", "wrong_intent"],
    )
    summary = store.summary()

    assert observation_id == 1
    assert summary["corrected_turns"] == 1
    assert summary["correction_rate"] == 1.0
    assert summary["outcomes"] == {"misaligned": 1}
    assert summary["issues"] == {"wrong_goal": 1, "wrong_intent": 1}
    assert summary["corrected_fields"] == {"goal": 1, "intent": 1}


def test_repeated_patterns_require_three_observations(
    store: AlignmentEvaluationStore,
) -> None:
    for index in range(3):
        session = f"sess-{index}"
        store.record(session, frame())
        store.mark_latest_corrected(session, ["goal"])
        store.record_feedback(session, outcome="misaligned", issues=["wrong_goal"])

    assert store.summary()["repeated_patterns"] == [
        {"kind": "corrected_field", "name": "goal", "count": 3},
        {"kind": "issue", "name": "wrong_goal", "count": 3},
    ]


def test_feedback_validates_labels_and_redacts_notes(
    store: AlignmentEvaluationStore,
) -> None:
    secret = "sk-" + "z" * 40
    store.record("sess", frame())

    with pytest.raises(ValueError, match="unsupported alignment outcome"):
        store.record_feedback("sess", outcome="approved")
    with pytest.raises(ValueError, match="no alignment observation"):
        store.record_feedback("missing", outcome="aligned")

    store.record_feedback(
        "sess",
        outcome="aligned",
        issues=["not-supported", "other"],
        notes=f"do not persist {secret}",
    )
    with get_connection(store.db_path) as conn:
        row = conn.execute(
            "SELECT issues_json, notes FROM alignment_observations WHERE id = 1"
        ).fetchone()

    assert row["issues_json"] == '["other"]'
    assert secret not in row["notes"]
    assert "REDACTED" in row["notes"]
    assert secret.encode() not in store.db_path.read_bytes()


def test_mark_latest_corrected_returns_false_without_observation(
    store: AlignmentEvaluationStore,
) -> None:
    assert store.mark_latest_corrected("missing", ["goal"]) is False


def test_explicit_observation_id_must_belong_to_session(
    store: AlignmentEvaluationStore,
) -> None:
    first_id = store.record("first", frame())
    second_id = store.record("second", frame())

    assert store.mark_latest_corrected(
        "first", ["goal"], observation_id=second_id
    ) is False
    with pytest.raises(ValueError, match="no alignment observation"):
        store.record_feedback(
            "first",
            outcome="aligned",
            observation_id=second_id,
        )
    assert store.record_feedback(
        "first",
        outcome="aligned",
        observation_id=first_id,
    ) == first_id
