"""The in-service repair path verifies its digests before it mutates anything.

Organ 13's C4. `aios/executor_service.py::execute_registered_operation_in_service`
computes a before-digest of the target file and a `tree_digest` of the workspace,
compares each against the caller's `verification_expectation`, and refuses on a
mismatch. **Nothing exercised it.** A grep across `tests/` for the function name
returned nothing before this file existed, so the integrity check that guards
every in-service repair had never been executed by a test.

## Why it looked covered, and was not

`aios/application/executor/service.py::execute_registered_repair_operation` is a
TWIN: same registered-operation id, same `("repair", <op>, <path>)` argv shape,
exercised by `tests/test_r15_production_repairs.py`. It is a different function
with different behaviour — it raises `IsolationUnavailable` where this one
returns `ExecutorResult(status="failed", ...)`, it performs no workspace-digest
check at all, and it reports `isolation_verified=False`. Testing the twin proved
nothing about the path the executor service actually dispatches to.

The two are told apart here by import site and by one observable: the real
function reads `AIOS_EXECUTOR_WORKSPACE_ROOT` to resolve the staged workspace;
the twin resolves `job.workspace_snapshot` directly and never reads that env var.

## Why these assertions

A refusal that happens *after* the file is rewritten is not a guard. Each case
therefore asserts the returned reason AND that the bytes on disk are unchanged —
the mismatch must short-circuit before mutation, which is the whole point of
checking a before-digest.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from aios.domain.executor import ExecutorCapability, ExecutorJob, ResourceLimits
from aios.executor_service import execute_registered_operation_in_service

_MARKER = "# DEFECT_MARKER: fix_required\n"
_OPERATION = "REMOVE_MAINTENANCE_MARKER_V1"


def _job(workspace: Path, target: str, expectation: dict) -> ExecutorJob:
    return ExecutorJob(
        job_id="job-organ13",
        mission_contract_digest="digest-organ13",
        capability=ExecutorCapability(
            capability_id="cap-organ13",
            action_digest="action-organ13",
            mission_contract_digest="digest-organ13",
            expires_at="2099-12-31T23:59:59Z",
        ),
        image="test-image",
        argv=("repair", _OPERATION, target),
        workspace_snapshot=str(workspace),
        resource_limits=ResourceLimits(
            timeout_seconds=30,
            max_output_bytes=1000,
            memory_budget_mb=512,
            cpu_budget=1.0,
            pids_limit=100,
        ),
        verification_expectation=expectation,
    )


def _workspace(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """A staged workspace holding one repairable file."""
    monkeypatch.setenv("AIOS_EXECUTOR_WORKSPACE_ROOT", str(tmp_path))
    target = tmp_path / "defect.py"
    target.write_text(f"print('hi')\n{_MARKER}", encoding="utf-8")
    return tmp_path, target


def test_a_wrong_target_digest_refuses_before_touching_the_file(
    tmp_path: Path, monkeypatch
) -> None:
    """The guard: the caller's view of the file must match reality."""
    workspace, target = _workspace(tmp_path, monkeypatch)
    before = target.read_bytes()

    result = execute_registered_operation_in_service(
        _job(workspace, "defect.py", {"expected_target_digest": "0" * 64})
    )

    assert result.status == "failed"
    assert result.reason == "original content digest mismatch"
    assert target.read_bytes() == before, (
        "the repair rewrote the file despite refusing it -- a digest check that "
        "runs after the mutation is not a guard"
    )


def test_a_wrong_workspace_digest_refuses_before_touching_the_file(
    tmp_path: Path, monkeypatch
) -> None:
    """The second, independent guard.

    The target digest can be correct while the surrounding workspace has drifted
    since the job was planned, so the tree digest is checked separately. This
    supplies a CORRECT target digest so only the workspace branch can fire.
    """
    workspace, target = _workspace(tmp_path, monkeypatch)
    before = target.read_bytes()
    correct_target_digest = hashlib.sha256(before).hexdigest()

    result = execute_registered_operation_in_service(
        _job(
            workspace,
            "defect.py",
            {
                "expected_target_digest": correct_target_digest,
                "workspace_digest": "0" * 64,
            },
        )
    )

    assert result.status == "failed"
    assert result.reason == "original workspace digest mismatch"
    assert target.read_bytes() == before


def test_matching_digests_let_the_repair_proceed(tmp_path: Path, monkeypatch) -> None:
    """The other direction, without which the refusals above prove nothing.

    A guard that refuses everything would pass both tests above while breaking
    every real repair.
    """
    workspace, target = _workspace(tmp_path, monkeypatch)
    correct_target_digest = hashlib.sha256(target.read_bytes()).hexdigest()

    result = execute_registered_operation_in_service(
        _job(workspace, "defect.py", {"expected_target_digest": correct_target_digest})
    )

    assert result.status == "completed", result.reason
    assert _MARKER not in target.read_text(encoding="utf-8"), (
        "the repair reported success without removing the maintenance marker"
    )
