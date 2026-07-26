from __future__ import annotations

import sqlite3


class AuthenticatedCorrectionEventsMigration:
    """Immutable authenticated correction projections for governed chat."""

    version = 20
    name = "authenticated_correction_events_v1"
    scope = "human_representation"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS authenticated_correction_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                correction_id TEXT NOT NULL,
                base_revision INTEGER NOT NULL,
                correction_revision INTEGER NOT NULL,
                correction_record_digest TEXT NOT NULL,
                prior_interpretation_digest TEXT NOT NULL,
                conversation_session_digest TEXT NOT NULL,
                operator_id TEXT NOT NULL,
                operator_identity_digest TEXT NOT NULL,
                authentication_event_id TEXT NOT NULL,
                authentication_verifier TEXT NOT NULL,
                event_kind TEXT NOT NULL,
                corrected_values_json TEXT NOT NULL,
                reason TEXT NOT NULL,
                previous_correction_digest TEXT,
                recorded_at TEXT NOT NULL,
                event_digest TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_authenticated_correction_event_revision
                ON authenticated_correction_events(
                    conversation_session_digest, correction_revision, event_kind
                );
            CREATE INDEX IF NOT EXISTS idx_authenticated_correction_event_lookup
                ON authenticated_correction_events(
                    conversation_session_digest, operator_identity_digest, id DESC
                );
            CREATE INDEX IF NOT EXISTS idx_authenticated_correction_event_correction
                ON authenticated_correction_events(correction_id);
            """
        )