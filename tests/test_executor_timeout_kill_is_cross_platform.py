"""A timed-out subprocess must actually be killed, on every platform.

Found by the first run of the mypy gate (Ultra-plan Phase 8 / item 86):

    aios/core/executor.py:197: Module has no attribute "SIGCONT"
    aios/core/executor.py:202: Module has no attribute "killpg"
    aios/core/executor.py:202: Module has no attribute "getpgid"
    aios/core/executor.py:202: Module has no attribute "SIGKILL"

Those four names are POSIX-only. Measured on this host (win32)::

    signal.SIGCONT: False    os.killpg:  False
    signal.SIGKILL: False    os.getpgid: False

The timeout path guarded them with ``except (OSError, ProcessLookupError)`` --
which does NOT catch `AttributeError`. So on Windows a subprocess that exceeded
its timeout raised `AttributeError` out of `_bounded_run` instead of being
killed: the `process.kill()` fallback was unreachable, the child was left
running, and the caller saw an attribute error rather than a timeout.

This is the executor -- the component whose entire job is bounding what an agent
may do -- and the operator's own platform is win32. No test caught it because no
test forced a timeout on Windows; the type checker found it statically.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from aios.core import executor as executor_module


class _HangingProcess:
    """A process that never exits, so `wait(timeout=...)` always times out."""

    def __init__(self) -> None:
        self.pid = 424242
        self.killed = False
        self.stdout = None
        self.stderr = None
        self._waits = 0

    def wait(self, timeout: float | None = None):  # noqa: ANN201
        self._waits += 1
        if timeout is not None:
            raise subprocess.TimeoutExpired(cmd="hang", timeout=timeout)
        return -9  # the post-kill wait

    def kill(self) -> None:
        self.killed = True


def test_a_timeout_kills_the_child_rather_than_raising_attributeerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bug, reproduced by removing the POSIX names on any platform.

    Deleting them models Windows exactly -- `hasattr` is False -- so this test is
    meaningful on Linux and macOS CI too, not only on the host that happened to
    expose it.
    """
    import os
    import signal

    for name in ("SIGCONT", "SIGKILL"):
        monkeypatch.delattr(signal, name, raising=False)
    for name in ("killpg", "getpgid"):
        monkeypatch.delattr(os, name, raising=False)

    process = _HangingProcess()
    monkeypatch.setattr(
        executor_module.subprocess, "Popen", lambda *a, **k: process
    )

    with pytest.raises(subprocess.TimeoutExpired):
        executor_module._bounded_run(
            ["python", "-c", "pass"],
            shell=False,
            env={},
            capture_output=True,
            text=True,
            timeout=0.01,
        )

    assert process.killed, (
        "the timed-out child was never killed. The POSIX-only kill path raised "
        "AttributeError, which `except (OSError, ProcessLookupError)` does not "
        "catch, so the process.kill() fallback was unreachable and the child was "
        "left running."
    )


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX group-kill is unavailable on Windows"
)
def test_the_posix_group_kill_is_still_preferred_where_it_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fix must not downgrade POSIX to a bare child kill.

    Killing only the immediate child leaves the process GROUP alive, which is
    how a sandboxed command escapes its timeout by forking. The group kill is
    the point; the fallback is for platforms that cannot do it.
    """
    import os

    called: dict[str, object] = {}
    monkeypatch.setattr(os, "getpgid", lambda pid: 4242)
    monkeypatch.setattr(
        os, "killpg", lambda pgid, sig: called.update(pgid=pgid, sig=sig)
    )

    process = _HangingProcess()
    monkeypatch.setattr(
        executor_module.subprocess, "Popen", lambda *a, **k: process
    )

    with pytest.raises(subprocess.TimeoutExpired):
        executor_module._bounded_run(
            ["python", "-c", "pass"],
            shell=False,
            env={},
            capture_output=True,
            text=True,
            timeout=0.01,
        )

    assert called.get("pgid") == 4242, (
        "the POSIX process-group kill was skipped; a forking child would survive "
        "its own timeout"
    )
    assert not process.killed, (
        "the group kill succeeded, so the single-child fallback should not have run"
    )
