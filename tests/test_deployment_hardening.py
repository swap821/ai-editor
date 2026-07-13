"""Deployment-hardening regression tests (Dockerfile / docker-compose / CI).

Guards the top-3 fixes picked from the 2026-07-05 deployment-hardening audit:

1. The main app's Docker image (``Dockerfile``, the internet-facing app --
   unlike ``Dockerfile.executor``'s already-sandboxed code-execution backend)
   must not run as root.
2. Every ``docker-compose.yml`` service must declare a restart policy, and the
   heavy ``aios`` service (torch/sentence-transformers/faiss-cpu) must declare
   resource limits so a runaway process can't take the whole host down.
3. CI must test the same Python interpreter the Dockerfile ships, pinned via a
   single ``.python-version`` source of truth (matters here specifically
   because the C-extension-heavy stack -- torch/faiss-cpu/numpy -- can behave
   differently across interpreter minor versions).
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PYTHON_VERSION_FILE = REPO_ROOT / ".python-version"


def _dockerfile_lines() -> list[str]:
    return DOCKERFILE.read_text(encoding="utf-8").splitlines()


def _load_compose() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. Non-root container user
# ---------------------------------------------------------------------------


def test_dockerfile_drops_root_before_cmd() -> None:
    """The internet-facing app image must run as a non-root user, mirroring
    ``Dockerfile.executor``'s ``USER 65534:65534`` (that one is a sandbox
    anyway; this one is the exposed app, so it matters more, not less)."""
    lines = _dockerfile_lines()
    user_lines = [ln for ln in lines if ln.strip().startswith("USER ")]
    assert user_lines, "Dockerfile has no USER directive - image runs as root"

    user_arg = user_lines[-1].split(maxsplit=1)[1].strip()
    assert user_arg not in ("root", "0", "0:0"), (
        f"USER directive still resolves to root: {user_arg!r}"
    )

    # USER must precede CMD/ENTRYPOINT, otherwise the runtime process never
    # actually drops privileges (a USER line after CMD is a dead no-op).
    user_idx = max(i for i, ln in enumerate(lines) if ln.strip().startswith("USER "))
    cmd_idx = next(
        i for i, ln in enumerate(lines) if ln.strip().startswith(("CMD", "ENTRYPOINT"))
    )
    assert user_idx < cmd_idx, "USER directive must precede CMD/ENTRYPOINT"


def test_dockerfile_app_directory_writable_by_non_root_user() -> None:
    """``/app`` (and the ``AIOS_DATA_DIR=/app/data`` mount point under it) must
    be owned by the non-root user, or the process can't write its own data
    once privileges are dropped."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"\bchown\b", text), (
        "Dockerfile drops root but never chowns /app for the new user"
    )


# ---------------------------------------------------------------------------
# 2. Restart policy + resource limits in docker-compose.yml
# ---------------------------------------------------------------------------


def test_all_compose_services_have_restart_policy() -> None:
    compose = _load_compose()
    services = compose["services"]
    missing = [name for name, svc in services.items() if "restart" not in svc]
    assert not missing, f"Services missing a restart policy: {missing}"
    for name, svc in services.items():
        assert svc["restart"] in ("unless-stopped", "always", "on-failure"), (
            f"Service {name!r} has an unrecognised restart policy: {svc['restart']!r}"
        )


def test_aios_service_has_memory_and_cpu_limits() -> None:
    """The ``aios`` service loads torch/sentence-transformers/faiss-cpu; an
    unbounded process can take down the whole host on OOM."""
    compose = _load_compose()
    aios = compose["services"]["aios"]

    has_top_level_limits = "mem_limit" in aios and "cpus" in aios
    has_deploy_limits = (
        "deploy" in aios
        and "resources" in aios["deploy"]
        and "limits" in aios["deploy"]["resources"]
        and "memory" in aios["deploy"]["resources"]["limits"]
    )
    assert has_top_level_limits or has_deploy_limits, (
        "aios service declares no memory/CPU resource limits"
    )


# ---------------------------------------------------------------------------
# 3. CI Python version matches the Dockerfile
# ---------------------------------------------------------------------------


def test_ci_python_version_matches_dockerfile_and_pin_file() -> None:
    """CI must validate the same interpreter minor version the container
    ships, and both must agree with a single ``.python-version`` pin."""
    dockerfile_text = DOCKERFILE.read_text(encoding="utf-8")
    match = re.search(r"FROM python:(\d+\.\d+)", dockerfile_text)
    assert match, "Could not find a `FROM python:X.Y...` line in Dockerfile"
    dockerfile_version = match.group(1)

    ci = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    setup_python_step = next(
        step
        for job in ci["jobs"].values()
        for step in job.get("steps", [])
        if step.get("uses", "").startswith("actions/setup-python")
    )
    ci_version = str(setup_python_step["with"]["python-version"])

    assert ci_version == dockerfile_version, (
        f"CI tests Python {ci_version} but Dockerfile ships {dockerfile_version} - "
        "the coverage-gated test suite never runs on the interpreter that ships to prod"
    )

    assert PYTHON_VERSION_FILE.exists(), ".python-version pin file is missing"
    pinned = PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip()
    assert pinned.startswith(dockerfile_version), (
        f".python-version ({pinned!r}) does not match Dockerfile ({dockerfile_version!r})"
    )
