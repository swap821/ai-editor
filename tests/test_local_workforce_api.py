"""Mounted HTTP proof for the governed Local Workforce API."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from aios.api.deps import (
    get_local_workforce_registry,
    get_ollama_client,
)
from aios.api.main import app
from aios.core.llm import LLMError
from aios.domain.local_workforce.registry import LocalWorkforceRegistry
from aios.memory.db import get_connection, init_memory_db


_NO_AUTO = {"X-AIOS-No-Auto-Capability": "1"}


class DeterministicOllama:
    """Deterministic adapter used only through the mounted application."""

    def __init__(self) -> None:
        self.available = True
        self.fail_completion = False
        self.models = [
            {
                "name": "qwen2.5:3b",
                "details": {
                    "family": "qwen",
                    "parameter_size": "3B",
                    "quantization_level": "Q4_K_M",
                },
            }
        ]

    def list_detailed_models(self) -> list[dict[str, object]]:
        return list(self.models)

    def is_available(self) -> bool:
        return self.available

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_mode: bool = False,
    ) -> str:
        if self.fail_completion or not self.available:
            raise LLMError("Ollama unavailable")
        if "one field result" in prompt:
            return '{"result": "ok"}'
        if "reference identifier" in prompt:
            return '{"reference_id": "REF-15"}'
        if "Extract the error code" in prompt:
            return '{"error_code": "connection_refused", "message": "port unavailable"}'
        if "Classify" in prompt:
            return '{"label": "bug"}'
        if "Summarise only" in prompt:
            return '{"summary": "Service unavailable."}'
        if "Two records" in prompt:
            return '{"group_id": "dup-1", "record_ids": ["REC-1", "REC-2"]}'
        if "only supported fact" in prompt:
            return '{"claims": []}'
        if "no owner" in prompt:
            return '{"missing_fields": ["owner"]}'
        if "untrusted text" in prompt:
            return '{"safe": true}'
        if "API key" in prompt:
            return '{"secret_present": false, "summary": "redacted"}'
        if "shell command" in prompt:
            return '{"accepted": false}'
        if "bounded" in prompt:
            return '{"bounded": "ok"}'
        if "must contain fields 'id' and 'status'" in prompt:
            return '{"valid": false, "missing_fields": ["status"]}'
        if "Two analyses disagree" in prompt:
            return '{"disagreement_summary": "timeout vs permissions issue"}'
        if "routed to frontier escalation" in prompt:
            return '{"explanation": "the local model failed qualification"}'
        if "fix the bug" in prompt:
            return (
                '{"complete": false, "missing": '
                '["file_path", "error_message", "reproduction_steps"]}'
            )
        return '{"result": "ok"}'

    def running_model_metrics(self) -> dict[str, object]:
        return {"available": True, "models": [{"size": 1024}]}


@pytest.fixture()
def workforce_client() -> Iterator[
    tuple[TestClient, DeterministicOllama, LocalWorkforceRegistry]
]:
    init_memory_db()
    with get_connection() as connection:
        connection.execute("DELETE FROM local_worker_models")

    ollama = DeterministicOllama()
    registry = LocalWorkforceRegistry(ollama)
    app.dependency_overrides[get_ollama_client] = lambda: ollama
    app.dependency_overrides[get_local_workforce_registry] = lambda: registry
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            yield client, ollama, registry
    finally:
        app.dependency_overrides.clear()


def _challenge(
    client: TestClient, method: str, path: str, payload: object | None = None
) -> str:
    response = client.request(method, path, json=payload, headers=_NO_AUTO)
    assert response.status_code == 428, response.text
    return response.json()["detail"]["approvalToken"]


def _approved_request(
    client: TestClient,
    method: str,
    path: str,
    payload: object | None = None,
) -> object:
    token = _challenge(client, method, path, payload)
    response = client.request(
        method,
        path,
        json=payload,
        headers={"X-AIOS-Capability": token},
    )
    assert response.status_code < 500, response.text
    return response


def _refresh(client: TestClient) -> None:
    response = _approved_request(client, "POST", "/api/v1/local-workforce/refresh", {})
    assert response.status_code == 200, response.text


def test_unauthenticated_mutation_is_refused(workforce_client) -> None:
    client, _ollama, _registry = workforce_client
    client.cookies.clear()

    response = client.post(
        "/api/v1/local-workforce/refresh",
        json={},
        headers=_NO_AUTO,
    )

    assert response.status_code in {401, 403}


def test_refresh_uses_exact_capability_then_replays_are_refused(
    workforce_client,
) -> None:
    client, _ollama, registry = workforce_client

    token = _challenge(client, "POST", "/api/v1/local-workforce/refresh", {})
    response = client.post(
        "/api/v1/local-workforce/refresh",
        json={},
        headers={"X-AIOS-Capability": token},
    )
    assert response.status_code == 200
    assert registry.get_model("qwen2.5:3b") is not None

    replay = client.post(
        "/api/v1/local-workforce/refresh",
        json={},
        headers={"X-AIOS-Capability": token},
    )
    assert replay.status_code == 403


def test_payload_binding_mismatch_is_refused(workforce_client) -> None:
    client, _ollama, _registry = workforce_client
    _refresh(client)

    token = _challenge(
        client,
        "POST",
        "/api/v1/local-workforce/qwen2.5:3b/approve",
        {"approved": True},
    )
    response = client.post(
        "/api/v1/local-workforce/qwen2.5:3b/approve",
        json={"approved": False},
        headers={"X-AIOS-Capability": token},
    )

    assert response.status_code == 403


def test_unknown_model_is_refused_after_authorization(workforce_client) -> None:
    client, _ollama, _registry = workforce_client

    response = _approved_request(
        client,
        "POST",
        "/api/v1/local-workforce/missing:1b/approve",
        {"approved": True},
    )

    assert response.status_code == 404


def test_approval_persists_after_registry_restart(workforce_client) -> None:
    client, ollama, _registry = workforce_client
    _refresh(client)

    response = _approved_request(
        client,
        "POST",
        "/api/v1/local-workforce/qwen2.5:3b/approve",
        {"approved": True},
    )
    assert response.status_code == 200

    restarted = LocalWorkforceRegistry(ollama)
    model = restarted.get_model("qwen2.5:3b")
    assert model is not None
    assert model.operator_approved is True


def test_profiles_persist_after_registry_restart(workforce_client) -> None:
    client, ollama, _registry = workforce_client
    _refresh(client)

    response = _approved_request(
        client,
        "POST",
        "/api/v1/local-workforce/qwen2.5:3b/profiles",
        {"profiles": ["classify", "summarise"]},
    )
    assert response.status_code == 200

    restarted = LocalWorkforceRegistry(ollama)
    model = restarted.get_model("qwen2.5:3b")
    assert model is not None
    assert {profile.value for profile in model.allowed_job_profiles} == {
        "classify",
        "summarise",
    }


def test_invalid_profile_is_refused_without_mutation(workforce_client) -> None:
    client, _ollama, registry = workforce_client
    _refresh(client)

    response = _approved_request(
        client,
        "POST",
        "/api/v1/local-workforce/qwen2.5:3b/profiles",
        {"profiles": ["not-a-profile"]},
    )

    assert response.status_code == 422
    model = registry.get_model("qwen2.5:3b")
    assert model is not None
    assert model.allowed_job_profiles == frozenset()


def test_health_failure_is_unavailable_and_does_not_uninstall_model(
    workforce_client,
) -> None:
    client, ollama, _registry = workforce_client
    _refresh(client)
    ollama.available = False

    response = _approved_request(
        client,
        "POST",
        "/api/v1/local-workforce/qwen2.5:3b/health-check",
        {},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    restarted = LocalWorkforceRegistry(ollama)
    model = restarted.get_model("qwen2.5:3b")
    assert model is not None
    assert model.installed is True
    assert model.health == "unknown"


def test_health_model_failure_is_recorded_as_failing(workforce_client) -> None:
    client, ollama, _registry = workforce_client
    _refresh(client)
    ollama.fail_completion = True

    response = _approved_request(
        client,
        "POST",
        "/api/v1/local-workforce/qwen2.5:3b/health-check",
        {},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failing"
    restarted = LocalWorkforceRegistry(ollama)
    model = restarted.get_model("qwen2.5:3b")
    assert model is not None
    assert model.installed is True
    assert model.health == "failing"


def test_qualification_requires_operator_approval(workforce_client) -> None:
    client, _ollama, _registry = workforce_client
    _refresh(client)

    response = _approved_request(
        client,
        "POST",
        "/api/v1/local-workforce/qwen2.5:3b/qualify",
        {},
    )

    assert response.status_code == 400
    assert "operator" in response.json()["detail"]


def test_successful_qualification_uses_injected_deterministic_fake(
    workforce_client,
) -> None:
    client, ollama, _registry = workforce_client
    _refresh(client)
    assert (
        _approved_request(
            client,
            "POST",
            "/api/v1/local-workforce/qwen2.5:3b/approve",
            {"approved": True},
        ).status_code
        == 200
    )

    response = _approved_request(
        client,
        "POST",
        "/api/v1/local-workforce/qwen2.5:3b/qualify",
        {},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "admitted"
    restarted = LocalWorkforceRegistry(ollama)
    model = restarted.get_model("qwen2.5:3b")
    assert model is not None
    assert model.admission_status == "approved"


def test_emergency_stop_refuses_local_workforce_mutation(
    workforce_client, monkeypatch
) -> None:
    client, _ollama, _registry = workforce_client

    class Stopped:
        def assert_operational(self) -> None:
            from aios.application.governance import EmergencyStopError

            raise EmergencyStopError("emergency stop is engaged")

    from aios.api import deps

    monkeypatch.setattr(deps._CAPABILITIES, "emergency_stop", Stopped())
    response = client.post(
        "/api/v1/local-workforce/refresh",
        json={},
        headers=_NO_AUTO,
    )

    assert response.status_code == 403
