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
import os
import shutil
import tempfile

# Set BEFORE importing anything from aios so config picks up the temp location.
_TEST_DATA_DIR = tempfile.mkdtemp(prefix="aios-test-data-")
os.environ["AIOS_DATA_DIR"] = _TEST_DATA_DIR

# Best-effort cleanup at interpreter exit (the OS would reclaim the temp dir
# anyway, but tidy up so repeated local runs don't accumulate scratch dirs).
atexit.register(shutil.rmtree, _TEST_DATA_DIR, ignore_errors=True)
