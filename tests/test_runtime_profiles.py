"""Tests for runtime profile loading, storage, and kernel integration."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from aios import config
from aios.policy.kernel import PolicyKernel
from aios.runtime import profiles
from aios.security.gateway import RateLimiter


@pytest.fixture
def isolated_profiles(monkeypatch, tmp_path):
    """Use a temporary runtime-profiles directory and a fresh registry cache."""
    monkeypatch.setattr(profiles, "RUNTIME_PROFILES_DIR", tmp_path / "runtime_profiles")
    monkeypatch.setattr(profiles, "ACTIVE_PROFILE_PATH", tmp_path / "runtime_profiles" / "active.json")
    # Ensure the module-level directory creation uses the new path.
    profiles.RUNTIME_PROFILES_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def kernel(tmp_path, monkeypatch):
    """Fresh policy kernel with isolated autonomy ledger and profile cache."""
    k = PolicyKernel(
        rate_limiter=RateLimiter(max_per_session=100),
        autonomy_ledger=None,
    )
    monkeypatch.setattr(k, "_active_profile", None)
    return k


# --------------------------------------------------------------------------- #
# Built-in registry
# --------------------------------------------------------------------------- #

def test_builtin_profiles_loaded():
    assert "local-first" in profiles.RUNTIME_PROFILES
    assert "operator" in profiles.RUNTIME_PROFILES
    assert "autonomous" in profiles.RUNTIME_PROFILES
    assert "air-gapped" in profiles.RUNTIME_PROFILES


def test_get_profile_case_insensitive():
    assert profiles.get_profile("Operator") is profiles.RUNTIME_PROFILES["operator"]
    assert profiles.get_profile("UNKNOWN") is None


def test_local_first_profile_values():
    profile = profiles.RUNTIME_PROFILES["local-first"]
    assert profile.execution_backend == "host"
    assert profile.earned_autonomy is False
    assert profile.router_cloud_tasks == ()
    assert profile.offline_mode is False
    assert profile.swarm_cloud_burst is False


def test_operator_profile_values():
    profile = profiles.RUNTIME_PROFILES["operator"]
    assert profile.execution_backend == "container"
    assert profile.earned_autonomy is True
    assert profile.router_cloud_tasks == ("reasoning", "coding")
    assert profile.router_prefer_local is True


def test_autonomous_profile_allows_more_cloud_tasks():
    profile = profiles.RUNTIME_PROFILES["autonomous"]
    assert profile.router_cloud_tasks == ("reasoning", "coding", "browse", "swarm")
    assert profile.router_prefer_local is False
    assert profile.swarm_cloud_burst is True


def test_air_gapped_profile_is_most_restrictive():
    profile = profiles.RUNTIME_PROFILES["air-gapped"]
    assert profile.execution_backend == "host"
    assert profile.earned_autonomy is False
    assert profile.router_cloud_tasks == ()
    assert profile.offline_mode is True
    assert profile.router_max_cost == "low"


def test_cloud_task_allowed():
    profile = profiles.RUNTIME_PROFILES["operator"]
    assert profile.cloud_task_allowed("coding") is True
    assert profile.cloud_task_allowed("CODING") is True
    assert profile.cloud_task_allowed("browse") is False


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #

def test_save_and_load_active_profile_roundtrip(isolated_profiles, tmp_path):
    profile = profiles.RUNTIME_PROFILES["operator"]
    profiles.save_active_profile(profile)

    assert profiles.load_active_profile_name() == "operator"

    payload = json.loads(profiles.ACTIVE_PROFILE_PATH.read_text(encoding="utf-8"))
    assert payload["name"] == "operator"
    assert payload["profile"]["name"] == "operator"


def test_load_active_profile_name_missing(isolated_profiles):
    assert profiles.load_active_profile_name() is None


def test_load_active_profile_name_invalid_json(isolated_profiles):
    profiles.ACTIVE_PROFILE_PATH.write_text("not json", encoding="utf-8")
    assert profiles.load_active_profile_name() is None


# --------------------------------------------------------------------------- #
# PolicyKernel integration
# --------------------------------------------------------------------------- #

def test_kernel_defaults_to_local_first(kernel, monkeypatch, isolated_profiles):
    monkeypatch.delenv("AIOS_RUNTIME_PROFILE", raising=False)
    assert kernel.active_runtime_profile().name == "local-first"


def test_kernel_respects_runtime_profile_env(kernel, monkeypatch, isolated_profiles):
    monkeypatch.setenv("AIOS_RUNTIME_PROFILE", "operator")
    assert kernel.active_runtime_profile().name == "operator"


def test_kernel_falls_back_for_unknown_profile_name(kernel, monkeypatch, isolated_profiles):
    monkeypatch.setenv("AIOS_RUNTIME_PROFILE", "does-not-exist")
    profile = kernel.active_runtime_profile()
    assert profile.name == profiles.default_profile_name()


def test_kernel_prefers_persisted_over_env(kernel, monkeypatch, isolated_profiles):
    monkeypatch.setenv("AIOS_RUNTIME_PROFILE", "operator")
    profiles.save_active_profile(profiles.RUNTIME_PROFILES["air-gapped"])
    assert kernel.active_runtime_profile().name == "air-gapped"


def test_kernel_cloud_tasks_allowed(kernel, monkeypatch, isolated_profiles):
    monkeypatch.setenv("AIOS_RUNTIME_PROFILE", "operator")
    assert kernel.cloud_tasks_allowed("coding") is True
    assert kernel.cloud_tasks_allowed("browse") is False


def test_kernel_earned_autonomy_enabled(kernel, monkeypatch, isolated_profiles):
    monkeypatch.setenv("AIOS_RUNTIME_PROFILE", "operator")
    assert kernel.earned_autonomy_enabled() is True

    monkeypatch.setenv("AIOS_RUNTIME_PROFILE", "local-first")
    monkeypatch.setattr(kernel, "_active_profile", None)
    assert kernel.earned_autonomy_enabled() is False


def test_kernel_execution_backend(kernel, monkeypatch, isolated_profiles):
    monkeypatch.setenv("AIOS_RUNTIME_PROFILE", "autonomous")
    assert kernel.execution_backend() == "container"


def test_kernel_offline_mode(kernel, monkeypatch, isolated_profiles):
    monkeypatch.setenv("AIOS_RUNTIME_PROFILE", "air-gapped")
    assert kernel.offline_mode() is True


def test_kernel_router_policy(kernel, monkeypatch, isolated_profiles):
    monkeypatch.setenv("AIOS_RUNTIME_PROFILE", "operator")
    policy = kernel.router_policy()
    assert policy.cloud_tasks == frozenset({"reasoning", "coding"})
    assert policy.prefer_local is True


def test_kernel_runtime_profile_decisions(kernel, monkeypatch, isolated_profiles):
    monkeypatch.setenv("AIOS_RUNTIME_PROFILE", "operator")
    decisions = kernel.runtime_profile_decisions()
    assert decisions["name"] == "operator"
    assert decisions["cloud_tasks_allowed"]["coding"] is True
    assert decisions["cloud_tasks_allowed"]["browse"] is False


def test_kernel_load_runtime_profile_unknown(kernel):
    with pytest.raises(ValueError, match="Unknown runtime profile"):
        kernel.load_runtime_profile("missing")


def test_kernel_save_runtime_profile(kernel, isolated_profiles):
    profile = profiles.RUNTIME_PROFILES["autonomous"]
    kernel.save_runtime_profile(profile)
    assert kernel.active_runtime_profile().name == "autonomous"
    assert profiles.load_active_profile_name() == "autonomous"


def test_kernel_list_runtime_profiles(kernel):
    names = kernel.list_runtime_profiles()
    assert sorted(names) == ["air-gapped", "autonomous", "local-first", "operator"]


# --------------------------------------------------------------------------- #
# Runtime profile overrides env-driven config expectations
# --------------------------------------------------------------------------- #

def test_operator_profile_matches_default_config_cloud_tasks():
    """The operator profile mirrors the shipped default cloud-task eligibility."""
    profile = profiles.RUNTIME_PROFILES["operator"]
    assert set(profile.router_cloud_tasks) == set(config.ROUTER_CLOUD_TASKS)


# --------------------------------------------------------------------------- #
# Integration: decisions reach the router and executor authority surface
# --------------------------------------------------------------------------- #

def test_router_wiring_uses_kernel_policy(monkeypatch, isolated_profiles):
    from aios.core.router_wiring import _router_policy
    from aios.policy import kernel as kernel_module

    monkeypatch.setenv("AIOS_RUNTIME_PROFILE", "operator")
    # Force a fresh kernel by clearing the module-level singleton.
    monkeypatch.setattr(kernel_module, "_KERNEL", None)

    policy = _router_policy()
    assert policy.cloud_tasks == frozenset({"reasoning", "coding"})
    assert policy.prefer_local is True


def _seed_earned_command(ledger, command: str) -> None:
    """Insert an earned row for *command* directly into the autonomy ledger."""
    from aios.memory.db import get_connection

    sig = ledger.signature("command", command)
    norm = ledger._normalize("command", command)
    with get_connection(ledger.db_path) as conn:
        conn.execute(
            "INSERT INTO earned_autonomy "
            "(signature, action_type, target_shape, success_count, failure_count, "
            "streak, status, earned_at, last_outcome_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sig, "command", norm, 10, 0, 10, "earned", "now", "now", "now"),
        )


def test_executor_authority_uses_kernel_for_earned_autonomy(kernel, monkeypatch, isolated_profiles, tmp_path):
    from aios.core.autonomy import AutonomyLedger
    from aios.core.executor import Executor

    ledger = AutonomyLedger(db_path=tmp_path / "autonomy.db")
    kernel.autonomy = ledger
    monkeypatch.setenv("AIOS_RUNTIME_PROFILE", "operator")
    monkeypatch.setattr(kernel, "_active_profile", None)

    command = "mkdir -p training_ground/test_dir"
    _seed_earned_command(ledger, command)

    executor = Executor(approved_runner=None, policy_kernel=kernel)
    result = executor.execute(command)
    assert result.status == "OK"


def test_executor_authority_respects_profile_without_autonomy(kernel, monkeypatch, isolated_profiles, tmp_path):
    from aios.core.autonomy import AutonomyLedger
    from aios.core.executor import Executor

    ledger = AutonomyLedger(db_path=tmp_path / "autonomy.db")
    kernel.autonomy = ledger
    monkeypatch.setenv("AIOS_RUNTIME_PROFILE", "local-first")
    monkeypatch.setattr(kernel, "_active_profile", None)

    command = "mkdir training_ground/test_dir"
    _seed_earned_command(ledger, command)

    executor = Executor(approved_runner=None, policy_kernel=kernel)
    result = executor.execute(command)
    assert result.status == "REQUIRE_APPROVAL"
