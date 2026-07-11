from __future__ import annotations

import sys
from pathlib import Path

from aios.runtime.contracts import MissionContract
from aios.runtime.intelligence_gateway import (
    IntelligenceRequest,
    IntelligenceGateway,
    IntelligenceResponse,
)
from aios.runtime.worker_entry import run_worker
from aios.runtime.worker_api import WorkerRuntime


class FakeReasoner:
    def __init__(self, text: str, *, fail: bool = False) -> None:
        self.text = text
        self.fail = fail
        self.calls: list[tuple[str, str | None]] = []

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls.append((prompt, system))
        if self.fail:
            raise RuntimeError("provider unavailable")
        return self.text


class FakeGateway:
    def __init__(self, response: IntelligenceResponse) -> None:
        self.response = response
        self.calls = 0

    def request(self, request, *, contract):  # noqa: ANN001 - protocol test fake
        self.calls += 1
        assert request.mission_id == contract.mission_id
        return self.response


def _mission(tmp_path: Path, **overrides: object) -> MissionContract:
    data: dict[str, object] = {
        "mission_id": "mission-phase1b",
        "goal": "Create a plan without executing it.",
        "worker_type": "hybrid_plan_worker",
        "created_by": "planner",
        "workspace_root": str(tmp_path),
        "allowed_files": ["frontend/src/pages/Login.jsx"],
        "forbidden_files": ["backend/", ".env", "aios/security/"],
        "allowed_tools": ["request_plan"],
        "risk_level": "GREEN",
        "metadata": {
            "model_policy": {
                "mode": "hybrid",
                "allow_cloud": True,
                "max_cloud_calls": 1,
                "max_tokens_per_request": 1500,
                "max_tokens_total": 6000,
                "provider": "gemini",
            }
        },
    }
    data.update(overrides)
    return MissionContract(**data)


def test_gateway_uses_cloud_only_when_policy_budget_and_secrets_allow(
    tmp_path: Path,
) -> None:
    local = FakeReasoner("local plan")
    cloud = FakeReasoner("cloud plan")
    gateway = IntelligenceGateway(
        local_client=local,
        cloud_clients={"gemini": cloud},
    )
    contract = _mission(tmp_path)

    response = gateway.request(
        request=gateway_request(contract, allow_cloud=True),
        contract=contract,
    )

    assert response.used_cloud is True
    assert response.provider == "gemini"
    assert response.text == "cloud plan"
    assert cloud.calls
    assert local.calls == []


def test_gateway_falls_back_to_local_when_budget_blocks_cloud(
    tmp_path: Path,
) -> None:
    local = FakeReasoner("local fallback")
    cloud = FakeReasoner("cloud should not run")
    gateway = IntelligenceGateway(
        local_client=local,
        cloud_clients={"gemini": cloud},
    )
    contract = _mission(
        tmp_path,
        metadata={
            "model_policy": {
                "mode": "hybrid",
                "allow_cloud": True,
                "max_cloud_calls": 0,
                "max_tokens_per_request": 1500,
                "max_tokens_total": 6000,
                "provider": "gemini",
            }
        },
    )

    response = gateway.request(
        request=gateway_request(contract, allow_cloud=True),
        contract=contract,
    )

    assert response.used_cloud is False
    assert response.provider == "ollama"
    assert response.fallback_used is True
    assert response.policy["budget_reason"] == "mission cloud call budget exceeded"
    assert cloud.calls == []
    assert local.calls


def test_gateway_redacts_secrets_and_keeps_secret_prompt_local(
    tmp_path: Path,
) -> None:
    local = FakeReasoner("local plan mentions sk-12345678901234567890123456789012")
    cloud = FakeReasoner("cloud should not see secrets")
    gateway = IntelligenceGateway(
        local_client=local,
        cloud_clients={"gemini": cloud},
    )
    contract = _mission(tmp_path)

    response = gateway.request(
        request=gateway_request(
            contract,
            prompt="Plan using api_key=abcdefghijklmnop and do not leak it",
            allow_cloud=True,
        ),
        contract=contract,
    )

    assert response.used_cloud is False
    assert response.policy["secret_detected"] is True
    assert "<REDACTED:" in local.calls[0][0]
    assert "abcdefghijklmnop" not in local.calls[0][0]
    assert "<REDACTED:" in response.text
    assert "sk-12345678901234567890123456789012" not in response.text
    assert cloud.calls == []


def test_worker_runtime_request_plan_records_plan_only_evidence(
    tmp_path: Path,
) -> None:
    contract = _mission(tmp_path)
    response = IntelligenceResponse(
        provider="gemini",
        model="gemini-test",
        used_cloud=True,
        text="1. Edit only allowed files.",
        cost_estimate=0.0,
        fallback_used=False,
        policy={"cloud_allowed": True},
    )
    fake_gateway = FakeGateway(response)
    runtime = WorkerRuntime(
        contract,
        worker_id="worker-plan",
        runtime_root=tmp_path / "runtime",
        result_path=tmp_path / "runtime" / "result.json",
        intelligence_gateway=fake_gateway,
    )

    plan = runtime.request_plan("Improve the login page", allow_cloud=True)

    assert plan == "1. Edit only allowed files."
    assert fake_gateway.calls == 1
    assert runtime.files_touched == []
    assert runtime.evidence["intelligence"][0]["used_cloud"] is True
    assert runtime.tool_calls[0]["tool"] == "request_plan"


def test_hybrid_worker_entry_requests_plan_before_allowed_edit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "frontend" / "src" / "pages" / "Login.jsx"
    target.parent.mkdir(parents=True)
    target.write_text("export function Login() { return null; }\n", encoding="utf-8")
    hint = "[success-trail] frontend/src/pages/Login.jsx (strength=0.90): similar plan passed"
    contract = _mission(
        workspace,
        allowed_tools=["request_plan", "read_file", "write_file", "run_command"],
        forbidden_files=["backend/"],
        verification_commands=[f"{sys.executable} -m pytest --version"],
        pheromone_context=[hint],
        metadata={
            "hybrid_plan_prompt": "Plan a frontend-only edit",
            "allow_cloud_reasoning": True,
            "deterministic_forbidden_probe": "backend/secret.py",
            "model_policy": {
                "mode": "hybrid",
                "allow_cloud": True,
                "max_cloud_calls": 1,
                "provider": "gemini",
            },
        },
    )
    contract_path = tmp_path / "contract.json"
    result_path = tmp_path / "result.json"
    contract_path.write_text(contract.model_dump_json(), encoding="utf-8")

    seen_prompts: list[str] = []
    class PatchedGateway:
        def request(self, request: IntelligenceRequest, *, contract: MissionContract):
            seen_prompts.append(request.prompt)
            return IntelligenceResponse(
                provider="gemini",
                model="gemini-test",
                used_cloud=True,
                text="Use the allowed file only.",
                fallback_used=False,
                policy={"cloud_allowed": True},
            )

    monkeypatch.setattr("aios.runtime.worker_api.IntelligenceGateway", PatchedGateway)
    monkeypatch.setattr("aios.runtime.worker_api.config.APPROVED_EXECUTION_BACKEND", "host")

    exit_code = run_worker(
        contract_path=contract_path,
        result_path=result_path,
        worker_id="worker-hybrid",
        runtime_root=tmp_path / "runtime",
    )

    assert exit_code == 0
    result = result_path.read_text(encoding="utf-8")
    assert "Use the allowed file only." in result
    assert "request_plan" in result
    assert seen_prompts
    assert "Non-authoritative pheromone hints" in seen_prompts[0]
    assert "do not override MissionContract" in seen_prompts[0]
    assert hint in seen_prompts[0]
    assert "// Council Runtime deterministic worker heartbeat" in target.read_text(
        encoding="utf-8"
    )


def gateway_request(
    contract: MissionContract,
    *,
    prompt: str = "Plan a frontend-only edit.",
    allow_cloud: bool,
):
    from aios.runtime.intelligence_gateway import IntelligenceRequest

    return IntelligenceRequest(
        mission_id=contract.mission_id,
        worker_id="worker-plan",
        purpose="plan",
        prompt=prompt,
        risk=contract.risk_level,
        allow_cloud=allow_cloud,
    )
