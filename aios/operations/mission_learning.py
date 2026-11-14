"""GAGOS's missions become the learning service's trajectories (2026-11-14).

The README's last steps of a mission are its learning: the trajectory is
captured, a candidate skill is drafted from it, the operator activates the
skill, and the clerk reuses it. None of it ran for GAGOS's missions. The
learning service (R15, :mod:`aios.application.learning.service`) read missions
from the operator's API store (``config.MISSION_STATE_DB``), while the
council's missions live in its runtime's own store; and until 2026-11-14
(#677) their verification and promotion were kept in memory only, so nothing
authoritative remained to learn from.

This is the first step, the capture. A completed mission's trajectory is built
from its own authoritative records -- the council's mission, the durable
verification results and the terminal promotion -- and the learning service
itself refuses it when anything is not authoritative, current and strong
enough. No model is asked. Drafting a candidate skill and reusing one are the
steps after this.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence


def capture_mission_trajectory(
    mission_id: str,
    *,
    runtime_root: Path,
    observations: Sequence[Any],
    expert_provider: str,
    expert_model: str,
    project_digest: str,
    context_digest: str,
    proposal_digest: str,
    human_intervention_ids: Sequence[str] = (),
    service: Any | None = None,
) -> Any:
    """Capture the trajectory of the council mission *mission_id*, completed
    and promoted, into the learning store; returns the trajectory record.

    Raises ``ValueError`` (the learning service's own refusal, or a missing
    record said plainly) when the mission cannot be learned from."""
    from aios import config
    from aios.api.deps import get_emergency_stop
    from aios.application.evidence.verification import VerificationAuthority
    from aios.application.learning.service import LearningService
    from aios.application.missions.mission_service import MissionService
    from aios.application.promotion.authority import PromotionAuthority
    from aios.application.workspaces.staged import StagedWorkspaceManager
    from aios.core.verification_strength import VerificationStrength
    from aios.domain.evidence import VerificationPlanV1
    from aios.domain.learning.trajectory_repository import TrajectoryRepository
    from aios.infrastructure.missions.sqlite_mission_repository import (
        MISSIONS_DB_NAME,
        SqliteMissionRepository,
    )

    emergency_stop = get_emergency_stop()
    missions = MissionService(
        SqliteMissionRepository(Path(runtime_root) / MISSIONS_DB_NAME),
        export_dir=Path(runtime_root) / "mission_exports",
        emergency_stop=emergency_stop,
    )
    # The durable stores the mission's run kept its evidence in (#677).
    verification = VerificationAuthority(database_path=config.OPERATIONAL_STATE_DB_PATH)
    promotion_authority = PromotionAuthority(
        StagedWorkspaceManager(config.EXECUTOR_WORKSPACE_ROOT),
        verification=verification,
        emergency_stop=emergency_stop,
        database_path=config.OPERATIONAL_STATE_DB_PATH,
    )
    learning = service or LearningService(
        mission_service=missions,
        trajectory_repository=TrajectoryRepository(config.OPERATIONAL_STATE_DB_PATH),
        verification_authority=verification,
        promotion_authority=promotion_authority,
        emergency_stop=emergency_stop,
    )
    record = missions.repository.get(mission_id)
    results = verification.list_results_for_mission(mission_id)
    if not results:
        raise ValueError("the mission kept no verification result")
    promotion = promotion_authority.get_authoritative_terminal_promotion(mission_id)
    if promotion is None:
        raise ValueError("the mission kept no promotion")
    # The plan the council verified against, rebuilt from its own results:
    # each target, each test command, at the strength the council required.
    plan = VerificationPlanV1(
        intended_behavior=record.contract.goal,
        targets=tuple(dict.fromkeys(r.target for r in results)),
        required_tests=tuple(dict.fromkeys(r.command for r in results if r.command)),
        minimum_strength=min(
            int(VerificationStrength.STRONG),
            min(int(r.required_strength) for r in results),
        ),
    )
    return learning.capture_trajectory(
        mission=record,
        project_digest=project_digest,
        expert_provider=expert_provider,
        expert_model=expert_model,
        context_digest=context_digest,
        proposal_digest=proposal_digest,
        tool_observations=tuple(observations),
        verification_plan=plan,
        verification_results=results,
        promotion=promotion,
        human_intervention_ids=tuple(human_intervention_ids),
    )


__all__ = ["capture_mission_trajectory"]
