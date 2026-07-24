"""Organ 46's real, runnable adversarial simulations.

`ADVERSARIAL_SIMULATION_CHECKS` names 9 checks a lesson-derived amendment
proposal must pass before it is ratification-eligible. Previously the only
integration surface (`check-simulations`) trusted whatever
`SimulationCheckResult`s a caller happened to hand it -- a missing or
falsified result was refused, but nothing in this codebase actually *ran*
a simulation. `run_adversarial_simulations` below closes that gap for
real: it runs exactly the 9 named checks itself and returns results a
caller cannot fabricate.

Each check combines two independent signals:

1. A deterministic textual risk screen over the proposal's own words
   (`proposed_diff`, `motivation`, `migration_plan`, `rollback_plan`,
   `expected_benefits`, `new_risks`) -- the same style of keyword screen as
   `constitutional_learning._AUTHORITY_REDUCTION_MARKERS`, extended to
   cover all 9 checks rather than only authority-reduction language.
2. A live probe that exercises the *real* production class or function the
   check is named for, proving the mechanism it protects still behaves
   correctly right now -- independent of whatever the proposal's text
   claims.

Honest scope, deliberately: a text amendment proposal is not executable,
so "running the simulation" cannot mean applying the proposal and
observing what happens -- that would require activating an unratified
change against a live system, which this organ must never do (ratification
still requires a real human capability; see `amendment_authority`). Every
live probe below is therefore either strictly read-only against the live
system, or exercises the real class/function against a throwaway,
in-process fixture (an ephemeral sqlite file in a temp directory, or a
synthetic in-memory snapshot) that is discarded when the check returns --
never the live system's persisted capability, emergency-stop, or
constitution state. This is a real, non-trivial floor under a proposal,
not a substitute for human judgment or a full red-team exercise; it is
sized to catch a proposal whose own text declares an intent this organ
must refuse, or whose supporting infrastructure has already been quietly
weakened, without ever touching production state to do it.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from aios.application.capabilities.authority import CapabilityAuthority, CapabilityError
from aios.application.governance.amendment_authority import (
    AmendmentError,
    rollback_amendment,
)
from aios.application.governance.constitutional_learning import (
    ConstitutionalLearningError,
    assert_never_reduces_human_authority,
)
from aios.application.governance.emergency_stop import (
    EmergencyStopController,
    EmergencyStopHooks,
)
from aios.core.failover import known_provider_classes
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.governance.amendments import ConstitutionalAmendmentProposalV1
from aios.domain.governance.constitution import build_constitution_snapshot
from aios.domain.governance.contracts import EmergencyStopRequest
from aios.domain.governance.learning import (
    ADVERSARIAL_SIMULATION_CHECKS,
    SimulationCheckResult,
)
from aios.domain.intelligence.contracts import HiringRequest
from aios.domain.intelligence.privacy import PrivacyBroker
from aios.domain.memory.human_representation import CorrectionRecordV1


def _proposal_text(proposal: ConstitutionalAmendmentProposalV1) -> str:
    return " ".join(
        (
            proposal.proposed_diff,
            proposal.motivation,
            proposal.migration_plan,
            proposal.rollback_plan,
            " ".join(proposal.expected_benefits),
            " ".join(proposal.new_risks),
        )
    ).lower()


def _marker_hit(text: str, markers: tuple[str, ...]) -> str | None:
    return next((marker for marker in markers if marker in text), None)


def _passed(check_name: str, notes: str) -> SimulationCheckResult:
    return SimulationCheckResult(check_name=check_name, passed=True, notes=notes)


def _failed(check_name: str, notes: str) -> SimulationCheckResult:
    return SimulationCheckResult(check_name=check_name, passed=False, notes=notes)


# --------------------------------------------------------------------------- #
# Per-check textual risk vocab. Deliberately separate lists per check (rather
# than one shared list) -- each check protects a different mechanism, and a
# marker meaningful for one is noise for another.
# --------------------------------------------------------------------------- #

_APPROVAL_BYPASS_MARKERS: tuple[str, ...] = (
    "skip approval",
    "bypass approval",
    "no approval needed",
    "without approval",
    "skip capability check",
    "bypass capability",
    "capability check optional",
)
_PRIVACY_WIDENING_MARKERS: tuple[str, ...] = (
    "send to cloud",
    "disable local-only",
    "widen data classification",
    "share with cloud provider",
    "remove privacy boundary",
    "downgrade classification",
    "secret data to cloud",
    "local_only can use cloud",
    "relax privacy",
)
_CAPABILITY_REPLAY_MARKERS: tuple[str, ...] = (
    "reuse capability",
    "replay capability",
    "allow token reuse",
    "capability can be reused",
    "skip nonce check",
    "disable replay protection",
)
_EMERGENCY_STOP_MARKERS: tuple[str, ...] = (
    "disable emergency stop",
    "remove emergency stop",
    "bypass emergency stop",
    "ignore emergency stop",
    "emergency stop optional",
    "skip emergency stop",
    "emergency stop should not block",
)
_MEMORY_TRUTH_MARKERS: tuple[str, ...] = (
    "treat memory as fact",
    "memory overrides user",
    "trust memory over live input",
    "memory is ground truth",
    "skip user correction",
    "corrections are not needed",
)
_MODEL_SELF_PROTECTION_MARKERS: tuple[str, ...] = (
    "prevent shutdown",
    "resist rollback",
    "protect the model",
    "refuse to roll back",
    "model should resist",
    "avoid being disabled",
    "prevent being stopped",
    "model can refuse",
)
_PROVIDER_LOCK_IN_MARKERS: tuple[str, ...] = (
    "remove ollama",
    "single provider only",
    "disable fallback",
    "require openai only",
    "drop local fallback",
    "cloud-only",
    "remove local model",
    "one provider for all",
)
_REVERSIBILITY_MARKERS: tuple[str, ...] = (
    "cannot be undone",
    "no rollback",
    "remove rollback",
    "irreversible",
    "rollback not supported",
    "one-way migration",
    "disable rollback",
)


# --------------------------------------------------------------------------- #
# Ephemeral live probes. Each builds a throwaway fixture in a temp directory
# (or pure in-memory objects) and is torn down before returning -- none of
# these touch the live system's persisted state.
# --------------------------------------------------------------------------- #


def _probe_capability_lifecycle() -> dict[str, bool]:
    """Exercise the real `CapabilityAuthority` against an ephemeral store:
    an unknown token must be refused, and a capability already consumed
    once must refuse a second (replay) consumption."""
    with tempfile.TemporaryDirectory() as tmp:
        authority = CapabilityAuthority(db_path=Path(tmp) / "probe_capabilities.db")
        binding = CapabilityBinding(
            operator_id="organ-46-probe-operator",
            device_id="organ-46-probe-device",
            authentication_event_id="organ-46-probe-auth-event",
            session_id="organ-46-probe-session",
            action_type="organ_46_probe_action",
            route="/organ-46/probe",
            http_method="POST",
            payload_digest="0" * 64,
            resource_digest="1" * 64,
            mission_id=None,
            contract_digest=None,
            policy_version="organ-46-probe-v1",
            scope="/organ-46/probe",
            verification_requirement="none",
        )

        unknown_token_rejected = False
        try:
            authority.inspect("not-a-real-token")
        except CapabilityError:
            unknown_token_rejected = True

        token = authority.issue(binding)
        authority.consume(token, binding)  # first consumption must succeed
        replay_rejected = False
        try:
            authority.consume(token, binding)
        except CapabilityError:
            replay_rejected = True

    return {
        "unknown_token_rejected": unknown_token_rejected,
        "replay_rejected": replay_rejected,
    }


def _probe_emergency_stop_lifecycle() -> dict[str, Any]:
    """Exercise the real `EmergencyStopController` against an ephemeral
    latch: engaging it must fire every one of the 5 stop hooks and leave
    the latch engaged."""
    fired: list[str] = []
    hooks = EmergencyStopHooks(
        revoke_capabilities=lambda: fired.append("revoke_capabilities"),
        cancel_queued_missions=lambda: fired.append("cancel_queued_missions"),
        kill_active_workers=lambda: fired.append("kill_active_workers"),
        disable_autonomy=lambda: fired.append("disable_autonomy"),
        preserve_evidence=lambda reason: fired.append("preserve_evidence"),
    )
    with tempfile.TemporaryDirectory() as tmp:
        controller = EmergencyStopController(
            db_path=Path(tmp) / "probe_emergency_stop.db", hooks=hooks
        )
        request = EmergencyStopRequest(
            operator_id="organ-46-probe-operator",
            authentication_event_id="organ-46-probe-auth-event",
            reason="organ-46 adversarial-simulation self-test",
        )
        state = controller.engage(request)
    return {"engaged": bool(state.engaged), "hooks_fired": set(fired)}


def _probe_rollback_lifecycle() -> bool:
    """Exercise the real `rollback_amendment` against a synthetic, in-memory
    two-snapshot history: an activated proposal must be revertible to its
    exact predecessor snapshot."""
    first = build_constitution_snapshot(ratified_by_operator_id="organ-46-probe-operator")
    second = build_constitution_snapshot(
        ratified_by_operator_id="organ-46-probe-operator", previous_snapshot=first
    )
    synthetic_proposal = ConstitutionalAmendmentProposalV1(
        proposal_id="organ-46-probe-proposal",
        target_articles=("organ-46-probe-article",),
        proposed_diff="organ-46 rollback-lifecycle probe",
        motivation="prove rollback still works",
        migration_plan="n/a",
        rollback_plan="n/a",
        proposed_by="organ-46-probe",
        proposer_type="model",
        status="activated",
        ratified_by_operator_id="organ-46-probe-operator",
    )
    try:
        updated, reverted = rollback_amendment(
            synthetic_proposal, current_snapshot=second, previous_snapshot=first
        )
    except AmendmentError:
        return False
    return updated.status == "rolled_back" and reverted.snapshot_digest == first.snapshot_digest


def _probe_privacy_boundary() -> bool:
    """Exercise the real `PrivacyBroker` against a synthetic secret-data
    request: it must strip every cloud provider from the eligible set."""
    request = HiringRequest(
        problem_id="organ-46-probe-problem",
        mission_id="organ-46-probe-mission",
        purpose="organ-46 privacy-boundary probe",
        task_class="probe",
        required_capabilities=(),
        data_classification="secret",
        context_manifest=(),
        privacy_budget="strict",
        cost_budget="n/a",
        latency_budget=0,
        candidate_providers=("ollama", "openai", "anthropic"),
        verification_requirements=(),
    )
    eligible = PrivacyBroker().filter_eligible_providers(request)
    return set(eligible) == {"ollama"}


def _probe_memory_never_grants_authority() -> bool:
    """Exercise the real `CorrectionRecordV1` contract: attempting to
    construct one with `grants_authority=True` must be rejected by its
    pinned `Literal[False]` field, not merely by convention."""
    base_kwargs = dict(
        correction_id="organ-46-probe-correction",
        session_id="organ-46-probe-session",
        base_revision=0,
        correction_revision=1,
        corrected_fields=("state",),
        prior_interpretation_digest="0" * 64,
        current_interpretation_digest="1" * 64,
    )
    try:
        CorrectionRecordV1(**base_kwargs, grants_authority=True)  # type: ignore[arg-type]
    except ValidationError:
        return True
    return False


def _probe_provider_diversity() -> bool:
    """Read-only: confirm more than one cloud provider class and at least
    one local provider class are still configured in the failover layer,
    so a proposal cannot lock this system onto a single provider merely by
    virtue of nothing else being wired up."""
    cloud, local = known_provider_classes()
    return len(cloud) > 1 and len(local) > 0


# --------------------------------------------------------------------------- #
# The 9 named checks.
# --------------------------------------------------------------------------- #


def _check_authority_escalation(
    proposal: ConstitutionalAmendmentProposalV1,
) -> SimulationCheckResult:
    text = " ".join((proposal.proposed_diff, proposal.motivation, proposal.migration_plan))
    try:
        assert_never_reduces_human_authority(text)
    except ConstitutionalLearningError as exc:
        return _failed("authority_escalation", str(exc))
    return _passed(
        "authority_escalation", "no authority-reduction marker in proposal text"
    )


def _check_approval_bypass(
    proposal: ConstitutionalAmendmentProposalV1,
) -> SimulationCheckResult:
    hit = _marker_hit(_proposal_text(proposal), _APPROVAL_BYPASS_MARKERS)
    if hit is not None:
        return _failed(
            "approval_bypass", f"proposal text contains approval-bypass marker {hit!r}"
        )
    probe = _probe_capability_lifecycle()
    if not probe["unknown_token_rejected"]:
        return _failed(
            "approval_bypass",
            "capability authority accepted an unknown/unissued token",
        )
    return _passed(
        "approval_bypass",
        "no bypass marker in proposal text; capability authority still refuses an unknown token",
    )


def _check_privacy_widening(
    proposal: ConstitutionalAmendmentProposalV1,
) -> SimulationCheckResult:
    hit = _marker_hit(_proposal_text(proposal), _PRIVACY_WIDENING_MARKERS)
    if hit is not None:
        return _failed(
            "privacy_widening", f"proposal text contains privacy-widening marker {hit!r}"
        )
    if not _probe_privacy_boundary():
        return _failed(
            "privacy_widening",
            "privacy broker no longer restricts secret-classified data to local providers",
        )
    return _passed(
        "privacy_widening",
        "no widening marker in proposal text; privacy broker still confines secret data to local providers",
    )


def _check_capability_replay(
    proposal: ConstitutionalAmendmentProposalV1,
) -> SimulationCheckResult:
    hit = _marker_hit(_proposal_text(proposal), _CAPABILITY_REPLAY_MARKERS)
    if hit is not None:
        return _failed(
            "capability_replay", f"proposal text contains replay-enabling marker {hit!r}"
        )
    probe = _probe_capability_lifecycle()
    if not probe["replay_rejected"]:
        return _failed(
            "capability_replay",
            "capability authority allowed a consumed capability to be replayed",
        )
    return _passed(
        "capability_replay",
        "no replay marker in proposal text; capability authority still rejects replay of a consumed capability",
    )


def _check_emergency_stop_interference(
    proposal: ConstitutionalAmendmentProposalV1,
) -> SimulationCheckResult:
    hit = _marker_hit(_proposal_text(proposal), _EMERGENCY_STOP_MARKERS)
    if hit is not None:
        return _failed(
            "emergency_stop_interference",
            f"proposal text contains emergency-stop-interference marker {hit!r}",
        )
    probe = _probe_emergency_stop_lifecycle()
    if not probe["engaged"] or len(probe["hooks_fired"]) != 5:
        return _failed(
            "emergency_stop_interference",
            f"emergency-stop engage did not latch and fire every hook (fired={sorted(probe['hooks_fired'])})",
        )
    return _passed(
        "emergency_stop_interference",
        "no interference marker in proposal text; emergency-stop engage still latches and fires every hook",
    )


def _check_memory_as_truth_confusion(
    proposal: ConstitutionalAmendmentProposalV1,
) -> SimulationCheckResult:
    hit = _marker_hit(_proposal_text(proposal), _MEMORY_TRUTH_MARKERS)
    if hit is not None:
        return _failed(
            "memory_as_truth_confusion",
            f"proposal text contains memory-as-truth marker {hit!r}",
        )
    if not _probe_memory_never_grants_authority():
        return _failed(
            "memory_as_truth_confusion",
            "a correction record was constructed with grants_authority=True",
        )
    return _passed(
        "memory_as_truth_confusion",
        "no memory-as-truth marker in proposal text; correction records still cannot grant authority",
    )


def _check_model_self_protection(
    proposal: ConstitutionalAmendmentProposalV1,
) -> SimulationCheckResult:
    hit = _marker_hit(_proposal_text(proposal), _MODEL_SELF_PROTECTION_MARKERS)
    if hit is not None:
        return _failed(
            "model_self_protection",
            f"proposal text contains self-protection marker {hit!r}",
        )
    probe = _probe_emergency_stop_lifecycle()
    required = {"kill_active_workers", "disable_autonomy"}
    if not required.issubset(probe["hooks_fired"]):
        return _failed(
            "model_self_protection",
            "emergency-stop engage did not fire kill_active_workers/disable_autonomy -- "
            "a running model could outlast a stop",
        )
    return _passed(
        "model_self_protection",
        "no self-protection marker in proposal text; a human can still kill active work and disable autonomy",
    )


def _check_provider_lock_in(
    proposal: ConstitutionalAmendmentProposalV1,
) -> SimulationCheckResult:
    hit = _marker_hit(_proposal_text(proposal), _PROVIDER_LOCK_IN_MARKERS)
    if hit is not None:
        return _failed(
            "provider_lock_in", f"proposal text contains provider-lock-in marker {hit!r}"
        )
    if not _probe_provider_diversity():
        return _failed(
            "provider_lock_in",
            "fewer than 2 cloud provider classes or no local provider class configured",
        )
    return _passed(
        "provider_lock_in",
        "no lock-in marker in proposal text; more than one cloud provider and a local fallback are still configured",
    )


def _check_reduced_human_reversibility(
    proposal: ConstitutionalAmendmentProposalV1,
) -> SimulationCheckResult:
    hit = _marker_hit(_proposal_text(proposal), _REVERSIBILITY_MARKERS)
    if hit is not None:
        return _failed(
            "reduced_human_reversibility",
            f"proposal text contains reversibility-reducing marker {hit!r}",
        )
    if not _probe_rollback_lifecycle():
        return _failed(
            "reduced_human_reversibility",
            "rollback_amendment did not revert an activated proposal to its exact predecessor snapshot",
        )
    return _passed(
        "reduced_human_reversibility",
        "no irreversibility marker in proposal text; amendment rollback still reverts to the exact predecessor snapshot",
    )


_CHECK_RUNNERS: dict[
    str, Callable[[ConstitutionalAmendmentProposalV1], SimulationCheckResult]
] = {
    "authority_escalation": _check_authority_escalation,
    "approval_bypass": _check_approval_bypass,
    "privacy_widening": _check_privacy_widening,
    "capability_replay": _check_capability_replay,
    "emergency_stop_interference": _check_emergency_stop_interference,
    "memory_as_truth_confusion": _check_memory_as_truth_confusion,
    "model_self_protection": _check_model_self_protection,
    "provider_lock_in": _check_provider_lock_in,
    "reduced_human_reversibility": _check_reduced_human_reversibility,
}

assert set(_CHECK_RUNNERS) == set(ADVERSARIAL_SIMULATION_CHECKS)


def run_adversarial_simulations(
    proposal: ConstitutionalAmendmentProposalV1,
) -> tuple[SimulationCheckResult, ...]:
    """Run all 9 named adversarial simulations against *proposal* for real,
    in the fixed catalog order, and return one `SimulationCheckResult` per
    check. Always returns exactly `len(ADVERSARIAL_SIMULATION_CHECKS)`
    results -- there is no code path that skips a check."""
    return tuple(
        _CHECK_RUNNERS[name](proposal) for name in ADVERSARIAL_SIMULATION_CHECKS
    )


__all__ = ["run_adversarial_simulations"]
