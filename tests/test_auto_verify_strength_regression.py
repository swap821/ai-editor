"""Regression: the forced auto-verify must yield STRONG from a REAL pytest run.

Found live by prove_it.py (2026-07-03): every unit test that asserts
strength=STRONG feeds the parser a canned "1 passed" string through a
FakeRunner, so none of them ever walked the true chain — a real pytest
subprocess, launched from the sandbox scope root, inheriting this repo's
own pytest.ini. That ini contributes ``-q`` via addopts; stacked with the
auto-verify command's own ``-q`` it becomes ``-qq``, which suppresses the
"N passed" summary line entirely. ``_parse_counts()`` then reads (0, 0)
and ``derive_strength()`` refuses STRONG — so no real auto-verify could
ever promote a skill, silently, in exactly the environment that matters.

This test closes that gap: it runs the EXACT production command (shared
builder, no drift) as a real subprocess and walks the output through the
real parser and the real strength taxonomy.
"""
from __future__ import annotations

import shlex
import subprocess
import sys
import uuid
from pathlib import Path

from aios import config
from aios.agents.tool_agent import build_auto_verify_command
from aios.core.verification_strength import VerificationStrength, derive_strength
from aios.core.verifier import _parse_counts

_TRIVIAL_TEST = '''\
def test_trivially_true():
    assert (1 + 1) == 2


def test_also_true():
    assert "aios"[::-1] == "soia"
'''


def test_real_pytest_auto_verify_reaches_strong(tmp_path_factory) -> None:
    scope_root = config.SCOPE_ROOTS[0].resolve()
    repo_root = scope_root.parent  # the executor's actual cwd (see Executor._scope_cwd)
    # A unique sibling-test filename inside the REAL sandbox scope root — the
    # defect only reproduces under this repo's own pytest.ini inheritance, so a
    # tmp_path sandbox would not exercise the true chain.
    test_file = scope_root / f"test_w4_strength_regress_{uuid.uuid4().hex[:8]}.py"
    test_file.write_text(_TRIVIAL_TEST, encoding="utf-8")
    try:
        test_arg = f"{scope_root.name}/{test_file.name}"
        command = build_auto_verify_command(test_arg)

        # Execute the EXACT command production would run, from the executor's
        # cwd (the repo root, not the sandbox scope root -- training_ground.X
        # imports must resolve). Only the program token is pinned to this
        # interpreter at exec time (PATH-independence for the test harness);
        # the command STRING — what the gateway classifies and derive_strength
        # anchors on — is the untouched production artifact.
        tokens = shlex.split(command)
        assert tokens[:3] == ["python", "-m", "pytest"], (
            f"auto-verify no longer fronts the recognized runner: {command!r}"
        )
        exec_tokens = [sys.executable] + tokens[1:]
        proc = subprocess.run(
            exec_tokens,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (proc.stdout or "") + (proc.stderr or "")

        assert proc.returncode == 0, f"trivial test failed to pass:\n{output}"

        passed_count, failed_count = _parse_counts(output)
        assert passed_count > 0, (
            "the real pytest run printed no parseable 'N passed' summary — "
            "the -q/addopts stacking defect is back:\n" + output[-800:]
        )
        assert failed_count == 0

        strength = derive_strength(
            passed=True,
            passed_count=passed_count,
            failed_count=failed_count,
            command=command,
        )
        assert strength is VerificationStrength.STRONG, (
            f"a genuine passing auto-verify must be STRONG, got {strength.name}"
        )
    finally:
        test_file.unlink(missing_ok=True)
        # pytest may leave a cache dir for the sandbox run; drop it if empty-ish
        # is not worth chasing — only the test file itself was ours to manage.
