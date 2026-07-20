"""Application orchestration for the governed local clerical workforce."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from aios.core.llm import LLMClient, LLMError, OllamaClient
from aios.domain.local_workforce.admission import (
    AdmissionContext,
    HardwareAdmission,
)
from aios.domain.local_workforce.contracts import (
    LocalJobProfile,
    LocalJobRequest,
    LocalJobResult,
    LocalWorkerModel,
)
from aios.domain.local_workforce.qualifier import QualificationSuite
from aios.domain.local_workforce.registry import LocalWorkforceRegistry

logger = logging.getLogger(__name__)


class LocalModelNotFound(LookupError):
    """Raised when a requested model is not in the durable registry."""


class LocalModelNotApproved(PermissionError):
    """Raised when qualification is requested before human approval."""


class InvalidLocalJobProfile(ValueError):
    """Raised when a profile is outside the governed clerical vocabulary."""


ModelClientFactory = Callable[[str], LLMClient]
QualificationSuiteFactory = Callable[[LLMClient], QualificationSuite]


class LocalWorkforceService:
    """Coordinate local-workforce operations without owning policy authority."""

    def __init__(
        self,
        registry: LocalWorkforceRegistry,
        ollama: LLMClient,
        *,
        hardware_admission: HardwareAdmission | None = None,
        qualification_suite_factory: QualificationSuiteFactory = QualificationSuite,
        model_client_factory: ModelClientFactory | None = None,
    ) -> None:
        self.registry = registry
        self.ollama = ollama
        self.hardware_admission = hardware_admission or HardwareAdmission()
        self.qualification_suite_factory = qualification_suite_factory
        self.model_client_factory = model_client_factory or self._default_model_client

    def refresh(self) -> Sequence[LocalWorkerModel]:
        """Reconcile durable state with the real Ollama model listing."""
        self.registry.reconcile()
        return self.registry.list_models()

    def approve(self, model_id: str, approved: bool) -> LocalWorkerModel:
        model = self._require_model(model_id)
        self.registry.update_approval(model.model_id, approved)
        return self._require_model(model_id)

    def update_profiles(
        self, model_id: str, profile_values: Sequence[str]
    ) -> LocalWorkerModel:
        model = self._require_model(model_id)
        try:
            profiles = {LocalJobProfile(value) for value in profile_values}
        except ValueError as exc:
            raise InvalidLocalJobProfile(str(exc)) from exc
        self.registry.update_profiles(model.model_id, profiles)
        return self._require_model(model_id)

    def health_check(self, model_id: str) -> dict[str, Any]:
        """Probe Ollama and the selected model, preserving unknown availability."""
        model = self._require_model(model_id)
        client = self.model_client_factory(model.model_id)
        is_available = getattr(self.ollama, "is_available", None)
        if callable(is_available) and not bool(is_available()):
            detail = "Ollama is unavailable"
            self.registry.record_health(model.model_id, "unknown", success=False)
            return {
                "status": "unavailable",
                "health": "unknown",
                "model_id": model.model_id,
                "detail": detail,
            }

        try:
            client.complete(
                "Respond with exactly one word: healthy",
                system="Health probe. Return only the requested word.",
            )
        except LLMError as exc:
            logger.warning(
                "Local model %s health probe failed: %s", model.model_id, exc
            )
            self.registry.record_health(model.model_id, "failing", success=False)
            return {
                "status": "failing",
                "health": "failing",
                "model_id": model.model_id,
                "detail": "Model health probe failed; see server logs for details.",
            }

        self.registry.record_health(model.model_id, "healthy", success=True)
        return {"status": "healthy", "health": "healthy", "model_id": model.model_id}

    def qualify(self, model_id: str) -> dict[str, Any]:
        """Run health, hardware, and structured qualification for one model."""
        model = self._require_model(model_id)
        if not model.operator_approved:
            raise LocalModelNotApproved(
                "Model must be operator_approved before qualification"
            )

        health = self.health_check(model.model_id)
        if health["status"] != "healthy":
            reason = str(health.get("detail") or "Health check failed")
            self.registry.update_admission(model.model_id, "rejected", reason)
            return {"status": "rejected", "reason": reason, "health": health}

        admission = self.hardware_admission.evaluate(
            AdmissionContext(
                requested_context_size=model.max_context,
                requested_output_size=model.max_output,
            )
        )
        if not admission.admitted:
            reason = admission.reason or "Hardware admission refused"
            self.registry.update_admission(model.model_id, "rejected", reason)
            return {
                "status": "rejected",
                "reason": reason,
                "admission": admission.model_dump(),
            }

        result = self.qualification_suite_factory(
            self.model_client_factory(model.model_id)
        ).run()
        if result.passed:
            self.registry.update_admission(
                model.model_id,
                "approved",
                "Passed all qualification checks",
            )
            return {"status": "admitted", "qualification": result.model_dump()}

        reason = "Failed qualification suite"
        self.registry.update_admission(model.model_id, "rejected", reason)
        return {
            "status": "rejected",
            "reason": reason,
            "qualification": result.model_dump(),
        }

    def run_advisory_job(
        self,
        request: LocalJobRequest,
        *,
        model_id: str | None = None,
    ) -> LocalJobResult:
        """Execute a governed local clerical job through an admitted model."""
        import time, json

        start_t = time.time()

        registry = self.registry
        if (
            registry is None
            or hasattr(registry, "dependency")
            or not hasattr(registry, "list_models")
        ):
            from aios.api.deps import get_local_workforce_registry

            registry = get_local_workforce_registry()

        try:
            models = registry.list_models()
        except Exception:
            models = []
        admitted = [
            m
            for m in models
            if m.installed
            and m.operator_approved
            and m.admission_status == "approved"
            and getattr(m, "health", "healthy") == "healthy"
            and request.job_profile in m.allowed_job_profiles
        ]
        if not admitted:
            return LocalJobResult(
                job_id=request.job_id,
                model_id=model_id or "none",
                structured_output=None,
                schema_valid=False,
                evidence_references_preserved=False,
                unsupported_claims=("No admitted healthy local model for profile",),
                latency=time.time() - start_t,
                status="rejected",
                failure_reason="No admitted healthy local model for profile",
            )

        selected = admitted[0]
        if model_id and any(m.model_id == model_id for m in admitted):
            selected = next(m for m in admitted if m.model_id == model_id)

        try:
            client = self.model_client_factory(selected.model_id)
            system_msg = (
                f"Advisory clerical job: profile={request.job_profile.value}. "
                "Respond strictly with JSON matching the required schema. No extra text or fields."
            )
            raw_output = client.complete(
                request.redacted_payload,
                system=system_msg,
            )
            parsed = json.loads(raw_output)
            if not isinstance(parsed, dict):
                raise ValueError("Output is not a JSON object")

            schema = dict(request.required_output_schema)
            required_keys = set(schema.keys())
            output_keys = set(parsed.keys())

            # Blocker 9 fix: strict schema validation
            # 1. No extra fields beyond the declared schema
            extra_keys = output_keys - required_keys
            if extra_keys:
                return LocalJobResult(
                    job_id=request.job_id,
                    model_id=selected.model_id,
                    structured_output=parsed,
                    schema_valid=False,
                    evidence_references_preserved=False,
                    unsupported_claims=(
                        f"Extra fields not in schema: {sorted(extra_keys)}",
                    ),
                    latency=time.time() - start_t,
                    status="failed",
                    failure_reason=f"Extra fields rejected: {sorted(extra_keys)}",
                )

            # 2. All required fields must be present
            missing_keys = required_keys - output_keys
            if missing_keys:
                return LocalJobResult(
                    job_id=request.job_id,
                    model_id=selected.model_id,
                    structured_output=parsed,
                    schema_valid=False,
                    evidence_references_preserved=False,
                    unsupported_claims=(
                        f"Missing required fields: {sorted(missing_keys)}",
                    ),
                    latency=time.time() - start_t,
                    status="failed",
                    failure_reason=f"Missing required fields: {sorted(missing_keys)}",
                )

            # 3. Type validation for declared schema types
            _TYPE_MAP = {"bool": bool, "float": (float, int), "int": int, "str": str}
            type_errors: list[str] = []
            for field, declared_type in schema.items():
                if field not in parsed:
                    continue
                expected_py = _TYPE_MAP.get(str(declared_type))
                if expected_py is None:
                    continue
                val = parsed[field]
                if declared_type == "float" and isinstance(val, bool):
                    type_errors.append(f"{field!r}: bool is not a valid float")
                elif declared_type == "bool" and not isinstance(val, bool):
                    type_errors.append(
                        f"{field!r}: expected bool, got {type(val).__name__}"
                    )
                elif declared_type not in ("bool",) and not isinstance(
                    val, expected_py
                ):
                    type_errors.append(
                        f"{field!r}: expected {declared_type}, got {type(val).__name__}"
                    )
            if type_errors:
                return LocalJobResult(
                    job_id=request.job_id,
                    model_id=selected.model_id,
                    structured_output=parsed,
                    schema_valid=False,
                    evidence_references_preserved=False,
                    unsupported_claims=tuple(type_errors),
                    latency=time.time() - start_t,
                    status="failed",
                    failure_reason=f"Type validation failed: {type_errors}",
                )

            # 4. Validate evidence references are preserved
            evidence_refs = set(request.evidence_references)
            evidence_refs_preserved = len(evidence_refs) == 0 or any(
                str(ref) in request.redacted_payload for ref in evidence_refs
            )

            latency = time.time() - start_t
            return LocalJobResult(
                job_id=request.job_id,
                model_id=selected.model_id,
                structured_output=parsed,
                schema_valid=True,
                evidence_references_preserved=evidence_refs_preserved,
                unsupported_claims=(),
                latency=latency,
                status="completed",
                failure_reason=None,
            )
        except Exception as exc:
            return LocalJobResult(
                job_id=request.job_id,
                model_id=selected.model_id,
                structured_output=None,
                schema_valid=False,
                evidence_references_preserved=False,
                unsupported_claims=(str(exc),),
                latency=time.time() - start_t,
                status="failed",
                failure_reason=str(exc),
            )

    def _require_model(self, model_id: str) -> LocalWorkerModel:
        model = self.registry.get_model(model_id)
        if model is None:
            raise LocalModelNotFound(f"Model {model_id} not found in registry")
        return model

    def _default_model_client(self, model_id: str) -> LLMClient:
        if not isinstance(self.ollama, OllamaClient):
            return self.ollama
        return OllamaClient(
            model=model_id,
            host=self.ollama.host,
            timeout_s=self.ollama.timeout_s,
            temperature=self.ollama.temperature,
            num_ctx=self.ollama.num_ctx,
        )


__all__ = [
    "InvalidLocalJobProfile",
    "LocalModelNotFound",
    "LocalModelNotApproved",
    "LocalWorkforceService",
]
