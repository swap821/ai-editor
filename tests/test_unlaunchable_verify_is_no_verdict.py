"""An unlaunchable verify is no verdict (2026-10-21).

Docker was down after a reboot. The client exited 1 ("failed to connect to the
docker API"), the executor reported that as a command that RAN and exited 1,
the verify tool scored it `[VERIFY FAIL] 0 passed, 0 failed`, the turn became a
verified failure, and three learned skills recalled into it lost 0.20
confidence each -- for a test that never ran. The outage also wrote "Docker is
not running" into the mistake pool twice.

Each layer is pinned here: the runner asks the engine, an engine that is not
there is ERROR ("could not be launched"), the verifier reflects on nothing, and
the verify tool says SKIPPED -- while a real failure stays a failure.
"""

from __future__ import annotations

import pytest

from aios.agents import tool_handlers
from aios.core import executor as executor_module
from aios.core.verifier import Verifier, VerifierResult

ENGINE_DOWN = (
    "failed to connect to the docker API at npipe:////./pipe/docker_engine; "
    "check if the path is correct and if the daemon is running"
)


def _engine(*, run_rc: int, run_out: str = "", run_err: str = "", engine_up: bool):
    """A fake process runner: `docker run` answers *run_rc*; `docker version`
    answers 0 only when the engine is up. Records which it was asked."""
    asked: list[str] = []

    def fake(argv, **kwargs):
        verb = argv[1]
        asked.append(verb)

        class _Completed:
            pass

        done = _Completed()
        if verb == "version":
            done.stdout, done.stderr = (
                ("29.5.2", "") if engine_up else ("", ENGINE_DOWN)
            )
            done.returncode = 0 if engine_up else 1
        else:
            done.stdout, done.stderr, done.returncode = run_out, run_err, run_rc
        return done

    return fake, asked


def _run(monkeypatch, tmp_path, fake):
    monkeypatch.setattr(executor_module, "get_scope_roots", lambda: ())
    runner = executor_module.DockerRunner(process_runner=fake)
    return runner("pytest -q", cwd=str(tmp_path.resolve()), env={}, timeout_s=5)


def test_an_engine_that_is_not_there_is_a_launch_failure(monkeypatch, tmp_path) -> None:
    fake, asked = _engine(run_rc=1, run_err=ENGINE_DOWN, engine_up=False)
    with pytest.raises(RuntimeError, match="isolated execution unavailable"):
        _run(monkeypatch, tmp_path, fake)
    assert asked == ["run", "version"], "the engine itself is asked, not the error text"


def test_a_real_failure_stays_a_failure(monkeypatch, tmp_path) -> None:
    fake, asked = _engine(run_rc=1, run_out="1 failed, 2 passed", engine_up=True)
    assert _run(monkeypatch, tmp_path, fake) == ("1 failed, 2 passed", "", 1)
    assert asked == ["run", "version"]


def test_docker_run_failing_to_start_the_container_is_a_launch_failure(
    monkeypatch, tmp_path
) -> None:
    """125 is `docker run`'s own failure; no probe is needed to know it."""
    fake, asked = _engine(run_rc=125, run_err="Unable to find image", engine_up=True)
    with pytest.raises(RuntimeError, match="isolated execution unavailable"):
        _run(monkeypatch, tmp_path, fake)
    assert asked == ["run"]


def test_a_pass_never_probes(monkeypatch, tmp_path) -> None:
    fake, asked = _engine(run_rc=0, run_out="3 passed", engine_up=True)
    assert _run(monkeypatch, tmp_path, fake)[2] == 0
    assert asked == ["run"]


class _Result:
    def __init__(self, status, exit_code=None, stdout="", reason=""):
        self.status, self.exit_code, self.stdout = status, exit_code, stdout
        self.stderr, self.reason = "", reason


class _Executor:
    def __init__(self, result):
        self.result = result

    def execute_approved(self, command):
        return self.result

    def execute(self, command, *, session_id=None):
        return self.result


def test_the_verifier_reflects_on_nothing_that_never_ran() -> None:
    reflected: list[str] = []
    down = _Result(
        "ERROR", reason="Execution failed to launch: isolated execution unavailable"
    )
    result = Verifier(
        _Executor(down), on_failure=lambda c, o: reflected.append(o)
    ).verify("pytest -q", approved=True)
    assert result.passed is False and result.status == "ERROR"
    assert reflected == [], "an outage is not a mistake to learn from"

    failed = _Result("OK", exit_code=1, stdout="1 failed")
    Verifier(_Executor(failed), on_failure=lambda c, o: reflected.append(o)).verify(
        "pytest -q", approved=True
    )
    assert len(reflected) == 1, "a real failure still feeds reflection"


def test_the_verify_tool_says_skipped_not_fail() -> None:
    class _Verifier:
        def __init__(self, result):
            self.result = result

        def verify(self, command, *, session_id=None, approved=False):
            return self.result

    down = VerifierResult(
        passed=False,
        summary="[ERROR] Execution failed to launch: isolated execution unavailable",
        confidence_delta=-0.1,
        status="ERROR",
    )
    output, status, failed = tool_handlers.verify_command(
        "pytest -q",
        approved=True,
        approved_commands=set(),
        verifier=_Verifier(down),
        session_id=None,
    )
    assert output.startswith("[VERIFY SKIPPED]"), output
    assert "[VERIFY FAIL]" not in output and "could not be launched" in output
    assert (status, failed) == ("blocked", True)

    real = VerifierResult(
        passed=False,
        summary="1 failed",
        confidence_delta=-0.1,
        failed_count=1,
        exit_code=1,
        status="OK",
    )
    output, _, _ = tool_handlers.verify_command(
        "pytest -q",
        approved=True,
        approved_commands=set(),
        verifier=_Verifier(real),
        session_id=None,
    )
    assert output.startswith("[VERIFY FAIL]"), "a real failure is still a verdict"
