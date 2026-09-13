"""Private structured Executor Service process.

The control plane talks to this process over the Compose network. Only this
process is given the Docker socket; submitted jobs are structured
``ExecutorJob`` messages and never opaque shell strings. Missing runtime,
workspace or token configuration returns an explicit refusal.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Request

from aios import config
from aios.domain.executor import ExecutorJob, ExecutorRepairReceipt, ExecutorResult
from aios.infrastructure.executor.docker_runner import DockerJobRunner
from aios.infrastructure.executor import workspace as workspace_policy
from aios.operations.tracing import bind_trace_context, new_trace_context


EXECUTOR_SERVICE_IDENTITY_VERSION = "gagos-executor-service/1"


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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def execute_registered_operation_in_service(job: ExecutorJob) -> ExecutorResult:
    started = utc_now()
    if not job.argv or len(job.argv) < 3 or job.argv[0] != "repair":
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=False,
            started_at=started,
            ended_at=utc_now(),
            reason="executor job is not a valid repair operation",
        )

    op_id = job.argv[1]
    if op_id != "REMOVE_MAINTENANCE_MARKER_V1":
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=False,
            started_at=started,
            ended_at=utc_now(),
            reason=f"unsupported repair operation: {op_id!r}",
        )

    target_rel = job.argv[2]
    if any(char in target_rel for char in ";&|<>`\r\n\x00"):
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=False,
            started_at=started,
            ended_at=utc_now(),
            reason="target relative path contains forbidden characters",
        )

    if (
        target_rel.startswith(("/", "\\"))
        or ":" in target_rel[:3]
        or ".." in target_rel.split("/")
        or ".." in target_rel.split("\\")
    ):
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=False,
            started_at=started,
            ended_at=utc_now(),
            reason="target relative path must not escape workspace",
        )

    staged_root = os.getenv("AIOS_EXECUTOR_WORKSPACE_ROOT", "/workspace/jobs")
    try:
        workspace_root = workspace_policy.resolve_staged_workspace(
            job.workspace_snapshot, staged_root
        )
        root_text = str(workspace_root)
        candidate = os.path.normpath(
            os.path.join(root_text, target_rel.replace("\\", "/"))
        )
        # CANONICALISE, do not merely spell-check.
        #
        # This used to be `candidate.startswith(root_text + os.sep)` and nothing
        # else. `normpath` is LEXICAL -- it collapses "..", it does not follow
        # links -- so a redirected intermediate directory sails through: the
        # path still reads as being inside the staged root. The only link test
        # was `target_path.is_symlink()` below, which inspects the FINAL
        # component, and the leaf here is an ordinary file. Measured
        # 2026-09-13: the repair completed, reported isolation_verified=True,
        # and edited a file outside the staged root.
        #
        # `resolve_staged_workspace` -- called three lines above, and described
        # in its own docstring as "the trust boundary for the authenticated
        # executor service" -- already canonicalises BOTH sides with realpath.
        # The bug was re-deriving that same question lexically right after
        # asking it correctly. So ask the one that works, about the target too.
        #
        # Note this cannot be fixed by checking `is_symlink()` on every
        # component. On Windows a DIRECTORY JUNCTION redirects identically,
        # needs no privilege to create, and `Path.is_symlink()` reports False
        # for it. realpath is what sees through both.
        target_path = workspace_policy.resolve_staged_workspace(
            candidate, workspace_root
        )
    except (ValueError, OSError) as exc:
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=False,
            started_at=started,
            ended_at=utc_now(),
            reason=f"workspace resolution failure: {exc}",
        )

    if target_path.is_symlink():
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=False,
            started_at=started,
            ended_at=utc_now(),
            reason="symlink target escape refused",
        )

    if not target_path.exists() or not target_path.is_file():
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=False,
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
            isolation_verified=False,
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
            isolation_verified=False,
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
            isolation_verified=False,
            started_at=started,
            ended_at=utc_now(),
            reason="target file contained no allowed maintenance marker",
        )

    after_bytes = new_content.encode("utf-8")
    after_digest = hashlib.sha256(after_bytes).hexdigest()

    # Re-verify containment IMMEDIATELY before writing.
    #
    # The resolution above canonicalises, but a check and a write are two
    # moments. Between them the workspace is still on disk and still writable,
    # so a component can be swapped for a link after it was judged safe -- the
    # classic time-of-check/time-of-use window. Re-asking costs one realpath on
    # a path already in cache, and it shrinks the window to the width of this
    # call rather than the width of the whole repair.
    #
    # O_NOFOLLOW would narrow the leaf further, but it does not exist on
    # Windows (checked: `hasattr(os, "O_NOFOLLOW")` is False there), and this
    # service runs on the operator's Windows laptop as well as in CI. A guard
    # that exists on one platform and silently vanishes on another is worse
    # than one that works the same everywhere, so the re-check is the control
    # and the flag is applied only where the platform actually offers it.
    try:
        workspace_policy.resolve_staged_workspace(str(target_path), workspace_root)
    except (ValueError, OSError) as exc:
        return ExecutorResult(
            job_id=job.job_id,
            status="failed",
            isolation_verified=False,
            started_at=started,
            ended_at=utc_now(),
            reason=f"target left the staged workspace before the write: {exc}",
        )

    tmp_target = target_path.with_suffix(target_path.suffix + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(tmp_target, flags, 0o600)
    try:
        os.write(fd, after_bytes)
        os.fsync(fd)
    finally:
        os.close(fd)
    tmp_target.replace(target_path)

    ws_digest_after = tree_digest(workspace_root)

    env_dig = hashlib.sha256(
        json.dumps({"op_id": op_id}, sort_keys=True).encode()
    ).hexdigest()
    ended = utc_now()
    receipt = ExecutorRepairReceipt(
        job_id=job.job_id,
        mission_contract_digest=job.mission_contract_digest,
        operation_id=op_id,
        target=target_rel,
        changed=changed,
        before_target_digest=before_digest,
        after_target_digest=after_digest,
        workspace_digest_before=ws_digest_before,
        workspace_digest_after=ws_digest_after,
        isolation_backend="private_executor_service",
        environment_digest=env_dig,
        started_timestamp=started,
        ended_timestamp=ended,
        executor_service_identity_version=EXECUTOR_SERVICE_IDENTITY_VERSION,
        exit_code=0,
        receipt_version="1.0",
    )

    return ExecutorResult(
        job_id=job.job_id,
        status="completed",
        exit_code=0,
        stdout=receipt.model_dump_json(),
        stderr="",
        isolation_verified=True,
        environment_digest=env_dig,
        started_at=started,
        ended_at=ended,
    )


class ExecutorServiceAuthority:
    """Own the authenticated, network-disabled executor dispatch boundary."""

    def execute(
        self,
        job: ExecutorJob,
        request: Request,
        authorization: str | None,
    ) -> ExecutorResult:
        if not _token():
            raise HTTPException(
                status_code=503, detail="executor authentication is not configured"
            )
        if not _authorized(authorization):
            raise HTTPException(
                status_code=401, detail="executor authentication failed"
            )
        if job.network_policy.mode != "none":
            raise HTTPException(
                status_code=403, detail="executor network access is disabled in v1"
            )
        if not _workspace_allowed(job.workspace_snapshot):
            raise HTTPException(
                status_code=403, detail="workspace is outside executor staging root"
            )
        # Organ 52: bind the caller's propagated trace context (if any) for the
        # duration of this job's dispatch, so a spawned per-job container's
        # --env entries (aios.core.executor.DockerRunner) carry the same
        # correlation ids the request arrived with, instead of a fresh,
        # unrelated one generated inside this process.
        with bind_trace_context(new_trace_context(request.headers)):
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
        stdout = result.stdout.encode("utf-8", "replace")[:limit].decode(
            "utf-8", "replace"
        )
        stderr = result.stderr.encode("utf-8", "replace")[:limit].decode(
            "utf-8", "replace"
        )
        truncated = (
            result.output_truncated
            or len(result.stdout.encode()) > limit
            or len(result.stderr.encode()) > limit
        )
        return result.model_copy(
            update={"stdout": stdout, "stderr": stderr, "output_truncated": truncated}
        )


_EXECUTOR_SERVICE_AUTHORITY = ExecutorServiceAuthority()


@app.post("/v1/jobs", response_model=ExecutorResult)
def execute_job(
    job: ExecutorJob,
    request: Request,
    authorization: str | None = Header(default=None),
) -> ExecutorResult:
    """Dispatch through the one concrete executor-service authority."""
    return _EXECUTOR_SERVICE_AUTHORITY.execute(job, request, authorization)


__all__ = [
    "ExecutorServiceAuthority",
    "execute_job",
    "execute_registered_operation_in_service",
    "health",
]


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
