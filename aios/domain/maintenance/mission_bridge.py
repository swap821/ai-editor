"""Bridge converting maintenance findings to canonical missions."""

import uuid

from aios.domain.maintenance.contracts import MaintenanceFinding
from aios.domain.missions.mission_contract import (
    MissionContract,
    MissionBudget,
    VerificationPlan,
)
from aios.domain.verification import VerifierSpec


class MaintenanceMissionBridge:
    """Creates normal governed missions from maintenance findings."""

    @staticmethod
    def create_repair_mission(
        finding: MaintenanceFinding,
        operator_id: str,
        *,
        workspace_root: str | None = None,
    ) -> MissionContract:
        """Translate a finding into a standard MissionContract.

        This avoids duplicating mission execution or approval infrastructure for maintenance.
        The resulting mission binds precisely to the finding's target context.
        """
        mission_id = f"maint-{uuid.uuid4().hex[:8]}"

        metadata = {
            "finding_id": finding.finding_id,
            "finding_fingerprint": finding.fingerprint,
            "scanner_id": finding.scanner_id,
            "scanner_version": finding.scanner_version,
            "target_id": finding.target_id,
            "target_digest": finding.target_digest,
            "required_post_repair_rescan": True,
            "max_repair_attempts": 3,
            "escalation_condition": "Repeated verification failure or unresolved finding after rescan",
            "verification_spec": {
                "verifier_id": "maintenance.rescan",
                "version": "1",
                "scanner_id": finding.scanner_id,
                "scanner_version": finding.scanner_version,
                "target_id": finding.target_id,
                "rescan_of": finding.fingerprint,
                "allowed_root": workspace_root or "",
            },
        }
        structured_verifiers = ()
        if workspace_root:
            structured_verifiers = (
                VerifierSpec(
                    scanner_id=finding.scanner_id,
                    scanner_version=finding.scanner_version,
                    target_id=finding.target_id,
                    rescan_of=finding.fingerprint,
                    allowed_root=workspace_root,
                ),
            )

        return MissionContract(
            mission_id=mission_id,
            operator_id=operator_id,
            goal=f"Repair maintenance finding {finding.finding_id}: {finding.deterministic_evidence}",
            worker_type="code",
            created_by="AutonomousMaintenanceForce",
            risk_level="YELLOW",  # Typically YELLOW because it writes to code
            requires_approval=True,
            budget=MissionBudget(max_workers=1, max_steps=12, timeout_seconds=600),
            allowed_files=[finding.target_id],
            allowed_tools=["read_file", "edit_file", "run_verification"],
            verification_plan=VerificationPlan(
                required_strength="moderate",
                verifiers=structured_verifiers,
            ),
            metadata={
                **metadata,
                "worker_strategy": "code",
                "executor_policy": "private_service",
            },
            workspace_root=workspace_root,
        )
