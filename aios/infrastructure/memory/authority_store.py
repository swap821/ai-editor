"""SQLite reference store for evidence-backed memory provenance.

This store is intentionally a registry.  It records the authority metadata
and content references while the existing specialized memory stores keep their
own physical representations and derived indexes.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence

from aios.domain.memory import (
    MemoryProposal,
    MemoryRecord,
    MemoryRecordProvenance,
    MemoryStatus,
)
from aios.infrastructure.storage.migrations import apply_migrations


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class MemoryAuthorityStore:
    """Durable CRUD for proposals, promoted references and evidence links."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._shared_conn: sqlite3.Connection | None = None
        if self.db_path == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:")
            self._shared_conn.row_factory = sqlite3.Row
        self._initialize()

    def _open(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _close(self, conn: sqlite3.Connection) -> None:
        if conn is not self._shared_conn:
            conn.close()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._open()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._close(conn)

    def _initialize(self) -> None:
        with self._connection() as conn:
            apply_migrations(conn, scope="memory")

    @staticmethod
    def _proposal_from_row(row: sqlite3.Row) -> MemoryProposal:
        return MemoryProposal(
            proposal_id=str(row["proposal_id"]),
            memory_type=str(row["memory_type"]),
            content_reference=str(row["content_reference"]),
            content_digest=str(row["content_digest"]),
            project_id=row["project_id"],
            source_principal=str(row["source_principal"]),
            source_turn_id=row["source_turn_id"],
            source_mission_id=row["source_mission_id"],
            source_action_id=row["source_action_id"],
            evidence_ids=tuple(json.loads(str(row["evidence_ids_json"]))),
            required_strength=int(row["required_strength"]),
            policy_version=str(row["policy_version"]),
            confidence_basis=str(row["confidence_basis"]),
            requires_operator_approval=bool(row["requires_operator_approval"]),
            metadata=json.loads(str(row["metadata_json"])),
            proposed_at=str(row["proposed_at"]),
            evidence_freshness_seconds=int(row["evidence_freshness_seconds"]),
        )

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            record_id=str(row["record_id"]),
            proposal_id=str(row["proposal_id"]),
            memory_type=str(row["memory_type"]),
            content_reference=str(row["content_reference"]),
            content_digest=str(row["content_digest"]),
            project_id=row["project_id"],
            provenance=MemoryRecordProvenance.model_validate_json(
                str(row["provenance_json"])
            ),
            status=MemoryStatus(str(row["status"])),
            promoted_at=str(row["promoted_at"]),
        )

    def save_proposal(self, proposal: MemoryProposal) -> MemoryProposal:
        """Persist a quarantined proposal without making it recallable."""
        with self._connection() as conn:
            existing = conn.execute(
                "SELECT * FROM memory_authority_proposals WHERE proposal_id = ?",
                (proposal.proposal_id,),
            ).fetchone()
            if existing is not None:
                current = self._proposal_from_row(existing)
                if current != proposal:
                    raise ValueError(
                        "proposal id already exists with different content"
                    )
                return current
            conn.execute(
                """
                INSERT INTO memory_authority_proposals (
                    proposal_id, memory_type, content_reference, content_digest,
                    project_id, source_principal, source_turn_id, source_mission_id,
                    source_action_id, evidence_ids_json, required_strength,
                    policy_version, confidence_basis, requires_operator_approval,
                    metadata_json, evidence_freshness_seconds, status, proposed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.proposal_id,
                    proposal.memory_type,
                    proposal.content_reference,
                    proposal.content_digest,
                    proposal.project_id,
                    proposal.source_principal,
                    proposal.source_turn_id,
                    proposal.source_mission_id,
                    proposal.source_action_id,
                    json.dumps(list(proposal.evidence_ids), sort_keys=True),
                    proposal.required_strength,
                    proposal.policy_version,
                    proposal.confidence_basis,
                    int(proposal.requires_operator_approval),
                    json.dumps(proposal.metadata, sort_keys=True),
                    proposal.evidence_freshness_seconds,
                    MemoryStatus.PROPOSED.value,
                    proposal.proposed_at,
                ),
            )
        return proposal

    def get_proposal(self, proposal_id: str) -> MemoryProposal | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM memory_authority_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
        return self._proposal_from_row(row) if row is not None else None

    def proposal_status(self, proposal_id: str) -> MemoryStatus | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT status FROM memory_authority_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
        return MemoryStatus(str(row["status"])) if row is not None else None

    def save_promoted(
        self,
        record: MemoryRecord,
        *,
        evidence_strengths: Sequence[tuple[str, int]],
    ) -> MemoryRecord:
        """Atomically create the record, evidence links and proposal transition."""
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            proposal = conn.execute(
                "SELECT status FROM memory_authority_proposals WHERE proposal_id = ?",
                (record.proposal_id,),
            ).fetchone()
            if proposal is None:
                raise ValueError("proposal does not exist")
            if str(proposal["status"]) != MemoryStatus.PROPOSED.value:
                raise ValueError("proposal is no longer promotable")
            conn.execute(
                """
                INSERT INTO memory_authority_records (
                    record_id, proposal_id, memory_type, content_reference,
                    content_digest, project_id, provenance_json, status, promoted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.proposal_id,
                    record.memory_type,
                    record.content_reference,
                    record.content_digest,
                    record.project_id,
                    record.provenance.model_dump_json(),
                    record.status.value,
                    record.promoted_at,
                ),
            )
            conn.executemany(
                """
                INSERT INTO memory_authority_evidence
                    (record_id, evidence_id, verification_strength, attached_at)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (record.record_id, evidence_id, strength, _utc_now())
                    for evidence_id, strength in evidence_strengths
                ],
            )
            conn.execute(
                "UPDATE memory_authority_proposals SET status = ? WHERE proposal_id = ?",
                (MemoryStatus.VERIFIED.value, record.proposal_id),
            )
        return record

    def get_record(self, record_id: str) -> MemoryRecord | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM memory_authority_records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
        return self._record_from_row(row) if row is not None else None

    def list_records(
        self,
        *,
        project_id: str | None,
        memory_types: Sequence[str] = (),
        include_superseded: bool = False,
        limit: int = 100,
    ) -> tuple[MemoryRecord, ...]:
        """Read only current indexed records; no history scan is required."""
        clauses = ["status = ?"]
        params: list[object] = [
            MemoryStatus.SUPERSEDED.value
            if include_superseded
            else MemoryStatus.VERIFIED.value
        ]
        if project_id is None:
            clauses.append("project_id IS NULL")
        else:
            clauses.append("project_id = ?")
            params.append(project_id)
        if memory_types:
            placeholders = ",".join("?" for _ in memory_types)
            clauses.append(f"memory_type IN ({placeholders})")
            params.extend(memory_types)
        params.append(max(1, min(limit, 100)))
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_authority_records WHERE "
                + " AND ".join(clauses)
                + " ORDER BY promoted_at DESC LIMIT ?",
                params,
            ).fetchall()
        return tuple(self._record_from_row(row) for row in rows)

    def supersede(self, record_id: str, replacement_record_id: str) -> MemoryRecord:
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT * FROM memory_authority_records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            replacement = conn.execute(
                "SELECT record_id, project_id FROM memory_authority_records WHERE record_id = ?",
                (replacement_record_id,),
            ).fetchone()
            if current is None or replacement is None:
                raise ValueError("both memory records are required for supersession")
            if current["project_id"] != replacement["project_id"]:
                raise ValueError(
                    "memory records from different projects cannot supersede"
                )
            conn.execute(
                "UPDATE memory_authority_records SET status = ? WHERE record_id = ?",
                (MemoryStatus.SUPERSEDED.value, record_id),
            )
            row = conn.execute(
                "SELECT * FROM memory_authority_records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
        return self._record_from_row(row)

    def compact(self, *, keep_superseded: bool = True) -> int:
        """Compact only rejected proposals; verified lineage is retained."""
        with self._connection() as conn:
            cur = conn.execute(
                "DELETE FROM memory_authority_proposals WHERE status = ?",
                (MemoryStatus.REJECTED.value,),
            )
            # Superseded records remain by default for provenance and rollback.
            if not keep_superseded:
                conn.execute(
                    "DELETE FROM memory_authority_records WHERE status = ?",
                    (MemoryStatus.SUPERSEDED.value,),
                )
            return int(cur.rowcount)
