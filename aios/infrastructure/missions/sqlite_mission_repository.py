from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from aios import config
from aios.domain.missions.mission_contract import MissionContract
from aios.domain.missions.mission_repository import (
    MissionNotFoundError,
    MissionRecord,
    MissionRepository,
    MissionTransitionError,
)
from aios.domain.missions.mission_state import MissionState, MissionTransition
from aios.infrastructure.storage.migrations import apply_migrations


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class SqliteMissionRepository(MissionRepository):
    """SQLite-backed authoritative mission repository."""

    def __init__(self, db_path: str | Path = config.MISSION_STATE_DB) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            apply_migrations(conn)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> MissionRecord:
        return MissionRecord(
            mission_id=row["mission_id"],
            parent_mission_id=row["parent_mission_id"],
            turn_id=row["turn_id"],
            project_id=row["project_id"],
            operator_id=row["operator_id"],
            contract=MissionContract.model_validate_json(row["contract_json"]),
            state=MissionState(row["state"]),
            contract_digest=row["contract_digest"],
            runtime_contract_digest=row["runtime_contract_digest"],
            capability_digest=row["capability_digest"],
            policy_version=row["policy_version"],
            exported_path=row["exported_path"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create(
        self,
        contract: MissionContract,
        state: MissionState = MissionState.DRAFT,
        *,
        runtime_contract_digest: str | None = None,
    ) -> MissionRecord:
        digest = contract.digest()
        now = _utc_now()
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO missions (
                        mission_id, parent_mission_id, turn_id, project_id, operator_id,
                        contract_json, contract_digest, capability_digest, policy_version,
                        runtime_contract_digest, state, exported_path, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        contract.mission_id,
                        contract.parent_mission_id,
                        contract.turn_id,
                        contract.project_id,
                        contract.operator_id,
                        contract.model_dump_json(),
                        digest,
                        contract.capability_digest,
                        contract.policy_version,
                        runtime_contract_digest,
                        state.value,
                        None,
                        contract.created_at,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise MissionTransitionError(
                    f"mission {contract.mission_id!r} already exists"
                ) from exc
        return self.get(contract.mission_id)

    def get(self, mission_id: str) -> MissionRecord:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM missions WHERE mission_id = ?", (mission_id,)
            ).fetchone()
        if row is None:
            raise MissionNotFoundError(f"mission {mission_id!r} not found")
        return self._record_from_row(row)

    def apply_transition(
        self,
        mission_id: str,
        to_state: MissionState,
        *,
        actor: str,
        reason: str | None = None,
        capability_digest: str | None = None,
        contract_digest: str | None = None,
        authentication_event_id: str | None = None,
        session_id: str | None = None,
    ) -> MissionRecord:
        with self._connect() as conn:
            # Serialize read/validate/update so two concurrent approvals cannot
            # both observe AWAITING_APPROVAL and both transition it.
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT state, contract_digest FROM missions WHERE mission_id = ?",
                (mission_id,),
            ).fetchone()
            if row is None:
                raise MissionNotFoundError(f"mission {mission_id!r} not found")
            from_state = MissionState(row["state"])
            if not MissionTransition.is_allowed(from_state, to_state):
                raise MissionTransitionError(
                    f"invalid transition {from_state.value} -> {to_state.value}"
                )
            if to_state in {MissionState.APPROVED, MissionState.REJECTED}:
                if actor.strip().lower() in {
                    "system",
                    "orchestrator",
                    "council",
                    "planner",
                    "worker",
                    "scheduler",
                } or actor.startswith("orchestrator-auto-"):
                    raise MissionTransitionError(
                        "Human Sovereign operator is required for approval"
                    )
                if not capability_digest:
                    raise MissionTransitionError(
                        "exact capability digest is required for approval"
                    )
                if not contract_digest:
                    raise MissionTransitionError(
                        "contract digest is required for approval"
                    )
                if contract_digest != row["contract_digest"]:
                    raise MissionTransitionError(
                        "contract digest does not match authoritative mission"
                    )
                if not authentication_event_id or not session_id:
                    raise MissionTransitionError(
                        "authentication event and session are required for approval"
                    )
            now = _utc_now()
            if to_state in {MissionState.APPROVED, MissionState.REJECTED}:
                conn.execute(
                    "UPDATE missions SET state = ?, operator_id = ?, "
                    "capability_digest = ?, updated_at = ? WHERE mission_id = ?",
                    (to_state.value, actor, capability_digest, now, mission_id),
                )
            else:
                conn.execute(
                    "UPDATE missions SET state = ?, updated_at = ? WHERE mission_id = ?",
                    (to_state.value, now, mission_id),
                )
            conn.execute(
                """
                INSERT INTO mission_transitions (
                    mission_id, from_state, to_state, actor, reason,
                    capability_digest, contract_digest, authentication_event_id,
                    session_id, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    from_state.value,
                    to_state.value,
                    actor,
                    reason,
                    capability_digest,
                    contract_digest,
                    authentication_event_id,
                    session_id,
                    now,
                ),
            )
        return self.get(mission_id)

    def list_by_project(self, project_id: str) -> list[MissionRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM missions WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def list_by_turn(self, turn_id: str) -> list[MissionRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM missions WHERE turn_id = ? ORDER BY created_at DESC",
                (turn_id,),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def list_active(self) -> list[MissionRecord]:
        terminal = {s.value for s in (
            MissionState.COMPLETED, MissionState.FAILED, MissionState.REJECTED,
            MissionState.ROLLED_BACK, MissionState.KILLED, MissionState.BLOCKED,
        )}
        placeholders = ",".join("?" * len(terminal))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM missions WHERE state NOT IN ({placeholders}) ORDER BY created_at DESC",
                tuple(terminal),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def transition_history(self, mission_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT from_state, to_state, actor, reason, capability_digest,
                       contract_digest, authentication_event_id, session_id, recorded_at
                FROM mission_transitions
                WHERE mission_id = ?
                ORDER BY id ASC
                """,
                (mission_id,),
            ).fetchall()
        return [
            {
                "from_state": row["from_state"],
                "to_state": row["to_state"],
                "actor": row["actor"],
                "reason": row["reason"],
                "capability_digest": row["capability_digest"],
                "contract_digest": row["contract_digest"],
                "authentication_event_id": row["authentication_event_id"],
                "session_id": row["session_id"],
                "recorded_at": row["recorded_at"],
            }
            for row in rows
        ]

    def migrate_from_legacy(
        self,
        mission_id: str,
        contract: MissionContract,
        state: MissionState,
        *,
        exported_path: str | None = None,
    ) -> MissionRecord:
        digest = contract.digest()
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO missions (
                    mission_id, parent_mission_id, turn_id, project_id, operator_id,
                    contract_json, contract_digest, capability_digest, policy_version,
                    runtime_contract_digest, state, exported_path, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    contract.parent_mission_id,
                    contract.turn_id,
                    contract.project_id,
                    contract.operator_id,
                    contract.model_dump_json(),
                    digest,
                    contract.capability_digest,
                    contract.policy_version,
                    None,
                    state.value,
                    exported_path,
                    contract.created_at,
                    now,
                ),
            )
        return self.get(mission_id)


__all__ = ["SqliteMissionRepository"]
