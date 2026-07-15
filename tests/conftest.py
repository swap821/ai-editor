"""Session-wide test isolation.

CRITICAL ORDERING: pytest imports this file BEFORE any test module, and therefore
before ``aios.config`` is first imported (config is only pulled in by the test
modules). We exploit that ordering to point the whole test session at a throwaway
``AIOS_DATA_DIR`` *before* config derives its paths — so tests never read or write
the real ``data/`` (the SQLite memory/audit DBs and the FAISS index).

``aios.config`` reads ``AIOS_DATA_DIR`` via ``_env_path`` at import time and
derives ``DATA_DIR`` and, from it, ``MEMORY_DB_PATH`` / ``AUDIT_DB_PATH`` /
``FAISS_INDEX_PATH`` / ``ROLLBACK_DIR``. Setting the env var here thus isolates the
entire run to a fresh temp directory with an empty index — which also makes the
old per-test ``hybrid_search`` stub unnecessary: ``hybrid_search`` short-circuits
to ``[]`` on an empty index without ever loading the embedding model.

Nothing from ``aios`` may be imported above this assignment, or config would bind
to the real ``data/`` first.
"""
from __future__ import annotations

import atexit
import getpass
import os
import shutil
from pathlib import Path
from uuid import uuid4
import _pytest.pathlib as pytest_pathlib

# Patch TestClient to always include a local Origin so mutation protection allows it
from fastapi.testclient import TestClient
_original_testclient_init = TestClient.__init__
_original_testclient_request = TestClient.request
_TEST_OPERATOR_CREDENTIAL = None


def _router_contains_path(route, target: str) -> bool:
    """Find a path through FastAPI's eager and lazy included-router wrappers."""
    if getattr(route, "path", "") == target:
        return True
    original = getattr(route, "original_router", None)
    if original is not None:
        return any(_router_contains_path(child, target) for child in original.routes)
    return False


def _patched_testclient_init(self, *args, **kwargs):
    _original_testclient_init(self, *args, **kwargs)
    if "Origin" not in self.headers:
        self.headers["Origin"] = "http://localhost:5173"
    if "Host" not in self.headers:
        self.headers["Host"] = "localhost:8000"
    # Browser mutation tests need the same session-bound proof as the real UI.
    # Bootstrap only loopback clients for the main API app; remote-client and
    # non-API tests must retain their unauthenticated behavior.
    client_addr = kwargs.get("client")
    app_instance = args[0] if args else kwargs.get("app")
    has_session_route = bool(
        app_instance
        and any(
            _router_contains_path(route, "/api/v1/auth/session")
            for route in app_instance.routes
        )
    )
    if has_session_route and client_addr and client_addr[0] in {"127.0.0.1", "::1"}:
        # Endpoint-rate-limit buckets are process-wide policy state. Reset them
        # at the test-client boundary so one test cannot make a later
        # authorization assertion observe a synthetic 429.
        from aios.api.main import _RATE_LIMIT_HITS

        _RATE_LIMIT_HITS.clear()
        # Seed an explicitly authenticated Human Sovereign session without
        # spending the API's endpoint-rate-limit bucket during TestClient setup.
        # Tests that need an anonymous-but-valid session call /auth/session or
        # clear the cookie explicitly; the default fixture must not impersonate
        # operator authority with a bare session id.
        from aios.api.deps import get_identity_service

        global _TEST_OPERATOR_CREDENTIAL
        identity = get_identity_service()
        if not identity.is_enrolled():
            enrollment = identity.enroll_operator(display_name="Test Human Sovereign")
            _TEST_OPERATOR_CREDENTIAL = enrollment.enrollment_credential
        if not _TEST_OPERATOR_CREDENTIAL:
            raise RuntimeError("test operator credential was not initialized")
        authenticated = identity.authenticate_credential(_TEST_OPERATOR_CREDENTIAL)
        # Privileged route fixtures model the real UI flow: credential login
        # establishes identity, then a fresh re-authentication event upgrades
        # the rotated session before any control-plane mutation is exercised.
        authenticated = identity.reauthenticate(
            authenticated.session_cookie, _TEST_OPERATOR_CREDENTIAL
        )
        csrf_token = identity.sessions.ensure_csrf_token(authenticated.session_cookie)
        self.cookies.set("session_id", authenticated.session_cookie)
        self.cookies.set("csrf_token", csrf_token)
TestClient.__init__ = _patched_testclient_init


def _capability_aware_request(self, method, url, **kwargs):
    """Exercise the real two-request YELLOW protocol in legacy API tests.

    Ordinary historical tests predate exact capabilities and issue one request
    to a YELLOW route.  The production boundary now returns an opaque token
    without invoking the handler.  Automatically retry the identical request
    with that server-issued token so those tests continue to assert the route's
    application behavior; new adversarial tests can set
    ``X-AIOS-No-Auto-Capability: 1`` to inspect the challenge itself.
    """
    response = _original_testclient_request(self, method, url, **kwargs)
    if response.status_code != 428:
        return response
    headers = dict(kwargs.get("headers") or {})
    if headers.get("X-AIOS-No-Auto-Capability") == "1":
        return response
    try:
        detail = response.json().get("detail", {})
        token = detail.get("approvalToken")
    except (AttributeError, ValueError):
        token = None
    if not token:
        return response
    headers["X-AIOS-Capability"] = token
    headers.pop("X-AIOS-No-Auto-Capability", None)
    retry_kwargs = dict(kwargs)
    retry_kwargs["headers"] = headers
    return _original_testclient_request(self, method, url, **retry_kwargs)


TestClient.request = _capability_aware_request

if os.name == "nt":
    _original_make_numbered_dir = pytest_pathlib.make_numbered_dir

    def _sandbox_make_numbered_dir(root: Path, prefix: str, mode: int = 0o700) -> Path:
        # Pytest's default 0o700 temp dirs reject creating the per-dir .lock file
        # under this Windows sandbox. Use a writable directory mode instead.
        return _original_make_numbered_dir(root, prefix, mode=0o777)

    pytest_pathlib.make_numbered_dir = _sandbox_make_numbered_dir

# Keep pytest's own numbered tmp root on a writable scratch path. With no
# explicit --basetemp, pytest reads PYTEST_DEBUG_TEMPROOT lazily when tmp_path
# is first used, so setting it here is early enough for the session.
#
# Session/data dir suffixes use only 8 hex chars (not a full 32-char uuid4().hex)
# to leave headroom under Windows' 260-char MAX_PATH: this root gets nested under
# pytest-of-<user>/pytest-N/<test-name>/... plus per-test subdirs (mission/worker/
# git-repo trees), and a git worktree checkout adds its own long prefix on top of
# the repo root. 8 hex chars (~4e9 values) is still effectively collision-free for
# a single machine's concurrent local runs.
_DEFAULT_SCRATCH_ROOT = Path(__file__).resolve().parents[1] / ".aios" / "tmp" / "pytest-root"
_PYTEST_SESSION_ROOT = Path(
    os.environ.get(
        "PYTEST_DEBUG_TEMPROOT",
        _DEFAULT_SCRATCH_ROOT / f"pytest-session-{uuid4().hex[:8]}",
    )
)
_PYTEST_SESSION_ROOT.mkdir(parents=True, exist_ok=True)
_PYTEST_USER_ROOT = _PYTEST_SESSION_ROOT / f"pytest-of-{getpass.getuser() or 'unknown'}"
_PYTEST_USER_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["PYTEST_DEBUG_TEMPROOT"] = str(_PYTEST_SESSION_ROOT)

# Set BEFORE importing anything from aios so config picks up the temp location.
# Use the repo's ignored scratch area by default so the suite does not depend on
# the host OS temp directory being writable (sandboxed runs often block it).
_TEST_TMP_ROOT = Path(
    os.environ.get(
        "AIOS_TEST_TMP_ROOT",
        _PYTEST_SESSION_ROOT / "aios-test-data",
    )
)
_TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
_TEST_DATA_DIR_PATH = _TEST_TMP_ROOT / f"aios-test-data-{uuid4().hex[:8]}"
_TEST_DATA_DIR_PATH.mkdir(parents=True, exist_ok=False)
os.environ["AIOS_DATA_DIR"] = str(_TEST_DATA_DIR_PATH)

# Point COUNCIL_RUNTIME_DIR at the session root so _safe_resolve's containment
# check (startswith) passes for every test's tmp_path — which is always a child
# of _PYTEST_SESSION_ROOT.  Set as env var (not monkeypatch) so subprocess workers
# spawned by the council runtime inherit it automatically.
os.environ["AIOS_COUNCIL_RUNTIME_DIR"] = str(_PYTEST_SESSION_ROOT)

# Best-effort cleanup at interpreter exit (the OS would reclaim the temp dir
# anyway, but tidy up so repeated local runs don't accumulate scratch dirs).
atexit.register(shutil.rmtree, _TEST_DATA_DIR_PATH, ignore_errors=True)
atexit.register(shutil.rmtree, _PYTEST_SESSION_ROOT, ignore_errors=True)
