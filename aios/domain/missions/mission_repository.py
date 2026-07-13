from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from aios.domain.missions.mission_contract import MissionContract
from aios.domain.missions.mission_state import MissionState


class MissionNotFoundError(Exception):
    """Raised when a requested mission does not exist in the authoritative store."""


class MissionTransitionError(Exception):
    """Raised when a state transition violates the mission state machine."""


class MissionRecord:
    """Authoritative mission record stored by the repository."""

    def __init__(
        self,
        *,
        mission_id: str,
        parent_mission_id: str | None,
        turn_id: str | None,
        project_id: str | None,
        operator_id: str,
        contract: MissionContract,
        state: MissionState,
        contract_digest: str,
        capability_digest: str | None,
        policy_version: str,
        exported_path: str | None = None,
        created_at: str,
        updated_at: str,
    ) -> None:
        self.mission_id = mission_id
        self.parent_mission_id = parent_mission_id
        self.turn_id = turn_id
        self.project_id = project_id
        self.operator_id = operator_id
        self.contract = contract
        self.state = state
        self.contract_digest = contract_digest
        self.capability_digest = capability_digest
        self.policy_version = policy_version
        self.exported_path = exported_path
        self.created_at = created_at
        self.updated_at = updated_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "parent_mission_id": self.parent_mission_id,
            "turn_id": self.turn_id,
            "project_id": self.project_id,
            "operator_id": self.operator_id,
            "contract": self.contract.model_dump(mode="json"),
            "state": self.state.value,
            "contract_digest": self.contract_digest,
            "capability_digest": self.capability_digest,
            "policy_version": self.policy_version,
            "exported_path": self.exported_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class MissionRepository(ABC):
    """Abstract authoritative store for mission lifecycle state."""

    @abstractmethod
    def create(self, contract: MissionContract, state: MissionState = MissionState.DRAFT) -> MissionRecord:
        """Persist a new mission contract as the authoritative record."""

    @abstractmethod
    def get(self, mission_id: str) -> MissionRecord:
        """Return the authoritative mission record."""

    @abstractmethod
    def apply_transition(
        self,
        mission_id: str,
        to_state: MissionState,
        *,
        actor: str,
        reason: str | None = None,
        capability_digest: str | None = None,
    ) -> MissionRecord:
        """Atomically transition a mission if the transition is valid."""

    @abstractmethod
    def list_by_project(self, project_id: str) -> list[MissionRecord]:
        """Return missions for a project, newest first."""

    @abstractmethod
    def list_by_turn(self, turn_id: str) -> list[MissionRecord]:
        """Return missions for a turn, newest first."""

    @abstractmethod
    def list_active(self) -> list[MissionRecord]:
        """Return missions not in a terminal state."""

    @abstractmethod
    def transition_history(self, mission_id: str) -> list[dict[str, Any]]:
        """Return auditable transition history for a mission."""

    @abstractmethod
    def migrate_from_legacy(
        self,
        mission_id: str,
        contract: MissionContract,
        state: MissionState,
        *,
        exported_path: str | None = None,
    ) -> MissionRecord:
        """Import an existing mission artifact into the authoritative store."""


__all__ = [
    "MissionNotFoundError",
    "MissionRecord",
    "MissionRepository",
    "MissionTransitionError",
]
