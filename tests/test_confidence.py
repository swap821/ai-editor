"""Confidence-gating tests — threshold boundaries and step partitioning."""
from __future__ import annotations

from aios.core.confidence_filter import TaskStep, filter_steps, gate


def test_gate_boundaries_at_threshold() -> None:
    # Blueprint: 0.720 passes, 0.719 escalates.
    assert gate(0.720).passed is True
    assert gate(0.719).passed is False
    assert gate(0.72).passed is True


def test_filter_partitions_by_threshold() -> None:
    steps = [
        TaskStep("s1", "safe step", 0.95),
        TaskStep("s2", "unsure step", 0.50),
        TaskStep("s3", "exactly at threshold", 0.72),
    ]
    out = filter_steps(steps)
    assert [s.step_id for s in out["approved"]] == ["s1", "s3"]
    assert len(out["escalate"]) == 1
    assert out["escalate"][0]["action"] == "REQUIRE_HUMAN_REVIEW"
    assert out["escalate"][0]["step"].step_id == "s2"
