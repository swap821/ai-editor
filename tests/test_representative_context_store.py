"""Organ 31: durable, append-only history for RepresentativeContextV1."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from aios.application.intelligence.context_compiler import compile_representative_context
from aios.infrastructure.intelligence.representative_context_store import (
    RecordTamperedError,
    RepresentativeContextStore,
)


def _context(request_id: str = "req-1", target: str = "local"):
    return compile_representative_context(
        request_id=request_id,
        operator_identity_digest="operator-digest",
        constitution_digest="c" * 64,
        goal="summarize the incident",
        desired_outcome="a short, accurate summary",
        target=target,
        delegated_authority_summary="advisory only, no write authority",
    )


def test_save_and_get_round_trips(tmp_path: Path) -> None:
    store = RepresentativeContextStore(tmp_path / "contexts.db")
    context = _context()
    store.save(context)

    loaded = store.get("req-1")

    assert loaded is not None
    assert loaded == context


def test_get_missing_request_id_returns_none(tmp_path: Path) -> None:
    store = RepresentativeContextStore(tmp_path / "contexts.db")
    assert store.get("no-such-request") is None


def test_list_recent_returns_newest_first(tmp_path: Path) -> None:
    store = RepresentativeContextStore(tmp_path / "contexts.db")
    store.save(_context("req-1"))
    store.save(_context("req-2"))
    store.save(_context("req-3"))

    recent = store.list_recent(limit=2)

    assert [c.request_id for c in recent] == ["req-3", "req-2"]


def test_tampered_row_is_detected_at_read_time(tmp_path: Path) -> None:
    db_path = tmp_path / "contexts.db"
    store = RepresentativeContextStore(db_path)
    context = _context()
    store.save(context)

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT context_json FROM representative_contexts WHERE request_id = ?",
        (context.request_id,),
    ).fetchone()
    payload = json.loads(row[0])
    payload["goal"] = "a goal nobody actually approved"
    conn.execute(
        "UPDATE representative_contexts SET context_json = ? WHERE request_id = ?",
        (json.dumps(payload), context.request_id),
    )
    conn.commit()
    conn.close()

    with pytest.raises(RecordTamperedError):
        store.get(context.request_id)


def test_duplicate_request_id_is_rejected(tmp_path: Path) -> None:
    store = RepresentativeContextStore(tmp_path / "contexts.db")
    store.save(_context("req-1"))

    with pytest.raises(sqlite3.IntegrityError):
        store.save(_context("req-1"))
