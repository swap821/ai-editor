"""SQLite persistence for representative contexts and authenticated receipts.

RepresentativeContextV1 remains the provider-neutral packet and retains its
historic digest shape. RepresentativeContextReceiptV1 is an append-only
sidecar used by authenticated chat to record the selected human-representation
sources, the explicit omissions, consent scope, and validity window.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from aios.application.intelligence.context_compiler import context_digest_from_record
from aios.domain.intelligence.representative_context import (
    RepresentativeContextReceiptV1,
    RepresentativeContextV1,
    receipt_digest_from_record,
)
from aios.infrastructure.storage.migrations import apply_migrations


class RecordTamperedError(RuntimeError):
    """Raised when a stored context or receipt no longer matches its digest."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class RepresentativeContextStore:
    """Durable append-only contexts, with optional atomic receipt bundles."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            apply_migrations(conn, scope="intelligence")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, context: RepresentativeContextV1) -> None:
        """Persist a legacy/general context record without a receipt."""
        _validate_context(context)
        with closing(self._connect()) as conn:
            self._insert_context(conn, context)
            conn.commit()

    def save_bundle(
        self,
        context: RepresentativeContextV1,
        receipt: RepresentativeContextReceiptV1,
    ) -> None:
        """Atomically persist one authenticated context and its receipt.

        A receipt-store failure is intentionally observable to this caller:
        authenticated chat uses this strict operation before it invokes a
        provider, so there is no unreceipted governed model request.
        """
        _validate_bundle(context, receipt)
        with closing(self._connect()) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._insert_context(conn, context)
                self._insert_receipt(conn, receipt)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def get(self, request_id: str) -> RepresentativeContextV1 | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM representative_contexts WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        return _context_from_row(row)

    def get_bundle(
        self, request_id: str
    ) -> tuple[RepresentativeContextV1, RepresentativeContextReceiptV1] | None:
        """Load and validate an authenticated context plus its receipt."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT
                    contexts.*,
                    receipts.request_id AS receipt_request_id,
                    receipts.context_digest AS receipt_context_digest,
                    receipts.operator_identity_digest AS receipt_operator_identity_digest,
                    receipts.constitution_digest AS receipt_constitution_digest,
                    receipts.receipt_json,
                    receipts.receipt_digest
                FROM representative_contexts AS contexts
                JOIN representative_context_receipts AS receipts
                    ON receipts.request_id = contexts.request_id
                WHERE contexts.request_id = ?
                """,
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        context = _context_from_row(row)
        receipt = _receipt_from_row(row)
        if (
            receipt.request_id != context.request_id
            or receipt.context_digest != context.context_digest
            or receipt.operator_identity_digest != context.operator_identity_digest
            or receipt.constitution_digest != context.constitution_digest
            or row["receipt_request_id"] != context.request_id
            or row["receipt_context_digest"] != context.context_digest
            or row["receipt_operator_identity_digest"]
            != context.operator_identity_digest
            or row["receipt_constitution_digest"] != context.constitution_digest
        ):
            raise RecordTamperedError(
                f"stored representative context receipt linkage mismatch for "
                f"{request_id!r}"
            )
        return context, receipt

    def list_recent(self, limit: int = 20) -> tuple[RepresentativeContextV1, ...]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM representative_contexts "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(_context_from_row(row) for row in rows)

    @staticmethod
    def _insert_context(conn: sqlite3.Connection, context: RepresentativeContextV1) -> None:
        conn.execute(
            """
            INSERT INTO representative_contexts (
                request_id, operator_identity_digest, constitution_digest,
                privacy_classification, context_json, context_digest,
                recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                context.request_id,
                context.operator_identity_digest,
                context.constitution_digest,
                context.privacy_classification,
                json.dumps(context.as_dict(), sort_keys=True),
                context.context_digest,
                _utc_now(),
            ),
        )

    @staticmethod
    def _insert_receipt(
        conn: sqlite3.Connection, receipt: RepresentativeContextReceiptV1
    ) -> None:
        conn.execute(
            """
            INSERT INTO representative_context_receipts (
                request_id, context_digest, operator_identity_digest,
                constitution_digest, created_at, expires_at, receipt_json,
                receipt_digest, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt.request_id,
                receipt.context_digest,
                receipt.operator_identity_digest,
                receipt.constitution_digest,
                receipt.created_at,
                receipt.expires_at,
                json.dumps(receipt.as_dict(), sort_keys=True),
                receipt.receipt_digest,
                _utc_now(),
            ),
        )


def _validate_context(context: RepresentativeContextV1) -> None:
    if context_digest_from_record(context) != context.context_digest:
        raise RecordTamperedError(
            f"representative context digest mismatch for {context.request_id!r}"
        )


def _validate_bundle(
    context: RepresentativeContextV1, receipt: RepresentativeContextReceiptV1
) -> None:
    _validate_context(context)
    if receipt_digest_from_record(receipt) != receipt.receipt_digest:
        raise RecordTamperedError(
            f"representative context receipt digest mismatch for {receipt.request_id!r}"
        )
    if (
        receipt.request_id != context.request_id
        or receipt.context_digest != context.context_digest
        or receipt.operator_identity_digest != context.operator_identity_digest
        or receipt.constitution_digest != context.constitution_digest
    ):
        raise ValueError("representative context receipt does not bind this context")


def _context_from_row(row: sqlite3.Row) -> RepresentativeContextV1:
    payload = json.loads(row["context_json"])
    record = RepresentativeContextV1.model_validate(payload)
    row_digest = str(row["context_digest"])
    if record.context_digest != row_digest:
        raise RecordTamperedError(
            f"stored representative context embedded digest mismatch for "
            f"{row['request_id']!r}"
        )
    if context_digest_from_record(record) != row_digest:
        raise RecordTamperedError(
            f"stored representative context digest mismatch for {row['request_id']!r}: "
            "the row was altered outside this store"
        )
    return record


def _receipt_from_row(row: sqlite3.Row) -> RepresentativeContextReceiptV1:
    payload = json.loads(row["receipt_json"])
    record = RepresentativeContextReceiptV1.model_validate(payload)
    row_digest = str(row["receipt_digest"])
    if record.receipt_digest != row_digest:
        raise RecordTamperedError(
            f"stored representative context receipt embedded digest mismatch for "
            f"{record.request_id!r}"
        )
    if receipt_digest_from_record(record) != row_digest:
        raise RecordTamperedError(
            f"stored representative context receipt digest mismatch for "
            f"{record.request_id!r}: the row was altered outside this store"
        )
    return record


__all__ = ["RepresentativeContextStore", "RecordTamperedError"]