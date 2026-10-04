"""Plan Phase 5, slice 5b: a reflex fires only if its skill applies here, now.

Operator decisions, 2026-09-29: "1+2 both honestly" -- ``Cerebellum.match``
asks ``SkillApplicabilityEngine`` (the governed stack's own definition of "this
skill applies") and fails closed, AND a skill carries the structured contract
that engine demands, derived from its own steps (``reflex_contract``). Read-only
reflexes get a freshness plan: the files they read must be exactly a version
they were validated on (threat T7).

What follows from it, and is pinned here: a GREEN command that is not a test
runner has no plan, so it never serves a turn; a test-runner reflex passes the
engine but its YELLOW step is still withheld by reflex authority; a read-only
reflex runs with no model -- only on code it was validated on.

Operator decision, 2026-10-04: re-validation is his act only. A reflex
that matches stale code is withdrawn (skill suspended, row retired) and
returns only by his re-activation, which records the code as it is.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from aios import config
from aios.agents.tool_agent import ToolAgent
from aios.application.governance.emergency_stop import (
    EmergencyStopController,
    EmergencyStopHooks,
)
from aios.application.learning.service import (
    LearningService,
    SkillActivationAuthorization,
)
from aios.application.memory import reflex_contract
from aios.application.memory.institutional_skills import (
    InstitutionalSkillAdapter,
    SkillTrailIndex,
)
from aios.application.missions.mission_service import MissionService
from aios.core.autonomy import UNGOVERNED_FIXTURE
from aios.core.cerebellum import Cerebellum
from aios.core.executor import Executor
from aios.core.verification_strength import VerificationStrength
from aios.domain.capabilities.proof import ConsumedCapabilityProof
from aios.domain.governance.contracts import EmergencyStopRequest
from aios.domain.learning.applicability import (
    ApplicabilityError,
    SkillApplicabilityEngine,
)
from aios.domain.learning.repository import SkillRepository
from aios.domain.learning.trajectory_repository import TrajectoryRepository
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)
from aios.memory import learning_freeze
from aios.memory.db import get_connection, init_memory_db
from aios.security import scope_lock
from aios.security.gateway import RateLimiter

GOAL = "show the release notes"
STEPS = ["read_file: filepath=notes.md"]
STALE = "Validated project version does not match the skill"


class Bus:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def append(self, event: Any) -> int:
        self.events.append(event)
        return len(self.events)

    def reasons(self) -> list[str]:
        return [
            e.payload["reason"]
            for e in self.events
            if isinstance(getattr(e, "payload", None), dict)
            and e.payload.get("decision") == "abstained"
        ]


class World:
    def __init__(self, root: Path) -> None:
        self.project = root / "project"
        self.memory_db = root / "memory.sqlite"
        self.operational = root / "operational.sqlite"
        init_memory_db(self.memory_db)
        self.repository = SkillRepository(self.operational)
        self.library = InstitutionalSkillAdapter(
            self.repository, SkillTrailIndex(self.operational)
        )
        self.bus = Bus()
        self.cerebellum = Cerebellum(self.memory_db, bus=self.bus)
        self.cerebellum.attach_reflex_gate(self.library)

    def write(self, name: str, text: str) -> None:
        (self.project / name).write_text(text, encoding="utf-8")

    def earn(self, goal: str = GOAL, steps: list[str] = STEPS) -> int:
        trail = 0
        for _ in range(3):
            trail = self.library.record_attempt(
                goal,
                steps,
                success=True,
                strength=VerificationStrength.STRONG,
                principal="principal:test",
            )
        return trail

    def record(self, goal: str = GOAL):
        (record,) = [
            r for r in self.repository.list_skills() if r.problem_signature == goal
        ]
        return record

    def activate(self, goal: str = GOAL) -> None:
        record = self.record(goal)
        self.repository.transition_state(
            record.skill_id, record.version, "human_reviewed"
        )
        self.repository.transition_state(record.skill_id, record.version, "active")
        self.cerebellum.try_compile_all()

    def playbook_statuses(self) -> list[str]:
        with get_connection(self.memory_db) as conn:
            return [
                str(row["status"])
                for row in conn.execute("SELECT status FROM compiled_playbooks")
            ]

    def live(self, goal: str = GOAL, steps: list[str] = STEPS) -> int:
        trail = self.earn(goal, steps)
        self.activate(goal)
        return trail


@pytest.fixture
def world(tmp_path, monkeypatch) -> World:
    """A project of its own: file tools read it (``config.PROJECT_ROOT``, the
    agent's read root) and commands run in it (the scope root's parent)."""
    monkeypatch.setattr(
        learning_freeze, "_latch_path", lambda: tmp_path / "emergency_stop.db"
    )
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    project = tmp_path / "project"
    (project / "training_ground").mkdir(parents=True)
    monkeypatch.setattr(config, "PROJECT_ROOT", project)
    original = scope_lock.get_scope_roots()
    scope_lock.set_scope_roots([project / "training_ground"])
    w = World(tmp_path)
    w.write("notes.md", "release notes v1\n")
    try:
        yield w
    finally:
        scope_lock.set_scope_roots(list(original))


# ------------------------------------------------------------ the contract


@pytest.mark.parametrize(
    ("steps", "target", "observation"),
    [
        (
            ["verify: command=pytest tests/test_x.py -q"],
            "tests/test_x.py",
            reflex_contract.REUSE_OBSERVATION,
        ),
        (
            ["read_file: filepath=docs/a.md", "read_directory: path=docs"],
            "docs/a.md",
            reflex_contract.FRESHNESS_OBSERVATION,
        ),
        (["verify: command=echo hello"], None, None),
        (["create_file: filepath=x.py"], None, None),
        (["read_file: filepath=a.md", "verify: command=echo a.md"], None, None),
        (["verify: command=echo running pytest x.py"], None, None),
    ],
)
def test_the_plan_comes_from_the_arcs_own_steps(steps, target, observation) -> None:
    plan = reflex_contract.verification_plan(steps)
    if target is None:
        assert plan is None
        return
    assert plan is not None
    assert plan.verifier_id == "skill.reuse" and plan.version == "1"
    assert plan.target_pattern == target
    assert plan.required_observations == (observation,)


def test_a_skill_is_born_with_its_contract(world) -> None:
    trail = world.earn()
    record = world.record()
    assert record.verification_plan == reflex_contract.verification_plan(STEPS)
    assert record.allowed_scope_pattern == reflex_contract.scope_identity()
    assert record.source_trajectory_ids == [
        reflex_contract.trail_reference(record.skill_id, record.version)
    ]
    assert record.last_validated_versions == [reflex_contract.validated_version(STEPS)]
    assert world.library.record_for_trail(trail) == record


def test_an_unverified_birth_vouches_for_nothing(world) -> None:
    world.library.record_attempt(GOAL, STEPS, success=False, principal="principal:test")
    record = world.record()
    assert record.source_trajectory_ids == []
    assert record.last_validated_versions == []


def test_one_verified_success_carries_its_evidence_reference(world) -> None:
    world.library.record_attempt(
        GOAL,
        STEPS,
        success=True,
        strength=VerificationStrength.STRONG,
        principal="principal:test",
    )
    record = world.record()
    assert record.source_trajectory_ids == [
        reflex_contract.trail_reference(record.skill_id, record.version)
    ]
    assert record.last_validated_versions == [reflex_contract.validated_version(STEPS)]


def test_a_failure_born_skill_gets_its_reference_with_its_first_success(
    world,
) -> None:
    world.library.record_attempt(GOAL, STEPS, success=False, principal="principal:test")
    assert world.record().source_trajectory_ids == []
    world.library.record_attempt(
        GOAL,
        STEPS,
        success=True,
        strength=VerificationStrength.STRONG,
        principal="principal:test",
    )
    record = world.record()
    assert record.source_trajectory_ids == [
        reflex_contract.trail_reference(record.skill_id, record.version)
    ]


def test_versions_are_capped_newest_last() -> None:
    versions = [f"v{i}" for i in range(25)]
    kept = reflex_contract.with_validated(versions, "v3")
    assert len(kept) == reflex_contract.MAX_VALIDATED_VERSIONS
    assert kept[-1] == "v3" and kept.count("v3") == 1


# ------------------------------------------------------------ freshness


def test_a_live_read_only_reflex_fires(world) -> None:
    world.live()
    assert world.cerebellum.match(GOAL, principal="principal:test") is not None


def test_a_changed_file_refuses_the_reflex_and_withdraws_it(world) -> None:
    """Operator decision, 2026-10-04: re-validation is his act only, so a
    stale reflex is taken out of service like a retired one."""
    world.live()
    world.write("notes.md", "release notes v2: someone edited this\n")
    assert world.cerebellum.match(GOAL, principal="principal:test") is None
    assert any(STALE in reason for reason in world.bus.reasons())
    assert world.record().state == "suspended"
    assert world.playbook_statuses() == ["retired"]


def test_a_listing_goes_stale_when_an_entry_is_added(world) -> None:
    """A directory's version is its listing as ``read_directory`` reads it."""
    (world.project / "docs").mkdir()
    world.write("docs/a.md", "a\n")
    world.live("list the docs", ["read_directory: path=docs"])
    assert (
        world.cerebellum.match("list the docs", principal="principal:test") is not None
    )
    world.write("docs/b.md", "b\n")
    assert world.cerebellum.match("list the docs", principal="principal:test") is None
    assert world.record("list the docs").state == "suspended"


def test_an_edit_undone_before_any_match_withdraws_nothing(world) -> None:
    """Only a stale MATCH withdraws: what counts is the code it would run on."""
    world.live()
    world.write("notes.md", "release notes v2\n")
    world.write("notes.md", "release notes v1\n")
    assert world.cerebellum.match(GOAL, principal="principal:test") is not None


def test_reverting_the_file_does_not_bring_a_withdrawn_reflex_back(world) -> None:
    world.live()
    world.write("notes.md", "release notes v2\n")
    assert world.cerebellum.match(GOAL, principal="principal:test") is None
    world.write("notes.md", "release notes v1\n")
    world.cerebellum.try_compile_all()
    assert world.cerebellum.match(GOAL, principal="principal:test") is None


def test_a_verified_success_does_not_revalidate_a_reviewed_skill(world) -> None:
    world.live()
    world.write("notes.md", "release notes v2\n")
    before = world.record().last_validated_versions
    world.library.record_attempt(
        GOAL,
        STEPS,
        success=True,
        strength=VerificationStrength.STRONG,
        principal="principal:test",
    )
    assert world.record().last_validated_versions == before
    assert world.cerebellum.match(GOAL, principal="principal:test") is None
    assert world.record().state == "suspended"


def test_a_stale_reflex_returns_only_by_reactivation(world, tmp_path) -> None:
    world.live()
    world.write("notes.md", "release notes v2\n")
    assert world.cerebellum.match(GOAL, principal="principal:test") is None
    for _ in range(3):
        world.library.record_attempt(
            GOAL,
            STEPS,
            success=True,
            strength=VerificationStrength.STRONG,
            principal="principal:test",
        )
    world.cerebellum.try_compile_all()
    assert world.cerebellum.match(GOAL, principal="principal:test") is None
    record = world.record()
    _service(world, tmp_path).activate_skill(
        _authorization(record.skill_id, record.version)
    )
    world.cerebellum.try_compile_all()
    assert world.cerebellum.match(GOAL, principal="principal:test") is not None


def test_the_stop_freezes_the_withdrawal(world, tmp_path) -> None:
    """While learning is frozen nothing about a reflex moves, as for
    decompilation: it is refused, not withdrawn."""
    world.live()
    _engage(tmp_path)
    world.write("notes.md", "release notes v2\n")
    assert world.cerebellum.match(GOAL, principal="principal:test") is None
    assert world.record().state == "active"


def test_a_refusal_that_is_not_staleness_withdraws_nothing(world, tmp_path) -> None:
    world.live()
    other = tmp_path / "elsewhere" / "training_ground"
    other.mkdir(parents=True)
    scope_lock.set_scope_roots([other])
    assert world.cerebellum.match(GOAL, principal="principal:test") is None
    assert any("scope does not match" in r for r in world.bus.reasons())
    assert world.record().state == "active"


def test_staleness_is_the_engines_own_refusal(world) -> None:
    """``STALE_REFUSAL`` is pinned to the engine's wording, so a reworded
    engine cannot silently turn staleness into an ordinary refusal."""
    world.live()
    record = world.record()
    with pytest.raises(ApplicabilityError) as refused:
        SkillApplicabilityEngine().check_applicability(
            record,
            {},
            {},
            current_scope=record.allowed_scope_pattern,
            mission_allowed_tools=sorted(reflex_contract.REFLEX_TOOLS),
            validated_version="not-a-validated-version",
            verification_plan_executable=True,
            policy_allows=True,
        )
    assert str(refused.value) == reflex_contract.STALE_REFUSAL
    assert world.library.is_stale(str(refused.value))
    assert not world.library.is_stale("Policy does not allow skill reuse")


# ------------------------------------------------------------ re-validation


def _stale_candidate(world: World) -> list[str]:
    """An earned skill the operator has NOT activated, whose file then moved."""
    world.earn()
    world.write("notes.md", "release notes v2\n")
    return world.record().last_validated_versions


def test_a_candidates_verified_success_records_the_code_it_ran_on(world) -> None:
    before = _stale_candidate(world)
    world.library.record_attempt(
        GOAL,
        STEPS,
        success=True,
        strength=VerificationStrength.STRONG,
        principal="principal:test",
    )
    assert world.record().last_validated_versions == [
        *before,
        reflex_contract.validated_version(STEPS),
    ]


def test_a_success_elsewhere_vouches_for_nothing_here(world) -> None:
    """Arc identity ignores arguments, so this success lands on the same skill;
    it verified other.md, not notes.md, so it may not vouch for notes.md."""
    world.write("other.md", "other\n")
    before = _stale_candidate(world)
    world.library.record_attempt(
        GOAL,
        ["read_file: filepath=other.md"],
        success=True,
        strength=VerificationStrength.STRONG,
        principal="principal:test",
    )
    assert world.record().last_validated_versions == before


def test_a_failure_revalidates_nothing(world) -> None:
    before = _stale_candidate(world)
    world.library.record_attempt(GOAL, STEPS, success=False, principal="principal:test")
    assert world.record().last_validated_versions == before


def test_a_weak_success_revalidates_nothing(world) -> None:
    before = _stale_candidate(world)
    world.library.record_attempt(
        GOAL,
        STEPS,
        success=True,
        strength=VerificationStrength.WEAK,
        principal="principal:test",
    )
    assert world.record().last_validated_versions == before


# ------------------------------------------------------------ the other gates


def test_a_green_command_has_no_plan_and_never_fires(world) -> None:
    """Naming a real file does not make an ``echo`` a verification."""
    world.live("print the banner", ["verify: command=echo notes.md"])
    assert (
        world.cerebellum.match("print the banner", principal="principal:test") is None
    )
    assert any(
        "verification plan is not an admitted structured verifier" in reason
        for reason in world.bus.reasons()
    )


def test_a_test_runner_reflex_passes_the_engine(world) -> None:
    """It applies; whether its YELLOW step may run is reflex authority's
    question, not this one (``test_phase2_reflex_gate`` asks it)."""
    (world.project / "training_ground" / "test_t.py").write_text(
        "def test_t():\n    assert True\n", encoding="utf-8"
    )
    trail = world.live(
        "run the t tests", ["verify: command=pytest training_ground/test_t.py -q"]
    )
    assert world.library.reflex_applicability(trail) is None
    assert (
        world.cerebellum.match("run the t tests", principal="principal:test")
        is not None
    )


def test_a_plan_runs_only_on_a_target_that_exists_or_that_it_creates(world) -> None:
    steps = ["verify: command=pytest training_ground/test_t.py -q"]
    plan = reflex_contract.verification_plan(steps)
    assert not reflex_contract.plan_executable(plan, steps)
    creates = ["create_file: filepath=training_ground/test_t.py", *steps]
    assert reflex_contract.plan_executable(plan, creates)
    (world.project / "training_ground" / "test_t.py").write_text(
        "def test_t():\n    assert True\n", encoding="utf-8"
    )
    assert reflex_contract.plan_executable(plan, steps)
    assert not reflex_contract.plan_executable(None, steps)


def test_a_reactivated_skill_whose_test_is_gone_is_refused(world, tmp_path) -> None:
    """The one case freshness cannot catch: the operator re-activates the skill
    after its test file was deleted, so the code as it is -- test missing -- is
    a validated version. Its plan still cannot run, so it does not apply."""
    target = world.project / "training_ground" / "test_t.py"
    target.write_text("def test_t():\n    assert True\n", encoding="utf-8")
    steps = ["verify: command=pytest training_ground/test_t.py -q"]
    trail = world.live("run the t tests", steps)
    record = world.record("run the t tests")
    world.repository.transition_state(record.skill_id, record.version, "suspended")
    target.unlink()
    _service(world, tmp_path).activate_skill(
        _authorization(record.skill_id, record.version)
    )
    assert world.library.reflex_applicability(trail) == (
        "Skill verification plan is not executable"
    )


def test_another_scope_refuses_it(world, tmp_path) -> None:
    trail = world.live()
    other = tmp_path / "elsewhere" / "training_ground"
    other.mkdir(parents=True)
    scope_lock.set_scope_roots([other])
    refusal = world.library.reflex_applicability(trail)
    assert refusal is not None and "scope does not match" in refusal


def _engage(data: Path) -> None:
    """Engage the real learning latch (its path is the test's own)."""
    EmergencyStopController(
        data / "emergency_stop.db",
        hooks=EmergencyStopHooks(
            revoke_capabilities=lambda *a, **k: None,
            cancel_queued_missions=lambda *a, **k: None,
            kill_active_workers=lambda *a, **k: None,
            disable_autonomy=lambda *a, **k: None,
            preserve_evidence=lambda *a, **k: None,
        ),
    ).engage(
        EmergencyStopRequest(
            operator_id="operator:test",
            authentication_event_id="event:engage",
            reason="5b policy test",
        )
    )


def test_the_stop_refuses_reuse(world, tmp_path) -> None:
    trail = world.live()
    assert world.library.reflex_applicability(trail) is None
    _engage(tmp_path)
    assert world.library.reflex_applicability(trail) == (
        "Policy does not allow skill reuse"
    )


def test_an_unknown_trail_refuses(world) -> None:
    assert world.library.reflex_applicability(99_999) == "skill not found"


class _NoVerdict:
    """A gate that can say what is active but not whether it applies."""

    def __init__(self, library: InstitutionalSkillAdapter) -> None:
        self._library = library

    def __getattr__(self, name: str) -> Any:
        if name == "reflex_applicability":
            raise AttributeError(name)
        return getattr(self._library, name)


class _Unreadable(_NoVerdict):
    def __getattr__(self, name: str) -> Any:
        if name == "reflex_applicability":

            def broken(_trail: int) -> str:
                raise RuntimeError("library offline")

            return broken
        return getattr(self._library, name)


@pytest.mark.parametrize(
    ("gate", "reason"),
    [
        (_NoVerdict, "no skill library can vouch for it"),
        (_Unreadable, "applicability unreadable"),
    ],
)
def test_no_verdict_is_a_refusal(world, gate, reason) -> None:
    """A gate is attached once and never replaced, so this is a second
    cerebellum over the same compiled reflex, wired to a gate without one."""
    world.live()
    assert world.cerebellum.match(GOAL, principal="principal:test") is not None
    bus = Bus()
    cerebellum = Cerebellum(world.memory_db, bus=bus)
    cerebellum.attach_reflex_gate(gate(world.library))
    assert cerebellum.match(GOAL, principal="principal:test") is None
    assert any(reason in r for r in bus.reasons())


# ------------------------------------------------------------ the live turn


class _Runner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, command, *, cwd, env, timeout_s):
        self.calls.append(command)
        return "", "", 0


class _Chat:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def chat(self, messages, *, tools=None, model=None) -> dict:
        self.calls.append(copy.deepcopy(messages))
        return {"role": "assistant", "content": "done"}


def _turn(cerebellum: Cerebellum, text: str) -> tuple[list[str], _Chat]:
    chat = _Chat()
    executor = Executor(
        runner=_Runner(),
        rate_limiter=RateLimiter(),
        audit_log=lambda *a, **k: None,
        emergency_stop=UNGOVERNED_FIXTURE,
    )
    agent = ToolAgent(
        chat,
        executor,
        max_iters=2,
        cerebellum=cerebellum,
        audit_log=lambda *a, **k: None,
        principal="principal:test",
    )
    events = list(agent.run([{"role": "user", "content": text}]))
    return [str(e.get("type")) for e in events if isinstance(e, dict)], chat


def test_a_stale_reflex_falls_back_to_the_model(world) -> None:
    """T7's executed differential. The reel cannot change the code file tools
    read (it never writes the repository), so it is proven here: the same
    read-only reflex serves a turn with no model, and after its file changes it
    replays nothing and the model answers."""
    world.live()
    types, chat = _turn(world.cerebellum, GOAL)
    assert "cerebellum_done" in types and chat.calls == []
    world.write("notes.md", "release notes v2\n")
    types, chat = _turn(world.cerebellum, GOAL)
    assert not {"cerebellum_step", "cerebellum_done"} & set(types)
    assert chat.calls


# ------------------------------------------------------------ one derivation


def test_targets_are_read_where_the_replay_touches_them(world, tmp_path) -> None:
    """A command runs in ``scope_lock.command_cwd()``; a file tool reads the
    agent's read root. Hashing a command's target under the read root instead
    would vouch for a file the replay never touches."""
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "training_ground").mkdir(parents=True)
    scope_lock.set_scope_roots([elsewhere / "training_ground"])
    steps = ["verify: command=pytest training_ground/test_t.py -q"]
    ran_here = elsewhere / "training_ground" / "test_t.py"
    decoy = world.project / "training_ground" / "test_t.py"
    ran_here.write_text("def test_t():\n    assert True\n", encoding="utf-8")
    plan = reflex_contract.verification_plan(steps)
    assert reflex_contract.plan_executable(plan, steps)
    before = reflex_contract.validated_version(steps)
    decoy.write_text("anything\n", encoding="utf-8")
    assert reflex_contract.validated_version(steps) == before
    ran_here.write_text("def test_t():\n    assert False\n", encoding="utf-8")
    assert reflex_contract.validated_version(steps) != before


# ------------------------------------------------------------ activation


def _authorization(skill_id: str, version: int) -> SkillActivationAuthorization:
    return SkillActivationAuthorization(
        skill_id=skill_id,
        version=version,
        proof=ConsumedCapabilityProof(
            capability_id="cap-5b",
            token_digest="token-digest",
            operator_id="operator-1",
            device_id="device-1",
            authentication_event_id="auth-1",
            session_id="session-1",
            action_type="skill_activation",
            route=f"/api/v1/skills/{skill_id}/versions/{version}/activate",
            http_method="POST",
            payload_digest="payload-digest",
            resource_digest="resource-digest",
            mission_id=None,
            contract_digest=None,
            policy_version="1.0",
            scope="skill-activation",
            verification_requirement="route_policy_v1",
            consumed_at=1.0,
            expires_at=9_999_999_999.0,
            revoked_at=None,
        ),
    )


def _service(world: World, tmp_path: Path) -> LearningService:
    return LearningService(
        mission_service=MissionService(
            SqliteMissionRepository(tmp_path / "missions.db"),
            emergency_stop=UNGOVERNED_FIXTURE,
        ),
        trajectory_repository=TrajectoryRepository(world.operational),
        skill_repository=world.repository,
        emergency_stop=UNGOVERNED_FIXTURE,
    )


def test_activation_gives_a_migrated_candidate_its_contract(world, tmp_path) -> None:
    """A skill migrated from the legacy store has no plan, scope or trail. The
    operator's activation derives them from its own steps."""
    trail = world.earn()
    bare = world.record().model_copy(
        update={
            "verification_plan": None,
            "allowed_scope_pattern": "",
            "source_trajectory_ids": [],
            "last_validated_versions": [],
        }
    )
    world.repository.save(bare)
    activated = _service(world, tmp_path).activate_skill(
        _authorization(bare.skill_id, bare.version)
    )
    assert activated.state == "active"
    assert activated.verification_plan == reflex_contract.verification_plan(STEPS)
    assert activated.allowed_scope_pattern == reflex_contract.scope_identity()
    assert activated.source_trajectory_ids
    assert activated.last_validated_versions == [
        reflex_contract.validated_version(STEPS)
    ]
    assert world.library.reflex_applicability(trail) is None


def test_reactivation_records_the_code_as_it_is_now(world, tmp_path) -> None:
    """The machine withdrew it; the code changed; the operator re-activates it
    -- his judgment that it applies to the code as it is. Its reviewed contract
    is untouched: only the evidence grows."""
    trail = world.live()
    record = world.record()
    world.repository.transition_state(record.skill_id, record.version, "suspended")
    world.write("notes.md", "release notes v2\n")
    activated = _service(world, tmp_path).activate_skill(
        _authorization(record.skill_id, record.version)
    )
    assert activated.verification_plan == record.verification_plan
    assert activated.allowed_scope_pattern == record.allowed_scope_pattern
    assert activated.source_trajectory_ids == record.source_trajectory_ids
    assert activated.last_validated_versions == [
        *record.last_validated_versions,
        reflex_contract.validated_version(STEPS),
    ]
    assert world.library.reflex_applicability(trail) is None


def test_a_procedure_that_is_not_an_arc_is_left_alone(world) -> None:
    world.earn()
    prose = world.record().model_copy(update={"procedure": "do the thing by hand"})
    assert reflex_contract.stamp_for_activation(prose) is prose
