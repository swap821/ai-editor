"""Self-consistency-by-verification — N-candidate majority-vote election."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aios.core.verifier import Verifier, VerifierResult


@dataclass(frozen=True)
class ConsistencyResult:
    winner_index: int
    winner_result: "VerifierResult"
    votes: list[bool]
    total_candidates: int
    consensus: bool
    pass_count: int
    fail_count: int


def run_self_consistency(
    verifier: "Verifier",
    candidates: list[str],
    *,
    n: int | None = None,
    session_id: str | None = None,
) -> ConsistencyResult:
    effective_n = n if n is not None else len(candidates)
    effective_n = max(3, effective_n)

    if len(candidates) < effective_n:
        raise ValueError(
            f"need at least {effective_n} candidates, got {len(candidates)}"
        )

    results: list["VerifierResult"] = [
        verifier.verify(candidate, session_id=session_id, approved=True)
        for candidate in candidates
    ]
    votes = [result.passed for result in results]

    pass_count = sum(1 for vote in votes if vote)
    fail_count = len(votes) - pass_count

    threshold = math.ceil(len(candidates) / 2)
    consensus = pass_count >= threshold or fail_count >= threshold

    if pass_count >= threshold:
        winner_index = _best_passing_index(results)
    else:
        winner_index = _best_failing_index(results)

    return ConsistencyResult(
        winner_index=winner_index,
        winner_result=results[winner_index],
        votes=votes,
        total_candidates=len(candidates),
        consensus=consensus,
        pass_count=pass_count,
        fail_count=fail_count,
    )


def _best_passing_index(results: list["VerifierResult"]) -> int:
    best_index = -1
    best_key: tuple[int, float] | None = None
    for index, result in enumerate(results):
        if not result.passed:
            continue
        key = (result.passed_count, result.confidence_delta)
        if best_key is None or key > best_key:
            best_key = key
            best_index = index
    return best_index


def _best_failing_index(results: list["VerifierResult"]) -> int:
    best_index = -1
    best_delta: float | None = None
    for index, result in enumerate(results):
        if result.passed:
            continue
        if best_delta is None or result.confidence_delta > best_delta:
            best_delta = result.confidence_delta
            best_index = index
    return best_index


def elect_best(
    verifier: "Verifier",
    candidates: list[str],
    *,
    session_id: str | None = None,
) -> tuple[int, "VerifierResult"]:
    """Shortcut: run self-consistency and return (winner_index, winner_result)."""
    result = run_self_consistency(verifier, candidates, session_id=session_id)
    return result.winner_index, result.winner_result
