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
