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

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile"
EXECUTOR_DOCKERFILE = REPO_ROOT / "Dockerfile.executor"
FRONTEND_DOCKERFILE = REPO_ROOT / "Dockerfile.frontend"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PYTHON_VERSION_FILE = REPO_ROOT / ".python-version"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
GATEWAY_NGINX_TEMPLATE = REPO_ROOT / "gateway" / "nginx.conf.template"


def _dockerfile_lines() -> list[str]:
    return DOCKERFILE.read_text(encoding="utf-8").splitlines()


def _load_compose() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


def test_dockerignore_excludes_local_locked_control_artifacts() -> None:
    """Docker builds must not archive mutable local agent/IDE directories.

    These directories are not runtime inputs and can be held open by the local
    coordination tooling. Including them makes the Windows Docker context
    nondeterministic and can prevent the production image from building at all.
    """
    entries = {
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    missing = {".swarm", ".vscode", "GAG demo"} - entries
    assert not missing, (
        f"Docker context includes locked local artifacts: {sorted(missing)}"
    )


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


def test_executor_image_uses_minimal_runtime_closure() -> None:
    """The Docker-socket owner must not install the full ML control plane."""
    text = EXECUTOR_DOCKERFILE.read_text(encoding="utf-8")
    assert "requirements-executor.txt" in text
    assert "requirements.txt" not in text
    assert "COPY aios /app/aios" in text
    assert "COPY . /app" not in text
    assert "docker.io docker-cli" in text
    assert "git docker.io" not in text


def test_executor_image_prepares_non_root_data_directory() -> None:
    text = EXECUTOR_DOCKERFILE.read_text(encoding="utf-8")
    assert "mkdir -p /app/data" in text
    assert re.search(r"chown\s+-R\s+65534:65534\s+/app", text)


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


def test_only_private_executor_service_receives_docker_socket() -> None:
    services = _load_compose()["services"]
    aios_volumes = "\n".join(str(item) for item in services["aios"].get("volumes", []))
    executor_volumes = "\n".join(
        str(item) for item in services["executor"].get("volumes", [])
    )
    assert "docker.sock" not in aios_volumes
    assert "docker.sock" in executor_volumes
    executor_environment = "\n".join(
        str(item) for item in services["executor"].get("environment", [])
    )
    assert "AIOS_EXECUTOR_DAEMON_WORKSPACE_ROOT" in executor_environment
    assert "AIOS_EXECUTOR_HOST_WORKSPACE_ROOT" in executor_volumes
    assert services["executor"]["image"] == "aios-executor:local"
    assert services["aios"]["depends_on"]["executor"]["condition"] == "service_healthy"


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


# ---------------------------------------------------------------------------
# 4. The packaged gateway forwards the API bearer the backend requires
# ---------------------------------------------------------------------------
#
# docker-compose.yml's own header comment says AIOS_API_TOKEN is required
# (the aios service binds 0.0.0.0). Browser JavaScript never holds this
# token by design (frontend/src/superbrain/lib/aiosAdapter.ts's authHeaders()
# always returns {}), so the gateway -- the only process that both
# terminates the browser connection and can hold the real secret -- must be
# the one to inject it into every proxied /api/ request. Without this, a
# real AIOS_API_TOKEN 401s every single request through the packaged
# topology (aios/interfaces/http/edge_security.py's check_bearer_token()).


def test_gateway_service_receives_the_api_token() -> None:
    compose = _load_compose()
    gateway_environment = "\n".join(
        str(item) for item in compose["services"]["gateway"].get("environment", [])
    )
    assert "AIOS_API_TOKEN" in gateway_environment, (
        "gateway service never receives AIOS_API_TOKEN -- it cannot forward "
        "a bearer it was never given"
    )


def test_frontend_dockerfile_templates_nginx_conf_instead_of_a_static_copy() -> None:
    """A static COPY to conf.d can never see the token at build time (it isn't
    set yet, and baking a real secret into an image layer would be worse
    anyway); the config must be rendered from the container's own runtime
    environment via nginx's standard envsubst templating mechanism."""
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "/etc/nginx/templates/" in text, (
        "nginx config is not installed as a template -- ${AIOS_API_TOKEN} "
        "can never be substituted at container startup"
    )
    assert "conf.d/default.conf\n" not in text and "conf.d/default.conf " not in text


def test_gateway_nginx_template_forwards_authorization_header_to_the_api() -> None:
    text = GATEWAY_NGINX_TEMPLATE.read_text(encoding="utf-8")
    api_block_match = re.search(r"location /api/ \{(.*?)\n    \}", text, re.DOTALL)
    assert api_block_match, "could not find the /api/ location block"
    api_block = api_block_match.group(1)
    assert "proxy_set_header Authorization" in api_block, (
        "the /api/ location block never sets an Authorization header -- the "
        "backend's required bearer is never forwarded"
    )
    assert "${AIOS_API_TOKEN}" in api_block


def test_gateway_nginx_template_renders_the_real_bearer_via_envsubst() -> None:
    """Exercises the exact mechanism the official nginx image's own
    docker-entrypoint.d/20-envsubst-on-templates.sh uses: envsubst scoped to
    only the container's currently-defined environment variable names, so
    nginx's own runtime variables ($scheme, $remote_addr, ...) are never
    touched. This is real, live verification of the substitution itself --
    not of the running container, since no Docker daemon is available in
    this environment."""
    if shutil.which("envsubst") is None:
        pytest.skip("envsubst is not installed in this environment")

    token = "test-token-01234567890123456789012345"
    env = dict(os.environ)
    env["AIOS_API_TOKEN"] = token
    defined_envs = " ".join(f"${{{name}}}" for name in env)
    rendered = subprocess.run(
        ["envsubst", defined_envs],
        input=GATEWAY_NGINX_TEMPLATE.read_text(encoding="utf-8"),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    assert f'proxy_set_header Authorization "Bearer {token}";' in rendered
    # nginx's own runtime variables must survive untouched -- envsubst here
    # is scoped to exactly the container's defined env var names, none of
    # which are named "scheme" or "remote_addr".
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in rendered
    assert "proxy_set_header X-Real-IP $remote_addr;" in rendered
