from __future__ import annotations

import sqlite3


class GovernanceAmendmentHistoryMigration:
    """Reconciliation pass item 6 -- durable, append-only history for
    ConstitutionalAmendmentProposalV1 (Slice 37) and GovernanceLessonV1
    (Slice 38). Both were pure in-memory pipelines with zero persistence
    before this migration.

    Rows are append-only (primary key includes ``revision``) rather than
    upserted in place, matching the correction-lineage philosophy already
    established for operator preferences (Slice 28): every state transition
    -- propose, critique, simulate, ratify, reject, activate, roll back --
    is preserved as its own row instead of overwriting the prior one.
    """

    version = 7
    name = "governance_amendment_history_v1"
    scope = "governance"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS governance_amendment_proposals (
                proposal_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                target_articles_json TEXT NOT NULL,
                proposed_diff TEXT NOT NULL,
                motivation TEXT NOT NULL,
                incident_refs_json TEXT NOT NULL,
                evidence_refs_json TEXT NOT NULL,
                threat_model_json TEXT NOT NULL,
                expected_benefits_json TEXT NOT NULL,
                new_risks_json TEXT NOT NULL,
                migration_plan TEXT NOT NULL,
                rollback_plan TEXT NOT NULL,
                proposed_by TEXT NOT NULL,
                proposer_type TEXT NOT NULL,
                status TEXT NOT NULL,
                critiques_json TEXT NOT NULL,
                simulation_notes_json TEXT NOT NULL,
                ratified_by_operator_id TEXT,
                ratification_capability_digest TEXT,
                created_at TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                record_digest TEXT NOT NULL,
                PRIMARY KEY (proposal_id, revision)
            );
            CREATE INDEX IF NOT EXISTS idx_governance_amendment_proposals_id
                ON governance_amendment_proposals(proposal_id);
            CREATE TABLE IF NOT EXISTS governance_lessons (
                lesson_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                problem_class TEXT NOT NULL,
                evidence_refs_json TEXT NOT NULL,
                observed_harm TEXT NOT NULL,
                current_rule TEXT NOT NULL,
                proposed_improvement TEXT NOT NULL,
                confidence REAL NOT NULL,
                amendment_proposal_id TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                record_digest TEXT NOT NULL,
                PRIMARY KEY (lesson_id, revision)
            );
            CREATE INDEX IF NOT EXISTS idx_governance_lessons_id
                ON governance_lessons(lesson_id);
            """
        )
