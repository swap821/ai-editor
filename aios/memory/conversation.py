"""Durable, advisory conversation-alignment state.

This store persists only the latest already-validated understanding frame for a
session. It restores continuity; it does not verify the frame, promote facts, or
grant any authority. Caller-supplied session identifiers are stored only as
SHA-256 digests.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from aios import config
from aios.memory.db import get_connection, init_memory_db
from aios.security.secret_scanner import scan_and_redact


class ConversationStateStore:
    """Persist and retrieve the latest advisory frame for each session."""

    def __init__(self, db_path: Path = config.MEMORY_DB_PATH) -> None:
        self.db_path = db_path

    @staticmethod
    def _session_key(session_id: str) -> str:
        return hashlib.sha256(session_id.encode("utf-8")).hexdigest()

    @staticmethod
    def _payload(value: object, *, label: str) -> str:
        payload = scan_and_redact(
            json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        ).scrubbed
        parsed = json.loads(payload)
        if not isinstance(parsed, (dict, list)):
            raise ValueError(f"{label} must remain structured JSON")
        return payload

    def save(self, session_id: str, frame: dict[str, Any]) -> None:
        """Persist a secret-scrubbed frame, replacing the prior session state."""
        if not session_id:
            raise ValueError("conversation state requires a session id")
        if not isinstance(frame, dict):
            raise ValueError("conversation state frame must be an object")
        payload = self._payload(frame, label="conversation state frame")
        if not isinstance(json.loads(payload), dict):
            raise ValueError("conversation state frame must remain an object")
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            conn.execute(
                "INSERT INTO conversation_state (session_id, updated_at, frame_json) "
                "VALUES (?, CURRENT_TIMESTAMP, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET "
                "updated_at = CURRENT_TIMESTAMP, frame_json = excluded.frame_json",
                (self._session_key(session_id), payload),
            )

    def get(self, session_id: str) -> Optional[dict[str, Any]]:
        """Return the latest advisory frame for *session_id*, if one exists."""
        if not session_id:
            return None
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT frame_json FROM conversation_state WHERE session_id IN (?, ?)",
                (self._session_key(session_id), session_id),
            ).fetchone()
        if row is None:
            return None
        try:
            value = json.loads(str(row["frame_json"]))
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def active_correction(self, session_id: str) -> Optional[dict[str, Any]]:
        """Return the active user-authored correction revision, if any."""
        if not session_id:
            return None
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, overrides_json, corrected_fields_json "
                "FROM conversation_corrections "
                "WHERE session_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
                (self._session_key(session_id),),
            ).fetchone()
        if row is None:
            return None
        try:
            overrides = json.loads(str(row["overrides_json"]))
            fields = json.loads(str(row["corrected_fields_json"]))
        except json.JSONDecodeError:
            return None
        if not isinstance(overrides, dict) or not isinstance(fields, list):
            return None
        return {"revision": int(row["id"]), "corrections": overrides, "fields": fields}

    def refresh_active_correction(
        self,
        session_id: str,
        *,
        base_frame: dict[str, Any],
        corrected_frame: dict[str, Any],
    ) -> None:
        """Persist a new interpreted base plus the active corrected projection."""
        if not session_id:
            raise ValueError("conversation correction requires a session id")
        base_payload = self._payload(base_frame, label="base frame")
        corrected_payload = self._payload(corrected_frame, label="corrected frame")
        key = self._session_key(session_id)
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE conversation_corrections SET before_frame_json = ?, "
                "after_frame_json = ? WHERE session_id = ? AND status = 'active'",
                (base_payload, corrected_payload, key),
            )
            if cur.rowcount != 1:
                raise ValueError("no active conversation correction")
            conn.execute(
                "INSERT INTO conversation_state (session_id, updated_at, frame_json) "
                "VALUES (?, CURRENT_TIMESTAMP, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET "
                "updated_at = CURRENT_TIMESTAMP, frame_json = excluded.frame_json",
                (key, corrected_payload),
            )

    def record_correction(
        self,
        session_id: str,
        *,
        before_frame: dict[str, Any],
        after_frame: dict[str, Any],
        corrections: dict[str, Any],
        corrected_fields: list[str],
        expected_revision: Optional[int] = None,
    ) -> tuple[int, dict[str, Any]]:
        """Atomically supersede the active correction and persist a new revision."""
        if not session_id:
            raise ValueError("conversation correction requires a session id")
        before_payload = self._payload(before_frame, label="before frame")
        overrides_payload = self._payload(corrections, label="corrections")
        fields_payload = self._payload(corrected_fields, label="corrected fields")
        key = self._session_key(session_id)
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            active = conn.execute(
                "SELECT id, before_frame_json FROM conversation_corrections "
                "WHERE session_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
                (key,),
            ).fetchone()
            current_revision = int(active["id"]) if active is not None else None
            if current_revision != expected_revision:
                raise ValueError("conversation correction changed; retry")
            base_before = (
                str(active["before_frame_json"]) if active is not None else before_payload
            )
            conn.execute(
                "UPDATE conversation_corrections SET status = 'superseded', "
                "superseded_at = CURRENT_TIMESTAMP "
                "WHERE session_id = ? AND status = 'active'",
                (key,),
            )
            cur = conn.execute(
                "INSERT INTO conversation_corrections "
                "(session_id, status, overrides_json, corrected_fields_json, "
                "before_frame_json, after_frame_json) VALUES (?, 'active', ?, ?, ?, ?)",
                (key, overrides_payload, fields_payload, base_before, "{}"),
            )
            revision = int(cur.lastrowid)
            persisted_after = json.loads(
                json.dumps(after_frame, ensure_ascii=True, separators=(",", ":"))
            )
            correction = persisted_after.get("correction")
            if not isinstance(correction, dict):
                correction = {}
                persisted_after["correction"] = correction
            correction["revision"] = revision
            after_payload = self._payload(persisted_after, label="after frame")
            conn.execute(
                "UPDATE conversation_corrections SET after_frame_json = ? WHERE id = ?",
                (after_payload, revision),
            )
            conn.execute(
                "INSERT INTO conversation_state (session_id, updated_at, frame_json) "
                "VALUES (?, CURRENT_TIMESTAMP, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET "
                "updated_at = CURRENT_TIMESTAMP, frame_json = excluded.frame_json",
                (key, after_payload),
            )
            return revision, persisted_after

    def clear_correction(self, session_id: str) -> dict[str, Any]:
        """Clear the active correction and restore its original base frame."""
        if not session_id:
            raise ValueError("conversation correction requires a session id")
        key = self._session_key(session_id)
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            active = conn.execute(
                "SELECT overrides_json, corrected_fields_json, before_frame_json, "
                "after_frame_json FROM conversation_corrections "
                "WHERE session_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
                (key,),
            ).fetchone()
            if active is None:
                raise ValueError("no active conversation correction")
            restored_payload = str(active["before_frame_json"])
            restored = json.loads(restored_payload)
            if not isinstance(restored, dict):
                raise ValueError("stored base frame is invalid")
            conn.execute(
                "UPDATE conversation_corrections SET status = 'superseded', "
                "superseded_at = CURRENT_TIMESTAMP "
                "WHERE session_id = ? AND status = 'active'",
                (key,),
            )
            conn.execute(
                "INSERT INTO conversation_corrections "
                "(session_id, status, overrides_json, corrected_fields_json, "
                "before_frame_json, after_frame_json) VALUES (?, 'cleared', ?, ?, ?, ?)",
                (
                    key,
                    str(active["overrides_json"]),
                    str(active["corrected_fields_json"]),
                    str(active["after_frame_json"]),
                    restored_payload,
                ),
            )
            conn.execute(
                "INSERT INTO conversation_state (session_id, updated_at, frame_json) "
                "VALUES (?, CURRENT_TIMESTAMP, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET "
                "updated_at = CURRENT_TIMESTAMP, frame_json = excluded.frame_json",
                (key, restored_payload),
            )
        return restored

    def correction_history(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return newest-first correction lifecycle entries without raw session ids."""
        if not session_id:
            return []
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, created_at, superseded_at, status, overrides_json, "
                "corrected_fields_json FROM conversation_corrections "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (self._session_key(session_id), max(1, min(100, int(limit)))),
            ).fetchall()
        history: list[dict[str, Any]] = []
        for row in rows:
            try:
                overrides = json.loads(str(row["overrides_json"]))
                fields = json.loads(str(row["corrected_fields_json"]))
            except json.JSONDecodeError:
                continue
            history.append(
                {
                    "revision": int(row["id"]),
                    "created_at": str(row["created_at"]),
                    "superseded_at": (
                        str(row["superseded_at"]) if row["superseded_at"] else None
                    ),
                    "status": str(row["status"]),
                    "corrections": overrides if isinstance(overrides, dict) else {},
                    "corrected_fields": fields if isinstance(fields, list) else [],
                }
            )
        return history
