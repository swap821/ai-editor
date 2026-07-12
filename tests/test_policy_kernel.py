"""Tests for the unified PolicyKernel authority facade."""
from __future__ import annotations

import pytest
from starlette.requests import Request

from aios import config
from aios.core.autonomy import AutonomyLedger
from aios.memory.db import get_connection
from aios.policy.kernel import PolicyKernel, _ROUTE_AUTHORITY
from aios.security.gateway import RateLimiter, Zone


@pytest.fixture
def kernel(tmp_path):
    """Fresh policy kernel with isolated autonomy ledger."""
    return PolicyKernel(
        rate_limiter=RateLimiter(max_per_session=100),
        autonomy_ledger=AutonomyLedger(db_path=tmp_path / "autonomy.db"),
    )


# --------------------------------------------------------------------------- #
# Route authority
# --------------------------------------------------------------------------- #

def test_route_authority_exact_match(kernel):
    authority = kernel.route_authority("/api/v1/execute")
    assert authority == _ROUTE_AUTHORITY["/api/v1/execute"]


def test_route_authority_templated_match(kernel):
    authority = kernel.route_authority("/api/v1/policy/abc123/vote")
    assert authority == _ROUTE_AUTHORITY["/api/v1/policy/{policy_id}/vote"]


def test_route_authority_fallback(kernel):
    authority = kernel.route_authority("/not/in/table")
    assert authority.authority_class == "GREEN"
    assert authority.rate_limit_per_minute == 120


# --------------------------------------------------------------------------- #
# Endpoint rate limiting
# --------------------------------------------------------------------------- #

def test_rate_limited_route_path_exact(kernel):
    assert kernel.rate_limited_route_path("/api/v1/execute") == "/api/v1/execute"


def test_rate_limited_route_path_templated(kernel):
    assert (
        kernel.rate_limited_route_path("/api/v1/policy/abc123/vote")
        == "/api/v1/policy/{policy_id}/vote"
    )


def test_rate_limited_route_path_unknown(kernel):
    assert kernel.rate_limited_route_path("/not/rate/limited") is None


def test_check_endpoint_rate_limit_allows_within_cap(kernel):
    path = "/api/v1/runtime/rollbacks/prune"
    for _ in range(5):
        kernel.check_endpoint_rate_limit(path, "127.0.0.1")


def test_check_endpoint_rate_limit_blocks_over_cap(kernel):
    path = "/api/v1/runtime/rollbacks/prune"
    cap = kernel.rate_limit_endpoints[path]
    for _ in range(cap):
        kernel.check_endpoint_rate_limit(path, "127.0.0.1")

    with pytest.raises(Exception) as exc_info:  # FastAPI HTTPException
        kernel.check_endpoint_rate_limit(path, "127.0.0.1")
    assert exc_info.value.status_code == 429


def test_check_endpoint_rate_limit_uses_per_ip_bucket(kernel):
    path = "/api/v1/runtime/rollbacks/prune"
    cap = kernel.rate_limit_endpoints[path]
    for _ in range(cap):
        kernel.check_endpoint_rate_limit(path, "1.1.1.1")
    # Different IP is not blocked by the first IP's bucket.
    kernel.check_endpoint_rate_limit(path, "2.2.2.2")


# --------------------------------------------------------------------------- #
# Action evaluation
# --------------------------------------------------------------------------- #

def test_evaluate_action_green(kernel):
    decision = kernel.evaluate_action("echo hello")
    assert decision.allowed
    assert decision.zone is Zone.GREEN


def test_evaluate_action_yellow_requires_approval(kernel):
    decision = kernel.evaluate_action("mkdir training_ground/test")
    assert decision.requires_approval
    assert decision.zone is Zone.YELLOW


def test_evaluate_action_red_blocked(kernel):
    decision = kernel.evaluate_action("rm -rf /")
    assert decision.blocked
    assert decision.zone is Zone.RED


def test_evaluate_action_oversized_blocked(kernel, monkeypatch):
    monkeypatch.setattr(config, "MAX_COMMAND_CHARS", 5)
    decision = kernel.evaluate_action("echo " + "x" * 100)
    assert decision.blocked
    assert "character limit" in decision.reason


# --------------------------------------------------------------------------- #
# Earned autonomy
# --------------------------------------------------------------------------- #

def _earn_signature(ledger: AutonomyLedger, command: str) -> None:
    """Seed an earned autonomy row for *command*."""
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


def test_evaluate_action_earned_autonomy_short_circuits_yellow(kernel, monkeypatch):
    monkeypatch.setattr(config, "EARNED_AUTONOMY_ENABLED", True)
    command = "mkdir training_ground/test_dir"
    _earn_signature(kernel.autonomy, command)

    decision = kernel.evaluate_action(command)
    assert decision.allowed
    assert decision.zone is Zone.YELLOW
    assert "earned" in decision.reason.lower()


# --------------------------------------------------------------------------- #
# Approved-path re-evaluation
# --------------------------------------------------------------------------- #

def test_evaluate_approved_red_still_blocked(kernel):
    decision = kernel.evaluate_approved("rm -rf /")
    assert decision.blocked
    assert decision.zone is Zone.RED


def test_evaluate_approved_green_allowed(kernel):
    decision = kernel.evaluate_approved("echo hello")
    assert decision.allowed
    assert decision.zone is Zone.GREEN


def test_evaluate_approved_oversized_blocked(kernel, monkeypatch):
    monkeypatch.setattr(config, "MAX_COMMAND_CHARS", 5)
    decision = kernel.evaluate_approved("echo " + "x" * 100)
    assert decision.blocked
    assert "character limit" in decision.reason


# --------------------------------------------------------------------------- #
# Request authority
# --------------------------------------------------------------------------- #

def _request(path: str, method: str = "GET") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
        }
    )


def test_request_authority_returns_summary(kernel, monkeypatch):
    monkeypatch.setattr(
        "aios.policy.kernel.edge_security.check_api_token_or_loopback",
        lambda _r: None,
    )
    monkeypatch.setattr(
        "aios.policy.kernel.edge_security.check_mutation_origin_or_token",
        lambda _r: None,
    )

    summary = kernel.request_authority(_request("/api/v1/execute"))
    assert summary["allowed"] is True
    assert summary["path"] == "/api/v1/execute"
    assert summary["authority"].authority_class == "YELLOW"


def test_request_authority_raises_when_edge_check_fails(kernel, monkeypatch):
    from starlette.responses import JSONResponse

    monkeypatch.setattr(
        "aios.policy.kernel.edge_security.check_api_token_or_loopback",
        lambda _r: JSONResponse({"detail": "unauthorised"}, status_code=401),
    )

    with pytest.raises(Exception) as exc_info:
        kernel.request_authority(_request("/api/v1/execute"))
    assert exc_info.value.status_code == 401


# --------------------------------------------------------------------------- #
# Feature flags and constitution
# --------------------------------------------------------------------------- #

def test_feature_enabled_reads_config(kernel, monkeypatch):
    monkeypatch.setattr(config, "EARNED_AUTONOMY_ENABLED", True)
    assert kernel.feature_enabled("earned_autonomy") is True
    monkeypatch.setattr(config, "EARNED_AUTONOMY_ENABLED", False)
    assert kernel.feature_enabled("earned_autonomy") is False


def test_constitution_snapshot(kernel):
    snapshot = kernel.constitution_snapshot()
    assert snapshot is kernel.constitution
