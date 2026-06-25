# P2-3 memory forgetting / compaction — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an operator-triggered, audited "sleep" compaction sweep that safely forgets stale unverified chat, caps per-type semantic rows, enforces working-memory idle TTL, and leaves verified evidence untouched.

**Architecture:** A new `aios/memory/compaction.py` `MemoryCompactor` owns the sweep logic for all four layers (working, episodic, semantic, vector). It exposes `preview()` and `compact(dry_run=False)`. Configuration lives in `aios/config.py` as env-overridable tunables. A gated `POST /api/v1/memory/compact` endpoint in `aios/api/main.py` requires the operator bearer token, mandates a `dry_run` query flag for preview, and writes one audit entry per batch under actor `sleep-consolidation`.

**Tech Stack:** Python 3.12, SQLite, FAISS (`IndexIDMap.remove_ids`), FastAPI, existing `aios.security.audit_logger`.

---

## File map

- Modify: `aios/config.py` — add compaction env tunables.
- Modify: `aios/memory/embeddings.py` — add `VectorIndex.remove(ids)` and `VectorIndex.rebuild_without(ids)` for FAISS cleanup.
- Create: `aios/memory/compaction.py` — `MemoryCompactor` class.
- Modify: `aios/api/main.py` — add `POST /api/v1/memory/compact` endpoint.
- Create: `tests/test_memory_compaction.py` — unit tests.

---

## Task 1: Add compaction config to `aios/config.py`

**Files:**
- Modify: `aios/config.py`

- [ ] **Step 1: Insert new tunables**

After the retrieval weights block (around line 161), add:

```python
# --------------------------------------------------------------------------- #
# Memory compaction (audited "sleep") — operator-controlled forgetting.
# --------------------------------------------------------------------------- #
#: Unverified semantic chat rows older than this many days are eligible for
#: removal during compaction. Verified/superseded rows are never touched.
MEMORY_COMPACT_UNVERIFIED_CHAT_DAYS: Final[float] = _env_float(
    "AIOS_MEMORY_COMPACT_UNVERIFIED_CHAT_DAYS", 7.0
)
#: Episodic rows older than this many days are eligible for removal.
MEMORY_COMPACT_EPISODIC_DAYS: Final[float] = _env_float(
    "AIOS_MEMORY_COMPACT_EPISODIC_DAYS", 30.0
)
#: Per-type cap for active (non-superseded) semantic rows. Each memory_type is
#: capped independently, keeping the newest rows by last_seen_at/timestamp.
MEMORY_COMPACT_SEMANTIC_MAX_PER_TYPE: Final[int] = _env_int(
    "AIOS_MEMORY_COMPACT_SEMANTIC_MAX_PER_TYPE", 5_000
)
#: Working-memory sessions idle longer than this many minutes are dropped.
MEMORY_COMPACT_WORKING_IDLE_MINUTES: Final[int] = _env_int(
    "AIOS_MEMORY_COMPACT_WORKING_IDLE_MINUTES", 60
)
```

- [ ] **Step 2: Export the new names**

Add them to `__all__`:

```python
    "MEMORY_COMPACT_UNVERIFIED_CHAT_DAYS",
    "MEMORY_COMPACT_EPISODIC_DAYS",
    "MEMORY_COMPACT_SEMANTIC_MAX_PER_TYPE",
    "MEMORY_COMPACT_WORKING_IDLE_MINUTES",
```

- [ ] **Step 3: Compile check**

Run: `.venv/Scripts/python -m py_compile aios/config.py`
Expected: exit 0.

---

## Task 2: Add FAISS vector removal to `aios/memory/embeddings.py`

**Files:**
- Modify: `aios/memory/embeddings.py`

- [ ] **Step 1: Add `remove` method**

Insert after `VectorIndex.add`:

```python
    def remove(self, vector_ids: Sequence[int]) -> None:
        """Remove the vectors with the given integer ids from the index.

        Silently ignores ids that do not exist. No-op if the index is empty or
        *vector_ids* is empty.
        """
        if not vector_ids or self.size == 0:
            return
        ids = np.asarray(list({int(v) for v in vector_ids}), dtype="int64")
        with self._lock:
            self._index.remove_ids(ids)
```

- [ ] **Step 2: Add `rebuild_without` helper**

Insert after `remove`:

```python
    def rebuild_without(self, vector_ids: Sequence[int]) -> None:
        """Persist a fresh index that omits the given ids.

        This is a convenience wrapper for compaction callers: it removes the ids
        and flushes the index atomically.
        """
        self.remove(vector_ids)
        self.persist()
```

- [ ] **Step 3: Compile check**

Run: `.venv/Scripts/python -m py_compile aios/memory/embeddings.py`
Expected: exit 0.

---

## Task 3: Implement `aios/memory/compaction.py`

**Files:**
- Create: `aios/memory/compaction.py`

- [ ] **Step 1: Create module**

```python
"""Audited memory compaction (the "sleep" sweep): forgetting with reversibility.

A `MemoryCompactor` performs three independent sweeps, each gated by operator
config and each safe to run as a dry-run preview first:

1. Working memory: drop in-process sessions whose last activity is older than
   ``MEMORY_COMPACT_WORKING_IDLE_MINUTES``.
2. Episodic memory: delete rows older than ``MEMORY_COMPACT_EPISODIC_DAYS``.
3. Semantic memory: (a) delete unverified ``chat`` rows older than
   ``MEMORY_COMPACT_UNVERIFIED_CHAT_DAYS``; (b) cap each active memory_type to
   ``MEMORY_COMPACT_SEMANTIC_MAX_PER_TYPE``, keeping newest first. Verified and
   superseded rows are never deleted.

Every real (non-dry-run) compaction writes one audit entry under actor
``sleep-consolidation`` summarising the batch.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from aios import config
from aios.logging_config import get_logger
from aios.memory.db import get_connection, init_memory_db
from aios.memory.embeddings import VectorIndex
from aios.memory.episodic import EpisodicMemory
from aios.memory.semantic import SemanticMemory
from aios.memory.working import WorkingMemory
from aios.security.audit_logger import log_action
from aios.security.gateway import Zone

logger = get_logger(__name__)


@dataclass(frozen=True)
class CompactionPreview:
    """What a compaction sweep would remove, without touching storage."""

    working_sessions: list[str]
    working_sessions_count: int
    episodic_row_count: int
    semantic_chat_old_count: int
    semantic_per_type_cap_rows: dict[str, int]
    semantic_vector_ids_to_remove: list[int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "working_sessions": self.working_sessions,
            "working_sessions_count": self.working_sessions_count,
            "episodic_row_count": self.episodic_row_count,
            "semantic_chat_old_count": self.semantic_chat_old_count,
            "semantic_per_type_cap_rows": self.semantic_per_type_cap_rows,
            "semantic_vector_ids_to_remove": self.semantic_vector_ids_to_remove,
        }


class MemoryCompactor:
    """Operator-triggered memory forgetting with dry-run preview."""

    def __init__(
        self,
        db_path: Path = config.MEMORY_DB_PATH,
        audit_db_path: Path = config.AUDIT_DB_PATH,
        working: Optional[WorkingMemory] = None,
        semantic: Optional[SemanticMemory] = None,
        episodic: Optional[EpisodicMemory] = None,
        index: Optional[VectorIndex] = None,
        *,
        unverified_chat_days: float = config.MEMORY_COMPACT_UNVERIFIED_CHAT_DAYS,
        episodic_days: float = config.MEMORY_COMPACT_EPISODIC_DAYS,
        semantic_max_per_type: int = config.MEMORY_COMPACT_SEMANTIC_MAX_PER_TYPE,
        working_idle_minutes: int = config.MEMORY_COMPACT_WORKING_IDLE_MINUTES,
    ) -> None:
        self.db_path = db_path
        self.audit_db_path = audit_db_path
        self.working = working
        self.semantic = semantic
        self.episodic = episodic
        self.index = index
        self.unverified_chat_days = max(0.0, unverified_chat_days)
        self.episodic_days = max(0.0, episodic_days)
        self.semantic_max_per_type = max(0, semantic_max_per_type)
        self.working_idle_minutes = max(0, working_idle_minutes)
        self._working_last_seen: dict[str, float] = {}
        self._working_lock = threading.Lock()

    # --------------------------------------------------------------------- #
    # Working memory hooks
    # --------------------------------------------------------------------- #
    def touch_working_session(self, session_id: str) -> None:
        """Record latest activity so idle TTL can be computed."""
        with self._working_lock:
            self._working_last_seen[session_id] = time.monotonic()

    def _stale_working_sessions(self) -> list[str]:
        if self.working is None:
            return []
        cutoff = time.monotonic() - (self.working_idle_minutes * 60)
        with self._working_lock:
            return [
                sid
                for sid in self.working.sessions()
                if self._working_last_seen.get(sid, 0) < cutoff
            ]

    # --------------------------------------------------------------------- #
    # Episodic sweep
    # --------------------------------------------------------------------- #
    def _old_episodic_cutoff(self) -> str:
        dt = datetime.now(timezone.utc) - timedelta(days=self.episodic_days)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def _preview_episodic(self, conn: Any) -> int:
        if self.episodic_days <= 0:
            return 0
        cutoff = self._old_episodic_cutoff()
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM episodic_memory WHERE timestamp < ?",
            (cutoff,),
        ).fetchone()
        return int(row["n"])

    def _compact_episodic(self, conn: Any, dry_run: bool) -> int:
        count = self._preview_episodic(conn)
        if count and not dry_run:
            cutoff = self._old_episodic_cutoff()
            conn.execute(
                "DELETE FROM episodic_memory WHERE timestamp < ?", (cutoff,)
            )
        return count

    # --------------------------------------------------------------------- #
    # Semantic sweep
    # --------------------------------------------------------------------- #
    def _old_unverified_chat_ids(self, conn: Any) -> list[int]:
        if self.unverified_chat_days <= 0:
            return []
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=self.unverified_chat_days)
        ).strftime("%Y-%m-%d %H:%M:%S")
        rows = conn.execute(
            "SELECT id FROM semantic_memory "
            "WHERE memory_type = 'chat' AND verification_status = 'unverified' "
            "AND timestamp < ?",
            (cutoff,),
        ).fetchall()
        return [int(r["id"]) for r in rows]

    def _per_type_cap_ids(self, conn: Any) -> list[int]:
        if self.semantic_max_per_type <= 0:
            return []
        ids: list[int] = []
        for mem_type in ("chat", "lesson", "fact", "preference", "procedure"):
            rows = conn.execute(
                "SELECT id FROM semantic_memory "
                "WHERE memory_type = ? AND verification_status != 'superseded' "
                "ORDER BY COALESCE(last_seen_at, timestamp) DESC, id DESC "
                "LIMIT -1 OFFSET ?",
                (mem_type, self.semantic_max_per_type),
            ).fetchall()
            ids.extend(int(r["id"]) for r in rows)
        return ids

    def _preview_semantic(self, conn: Any) -> tuple[list[int], dict[str, int]]:
        old_chat = self._old_unverified_chat_ids(conn)
        cap_ids = self._per_type_cap_ids(conn)
        # Avoid double-counting ids that appear in both sets.
        all_ids = list(dict.fromkeys(old_chat + cap_ids))
        per_type: dict[str, int] = {}
        if self.semantic_max_per_type > 0:
            for mem_type in ("chat", "lesson", "fact", "preference", "procedure"):
                rows = conn.execute(
                    "SELECT COUNT(*) AS n FROM semantic_memory "
                    "WHERE memory_type = ? AND verification_status != 'superseded' "
                    "ORDER BY COALESCE(last_seen_at, timestamp) DESC, id DESC "
                    "LIMIT -1 OFFSET ?",
                    (mem_type, self.semantic_max_per_type),
                ).fetchall()
                per_type[mem_type] = int(rows[0]["n"])
        return all_ids, per_type

    def _compact_semantic(self, conn: Any, dry_run: bool) -> tuple[list[int], dict[str, int]]:
        ids, per_type = self._preview_semantic(conn)
        if ids and not dry_run:
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"DELETE FROM semantic_memory WHERE id IN ({placeholders})",
                tuple(ids),
            )
        return ids, per_type

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def preview(self) -> CompactionPreview:
        """Return what would be removed without mutating any store."""
        init_memory_db(self.db_path)
        working = self._stale_working_sessions()
        with get_connection(self.db_path) as conn:
            episodic = self._preview_episodic(conn)
            semantic_ids, per_type = self._preview_semantic(conn)
        return CompactionPreview(
            working_sessions=working,
            working_sessions_count=len(working),
            episodic_row_count=episodic,
            semantic_chat_old_count=len(self._old_unverified_chat_ids(conn)) if False else 0,
            semantic_per_type_cap_rows=per_type,
            semantic_vector_ids_to_remove=semantic_ids,
        )
```

Wait — `preview()` closes the connection before `_old_unverified_chat_ids` is called for the chat count. Fix the preview method to compute the chat-old count inside the connection block:

```python
    def preview(self) -> CompactionPreview:
        """Return what would be removed without mutating any store."""
        init_memory_db(self.db_path)
        working = self._stale_working_sessions()
        with get_connection(self.db_path) as conn:
            episodic = self._preview_episodic(conn)
            old_chat_ids = self._old_unverified_chat_ids(conn)
            semantic_ids, per_type = self._preview_semantic(conn)
        return CompactionPreview(
            working_sessions=working,
            working_sessions_count=len(working),
            episodic_row_count=episodic,
            semantic_chat_old_count=len(old_chat_ids),
            semantic_per_type_cap_rows=per_type,
            semantic_vector_ids_to_remove=semantic_ids,
        )
```

- [ ] **Step 2: Add `compact()` method**

Append to `MemoryCompactor`:

```python
    def compact(self, dry_run: bool = True) -> dict[str, Any]:
        """Run the compaction sweep.

        Args:
            dry_run: When True (the safe default), report what would change but
                do not mutate durable stores.

        Returns:
            A dict summarising the sweep, including the same keys a caller would
            use for preview plus the ``dry_run`` flag.
        """
        init_memory_db(self.db_path)
        working_removed: list[str] = []
        if self.working is not None:
            working_removed = self._stale_working_sessions()
            if not dry_run:
                for sid in working_removed:
                    self.working.clear(sid)

        with get_connection(self.db_path) as conn:
            episodic_count = self._compact_episodic(conn, dry_run)
            semantic_ids, per_type = self._compact_semantic(conn, dry_run)
            old_chat_count = len(self._old_unverified_chat_ids(conn))

        # FAISS cleanup happens outside the SQLite transaction.
        if not dry_run and semantic_ids and self.index is not None:
            try:
                self.index.rebuild_without(semantic_ids)
            except Exception as exc:  # noqa: BLE001 - vector cleanup must not crash the sweep
                logger.warning("Semantic vector cleanup failed", exc_info=exc)

        result = {
            "dry_run": dry_run,
            "working_sessions_removed": len(working_removed),
            "episodic_rows_removed": episodic_count,
            "semantic_unverified_chat_removed": old_chat_count,
            "semantic_per_type_cap_rows": per_type,
            "semantic_vector_ids_removed": semantic_ids,
        }

        if not dry_run:
            self._audit(result)

        return result

    def _audit(self, result: dict[str, Any]) -> None:
        """Write one tamper-evident audit entry for the batch."""
        payload = json.dumps(result, sort_keys=True, default=str)
        try:
            log_action(
                actor="sleep-consolidation",
                payload=payload,
                zone=Zone.YELLOW,
                db_path=self.audit_db_path,
            )
        except Exception as exc:  # noqa: BLE001 - audit failure is logged but does not rollback memory
            logger.warning("Compaction audit entry failed", exc_info=exc)
```

- [ ] **Step 3: Compile check**

Run: `.venv/Scripts/python -m py_compile aios/memory/compaction.py`
Expected: exit 0.

---

## Task 4: Wire `POST /api/v1/memory/compact`

**Files:**
- Modify: `aios/api/main.py`

- [ ] **Step 1: Add request/response models**

Near the other request models (around the `/api/v1/memory/consolidate` block), add:

```python
class CompactRequest(BaseModel):
    dry_run: bool = True
```

- [ ] **Step 2: Add endpoint**

After the `/api/v1/memory/consolidate` endpoint, add:

```python
@app.post("/api/v1/memory/compact")
def compact_memory(
    req: CompactRequest,
    token: str = Depends(require_api_token),
    compactor: MemoryCompactor = Depends(get_compactor),
) -> JSONResponse:
    """Operator-triggered memory compaction (audited "sleep" sweep).

    Defaults to ``dry_run=True`` so the caller MUST explicitly set
    ``dry_run=false`` to mutate stores. Returns a preview of what would be
    removed when dry-run is enabled; when disabled, performs the sweep and
    writes one audit entry under actor ``sleep-consolidation``.
    """
    result = compactor.compact(dry_run=req.dry_run)
    status_code = 200 if req.dry_run else 202
    return JSONResponse(content=result, status_code=status_code)
```

- [ ] **Step 3: Provide `get_compactor` dependency**

Add near other dependency getters (e.g., `get_indexer`):

```python
def get_compactor() -> MemoryCompactor:
    """Return the process-wide memory compactor backed by the real stores."""
    return MemoryCompactor(
        working=working_memory,
        semantic=semantic_memory,
        episodic=episodic_memory,
        index=vector_index,
    )
```

Ensure `MemoryCompactor` is imported at the top of `main.py`:

```python
from aios.memory.compaction import MemoryCompactor
```

- [ ] **Step 4: Touch working sessions on chat/generate**

Inside the turn paths that use `working_memory`, call:

```python
compactor.touch_working_session(session_id)
```

A cheap place is the start of the `/api/v1/chat` and `/api/generate` endpoints, or where `working_memory` is already accessed. For minimal change, add it immediately after `_record_episode` in both turn paths.

- [ ] **Step 5: Compile check**

Run: `.venv/Scripts/python -m py_compile aios/api/main.py`
Expected: exit 0.

---

## Task 5: Add tests

**Files:**
- Create: `tests/test_memory_compaction.py`

- [ ] **Step 1: Create test file**

```python
"""Tests for the memory compaction sweep."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from aios import config
from aios.memory import db as memdb
from aios.memory.compaction import CompactionPreview, MemoryCompactor
from aios.memory.embeddings import VectorIndex
from aios.memory.episodic import EpisodicMemory
from aios.memory.semantic import SemanticMemory
from aios.memory.working import WorkingMemory
from aios.security import audit_logger


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "memory.db"
    memdb.init_memory_db(path)
    return path


@pytest.fixture()
def audit_db(tmp_path: Path) -> Path:
    path = tmp_path / "audit.db"
    audit_logger.init_audit_db(path)
    return path


class FakeIndex:
    """Records removes without loading sentence-transformers/FAISS."""

    def __init__(self) -> None:
        self.removed: list[int] = []

    def remove(self, ids):
        self.removed.extend(ids)

    def rebuild_without(self, ids):
        self.removed.extend(ids)

    def persist(self):
        pass


def test_preview_never_mutates(db_path: Path, audit_db: Path) -> None:
    wm = WorkingMemory()
    wm.set("s1", "k", "v")
    wm.touch_working_session("s1")

    ep = EpisodicMemory(db_path)
    ep.record("s1", "user", "hello")

    sem = SemanticMemory(db_path)
    sem.add("old chat", memory_type="chat", verification_status="unverified")

    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        working=wm,
        semantic=sem,
        episodic=ep,
        index=FakeIndex(),
        unverified_chat_days=0.0,
        episodic_days=0.0,
        semantic_max_per_type=0,
        working_idle_minutes=0,
    )
    before = comp.preview()
    assert before.working_sessions_count == 1
    comp.preview()
    assert wm.get("s1", "k") == "v"
    assert ep.count() == 1


def test_dry_run_reports_but_does_not_delete(db_path: Path, audit_db: Path) -> None:
    wm = WorkingMemory()
    wm.set("s1", "k", "v")
    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        working=wm,
        unverified_chat_days=0.0,
        episodic_days=0.0,
        semantic_max_per_type=0,
        working_idle_minutes=0,
    )
    result = comp.compact(dry_run=True)
    assert result["dry_run"] is True
    assert result["working_sessions_removed"] == 1
    assert wm.get("s1", "k") == "v"


def test_compact_removes_idle_working_session(db_path: Path, audit_db: Path) -> None:
    wm = WorkingMemory()
    wm.set("s1", "k", "v")
    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        working=wm,
        unverified_chat_days=9999.0,
        episodic_days=9999.0,
        semantic_max_per_type=9999,
        working_idle_minutes=0,
    )
    result = comp.compact(dry_run=False)
    assert result["dry_run"] is False
    assert result["working_sessions_removed"] == 1
    assert wm.get("s1", "k") is None


def test_compact_deletes_old_episodic_rows(db_path: Path, audit_db: Path) -> None:
    ep = EpisodicMemory(db_path)
    ep.record("s", "user", "hello")

    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        episodic=ep,
        unverified_chat_days=9999.0,
        episodic_days=0.0,
        semantic_max_per_type=9999,
        working_idle_minutes=9999,
    )
    result = comp.compact(dry_run=False)
    assert result["episodic_rows_removed"] == 1
    assert ep.count() == 0


def test_compact_deletes_old_unverified_chat(db_path: Path, audit_db: Path) -> None:
    sem = SemanticMemory(db_path, index=FakeIndex(), embedder=_FakeEmbedder())
    sem.add("old chat", memory_type="chat", verification_status="unverified")

    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        semantic=sem,
        index=FakeIndex(),
        unverified_chat_days=0.0,
        episodic_days=9999.0,
        semantic_max_per_type=9999,
        working_idle_minutes=9999,
    )
    result = comp.compact(dry_run=False)
    assert result["semantic_unverified_chat_removed"] == 1
    assert sem.count() == 0


def test_compact_keeps_verified_rows(db_path: Path, audit_db: Path) -> None:
    sem = SemanticMemory(db_path, index=FakeIndex(), embedder=_FakeEmbedder())
    sem.add("verified fact", memory_type="fact", verification_status="verified")

    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        semantic=sem,
        index=FakeIndex(),
        unverified_chat_days=0.0,
        episodic_days=0.0,
        semantic_max_per_type=0,
        working_idle_minutes=9999,
    )
    result = comp.compact(dry_run=False)
    assert result["semantic_vector_ids_removed"] == []
    assert sem.count() == 1


def test_compact_cleans_vector_index(db_path: Path, audit_db: Path) -> None:
    fake = FakeIndex()
    sem = SemanticMemory(db_path, index=fake, embedder=_FakeEmbedder())
    sem.add("old chat", memory_type="chat", verification_status="unverified")

    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        semantic=sem,
        index=fake,
        unverified_chat_days=0.0,
        episodic_days=9999.0,
        semantic_max_per_type=9999,
        working_idle_minutes=9999,
    )
    comp.compact(dry_run=False)
    assert fake.removed


def test_compact_writes_one_audit_entry(db_path: Path, audit_db: Path) -> None:
    wm = WorkingMemory()
    wm.set("s1", "k", "v")
    comp = MemoryCompactor(
        db_path=db_path,
        audit_db_path=audit_db,
        working=wm,
        unverified_chat_days=9999.0,
        episodic_days=9999.0,
        semantic_max_per_type=9999,
        working_idle_minutes=0,
    )
    comp.compact(dry_run=False)
    status = audit_logger.verify_chain(db_path=audit_db)
    assert status.valid is True
    assert status.total_entries == 2  # genesis + one action


class _FakeEmbedder:
    dim = 2

    def encode(self, texts):
        import numpy as np

        return np.asarray([[0.0, 1.0]], dtype="float32")
```

- [ ] **Step 2: Run the new tests**

Run: `.venv/Scripts/python -m pytest tests/test_memory_compaction.py -v`
Expected: 8 passed.

---

## Task 6: Full-suite verification and commit

- [ ] **Step 1: Run backend full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass (live count, currently 655 passed, 1 skipped).

- [ ] **Step 2: Update `.aios/state/RESUME.md`**

Add a P2-3 row summarising config changes, compaction module, endpoint, tests, and audit behavior.

- [ ] **Step 3: Commit and push**

```bash
git add -A
git commit -m "feat: audited memory compaction sweep (P2-3)

Add MemoryCompactor with dry-run preview and compact() for working,
episodic, and semantic layers. Verified rows are never deleted.
FAISS vectors are removed via VectorIndex.rebuild_without. New
POST /api/v1/memory/compact endpoint requires API token and defaults
TO dry_run. One audit entry per batch under sleep-consolidation.

Verified: pytest tests/test_memory_compaction.py + full backend suite."
git push origin master
```

---

## Self-review checklist

- [ ] Spec coverage: unverified chat TTL, episodic TTL, working idle TTL, per-type semantic cap, dry-run, audit entry, verified rows preserved — all covered above.
- [ ] No placeholders: every code block is concrete.
- [ ] Type consistency: `MemoryCompactor` constructor signatures match usage; `VectorIndex.remove` accepts `Sequence[int]`.
