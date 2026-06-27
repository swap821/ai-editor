"""Reasoning helpers for the thinking Queens (Phase 3).

This module holds the *advisory* reasoning surface for the Council Queens and,
critically, the **narrow-only reconciliation** that keeps a reasoning LLM from
ever escalating privilege. The rule everywhere here: reasoning may make a mission
**more cautious or more detailed**; it can never widen scope, lower risk, or
clear an approval requirement. Anything an LLM proposes that would do so is
discarded, not trusted (fail-closed).

Nothing in this module performs network or model calls directly: PlannerQueen /
MemoryQueen receive an injected ``LLMClient`` / retriever, so tests use fakes and
need neither Ollama nor a populated memory DB.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

from aios.core.llm import LLMClient, LLMError
from aios.memory.mistake import MistakeMemory
from aios.runtime.contracts import RiskLevel

_LOGGER = logging.getLogger(__name__)

#: GREEN < YELLOW < RED — used so reasoning can only *raise* risk, never lower it.
_RISK_ORDER: dict[str, int] = {"GREEN": 0, "YELLOW": 1, "RED": 2}


def _max_risk(current: str, proposed: object) -> RiskLevel:
    """Return the higher of *current* and *proposed* risk; never lower than current.

    Fail-closed: an unrecognized *current* risk collapses to RED (the ceiling),
    never the middle — so a malformed floor can never silently relax to YELLOW.
    """
    base = current if current in _RISK_ORDER else "RED"
    if not isinstance(proposed, str) or proposed not in _RISK_ORDER:
        return base  # type: ignore[return-value]
    return (proposed if _RISK_ORDER[proposed] > _RISK_ORDER[base] else base)  # type: ignore[return-value]


def _clamp01(value: object, *, default: float = 0.6) -> float:
    """Parse *value* into a confidence in [0, 1]; fall back to *default*."""
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):  # reject NaN / inf (would surface as max confidence)
        return default
    return max(0.0, min(1.0, result))


def _str_list(value: object) -> list[str]:
    """Return the string items of *value* if it is a list, else [] (defensive)."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


@dataclass(frozen=True)
class ReconciledPlan:
    """An LLM plan after it has been clamped to the request's bounds (fail-closed)."""

    allowed_files: list[str]
    forbidden_files: list[str]
    risk_level: RiskLevel
    requires_approval: bool
    verification_commands: list[str]
    confidence: float
    steps: list[str]


def reconcile_plan(
    *,
    request_allowed: list[str],
    request_forbidden: list[str],
    request_risk: str,
    request_requires_approval: bool,
    request_verification: list[str],
    plan: dict[str, Any],
) -> ReconciledPlan:
    """Clamp an LLM-proposed *plan* to the request's bounds — the security core.

    Narrow-only guarantees:
      * ``allowed_files`` — the LLM may DROP files, never ADD. Files it proposes
        that are not already permitted are ignored. If nothing valid remains, the
        request's allowed set is kept (we never empty or widen it).
      * ``forbidden_files`` — UNION (may add, never remove).
      * ``risk_level`` — may only be RAISED.
      * ``requires_approval`` — may only be set True, never cleared.
      * ``verification_commands`` — UNION (may add; existing preserved).
    """
    narrowed = [f for f in _str_list(plan.get("files_to_touch")) if f in request_allowed]
    allowed_files = narrowed or list(request_allowed)  # never widen, never empty

    forbidden_files = list(
        dict.fromkeys([*request_forbidden, *_str_list(plan.get("forbidden_files"))])
    )

    risk_level = _max_risk(request_risk, plan.get("risk_level"))

    requires_approval = bool(request_requires_approval) or (
        plan.get("requires_approval") is True
    )

    proposed_verif = [c for c in _str_list(plan.get("verification_commands")) if c.strip()]
    verification_commands = list(dict.fromkeys([*request_verification, *proposed_verif]))

    steps = [s for s in _str_list(plan.get("steps")) if s.strip()]

    return ReconciledPlan(
        allowed_files=allowed_files,
        forbidden_files=forbidden_files,
        risk_level=risk_level,
        requires_approval=requires_approval,
        verification_commands=verification_commands,
        confidence=_clamp01(plan.get("confidence")),
        steps=steps,
    )


_PLANNER_SYSTEM = (
    "You are the Planner Queen of a supervised, fail-closed AI operating system. "
    "You propose a bounded plan for a mission. You CANNOT grant permissions: you "
    "may only narrow scope, raise risk, or add verification. Respond with ONE JSON "
    "object and nothing else."
)


def _planner_prompt(*, goal: str, allowed_files: list[str], risk: str) -> str:
    return (
        f"Mission goal:\n{goal}\n\n"
        f"Files you may touch (you may use FEWER, never more): {allowed_files}\n"
        f"Current risk floor (you may RAISE, never lower): {risk}\n\n"
        "Return JSON with keys: steps (string[]), files_to_touch (string[] subset "
        "of the allowed files), verification_commands (string[]), risk_level "
        '("GREEN"|"YELLOW"|"RED"), requires_approval (boolean), confidence '
        "(0..1 number). JSON only."
    )


def _extract_json(text: str) -> dict[str, Any]:
    """Best-effort: parse the first JSON object in *text*. Raise ValueError if none."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object in reasoning output")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("reasoning output is not a JSON object")
    return parsed


def plan_with_llm(
    llm: LLMClient,
    *,
    goal: str,
    allowed_files: list[str],
    risk: str,
) -> dict[str, Any]:
    """Ask *llm* for a plan dict. Raises on transport/parse failure (caller falls back)."""
    try:
        raw = llm.complete(
            _planner_prompt(goal=goal, allowed_files=allowed_files, risk=risk),
            system=_PLANNER_SYSTEM,
        )
    except LLMError as exc:  # transport/model failure → caller uses deterministic path
        raise ValueError(f"planner reasoning failed: {exc}") from exc
    return _extract_json(raw)


@dataclass(frozen=True)
class MemoryRetrieval:
    """What the Memory Queen learned about a mission before it runs."""

    hints: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)  # relevant prior verified failures
    block: bool = False  # a strong exact-shape failure → DENY


@runtime_checkable
class CouncilMemoryRetriever(Protocol):
    """Read-only adapter the Memory Queen consults before a mission."""

    def retrieve(self, goal: str) -> MemoryRetrieval:
        ...


class MistakeBackedRetriever:
    """Default retriever: surfaces verified prior failures relevant to the goal.

    Uses :meth:`MistakeMemory.relevant_verified` (deterministic lexical overlap,
    no embeddings) so the Memory Queen can DEFER on a known failure and DENY when
    a prior failure matches the mission shape strongly.
    """

    def __init__(
        self,
        mistakes: Optional[MistakeMemory] = None,
        *,
        block_relevance: float = 0.6,
        limit: int = 5,
    ) -> None:
        self._mistakes = mistakes or MistakeMemory()
        self._block_relevance = block_relevance
        self._limit = limit

    def retrieve(self, goal: str) -> MemoryRetrieval:
        try:
            lessons = self._mistakes.relevant_verified(goal, limit=self._limit)
        except Exception as exc:  # noqa: BLE001 - retrieval must never break deliberation
            _LOGGER.warning("council_memory_retrieval_failed", exc_info=exc)
            return MemoryRetrieval()
        cautions = [
            f"prior failure [{lesson.get('error_type', 'unknown')}]: "
            f"{lesson.get('lesson_text', '')}".strip()
            for lesson in lessons
        ]
        block = any(
            float(lesson.get("relevance", 0.0)) >= self._block_relevance
            for lesson in lessons
        )
        return MemoryRetrieval(hints=[], cautions=cautions, block=block)


__all__ = [
    "CouncilMemoryRetriever",
    "MemoryRetrieval",
    "MistakeBackedRetriever",
    "ReconciledPlan",
    "plan_with_llm",
    "reconcile_plan",
]
