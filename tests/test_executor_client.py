"""Conformance tests for the control-plane private Executor client."""

from __future__ import annotations

import json
import urllib.error

import pytest

from aios.application.executor.service import (
    ExecutorService,
    IsolationUnavailable,
    StructuredCommandRunner,
    StructuredExecutorClient,
)
from aios.domain.executor import ExecutorCapability, ExecutorJob, ExecutorResult


class _Response:
    def __init__(self, payload: object, *, status: int = 200) -> None:
        self.status = status
        self._body = json.dumps(payload).encode("utf-8")

    def read(self, limit: int = -1) -> bytes:
        return self._body if limit < 0 else self._body[:limit]

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _job(job_id: str = "job-1") -> ExecutorJob:
    return ExecutorJob(
        job_id=job_id,
        mission_contract_digest="contract-1",
        capability=ExecutorCapability(
            capability_id="cap-1",
            action_digest="action-1",
            mission_contract_digest="contract-1",
            expires_at="2099-01-01T00:00:00+00:00",
        ),
        image="aios-executor:local",
        argv=("python", "-c", "print('ok')"),
        workspace_snapshot="/workspace/jobs/job-1",
    )


def _result(job_id: str = "job-1", **changes: object) -> dict[str, object]:
    result = ExecutorResult(
        job_id=job_id,
        status="completed",
        exit_code=0,
        stdout="ok\n",
        isolation_verified=True,
    ).model_dump(mode="json")
    result.update(changes)
    return result


def test_structured_client_submits_job_with_private_auth_and_validates_isolation() -> (
    None
):
    seen: dict[str, object] = {}

    def transport(request, timeout):
        seen["url"] = request.full_url
        seen["authorization"] = request.headers.get("Authorization")
        seen["timeout"] = timeout
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return _Response(_result())

    result = StructuredExecutorClient(
        base_url="http://executor:8081/",
        token="private-token",
        timeout_s=7,
        transport=transport,
    ).execute(_job())

    assert result.job_id == "job-1"
    assert result.isolation_verified is True
    assert seen == {
        "url": "http://executor:8081/v1/jobs",
        "authorization": "Bearer private-token",
        "timeout": 7,
        "body": _job().model_dump(mode="json"),
    }


def test_structured_client_propagates_the_current_trace_context() -> None:
    """Organ 52: the caller's trace context crosses the HTTP boundary into
    the isolated executor service as request headers -- correlation
    metadata only, never authority."""
    from aios.operations.tracing import bind_trace_context, new_trace_context

    seen: dict[str, object] = {}

    def transport(request, timeout):
        seen["request_id"] = request.get_header("X-request-id")
        seen["mission_id"] = request.get_header("X-mission-id")
        return _Response(_result())

    trace = new_trace_context(
        {"x-request-id": "req-trace-1", "x-mission-id": "mission-trace-1"}
    )
    with bind_trace_context(trace):
        StructuredExecutorClient(
            base_url="http://executor:8081",
            token="private-token",
            transport=transport,
        ).execute(_job())

    assert seen == {"request_id": "req-trace-1", "mission_id": "mission-trace-1"}


def test_structured_client_refuses_job_id_mismatch() -> None:
    client = StructuredExecutorClient(
        base_url="http://executor:8081",
        token="private-token",
        transport=lambda request, timeout: _Response(_result("other-job")),
    )

    with pytest.raises(IsolationUnavailable, match="mismatched job id"):
        client.execute(_job())


def test_structured_client_refuses_malformed_or_unproven_results() -> None:
    for payload, message in (
        ({"job_id": "job-1", "status": "completed"}, "isolation"),
        (_result(isolation_verified=False), "isolation"),
        (_result(status="timeout"), "timeout"),
        (_result(status="unavailable"), "unavailable"),
    ):
        client = StructuredExecutorClient(
            base_url="http://executor:8081",
            token="private-token",
            transport=lambda request, timeout, payload=payload: _Response(payload),
        )
        with pytest.raises(IsolationUnavailable, match=message):
            client.execute(_job())


def test_structured_client_refuses_timeout_and_http_failure() -> None:
    timeout_client = StructuredExecutorClient(
        base_url="http://executor:8081",
        token="private-token",
        transport=lambda request, timeout: (_ for _ in ()).throw(TimeoutError()),
    )
    with pytest.raises(IsolationUnavailable, match="timed out"):
        timeout_client.execute(_job())

    unavailable_client = StructuredExecutorClient(
        base_url="http://executor:8081",
        token="private-token",
        transport=lambda request, timeout: (_ for _ in ()).throw(
            urllib.error.URLError("connection refused")
        ),
    )
    with pytest.raises(IsolationUnavailable, match="unavailable"):
        unavailable_client.execute(_job())


def test_structured_client_refuses_missing_private_configuration() -> None:
    client = StructuredExecutorClient(base_url="", token="")
    with pytest.raises(IsolationUnavailable, match="not configured"):
        client.execute(_job())


def test_production_executor_service_requires_private_client() -> None:
    with pytest.raises(IsolationUnavailable, match="private executor service"):
        ExecutorService(profile="production").execute(_job())


def test_structured_command_runner_builds_a_staged_job_without_host_fallback(
    tmp_path,
) -> None:
    root = tmp_path / "staged"
    workspace = root / "mission-1"
    workspace.mkdir(parents=True)
    seen: list[ExecutorJob] = []

    class _Client:
        def execute(self, job: ExecutorJob) -> ExecutorResult:
            seen.append(job)
            return ExecutorResult(
                job_id=job.job_id,
                status="completed",
                exit_code=0,
                stdout="ok\n",
                isolation_verified=True,
            )

    stdout, stderr, code = StructuredCommandRunner(
        _Client(),
        local_workspace_root=root,
        remote_workspace_root="/workspace/jobs",
    )("echo ok", cwd=str(workspace), env={"SAFE": "1"}, timeout_s=3)

    assert (stdout, stderr, code) == ("ok\n", "", 0)
    assert seen[0].argv == ("echo", "ok")
    assert seen[0].workspace_snapshot == "/workspace/jobs/mission-1"
    assert seen[0].network_policy.mode == "none"
    assert seen[0].environment == {"SAFE": "1"}


def test_structured_command_runner_refuses_unstaged_project_path(tmp_path) -> None:
    calls: list[ExecutorJob] = []

    class _Client:
        def execute(self, job: ExecutorJob) -> ExecutorResult:
            calls.append(job)
            raise AssertionError("unstaged command must not reach the service")

    runner = StructuredCommandRunner(
        _Client(),
        local_workspace_root=tmp_path / "staged",
    )
    with pytest.raises(IsolationUnavailable, match="staged workspace"):
        runner("echo ok", cwd=str(tmp_path), env={}, timeout_s=3)
    assert calls == []


def test_core_executor_uses_private_runner_in_production(monkeypatch) -> None:
    monkeypatch.setenv("AIOS_PROFILE", "production")
    from aios.core.executor import Executor, approved_runner_from_config

    runner = approved_runner_from_config()
    assert getattr(runner, "is_private_service", False) is True
    executor = Executor()
    assert getattr(executor.runner, "is_private_service", False) is True
    assert getattr(executor.approved_runner, "is_private_service", False) is True


def test_api_executor_dependency_has_no_local_runner_in_production(monkeypatch) -> None:
    monkeypatch.setenv("AIOS_PROFILE", "production")
    from aios.api import deps
    from aios import config

    monkeypatch.setattr(config, "EXECUTOR_TOKEN", "private-token")
    executor = deps.get_executor()

    assert getattr(executor.runner, "is_private_service", False) is True
    assert getattr(executor.approved_runner, "is_private_service", False) is True
