"""Clerical job dispatcher (Slice 32, organ 36).

Chooses between deterministic code, the local clerk, frontier escalation,
and human clarification for one clerical job. Granite (or any local model)
is never used merely because it is running: a caller that can answer
deterministically should never reach this function's local-clerk branch at
all, and an unqualified or failing-qualification model must escalate to
frontier intelligence rather than being trusted anyway.

The ledger has always named `ClerkDispatcherAuthority` as this organ's
authority owner, but no such class existed anywhere (Decision A,
docs/architecture/GAGOS_54_ORGANS.md). `dispatch_clerical_job()` itself was
already real and already the thing `LocalWorkforceService._execute_advisory
_job()` calls for every real job (with a genuinely persisted qualification
lookup, `LocalWorkforceRegistry.get_qualification()`, never a fabricated
one) -- the ledger's own blocker text calling this "not wired into the live
request path" was stale, contradicted by the code since PR #165.
`ClerkDispatcherAuthority` makes that real ownership explicit: the service
now calls through it rather than importing the bare function directly.
"""

from __future__ import annotations

from typing import Literal

from aios.domain.local_workforce.qualifier import QualificationResult

DispatchDecision = Literal[
    "deterministic", "local_clerk", "frontier_escalation", "human_clarification"
]


class ClerkDispatcherAuthority:
    """The one authority over how a clerical job is routed: deterministic
    code, the local clerk, frontier escalation, or human clarification.

    Stateless by nature (the decision depends only on its own arguments,
    never on process state) -- the class exists so production code calls
    through one named, ledger-visible owner instead of importing the bare
    decision function directly, matching the organ 42/46/52/29 template.
    """

    def dispatch(
        self,
        *,
        deterministic_available: bool,
        qualification: QualificationResult | None,
        confidence: float | None = None,
        confidence_floor: float = 0.6,
    ) -> DispatchDecision:
        """Decide how one clerical job should be handled.

        Order matters: deterministic code wins whenever it is actually capable
        of answering (checked first, so Granite is never consulted for
        something a parser can already do exactly); an unqualified or failed-
        qualification local model always escalates to frontier, regardless of
        confidence, because a model that has not proven its own reliability
        cannot be trusted to self-report a high-confidence answer; only a
        qualified model's own low-confidence result routes to a human instead
        of silently proceeding or silently escalating.
        """
        if deterministic_available:
            return "deterministic"
        if qualification is None or not qualification.passed:
            return "frontier_escalation"
        if confidence is not None and confidence < confidence_floor:
            return "human_clarification"
        return "local_clerk"


_CLERK_DISPATCHER = ClerkDispatcherAuthority()


def dispatch_clerical_job(
    *,
    deterministic_available: bool,
    qualification: QualificationResult | None,
    confidence: float | None = None,
    confidence_floor: float = 0.6,
) -> DispatchDecision:
    return _CLERK_DISPATCHER.dispatch(
        deterministic_available=deterministic_available,
        qualification=qualification,
        confidence=confidence,
        confidence_floor=confidence_floor,
    )


__all__ = ["ClerkDispatcherAuthority", "DispatchDecision", "dispatch_clerical_job"]
