"""Application orchestration for the governed local clerical workforce."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
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
    LocalClerkRuntimeAuthority,
)
from aios.domain.local_workforce.qualifier import QualificationSuite
from aios.domain.local_workforce.registry import LocalWorkforceRegistry
from aios.infrastructure.local_workforce.sqlite_store import (
    LocalWorkforceProvenanceStore,
)
from aios.application.local_workforce.dispatcher import ClerkDispatcherAuthority
from aios.application.local_workforce.provenance import ClerkProvenanceAuthority
from aios.application.local_workforce.qualification_evidence import (
    evidence_backed_profiles,
)

logger = logging.getLogger(__name__)

#: How long a qualification run stays valid before the passport is
#: auto-suspended as expired. A stated convention, not a measurement.
QUALIFICATION_VALIDITY_DAYS = 30


class LocalModelNotFound(LookupError):
    """Raised when a requested model is not in the durable registry."""


class LocalModelNotApproved(PermissionError):
    """Raised when qualification is requested before human approval."""


class InvalidLocalJobProfile(ValueError):
    """Raised when a profile is outside the governed clerical vocabulary."""


class UnsupportedJobProfileClaim(InvalidLocalJobProfile):
    """Raised when a profile is a real vocabulary member but the model's own
    qualification evidence does not back it.

    Subclasses InvalidLocalJobProfile so the existing route handler keeps
    returning 422 unchanged, while the type and message stay specific: this
    is "not earned", not "not a real profile".
    """


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
        provenance_store: LocalWorkforceProvenanceStore | None = None,
    ) -> None:
        self.registry = registry
        self.ollama = ollama
        self.hardware_admission = hardware_admission or HardwareAdmission()
        self.qualification_suite_factory = qualification_suite_factory
        self.model_client_factory = model_client_factory or self._default_model_client
        self.provenance_store = provenance_store
        self.local_clerk_runtime_authority = LocalClerkRuntimeAuthority()
        self.provenance_authority = (
            ClerkProvenanceAuthority(provenance_store)
            if provenance_store is not None
            else None
        )
        self.dispatcher_authority = ClerkDispatcherAuthority()

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

        # Organ 33: a profile must be EARNED, never asserted.
        #
        # This route previously wrote whatever the request body asked for,
        # checking only that each value was a real vocabulary member. That is
        # the exact mechanism behind the drift already found in this repo's
        # live registry: granite3.2:2b claimed `summarise` while every recorded
        # qualification run failed summarisation. Validating the vocabulary
        # never had a chance of catching that -- `summarise` IS a valid
        # profile; the model just had not earned it.
        #
        # A profile is now granted only when the model's OWN persisted
        # qualification evidence backs it. Profiles with no test coverage in
        # the suite (9 of 13 today) can never be evidence-backed, so they are
        # refused rather than silently trusted -- an honest limit, not an
        # oversight.
        unsupported = self.unsupported_profile_claims(model_id, frozenset(profiles))
        if unsupported:
            names = ", ".join(sorted(p.value for p in unsupported))
            raise UnsupportedJobProfileClaim(
                f"qualification evidence does not back these profiles for "
                f"{model_id}: {names}. Run qualification first; a profile with "
                "no suite coverage cannot be granted."
            )
        self.registry.update_profiles(model.model_id, profiles)
        return self._require_model(model_id)

    def unsupported_profile_claims(
        self, model_id: str, claimed: frozenset[LocalJobProfile]
    ) -> frozenset[LocalJobProfile]:
        """Which of `claimed` the model's persisted evidence does not support."""
        qualification = self.registry.get_qualification(model_id)
        if qualification is None:
            # Never qualified: nothing is backed. Refusing everything is the
            # honest answer, not an inconvenience to route around.
            return claimed
        evidence = {"runs": [{"result": qualification.model_dump(mode="json")}]}
        return claimed - evidence_backed_profiles(evidence)

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
        # Record the real result BEFORE admission is decided, and on both
        # branches -- a failure is evidence too, and the dispatcher must be
        # able to see one.
        self.registry.record_qualification(model.model_id, result)
        if result.passed:
            # Organ 33: populate the passport from THIS run.
            #
            # record_passport() existed but had zero callers anywhere, so
            # artifact_digest / qualification_evidence_digest / qualified_at /
            # expires_at were never written -- which silently disarmed the
            # auto-suspend triggers that compare against them. A NULL
            # artifact_digest can never differ from a new one, and a NULL
            # expires_at can never be in the past.
            evidence_digest = hashlib.sha256(
                result.model_dump_json().encode("utf-8")
            ).hexdigest()
            qualified_at = datetime.now(timezone.utc)
            self.registry.record_passport(
                model.model_copy(
                    update={
                        "model_version": model.model_version,
                        "artifact_digest": self.registry.current_artifact_digest(
                            model.model_id
                        ),
                        "qualification_suite_version": result.suite_version,
                        "qualification_evidence_digest": evidence_digest,
                        "qualified_at": qualified_at,
                        "expires_at": qualified_at
                        + timedelta(days=QUALIFICATION_VALIDITY_DAYS),
                    }
                )
            )
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
        deterministic_available: bool = False,
        confidence: float | None = None,
    ) -> LocalJobResult:
        """Execute a governed local clerical job, then durably record its
        full provenance (Slice 33, organ 38's `ClerkProvenanceAuthority`)
        -- the real request, model call, and result -- when a store is
        configured. Recording happens after execution, from the same
        request/result objects a caller already sees, so it can never
        fabricate what actually happened; a rejection (no admitted model)
        is recorded as honestly as a success."""
        result, decision = self._execute_advisory_job(
            request,
            model_id=model_id,
            deterministic_available=deterministic_available,
            confidence=confidence,
        )
        if self.provenance_authority is not None:
            model = (
                self.registry.get_model(result.model_id)
                if result.model_id and result.model_id != "none"
                else None
            )
            self.provenance_authority.record_advisory_job(
                request, result, decision, model=model
            )
        return result

    def _execute_advisory_job(
        self,
        request: LocalJobRequest,
        *,
        model_id: str | None = None,
        deterministic_available: bool = False,
        confidence: float | None = None,
    ) -> tuple[LocalJobResult, str]:
        """Execute a governed local clerical job through an admitted model."""
        import time

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
        admitted = list(
            self.local_clerk_runtime_authority.eligible_models(request, models)
        )
        if not admitted:
            decision = self.dispatcher_authority.dispatch(
                deterministic_available=deterministic_available,
                qualification=None,
                confidence=confidence,
            )
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
            ), decision

        selected = admitted[0]
        if model_id and any(m.model_id == model_id for m in admitted):
            selected = next(m for m in admitted if m.model_id == model_id)

        # Organ 36: the REAL persisted qualification, never a fabricated one.
        #
        # This previously constructed a QualificationResult with passed=True,
        # schema_validity=1.0 and secret_reproduction=0 out of nothing, on the
        # grounds that admission_status was already "approved". That made the
        # dispatcher's ONE protection -- "an unqualified or failed-qualification
        # model always escalates to frontier" -- structurally unreachable, since
        # a passing qualification was manufactured at the call site. It also
        # asserted safety properties (no secret reproduction, no authority
        # mutation attempts) from zero evidence, and it laundered an admission
        # that this repo has already seen be wrong in production: granite3.2:2b
        # once claimed `summarise` while every recorded run failed it.
        #
        # None is the honest value for a model with no persisted qualification,
        # and the dispatcher already handles it correctly by escalating.
        qual = self.registry.get_qualification(selected.model_id)

        decision = self.dispatcher_authority.dispatch(
            deterministic_available=deterministic_available,
            qualification=qual,
            confidence=confidence,
        )

        if decision != "local_clerk":
            return LocalJobResult(
                job_id=request.job_id,
                model_id=selected.model_id,
                structured_output=None,
                schema_valid=False,
                evidence_references_preserved=False,
                unsupported_claims=(f"Dispatched to {decision}",),
                latency=time.time() - start_t,
                status="rejected",
                failure_reason=f"Dispatched to {decision}",
            ), decision

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
                ), decision

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
                ), decision

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
                ), decision

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
            ), decision
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
            ), decision

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
