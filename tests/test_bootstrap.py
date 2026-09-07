"""Tests for ``aios.bootstrap`` health-check module."""

from __future__ import annotations

import os
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from aios import __version__
from aios.api.main import app
from aios.bootstrap import (
    BootstrapCheck,
    BootstrapResult,
    _check_data_dir,
    _check_env_file,
    _check_ollama,
    _check_package_imports,
    _check_python_version,
    _check_token_length,
    default_env_contents,
    run_bootstrap,
    write_env_template,
)

#: The repository root, for the installer files these tests read as text.
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestIndividualChecks:
    def test_python_version(self):
        result = _check_python_version()
        assert result.name == "python_version"
        assert result.passed is (sys.version_info >= (3, 11))
        assert result.required is True

    def test_data_dir_passes(self, tmp_path: Path):
        result = _check_data_dir(tmp_path / "data")
        assert result.passed is True
        assert "writable" in result.message

    def test_data_dir_fails_when_not_writable(self, tmp_path: Path):
        # A file with the same name blocks directory creation.
        probe = tmp_path / "blocked"
        probe.write_text("")
        result = _check_data_dir(probe / "data")
        assert result.passed is False

    def test_env_file_passes_when_present(self, tmp_path: Path):
        (tmp_path / ".env").write_text("AIOS_API_TOKEN=x\n")
        result = _check_env_file(tmp_path)
        assert result.passed is True

    def test_env_file_passes_with_env_vars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        (tmp_path / ".env").unlink(missing_ok=True)
        monkeypatch.setenv("AIOS_API_TOKEN", "x")
        monkeypatch.setenv("AIOS_DATA_DIR", "/tmp/aios")
        result = _check_env_file(tmp_path)
        assert result.passed is True

    def test_env_file_fails_when_missing_and_no_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        (tmp_path / ".env").unlink(missing_ok=True)
        monkeypatch.delenv("AIOS_API_TOKEN", raising=False)
        monkeypatch.delenv("AIOS_DATA_DIR", raising=False)
        result = _check_env_file(tmp_path)
        assert result.passed is False

    def test_token_length_loopback_advisory(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AIOS_API_HOST", "127.0.0.1")
        monkeypatch.setenv("AIOS_API_TOKEN", "short")
        result = _check_token_length()
        assert result.passed is True
        assert result.required is False

    def test_token_length_non_loopback_requires_32(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("AIOS_API_HOST", "0.0.0.0")
        monkeypatch.setenv("AIOS_API_TOKEN", "short")
        result = _check_token_length()
        assert result.passed is False
        assert result.required is True

    def test_token_length_non_loopback_passes_with_long_token(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("AIOS_API_HOST", "0.0.0.0")
        monkeypatch.setenv("AIOS_API_TOKEN", "x" * 32)
        result = _check_token_length()
        assert result.passed is True

    @patch("aios.bootstrap.socket.create_connection")
    @patch("aios.bootstrap.urllib.request.urlopen")
    def test_ollama_reachable(
        self, mock_urlopen, mock_connect, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("AIOS_BOOTSTRAP_SKIP_OLLAMA", raising=False)
        mock_connect.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        result = _check_ollama()
        assert result.passed is True

    @patch("aios.bootstrap.socket.create_connection", side_effect=OSError("refused"))
    def test_ollama_unreachable(self, mock_connect, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("AIOS_BOOTSTRAP_SKIP_OLLAMA", raising=False)
        result = _check_ollama()
        assert result.passed is False
        assert "refused" in result.message

    def test_ollama_skipped(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AIOS_BOOTSTRAP_SKIP_OLLAMA", "1")
        result = _check_ollama()
        assert result.passed is True
        assert "skipped" in result.message

    @patch(
        "aios.bootstrap.importlib.util.find_spec",
        side_effect=lambda name: None if name == "fastapi" else MagicMock(),
    )
    def test_package_imports_fails_when_missing(self, mock_find_spec):
        result = _check_package_imports()
        assert result.passed is False
        assert "fastapi" in result.message

    @patch("aios.bootstrap.importlib.util.find_spec", return_value=MagicMock())
    def test_package_imports_passes(self, mock_find_spec):
        result = _check_package_imports()
        assert result.passed is True


class TestRunBootstrap:
    def test_run_bootstrap_ok(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        project_root = tmp_path / "project"
        data_dir = tmp_path / "data"
        project_root.mkdir()
        (project_root / ".env").write_text("AIOS_API_TOKEN=" + "x" * 32 + "\n")
        monkeypatch.setenv("AIOS_API_HOST", "127.0.0.1")
        monkeypatch.setenv(
            "AIOS_OLLAMA_URL", "http://127.0.0.1:9"
        )  # unreachable port is fine if skipped
        monkeypatch.setenv("AIOS_BOOTSTRAP_SKIP_OLLAMA", "1")

        result = run_bootstrap(project_root=project_root, data_dir=data_dir)
        assert isinstance(result, BootstrapResult)
        assert result.ok is True
        assert any(c.name == "python_version" for c in result.checks)
        assert __version__ in result.summary

    def test_run_bootstrap_fails_when_env_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "project"
        data_dir = tmp_path / "data"
        project_root.mkdir()
        monkeypatch.delenv("AIOS_API_TOKEN", raising=False)
        monkeypatch.delenv("AIOS_DATA_DIR", raising=False)
        monkeypatch.setenv("AIOS_BOOTSTRAP_SKIP_OLLAMA", "1")
        result = run_bootstrap(project_root=project_root, data_dir=data_dir)
        assert result.ok is False
        env_check = next(c for c in result.checks if c.name == "env_file")
        assert env_check.passed is False

    def test_run_bootstrap_reports_non_blocking_ollama_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        project_root = tmp_path / "project"
        data_dir = tmp_path / "data"
        project_root.mkdir()
        (project_root / ".env").write_text("AIOS_API_TOKEN=" + "x" * 32 + "\n")
        monkeypatch.setenv("AIOS_API_HOST", "127.0.0.1")
        monkeypatch.delenv("AIOS_BOOTSTRAP_SKIP_OLLAMA", raising=False)
        result = run_bootstrap(project_root=project_root, data_dir=data_dir)
        ollama_check = next(c for c in result.checks if c.name == "ollama_reachable")
        assert ollama_check.required is False


class TestEnvTemplate:
    def test_default_env_contents(self):
        text = default_env_contents()
        assert "AIOS_API_HOST=127.0.0.1" in text
        assert "AIOS_DATA_DIR=./data" in text
        assert "change-me" in text

    def test_write_env_template_creates_file(self, tmp_path: Path):
        env_path = tmp_path / ".env"
        assert write_env_template(env_path) is True
        assert env_path.exists()

    def test_write_env_template_refuses_overwrite(self, tmp_path: Path):
        env_path = tmp_path / ".env"
        env_path.write_text("existing")
        assert write_env_template(env_path) is False


class TestBootstrapEndpoint:
    def test_bootstrap_status_endpoint(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AIOS_BOOTSTRAP_SKIP_OLLAMA", "1")
        monkeypatch.setenv("AIOS_API_HOST", "127.0.0.1")
        monkeypatch.setenv("AIOS_API_TOKEN", "x" * 32)
        monkeypatch.setenv("AIOS_DATA_DIR", "/tmp/aios-bootstrap-ci")
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            response = client.get("/api/v1/system/bootstrap")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert __version__ in payload["summary"]
        assert any(c["name"] == "python_version" for c in payload["checks"])


# --------------------------------------------------------------------------- #
# What a stranger gets: the four defects the 2026-09-07 clean box exposed
# --------------------------------------------------------------------------- #


def test_the_env_template_carries_a_real_verification_key(tmp_path) -> None:
    """The README calls this the one genuinely required setting.

    The template omitted it, so a newcomer running the installer got a `.env`
    that could not run -- and cohort 27 died on exactly this absence. A
    placeholder would be no better than nothing, so assert a real 32-byte value.
    """
    from aios.bootstrap import write_env_template

    target = tmp_path / ".env"
    write_env_template(target)
    line = next(
        ln
        for ln in target.read_text(encoding="utf-8").splitlines()
        if ln.startswith("AIOS_VERIFICATION_AUTHORITY_KEY=")
    )
    value = line.partition("=")[2].strip()

    assert len(value) == 64, f"not a 32-byte hex key: {value!r}"
    int(value, 16)  # raises unless it is actually hex


def test_two_installs_do_not_share_a_key(tmp_path) -> None:
    """Generated per install, never a constant baked into the repo.

    A fixed key in the template would be a published secret the moment it
    landed, and every deployment would share it (SS VII.4).
    """
    from aios.bootstrap import write_env_template

    def key_of(name):
        p = tmp_path / name
        write_env_template(p)
        return next(
            ln
            for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.startswith("AIOS_VERIFICATION_AUTHORITY_KEY=")
        )

    assert key_of("a.env") != key_of("b.env")


def test_the_import_check_covers_multipart() -> None:
    """The dependency whose absence actually broke a fresh clone.

    FastAPI needs `python-multipart` at IMPORT time to build the route table, so
    without it the backend died before serving anything -- while `bootstrap`
    reported every required package importable, because the list was
    hand-maintained and nobody had added it.
    """
    from aios.bootstrap import _import_names

    assert "multipart" in _import_names()


def test_the_import_list_is_derived_from_the_manifest() -> None:
    """Not a list that can fall behind pyproject.toml.

    This is the same failure mode as release-authority's hand-maintained format
    list: coverage depends on memory. Assert the derivation reaches a
    representative spread, including the three whose import name differs from
    the distribution name, so a regression to hand-listing fails here.
    """
    from aios.bootstrap import _declared_dependencies, _import_names

    declared = _declared_dependencies(PROJECT_ROOT)
    assert "python-multipart" in declared
    assert "fastapi" in declared

    names = _import_names()
    for expected in ("fastapi", "multipart", "sklearn", "faiss", "bs4", "git"):
        assert expected in names, f"{expected} not derived"

    # torch and sentence-transformers import multi-second CUDA/BLAS stacks and
    # are deliberately skipped; probing them would make bootstrap slow enough
    # that people skip it, which is worse than the coverage it buys.
    assert "torch" not in names


def test_a_missing_dependency_makes_bootstrap_fail(monkeypatch) -> None:
    """The check must be shown CATCHING something, not merely existing.

    A check that has never failed is indistinguishable from one that cannot.
    Masked at `find_spec`, which is where `_check_package_imports` actually
    looks -- an uninstalled distribution has no spec to find.
    """
    import importlib.util

    from aios import bootstrap

    real_find_spec = importlib.util.find_spec

    def blind_to_multipart(name, *args, **kwargs):
        if name == "multipart":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(bootstrap.importlib.util, "find_spec", blind_to_multipart)

    result = bootstrap._check_package_imports()

    assert result.passed is False
    assert "multipart" in result.message


def test_shell_scripts_are_pinned_to_lf() -> None:
    """A CRLF shebang is fatal on the platform the installer exists to serve.

    `core.autocrlf=true` gives a Windows contributor CRLF in the working tree.
    One committed that way is `/usr/bin/env: 'bash\r': No such file or
    directory` on Linux -- measured 2026-09-07 in a clean Fedora container,
    before pip ever ran.
    """
    attrs = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "*.sh text eol=lf" in attrs


def test_the_installers_share_one_env_template() -> None:
    """install.ps1 used to keep its own copy, and that copy lacked the key.

    Two templates drift; one cannot. Assert the PowerShell installer delegates
    rather than restating the contents.
    """
    ps1 = (PROJECT_ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "write_env_template" in ps1, "install.ps1 no longer shares the template"
    assert "AIOS_API_HOST" not in ps1, "install.ps1 is restating the template again"
