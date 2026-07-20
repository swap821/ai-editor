"""Fail-closed application gateway to an isolated executor service."""

from __future__ import annotations

import hashlib
import json
import math
import socket
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Protocol

from aios import config
from aios.domain.executor import ExecutorJob, ExecutorResult
from aios.domain.executor import ExecutorCapability, ResourceLimits
from aios.infrastructure.executor.argv import parse_argv
from aios.infrastructure.executor.workspace import resolve_staged_workspace


class IsolationUnavailable(RuntimeError):
    """Raised when the required isolation boundary cannot be used."""


class JobRunner(Protocol):
    def __call__(self, job: ExecutorJob) -> ExecutorResult: ...


class StructuredExecutorClient:
    """Authenticated control-plane client for the private executor service.

    This is deliberately a structured transport boundary: callers submit an
    :class:`ExecutorJob`, never a shell command, and every response must prove
    that it belongs to the submitted job and came from an isolated backend.
    Transport failure, malformed data, timeouts, and an unproven response are
    all refusals.  There is no host-runner fallback in this class.
    """

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_s: float = 30.0,
        transport: Callable[..., Any] | None = None,
        max_response_bytes: int = 8 * 1024 * 1024,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        timeout_value = max(float(timeout_s), 0.001)
        # Preserve integral caller values for deterministic transports/tests while
        # retaining sub-second precision when a fractional timeout is requested.
        self.timeout_s = (
            int(timeout_value) if timeout_value.is_integer() else timeout_value
        )
        self.transport = transport or urllib.request.urlopen
        self.max_response_bytes = max(int(max_response_bytes), 1024)

    def execute(self, job: ExecutorJob) -> ExecutorResult:
        if not self.base_url or not self.token:
            raise IsolationUnavailable("private executor service is not configured")
        payload = json.dumps(
            job.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/v1/jobs",
            data=payload,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self.transport(request, timeout=self.timeout_s) as response:
                status = int(getattr(response, "status", 200))
                raw = response.read(self.max_response_bytes + 1)
        except (TimeoutError, socket.timeout) as exc:
            raise IsolationUnavailable("private executor request timed out") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise IsolationUnavailable(
                f"private executor service unavailable: {exc}"
            ) from exc
        if len(raw) > self.max_response_bytes:
            raise IsolationUnavailable("private executor response exceeded its bound")
        if status < 200 or status >= 300:
            raise IsolationUnavailable(f"private executor returned HTTP {status}")
        try:
            decoded = json.loads(raw.decode("utf-8"))
            result = ExecutorResult.model_validate(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise IsolationUnavailable(
                "private executor returned malformed JSON"
            ) from exc
        if result.job_id != job.job_id:
            raise IsolationUnavailable("private executor returned a mismatched job id")
        if result.status in {"timeout", "unavailable"}:
            raise IsolationUnavailable(f"private executor refused job: {result.status}")
        if not result.isolation_verified:
            raise IsolationUnavailable("private executor did not prove isolation")
        return result

    def __call__(self, job: ExecutorJob) -> ExecutorResult:
        return self.execute(job)

    def health(self) -> dict[str, Any]:
        """Return a truthful authenticated health response from the service."""
        if not self.base_url or not self.token:
            raise IsolationUnavailable("private executor service is not configured")
        request = urllib.request.Request(
            f"{self.base_url}/health",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
            method="GET",
        )
        try:
            with self.transport(request, timeout=self.timeout_s) as response:
                status = int(getattr(response, "status", 200))
                raw = response.read(self.max_response_bytes + 1)
        except (TimeoutError, socket.timeout) as exc:
            raise IsolationUnavailable(
                "private executor health request timed out"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise IsolationUnavailable(
                f"private executor service unavailable: {exc}"
            ) from exc
        if len(raw) > self.max_response_bytes or status < 200 or status >= 300:
            raise IsolationUnavailable("private executor health response is invalid")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IsolationUnavailable(
                "private executor health response is malformed"
            ) from exc
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            raise IsolationUnavailable("private executor health check failed")
        if payload.get("token_configured") is not True:
            raise IsolationUnavailable("private executor token is not configured")
        return payload


class StructuredCommandRunner:
    """Adapt a staged, shell-free command to :class:`StructuredExecutorClient`.

    The adapter intentionally accepts only a workspace already under the
    control-plane staging root.  It never mounts the project root directly and
    never delegates to the legacy host runner.  R9 owns creating/retaining
    those stages; until then an absent stage is a truthful refusal.
    """

    is_private_service = True

    def __init__(
        self,
        client: StructuredExecutorClient,
        *,
        local_workspace_root: str | Path,
        remote_workspace_root: str = "/workspace/jobs",
        image: str = config.CONTAINER_IMAGE,
    ) -> None:
        self.client = client
        self.local_workspace_root = Path(local_workspace_root)
        self.remote_workspace_root = PurePosixPath(remote_workspace_root)
        self.image = image

    def __call__(
        self,
        command: str,
        *,
        cwd: str,
        env: dict[str, str],
        timeout_s: int,
    ) -> tuple[str, str, int]:
        argv = tuple(parse_argv(command))
        local_root = self.local_workspace_root.resolve()
        try:
            workspace = resolve_staged_workspace(cwd, local_root)
        except (OSError, ValueError) as exc:
            raise IsolationUnavailable(
                "private executor requires a staged workspace"
            ) from exc
        relative = workspace.relative_to(local_root)
        remote_workspace = self.remote_workspace_root.joinpath(*relative.parts)
        job_id = f"job-{uuid.uuid4().hex}"
        contract_material = {
            "argv": list(argv),
            "workspace": str(remote_workspace),
            "environment_names": sorted(env),
            "image": self.image,
        }
        contract_digest = hashlib.sha256(
            json.dumps(contract_material, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        action_digest = hashlib.sha256(
            json.dumps(
                {**contract_material, "job_id": job_id},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        expires_at = (
            (datetime.now(timezone.utc) + timedelta(seconds=max(int(timeout_s), 1) + 5))
            .replace(microsecond=0)
            .isoformat()
        )
        job = ExecutorJob(
            job_id=job_id,
            mission_contract_digest=contract_digest,
            capability=ExecutorCapability(
                capability_id=f"executor-capability:{job_id}",
                action_digest=action_digest,
                mission_contract_digest=contract_digest,
                expires_at=expires_at,
            ),
            image=self.image,
            argv=argv,
            workspace_snapshot=str(remote_workspace),
            environment_allowlist=tuple(sorted(env)),
            environment=dict(env),
            resource_limits=ResourceLimits(
                timeout_seconds=max(int(math.ceil(timeout_s)), 1),
                max_output_bytes=config.MAX_COMMAND_OUTPUT_BYTES,
                memory_budget_mb=config.CONTAINER_MEMORY_MB,
                cpu_budget=config.CONTAINER_CPUS,
                pids_limit=config.CONTAINER_PIDS_LIMIT,
            ),
            verification_expectation={
                "executor_policy": "private_service",
                "workspace_root": str(self.remote_workspace_root),
            },
        )
        result = self.client.execute(job)
        return (
            result.stdout,
            result.stderr,
            result.exit_code if result.exit_code is not None else 1,
        )


def private_executor_runner_from_config() -> StructuredCommandRunner:
    """Build the production-only private-service command runner."""
    client = StructuredExecutorClient(
        base_url=config.EXECUTOR_URL,
        token=config.EXECUTOR_TOKEN,
        timeout_s=config.EXECUTOR_HTTP_TIMEOUT_S,
    )
    return StructuredCommandRunner(
        client,
        local_workspace_root=config.EXECUTOR_WORKSPACE_ROOT,
        remote_workspace_root=config.EXECUTOR_REMOTE_WORKSPACE_ROOT,
        image=config.CONTAINER_IMAGE,
    )


class ExecutorService:
    """Dispatch structured jobs to one configured execution backend.

    The control plane owns this client boundary but never the container
    runtime socket. A missing or disallowed backend is a refusal, never a host
    fallback.
    """

    def __init__(
        self,
        *,
        profile: str,
        runner: JobRunner | None = None,
        client: StructuredExecutorClient | None = None,
        backend_name: str = "private_service",
        require_isolation: bool = True,
    ) -> None:
        self.profile = profile
        self.runner = runner
        self.client = client
        self.backend_name = backend_name
        self.require_isolation = require_isolation

    def build_command_job(
        self,
        *,
        mission_contract_digest: str,
        command: str,
        workspace_snapshot: str,
        timeout_seconds: int,
        job_id: str | None = None,
    ) -> ExecutorJob:
        """Build one shell-free, staged-workspace job for this executor boundary."""
        argv = tuple(parse_argv(command))
        if not argv:
            raise ValueError("executor command cannot be empty")
        actual_job_id = job_id or f"executor-job-{uuid.uuid4().hex}"
        material = {
            "argv": list(argv),
            "workspace_snapshot": workspace_snapshot,
            "mission_contract_digest": mission_contract_digest,
        }
        action_digest = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        expires_at = (
            (
                datetime.now(timezone.utc)
                + timedelta(seconds=max(int(timeout_seconds), 1) + 5)
            )
            .replace(microsecond=0)
            .isoformat()
        )
        return ExecutorJob(
            job_id=actual_job_id,
            mission_contract_digest=mission_contract_digest,
            capability=ExecutorCapability(
                capability_id=f"executor-capability:{actual_job_id}",
                action_digest=action_digest,
                mission_contract_digest=mission_contract_digest,
                expires_at=expires_at,
            ),
            image=config.CONTAINER_IMAGE,
            argv=argv,
            workspace_snapshot=workspace_snapshot,
            resource_limits=ResourceLimits(
                timeout_seconds=max(int(timeout_seconds), 1),
                max_output_bytes=config.MAX_COMMAND_OUTPUT_BYTES,
                memory_budget_mb=config.CONTAINER_MEMORY_MB,
                cpu_budget=config.CONTAINER_CPUS,
                pids_limit=config.CONTAINER_PIDS_LIMIT,
            ),
            verification_expectation={
                "executor_policy": "private_service",
                "mission_contract_digest": mission_contract_digest,
            },
        )

    def build_repair_job(
        self,
        *,
        mission_contract_digest: str,
        operation_id: str,
        target_rel: str,
        workspace_path: str,
        workspace_digest: str,
        timeout_seconds: int,
        expected_digest: str = "",
        job_id: str | None = None,
    ) -> ExecutorJob:
        """Build a typed repair job for the private executor."""
        argv = ("repair", operation_id, target_rel)
        actual_job_id = job_id or f"executor-repair-{uuid.uuid4().hex}"
        material = {
            "argv": list(argv),
            "operation_id": operation_id,
            "target_rel": target_rel,
            "workspace_path": workspace_path,
            "workspace_digest": workspace_digest,
            "mission_contract_digest": mission_contract_digest,
        }
        action_digest = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        expires_at = (
            (
                datetime.now(timezone.utc)
                + timedelta(seconds=max(int(timeout_seconds), 1) + 5)
            )
            .replace(microsecond=0)
            .isoformat()
        )
        return ExecutorJob(
            job_id=actual_job_id,
            mission_contract_digest=mission_contract_digest,
            capability=ExecutorCapability(
                capability_id=f"executor-capability:{actual_job_id}",
                action_digest=action_digest,
                mission_contract_digest=mission_contract_digest,
                expires_at=expires_at,
            ),
            image=config.CONTAINER_IMAGE,
            argv=argv,
            workspace_snapshot=workspace_path,
            resource_limits=ResourceLimits(
                timeout_seconds=max(int(timeout_seconds), 1),
                max_output_bytes=config.MAX_COMMAND_OUTPUT_BYTES,
                memory_budget_mb=config.CONTAINER_MEMORY_MB,
                cpu_budget=config.CONTAINER_CPUS,
                pids_limit=config.CONTAINER_PIDS_LIMIT,
            ),
            verification_expectation={
                "executor_policy": "private_service",
                "mission_contract_digest": mission_contract_digest,
                "workspace_digest": workspace_digest,
                "expected_target_digest": expected_digest,
            },
        )

    def execute(self, job: ExecutorJob) -> ExecutorResult:
        if self.profile in ("production", "demo"):
            if self.backend_name != "private_service" or self.client is None:
                raise IsolationUnavailable(
                    "private executor service is required in production"
                )
            result = self.client.execute(job)
        elif self.client is not None:
            result = self.client.execute(job)
        elif self.runner is not None:
            result = self.runner(job)
        elif job.argv and job.argv[0] == "repair":
            result = execute_registered_repair_operation(job)
        else:
            raise IsolationUnavailable("isolated executor service is unavailable")
        if self.profile in ("production", "demo"):
            if self.backend_name != "private_service":
                raise IsolationUnavailable(
                    f"executor backend {self.backend_name!r} does not satisfy isolation"
                )
            if self.require_isolation and not result.isolation_verified:
                raise IsolationUnavailable("executor did not prove isolation")
        if result.job_id != job.job_id:
            raise IsolationUnavailable("executor returned a mismatched job id")
        return result


def execute_registered_repair_operation(job: ExecutorJob) -> ExecutorResult:
    """Execute a registered structured repair operation inside the staged workspace boundary."""
    if not job.argv or len(job.argv) < 3 or job.argv[0] != "repair":
        raise IsolationUnavailable("executor job is not a valid repair operation")

    op_id = job.argv[1]
    if op_id != "REMOVE_MAINTENANCE_MARKER_V1":
        raise IsolationUnavailable(f"unsupported repair operation: {op_id!r}")

    target_rel = job.argv[2]
    if any(char in target_rel for char in ";&|<>`\r\n\x00"):
        raise IsolationUnavailable("target relative path contains forbidden characters")
    if target_rel.startswith(("/", "\\")) or ":" in target_rel[:3]:
        raise IsolationUnavailable("target relative path must not be absolute")

    workspace_root = Path(job.workspace_snapshot).resolve()
    target_path = (workspace_root / target_rel.replace("\\", "/")).resolve()

    try:
        target_path.relative_to(workspace_root)
    except (ValueError, OSError) as exc:
        raise IsolationUnavailable("target path escapes staged workspace root") from exc

    if target_path.is_symlink():
        raise IsolationUnavailable("symlink target escape refused")

    if not target_path.exists() or not target_path.is_file():
        raise IsolationUnavailable("target file does not exist")

    original_bytes = target_path.read_bytes()
    before_digest = hashlib.sha256(original_bytes).hexdigest()

    expected_digest = job.verification_expectation.get("expected_target_digest")
    if expected_digest and before_digest != expected_digest:
        raise IsolationUnavailable("original content digest mismatch")

    content = original_bytes.decode("utf-8", errors="replace")
    new_content = (
        content.replace("# DEFECT_MARKER: fix_required\n", "")
        .replace("# DEFECT_MARKER: fix_required", "")
        .replace("TODO_MAINTENANCE_DEFECT\n", "")
        .replace("TODO_MAINTENANCE_DEFECT", "")
    )
    changed = new_content != content
    after_digest = hashlib.sha256(new_content.encode("utf-8")).hexdigest()

    if changed:
        tmp_target = target_path.with_suffix(target_path.suffix + ".tmp")
        tmp_target.write_text(new_content, encoding="utf-8")
        tmp_target.replace(target_path)

    out_payload = json.dumps(
        {
            "job_id": job.job_id,
            "operation_id": op_id,
            "target": target_rel,
            "before_digest": before_digest,
            "after_digest": after_digest,
            "changed": changed,
            "backend_name": "in_process_fixture",
        },
        sort_keys=True,
    )
    return ExecutorResult(
        job_id=job.job_id,
        status="completed",
        exit_code=0,
        stdout=out_payload,
        stderr="",
        isolation_verified=False,  # in-process fixture: isolation is NOT proven
        environment_digest=environment_digest({"op_id": op_id}),
    )


def environment_digest(environment: dict[str, str]) -> str:
    canonical = json.dumps(environment, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = [
    "ExecutorService",
    "IsolationUnavailable",
    "JobRunner",
    "StructuredCommandRunner",
    "StructuredExecutorClient",
    "environment_digest",
    "private_executor_runner_from_config",
]
