"""Critique Queen — a second-order check on verification SUFFICIENCY.

The Testing Queen answers "did it pass?". The Critique Queen answers the deeper
question "was that pass EARNED?" — a green can be hollow: weak strength (an echo/
trivial command), or it never exercised the file that changed. This Queen is
DETERMINISTIC (no LLM) and STRENGTHEN-ONLY: it can only ADD caution (defer); it
never relaxes another Queen's block. Opt-in via AIOS_COUNCIL_CRITIQUE.
"""
from __future__ import annotations

from aios.core.verification_strength import (
    VerificationStrength,
    meets_promotion_floor,
    promotion_floor,
    strength_from_name,
)
from aios.runtime.contracts import MissionContract, QueenVerdict


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


class CritiqueQueen:
    """Scrutinize whether a PASSING verification is actually sufficient."""

    name = "critique"

    def review(
        self,
        *,
        contract: MissionContract,
        testing_verdict: QueenVerdict,
    ) -> QueenVerdict:
        # If the Testing Queen already blocked, the gate handles it — concur quietly.
        # Strengthen-only: the Critique Queen never flips a block to "allow" on its own.
        if testing_verdict.verdict != "allow":
            return QueenVerdict(
                queen=self.name,
                verdict="allow",
                risk="GREEN",
                reason="Deferring to the Testing Queen's blocking verdict.",
                confidence=0.6,
                metadata={"deferred_to": "testing"},
            )

        meta = testing_verdict.metadata or {}
        strength = strength_from_name(
            meta.get("verification_strength"), VerificationStrength.NONE
        )
        cautions: list[str] = []

        # (1) Strength on pass: a green below the promotion floor may be hollow.
        if not meets_promotion_floor(strength):
            cautions.append(
                f"verification is {strength.name}, below the {promotion_floor().name} "
                "floor — the green may not truly exercise the change"
            )

        # (2) Coverage: did any verification command reference a changed file?
        changed = [f for f in (contract.allowed_files or []) if f]
        commands = " ".join(str(c) for c in (contract.verification_commands or []))
        if changed and commands and not any(_basename(f) in commands for f in changed):
            cautions.append(
                "verification commands do not reference the changed file(s): "
                + ", ".join(_basename(f) for f in changed)
            )

        if cautions:
            return QueenVerdict(
                queen=self.name,
                verdict="defer",
                risk="YELLOW",
                reason="Verification passed but looks insufficient: " + "; ".join(cautions),
                constraints=[
                    "Add a test that exercises the change and reaches the STRONG floor.",
                ],
                confidence=0.8,
                metadata={"cautions": cautions, "verification_strength": strength.name},
            )

        return QueenVerdict(
            queen=self.name,
            verdict="allow",
            risk="GREEN",
            reason="Verification is sufficient — STRONG and exercises the change.",
            confidence=0.85,
            metadata={"verification_strength": strength.name},
        )


__all__ = ["CritiqueQueen"]
