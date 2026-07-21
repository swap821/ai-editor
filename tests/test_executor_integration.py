"""Live private Executor Service proof used by the Linux release job.

The file is skipped during ordinary unit runs and is executed inside the
control-plane container after Compose starts the private executor.  Keeping the
probe in the repository makes the isolation claims executable rather than
documentation-only.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from aios.application.executor.service import (
    IsolationUnavailable,
    StructuredExecutorClient,
)
from aios.domain.executor import ExecutorCapability, ExecutorJob, ResourceLimits


pytestmark = pytest.mark.skipif(
    os.getenv("AIOS_EXECUTOR_INTEGRATION") != "1",
    reason="live private executor service is not enabled",
)


def _job(
    root: Path,
    remote_root: str,
    *,
    job_id: str,
    argv: tuple[str, ...],
    timeout_seconds: int = 10,
    max_output_bytes: int = 4096,
) -> ExecutorJob:
    return ExecutorJob(
        job_id=job_id,
        mission_contract_digest=f"contract-{job_id}",
        capability=ExecutorCapability(
            capability_id=f"cap-{job_id}",
            action_digest=f"action-{job_id}",
            mission_contract_digest=f"contract-{job_id}",
            expires_at="2099-01-01T00:00:00+00:00",
        ),
        image=os.getenv("AIOS_CONTAINER_IMAGE", "aios-executor:local"),
        argv=argv,
        workspace_snapshot=f"{remote_root}/{root.name}",
        resource_limits=ResourceLimits(
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        ),
    )


def test_private_executor_isolation_contract() -> None:
    assert not Path("/var/run/docker.sock").exists(), (
        "control-plane container must not receive the Docker socket"
    )
    local_root = Path(
        os.getenv("AIOS_EXECUTOR_WORKSPACE_ROOT", "/app/data/executor-workspaces")
    )
    workspace = local_root / "integration"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "probe.py").write_text(
        "import os\n"
        "import socket\n"
        "from pathlib import Path\n"
        "print(f'uid={os.getuid()}')\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 80), timeout=1)\n"
        "    print('network=allowed')\n"
        "except Exception:\n"
        "    print('network=blocked')\n"
        "try:\n"
        "    Path('/app/outside.txt').write_text('escape')\n"
        "    print('outside=written')\n"
        "except Exception:\n"
        "    print('outside=blocked')\n"
        "print('x' * 10000)\n",
        encoding="utf-8",
    )
    client = StructuredExecutorClient(
        base_url=os.environ["AIOS_EXECUTOR_URL"],
        token=os.environ["AIOS_EXECUTOR_TOKEN"],
        timeout_s=30,
    )
    result = client.execute(
        _job(
            workspace,
            os.getenv("AIOS_EXECUTOR_REMOTE_WORKSPACE_ROOT", "/workspace/jobs"),
            job_id="integration-proof",
            argv=("python", "probe.py"),
            max_output_bytes=1024,
        )
    )
    assert result.status == "completed"
    assert result.isolation_verified is True
    assert "uid=65534" in result.stdout
    assert "network=blocked" in result.stdout
    assert "outside=blocked" in result.stdout
    assert len(result.stdout.encode("utf-8")) <= 1024
    assert result.output_truncated is True


def test_private_executor_timeout_is_refused() -> None:
    local_root = Path(
        os.getenv("AIOS_EXECUTOR_WORKSPACE_ROOT", "/app/data/executor-workspaces")
    )
    workspace = local_root / "timeout"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "sleep.py").write_text(
        "import time\ntime.sleep(10)\n", encoding="utf-8"
    )
    client = StructuredExecutorClient(
        base_url=os.environ["AIOS_EXECUTOR_URL"],
        token=os.environ["AIOS_EXECUTOR_TOKEN"],
        timeout_s=30,
    )
    with pytest.raises(IsolationUnavailable, match="timeout"):
        client.execute(
            _job(
                workspace,
                os.getenv("AIOS_EXECUTOR_REMOTE_WORKSPACE_ROOT", "/workspace/jobs"),
                job_id="integration-timeout",
                argv=("python", "sleep.py"),
                timeout_seconds=1,
            )
        )


def test_missing_private_executor_is_refused() -> None:
    local_root = Path(
        os.getenv("AIOS_EXECUTOR_WORKSPACE_ROOT", "/app/data/executor-workspaces")
    )
    workspace = local_root / "missing"
    workspace.mkdir(parents=True, exist_ok=True)
    client = StructuredExecutorClient(
        base_url="http://127.0.0.1:1",
        token=os.environ["AIOS_EXECUTOR_TOKEN"],
        timeout_s=1,
    )
    with pytest.raises(IsolationUnavailable, match="unavailable"):
        client.execute(
            _job(
                workspace,
                os.getenv("AIOS_EXECUTOR_REMOTE_WORKSPACE_ROOT", "/workspace/jobs"),
                job_id="integration-missing",
                argv=("python", "-c", "print('ok')"),
            )
        )
