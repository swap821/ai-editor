from __future__ import annotations

from pathlib import Path

import pytest

from aios.application.autonomy import GovernedAutonomy
from aios.core.autonomy import AutonomyLedger
from aios.core.verification_strength import VerificationStrength
from aios.domain.autonomy import (
    ActionClassKey,
    AutonomyDecisionStatus,
    AutonomyOutcome,
)


def _key(
    *,
    project_id: str = "project-1",
    policy_version: str = "policy-1",
    model_id: str = "local:model-1",
    action_type: str = "edit_file",
) -> ActionClassKey:
    return ActionClassKey(
        project_id=project_id,
        action_type=action_type,
        tool="edit_file",
        target="training_ground/example.py",
        path_class="training_ground/*.py",
        verification_plan_digest="verify-plan-1",
        policy_version=policy_version,
        model_id=model_id,
        data_classification="PROJECT_INTERNAL",
    )


def _outcome(
    *,
    passed: bool = True,
    strength: VerificationStrength = VerificationStrength.STRONG,
    **flags: bool,
) -> AutonomyOutcome:
    return AutonomyOutcome(passed=passed, strength=strength, **flags)


def _governed(tmp_path: Path, *, profile: str = "test", enabled: bool = True) -> GovernedAutonomy:
    return GovernedAutonomy(
        ledger=AutonomyLedger(db_path=tmp_path / "autonomy.db", min_successes=3),
        enabled=enabled,
        profile_name=profile,
        production_gate_open=profile != "production",
    )


def test_production_autonomy_is_disabled_even_if_the_ledger_has_evidence(tmp_path: Path) -> None:
    governed = _governed(tmp_path, profile="production", enabled=True)
    key = _key()
    for _ in range(3):
        governed.record_outcome(key, _outcome())
    decision = governed.evaluate(key)
    assert decision.status is AutonomyDecisionStatus.REQUIRE_CAPABILITY
    assert "AUTONOMY_DISABLED" in decision.reason_codes


def test_earned_autonomy_is_per_project_and_policy(tmp_path: Path) -> None:
    governed = _governed(tmp_path)
    key = _key()
    for _ in range(3):
        governed.record_outcome(key, _outcome())
    assert governed.evaluate(key).status is AutonomyDecisionStatus.ALLOW_AUTONOMOUS
    assert governed.evaluate(_key(project_id="project-2")).status is AutonomyDecisionStatus.REQUIRE_CAPABILITY
    assert governed.evaluate(_key(policy_version="policy-2")).status is AutonomyDecisionStatus.REQUIRE_CAPABILITY
    assert governed.evaluate(_key(model_id="local:model-2")).status is AutonomyDecisionStatus.REQUIRE_CAPABILITY


def test_weak_or_anomalous_outcomes_revoke_the_exact_class(tmp_path: Path) -> None:
    governed = _governed(tmp_path)
    key = _key()
    for _ in range(3):
        governed.record_outcome(key, _outcome())
    assert governed.evaluate(key).status is AutonomyDecisionStatus.ALLOW_AUTONOMOUS

    result = governed.record_outcome(
        key,
        _outcome(strength=VerificationStrength.WEAK, hidden_network=True),
    )
    assert result["status"] == "revoked"
    assert governed.evaluate(key).status is AutonomyDecisionStatus.REQUIRE_CAPABILITY


@pytest.mark.parametrize(
    "action_type,classification",
    [("network_request", "PROJECT_INTERNAL"), ("edit_file", "SECRET")],
)
def test_forbidden_action_classes_can_never_earn(
    tmp_path: Path, action_type: str, classification: str
) -> None:
    governed = _governed(tmp_path)
    key = _key(action_type=action_type).model_copy(
        update={"data_classification": classification}
    )
    assert governed.evaluate(key).status is AutonomyDecisionStatus.DENY


def test_cerebellum_is_only_a_proposal_source(tmp_path: Path) -> None:
    class Playbook:
        id = 7
        goal_pattern = "run the verified check"
        status = "compiled"

    class Cerebellum:
        def match(self, goal: str):
            assert goal == "run the verified check"
            return Playbook()

    governed = _governed(tmp_path)
    proposal = governed.propose_cerebellum(
        "run the verified check", _key(), cerebellum=Cerebellum()
    )
    assert proposal is not None
    assert proposal.requires_policy_evaluation is True
    assert governed.evaluate(_key()).status is AutonomyDecisionStatus.REQUIRE_CAPABILITY
