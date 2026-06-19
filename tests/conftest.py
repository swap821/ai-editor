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
_DEFAULT_SCRATCH_ROOT = Path(__file__).resolve().parents[1] / ".aios" / "tmp" / "pytest-root"
_PYTEST_SESSION_ROOT = Path(
    os.environ.get(
        "PYTEST_DEBUG_TEMPROOT",
        _DEFAULT_SCRATCH_ROOT / f"pytest-session-{uuid4().hex}",
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
_TEST_DATA_DIR_PATH = _TEST_TMP_ROOT / f"aios-test-data-{uuid4().hex}"
_TEST_DATA_DIR_PATH.mkdir(parents=True, exist_ok=False)
os.environ["AIOS_DATA_DIR"] = str(_TEST_DATA_DIR_PATH)

# Best-effort cleanup at interpreter exit (the OS would reclaim the temp dir
# anyway, but tidy up so repeated local runs don't accumulate scratch dirs).
atexit.register(shutil.rmtree, _TEST_DATA_DIR_PATH, ignore_errors=True)
atexit.register(shutil.rmtree, _PYTEST_SESSION_ROOT, ignore_errors=True)
