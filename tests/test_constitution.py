from __future__ import annotations

from pathlib import Path

from aios import config
from aios.policy.constitution import build_constitution
from aios.policy.constitution_enforcer import ConstitutionEnforcer
from aios.runtime.budget_guard import BudgetGuard
from aios.runtime.contracts import MissionContract


def _contract(tmp_path: Path, **overrides: object) -> MissionContract:
    data: dict[str, object] = {
        "mission_id": "m-constitution",
        "goal": "exercise constitution facade",
        "worker_type": "builder",
        "created_by": "test",
        "workspace_root": str(tmp_path),
        "allowed_files": ["src/allowed.py"],
        "allowed_tools": [
            "request_plan",
            "read_file",
            "write_file",
            "run_command",
            "request_change",
        ],
        "verification_commands": ["python -m pytest tests/test_constitution.py -q"],
        "metadata": {
            "model_policy": {
                "mode": "hybrid",
                "allow_cloud": True,
                "max_cloud_calls": 2,
                "max_tokens_per_request": 2000,
                "max_tokens_total": 4000,
            }
        },
    }
    data.update(overrides)
    return MissionContract(**data)  # type: ignore[arg-type]


def test_constitution_reflects_live_config_and_caste_profiles() -> None:
    constitution = build_constitution()

    assert constitution.router_cloud_tasks == config.ROUTER_CLOUD_TASKS
    assert constitution.router_max_cost == config.ROUTER_MAX_COST
    assert constitution.resource_mode == config.RESOURCE_MODE
    assert constitution.earned_autonomy_enabled is config.EARNED_AUTONOMY_ENABLED
    assert "aios/security/" in constitution.frozen_path_prefixes
    assert "builder" in constitution.castes
    assert constitution.castes["builder"].verification_required is True
    assert "write_file" not in constitution.castes["soldier"].allowed_tools


def test_enforcer_blocks_frozen_core_file_edits(tmp_path: Path) -> None:
    enforcer = ConstitutionEnforcer()

    blocked = enforcer.check_file_edit(r"aios\security\gateway.py", actor="builder")

    assert blocked.allowed is False
    assert blocked.risk == "RED"
    assert "frozen" in blocked.reason
    assert blocked.source == "constitution"


def test_enforcer_cannot_override_red_gateway_decisions() -> None:
    enforcer = ConstitutionEnforcer()

    decision = enforcer.check_command('python -c "print(1)"')

    assert decision.allowed is False
    assert decision.risk == "RED"
    assert decision.source == "security_gateway"
    assert "BLOCK" in decision.reason


def test_cloud_request_follows_router_policy_and_resource_budget(tmp_path: Path) -> None:
    contract = _contract(tmp_path)
    constitution = build_constitution(router_cloud_tasks=("reasoning",))

    normal = ConstitutionEnforcer(
        constitution=constitution,
        budget_guard=BudgetGuard(mode="normal"),
    )
    allowed = normal.check_cloud_request(
        contract,
        task="reasoning",
        estimated_tokens=100,
        estimated_cost=0.01,
    )
    blocked_by_router = normal.check_cloud_request(
        contract,
        task="general",
        estimated_tokens=100,
        estimated_cost=0.01,
    )
    blocked_by_budget = ConstitutionEnforcer(
        constitution=constitution,
        budget_guard=BudgetGuard(mode="conservation"),
    ).check_cloud_request(
        contract,
        task="reasoning",
        estimated_tokens=100,
        estimated_cost=0.01,
    )

    assert allowed.allowed is True
    assert allowed.risk == "YELLOW"
    assert blocked_by_router.allowed is False
    assert "router policy" in blocked_by_router.reason
    assert blocked_by_budget.allowed is False
    assert "conservation blocks cloud" in blocked_by_budget.reason


def test_caste_spawn_reflects_existing_profiles(tmp_path: Path) -> None:
    enforcer = ConstitutionEnforcer()
    builder_without_verification = _contract(
        tmp_path,
        verification_commands=[],
        metadata={"caste": "builder"},
    )
    soldier_with_write = _contract(
        tmp_path,
        worker_type="soldier",
        allowed_tools=["request_plan", "read_file", "write_file"],
        metadata={"caste": "soldier"},
    )
    builder_with_verification = _contract(tmp_path, metadata={"caste": "builder"})

    builder_blocked = enforcer.check_caste_spawn(builder_without_verification)
    soldier_blocked = enforcer.check_caste_spawn(soldier_with_write)
    builder_allowed = enforcer.check_caste_spawn(builder_with_verification)

    assert builder_blocked.allowed is False
    assert "requires verification_commands" in builder_blocked.reason
    assert soldier_blocked.allowed is False
    assert "tools exceed soldier caste" in soldier_blocked.reason
    assert builder_allowed.allowed is True
    assert builder_allowed.requires_human is True
