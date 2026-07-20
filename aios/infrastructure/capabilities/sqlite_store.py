"""SQLite persistence for exact capabilities."""

from __future__ import annotations

import sqlite3
from contextlib import closing
import json
from pathlib import Path
from typing import Any

from aios.domain.capabilities.contracts import Capability, CapabilityBinding


class CapabilityStore:
    """Durable store with atomic one-time consumption."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = FULL")
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS capabilities (
                    capability_id TEXT PRIMARY KEY,
                    token_digest TEXT NOT NULL UNIQUE,
                    operator_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    authentication_event_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    route TEXT NOT NULL,
                    http_method TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    resource_digest TEXT NOT NULL,
                    mission_id TEXT,
                    contract_digest TEXT,
                    policy_version TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    verification_requirement TEXT NOT NULL,
                    issued_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    nonce TEXT NOT NULL,
                    action_payload_json TEXT,
                    consumed_at REAL,
                    revoked_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS capability_grant_cursors (
                    session_id TEXT NOT NULL,
                    route TEXT NOT NULL,
                    cleared_at REAL NOT NULL,
                    PRIMARY KEY(session_id, route)
                )
                """
            )
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(capabilities)").fetchall()
            }
            if "action_payload_json" not in columns:
                conn.execute(
                    "ALTER TABLE capabilities ADD COLUMN action_payload_json TEXT"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_capability_expiry ON capabilities(expires_at)"
            )
            conn.commit()

    @staticmethod
    def _binding_values(binding: CapabilityBinding) -> tuple[Any, ...]:
        return (
            binding.operator_id,
            binding.device_id,
            binding.authentication_event_id,
            binding.session_id,
            binding.action_type,
            binding.route,
            binding.http_method,
            binding.payload_digest,
            binding.resource_digest,
            binding.mission_id,
            binding.contract_digest,
            binding.policy_version,
            binding.scope,
            binding.verification_requirement,
        )

    def insert(self, capability: Capability, token_digest: str) -> None:
        b = capability.binding
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO capabilities(
                    capability_id, token_digest, operator_id, device_id,
                    authentication_event_id, session_id, action_type, route,
                    http_method, payload_digest, resource_digest, mission_id,
                    contract_digest, policy_version, scope,
                    verification_requirement, issued_at, expires_at, nonce,
                    action_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    capability.capability_id,
                    token_digest,
                    *self._binding_values(b),
                    capability.issued_at,
                    capability.expires_at,
                    capability.nonce,
                    (
                        json.dumps(
                            capability.action_payload,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        )
                        if capability.action_payload is not None
                        else None
                    ),
                ),
            )
            conn.commit()

    @staticmethod
    def _row_to_capability(row: sqlite3.Row) -> Capability:
        binding = CapabilityBinding(
            operator_id=str(row["operator_id"]),
            device_id=str(row["device_id"]),
            authentication_event_id=str(row["authentication_event_id"]),
            session_id=str(row["session_id"]),
            action_type=str(row["action_type"]),
            route=str(row["route"]),
            http_method=str(row["http_method"]),
            payload_digest=str(row["payload_digest"]),
            resource_digest=str(row["resource_digest"]),
            mission_id=str(row["mission_id"])
            if row["mission_id"] is not None
            else None,
            contract_digest=str(row["contract_digest"])
            if row["contract_digest"] is not None
            else None,
            policy_version=str(row["policy_version"]),
            scope=str(row["scope"]),
            verification_requirement=str(row["verification_requirement"]),
        )
        return Capability(
            capability_id=str(row["capability_id"]),
            binding=binding,
            issued_at=float(row["issued_at"]),
            expires_at=float(row["expires_at"]),
            nonce=str(row["nonce"]),
            action_payload=(
                json.loads(str(row["action_payload_json"]))
                if row["action_payload_json"] is not None
                else None
            ),
            consumed_at=float(row["consumed_at"])
            if row["consumed_at"] is not None
            else None,
            revoked_at=float(row["revoked_at"])
            if row["revoked_at"] is not None
            else None,
        )

    def by_token_digest(self, token_digest: str) -> Capability | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM capabilities WHERE token_digest = ?",
                (token_digest,),
            ).fetchone()
        return self._row_to_capability(row) if row is not None else None

    def consume_if_available(self, capability_id: str, now: float) -> bool:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "UPDATE capabilities SET consumed_at = ? WHERE capability_id = ? "
                "AND consumed_at IS NULL AND revoked_at IS NULL AND expires_at > ?",
                (now, capability_id, now),
            )
            conn.commit()
        return cur.rowcount == 1

    def clear_grants(self, session_id: str, route: str, now: float) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO capability_grant_cursors(session_id, route, cleared_at) "
                "VALUES (?, ?, ?) ON CONFLICT(session_id, route) DO UPDATE SET cleared_at = excluded.cleared_at",
                (session_id, route, now),
            )
            conn.commit()

    def consumed_for_session(
        self,
        session_id: str,
        route: str,
        now: float,
    ) -> list[Capability]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT c.* FROM capabilities AS c "
                "LEFT JOIN capability_grant_cursors AS g "
                "ON g.session_id = c.session_id AND g.route = c.route "
                "WHERE c.session_id = ? AND c.route = ? "
                "AND c.consumed_at IS NOT NULL AND c.expires_at > ? "
                "AND c.consumed_at > COALESCE(g.cleared_at, 0) "
                "ORDER BY c.consumed_at, c.issued_at",
                (session_id, route, now),
            ).fetchall()
        return [self._row_to_capability(row) for row in rows]

    def has_consumed(self) -> bool:
        """Return whether any exact capability has ever been consumed."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM capabilities WHERE consumed_at IS NOT NULL LIMIT 1"
            ).fetchone()
        return row is not None

    def consumed_count(self) -> int:
        """Return the durable count of consumed exact capabilities."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM capabilities WHERE consumed_at IS NOT NULL"
            ).fetchone()
        return int(row["n"])

    def revoke(self, capability_id: str, now: float) -> bool:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "UPDATE capabilities SET revoked_at = ? WHERE capability_id = ? "
                "AND revoked_at IS NULL AND consumed_at IS NULL",
                (now, capability_id),
            )
            conn.commit()
        return cur.rowcount == 1

    def revoke_all_active(self, now: float) -> int:
        """Revoke all unconsumed, non-expired capabilities atomically."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "UPDATE capabilities SET revoked_at = ? "
                "WHERE revoked_at IS NULL AND consumed_at IS NULL AND expires_at > ?",
                (now, now),
            )
            conn.commit()
        return int(cur.rowcount)
