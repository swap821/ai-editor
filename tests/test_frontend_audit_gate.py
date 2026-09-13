"""The frontend audit gate must tell three different failures apart.

`npm audit --audit-level=high` exits 1 for reasons that deserve opposite
responses: it found a vulnerability, or it could not reach the advisory
endpoint, or it could not run at all. npm gives all three the same exit code.

On 2026-09-13 the second case took `frontend-tests` down in 19 seconds on
`400 Bad Request` from `/security/audits/quick`, while the same commit passed
the same job in a sibling run. npm's own notice says that endpoint is being
retired, so the false alarm becomes more frequent from here.

The danger is not the red build. It is that a gate which fails for reasons
unrelated to what it measures teaches people to re-run until green -- and that
habit is what lets a real finding through. So the step retries the transport
failure, reports an unrunnable audit as unrunnable rather than as a finding, and
still FAILS when the endpoint never answers. An audit that could not run is not
an audit that passed.

These tests execute the actual `run:` block extracted from `ci.yml` against a
fake `npm`, so the gate is exercised rather than asserted about.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_YML = REPO_ROOT / ".github/workflows/ci.yml"


def _working_bash() -> str | None:
    """The first `bash` on PATH that can actually run a command.

    NOT `shutil.which("bash")` alone. On Windows that resolves to whichever
    bash wins the PATH race, and System32's WSL stub wins when pytest is
    launched from PowerShell -- it then fails with

        WSL (12 - Relay) ERROR: execvpe(/bin/bash) failed

    which surfaced as five assertion failures in the full suite while the same
    tests passed when launched from Git Bash. A test whose result depends on how
    the runner was started teaches people to ignore the suite, which is the
    habit this file's own subject exists to prevent.
    """
    candidates: list[str] = []
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        found = shutil.which("bash", path=directory)
        if found:
            candidates.append(found)
    # Git Bash is a real POSIX shell that is frequently NOT on PowerShell's PATH
    # even when it is installed, so a PATH-only search would skip these tests on
    # a machine that can perfectly well run them -- trading a false failure for a
    # silent coverage hole, which is only a better bug.
    if os.name == "nt":
        candidates += [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        ]

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen or not os.path.exists(candidate):
            continue
        seen.add(candidate)
        try:
            probe = subprocess.run(
                [candidate, "-c", "echo ok"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if probe.returncode == 0 and "ok" in probe.stdout:
            return candidate
    return None


BASH = _working_bash()
pytestmark = pytest.mark.skipif(
    BASH is None, reason="no working POSIX shell; the step only ever runs on bash"
)


def _audit_step() -> dict:
    workflow = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["frontend-tests"]["steps"]
    return next(s for s in steps if s.get("name") == "Audit frontend dependencies")


def _run(tmp_path: Path, npm_script: str) -> tuple[int, str]:
    """Execute the real run-block with *npm_script* standing in for npm."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("npm", npm_script), ("sleep", "exit 0")):
        f = bin_dir / name
        f.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8", newline="\n")
        f.chmod(f.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    script = tmp_path / "step.sh"
    script.write_text(_audit_step()["run"], encoding="utf-8", newline="\n")

    env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    env["COUNTER"] = str(tmp_path / "count")
    proc = subprocess.run(
        [BASH, str(script)], capture_output=True, text=True, env=env, timeout=120
    )
    return proc.returncode, proc.stdout + proc.stderr


def test_a_clean_audit_passes_on_the_first_call(tmp_path: Path) -> None:
    rc, out = _run(tmp_path, "echo CALLED\nexit 0")

    assert rc == 0
    assert out.count("CALLED") == 1, "a passing audit must not be retried"


def test_a_real_finding_fails_immediately_and_is_not_retried(tmp_path: Path) -> None:
    """THE BAR. Retrying a finding would be a fail-open guard with extra steps."""
    rc, out = _run(
        tmp_path, 'echo CALLED\necho "1 high severity vulnerability"\nexit 1'
    )

    assert rc == 1
    assert out.count("CALLED") == 1, "a finding must fail on the first call"
    assert "reported a vulnerability" in out


def test_the_transport_failure_is_retried_and_recovers(tmp_path: Path) -> None:
    """The case that motivated this: a 400 that answers on the next attempt."""
    rc, out = _run(
        tmp_path,
        'n=$(cat "$COUNTER" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "$COUNTER"\n'
        "echo CALLED\n"
        'if [ "$n" -eq 1 ]; then echo "npm error audit endpoint returned an error"; exit 1; fi\n'
        'echo "found 0 vulnerabilities"; exit 0',
    )

    assert rc == 0
    assert out.count("CALLED") == 2, "should have retried exactly once"


def test_an_endpoint_that_never_answers_still_fails(tmp_path: Path) -> None:
    """An audit that could not run is not an audit that passed."""
    rc, out = _run(
        tmp_path,
        'echo CALLED\necho "npm error audit endpoint returned an error"\nexit 1',
    )

    assert rc == 1, "exhausted retries must fail, never fall through to success"
    assert out.count("CALLED") == 3
    assert "failing rather than assuming clean" in out


def test_an_unrunnable_audit_is_not_reported_as_a_finding(tmp_path: Path) -> None:
    """ENOLOCK means npm never checked anything.

    Calling that a vulnerability is a false accusation; calling it a pass is a
    fail-open guard. It is neither -- it is an audit that did not happen.
    """
    rc, out = _run(tmp_path, 'echo CALLED\necho "npm error code ENOLOCK"\nexit 1')

    assert rc == 1
    assert "could not run" in out
    assert "reported a vulnerability" not in out


def test_the_gate_still_enforces_high_and_never_swallows_failure() -> None:
    """Guards the shape itself: no `|| true`, no continue-on-error, no `set -e` loss."""
    step = _audit_step()
    run = step["run"]

    assert "--audit-level=high" in run, "the threshold is the gate"
    assert "|| true" not in run
    assert "continue-on-error" not in step
    assert step.get("continue-on-error") is not True
    # Every path out of the loop is an explicit exit; nothing falls through.
    assert run.rstrip().endswith("exit 1")
