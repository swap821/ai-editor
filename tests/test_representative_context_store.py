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


def _receipt_for_context(context):
    """Resolve the new contract dynamically so the first TDD run fails as an
    assertion in this test, not as a test-collection import failure."""
    from aios.domain.intelligence import representative_context

    receipt_type = getattr(
        representative_context, "RepresentativeContextReceiptV1", None
    )
    assert receipt_type is not None
    return receipt_type.create(
        request_id=context.request_id,
        context_digest=context.context_digest,
        operator_identity_digest=context.operator_identity_digest,
        constitution_digest=context.constitution_digest,
        target=context.privacy_classification,
        active_project_revision=7,
        included_preference_ids=("pref-global", "pref-project"),
        included_correction_ids=("correction-event-1",),
        human_state_hypothesis_id=42,
        human_state_disposition="included",
        exclusions=(),
        consent_status="not_required_local",
        consent_scope=("authenticated-chat", "project:ai-editor"),
        created_at="2026-07-26T00:00:00+00:00",
        expires_at="2026-07-26T00:05:00+00:00",
    )


def test_bundle_round_trips_after_store_reopen_with_the_complete_receipt(
    tmp_path: Path,
) -> None:
    """Authenticated chat needs an auditable receipt that survives restart."""
    db_path = tmp_path / "contexts.db"
    context = _context("req-receipt")
    store = RepresentativeContextStore(db_path)
    receipt = _receipt_for_context(context)

    store.save_bundle(context, receipt)

    reopened = RepresentativeContextStore(db_path)
    loaded_context, loaded_receipt = reopened.get_bundle(context.request_id)
    assert loaded_context == context
    assert loaded_receipt == receipt
    assert loaded_receipt.active_project_revision == 7
    assert loaded_receipt.included_preference_ids == ("pref-global", "pref-project")
    assert loaded_receipt.included_correction_ids == ("correction-event-1",)
    assert loaded_receipt.human_state_hypothesis_id == 42


def test_receipt_with_exclusion_metadata_has_a_stable_digest_and_round_trips(
    tmp_path: Path,
) -> None:
    from aios.domain.intelligence.representative_context import (
        ContextExclusionV1,
        RepresentativeContextReceiptV1,
        receipt_digest_from_record,
    )

    context = _context("req-exclusion-receipt")
    receipt = RepresentativeContextReceiptV1.create(
        request_id=context.request_id,
        context_digest=context.context_digest,
        operator_identity_digest=context.operator_identity_digest,
        constitution_digest=context.constitution_digest,
        target=context.privacy_classification,
        active_project_revision=7,
        included_preference_ids=("pref-project",),
        included_correction_ids=(),
        human_state_hypothesis_id=None,
        human_state_disposition="abstained",
        exclusions=(
            ContextExclusionV1(
                source="operator_preference",
                field="tone",
                source_id="pref-expired",
                reason="expired",
            ),
        ),
        consent_status="not_required_local",
        consent_scope=("authenticated-chat",),
        created_at="2026-07-26T00:00:00+00:00",
        expires_at="2026-07-26T00:05:00+00:00",
    )

    assert receipt_digest_from_record(receipt) == receipt.receipt_digest
    store = RepresentativeContextStore(tmp_path / "contexts.db")
    store.save_bundle(context, receipt)
    assert store.get_bundle(context.request_id) == (context, receipt)


def test_embedded_context_digest_tampering_is_detected(tmp_path: Path) -> None:
    """The row digest and the context's own digest must agree independently."""
    db_path = tmp_path / "contexts.db"
    store = RepresentativeContextStore(db_path)
    context = _context("req-embedded-digest")
    store.save(context)

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT context_json FROM representative_contexts WHERE request_id = ?",
        (context.request_id,),
    ).fetchone()
    payload = json.loads(row[0])
    payload["context_digest"] = "0" * 64
    conn.execute(
        "UPDATE representative_contexts SET context_json = ? WHERE request_id = ?",
        (json.dumps(payload), context.request_id),
    )
    conn.commit()
    conn.close()

    with pytest.raises(RecordTamperedError):
        store.get(context.request_id)
