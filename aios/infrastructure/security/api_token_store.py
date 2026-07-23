"""SQLite persistence for API bearer-token rotation state.

Single durable row: this token gates the whole API surface for every
already-running client at once, so there is exactly one current/previous
pair, not a per-caller history.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from aios.domain.security.api_token import ApiTokenRotationState


class ApiTokenStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_token_rotation (
                    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                    current_token_digest TEXT NOT NULL,
                    current_issued_at REAL NOT NULL,
                    previous_token_digest TEXT,
                    previous_expires_at REAL
                )
                """
            )
            conn.commit()

    def current(self) -> ApiTokenRotationState | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT current_token_digest, current_issued_at, "
                "previous_token_digest, previous_expires_at "
                "FROM api_token_rotation WHERE singleton_id = 1"
            ).fetchone()
        if row is None:
            return None
        return ApiTokenRotationState(
            current_token_digest=str(row["current_token_digest"]),
            current_issued_at=float(row["current_issued_at"]),
            previous_token_digest=(
                str(row["previous_token_digest"])
                if row["previous_token_digest"] is not None
                else None
            ),
            previous_expires_at=(
                float(row["previous_expires_at"])
                if row["previous_expires_at"] is not None
                else None
            ),
        )

    def save(self, state: ApiTokenRotationState) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO api_token_rotation (
                    singleton_id, current_token_digest, current_issued_at,
                    previous_token_digest, previous_expires_at
                ) VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    current_token_digest = excluded.current_token_digest,
                    current_issued_at = excluded.current_issued_at,
                    previous_token_digest = excluded.previous_token_digest,
                    previous_expires_at = excluded.previous_expires_at
                """,
                (
                    state.current_token_digest,
                    state.current_issued_at,
                    state.previous_token_digest,
                    state.previous_expires_at,
                ),
            )
            conn.commit()


__all__ = ["ApiTokenStore"]
