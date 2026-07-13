from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from aios import config
from aios.domain.missions.mission_contract import MissionContract
from aios.domain.missions.mission_repository import (
    MissionRecord,
    MissionRepository,
    MissionTransitionError,
)
from aios.domain.missions.mission_state import MissionState


class MissionService:
    """Application service for the mission lifecycle state machine."""

    def __init__(
        self,
        repository: MissionRepository,
        *,
        export_dir: Path | None = None,
    ) -> None:
        self.repository = repository
        self.export_dir = export_dir or config.MISSION_EXPORT_DIR
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def create(self, contract: MissionContract) -> MissionRecord:
        """Create the authoritative mission record from a v1 contract."""
        return self.repository.create(contract, state=MissionState.DRAFT)

    def start_deliberation(self, mission_id: str) -> MissionRecord:
        return self.repository.apply_transition(
            mission_id,
            MissionState.DELIBERATING,
            actor="system",
            reason="Council deliberation started",
        )

    def request_approval(self, mission_id: str) -> MissionRecord:
        return self.repository.apply_transition(
            mission_id,
            MissionState.AWAITING_APPROVAL,
            actor="council",
            reason="Council passed deliberation",
        )

    def block(self, mission_id: str, reason: str) -> MissionRecord:
        return self.repository.apply_transition(
            mission_id,
            MissionState.BLOCKED,
            actor="council",
            reason=reason,
        )

    def approve(
        self,
        mission_id: str,
        *,
        operator_id: str,
        capability_digest: str,
    ) -> MissionRecord:
        """Approve a mission with an exact, single-use capability digest."""
        return self.repository.apply_transition(
            mission_id,
            MissionState.APPROVED,
            actor=operator_id,
            reason="Operator approved with capability",
            capability_digest=capability_digest,
        )

    def reject(self, mission_id: str, *, operator_id: str, reason: str) -> MissionRecord:
        return self.repository.apply_transition(
            mission_id,
            MissionState.REJECTED,
            actor=operator_id,
            reason=reason,
        )

    def start_execution(self, mission_id: str) -> MissionRecord:
        return self.repository.apply_transition(
            mission_id,
            MissionState.RUNNING,
            actor="system",
            reason="Worker execution started",
        )

    def start_verification(self, mission_id: str) -> MissionRecord:
        return self.repository.apply_transition(
            mission_id,
            MissionState.VERIFYING,
            actor="system",
            reason="Worker completed; verification started",
        )

    def complete(self, mission_id: str, *, evidence_digest: str | None = None) -> MissionRecord:
        return self.repository.apply_transition(
            mission_id,
            MissionState.COMPLETED,
            actor="system",
            reason=f"Verification passed; evidence={evidence_digest}",
        )

    def fail(self, mission_id: str, *, reason: str) -> MissionRecord:
        return self.repository.apply_transition(
            mission_id,
            MissionState.FAILED,
            actor="system",
            reason=reason,
        )

    def rollback(self, mission_id: str, *, operator_id: str, capability_digest: str) -> MissionRecord:
        return self.repository.apply_transition(
            mission_id,
            MissionState.ROLLED_BACK,
            actor=operator_id,
            reason="Operator rolled back mission",
            capability_digest=capability_digest,
        )

    def export(self, mission_id: str) -> Path:
        """Write the current mission record to disk as a non-authoritative export."""
        record = self.repository.get(mission_id)
        export = record.to_dict()
        export["_exported_at"] = _utc_now()
        export["_authority"] = "sqlite_mission_repository"
        export["_warning"] = "This file is an export; the SQLite missions table is authoritative."
        payload = json.dumps(export, sort_keys=True, indent=2)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        path = self.export_dir / f"{mission_id}-{digest}.json"
        path.write_text(payload, encoding="utf-8")
        return path

    def migrate_legacy_ledger(
        self,
        mission_id: str,
        contract: MissionContract,
        state: MissionState,
        *,
        legacy_export_path: str | None = None,
    ) -> MissionRecord:
        """Import a legacy JSON artifact into the authoritative repository."""
        return self.repository.migrate_from_legacy(
            mission_id,
            contract,
            state,
            exported_path=legacy_export_path,
        )

    def double_approve_guard(
        self,
        mission_id: str,
        *,
        operator_id: str,
        capability_digest: str,
    ) -> MissionRecord:
        """Idempotent approval: succeeds once; second identical call fails closed."""
        record = self.repository.get(mission_id)
        if record.state == MissionState.APPROVED:
            history = self.repository.transition_history(mission_id)
            for transition in history:
                if transition["to_state"] == MissionState.APPROVED.value:
                    if transition["capability_digest"] == capability_digest:
                        raise MissionTransitionError(
                            "capability already consumed for this mission"
                        )
                    raise MissionTransitionError(
                        "mission already approved with a different capability"
                    )
        return self.approve(
            mission_id,
            operator_id=operator_id,
            capability_digest=capability_digest,
        )


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = ["MissionService"]
