"""Slice 33: Durable Local-Clerk Provenance and Continuity Organ."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aios.application.local_workforce import get_clerk_job_provenance
from aios.domain.local_workforce.contracts import (
    LocalJobRequestRecord,
    LocalJobResultRecord,
    LocalModelCallRecord,
)
from aios.infrastructure.local_workforce import (
    LocalWorkforceProvenanceStore,
    RecordTamperedError,
)


def _request(**overrides: object) -> LocalJobRequestRecord:
    fields: dict[str, object] = dict(
        job_id="job-1",
        job_profile="classify",
        input_schema_version="1.0",
        requested_model="granite3.2:2b",
        redacted_input_digest="a" * 64,
        token_budget=512,
        deadline="2026-07-22T00:00:00",
        created_at="2026-07-21T23:00:00",
    )
    fields.update(overrides)
    return LocalJobRequestRecord(**fields)


def _model_call(**overrides: object) -> LocalModelCallRecord:
    fields: dict[str, object] = dict(
        local_model_call_id="call-1",
        local_job_id="job-1",
        exact_model_id="granite3.2:2b",
        qualification_version="r15-v2",
        request_digest="b" * 64,
        response_digest="c" * 64,
        token_limits=512,
        measured_latency=1.2,
        start_time="2026-07-21T23:00:01",
        end_time="2026-07-21T23:00:02",
        status="completed",
    )
    fields.update(overrides)
    return LocalModelCallRecord(**fields)


def _result(**overrides: object) -> LocalJobResultRecord:
    fields: dict[str, object] = dict(
        local_job_id="job-1",
        local_model_call_id="call-1",
        structured_result_digest="d" * 64,
        schema_valid=True,
        evidence_references_preserved=True,
        status="completed",
    )
    fields.update(overrides)
    return LocalJobResultRecord(**fields)


def _store(tmp_path: Path) -> LocalWorkforceProvenanceStore:
    return LocalWorkforceProvenanceStore(tmp_path / "clerk.db")


# --- basic round-trip ------------------------------------------------------


def test_request_round_trips_exactly(tmp_path: Path) -> None:
    store = _store(tmp_path)
    request = _request()
    store.save_job_request(request)
    assert store.get_job_request("job-1") == request


def test_exact_model_id_is_stored_never_merely_local(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_job_request(_request())
    store.save_model_call(_model_call(exact_model_id="granite3.2:2b"))
    calls = store.get_model_calls_for_job("job-1")
    assert calls[0].exact_model_id == "granite3.2:2b"
    assert calls[0].exact_model_id != "local"


def test_only_digests_are_persisted_never_raw_input_or_output(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    with sqlite3.connect(str(tmp_path / "clerk.db")) as conn:
        conn.row_factory = sqlite3.Row
    store.save_job_request(_request())
    store.save_model_call(_model_call())
    store.save_job_result(_result())
    with sqlite3.connect(str(tmp_path / "clerk.db")) as conn:
        for table in ("local_job_requests", "local_model_calls", "local_job_results"):
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert not {"raw_input", "raw_output", "prompt", "response_text"} & columns


# --- crash-safety scenarios -------------------------------------------------


def test_crash_after_request_persistence_before_model_call(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_job_request(_request())
    assert store.get_model_calls_for_job("job-1") == ()
    assert store.get_job_result("job-1") is None
    trace = get_clerk_job_provenance(store, "job-1")
    assert trace.status == "request_recorded_awaiting_model_call"


def test_crash_after_model_response_before_result_persistence(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.save_job_request(_request())
    store.save_model_call(_model_call())
    assert store.get_job_result("job-1") is None
    trace = get_clerk_job_provenance(store, "job-1")
    assert trace.status == "model_call_recorded_awaiting_result"


def test_missing_job_id_provenance_is_honestly_unknown_not_fabricated(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    trace = get_clerk_job_provenance(store, "never-existed")
    assert trace.status == "unknown"
    assert trace.request is None


# --- duplicate retry / restart / tamper -------------------------------------


def test_duplicate_retry_does_not_create_ambiguous_lineage(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_job_request(_request())
    with pytest.raises(sqlite3.IntegrityError):
        store.save_job_request(_request())


def test_restart_reconstructs_pending_clerk_job_state(tmp_path: Path) -> None:
    db_path = tmp_path / "clerk.db"
    store = LocalWorkforceProvenanceStore(db_path)
    store.save_job_request(_request())
    store.save_model_call(_model_call())

    # Simulate a restart: a fresh store instance over the same durable file.
    restarted = LocalWorkforceProvenanceStore(db_path)
    assert restarted.get_job_request("job-1") == _request()
    assert restarted.get_model_calls_for_job("job-1") == (_model_call(),)
    assert restarted.get_job_result("job-1") is None


def test_tampered_record_breaks_digest_verification(tmp_path: Path) -> None:
    db_path = tmp_path / "clerk.db"
    store = LocalWorkforceProvenanceStore(db_path)
    store.save_job_request(_request())

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE local_job_requests SET requested_model = 'tampered-model' "
            "WHERE job_id = 'job-1'"
        )
        conn.commit()

    with pytest.raises(RecordTamperedError):
        store.get_job_request("job-1")


# --- full lineage rendering --------------------------------------------------


def test_full_lineage_renders_request_through_result(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_job_request(_request())
    store.save_model_call(_model_call())
    store.save_job_result(_result())
    trace = get_clerk_job_provenance(store, "job-1")
    assert trace.status == "completed"
    rendered = trace.render()
    assert "granite3.2:2b" in rendered
    assert "completed" in rendered
