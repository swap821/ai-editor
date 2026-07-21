"""Provider selection and model calls behind the Privacy Broker."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence

from aios.application.models.privacy_broker import PrivacyBroker, PrivacyViolation
from aios.core import router
from aios.domain.privacy import (
    ModelCallRecord,
    ModelCallRequest,
    PrivacyDecision,
    digest_output,
)


class ModelClient(Protocol):
    def complete(self, prompt: str, *, system: str | None = None) -> str: ...


class ModelRoutingError(RuntimeError):
    """Raised when policy leaves no usable model route."""


@dataclass(frozen=True)
class ModelRoute:
    route: router.Route
    privacy: PrivacyDecision


class ModelRouter:
    """The only application service allowed to invoke a model provider."""

    def __init__(
        self,
        *,
        privacy: PrivacyBroker | None = None,
        record_call: Callable[[ModelCallRecord], None] | None = None,
    ) -> None:
        self.privacy = privacy or PrivacyBroker()
        self.record_call = record_call

    def select(
        self,
        request: ModelCallRequest,
        providers: Sequence[router.Provider],
        *,
        policy: router.Policy = router.LOCAL_FIRST,
        require_tools: bool = False,
        metrics: Mapping[tuple[str, str, str], float] | None = None,
        picker: Callable[[Sequence[router.Route]], str | None] | None = None,
    ) -> ModelRoute:
        privacy = self.privacy.evaluate(request)
        eligible = [
            provider
            for provider in providers
            if provider.name in privacy.allowed_providers
        ]
        chosen = router.route(
            request.task,
            eligible,
            policy=policy,
            require_tools=require_tools,
            metrics=metrics,
            picker=picker,
        )
        if chosen is None:
            raise ModelRoutingError(
                f"no policy-allowed model for {request.task!r} "
                f"({request.data_classification.value})"
            )
        self.privacy.require(request, provider=chosen.provider)
        return ModelRoute(route=chosen, privacy=privacy)

    def complete(
        self,
        request: ModelCallRequest,
        providers: Sequence[router.Provider],
        clients: Mapping[str, ModelClient],
        *,
        policy: router.Policy = router.LOCAL_FIRST,
        require_tools: bool = False,
        metrics: Mapping[tuple[str, str, str], float] | None = None,
        picker: Callable[[Sequence[router.Route]], str | None] | None = None,
        system: str | None = None,
    ) -> tuple[str, ModelCallRecord]:
        started = time.perf_counter()
        estimated = max(1, len(request.prompt) // 4)
        selected: ModelRoute | None = None
        fallback: str | None = None
        try:
            selected = self.select(
                request,
                providers,
                policy=policy,
                require_tools=require_tools,
                metrics=metrics,
                picker=picker,
            )
            client = clients.get(selected.route.provider)
            if client is None:
                raise ModelRoutingError(
                    f"selected provider is not registered: {selected.route.provider}"
                )
            result = client.complete(selected.privacy.scrubbed_prompt, system=system)
        except Exception as exc:
            # A cloud failure may fall back only to a local provider explicitly
            # permitted by the same request. It never broadens the provider set.
            if selected is None or selected.route.privacy != router.PRIVACY_CLOUD:
                self._record_failure(request, estimated, started, selected, None)
                raise
            if request.policy.fallback_policy.value != "local_only":
                self._record_failure(request, estimated, started, selected, None)
                raise ModelRoutingError(
                    "cloud provider failed and fallback is denied"
                ) from exc
            local_request = request.model_copy(
                update={
                    "policy": request.policy.model_copy(update={"local_only": True})
                }
            )
            local = self.select(
                local_request,
                providers,
                policy=router.Policy(cloud_tasks=frozenset(), prefer_local=True),
                require_tools=require_tools,
                metrics=metrics,
            )
            local_client = clients.get(local.route.provider)
            if local_client is None:
                self._record_failure(request, estimated, started, selected, None)
                raise ModelRoutingError(
                    "cloud failed and no permitted local fallback exists"
                ) from exc
            fallback = f"{selected.route.provider}->{local.route.provider}"
            selected = local
            result = local_client.complete(local.privacy.scrubbed_prompt, system=system)
        actual = max(1, len(result) // 4)
        record = ModelCallRecord(
            request_id=request.request_id,
            principal_id=request.principal_id,
            mission_id=request.mission_id,
            purpose=request.purpose,
            data_classification=request.data_classification,
            redactions=selected.privacy.redactions if selected else (),
            allowed_providers=selected.privacy.allowed_providers if selected else (),
            selected_provider=selected.route.provider if selected else None,
            selected_model=selected.route.model if selected else None,
            local_cloud_decision="local"
            if selected.route.privacy == router.PRIVACY_LOCAL
            else "cloud",
            fallback=fallback,
            estimated_tokens=estimated,
            actual_tokens=actual,
            output_digest=digest_output(result),
            status="completed",
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
        self._emit(record)
        return result, record

    def _record_failure(
        self,
        request: ModelCallRequest,
        estimated: int,
        started: float,
        selected: ModelRoute | None,
        fallback: str | None,
    ) -> None:
        record = ModelCallRecord(
            request_id=request.request_id,
            principal_id=request.principal_id,
            mission_id=request.mission_id,
            purpose=request.purpose,
            data_classification=request.data_classification,
            redactions=selected.privacy.redactions if selected else (),
            allowed_providers=selected.privacy.allowed_providers if selected else (),
            selected_provider=selected.route.provider if selected else None,
            selected_model=selected.route.model if selected else None,
            local_cloud_decision=(
                "local"
                if selected and selected.route.privacy == router.PRIVACY_LOCAL
                else "cloud"
            ),
            fallback=fallback,
            estimated_tokens=estimated,
            status="failed",
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
        self._emit(record)

    def _emit(self, record: ModelCallRecord) -> None:
        if self.record_call is not None:
            self.record_call(record)


__all__ = ["ModelClient", "ModelRoute", "ModelRouter", "ModelRoutingError"]
