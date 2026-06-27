"""Memory Queen wrapper for current MissionContract context."""
from __future__ import annotations

from aios.runtime.contracts import MissionContract, QueenVerdict


class MemoryQueen:
    """Expose existing memory context without implementing Phase 4 pheromones yet."""

    name = "memory"

    def review(self, contract: MissionContract) -> QueenVerdict:
        metadata_context = contract.metadata.get("memory_context", [])
        if isinstance(metadata_context, str):
            metadata_context = [metadata_context]
        hints = [*contract.pheromone_context, *list(metadata_context)]
        constraints = [str(hint) for hint in hints if str(hint).strip()]
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


__all__ = ["MemoryQueen"]
