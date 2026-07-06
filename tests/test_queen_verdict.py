"""Direct unit tests for ``aios/council/queen_verdict.py``.

This module gates Council mission execution (``has_blocking_verdict`` decides
whether a worker runs; ``highest_risk`` folds queen risks into the mission
risk; ``verdicts_as_metadata`` shapes the JSON persisted into reports and
MissionContract metadata). Until now it was exercised only incidentally
through the orchestrator — these tests pin its contract directly, most
importantly the fail-closed rule that an UNRECOGNIZED risk string ranks as
RED, never silently as GREEN.
"""
from __future__ import annotations

import json

from aios.council.queen_verdict import (
    has_blocking_verdict,
    highest_risk,
    verdicts_as_metadata,
)
from aios.runtime.contracts import QueenVerdict


def _verdict(**overrides) -> QueenVerdict:
    base = {
        "queen": "security",
        "verdict": "allow",
        "risk": "GREEN",
        "reason": "no concerns",
    }
    base.update(overrides)
    return QueenVerdict(**base)


# ── highest_risk ─────────────────────────────────────────────────────────


def test_highest_risk_empty_iterable_is_green() -> None:
    assert highest_risk([]) == "GREEN"


def test_highest_risk_orders_green_yellow_red() -> None:
    assert highest_risk(["GREEN"]) == "GREEN"
    assert highest_risk(["GREEN", "YELLOW"]) == "YELLOW"
    assert highest_risk(["YELLOW", "GREEN", "RED"]) == "RED"


def test_highest_risk_is_order_independent() -> None:
    assert highest_risk(["RED", "GREEN", "GREEN"]) == "RED"
    assert highest_risk(["GREEN", "GREEN", "YELLOW"]) == "YELLOW"


def test_highest_risk_unknown_string_fails_closed_to_red() -> None:
    # An unrecognized risk label must escalate, never silently pass as GREEN.
    assert highest_risk(["banana"]) == "RED"
    assert highest_risk(["GREEN", ""]) == "RED"
    assert highest_risk(["green"]) == "RED"  # case-sensitive: lowercase is unknown


def test_highest_risk_coerces_non_string_inputs_via_str() -> None:
    # str(None) == "None" -> unknown -> RED; the function must not raise.
    assert highest_risk([None]) == "RED"  # type: ignore[list-item]
    assert highest_risk([42, "GREEN"]) == "RED"  # type: ignore[list-item]


def test_highest_risk_accepts_a_single_pass_generator() -> None:
    assert highest_risk(risk for risk in ("GREEN", "YELLOW")) == "YELLOW"


# ── has_blocking_verdict ─────────────────────────────────────────────────


def test_no_verdicts_do_not_block() -> None:
    assert has_blocking_verdict([]) is False


def test_allow_and_allow_with_approval_do_not_block() -> None:
    verdicts = [
        _verdict(verdict="allow"),
        _verdict(queen="critique", verdict="allow_with_approval", risk="YELLOW"),
    ]
    assert has_blocking_verdict(verdicts) is False


def test_deny_blocks() -> None:
    assert has_blocking_verdict([_verdict(verdict="deny", risk="RED")]) is True


def test_defer_blocks() -> None:
    assert has_blocking_verdict([_verdict(verdict="defer", risk="YELLOW")]) is True


def test_one_blocking_verdict_among_allows_blocks() -> None:
    verdicts = [
        _verdict(verdict="allow"),
        _verdict(queen="critique", verdict="allow"),
        _verdict(queen="planner", verdict="deny", risk="RED"),
    ]
    assert has_blocking_verdict(verdicts) is True


# ── verdicts_as_metadata ─────────────────────────────────────────────────


def test_metadata_empty_iterable_is_empty_list() -> None:
    assert verdicts_as_metadata([]) == []


def test_metadata_shape_and_values() -> None:
    verdict = _verdict(
        verdict="allow_with_approval",
        risk="YELLOW",
        reason="touches config",
        constraints=["no writes outside sandbox"],
        confidence=0.85,
        metadata={"pattern": "config-edit"},
    )
    (row,) = verdicts_as_metadata([verdict])
    assert row == {
        "queen": "security",
        "verdict": "allow_with_approval",
        "risk": "YELLOW",
        "reason": "touches config",
        "constraints": ["no writes outside sandbox"],
        "confidence": 0.85,
        "metadata": {"pattern": "config-edit"},
    }


def test_metadata_preserves_verdict_order() -> None:
    rows = verdicts_as_metadata(
        [_verdict(queen="security"), _verdict(queen="critique")]
    )
    assert [row["queen"] for row in rows] == ["security", "critique"]


def test_metadata_copies_are_isolated_from_the_verdict() -> None:
    # Reports mutate their own copies; that must never write back into the
    # QueenVerdict contract object.
    verdict = _verdict(constraints=["a"], metadata={"k": "v"})
    (row,) = verdicts_as_metadata([verdict])
    row["constraints"].append("b")
    row["metadata"]["k2"] = "v2"
    assert verdict.constraints == ["a"]
    assert verdict.metadata == {"k": "v"}


def test_metadata_is_json_serializable() -> None:
    rows = verdicts_as_metadata(
        [_verdict(constraints=["c1", "c2"], confidence=0.5, metadata={"n": 1})]
    )
    assert json.loads(json.dumps(rows)) == rows
