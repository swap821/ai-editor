"""Memory Queen for the Council Runtime.

Phase 2 echoes contract memory context. Phase 3 ("thinking Queens") optionally
consults an injected retriever over the existing memory engine: it surfaces
relevant prior verified failures and can DEFER (or DENY on a strong match) a
mission that repeats a known failure. It can never grant anything it could not
already — reasoning here only adds caution.
"""

from __future__ import annotations

import logging

from aios import config
from aios.council.reasoning import CouncilMemoryRetriever
from aios.runtime.contracts import MissionContract, QueenVerdict

_LOGGER = logging.getLogger(__name__)


class MemoryQueen:
    """Surface reusable memory context and block on known prior failures."""

    name = "memory"

    def __init__(self, retriever: CouncilMemoryRetriever | None = None) -> None:
        # Optional retriever. None (or config.COUNCIL_REASONING off) keeps the
        # Memory Queen a deterministic context echo that never blocks.
        self._retriever = retriever

    def review(self, contract: MissionContract) -> QueenVerdict:
        metadata_context = contract.metadata.get("memory_context", [])
        if isinstance(metadata_context, str):
            metadata_context = [metadata_context]
        hints = [*contract.pheromone_context, *list(metadata_context)]
        constraints = [str(hint) for hint in hints if str(hint).strip()]

        if self._retriever is not None and config.COUNCIL_REASONING:
            return self._review_with_retrieval(contract, constraints)

        reason = (
            f"Loaded {len(constraints)} memory hint(s) into council context."
            if constraints
            else "No reusable memory hints found for this mission."
        )
        return QueenVerdict(
            queen=self.name,
            verdict="allow",
            risk="GREEN",
            reason=reason,
            constraints=constraints,
            confidence=0.65 if constraints else 0.5,
            metadata={"memory_hints": constraints},
        )

    def _review_with_retrieval(
        self,
        contract: MissionContract,
        base_constraints: list[str],
    ) -> QueenVerdict:
        """Consult the retriever; DEFER on a relevant prior failure, DENY on a
        strong one. Any retrieval error falls back to a plain allow (fail-open is
        unacceptable for *granting*, but retrieval failure must not block work)."""
        assert self._retriever is not None
        try:
            result = self._retriever.retrieve(contract.goal)
        except Exception as exc:  # noqa: BLE001 - retrieval must not break deliberation
            _LOGGER.warning("memory_queen_retrieval_fallback", exc_info=exc)
            return QueenVerdict(
                queen=self.name,
                verdict="allow",
                risk="GREEN",
                reason="Memory retrieval unavailable; proceeding on contract context.",
                constraints=base_constraints,
                confidence=0.5,
                metadata={"memory_hints": base_constraints, "retrieval_error": True},
            )

        hints = [*base_constraints, *result.hints]
        cautions = list(result.cautions)
        metadata = {"memory_hints": hints, "cautions": cautions}

        if result.block:
            return QueenVerdict(
                queen=self.name,
                verdict="deny",
                risk="YELLOW",
                reason=f"Blocked: {len(cautions)} prior verified failure(s) match this mission.",
                constraints=[*cautions, *hints],
                confidence=0.9,
                metadata=metadata,
            )
        if cautions:
            return QueenVerdict(
                queen=self.name,
                verdict="defer",
                risk="YELLOW",
                reason=f"Deferring: {len(cautions)} relevant prior failure(s) to weigh.",
                constraints=[*cautions, *hints],
                confidence=0.8,
                metadata=metadata,
            )
        return QueenVerdict(
            queen=self.name,
            verdict="allow",
            risk="GREEN",
            reason=(
                f"Loaded {len(hints)} memory hint(s); no prior failures match."
                if hints
                else "No reusable memory hints or prior failures found."
            ),
            constraints=hints,
            confidence=0.65 if hints else 0.5,
            metadata=metadata,
        )


__all__ = ["MemoryQueen"]
