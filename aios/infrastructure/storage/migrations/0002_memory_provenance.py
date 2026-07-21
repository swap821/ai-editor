from __future__ import annotations

import sqlite3


class MemoryProvenanceMigration:
    """Slice 17 — a reference registry for evidence-backed memory lineage.

    The registry deliberately stores references and digests, not a second copy
    of memory content.  Existing working, episodic, semantic, fact, skill and
    pheromone stores remain specialized physical stores; this schema is their
    promotion/provenance authority.
    """

    version = 2
    name = "memory_provenance_v1"
    scope = "memory"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory_authority_proposals (
                proposal_id TEXT PRIMARY KEY,
                memory_type TEXT NOT NULL,
                content_reference TEXT NOT NULL,
                content_digest TEXT NOT NULL,
                project_id TEXT,
                source_principal TEXT NOT NULL,
                source_turn_id TEXT,
                source_mission_id TEXT,
                source_action_id TEXT,
                evidence_ids_json TEXT NOT NULL,
                required_strength INTEGER NOT NULL,
                policy_version TEXT NOT NULL,
                confidence_basis TEXT NOT NULL,
                requires_operator_approval INTEGER NOT NULL,
                metadata_json TEXT NOT NULL,
                evidence_freshness_seconds INTEGER NOT NULL,
                status TEXT NOT NULL,
                proposed_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_memory_proposals_project_status
                ON memory_authority_proposals(project_id, status);
            CREATE INDEX IF NOT EXISTS idx_memory_proposals_digest
                ON memory_authority_proposals(content_digest);

            CREATE TABLE IF NOT EXISTS memory_authority_records (
                record_id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL UNIQUE,
                memory_type TEXT NOT NULL,
                content_reference TEXT NOT NULL,
                content_digest TEXT NOT NULL,
                project_id TEXT,
                provenance_json TEXT NOT NULL,
                status TEXT NOT NULL,
                promoted_at TEXT NOT NULL,
                FOREIGN KEY (proposal_id)
                    REFERENCES memory_authority_proposals(proposal_id)
            );

            CREATE INDEX IF NOT EXISTS idx_memory_records_project_status
                ON memory_authority_records(project_id, status);
            CREATE INDEX IF NOT EXISTS idx_memory_records_type_status
                ON memory_authority_records(memory_type, status);
            CREATE INDEX IF NOT EXISTS idx_memory_records_digest
                ON memory_authority_records(content_digest);

            CREATE TABLE IF NOT EXISTS memory_authority_evidence (
                record_id TEXT NOT NULL,
                evidence_id TEXT NOT NULL,
                verification_strength INTEGER NOT NULL,
                attached_at TEXT NOT NULL,
                PRIMARY KEY(record_id, evidence_id),
                FOREIGN KEY (record_id)
                    REFERENCES memory_authority_records(record_id)
            );

            CREATE INDEX IF NOT EXISTS idx_memory_evidence_id
                ON memory_authority_evidence(evidence_id);
            """
        )
