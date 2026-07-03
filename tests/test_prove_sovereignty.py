"""Pytest wrapper for prove_sovereignty.py (sovereignty S4).

Exercises the full sovereignty proof as part of the test suite.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROVE_SOVEREIGNTY = REPO_ROOT / "prove_sovereignty.py"


def test_sovereignty_proof_passes() -> None:
    """The full sovereignty proof must pass: 18 assertions, 6 phases."""
    env = {**os.environ, "PYTHONUTF8": "1"}
    result = subprocess.run(
        [sys.executable, str(PROVE_SOVEREIGNTY)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert result.returncode == 0, (
        f"prove_sovereignty.py failed (exit {result.returncode}):\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert "[PASS]" in result.stdout
    assert "[FAIL]" not in result.stdout
    assert "SOVEREIGNTY PROOF" in result.stdout
