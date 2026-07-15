"""Compatibility adapter from structured jobs to the existing Docker runner."""

from __future__ import annotations

import os
import shlex
import subprocess

from aios.core.executor import DockerRunner
from aios.domain.executor import ExecutorJob, ExecutorResult
from aios.application.executor.service import environment_digest, utc_now
from aios.infrastructure.executor import workspace as workspace_policy


class DockerJobRunner:
    """Run one structured job in the existing locked-down Docker cage.

    ``shlex.join`` is an internal compatibility serialization only; callers of
    this adapter exchange ``ExecutorJob.argv`` and never raw shell strings.
    """

    def __init__(self, runner: DockerRunner | None = None) -> None:
        self.runner = runner or DockerRunner()

    def __call__(self, job: ExecutorJob) -> ExecutorResult:
        argv = job.argv or job.worker_entrypoint
        command = shlex.join(argv)
        env = {
            name: job.environment[name]
            for name in job.environment_allowlist
            if name in job.environment
        }
        started = utc_now()
        try:
            workspace = workspace_policy.resolve_staged_workspace(
                job.workspace_snapshot,
                os.getenv("AIOS_EXECUTOR_WORKSPACE_ROOT", "/workspace/jobs"),
            )
            daemon_workspace = workspace_policy.daemon_workspace_path(
                workspace,
                staged_root=os.getenv(
                    "AIOS_EXECUTOR_WORKSPACE_ROOT", "/workspace/jobs"
                ),
                daemon_root=os.getenv("AIOS_EXECUTOR_DAEMON_WORKSPACE_ROOT", ""),
            )
            stdout, stderr, code = self.runner(
                command,
                cwd=daemon_workspace,
                env=env,
                timeout_s=job.resource_limits.timeout_seconds,
            )
        except (TimeoutError, subprocess.TimeoutExpired):
            return ExecutorResult(
                job_id=job.job_id,
                status="timeout",
                isolation_verified=False,
                started_at=started,
                ended_at=utc_now(),
                reason="executor timeout",
            )
        except OSError as exc:
            return ExecutorResult(
                job_id=job.job_id,
                status="unavailable",
                isolation_verified=False,
                started_at=started,
                ended_at=utc_now(),
                reason=f"executor unavailable: {exc}",
            )
        except Exception as exc:  # noqa: BLE001 - normalize cage failures
            return ExecutorResult(
                job_id=job.job_id,
                status="failed",
                isolation_verified=True,
                started_at=started,
                ended_at=utc_now(),
                reason=str(exc),
            )
        return ExecutorResult(
            job_id=job.job_id,
            status="completed" if code == 0 else "failed",
            exit_code=code,
            stdout=stdout,
            stderr=stderr,
            output_truncated="OUTPUT TRUNCATED" in (stdout + stderr),
            isolation_verified=True,
            environment_digest=environment_digest(env),
            started_at=started,
            ended_at=utc_now(),
        )


__all__ = ["DockerJobRunner"]
