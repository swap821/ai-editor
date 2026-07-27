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
from aios.operations.tracing import TraceContext, bind_trace_context


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


def test_trace_context_reaches_the_isolated_container() -> None:
    """Organ 52: the three-hop correlation chain, asserted end to end.

    The chain itself already existed and already ran here on every commit:

      1. `StructuredExecutorClient.execute()` sends `get_trace_context()
         .headers()` on its HTTP request  (application/executor/service.py:82)
      2. `executor_service.execute_job()` binds a context from those incoming
         headers                                     (executor_service.py:290)
      3. `DockerRunner.__call__` reshapes it via `TraceContext.as_env()` into
         fixed `--env` entries on the spawned container   (core/executor.py:352)

    What did NOT exist was any assertion on it. The probe script in this file
    never printed an `AIOS_TRACE_*` value, so the string "AIOS_TRACE" appeared
    nowhere in the release job's ~2100 log lines: hop 3 was exercised live on
    every commit and verified by nothing. A regression anywhere along the chain
    would have left every existing test green.

    This is also the only place the third hop CAN be proven. Hops 1 and 2 are
    reachable with fakes, but hop 3 crosses a real `subprocess.Popen` into a
    real container, so it needs a real Docker daemon -- which this job has and
    a local sandbox does not.

    Correlation metadata only: a trace id never authenticates a caller or
    widens a scope, and these `--env` entries are deliberately separate from
    the job's security-reviewed `environment_allowlist`, which they must not
    bypass or widen.
    """
    local_root = Path(
        os.getenv("AIOS_EXECUTOR_WORKSPACE_ROOT", "/app/data/executor-workspaces")
    )
    workspace = local_root / "trace"
    workspace.mkdir(parents=True, exist_ok=True)
    # Printed before anything bulky: this job's other probe deliberately
    # overflows max_output_bytes, and a truncated tail would silently drop the
    # very assertion this test exists to make.
    (workspace / "trace_probe.py").write_text(
        "import os\n"
        "print('request=' + os.environ.get('AIOS_TRACE_REQUEST_ID', '<unset>'))\n"
        "print('mission=' + os.environ.get('AIOS_TRACE_MISSION_ID', '<unset>'))\n",
        encoding="utf-8",
    )

    # Both must satisfy tracing._SAFE_ID, or hop 2's `new_trace_context()`
    # would discard them and mint a fresh uuid -- which would make this test
    # pass against a chain that never carried OUR ids.
    request_id = "organ52-live-trace-request"
    mission_id = "organ52-live-trace-mission"

    client = StructuredExecutorClient(
        base_url=os.environ["AIOS_EXECUTOR_URL"],
        token=os.environ["AIOS_EXECUTOR_TOKEN"],
        timeout_s=30,
    )
    context = TraceContext(request_id=request_id).with_ids(mission_id=mission_id)
    with bind_trace_context(context):
        result = client.execute(
            _job(
                workspace,
                os.getenv("AIOS_EXECUTOR_REMOTE_WORKSPACE_ROOT", "/workspace/jobs"),
                job_id="integration-trace",
                argv=("python", "trace_probe.py"),
            )
        )

    assert result.status == "completed"
    # The specific ids, not merely "some trace id": a generated-fresh id at any
    # hop would still be non-empty and would still look like propagation.
    assert f"request={request_id}" in result.stdout, result.stdout
    assert f"mission={mission_id}" in result.stdout, result.stdout


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
