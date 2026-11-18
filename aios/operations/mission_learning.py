"""GAGOS's missions become the learning service's trajectories (2026-11-14).

The README's last steps of a mission are its learning: the trajectory is
captured, a candidate skill is drafted from it, the operator activates the
skill, and the clerk reuses it. None of it ran for GAGOS's missions. The
learning service (R15, :mod:`aios.application.learning.service`) read missions
from the operator's API store (``config.MISSION_STATE_DB``), while the
council's missions live in its runtime's own store; and until 2026-11-14
(#677) their verification and promotion were kept in memory only, so nothing
authoritative remained to learn from.

The capture (2026-11-14): a completed mission's trajectory is built from its
own authoritative records -- the council's mission, the durable verification
results and the terminal promotion -- and the learning service itself refuses
it when anything is not authoritative, current and strong enough. No model is
asked.

The skill (2026-11-15, the operator's word: "best of both"): the mission's own
writer drafts a candidate skill from the trajectory (:func:`draft_mission_skill`),
which the operator activates or leaves. An activated, signed mission skill
guides later goals of its kind: the local clerk judges that a goal is of that
kind (:func:`mission_skill_guidance`), the council and the writers are given
its procedure, and how the mission went raises or lowers the skill's
confidence (:func:`record_skill_outcome`). A mission skill is never a chat
recall and never a reflex. The local clerk doing such a goal itself first,
with the frontier as its escalation, is the step after this.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence


def _learning_service(runtime_root: Path) -> tuple[Any, Any, Any, Any]:
    """``(missions, verification, promotion, learning)`` over the council's
    mission store and the durable stores the mission's run kept its evidence
    in (#677)."""
    from aios import config
    from aios.api.deps import get_emergency_stop
    from aios.application.evidence.verification import VerificationAuthority
    from aios.application.learning.service import LearningService
    from aios.application.missions.mission_service import MissionService
    from aios.application.promotion.authority import PromotionAuthority
    from aios.application.workspaces.staged import StagedWorkspaceManager
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
    verification = VerificationAuthority(database_path=config.OPERATIONAL_STATE_DB_PATH)
    promotion = PromotionAuthority(
        StagedWorkspaceManager(config.EXECUTOR_WORKSPACE_ROOT),
        verification=verification,
        emergency_stop=emergency_stop,
        database_path=config.OPERATIONAL_STATE_DB_PATH,
    )
    learning = LearningService(
        mission_service=missions,
        trajectory_repository=TrajectoryRepository(config.OPERATIONAL_STATE_DB_PATH),
        verification_authority=verification,
        promotion_authority=promotion,
        emergency_stop=emergency_stop,
    )
    return missions, verification, promotion, learning


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
    from aios.core.verification_strength import VerificationStrength
    from aios.domain.evidence import VerificationPlanV1

    missions, verification, promotion_authority, learning = _learning_service(
        runtime_root
    )
    learning = service or learning
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


#: The memory of a GAGOS mission the council verified and promoted (organ 18,
#: 2026-11-14): the authority's own record, since no specialist store owns the
#: type, referring to the council's mission record, where its goal and files
#: are kept.
MISSION_MEMORY = "gagos_mission"
_MISSION_REFERENCE = "council-mission:"


def _mission_repository(runtime_root: Path) -> Any:
    from aios.infrastructure.missions.sqlite_mission_repository import (
        MISSIONS_DB_NAME,
        SqliteMissionRepository,
    )

    return SqliteMissionRepository(Path(runtime_root) / MISSIONS_DB_NAME)


def _remembered_contract(repository: Any, mission_id: str) -> Any | None:
    """The remembered mission's contract, or None when the council's store no
    longer holds it: a record gone from the store is no memory."""
    from aios.domain.missions.mission_repository import MissionNotFoundError

    try:
        return repository.get(mission_id).contract
    except MissionNotFoundError:
        return None


def remember_mission(
    mission_id: str, *, runtime_root: Path, authority: Any | None = None
) -> Any:
    """The council's completed mission *mission_id* as a memory: proposed and
    promoted through the Memory Authority with the mission's own verification
    results as its evidence, by policy, never by a model. Returns the record.

    Raises ``ValueError`` when the mission kept no evidence, and the
    authority's ``MemoryPromotionDenied`` when its checks refuse the evidence:
    stale, too weak, not passed, or not the mission's own."""
    from aios import config
    from aios.application.evidence.verification import VerificationAuthority
    from aios.core.verification_strength import VerificationStrength
    from aios.domain.memory import MemoryPromotionActor, MemoryProposal

    from aios.domain.missions.mission_state import MissionState

    record = _mission_repository(runtime_root).get(mission_id)
    if record.state is not MissionState.COMPLETED:
        # Tests that passed under a change the reviewer rejected are evidence,
        # but not of anything GAGOS did.
        raise ValueError(
            f"only a completed mission is remembered ({record.state.value})"
        )
    found = VerificationAuthority(
        database_path=config.OPERATIONAL_STATE_DB_PATH
    ).list_results_for_mission(mission_id)
    # Each piece of evidence once: a result whose evidence another already
    # declared adds nothing, and the authority refuses evidence given twice.
    results, declared = [], []
    for result in found:
        ids = tuple(result.evidence_ids or (result.verification_id,))
        if set(ids) & set(declared):
            continue
        results.append(result)
        declared.extend(ids)
    if not results:
        raise ValueError("the mission kept no verification result")
    proposal = MemoryProposal(
        proposal_id=f"mission-memory-{mission_id}",
        memory_type=MISSION_MEMORY,
        content_reference=f"{_MISSION_REFERENCE}{mission_id}",
        content_digest=record.contract_digest,
        source_principal="gagos",
        source_mission_id=mission_id,
        source_action_id=f"promotion:{mission_id}",
        evidence_ids=tuple(declared),
        required_strength=int(VerificationStrength.STRONG),
        policy_version="gagos-mission-memory/1",
        confidence_basis=(
            "verified in the sandbox, accepted by the reviewer and promoted by the "
            "council"
        ),
        requires_operator_approval=False,
        metadata={"files": list(record.contract.allowed_files)},
    )
    if authority is None:
        from aios.api.deps import get_memory_authority

        authority = get_memory_authority()
    authority.propose(proposal)
    return authority.promote(
        proposal,
        MemoryPromotionActor(
            actor_id="policy:gagos-mission-memory", actor_type="policy"
        ),
        evidence=tuple(results),
    )


def mission_memory_hints(
    files: Sequence[str],
    *,
    runtime_root: Path,
    authority: Any | None = None,
    limit: int = 20,
) -> list[str]:
    """What GAGOS remembers having done to any of *files*: one line for each
    remembered mission whose files overlap, from the council's own mission
    record. Read only and advisory: the council weighs it as context."""
    from aios.domain.memory import MemoryRecallContext

    if authority is None:
        from aios.api.deps import get_memory_authority

        authority = get_memory_authority()
    hits = authority.recall(
        "", MemoryRecallContext(memory_types=(MISSION_MEMORY,), limit=limit)
    )
    repository = _mission_repository(runtime_root)
    wanted = set(files)
    hints: list[str] = []
    for hit in hits:
        reference = str(hit.content_reference)
        if not reference.startswith(_MISSION_REFERENCE):
            continue
        mission_id = reference[len(_MISSION_REFERENCE) :]
        contract = _remembered_contract(repository, mission_id)
        shared = sorted(wanted & set(contract.allowed_files)) if contract else []
        if shared:
            hints.append(
                f"GAGOS already completed a mission on {', '.join(shared)}: "
                f"{' '.join(contract.goal.split())[:240]} (mission {mission_id}, "
                "verified, accepted and promoted)"
            )
    return hints


#: Bounds on what a drafter may write.
MAX_KIND_CHARS = 200
MAX_PROCEDURE_CHARS = 2_000
MAX_CONDITIONS = 6
MAX_CONDITION_CHARS = 200
#: The drafter's instructions: a skill is how to do goals of this kind, in
#: general, learned from the one mission it saw (2026-11-15). Every bound the
#: reader enforces is stated here from the same constants: until 2026-11-18 the
#: kind's 200 was not, and the first two completed missions' drafts were both
#: refused for a kind longer than that, so no mission skill was ever drafted.
MISSION_SKILL_SYSTEM = (
    "You write a skill for GAGOS, an AI operating system that improves its own "
    "code. GAGOS's council just completed the goal below: the change was verified "
    "in a sandbox, accepted by a reviewer and promoted. Write how GAGOS should do "
    "goals of the same kind in future, in general: not this goal's particulars, "
    "but the steps that made the change right. Answer with one JSON object and "
    "nothing else, holding exactly these fields:\n"
    '"kind": the kind of goal this skill is for, in one short line of at most '
    f"{MAX_KIND_CHARS} characters, general enough that a later goal of the same "
    "kind is recognised and narrow enough that another kind is not;\n"
    '"procedure": the steps, in plain prose, for a writer who will do such a goal '
    f"(at most {MAX_PROCEDURE_CHARS} characters);\n"
    f'"not_when": a list of at most {MAX_CONDITIONS} situations, each at most '
    f"{MAX_CONDITION_CHARS} characters, in which the skill must not be used;\n"
    f'"escalate_when": a list of at most {MAX_CONDITIONS} situations, each at most '
    f"{MAX_CONDITION_CHARS} characters, in which a stronger writer must take the "
    "goal instead."
)
#: What every mission skill's reuse is verified by: the mission's own steps.
MISSION_SKILL_OBSERVATIONS = ("sandbox:passed", "review:accepted")


def mission_skill_prompt(goal: str, files: Sequence[str], evidence: str) -> str:
    """What the drafter reads: the goal as it was given, its files, and the
    accepted change as the reviewer saw it (masked as the reviewer saw it)."""
    return (
        f"The goal, as the operator gave it:\n{goal.strip()}\n\n"
        f"Its files: {', '.join(files)}\n\n"
        f"The change that was verified, accepted and promoted:\n{evidence}"
    )


def read_skill_draft(raw: str) -> dict[str, Any]:
    """The drafter's answer, or ``ValueError`` saying why it is not one: exactly
    the four fields, within their bounds, and no injection in any of them --
    a procedure is read by later writers."""
    from aios.core.injection_scan import detect_injection

    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"the draft is not JSON: {exc}") from exc
    fields = {"kind", "procedure", "not_when", "escalate_when"}
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError(f"the draft must hold exactly {sorted(fields)}")
    kind, procedure = data["kind"], data["procedure"]
    if not isinstance(kind, str) or not 0 < len(kind.strip()) <= MAX_KIND_CHARS:
        raise ValueError(f"kind must be text of 1 to {MAX_KIND_CHARS} characters")
    if not isinstance(procedure, str) or not (
        0 < len(procedure.strip()) <= MAX_PROCEDURE_CHARS
    ):
        raise ValueError(
            f"procedure must be text of 1 to {MAX_PROCEDURE_CHARS} characters"
        )
    lists = {}
    for name in ("not_when", "escalate_when"):
        items = data[name]
        if (
            not isinstance(items, list)
            or len(items) > MAX_CONDITIONS
            or not all(
                isinstance(i, str) and 0 < len(i.strip()) <= MAX_CONDITION_CHARS
                for i in items
            )
        ):
            raise ValueError(
                f"{name} must be a list of at most {MAX_CONDITIONS} short texts"
            )
        lists[name] = tuple(i.strip() for i in items)
    for part in (kind, procedure, *lists["not_when"], *lists["escalate_when"]):
        why = detect_injection(part)
        if why:
            raise ValueError(f"the draft fails the injection check: {why}")
    return {
        "kind": " ".join(kind.split()),
        "procedure": procedure.strip(),
        **lists,
    }


def skill_scope(files: Sequence[str]) -> str:
    """The scope a mission skill applies in: the deepest folder holding every
    file of the mission it was learned from, as a pattern."""
    parents = [PurePosixPath(f).parent.parts for f in files]
    common: list[str] = []
    for level in zip(*parents):
        if len(set(level)) != 1:
            break
        common.append(level[0])
    return f"{'/'.join(common)}/*" if common else "*"


def draft_mission_skill(
    trajectory_id: str,
    *,
    runtime_root: Path,
    draft: Callable[[str, str], str],
    evidence: str,
    drafted_by: str,
    validated_version: str,
    service: Any | None = None,
) -> Any:
    """A candidate skill from the captured trajectory *trajectory_id* of a
    completed council mission (step 14 of the README's flow, 2026-11-15).

    The mission's own writer drafts what is intelligence -- the kind of goal,
    the procedure, when not to use it and when to escalate
    (:func:`read_skill_draft`); everything that is authority comes from the
    mission's records: its scope, its tools, its verification (sandbox and
    review, at strong strength) and the code it was validated on. The learning
    service qualifies the trajectory again before the candidate is kept.
    A candidate only: the operator activates it, or it stays one.

    *draft* is ``draft(prompt, system) -> answer``; *evidence* the accepted
    change as the reviewer saw it."""
    from aios.application.learning.service import SkillCandidateSpec
    from aios.application.memory.institutional_skills import MISSION_SKILL_SOURCE
    from aios.core.verification_strength import VerificationStrength
    from aios.domain.verification import SkillVerifierSpec

    missions, _verification, _promotion, learning = _learning_service(runtime_root)
    learning = service or learning
    trajectory = learning.trajectory_repository.get(trajectory_id)
    if trajectory is None:
        raise ValueError(f"no trajectory {trajectory_id}")
    record = missions.repository.get(trajectory.mission_id)
    files = list(record.contract.allowed_files)
    drafted = read_skill_draft(
        draft(
            mission_skill_prompt(record.contract.goal, files, evidence),
            MISSION_SKILL_SYSTEM,
        )
    )
    scope = skill_scope(files)
    candidate = SkillCandidateSpec(
        skill_id=f"gagos-{trajectory.mission_id}",
        version=1,
        problem_signature=trajectory.problem_signature,
        applicability_conditions={"kind": drafted["kind"]},
        known_exclusions=drafted["not_when"],
        required_inputs=("goal", "files"),
        required_project_state={},
        procedure=drafted["procedure"],
        allowed_tools=tuple(record.contract.allowed_tools),
        allowed_scope_pattern=scope,
        expected_observations=(
            "the change's tests pass in the sandbox against the base",
            "the chief reviewer accepts the change",
        ),
        verification_plan=SkillVerifierSpec(
            target_pattern=scope,
            required_observations=MISSION_SKILL_OBSERVATIONS,
            minimum_strength=int(VerificationStrength.STRONG),
        ),
        escalation_conditions=(
            *drafted["escalate_when"],
            "the change fails the sandbox or the review",
        ),
        validated_versions=(validated_version,),
    )
    return learning.create_skill_candidate(
        trajectory_id,
        candidate,
        provenance={
            "source": MISSION_SKILL_SOURCE,
            "mission_id": trajectory.mission_id,
            "trajectory_id": trajectory_id,
            "drafted_by": drafted_by,
            "kind": drafted["kind"],
        },
    )


@dataclass(frozen=True)
class SkillGuidance:
    """An active mission skill the clerk admitted for a goal: what the council
    and the writers are told of it."""

    skill_id: str
    version: int
    kind: str
    procedure: str

    def line(self) -> str:
        return (
            f"GAGOS learned how to do goals of this kind ({self.kind}; skill "
            f"{self.skill_id}@{self.version}, activated by the operator): "
            f"{self.procedure}"
        )

    def ref(self) -> dict[str, Any]:
        return {"skill_id": self.skill_id, "version": self.version}


#: Below this a mission skill is not offered: it has failed too often since
#: its activation.
MIN_GUIDANCE_CONFIDENCE = 0.8


def clerk_selects(service: Any, *, attempt: str) -> Callable[..., tuple[bool, str]]:
    """The local clerk's skill-selection job (organ 37's ``select_skill``,
    asked exactly as its qualification asks it): ``select(skill, goal=,
    files=) -> (admitted, why)``. The clerk can veto a skill, never grant one:
    it is asked only about a skill the operator activated, for a goal in the
    skill's scope."""
    from datetime import datetime, timedelta, timezone

    from aios.domain.local_workforce.contracts import LocalJobProfile, LocalJobRequest
    from aios.domain.local_workforce.skill_selection import (
        OUTPUT_SCHEMA,
        read_skill_selection,
        skill_selection_prompt,
    )

    def select(skill: Any, *, goal: str, files: Sequence[str]) -> tuple[bool, str]:
        kind = (skill.provenance or {}).get("kind") or skill.problem_signature
        request = LocalJobRequest(
            job_id=f"skill-{skill.skill_id}-v{skill.version}-{attempt}",
            job_profile=LocalJobProfile.SELECT_SKILL,
            input_schema_version="1.0",
            evidence_references=frozenset({skill.skill_id}),
            redacted_payload=skill_selection_prompt(
                problem_signature=kind,
                required_inputs=skill.required_inputs,
                known_exclusions=skill.known_exclusions,
                escalation_conditions=skill.escalation_conditions,
                inputs={"goal": goal, "files": list(files)},
                state={},
            ),
            token_budget=256,
            deadline=datetime.now(timezone.utc) + timedelta(seconds=180),
            required_output_schema=dict(OUTPUT_SCHEMA),
        )
        result = service.run_advisory_job(request)
        if result.status != "completed" or not result.structured_output:
            return (
                False,
                result.failure_reason or f"the clerk's job ended {result.status}",
            )
        answer = read_skill_selection(result.structured_output)
        if answer is None:
            return False, "the clerk's answer is not a skill selection"
        return answer.admits(), answer.reason

    return select


def mission_skill_guidance(
    goal: str,
    files: Sequence[str],
    *,
    principal: str,
    select: Callable[..., tuple[bool, str]],
    adapter: Any | None = None,
) -> tuple[list[SkillGuidance], list[str]]:
    """The operator's active mission skills that apply to *goal* (step 16 of
    the README's flow, 2026-11-15): ``(admitted, notes)``.

    Deterministic first: a skill the operator activated and signed for
    *principal*, confident enough, whose scope holds one of *files*. Then the
    local clerk judges whether the goal is of the skill's kind (*select*,
    :func:`clerk_selects`), and may only refuse. *notes* says why a skill in
    scope was not admitted. Advisory: guidance never blocks a goal."""
    if adapter is None:
        from aios.api.deps import get_memory_authority

        adapter = get_memory_authority().adapters.get("skills")
    mission_skills = getattr(adapter, "mission_skills", None)
    if mission_skills is None:
        return [], []
    admitted: list[SkillGuidance] = []
    notes: list[str] = []
    for skill in mission_skills(principal=principal):
        if not any(fnmatch(f, skill.allowed_scope_pattern) for f in files):
            continue
        name = f"{skill.skill_id}@{skill.version}"
        if skill.confidence < MIN_GUIDANCE_CONFIDENCE:
            notes.append(f"{name}: confidence {skill.confidence} after its failures")
            continue
        ok, why = select(skill, goal=goal, files=files)
        if not ok:
            notes.append(f"{name}: the clerk did not admit it ({why})")
            continue
        admitted.append(
            SkillGuidance(
                skill_id=skill.skill_id,
                version=skill.version,
                kind=(skill.provenance or {}).get("kind") or skill.problem_signature,
                procedure=skill.procedure,
            )
        )
    return admitted, notes


def record_skill_outcome(
    guided: Sequence[Mapping[str, Any]],
    *,
    success: bool,
    repository: Any | None = None,
) -> list[Any]:
    """Each mission skill that guided a mission learns how it went (organ 43's
    lifecycle): a completed mission raises its confidence, a mission whose
    change failed the sandbox or the review lowers it, and the library's own
    policy demotes a skill that keeps failing. Returns the updated records."""
    from aios.application.learning.skill_lifecycle import apply_reuse_outcome

    if repository is None:
        from aios import config
        from aios.domain.learning.repository import SkillRepository

        repository = SkillRepository(config.OPERATIONAL_STATE_DB_PATH)
    return [
        apply_reuse_outcome(
            repository,
            str(g["skill_id"]),
            int(g["version"]),
            success=success,
            reason=None if success else "verification",
        )
        for g in guided
    ]


__all__ = [
    "MISSION_MEMORY",
    "MISSION_SKILL_SYSTEM",
    "SkillGuidance",
    "capture_mission_trajectory",
    "clerk_selects",
    "draft_mission_skill",
    "mission_memory_hints",
    "mission_skill_guidance",
    "read_skill_draft",
    "record_skill_outcome",
    "remember_mission",
    "skill_scope",
]
