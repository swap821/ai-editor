"""Domain models for the Institutional Skill Library."""

from types import MappingProxyType
from typing import Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, model_validator

from aios.domain.verification import SkillVerifierSpec


SkillState = Literal[
    "candidate",
    "human_reviewed",
    "active",
    "probation",
    "degraded",
    "suspended",
    "revoked",
    "superseded",
    "deprecated",
    "blocked",
]
"""Slice 36 added `probation`, `suspended`, `revoked` -- each has a distinct
meaning from the states already here, not a synonym: `probation` is reduced-
trust reuse before a skill has earned full `active` status (distinct from
`human_reviewed`, which is pre-activation); `suspended` is an automatic,
confidence-driven, reviewable disablement (distinct from `blocked`, which is
an authority-imposed block); `revoked` is a permanent human decision
(distinct from `deprecated`, which means superseded by a newer version, not
that the skill was wrong). `active`/`degraded`/`superseded`/`deprecated`/
`blocked` already covered the brief's `trusted`/`degraded`/(none)/(none)/
(none) concepts, so were not duplicated.

Phase 2 removed `qualified`: it was declared here and nowhere else -- no
document defined it, no writer produced it, and no transition led into or out
of it -- so a record in that state made `transition_state` raise `KeyError`
instead of refusing. A state with no meaning is not kept as vocabulary."""


#: The skill lifecycle as pure policy: from each state, the states a skill may
#: move to. It is total over `SkillState` (a test pins that), so every
#: transition is either allowed here or refused with `ValueError`.
#:
#: "revoked" is reachable from every non-terminal state, not just adjacent
#: ones: the foundation law "human can stop, revoke and correct" (Slice 26)
#: means revocation is never gated behind the normal progression.
SKILL_TRANSITIONS: Mapping[SkillState, frozenset[SkillState]] = MappingProxyType(
    {
        "candidate": frozenset({"human_reviewed", "blocked", "deprecated", "revoked"}),
        "human_reviewed": frozenset(
            {"probation", "active", "blocked", "deprecated", "revoked"}
        ),
        "probation": frozenset(
            {"active", "degraded", "suspended", "blocked", "deprecated", "revoked"}
        ),
        "active": frozenset(
            {"degraded", "suspended", "superseded", "deprecated", "revoked"}
        ),
        "degraded": frozenset(
            {"human_reviewed", "suspended", "revoked", "blocked", "deprecated"}
        ),
        "suspended": frozenset({"human_reviewed", "revoked", "deprecated"}),
        "revoked": frozenset(),
        "superseded": frozenset(),
        "deprecated": frozenset(),
        "blocked": frozenset({"human_reviewed", "revoked", "deprecated"}),
    }
)

#: The one state a skill is born in. Every other state is reached through
#: `SKILL_TRANSITIONS`, so no write can put a skill straight into `active`:
#: activation stays a reviewed, capability-backed act.
BIRTH_STATE: SkillState = "candidate"

#: States a skill may still be moved INTO while the emergency stop is engaged.
#: Each takes the skill out of use and none moves it toward use: only `active`
#: skills pass applicability, and `human_reviewed`/`probation`/`active` are the
#: road there. A stop that blocked revocation would protect the skill, not the
#: operator.
WITHDRAWAL_STATES: frozenset[SkillState] = frozenset(
    {"degraded", "suspended", "revoked", "superseded", "deprecated", "blocked"}
)


def check_transition(current: SkillState, target: SkillState) -> None:
    """Refuse a transition the lifecycle does not allow."""
    if target not in SKILL_TRANSITIONS.get(current, frozenset()):
        raise ValueError(f"invalid skill transition {current!r} -> {target!r}")


class SkillContract(BaseModel):
    """An evidence-backed, reusable procedure extracted from a verified trajectory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    skill_id: str
    version: int
    problem_signature: str

    # Conditions that must be met to apply this skill
    applicability_conditions: Mapping[str, str]
    known_exclusions: Sequence[str]
    required_inputs: Sequence[str]
    required_project_state: Mapping[str, str]

    # The actual instruction/procedure
    procedure: str
    allowed_tools: Sequence[str]
    allowed_scope_pattern: str
    expected_observations: Sequence[str]

    # Gating and verification
    verification_plan: SkillVerifierSpec | None
    escalation_conditions: Sequence[str]

    # Provenance and reliability
    source_trajectory_ids: Sequence[str]
    confidence: float
    success_count: int
    failure_count: int
    last_validated_versions: Sequence[str]
    state: SkillState

    @model_validator(mode="before")
    @classmethod
    def _quarantine_legacy_verification_plan(cls, value):  # noqa: ANN001
        if isinstance(value, dict) and isinstance(value.get("verification_plan"), str):
            updated = dict(value)
            updated["verification_plan"] = None
            return updated
        return value
