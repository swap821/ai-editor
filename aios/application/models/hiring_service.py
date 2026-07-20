"""Application boundary for governed, durable intelligence hiring."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Protocol

from aios.core import router
from aios.core.events import CanonicalEvent, EventPhase, TrustLevel
from aios.domain.intelligence.broker import HiringBroker, HiringSelection
from aios.domain.intelligence.repository import HiringRecord, HiringRecordRepository
from aios.domain.privacy import ModelCallRecord, ModelCallRequest, digest_output
from aios.runtime.cortex_bus import CortexBus


class ProviderClient(Protocol):
    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int,
    ) -> str:
        """Execute one bounded, already-authorized provider call."""


class ChatProviderAdapter:
    """Adapt an injected chat client to the bounded completion seam."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int,
    ) -> str:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = self.client.chat(
            messages, tools=None, model=model, max_tokens=max_tokens
        )
        if not isinstance(response, Mapping):
            raise RuntimeError("provider returned an invalid chat response")
        return str(response.get("content") or "")


class IntelligenceHiringService:
    """Execute only routes selected by the canonical HiringBroker."""

    def __init__(
        self,
        *,
        broker: HiringBroker,
        providers: Sequence[router.Provider],
        clients: Mapping[str, ProviderClient],
        repository: HiringRecordRepository,
        cortex: CortexBus | None = None,
        policy: router.Policy = router.LOCAL_FIRST,
    ) -> None:
        self.broker = broker
        self.clients = dict(clients)
        # A provider row without its injected adapter is not executable runtime
        # truth.  Exclude it before HiringBroker selection rather than selecting
        # a route that can only fail after policy has supposedly approved it.
        self.providers = tuple(
            provider for provider in providers if provider.name in self.clients
        )
        self.repository = repository
        self.cortex = cortex
        self.policy = policy

    def complete(
        self,
        request: ModelCallRequest,
        *,
        system: str | None = None,
    ) -> tuple[str, ModelCallRecord]:
        started = time.perf_counter()
        selection = self.broker.select_model_call(
            request,
            self.providers,
            policy=self.policy,
        )
        self._save_selection(request, selection)
        if not selection.routes:
            self._record_observation(request, None, "blocked")
            raise RuntimeError("no eligible provider for governed intelligence request")

        selected = selection.routes[0]
        fallback: str | None = None
        try:
            result = self._execute(
                request, selection.privacy.scrubbed_prompt, selected, system
            )
        except Exception:
            if not self._can_use_local_fallback(request, selection):
                record = self._build_record(
                    request, selection, selected, fallback, "failed", started
                )
                self._persist_result(request, selection, record)
                self._record_observation(request, record, "failed")
                raise
            local = next(
                route
                for route in selection.routes[1:]
                if route.privacy == router.PRIVACY_LOCAL
            )
            fallback = f"{selected.provider}->{local.provider}"
            selected = local
            try:
                result = self._execute(
                    request, selection.privacy.scrubbed_prompt, selected, system
                )
            except Exception:
                record = self._build_record(
                    request, selection, selected, fallback, "failed", started
                )
                self._persist_result(request, selection, record)
                self._record_observation(request, record, "failed")
                raise

        record = self._build_record(
            request, selection, selected, fallback, "completed", started, result=result
        )
        self._persist_result(request, selection, record)
        self._record_observation(request, record, "completed")
        return result, record

    def _execute(
        self,
        request: ModelCallRequest,
        prompt: str,
        route: router.Route,
        system: str | None,
    ) -> str:
        client = self.clients.get(route.provider)
        if client is None:
            raise RuntimeError(
                f"selected provider adapter is not registered: {route.provider}"
            )
        return client.complete(
            prompt,
            system=system,
            model=route.model,
            max_tokens=request.max_tokens,
        )

    @staticmethod
    def _can_use_local_fallback(
        request: ModelCallRequest,
        selection: HiringSelection,
    ) -> bool:
        return (
            selection.routes[0].privacy == router.PRIVACY_CLOUD
            and request.policy.fallback_policy.value == "local_only"
            and any(
                route.privacy == router.PRIVACY_LOCAL for route in selection.routes[1:]
            )
        )

    def _save_selection(
        self, request: ModelCallRequest, selection: HiringSelection
    ) -> None:
        now = _utc_now()
        decision = selection.decision
        self.repository.save(
            HiringRecord(
                request_id=request.request_id,
                mission_id=request.mission_id or "",
                purpose=request.purpose,
                task_class=request.task,
                data_classification=request.data_classification.value,
                candidate_providers=[provider.name for provider in self.providers],
                eligible_providers=list(decision.eligible_providers),
                selected_provider=decision.selected_provider,
                selected_model=decision.selected_model,
                reason=decision.reason,
                redactions=list(decision.redactions),
                cost_class=decision.cost_limit,
                external_data_scope=decision.external_data_scope,
                human_approval_required=decision.human_approval_required,
                status="selected" if decision.selected_provider else "blocked",
                created_at=now,
                updated_at=now,
            )
        )

    def _persist_result(
        self,
        request: ModelCallRequest,
        selection: HiringSelection,
        record: ModelCallRecord,
    ) -> None:
        current = self.repository.get(request.request_id)
        if current is None:
            return
        self.repository.save(
            current.model_copy(
                update={
                    "selected_provider": record.selected_provider,
                    "selected_model": record.selected_model,
                    "status": record.status,
                    "updated_at": record.recorded_at,
                    "provider_call_provenance": record.model_dump(mode="json"),
                }
            )
        )

    def _build_record(
        self,
        request: ModelCallRequest,
        selection: HiringSelection,
        route: router.Route,
        fallback: str | None,
        status: str,
        started: float,
        *,
        result: str | None = None,
    ) -> ModelCallRecord:
        estimated = max(1, len(selection.privacy.scrubbed_prompt) // 4)
        return ModelCallRecord(
            request_id=request.request_id,
            principal_id=request.principal_id,
            mission_id=request.mission_id,
            turn_id=request.turn_id,
            purpose=request.purpose,
            data_classification=request.data_classification,
            redactions=tuple(selection.privacy.redactions),
            allowed_providers=tuple(selection.privacy.allowed_providers),
            requested_max_tokens=request.max_tokens,
            selected_provider=route.provider,
            selected_model=route.model,
            local_cloud_decision=(
                "local" if route.privacy == router.PRIVACY_LOCAL else "cloud"
            ),
            fallback=fallback,
            estimated_tokens=estimated,
            actual_tokens=max(1, len(result) // 4) if result is not None else 0,
            output_digest=digest_output(result) if result is not None else None,
            status=status,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )

    def _record_observation(
        self,
        request: ModelCallRequest,
        record: ModelCallRecord | None,
        status: str,
    ) -> None:
        if self.cortex is None:
            return
        payload: dict[str, Any] = {
            "request_id": request.request_id,
            "mission_id": request.mission_id,
            "turn_id": request.turn_id,
            "purpose": request.purpose,
            "status": status,
        }
        if record is not None:
            payload.update(
                {
                    "provider": record.selected_provider,
                    "model": record.selected_model,
                    "local_cloud_decision": record.local_cloud_decision,
                    "output_digest": record.output_digest,
                    "fallback": record.fallback,
                }
            )
        self.cortex.append(
            CanonicalEvent(
                event_type=f"intelligence.model_call.{status}",
                phase=EventPhase.WONDER.value,
                status=status,
                trust=TrustLevel.ADVISORY.value,
                source="aios.application.models.hiring_service",
                session_id=request.principal_id,
                turn_id=request.turn_id,
                mission_id=request.mission_id,
                payload=payload,
            )
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = ["ChatProviderAdapter", "IntelligenceHiringService", "ProviderClient"]
