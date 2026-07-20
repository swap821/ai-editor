"""Checkpoint-bound promotion authority.

This service owns the last transition from a verified staged workspace to the
enrolled project.  The callbacks are infrastructure seams: the authority
decides whether they may be called, while snapshot, patch application and
mission persistence remain owned by their existing adapters.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from aios import config
from aios.application.evidence.verification import VerificationAuthority
from aios.application.workspaces.staged import BaselineChanged, StagedWorkspaceManager
from aios.domain.missions.mission_state import MissionState
from aios.domain.promotion import (
    PromotionAuthorization,
    PromotionRequest,
    PromotionResult,
    PromotionStatus,
)



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
    def __call__(
        self, request: PromotionRequest, evidence_ids: tuple[str, ...]
    ) -> None: ...


class PromotionObserver(Protocol):
    def __call__(self, request: PromotionRequest, result: PromotionResult) -> None: ...


class PromotionAuthority:
    """Enforce all promotion preconditions before invoking side effects."""

    def __init__(
        self,
        workspace_manager: StagedWorkspaceManager,
        verification: VerificationAuthority | None = None,
        emergency_stop: Any | None = None,
        database_path: Path | str | None = None,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.verification = verification or VerificationAuthority()
        self.emergency_stop = emergency_stop
        self.database_path = Path(database_path) if database_path else None
        self._promotions: dict[str, PromotionResult] = {}
        self._signing_key = self._resolve_signing_key()

        if self.database_path is not None:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS promotion_records (
                        promotion_id TEXT PRIMARY KEY,
                        mission_id TEXT NOT NULL,
                        action_id TEXT NOT NULL,
                        worker_id TEXT NOT NULL,
                        executor_job_id TEXT NOT NULL,
                        contract_digest TEXT NOT NULL,
                        workspace_digest TEXT NOT NULL,
                        diff_digest TEXT NOT NULL,
                        status TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        integrity_proof TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )

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
            return self._record(request, PromotionStatus.REJECTED, reasons)

        try:
            self._assert_operational()
            checkpoint_id = create_checkpoint(request)
        except Exception as exc:  # noqa: BLE001 - checkpoint failure is a refusal
            return self._record(
                request,
                PromotionStatus.REJECTED,
                ("checkpoint_creation_failed", type(exc).__name__),
            )
        if not checkpoint_id:
            return self._record(
                request,
                PromotionStatus.REJECTED,
                ("checkpoint_id_missing",),
            )

        if request.requires_capability:
            try:
                capability_valid = consume_capability is not None and bool(
                    consume_capability(request)
                )
            except Exception:  # noqa: BLE001 - capability failures deny, never escape
                capability_valid = False
            if not capability_valid:
                return self._record(
                    request,
                    PromotionStatus.REJECTED,
                    ("capability_missing_or_invalid",),
                    checkpoint_id=checkpoint_id,
                )

        try:
            self._assert_operational()
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
            result = self._record(
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

        result = self._record(
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

    def _assert_operational(self) -> None:
        if self.emergency_stop is not None:
            self.emergency_stop.assert_operational()

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
        bundle = request.evidence_bundle
        if bundle is None:
            reasons.append("evidence_bundle_missing")
        else:
            if bundle.mission_id != request.mission_id:
                reasons.append("evidence_mission_mismatch")
            if bundle.worker_id != request.worker_id:
                reasons.append("evidence_worker_mismatch")
            if bundle.contract_digest != request.contract_digest:
                reasons.append("evidence_contract_mismatch")
            if bundle.executor_job_id != request.executor_job_id:
                reasons.append("evidence_executor_job_mismatch")
            if bundle.environment_digest != request.environment_digest:
                reasons.append("evidence_environment_mismatch")
            if bundle.workspace_digest != request.workspace_digest:
                reasons.append("evidence_workspace_mismatch")
            if bundle.diff_digest != request.diff_digest:
                reasons.append("evidence_diff_mismatch")
            if bundle.verification_strength < request.required_strength:
                reasons.append("evidence_strength_insufficient")
            if not set(request.required_targets).issubset(
                set(bundle.targets_exercised)
            ):
                reasons.append("evidence_target_missing")
        if request.requires_capability:
            if not request.capability_id or not request.capability_digest:
                reasons.append("capability_binding_missing")
            elif (
                request.authoritative_capability_digest is not None
                and request.capability_digest != request.authoritative_capability_digest
            ):
                reasons.append("capability_digest_mismatch")
        try:
            # A request carries a frozen lease, but the durable metadata under
            # the workspace manager is authoritative across restarts.  Never
            # promote from a caller-forged lease object or an unregistered
            # workspace path.
            durable_lease = self.workspace_manager.load(request.lease.lease_id)
            if durable_lease != request.lease:
                reasons.append("workspace_lease_mismatch")
            if durable_lease.mission_id != request.mission_id:
                reasons.append("workspace_mission_mismatch")
            if self._resolve(request.project_root) != self._resolve(
                durable_lease.project_root
            ):
                reasons.append("workspace_project_mismatch")
            self.workspace_manager.verify_baseline(durable_lease)
            diff = self.workspace_manager.diff(durable_lease)
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
                if not self.verification.is_authoritative(result):
                    reasons.append("verification_not_authoritative")
                if not self.verification.is_current(
                    result,
                    workspace_digest=request.workspace_digest,
                    diff_digest=request.diff_digest,
                    freshness_seconds=request.freshness_seconds,
                ):
                    reasons.append("verification_stale")
                if (
                    not result.meets_requirement
                    or result.strength < request.required_strength
                ):
                    reasons.append("verification_strength_insufficient")
        return tuple(dict.fromkeys(reasons))

    def is_authoritative(self, result: PromotionResult) -> bool:
        """Reject caller-constructed PromotionResult objects not issued by this authority."""
        held = self.get_promotion(result.mission_id)
        if held is None:
            return False
        return (
            held.status == result.status
            and held.mission_id == result.mission_id
            and held.action_id == result.action_id
            and held.checkpoint_id == result.checkpoint_id
            and held.diff_digest == result.diff_digest
        )

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

    def get_promotion(self, mission_id: str) -> PromotionResult | None:
        """Retrieve authoritative latest promotion result for a mission."""
        return self.get_authoritative_terminal_promotion(mission_id)

    def get_authoritative_terminal_promotion(self, mission_id: str) -> PromotionResult | None:
        """Retrieve the authoritative latest terminal promotion result for a mission."""
        rec = self.get_authoritative_terminal_record(mission_id)
        if rec is not None:
            import json
            res = PromotionResult.model_validate(json.loads(rec["payload_json"]))
            self._promotions[mission_id] = res
            return res
        return self._promotions.get(mission_id)

    # ---------------------------------------------------------------------------
    # Signing key resolution
    # ---------------------------------------------------------------------------

    _INSECURE_DEFAULT_KEYS: frozenset[str] = frozenset({
        "aios-authority-promotion-key-v1",
        "aios-authority-key",
        "changeme",
        "secret",
        "default",
    })

    @staticmethod
    def _resolve_signing_key() -> str:
        """Return the configured signing key or raise RuntimeError if insecure.

        Production policy: key must be configured, >= 32 chars, and not one of
        the known public insecure defaults. Tests use the env var override.
        """
        import os
        key = (
            os.environ.get("AIOS_PROMOTION_AUTHORITY_KEY")
            or getattr(config, "PROMOTION_AUTHORITY_KEY", "")
        )
        is_test = os.environ.get("AIOS_ENV", "").lower() in ("test", "testing", "ci")
        allow_insecure = bool(os.environ.get("AIOS_TEST_SIGNING_KEYS_ALLOWED", ""))
        if not key:
            if is_test or allow_insecure:
                return "test-promotion-signing-key-placeholder-safe"
            raise RuntimeError(
                "AIOS_PROMOTION_AUTHORITY_KEY must be set to a secret of at least "
                "32 characters. The promotion integrity chain is insecure without it."
            )
        if key in PromotionAuthority._INSECURE_DEFAULT_KEYS:
            raise RuntimeError(
                f"AIOS_PROMOTION_AUTHORITY_KEY is set to a known insecure default "
                f"({key!r}). Provide a unique secret."
            )
        if len(key) < 32 and not (is_test or allow_insecure):
            raise RuntimeError(
                "AIOS_PROMOTION_AUTHORITY_KEY must be at least 32 characters."
            )
        return key

    def _compute_integrity_proof(
        self,
        promotion_id: str,
        mission_id: str,
        action_id: str,
        worker_id: str,
        executor_job_id: str,
        contract_digest: str,
        workspace_digest: str,
        diff_digest: str,
        status: str,
        payload_digest: str,
        created_at: str,
    ) -> str:
        import hmac, hashlib
        material = f"{promotion_id}:{mission_id}:{action_id}:{worker_id}:{executor_job_id}:{contract_digest}:{workspace_digest}:{diff_digest}:{status}:{payload_digest}:{created_at}"
        return hmac.new(
            self._signing_key.encode("utf-8"), material.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _record(
        self,
        request: PromotionRequest,
        status: PromotionStatus,
        reasons: tuple[str, ...],
        *,
        checkpoint_id: str | None = None,
        restored: bool = False,
        evidence_ids: tuple[str, ...] = (),
    ) -> PromotionResult:
        import hashlib, json, uuid
        from datetime import datetime, timezone

        res = PromotionResult(
            mission_id=request.mission_id,
            action_id=request.action_id,
            status=status,
            reason_codes=reasons,
            checkpoint_id=checkpoint_id,
            diff_digest=request.diff_digest,
            restored=restored,
            evidence_ids=evidence_ids,
        )
        self._promotions[request.mission_id] = res
        if self.database_path is not None:
            payload = json.dumps(res.model_dump(mode="json"), sort_keys=True)
            payload_digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            promotion_id = f"promotion-{uuid.uuid4().hex}"
            integrity_proof = self._compute_integrity_proof(
                promotion_id,
                request.mission_id,
                request.action_id,
                request.worker_id,
                request.executor_job_id,
                request.contract_digest,
                request.workspace_digest,
                request.diff_digest,
                res.status.value,
                payload_digest,
                created_at,
            )
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO promotion_records (
                        promotion_id, mission_id, action_id, worker_id, executor_job_id,
                        contract_digest, workspace_digest, diff_digest, status, payload_json,
                        integrity_proof, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        promotion_id,
                        request.mission_id,
                        request.action_id,
                        request.worker_id,
                        request.executor_job_id,
                        request.contract_digest,
                        request.workspace_digest,
                        request.diff_digest,
                        res.status.value,
                        payload,
                        integrity_proof,
                        created_at,
                    ),
                )
        return res

    def get_record(self, promotion_id: str) -> dict[str, Any] | None:
        if self.database_path is None:
            return None
        import hmac, hashlib
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT promotion_id, mission_id, action_id, worker_id, executor_job_id,
                       contract_digest, workspace_digest, diff_digest, status, payload_json,
                       integrity_proof, created_at
                FROM promotion_records WHERE promotion_id = ?
                """,
                (promotion_id,),
            ).fetchone()
        if row is None:
            return None
        row_dict = dict(row)
        payload_json = row_dict.get("payload_json", "")
        stored_proof = row_dict.get("integrity_proof", "")
        if not stored_proof or not payload_json:
            return None
        payload_digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        expected_proof = self._compute_integrity_proof(
            row_dict["promotion_id"],
            row_dict["mission_id"],
            row_dict["action_id"],
            row_dict["worker_id"],
            row_dict["executor_job_id"],
            row_dict["contract_digest"],
            row_dict["workspace_digest"],
            row_dict["diff_digest"],
            row_dict["status"],
            payload_digest,
            row_dict["created_at"],
        )
        if not hmac.compare_digest(stored_proof, expected_proof):
            return None  # Tamper detected
        return row_dict

    def get_authoritative_terminal_record(self, mission_id: str) -> dict[str, Any] | None:
        if self.database_path is None:
            return None
        from aios.domain.promotion import PromotionStatus
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT promotion_id FROM promotion_records WHERE mission_id = ? ORDER BY created_at DESC",
                (mission_id,),
            ).fetchall()
        # Blocker 11+12 fix: return the newest valid (tamper-verified) record regardless of
        # status. A newer failure overrides an older promotion. We compare status using the
        # Pydantic enum's actual .value strings (all lowercase) rather than uppercase literals.
        _terminal_statuses = {
            PromotionStatus.PROMOTED.value,
            PromotionStatus.REJECTED.value,
            PromotionStatus.ROLLED_BACK.value,
            PromotionStatus.FAILED.value,
        }
        for row in rows:
            rec = self.get_record(row["promotion_id"])
            if rec is not None and rec["status"] in _terminal_statuses:
                return rec
        return None

    from contextlib import contextmanager
    import sqlite3

    @contextmanager
    def _connection(self) -> Any:
        if self.database_path is None:
            raise RuntimeError("PromotionAuthority database_path is not configured")
        import sqlite3
        conn = sqlite3.connect(self.database_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

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


__all__ = ["PromotionAuthority", "PromotionAuthorization", "PromotionRefused"]

