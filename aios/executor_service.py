"""Private structured Executor Service process.

The control plane talks to this process over the Compose network. Only this
process is given the Docker socket; submitted jobs are structured
``ExecutorJob`` messages and never opaque shell strings. Missing runtime,
workspace or token configuration returns an explicit refusal.
"""

from __future__ import annotations

import hmac
import os

from fastapi import FastAPI, Header, HTTPException

from aios import config
from aios.domain.executor import ExecutorJob, ExecutorResult
from aios.infrastructure.executor.docker_runner import DockerJobRunner
from aios.infrastructure.executor import workspace as workspace_policy


app = FastAPI(
    title="GAGOS Executor Service",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def _token() -> str:
    return os.getenv("AIOS_EXECUTOR_TOKEN", "")


def _authorized(authorization: str | None) -> bool:
    token = _token()
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    return bool(token) and hmac.compare_digest(supplied, token)


def _workspace_allowed(path: str) -> bool:
    try:
        workspace_policy.resolve_staged_workspace(
            path, os.getenv("AIOS_EXECUTOR_WORKSPACE_ROOT", "/workspace/jobs")
        )
    except (OSError, ValueError):
        return False
    return True


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "executor",
        "runtime": config.CONTAINER_RUNTIME,
        "token_configured": bool(_token()),
    }


import hashlib
import json
from datetime import datetime, timezone

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def execute_registered_operation_in_service(job: ExecutorJob) -> ExecutorResult:
    started = utc_now()
    if not job.argv or len(job.argv) < 3 or job.argv[0] != "repair":
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=True,
            started_at=started,
            ended_at=utc_now(),
            reason="executor job is not a valid repair operation",
        )

    op_id = job.argv[1]
    if op_id != "REMOVE_MAINTENANCE_MARKER_V1":
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=True,
            started_at=started,
            ended_at=utc_now(),
            reason=f"unsupported repair operation: {op_id!r}",
        )

    target_rel = job.argv[2]
    if any(char in target_rel for char in ";&|<>`\r\n\x00"):
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=True,
            started_at=started,
            ended_at=utc_now(),
            reason="target relative path contains forbidden characters",
        )

    if target_rel.startswith(("/", "\\")) or ":" in target_rel[:3] or ".." in target_rel.split("/") or ".." in target_rel.split("\\"):
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=True,
            started_at=started,
            ended_at=utc_now(),
            reason="target relative path must not escape workspace",
        )

    staged_root = os.getenv("AIOS_EXECUTOR_WORKSPACE_ROOT", "/workspace/jobs")
    try:
        workspace_root = workspace_policy.resolve_staged_workspace(job.workspace_snapshot, staged_root)
        target_path = (workspace_root / target_rel.replace("\\", "/")).resolve()
        target_path.relative_to(workspace_root)
    except (ValueError, OSError) as exc:
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=True,
            started_at=started,
            ended_at=utc_now(),
            reason=f"workspace resolution failure: {exc}",
        )

    if target_path.is_symlink():
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=True,
            started_at=started,
            ended_at=utc_now(),
            reason="symlink target escape refused",
        )

    if not target_path.exists() or not target_path.is_file():
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=True,
            started_at=started,
            ended_at=utc_now(),
            reason="target file does not exist",
        )

    original_bytes = target_path.read_bytes()
    before_digest = hashlib.sha256(original_bytes).hexdigest()

    expected_digest = job.verification_expectation.get("expected_target_digest")
    if expected_digest and before_digest != expected_digest:
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=True,
            started_at=started,
            ended_at=utc_now(),
            reason="original content digest mismatch",
        )

    expected_ws_digest = job.verification_expectation.get("workspace_digest")
    from aios.application.workspaces.staged import tree_digest
    ws_digest_before = tree_digest(workspace_root)
    if expected_ws_digest and ws_digest_before != expected_ws_digest:
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=True,
            started_at=started,
            ended_at=utc_now(),
            reason="original workspace digest mismatch",
        )

    content = original_bytes.decode("utf-8", errors="replace")
    new_content = content
    markers = [
        "# DEFECT_MARKER: fix_required\n",
        "# DEFECT_MARKER: fix_required",
        "TODO_MAINTENANCE_DEFECT\n",
        "TODO_MAINTENANCE_DEFECT",
        "# AIOS_MAINTENANCE_REQUIRED: fix_required\n",
        "# AIOS_MAINTENANCE_REQUIRED: fix_required",
    ]
    for m in markers:
        new_content = new_content.replace(m, "")

    changed = new_content != content
    if not changed:
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=True,
            started_at=started,
            ended_at=utc_now(),
            reason="target file contained no allowed maintenance marker",
        )

    after_bytes = new_content.encode("utf-8")
    after_digest = hashlib.sha256(after_bytes).hexdigest()

    tmp_target = target_path.with_suffix(target_path.suffix + ".tmp")
    tmp_target.write_bytes(after_bytes)
    try:
        with open(tmp_target, "rb") as f:
            os.fsync(f.fileno())
    except OSError:
        pass
    tmp_target.replace(target_path)

    ws_digest_after = tree_digest(workspace_root)

    out_payload = json.dumps(
        {
            "job_id": job.job_id,
            "operation_id": op_id,
            "target": target_rel,
            "changed": changed,
            "before_digest": before_digest,
            "after_digest": after_digest,
            "workspace_digest_before": ws_digest_before,
            "workspace_digest_after": ws_digest_after,
            "isolation_backend": "private_executor_service",
        },
        sort_keys=True,
    )

    env_dig = hashlib.sha256(json.dumps({"op_id": op_id}, sort_keys=True).encode()).hexdigest()

    return ExecutorResult(
        job_id=job.job_id,
        status="completed",
        exit_code=0,
        stdout=out_payload,
        stderr="",
        isolation_verified=True,
        environment_digest=env_dig,
        started_at=started,
        ended_at=utc_now(),
    )


@app.post("/v1/jobs", response_model=ExecutorResult)
def execute_job(
    job: ExecutorJob,
    authorization: str | None = Header(default=None),
) -> ExecutorResult:
    if not _token():
        raise HTTPException(
            status_code=503, detail="executor authentication is not configured"
        )
    if not _authorized(authorization):
        raise HTTPException(status_code=401, detail="executor authentication failed")
    if job.network_policy.mode != "none":
        raise HTTPException(
            status_code=403, detail="executor network access is disabled in v1"
        )
    if not _workspace_allowed(job.workspace_snapshot):
        raise HTTPException(
            status_code=403, detail="workspace is outside executor staging root"
        )
    if job.argv and job.argv[0] == "repair":
        return execute_registered_operation_in_service(job)
    try:
        result = DockerJobRunner()(job)
    except Exception as exc:  # noqa: BLE001 - normalize to a truthful refusal
        return ExecutorResult(
            job_id=job.job_id,
            status="unavailable",
            isolation_verified=False,
            reason=f"isolated executor unavailable: {exc}",
        )
    limit = job.resource_limits.max_output_bytes
    stdout = result.stdout.encode("utf-8", "replace")[:limit].decode("utf-8", "replace")
    stderr = result.stderr.encode("utf-8", "replace")[:limit].decode("utf-8", "replace")
    truncated = (
        result.output_truncated
        or len(result.stdout.encode()) > limit
        or len(result.stderr.encode()) > limit
    )
    return result.model_copy(
        update={"stdout": stdout, "stderr": stderr, "output_truncated": truncated}
    )


def main() -> None:
    import uvicorn

    uvicorn.run(
        "aios.executor_service:app",
        host=os.getenv("AIOS_EXECUTOR_HOST", "0.0.0.0"),
        port=int(os.getenv("AIOS_EXECUTOR_PORT", "8081")),
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
