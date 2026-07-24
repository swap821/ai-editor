from __future__ import annotations

import sqlite3


class HumanStateCorrectionsV2Migration:
    """Organ 30: a real, append-only, tamper-evident event stream for
    human-state corrections.

    Migration 0013 added ``corrected_state``/``corrected_at`` as mutable
    columns on the original ``human_state_hypotheses`` row and reasoned that
    this was safe because the hypothesis's own digest never covered them --
    but that is exactly the bug: nothing about a correction was ever
    tamper-evident, since the digest that DOES get checked on read
    (``HumanStateHypothesisStore.get_history``) only ever covers the
    classifier's own original output, never the correction applied on top
    of it. A row could have its ``corrected_state`` silently altered
    outside this store and no check anywhere would notice.

    ``human_state_corrections`` is a genuinely new, append-only table: one
    row per correction event, digested over its own fields (including the
    corrected hypothesis's own digest, so a correction is bound to the
    exact hypothesis content it corrects) and, honestly, over whatever
    operator identity was actually resolvable at correction time --
    ``operator_id`` is nullable because this route is reachable by an
    unauthenticated local session by design elsewhere in this codebase, and
    fabricating an identity would be worse than recording none.

    ``hypothesis_id`` (the corrected row's real primary key) is the join
    key used to resolve identity -- ``hypothesis_digest`` alone is not
    unique enough for that: two hypotheses with identical content (a real,
    common case -- the same classifier output on two different turns)
    share a digest, so joining correction-to-hypothesis on digest alone
    would silently fold distinct corrections together. ``hypothesis_digest``
    is kept anyway, purely for tamper evidence: it proves a correction was
    recorded against a hypothesis whose content was exactly this at
    correction time, independent of which row id happens to hold it.

    ``human_state_hypotheses.corrected_state``/``corrected_at`` (0013) are
    left in place (SQLite has no cheap column-drop) but are no longer read
    or written by this store -- superseded, not deleted, by this table.
    """

    version = 14
    name = "human_state_corrections_v2"
    scope = "human_representation"

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS human_state_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                hypothesis_id INTEGER NOT NULL,
                hypothesis_digest TEXT NOT NULL,
                corrected_state TEXT NOT NULL,
                operator_id TEXT,
                corrected_at TEXT NOT NULL,
                record_digest TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_human_state_corrections_turn "
            "ON human_state_corrections (session_id, turn_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_human_state_corrections_hypothesis "
            "ON human_state_corrections (hypothesis_id)"
        )
