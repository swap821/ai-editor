from __future__ import annotations

import subprocess

from fastapi.testclient import TestClient

from aios.domain.executor import ExecutorCapability, ExecutorJob
from aios.executor_service import app
from aios.infrastructure.executor.docker_runner import DockerJobRunner


def _job(workspace: str = "/tmp/not-a-staged-workspace") -> dict:
    return ExecutorJob(
        job_id="job-1",
        mission_contract_digest="contract-1",
        capability=ExecutorCapability(
            capability_id="cap-1",
            action_digest="action-1",
            mission_contract_digest="contract-1",
            expires_at="2099-01-01T00:00:00+00:00",
        ),
        image="aios-executor:local",
        argv=("python", "-c", "print('ok')"),
        workspace_snapshot=workspace,
    ).model_dump(mode="json")


def test_executor_health_does_not_expose_credentials(monkeypatch) -> None:
    monkeypatch.setenv("AIOS_EXECUTOR_TOKEN", "private-token")
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "executor",
        "runtime": "docker",
        "token_configured": True,
    }
    assert "private-token" not in response.text


def test_executor_job_requires_private_authentication(monkeypatch) -> None:
    monkeypatch.setenv("AIOS_EXECUTOR_TOKEN", "private-token")
    response = TestClient(app).post(
        "/v1/jobs", json=_job(), headers={"Authorization": "Bearer wrong"}
    )
    assert response.status_code == 401


def test_executor_rejects_workspace_escape_before_runtime(monkeypatch) -> None:
    monkeypatch.setenv("AIOS_EXECUTOR_TOKEN", "private-token")
    response = TestClient(app).post(
        "/v1/jobs",
        json=_job(),
        headers={"Authorization": "Bearer private-token"},
    )
    assert response.status_code == 403
    assert "outside executor staging root" in response.text


def test_docker_job_runner_rejects_workspace_outside_staging_root(
    monkeypatch, tmp_path
) -> None:
    staging_root = tmp_path / "jobs"
    staging_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("AIOS_EXECUTOR_WORKSPACE_ROOT", str(staging_root))
    calls: list[dict[str, object]] = []

    def fake_runner(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return "ok", "", 0

    result = DockerJobRunner(runner=fake_runner)(
        ExecutorJob.model_validate(_job(str(outside)))
    )

    assert result.status == "failed"
    assert "outside executor staging root" in result.reason
    assert calls == []


def test_docker_job_runner_passes_only_a_validated_workspace(
    monkeypatch, tmp_path
) -> None:
    staging_root = tmp_path / "jobs"
    workspace = staging_root / "job-1"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("AIOS_EXECUTOR_WORKSPACE_ROOT", str(staging_root))
    monkeypatch.setenv("AIOS_EXECUTOR_DAEMON_WORKSPACE_ROOT", str(staging_root))
    calls: list[dict[str, object]] = []

    def fake_runner(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return "ok", "", 0

    result = DockerJobRunner(runner=fake_runner)(
        ExecutorJob.model_validate(_job(str(workspace)))
    )

    assert result.status == "completed"
    assert calls[0]["cwd"] == str(workspace.resolve())


def test_docker_job_runner_maps_container_workspace_to_daemon_root(
    monkeypatch, tmp_path
) -> None:
    staging_root = tmp_path / "jobs"
    workspace = staging_root / "job-1"
    workspace.mkdir(parents=True)
    daemon_root = tmp_path / "daemon-visible-jobs"
    daemon_root.mkdir()
    monkeypatch.setenv("AIOS_EXECUTOR_WORKSPACE_ROOT", str(staging_root))
    monkeypatch.setenv("AIOS_EXECUTOR_DAEMON_WORKSPACE_ROOT", str(daemon_root))
    calls: list[dict[str, object]] = []

    def fake_runner(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return "ok", "", 0

    result = DockerJobRunner(runner=fake_runner)(
        ExecutorJob.model_validate(_job(str(workspace)))
    )

    assert result.status == "completed"
    assert calls[0]["cwd"] == str(daemon_root / "job-1")


def test_executor_service_binds_the_incoming_trace_context_for_the_job(
    monkeypatch, tmp_path
) -> None:
    """Organ 52: a real request-scoped trace id (propagated by
    StructuredExecutorClient) is bound for the duration of job dispatch, so
    aios.core.executor.DockerRunner's own get_trace_context() read sees the
    caller's real ids, not a fresh unrelated one."""
    from aios.operations.tracing import get_trace_context

    staging_root = tmp_path / "jobs"
    workspace = staging_root / "job-1"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("AIOS_EXECUTOR_TOKEN", "private-token")
    monkeypatch.setenv("AIOS_EXECUTOR_WORKSPACE_ROOT", str(staging_root))
    monkeypatch.setenv("AIOS_EXECUTOR_DAEMON_WORKSPACE_ROOT", str(staging_root))

    seen: dict[str, object] = {}

    def fake_runner(command, **kwargs):
        seen["mission_id"] = get_trace_context().mission_id
        seen["request_id"] = get_trace_context().request_id
        return "ok", "", 0

    monkeypatch.setattr(
        "aios.executor_service.DockerJobRunner",
        lambda: DockerJobRunner(runner=fake_runner),
    )

    response = TestClient(app).post(
        "/v1/jobs",
        json=_job(str(workspace)),
        headers={
            "Authorization": "Bearer private-token",
            "X-Request-Id": "req-from-caller",
            "X-Mission-Id": "mission-from-caller",
        },
    )

    assert response.status_code == 200
    assert seen == {
        "mission_id": "mission-from-caller",
        "request_id": "req-from-caller",
    }


def test_docker_job_runner_reports_timeout_as_timeout(monkeypatch, tmp_path) -> None:
    staging_root = tmp_path / "jobs"
    workspace = staging_root / "job-1"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("AIOS_EXECUTOR_WORKSPACE_ROOT", str(staging_root))
    monkeypatch.setenv("AIOS_EXECUTOR_DAEMON_WORKSPACE_ROOT", str(staging_root))

    def timeout_runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout_s"])

    result = DockerJobRunner(runner=timeout_runner)(
        ExecutorJob.model_validate(_job(str(workspace)))
    )

    assert result.status == "timeout"
    assert result.isolation_verified is False
