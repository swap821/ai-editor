"""Checkpoint-bound promotion authority.

This service owns the last transition from a verified staged workspace to the
enrolled project.  The callbacks are infrastructure seams: the authority
decides whether they may be called, while snapshot, patch application and
mission persistence remain owned by their existing adapters.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from aios.application.evidence.verification import VerificationAuthority
from aios.application.workspaces.staged import BaselineChanged, StagedWorkspaceManager
from aios.domain.missions.mission_state import MissionState
from aios.domain.promotion import PromotionRequest, PromotionResult, PromotionStatus


class CapabilityConsumer(Protocol):
    def __call__(self, request: PromotionRequest) -> bool: ...


class CheckpointCreator(Protocol):
    def __call__(self, request: PromotionRequest) -> str: ...


class DiffApplier(Protocol):
    def __call__(self, request: PromotionRequest) -> None: ...


class SmokeTest(Protocol):
    def __call__(self, request: PromotionRequest) -> bool: ...


class CheckpointRestorer(Protocol):
    def __call__(self, checkpoint_id: str, request: PromotionRequest) -> bool: ...


class MissionCompleter(Protocol):
    def __call__(self, request: PromotionRequest, evidence_ids: tuple[str, ...]) -> None: ...


class PromotionObserver(Protocol):
    def __call__(self, request: PromotionRequest, result: PromotionResult) -> None: ...


class PromotionAuthority:
    """Enforce all promotion preconditions before invoking side effects."""

    def __init__(
        self,
        workspace_manager: StagedWorkspaceManager,
        verification: VerificationAuthority | None = None,
        emergency_stop: Any | None = None,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.verification = verification or VerificationAuthority()
        self.emergency_stop = emergency_stop

    def promote(
        self,
        request: PromotionRequest,
        *,
        create_checkpoint: CheckpointCreator,
        apply_staged_diff: DiffApplier,
        smoke_test: SmokeTest,
        restore_checkpoint: CheckpointRestorer,
        consume_capability: CapabilityConsumer | None = None,
        mark_completed: MissionCompleter | None = None,
        emit_observation: PromotionObserver | None = None,
    ) -> PromotionResult:
        """Promote exactly one verified diff, or restore its checkpoint.

        No callback that can mutate the project is reached until every
        fail-closed precondition has passed and a checkpoint exists.  Restore
        receives the exact checkpoint identifier returned by the creator.
        """
        reasons = self._preconditions(request)
        if reasons:
            return self._result(request, PromotionStatus.REJECTED, reasons)

        try:
            checkpoint_id = create_checkpoint(request)
        except Exception as exc:  # noqa: BLE001 - checkpoint failure is a refusal
            return self._result(
                request,
                PromotionStatus.REJECTED,
                ("checkpoint_creation_failed", type(exc).__name__),
            )
        if not checkpoint_id:
            return self._result(
                request,
                PromotionStatus.REJECTED,
                ("checkpoint_id_missing",),
            )

        if request.requires_capability:
            try:
                capability_valid = (
                    consume_capability is not None
                    and bool(consume_capability(request))
                )
            except Exception:  # noqa: BLE001 - capability failures deny, never escape
                capability_valid = False
            if not capability_valid:
                return self._result(
                    request,
                    PromotionStatus.REJECTED,
                    ("capability_missing_or_invalid",),
                    checkpoint_id=checkpoint_id,
                )

        try:
            apply_staged_diff(request)
            if not smoke_test(request):
                raise PromotionRefused("post-promotion smoke test failed")
            evidence_ids = tuple(
                evidence_id
                for result in request.verification_results
                for evidence_id in result.evidence_ids
            )
            if mark_completed is not None:
                mark_completed(request, evidence_ids)
        except Exception as exc:  # noqa: BLE001 - every partial apply is recovered
            restored = self._restore(restore_checkpoint, checkpoint_id, request)
            result = self._result(
                request,
                PromotionStatus.ROLLED_BACK if restored else PromotionStatus.FAILED,
                (
                    "promotion_failed",
                    type(exc).__name__,
                    "checkpoint_restored" if restored else "checkpoint_restore_failed",
                ),
                checkpoint_id=checkpoint_id,
                restored=restored,
            )
            self._observe(emit_observation, request, result)
            return result

        result = self._result(
            request,
            PromotionStatus.PROMOTED,
            ("promotion_complete",),
            checkpoint_id=checkpoint_id,
            restored=False,
            evidence_ids=tuple(
                evidence_id
                for verification in request.verification_results
                for evidence_id in verification.evidence_ids
            ),
        )
        self._observe(emit_observation, request, result)
        return result

    def _preconditions(self, request: PromotionRequest) -> tuple[str, ...]:
        reasons: list[str] = []
        if self.emergency_stop is not None:
            try:
                self.emergency_stop.assert_operational()
            except Exception:  # noqa: BLE001 - engaged stop is a rejection
                reasons.append("emergency_stop_engaged")
        if request.current_state is not MissionState.VERIFYING:
            reasons.append("mission_not_verifying")
        if request.contract_digest != request.authoritative_contract_digest:
            reasons.append("contract_digest_mismatch")
        if request.policy_version != request.authoritative_policy_version:
            reasons.append("policy_version_mismatch")
        if request.requires_capability:
            if not request.capability_id or not request.capability_digest:
                reasons.append("capability_binding_missing")
            elif (
                request.authoritative_capability_digest is not None
                and request.capability_digest != request.authoritative_capability_digest
            ):
                reasons.append("capability_digest_mismatch")
        if request.lease.mission_id != request.mission_id:
            reasons.append("workspace_mission_mismatch")
        if self._resolve(request.project_root) != self._resolve(request.lease.project_root):
            reasons.append("workspace_project_mismatch")

        try:
            self.workspace_manager.verify_baseline(request.lease)
            diff = self.workspace_manager.diff(request.lease)
            if diff["workspace_digest"] != request.workspace_digest:
                reasons.append("workspace_digest_mismatch")
            if diff["diff_digest"] != request.diff_digest:
                reasons.append("diff_digest_mismatch")
        except BaselineChanged:
            reasons.append("project_baseline_changed")
        except (FileNotFoundError, OSError, ValueError):
            reasons.append("staged_workspace_unavailable")

        if not request.verification_results:
            reasons.append("verification_missing")
        else:
            targets = {result.target for result in request.verification_results}
            missing_targets = set(request.required_targets) - targets
            if missing_targets:
                reasons.append("verification_target_missing")
            for result in request.verification_results:
                if result.mission_id != request.mission_id:
                    reasons.append("verification_mission_mismatch")
                if result.action_id != request.action_id:
                    reasons.append("verification_action_mismatch")
                if result.workspace_digest != request.workspace_digest:
                    reasons.append("verification_workspace_mismatch")
                if result.diff_digest != request.diff_digest:
                    reasons.append("verification_diff_mismatch")
                if not self.verification.is_current(
                    result,
                    workspace_digest=request.workspace_digest,
                    diff_digest=request.diff_digest,
                    freshness_seconds=request.freshness_seconds,
                ):
                    reasons.append("verification_stale")
                if not result.meets_requirement or result.strength < request.required_strength:
                    reasons.append("verification_strength_insufficient")
        return tuple(dict.fromkeys(reasons))

    @staticmethod
    def _resolve(value: str) -> Path:
        return Path(value).resolve()

    @staticmethod
    def _restore(
        restore_checkpoint: CheckpointRestorer,
        checkpoint_id: str,
        request: PromotionRequest,
    ) -> bool:
        try:
            return bool(restore_checkpoint(checkpoint_id, request))
        except Exception:  # noqa: BLE001 - restore failure is recorded, never hidden
            return False

    @staticmethod
    def _result(
        request: PromotionRequest,
        status: PromotionStatus,
        reasons: tuple[str, ...],
        *,
        checkpoint_id: str | None = None,
        restored: bool = False,
        evidence_ids: tuple[str, ...] = (),
    ) -> PromotionResult:
        return PromotionResult(
            mission_id=request.mission_id,
            action_id=request.action_id,
            status=status,
            reason_codes=reasons,
            checkpoint_id=checkpoint_id,
            diff_digest=request.diff_digest,
            restored=restored,
            evidence_ids=evidence_ids,
        )

    @staticmethod
    def _observe(
        observer: PromotionObserver | None,
        request: PromotionRequest,
        result: PromotionResult,
    ) -> None:
        if observer is not None:
            observer(request, result)


class PromotionRefused(RuntimeError):
    """Raised internally to force checkpoint recovery after a failed smoke test."""


__all__ = ["PromotionAuthority", "PromotionRefused"]
