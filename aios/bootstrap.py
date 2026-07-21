"""Bootstrap health checks for a fresh GAGOS install.

This module is intentionally free of heavy runtime side effects: it imports
metadata and does lightweight filesystem / socket probes, but it never loads
models, writes secrets, or mutates the working tree except for an explicit
CLI ``--create-env`` flag that writes a *template* ``.env``.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import platform
import socket
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from aios import __version__
from aios.config import DATA_DIR, PROJECT_ROOT

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BootstrapCheck:
    """A single deterministic bootstrap check."""

    name: str
    passed: bool
    message: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """Aggregated result of all bootstrap checks."""

    ok: bool
    checks: list[BootstrapCheck] = field(default_factory=list)
    summary: str = ""


def _as_bool(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


def _check_python_version() -> BootstrapCheck:
    major, minor, *_ = platform.python_version_tuple()
    ok = sys.version_info >= (3, 11)
    return BootstrapCheck(
        name="python_version",
        passed=ok,
        message=f"Python {major}.{minor}.{platform.python_version_tuple()[2]}"
        + (" >= 3.11" if ok else " < 3.11 (upgrade required)"),
        required=True,
    )


def _check_data_dir(data_dir: Path = DATA_DIR) -> BootstrapCheck:
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".bootstrap_write_probe"
        probe.write_text("")
        probe.unlink()
    except OSError as exc:  # pragma: no cover - exercised by test with bad path
        return BootstrapCheck(
            name="data_dir",
            passed=False,
            message=f"Data directory {data_dir} is not writable: {exc}",
            required=True,
        )
    return BootstrapCheck(
        name="data_dir",
        passed=True,
        message=f"Data directory {data_dir} exists and is writable",
        required=True,
    )


def _check_env_file(project_root: Path = PROJECT_ROOT) -> BootstrapCheck:
    env_path = project_root / ".env"
    if env_path.exists():
        return BootstrapCheck(
            name="env_file",
            passed=True,
            message=f"Environment file {env_path} exists",
            required=True,
        )
    # Without .env, verify that critical runtime vars are already in the environment.
    token = os.getenv("AIOS_API_TOKEN")
    data_dir_env = os.getenv("AIOS_DATA_DIR")
    if token and data_dir_env:
        return BootstrapCheck(
            name="env_file",
            passed=True,
            message="No .env file, but AIOS_API_TOKEN and AIOS_DATA_DIR are set",
            required=True,
        )
    return BootstrapCheck(
        name="env_file",
        passed=False,
        message=f"No {env_path} found and AIOS_API_TOKEN/AIOS_DATA_DIR not both set",
        required=True,
    )


def _check_token_length() -> BootstrapCheck:
    host = os.getenv("AIOS_API_HOST", "127.0.0.1")
    token = os.getenv("AIOS_API_TOKEN", "")
    loopback = host.strip() in {"127.0.0.1", "localhost", "::1"}
    if loopback:
        return BootstrapCheck(
            name="token_length",
            passed=True,
            message=f"API binds to loopback ({host}); token length advisory only",
            required=False,
        )
    ok = len(token) >= 32
    return BootstrapCheck(
        name="token_length",
        passed=ok,
        message="API token is 32+ characters"
        if ok
        else f"API token is only {len(token)} characters (need >= 32 for non-loopback host {host})",
        required=True,
    )


def _check_ollama() -> BootstrapCheck:
    if os.getenv("AIOS_BOOTSTRAP_SKIP_OLLAMA", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return BootstrapCheck(
            name="ollama_reachable",
            passed=True,
            message="Ollama reachability check skipped (AIOS_BOOTSTRAP_SKIP_OLLAMA=1)",
            required=False,
        )

    url = os.getenv("AIOS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 11434

    # Fast path: TCP connect.
    try:
        with socket.create_connection((host, port), timeout=2.0):
            pass
    except OSError as exc:
        return BootstrapCheck(
            name="ollama_reachable",
            passed=False,
            message=f"Ollama TCP {host}:{port} unreachable: {exc}",
            required=False,
        )

    # HTTP sanity check.
    try:
        req = urllib.request.Request(
            f"{url}/api/tags",
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            _ = resp.read(1)
        return BootstrapCheck(
            name="ollama_reachable",
            passed=True,
            message=f"Ollama responded at {url}/api/tags",
            required=False,
        )
    except urllib.error.URLError as exc:
        return BootstrapCheck(
            name="ollama_reachable",
            passed=False,
            message=f"Ollama TCP open but HTTP probe failed: {exc.reason}",
            required=False,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return BootstrapCheck(
            name="ollama_reachable",
            passed=False,
            message=f"Ollama probe error: {exc}",
            required=False,
        )


# Required for the backend to import successfully; subset of pyproject.toml deps.
_REQUIRED_PACKAGES: tuple[str, ...] = (
    "fastapi",
    "uvicorn",
    "pydantic",
    "structlog",
    "numpy",
    "requests",
    "httpx",
    "faiss",
    "sentence_transformers",
)


def _check_package_imports(
    packages: Iterable[str] = _REQUIRED_PACKAGES,
) -> BootstrapCheck:
    missing: list[str] = []
    for name in packages:
        spec = importlib.util.find_spec(name)
        if spec is None:
            missing.append(name)
    ok = not missing
    return BootstrapCheck(
        name="package_imports",
        passed=ok,
        message="All required packages importable"
        if ok
        else f"Missing packages: {', '.join(missing)}",
        required=True,
    )


def run_bootstrap(
    *,
    project_root: Path = PROJECT_ROOT,
    data_dir: Path = DATA_DIR,
) -> BootstrapResult:
    """Run the full bootstrap health check suite deterministically."""
    checks: list[BootstrapCheck] = [
        _check_python_version(),
        _check_data_dir(data_dir),
        _check_env_file(project_root),
        _check_token_length(),
        _check_ollama(),
        _check_package_imports(),
    ]
    required_pass = all(c.passed for c in checks if c.required)
    failures = [c for c in checks if not c.passed]
    summary = (
        f"GAGOS v{__version__} bootstrap {'passed' if required_pass else 'failed'}; "
        f"{sum(1 for c in checks if c.passed)}/{len(checks)} checks passed"
    )
    if not required_pass:
        summary += f" (blocking: {', '.join(c.name for c in failures if c.required)})"
    return BootstrapResult(ok=required_pass, checks=checks, summary=summary)


def default_env_contents() -> str:
    """Return a safe, commented ``.env`` template for operators."""
    return (
        "# GAGOS local-first AI Operating System environment template\n"
        "# Generated by `python -m aios bootstrap --create-env`\n"
        "\n"
        "# Host and port for the API server\n"
        "AIOS_API_HOST=127.0.0.1\n"
        "AIOS_API_PORT=8000\n"
        "\n"
        "# 32+ character token for non-loopback hosts (loopback is advisory only)\n"
        "AIOS_API_TOKEN=change-me-to-a-32-character-secret-if-not-on-localhost\n"
        "\n"
        "# Local data directory (memory, approvals, sessions, audit)\n"
        "AIOS_DATA_DIR=./data\n"
        "\n"
        "# Local LLM routing (Ollama)\n"
        "AIOS_OLLAMA_URL=http://127.0.0.1:11434\n"
        "AIOS_ROUTER_PREFER_LOCAL=true\n"
        "AIOS_ROUTER_CLOUD_TASKS=reasoning,coding\n"
        "\n"
        "# Optional: disable Ollama reachability probe during bootstrap\n"
        "# AIOS_BOOTSTRAP_SKIP_OLLAMA=false\n"
    )


def write_env_template(path: Path = PROJECT_ROOT / ".env") -> bool:
    """Write a commented ``.env`` template if one does not already exist."""
    if path.exists():
        _LOGGER.info("Refusing to overwrite existing %s", path)
        return False
    path.write_text(default_env_contents(), encoding="utf-8")
    return True
