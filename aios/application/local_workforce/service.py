"""Application orchestration for the governed local clerical workforce."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from aios.core.llm import LLMClient, LLMError, OllamaClient
from aios.domain.local_workforce.admission import (
    AdmissionContext,
    HardwareAdmission,
)
from aios.domain.local_workforce.contracts import LocalJobProfile, LocalWorkerModel
from aios.domain.local_workforce.qualifier import QualificationSuite
from aios.domain.local_workforce.registry import LocalWorkforceRegistry


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
            self.registry.record_health(model.model_id, "failing", success=False)
            return {
                "status": "failing",
                "health": "failing",
                "model_id": model.model_id,
                "detail": str(exc),
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
