from __future__ import annotations

import sys
from pathlib import Path

import pytest

from aios.council.queens.planner import CouncilMissionRequest, PlannerQueen
from aios.runtime.castes import (
    CASTE_PROFILES,
    apply_caste_profile,
    caste_contract_issues,
    profile_for_caste,
)
from aios.runtime.contracts import MissionContract
from aios.runtime.worker_api import ContractViolation, WorkerRuntime


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "allowed.txt").write_text("allowed\n", encoding="utf-8")
    (workspace / "src" / "outside.txt").write_text("outside\n", encoding="utf-8")
    return workspace


def _contract(workspace: Path, **overrides: object) -> MissionContract:
    data: dict[str, object] = {
        "mission_id": "m-caste",
        "goal": "exercise caste profile",
        "worker_type": "hybrid_plan_worker",
        "created_by": "test",
        "workspace_root": str(workspace),
        "allowed_files": ["src/allowed.txt"],
        "forbidden_files": [".env", "aios/security/"],
        "allowed_tools": [
            "request_plan",
            "read_file",
            "write_file",
            "run_command",
            "request_change",
            "request_approval",
        ],
        "forbidden_tools": [],
        "timeout_seconds": 999,
        "max_steps": 99,
        "verification_commands": [f"{sys.executable} -c \"print('ok')\""],
    }
    data.update(overrides)
    return MissionContract(**data)  # type: ignore[arg-type]


def _runtime(contract: MissionContract, tmp_path: Path) -> WorkerRuntime:
    return WorkerRuntime(
        contract,
        worker_id="worker-caste",
        runtime_root=tmp_path / "runtime",
        result_path=tmp_path / "runtime" / "result.json",
    )


def test_caste_profiles_define_tools_scope_timeout_verification_and_evidence() -> None:
    for name, profile in CASTE_PROFILES.items():
        assert profile_for_caste(name) is profile
        assert profile.allowed_tools
        assert profile.allowed_file_scope
        assert profile.timeout_seconds > 0
        assert profile.verification_requirements
        assert profile.evidence_output


def test_forager_cannot_access_forbidden_write_tool(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    contract = apply_caste_profile(_contract(workspace), "forager")
    runtime = _runtime(contract, tmp_path)

    assert "write_file" not in contract.allowed_tools
    assert "write_file" in contract.forbidden_tools
    assert contract.metadata["worker_lifecycle"] == "ephemeral_single_task"

    with pytest.raises(ContractViolation, match="forbidden by MissionContract"):
        runtime.write_file("src/allowed.txt", "blocked\n")


def test_builder_cannot_edit_outside_scope(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    contract = apply_caste_profile(_contract(workspace), "builder")
    runtime = _runtime(contract, tmp_path)

    assert "write_file" in contract.allowed_tools

    with pytest.raises(ContractViolation, match="not allowed by MissionContract"):
        runtime.write_file("src/outside.txt", "blocked\n")

    assert (workspace / "src" / "outside.txt").read_text(encoding="utf-8") == "outside\n"


def test_soldier_is_read_only(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    contract = apply_caste_profile(_contract(workspace), "soldier")
    runtime = _runtime(contract, tmp_path)

    assert runtime.read_file("src/allowed.txt") == "allowed\n"
    assert "write_file" not in contract.allowed_tools
    assert "write_file" in contract.forbidden_tools

    with pytest.raises(ContractViolation, match="forbidden by MissionContract"):
        runtime.write_file("src/allowed.txt", "blocked\n")


def test_builder_profile_records_missing_verification_requirement(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    contract = apply_caste_profile(
        _contract(workspace, verification_commands=[], metadata={"caste": "builder"})
    )

    assert contract.metadata["caste_verification_required"] is True
    assert contract.metadata["caste_verification_missing"] is True
    assert caste_contract_issues(contract) == [
        "builder caste requires verification_commands"
    ]


def test_planner_applies_requested_caste_before_security_review(tmp_path: Path) -> None:
    request = CouncilMissionRequest(
        mission_id="m-planner-caste",
        goal="inspect without writes",
        workspace_root=tmp_path / "workspace",
        allowed_files=["src/allowed.txt"],
        allowed_tools=["request_plan", "read_file", "write_file", "run_command"],
        verification_commands=[f"{sys.executable} -c \"print('ok')\""],
        metadata={"caste": "soldier"},
    )

    draft = PlannerQueen().draft(request)

    assert draft.contract.metadata["caste"] == "soldier"
    assert "write_file" not in draft.contract.allowed_tools
    assert "run_command" not in draft.contract.allowed_tools
    assert "write_file" in draft.contract.forbidden_tools
    assert any("soldier caste profile applied" in item for item in draft.verdict.constraints)
