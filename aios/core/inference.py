"""Inference engine — composes graph traversal into structured answers.

Pure functions over WeightedEdge lists. No DB access, no state, no LLM.
The graph provides the data; inference provides the meaning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class InferenceStep:
    """One step in an inference chain."""

    subject: str
    predicate: str
    object: str
    depth: int
    confidence: float


@dataclass(frozen=True)
class InferenceResult:
    """A composed inference from graph traversal."""

    query: str
    chain: list[InferenceStep]
    combined_confidence: float
    answer: str
    reached_horizon: bool
    source_count: int


def infer(
    query: str,
    edges: list,
    *,
    min_confidence: float = 0.3,
) -> Optional[InferenceResult]:
    """Compose an inference from weighted graph edges.

    Returns None when no path exceeds min_confidence.
    """
    if not edges:
        return None

    above = [e for e in edges if e.path_confidence >= min_confidence]
    if not above:
        return InferenceResult(
            query=query,
            chain=[],
            combined_confidence=0.0,
            answer="",
            reached_horizon=True,
            source_count=len(edges),
        )

    above.sort(key=lambda e: (-e.path_confidence, e.depth))
    chain = [
        InferenceStep(
            subject=e.subject,
            predicate=e.predicate,
            object=e.object,
            depth=e.depth,
            confidence=e.path_confidence,
        )
        for e in above
    ]
    combined = min(step.confidence for step in chain) if chain else 0.0
    reached_horizon = any(e.path_confidence < min_confidence for e in edges)
    answer = compose_answer(chain)

    return InferenceResult(
        query=query,
        chain=chain,
        combined_confidence=combined,
        answer=answer,
        reached_horizon=reached_horizon,
        source_count=len(set((e.subject, e.object) for e in edges)),
    )


def compose_answer(chain: list[InferenceStep]) -> str:
    """Compose a readable sentence from an inference chain.

    Caps at 3 hops — beyond that, chains read like legal contracts.
    """
    if not chain:
        return ""
    display = chain[:3]
    parts: list[str] = []
    for i, step in enumerate(display):
        conf_pct = f"{step.confidence * 100:.0f}%"
        if i == 0:
            parts.append(f"{step.subject} {step.predicate} {step.object} ({conf_pct})")
        else:
            parts.append(f"which {step.predicate} {step.object} ({conf_pct})")
    result = ", ".join(parts)
    if len(chain) > 3:
        result += f" (...and {len(chain) - 3} further associations)"
    return result


def find_entities(query: str) -> list[str]:
    """Extract candidate entity names from a query for graph lookup.

    Delegates to graph_ingestion.find_entities() — single implementation,
    no divergence.
    """
    from aios.core.graph_ingestion import find_entities as _find

    return _find(query)
