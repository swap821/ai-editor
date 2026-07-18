from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from aios.application.models.hiring_service import (
    ChatProviderAdapter,
    IntelligenceHiringService,
)
from aios.api.deps import get_hiring_service
from aios.api.main import app
from aios.core import router
from aios.domain.intelligence.broker import HiringBroker
from aios.domain.intelligence.repository import HiringRecordRepository
from aios.domain.privacy import DataClassification, ModelCallRequest, PrivacyPolicy
from aios.domain.privacy import ModelCallRecord
from aios.runtime.cortex_bus import CortexBus


@dataclass
class FakeClient:
    response: str = "frontier answer"
    error: Exception | None = None
    calls: list[tuple[str, str | None, str | None]] = field(default_factory=list)
    max_tokens_seen: list[int | None] = field(default_factory=list)

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        self.calls.append((prompt, system, model))
        self.max_tokens_seen.append(max_tokens)
        if self.error is not None:
            raise self.error
        return self.response


def _request(
    *,
    request_id: str = "request-1",
    classification: DataClassification = DataClassification.PUBLIC,
    local_only: bool = False,
    fallback: str = "deny",
) -> ModelCallRequest:
    return ModelCallRequest(
        request_id=request_id,
        principal_id="operator-1",
        mission_id="mission-1",
        turn_id="turn-1",
        purpose="bounded frontier diagnosis",
        prompt="Explain the bounded failure and propose a verified next step.",
        data_classification=classification,
        task="reasoning",
        policy=PrivacyPolicy(
            data_classification=classification,
            local_only=local_only,
            allowed_providers=("gemini", "ollama"),
            fallback_policy=fallback,
        ),
    )


def _providers(*, cloud_available: bool = True) -> list[router.Provider]:
    return [
        router.Provider(
            "gemini",
            router.PRIVACY_CLOUD,
            router.COST_LOW,
            cloud_available,
            ("gemini-2.5-pro",),
        ),
        router.Provider(
            "ollama", router.PRIVACY_LOCAL, router.COST_FREE, True, ("llama3.2:3b",)
        ),
    ]


def test_hiring_call_executes_injected_provider_and_persists_provenance(
    tmp_path,
) -> None:
    cloud = FakeClient()
    repository = HiringRecordRepository(tmp_path / "state.db")
    cortex = CortexBus(tmp_path / "cortex.db")
    service = IntelligenceHiringService(
        broker=HiringBroker(),
        providers=_providers(),
        clients={"gemini": cloud},
        repository=repository,
        cortex=cortex,
        policy=router.Policy(cloud_tasks=frozenset({"reasoning"}), prefer_local=False),
    )

    result, call = service.complete(_request().model_copy(update={"max_tokens": 37}))

    assert result == "frontier answer"
    assert cloud.calls == [
        (
            "Explain the bounded failure and propose a verified next step.",
            None,
            "gemini-2.5-pro",
        )
    ]
    assert call.selected_provider == "gemini"
    assert call.selected_model == "gemini-2.5-pro"
    assert cloud.max_tokens_seen == [37]
    persisted = HiringRecordRepository(tmp_path / "state.db").get("request-1")
    assert persisted is not None
    assert persisted.status == "completed"
    assert persisted.provider_call_provenance["output_digest"] == call.output_digest
    assert persisted.provider_call_provenance["turn_id"] == "turn-1"
    observations = cortex.peek_pending(limit=10)
    assert len(observations) == 1
    assert observations[0].event_type == "intelligence.model_call.completed"
    assert observations[0].payload["trust"] == "advisory"
    assert observations[0].payload["missionId"] == "mission-1"
    assert observations[0].payload["turnId"] == "turn-1"
    assert observations[0].payload["payload"]["mission_id"] == "mission-1"
    assert observations[0].payload["payload"]["turn_id"] == "turn-1"


def test_chat_provider_adapter_preserves_model_and_bounded_messages() -> None:
    class ChatClient:
        def __init__(self) -> None:
            self.calls = []
            self.max_tokens_seen = []

        def chat(self, messages, *, tools=None, model=None, max_tokens=None):
            self.calls.append((messages, tools, model))
            self.max_tokens_seen.append(max_tokens)
            return {"role": "assistant", "content": "chat result"}

    client = ChatClient()
    adapter = ChatProviderAdapter(client)

    assert (
        adapter.complete(
            "question", system="context", model="gemini-2.5-pro", max_tokens=37
        )
        == "chat result"
    )
    assert client.calls == [
        (
            [
                {"role": "system", "content": "context"},
                {"role": "user", "content": "question"},
            ],
            None,
            "gemini-2.5-pro",
        )
    ]
    assert client.max_tokens_seen == [37]


def test_privacy_is_applied_before_cloud_selection(tmp_path) -> None:
    cloud = FakeClient()
    local = FakeClient(response="local answer")
    service = IntelligenceHiringService(
        broker=HiringBroker(),
        providers=_providers(),
        clients={"gemini": cloud, "ollama": local},
        repository=HiringRecordRepository(tmp_path / "state.db"),
        policy=router.Policy(cloud_tasks=frozenset({"reasoning"}), prefer_local=False),
    )

    result, call = service.complete(
        _request(
            classification=DataClassification.SECRET,
            local_only=False,
        ).model_copy(update={"prompt": "Bearer " + "a" * 32})
    )

    assert result == "local answer"
    assert cloud.calls == []
    assert local.calls[0][0] != "Bearer " + "a" * 32
    assert call.selected_provider == "ollama"
    assert call.redactions
    assert call.local_cloud_decision == "local"


def test_local_only_never_expands_operator_provider_allowlist(tmp_path) -> None:
    cloud = FakeClient()
    service = IntelligenceHiringService(
        broker=HiringBroker(),
        providers=[
            router.Provider(
                "gemini",
                router.PRIVACY_CLOUD,
                router.COST_LOW,
                True,
                ("gemini-2.5-pro",),
            )
        ],
        clients={"gemini": cloud},
        repository=HiringRecordRepository(tmp_path / "state.db"),
        policy=router.Policy(cloud_tasks=frozenset({"reasoning"}), prefer_local=False),
    )

    with pytest.raises(RuntimeError, match="no eligible provider"):
        service.complete(
            _request().model_copy(
                update={
                    "data_classification": DataClassification.SECRET,
                    "policy": PrivacyPolicy(
                        data_classification=DataClassification.SECRET,
                        local_only=False,
                        allowed_providers=("gemini",),
                    ),
                }
            )
        )
    assert cloud.calls == []


def test_cloud_failure_uses_only_explicit_local_fallback(tmp_path) -> None:
    cloud = FakeClient(error=RuntimeError("cloud unavailable"))
    local = FakeClient(response="bounded local fallback")
    service = IntelligenceHiringService(
        broker=HiringBroker(),
        providers=_providers(),
        clients={"gemini": cloud, "ollama": local},
        repository=HiringRecordRepository(tmp_path / "state.db"),
        policy=router.Policy(cloud_tasks=frozenset({"reasoning"}), prefer_local=False),
    )

    result, call = service.complete(_request(fallback="local_only"))

    assert result == "bounded local fallback"
    assert call.fallback == "gemini->ollama"
    assert call.selected_provider == "ollama"


def test_failed_local_fallback_is_persisted_as_failed(tmp_path) -> None:
    cloud = FakeClient(error=RuntimeError("cloud unavailable"))
    local = FakeClient(error=RuntimeError("local unavailable"))
    repository = HiringRecordRepository(tmp_path / "state.db")
    service = IntelligenceHiringService(
        broker=HiringBroker(),
        providers=_providers(),
        clients={"gemini": cloud, "ollama": local},
        repository=repository,
        policy=router.Policy(cloud_tasks=frozenset({"reasoning"}), prefer_local=False),
    )

    with pytest.raises(RuntimeError, match="local unavailable"):
        service.complete(_request(fallback="local_only"))
    persisted = HiringRecordRepository(tmp_path / "state.db").get("request-1")
    assert persisted is not None
    assert persisted.status == "failed"
    assert persisted.provider_call_provenance["fallback"] == "gemini->ollama"


def test_unavailable_provider_is_not_runtime_eligible(tmp_path) -> None:
    cloud = FakeClient()
    service = IntelligenceHiringService(
        broker=HiringBroker(),
        providers=_providers(cloud_available=False),
        clients={"gemini": cloud},
        repository=HiringRecordRepository(tmp_path / "state.db"),
        policy=router.Policy(cloud_tasks=frozenset({"reasoning"}), prefer_local=False),
    )

    with pytest.raises(RuntimeError, match="no eligible provider"):
        service.complete(_request())
    assert cloud.calls == []


class _HTTPHiringFake:
    def __init__(self) -> None:
        self.requests: list[ModelCallRequest] = []

    def complete(self, request: ModelCallRequest):
        self.requests.append(request)
        return "advisory result", ModelCallRecord(
            request_id=request.request_id,
            principal_id=request.principal_id,
            mission_id=request.mission_id,
            turn_id=request.turn_id,
            purpose=request.purpose,
            data_classification=request.data_classification,
            allowed_providers=request.policy.allowed_providers,
            selected_provider="gemini",
            selected_model="gemini-2.5-pro",
            local_cloud_decision="cloud",
            status="completed",
        )


def test_mounted_hiring_call_uses_exact_capability_and_real_service() -> None:
    from fastapi.testclient import TestClient

    fake = _HTTPHiringFake()
    app.dependency_overrides[get_hiring_service] = lambda: fake
    body = {
        "request_id": "http-request-1",
        "mission_id": "http-mission-1",
        "turn_id": "http-turn-1",
        "purpose": "bounded cloud diagnosis",
        "prompt": "Return one advisory diagnosis.",
        "data_classification": "PUBLIC",
        "task": "reasoning",
        "allowed_providers": ["gemini"],
        "local_only": False,
    }
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            challenge = client.post(
                "/api/v1/hiring/call",
                json=body,
                headers={"X-AIOS-No-Auto-Capability": "1"},
            )
            assert challenge.status_code == 428
            token = challenge.json()["detail"]["approvalToken"]
            approved = client.post(
                "/api/v1/hiring/call",
                json=body,
                headers={"X-AIOS-Capability": token},
            )
            assert approved.status_code == 200
            assert approved.json()["advisory"] is True
            assert fake.requests[0].principal_id
            replay = client.post(
                "/api/v1/hiring/call",
                json=body,
                headers={"X-AIOS-Capability": token},
            )
            assert replay.status_code == 403
    finally:
        app.dependency_overrides.clear()
