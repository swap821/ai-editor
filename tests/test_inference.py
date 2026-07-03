"""Tests for aios.core.inference — inference composition from graph edges."""
import pytest

from aios.core.inference import InferenceStep, compose_answer, infer
from aios.memory.facts import WeightedEdge


def _edge(subject: str, predicate: str, obj: str, depth: int = 1,
          confidence: float = 1.0, path_confidence: float = 1.0) -> WeightedEdge:
    return WeightedEdge(
        subject=subject, predicate=predicate, object=obj,
        depth=depth, confidence=confidence, path_confidence=path_confidence,
        path=f"→{subject}→{obj}→",
    )


def test_infer_composes_chain_into_answer() -> None:
    edges = [
        _edge("project", "uses", "FastAPI", depth=1, path_confidence=1.0),
        _edge("FastAPI", "needs", "uvicorn", depth=2, path_confidence=0.85),
    ]
    result = infer("what does project use", edges)
    assert result is not None
    assert "project" in result.answer
    assert "FastAPI" in result.answer
    assert "uvicorn" in result.answer
    assert result.combined_confidence == pytest.approx(0.85)


def test_infer_returns_none_below_confidence() -> None:
    edges = [
        _edge("a", "to", "b", path_confidence=0.05),
    ]
    result = infer("query", edges, min_confidence=0.3)
    assert result is not None
    assert result.answer == ""
    assert result.reached_horizon is True


def test_infer_returns_none_empty_edges() -> None:
    result = infer("query", [])
    assert result is None


def test_infer_reached_horizon_flag() -> None:
    edges = [
        _edge("a", "to", "b", path_confidence=0.5),
        _edge("b", "to", "c", path_confidence=0.1),
    ]
    result = infer("query", edges, min_confidence=0.3)
    assert result is not None
    assert result.reached_horizon is True


def test_compose_answer_caps_at_3_hops() -> None:
    chain = [
        InferenceStep("a", "to", "b", 1, 1.0),
        InferenceStep("b", "to", "c", 2, 0.85),
        InferenceStep("c", "to", "d", 3, 0.72),
        InferenceStep("d", "to", "e", 4, 0.61),
        InferenceStep("e", "to", "f", 5, 0.52),
    ]
    answer = compose_answer(chain)
    assert "a to b" in answer
    assert "which to c" in answer
    assert "which to d" in answer
    assert "e" not in answer.split("...and")[0] if "...and" in answer else True
    assert "2 further associations" in answer


def test_compose_answer_empty_chain() -> None:
    assert compose_answer([]) == ""


def test_compose_answer_single_hop() -> None:
    chain = [InferenceStep("project", "uses", "FastAPI", 1, 1.0)]
    answer = compose_answer(chain)
    assert "project uses FastAPI" in answer
    assert "which" not in answer
