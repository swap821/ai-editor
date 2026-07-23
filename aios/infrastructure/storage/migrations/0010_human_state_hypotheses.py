from __future__ import annotations

import sqlite3


class HumanStateHypothesesMigration:
    """Organ 30 (Tier 3): durable, append-only history of
    ``classify_human_state()`` outputs per live conversation turn.

    ``HumanStateHypothesis`` itself carries no session/turn identity -- it is
    a pure classification result (state/confidence/visible_reason plus the
    pinned ``user_correctable``/``grants_authority`` literals) -- so this
    table supplies that identity externally, the same way
    ``MissionTransitionJournal`` keys a domain-agnostic event onto a
    caller-supplied ``mission_id`` rather than the event type owning it.
    """

    version = 10
    name = "human_state_hypotheses_v1"
    scope = "human_representation"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS human_state_hypotheses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                state TEXT NOT NULL,
                confidence REAL NOT NULL,
                visible_reason TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                record_digest TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_human_state_hypotheses_session
                ON human_state_hypotheses(session_id);
            """
        )
