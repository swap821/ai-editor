"""P3-5: shared probe helpers — env-overridable BASE and sandbox allowlist."""
from __future__ import annotations

import re

import pytest

from aios import probe_common
from aios.config import PROBE_BASE


class TestProbeBase:
    """``AIOS_PROBE_BASE`` is the single source of truth for probe URLs."""

    def test_default_points_to_loopback_dev_server(self):
        assert PROBE_BASE == "http://127.0.0.1:8000"
        assert probe_common.BASE == PROBE_BASE

    def test_env_override_changes_base(self, monkeypatch):
        monkeypatch.setenv("AIOS_PROBE_BASE", "http://localhost:9000")
        # Force re-import of config to pick up the new env var.
        import importlib

        from aios import config

        importlib.reload(config)
        assert config.PROBE_BASE == "http://localhost:9000"


class TestAllowedFileRe:
    """Only bare .py files directly inside training_ground/ or lab/ are writable."""

    @pytest.mark.parametrize(
        "path",
        [
            "training_ground/foo.py",
            "training_ground/foo-bar.py",
            "training_ground/foo_bar.py",
            "training_ground/foo.py",
        ],
    )
    def test_accepts_valid_training_ground_py(self, path):
        assert probe_common.ALLOWED_FILE_RE.match(path)

    @pytest.mark.parametrize(
        "path",
        [
            "training_ground/subdir/foo.py",
            "training_ground/foo.txt",
            "other/foo.py",
            "foo.py",
            "training_ground/.hidden.py",
            "training_ground/foo bar.py",
        ],
    )
    def test_rejects_non_conforming_paths(self, path):
        assert probe_common.ALLOWED_FILE_RE.match(path) is None

    @pytest.mark.parametrize(
        "path",
        [
            "lab/foo.py",
            "lab/foo-bar.py",
            "lab/foo_bar.py",
        ],
    )
    def test_accepts_valid_lab_py(self, path):
        assert probe_common.ALLOWED_FILE_RE.match(path)

    @pytest.mark.parametrize(
        "path",
        [
            "lab/subdir/foo.py",
            "lab/foo.txt",
            "lab/.hidden.py",
            "lab/foo bar.py",
        ],
    )
    def test_rejects_non_conforming_lab_paths(self, path):
        assert probe_common.ALLOWED_FILE_RE.match(path) is None


class TestAllowedCmdRe:
    """Only pytest on a single training_ground/ or lab/ .py file is runnable."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "pytest training_ground/foo.py",
            'pytest "training_ground/foo.py"',
            "pytest -q training_ground/foo.py",
            "python -m pytest training_ground/foo.py",
            "python -m pytest -q training_ground/foo.py",
            "pytest training_ground/foo.py -q",
            "pytest",
        ],
    )
    def test_accepts_valid_pytest_commands(self, cmd):
        assert probe_common.ALLOWED_CMD_RE.match(cmd)

    @pytest.mark.parametrize(
        "cmd",
        [
            "pip install foo",
            "python training_ground/foo.py",
            "pytest other/foo.py",
            "pytest training_ground/foo.txt",
            "pytest training_ground/subdir/foo.py",
            "bash -c 'rm -rf /'",
        ],
    )
    def test_rejects_non_pytest_or_outside_sandbox(self, cmd):
        assert probe_common.ALLOWED_CMD_RE.match(cmd) is None

    @pytest.mark.parametrize(
        "cmd",
        [
            "pytest lab/foo.py",
            'pytest "lab/foo.py"',
            "pytest -q lab/foo.py",
            "python -m pytest lab/foo.py",
            "python -m pytest -q lab/foo.py",
            "pytest lab/foo.py -q",
        ],
    )
    def test_accepts_valid_lab_pytest_commands(self, cmd):
        assert probe_common.ALLOWED_CMD_RE.match(cmd)

    @pytest.mark.parametrize(
        "cmd",
        [
            "python lab/foo.py",
            "pytest lab/foo.txt",
            "pytest lab/subdir/foo.py",
        ],
    )
    def test_rejects_non_pytest_or_outside_sandbox_lab(self, cmd):
        assert probe_common.ALLOWED_CMD_RE.match(cmd) is None
