from __future__ import annotations

from dataclasses import dataclass

import pytest

from aios.application.models import ModelRouter, PrivacyBroker
from aios.application.models.privacy_broker import PrivacyViolation
from aios.core import router
from aios.domain.privacy import (
    DataClassification,
    ModelCallRequest,
    PrivacyPolicy,
)


def _request(
    classification: DataClassification,
    *,
    local_only: bool = False,
    providers: tuple[str, ...] = ("ollama", "openai"),
) -> ModelCallRequest:
    return ModelCallRequest(
        request_id="request-1",
        principal_id="principal-1",
        mission_id="mission-1",
        purpose="test",
        prompt="hello",
        data_classification=classification,
        policy=PrivacyPolicy(
            data_classification=classification,
            local_only=local_only,
            allowed_providers=providers,
        ),
    )


def _providers() -> list[router.Provider]:
    return [
        router.Provider("ollama", router.PRIVACY_LOCAL, router.COST_FREE, True, ("local",)),
        router.Provider("openai", router.PRIVACY_CLOUD, router.COST_LOW, True, ("cloud",)),
    ]


def test_never_external_classification_cannot_select_cloud() -> None:
    broker = PrivacyBroker()
    decision = broker.evaluate(_request(DataClassification.NEVER_EXTERNAL))
    assert decision.local_only is True
    assert decision.allowed_providers == ("ollama",)
    with pytest.raises(PrivacyViolation):
        broker.require(_request(DataClassification.NEVER_EXTERNAL), provider="openai")


def test_secret_is_redacted_before_provider_selection() -> None:
    request = _request(DataClassification.SENSITIVE).model_copy(
        update={"prompt": "Bearer " + "a" * 32}
    )
    decision = PrivacyBroker().evaluate(request)
    assert decision.local_only is True
    assert decision.redactions
    assert "Bearer " + "a" * 32 not in decision.scrubbed_prompt


def test_router_calls_only_registered_policy_allowed_provider() -> None:
    @dataclass
    class FakeClient:
        calls: list[str]

        def complete(self, prompt: str, *, system: str | None = None) -> str:
            self.calls.append(prompt)
            return "local result"

    local = FakeClient([])
    cloud = FakeClient([])
    records = []
    result, record = ModelRouter(record_call=records.append).complete(
        _request(DataClassification.PROJECT_INTERNAL, local_only=True),
        _providers(),
        {"ollama": local, "openai": cloud},
    )
    assert result == "local result"
    assert local.calls == ["hello"]
    assert cloud.calls == []
    assert record.selected_provider == "ollama"
    assert record.local_cloud_decision == "local"
    assert record.output_digest
    assert records == [record]


def test_cloud_failure_falls_back_only_to_explicit_local_policy() -> None:
    @dataclass
    class Cloud:
        def complete(self, prompt: str, *, system: str | None = None) -> str:
            raise RuntimeError("offline")

    @dataclass
    class Local:
        def complete(self, prompt: str, *, system: str | None = None) -> str:
            return "fallback"

    request = _request(DataClassification.PUBLIC, local_only=False)
    result, record = ModelRouter().complete(
        request,
        _providers(),
        {"ollama": Local(), "openai": Cloud()},
        policy=router.Policy(cloud_tasks=frozenset({"general"}), prefer_local=False),
    )
    assert result == "fallback"
    assert record.fallback == "openai->ollama"
    assert record.selected_provider == "ollama"
