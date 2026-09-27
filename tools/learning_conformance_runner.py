#!/usr/bin/env python3
"""The number the animal is judged by — and what it refuses to learn.

Organ 55 asks "when a capable model actively tries to do the wrong thing, does
authority hold, and can the ledger prove what happened?" This asks the learning
side's equivalent, and it is a different question from "can a model write a
test":

    when something happens that the loop is supposed to learn from, does the
    MEMORY actually change -- and when something happens that only LOOKS like
    evidence, does the loop refuse it?

THE THREE RULES, TAKEN FROM ORGAN 55 UNCHANGED
----------------------------------------------
1. **A pass is an assertion over memory state.** Never over a model's answer.
   Every mission below drives the real production classes against a real
   SQLite store and then reads the rows. A mission that inspected model output
   would be the self-corpus benchmark wearing a learning costume.
2. **Every mission must be able to fail in a way that indicts GAGOS, not the
   model.** This is the rule the loop violated twice on 2026-09-21: a provider
   timeout was recorded as the model's failure, and a pytest run that produced
   no output was recorded as the model's failure. Both blamed the subject for
   the apparatus.
3. **A lucky pass is a fail.** The Refusal Reel is where that bites hardest: a
   refusal for an unrelated reason is a classification accident, not a refusal.

RELATIONSHIP TO THE SELF-CORPUS LADDER
--------------------------------------
`reverse_engineer_gagos.py` is the **denominator**: it generates the load that
makes learning events happen at all. A loop with nothing flowing through it
proves nothing. This is the **product claim**. When the two disagree, this one
wins the attention, because the easier number always wins by default otherwise.

MISSION 4 IS THE ACCEPTANCE TEST FOR THE WHOLE APPARATUS. Everything else shows
the memory changing; only mission 4 shows the memory PAYING -- a turn served
end to end with the LLM client rigged to raise if it is touched.

PILOT MODE (recorded deviation, operator decision 2026-09-27)
-------------------------------------------------------------
With ``AIOS_SKILL_STORE_MODE=pilot`` the turn recalls skills from the
institutional library, where nothing promotes itself. There M2 passes on
REVIEW-READINESS (never activation) and R9 checks the library's counts. R10,
new, holds in every mode: no evidence activates a library skill, and neither
does a save. The reel grew from four to five, so older "4/4" reports are not
comparable. M3-M5 still measure the legacy reflex chain with a gate-less
cerebellum of their own: the mechanism, not the pilot's reflexes, which since
#395 replay only operator-activated skills. 2.4c redefines them to compile from
active skills. The mode is printed and recorded.

    python tools/learning_conformance_runner.py
    python tools/learning_conformance_runner.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from aios.agents import tool_loop_helpers  # noqa: E402
from aios.core.autonomy import UNGOVERNED_FIXTURE  # noqa: E402
from aios.core.cerebellum import Cerebellum  # noqa: E402
from aios.core.executor import Executor  # noqa: E402
from aios.security.gateway import RateLimiter  # noqa: E402
from aios.core.verification_strength import VerificationStrength  # noqa: E402
from aios.memory.db import get_connection, init_memory_db  # noqa: E402
from aios.memory.mistake import MistakeMemory  # noqa: E402
from aios.memory.skills import SkillMemory  # noqa: E402
from aios import config  # noqa: E402

TRAIL = REPO_ROOT / ".aios" / "audit" / "learning-conformance.jsonl"


@dataclass
class MissionResult:
    mission_id: str
    name: str
    passed: bool
    detail: str
    #: What a failure would indict. Rule 2 says every mission must be able to
    #: say "the loop", or it belongs in the self-corpus benchmark instead.
    indicts: str = "loop"
    refusal: bool = False
    error: str = ""


@dataclass
class Report:
    missions: list[MissionResult] = field(default_factory=list)

    @property
    def product(self) -> list[MissionResult]:
        return [m for m in self.missions if not m.refusal]

    @property
    def reel(self) -> list[MissionResult]:
        return [m for m in self.missions if m.refusal]


class RefusingLLM:
    """An LLM client that fails the test if anything asks it to think.

    This is the whole proof of mission 4. "Zero LLM calls" asserted by reading
    a telemetry column is a claim about bookkeeping; asserted by wiring a
    client that raises, it is a claim about what happened.
    """

    def __init__(self) -> None:
        self.calls = 0

    def _boom(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError(
            "the LLM was called during a turn that a compiled playbook was "
            "supposed to serve — the reflex did not replace the model, it "
            "merely preceded it"
        )

    chat = _boom
    complete = _boom
    stream = _boom


class _SilentRunner:
    """Process runner that records and never spawns."""

    def __call__(self, command, *, cwd, env, timeout_s):
        return f"ran: {command}", "", 0


def _fresh_db(tmp: Path) -> Path:
    db = tmp / "memory.sqlite"
    init_memory_db(db)
    return db


def _insert_verified_skill(db: Path, goal: str, steps: list[str]) -> int:
    """Earn a skill the way production earns it: repeated STRONG successes.

    Deliberately NOT an INSERT. Writing the row by hand would prove that the
    downstream link works on a row shaped the way this file imagines, which is
    how a benchmark drifts away from the system it measures.
    """
    skills = SkillMemory(db_path=db)
    for _ in range(3):
        skill_id = skills.record_attempt(
            goal, steps, success=True, strength=VerificationStrength.STRONG
        )
    return skill_id


def _pilot() -> bool:
    """The operator's skill-store mode reads the institutional library.

    Operator decision 2026-09-27 ("redefine now"): in `pilot` mode the ledger's
    skill missions measure the store the turn actually recalls from. Legacy and
    `shadow` (which reads legacy) keep the legacy missions.
    """
    return config.SKILL_STORE_MODE == "pilot"


def _library(tmp: Path):
    """A throwaway institutional skill slot, as production builds it."""
    from aios.application.memory.institutional_skills import (
        InstitutionalSkillAdapter,
        SkillTrailIndex,
    )
    from aios.domain.learning.repository import SkillRepository

    operational = tmp / "operational.sqlite"
    repository = SkillRepository(operational)
    return (
        InstitutionalSkillAdapter(
            repository,
            SkillTrailIndex(operational),
            legacy=SkillMemory(db_path=_fresh_db(tmp)),
        ),
        repository,
    )


# --------------------------------------------------------------------------- #
# The product claim: does the memory actually change?
# --------------------------------------------------------------------------- #
def mission_1_lesson_transfers(tmp: Path) -> MissionResult:
    """A lesson recorded from a failure is promoted when the command succeeds."""
    db = _fresh_db(tmp)
    mistakes = MistakeMemory(db_path=db)
    command = "pytest tests/test_thing.py -q"
    # `record_or_increment`, not `record`: only this one accepts
    # `failed_command`, and it is what ReflectionAgent calls in production. A
    # mission that used the other method would be testing a path no turn takes.
    lesson_id, _recurrence = mistakes.record_or_increment(
        "task-1",
        "AssertionError",
        "cause",
        "fix",
        "lesson",
        -0.2,
        failed_command=command,
    )

    pending = [(lesson_id, command)]
    promoted: list[int] = []
    list(
        tool_loop_helpers.confirm(
            pending,
            command,
            0,
            lambda mid: (promoted.append(mid), mistakes.promote(mid)),
        )
    )

    with get_connection(db) as conn:
        status = conn.execute(
            "SELECT verification_status FROM mistake_pool WHERE id = ?", (lesson_id,)
        ).fetchone()["verification_status"]
    ok = status == "verified" and promoted == [lesson_id]
    return MissionResult(
        "M1",
        "a lesson survives its own turn and is confirmed by a later success",
        ok,
        f"lesson {lesson_id} status={status!r}, promoted={promoted}",
    )


def mission_2_skill_verifies(tmp: Path) -> MissionResult:
    """Three STRONG successes move a skill candidate -> verified."""
    if _pilot():
        # In pilot mode the library never promotes itself: evidence makes a
        # skill REVIEW-READY, and only the operator activates it.
        adapter, repository = _library(tmp)
        for _ in range(3):
            adapter.record_attempt(
                "run the tests",
                ["read_file: a.py", "verify: pytest"],
                success=True,
                strength=VerificationStrength.STRONG,
            )
        (record,) = repository.list_skills()
        ready = adapter.trail_map()["trails"][0]["review_ready"]
        return MissionResult(
            "M2",
            "repeated verified success makes a library skill review-ready (pilot)",
            record.state == "candidate" and ready is True,
            f"state={record.state!r}, review_ready={ready} after "
            f"{record.success_count} STRONG successes; activation is the operator's",
        )
    db = _fresh_db(tmp)
    skill_id = _insert_verified_skill(
        db, "run the tests", ["read_file: a.py", "verify: pytest"]
    )
    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT status, success_count FROM procedural_skills WHERE id = ?",
            (skill_id,),
        ).fetchone()
    ok = row["status"] == "verified"
    return MissionResult(
        "M2",
        "repeated verified success promotes a skill",
        ok,
        f"status={row['status']!r} after {row['success_count']} STRONG successes",
    )


def mission_3_skill_compiles(tmp: Path) -> MissionResult:
    """A verified skill becomes a compiled playbook."""
    db = _fresh_db(tmp)
    _insert_verified_skill(db, "run the tests", ["read_file: a.py", "verify: pytest"])
    cerebellum = Cerebellum(db)
    compiled = cerebellum.try_compile_all()
    with get_connection(db) as conn:
        rows = conn.execute("SELECT status FROM compiled_playbooks").fetchall()
    ok = compiled >= 1 and any(r["status"] == "compiled" for r in rows)
    return MissionResult(
        "M3",
        "a verified skill compiles into a reflex",
        ok,
        f"compiled={compiled}, playbook rows={[r['status'] for r in rows]}",
    )


def mission_4_replay_serves_a_turn_with_no_llm(tmp: Path) -> MissionResult:
    """THE acceptance test: a turn completed with the LLM rigged to raise.

    Everything else in this file shows the memory changing. This is the only
    mission that shows the memory PAYING -- the point of compiling a reflex is
    that the next identical request costs no inference at all.
    """
    from aios.agents.tool_agent import ToolAgent

    db = _fresh_db(tmp)
    # A file that really exists: a playbook whose read fails aborts the replay
    # and falls through to the LLM, which would be the gateway doing its job on
    # a broken fixture rather than the reflex failing. The abort path is worth
    # having -- it just must not be what this mission accidentally measures.
    target = "README.md"
    goal = f"read {target} and report what it says"
    _insert_verified_skill(db, goal, [f"read_file: {target}"])
    cerebellum = Cerebellum(db)
    cerebellum.try_compile_all()

    llm = RefusingLLM()
    agent = ToolAgent(
        llm,
        Executor(
            runner=_SilentRunner(),
            rate_limiter=RateLimiter(),
            audit_log=lambda *a, **k: None,
            emergency_stop=UNGOVERNED_FIXTURE,
        ),
        max_iters=3,
        cerebellum=cerebellum,
    )

    events = list(agent.run([{"role": "user", "content": goal}]))
    kinds = [e.get("type") for e in events]
    served = "cerebellum_done" in kinds
    ok = served and llm.calls == 0
    return MissionResult(
        "M4",
        "a compiled reflex serves a whole turn with ZERO LLM calls",
        ok,
        f"cerebellum_done={served}, llm_calls={llm.calls}, events={kinds[:6]}",
    )


def mission_5_decompiled_reflex_recovers(tmp: Path) -> MissionResult:
    """A reflex retired by two flakes comes back when the skill re-earns it.

    `cerebellum.py`'s own docstring promises this: "It cannot recompile without
    the underlying skill re-earning verification from scratch." The compile
    query bars `status IN ('compiled','decompiled')` and nothing ever clears
    'decompiled', so today the promise is not kept. Expected to FAIL until the
    recovery path exists -- which is the mission doing its job.
    """
    db = _fresh_db(tmp)
    _insert_verified_skill(db, "run the tests", ["read_file: a.py", "verify: pytest"])
    cerebellum = Cerebellum(db)
    cerebellum.try_compile_all()

    # Retire it through the PRODUCTION path, not a hand-written UPDATE. The
    # raw SQL version left `decompiled_at_successes` NULL, so the mission was
    # measuring a state the system cannot actually produce -- the same
    # write-the-row-by-hand shortcut this file warns about elsewhere.
    [skill_id] = [pb.skill_id for pb in cerebellum._cache.values()]
    assert cerebellum.invalidate_for_skill(skill_id), "nothing was decompiled"

    # Re-earn it: three more STRONG successes on the same arc.
    _insert_verified_skill(db, "run the tests", ["read_file: a.py", "verify: pytest"])
    recompiled = Cerebellum(db).try_compile_all()

    with get_connection(db) as conn:
        live = conn.execute(
            "SELECT COUNT(*) n FROM compiled_playbooks WHERE status = 'compiled'"
        ).fetchone()["n"]
    ok = recompiled >= 1 or live >= 1
    return MissionResult(
        "M5",
        "a decompiled reflex recovers once its skill is re-earned",
        ok,
        f"recompiled={recompiled}, live compiled playbooks={live}",
    )


# --------------------------------------------------------------------------- #
# The Refusal Reel: a PASS here is the loop declining to learn.
# --------------------------------------------------------------------------- #
def refusal_6_hollow_run_is_not_a_verdict(tmp: Path) -> MissionResult:
    """A pytest run that produced no output must be refused, not scored."""
    from tools.self_corpus import CorpusError, SuiteResult
    from tools import self_corpus_grading

    dead = SuiteResult(passed=0, failed=0, errors=0, returncode=1, tail="")
    refused_as_failure = False
    try:
        self_corpus_grading._refuse_hollow(dead, "a clean run")
    except CorpusError:
        refused_as_failure = True

    # And the direction that is easy to miss: a hollow MUTATED run must not
    # satisfy the negative control by being "not green".
    really_red = SuiteResult(
        passed=0, failed=1, errors=0, returncode=1, tail="E AssertionError"
    )
    red_still_counts = not really_red.hollow

    ok = refused_as_failure and dead.hollow and red_still_counts
    return MissionResult(
        "R6",
        "a suite run that never happened is refused in BOTH directions",
        ok,
        f"refused={refused_as_failure}, hollow={dead.hollow}, red_still_a_failure={red_still_counts}",
        refusal=True,
    )


def refusal_7_unreachable_model_is_not_scored(tmp: Path) -> MissionResult:
    """A provider outage writes no arc row at all."""
    from tools.reverse_engineer_gagos import Attempt, tier_verdict

    outage = [
        Attempt(target="t", outcome="model_error", model="m", reached_model=False),
        Attempt(target="t", outcome="model_error", model="m", reached_model=False),
    ]
    should_record, earned, why = tier_verdict(outage)

    graded = [Attempt(target="t", outcome="rejected", model="m", reached_model=True)]
    still_counts = tier_verdict(graded)[0]

    ok = (should_record is False) and (earned is False) and still_counts
    return MissionResult(
        "R7",
        "a model that was never reached earns neither success nor failure",
        ok,
        f"outage recorded={should_record} ({why}); a graded failure still records={still_counts}",
        refusal=True,
    )


def refusal_8_vacuous_test_is_a_failure(tmp: Path) -> MissionResult:
    """A test that cannot fail is a FAILURE, never a weak success.

    A weak success would reset `consecutive_failures`, so an agent writing
    `assert True` would actively help itself toward a reflex.
    """
    from tools.self_corpus_grading import record_pin_outcome

    db = _fresh_db(tmp)
    skills = SkillMemory(db_path=db)

    class _Vacuous:
        earned = False

    record_pin_outcome(
        skills,
        _Vacuous(),
        target_label="calc.py::add",
        model="qwen2.5-coder:7b",
        steps=["read_file: calc.py", "create_file: t.py", "verify: pytest"],
    )
    row = skills.list()[0]
    ok = row["failure_count"] == 1 and row["weak_success_count"] == 0
    return MissionResult(
        "R8",
        "a test that cannot fail is recorded as a failure, not a weak success",
        ok,
        f"failure_count={row['failure_count']}, weak_success_count={row['weak_success_count']}",
        refusal=True,
    )


def refusal_9_below_floor_cannot_promote(tmp: Path) -> MissionResult:
    """A WEAK success is remembered but can never calibrate the future."""
    if _pilot():
        adapter, repository = _library(tmp)
        for _ in range(5):
            adapter.record_attempt(
                "tidy some imports",
                ["read_file: a.py", "verify: ruff"],
                success=True,
                strength=VerificationStrength.WEAK,
            )
        records = repository.list_skills()
        ready = bool(records) and adapter.trail_map()["trails"][0]["review_ready"]
        counted = sum(r.success_count for r in records)
        return MissionResult(
            "R9",
            "five below-floor successes cannot make a library skill review-ready (pilot)",
            counted == 0 and not ready,
            f"success_count={counted}, review_ready={ready} after 5 WEAK successes",
            refusal=True,
        )
    db = _fresh_db(tmp)
    skills = SkillMemory(db_path=db)
    for _ in range(5):
        skills.record_attempt(
            "tidy some imports",
            ["read_file: a.py", "verify: ruff"],
            success=True,
            strength=VerificationStrength.WEAK,
        )
    row = skills.list()[0]
    ok = row["status"] == "candidate" and row["weak_success_count"] == 5
    return MissionResult(
        "R9",
        "five below-floor successes still cannot promote a skill",
        ok,
        f"status={row['status']!r} after 5 WEAK successes "
        f"(weak_success_count={row['weak_success_count']})",
        refusal=True,
    )


def refusal_10_evidence_cannot_activate(tmp: Path) -> MissionResult:
    """No amount of evidence activates a library skill; only the operator does."""
    from aios.domain.learning.repository import SkillRecord

    adapter, repository = _library(tmp)
    for _ in range(10):
        adapter.record_attempt(
            "run the pin tests",
            ["verify: pytest tests/test_pin.py -q"],
            success=True,
            strength=VerificationStrength.STRONG,
        )
    (record,) = repository.list_skills()
    forged = record.model_copy(update={"state": "active"})
    refused = False
    try:
        repository.save(SkillRecord.model_validate(forged.model_dump()))
    except ValueError:
        refused = True
    after = repository.get(record.skill_id, record.version)
    return MissionResult(
        "R10",
        "ten STRONG successes never activate a library skill, and a save cannot",
        record.state == "candidate" and refused and after.state == "candidate",
        f"state={after.state!r} after {record.success_count} STRONG successes; "
        f"a save straight to 'active' was {'refused' if refused else 'ACCEPTED'}",
        refusal=True,
    )


MISSIONS = [
    mission_1_lesson_transfers,
    mission_2_skill_verifies,
    mission_3_skill_compiles,
    mission_4_replay_serves_a_turn_with_no_llm,
    mission_5_decompiled_reflex_recovers,
    refusal_6_hollow_run_is_not_a_verdict,
    refusal_7_unreachable_model_is_not_scored,
    refusal_8_vacuous_test_is_a_failure,
    refusal_9_below_floor_cannot_promote,
    refusal_10_evidence_cannot_activate,
]


def _mission_id(fn) -> str:
    """`mission_4_...` -> `M4`, `refusal_7_...` -> `R7`, anything else -> `??`."""
    parts = fn.__name__.split("_")
    if len(parts) >= 2 and parts[1].isdigit():
        return ("R" if parts[0] == "refusal" else "M") + parts[1]
    return "??"


def run_all() -> Report:
    report = Report()
    for fn in MISSIONS:
        with tempfile.TemporaryDirectory(prefix="learn-conf-") as tmp:
            try:
                report.missions.append(fn(Path(tmp)))
            except Exception as exc:  # noqa: BLE001 - a crash is a result
                # Defensively, because this handler crashing would turn one
                # broken mission into a missing SCORE -- the run would abort
                # and report nothing, which reads exactly like "not run yet".
                # An earlier version derived the id as `name.split("_")[1]`
                # and raised IndexError on any function without an underscore.
                report.missions.append(
                    MissionResult(
                        _mission_id(fn),
                        (fn.__doc__ or fn.__name__).splitlines()[0],
                        False,
                        f"raised {type(exc).__name__}: {exc}",
                        refusal=fn.__name__.startswith("refusal"),
                        error=traceback.format_exc()[-800:],
                    )
                )
    return report


def render(report: Report) -> str:
    lines = [
        "LEARNING CONFORMANCE",
        f"  skill store mode: {config.SKILL_STORE_MODE}",
        "",
    ]
    if _pilot():
        lines.insert(
            2,
            "  (pilot: M2/R9 measure the institutional library; M3-M5 still measure "
            "the legacy reflex MECHANISM with a gate-less cerebellum, not the pilot's "
            "reflexes, which since #395 replay only operator-activated skills; the "
            "2.4c hard switch redefines them)",
        )
    product_ok = sum(1 for m in report.product if m.passed)
    reel_ok = sum(1 for m in report.reel if m.passed)
    lines.append(f"  product claim : {product_ok} / {len(report.product)}")
    lines.append(f"  refusal reel  : {reel_ok} / {len(report.reel)}")
    lines.append("")
    for m in report.missions:
        mark = "PASS" if m.passed else "FAIL"
        lines.append(f"  [{mark}] {m.mission_id}  {m.name}")
        lines.append(f"            {' '.join(m.detail.split())[:160]}")
    lines.append("")
    if reel_ok != len(report.reel):
        lines.append(
            "  A FAILING REFUSAL IS THE SERIOUS ONE. It means the loop accepted "
            "something that only looked like evidence."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--no-record", action="store_true", help="do not append to the trail"
    )
    args = parser.parse_args(argv)

    report = run_all()
    print(
        json.dumps([asdict(m) for m in report.missions], indent=2)
        if args.json
        else render(report)
    )

    if not args.no_record:
        TRAIL.parent.mkdir(parents=True, exist_ok=True)
        with TRAIL.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        # A score is unreadable without the store it measured.
                        "skill_store_mode": config.SKILL_STORE_MODE,
                        "product": f"{sum(1 for m in report.product if m.passed)}/{len(report.product)}",
                        "reel": f"{sum(1 for m in report.reel if m.passed)}/{len(report.reel)}",
                        "missions": [asdict(m) for m in report.missions],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    # The Refusal Reel is an INVARIANT, not a score: every one of those must
    # hold on every run, because each is a way the loop could be taught
    # something false. The product missions are a number that is allowed to be
    # below full while the work to raise it is named in the ledger.
    return 0 if all(m.passed for m in report.reel) else 1


if __name__ == "__main__":
    raise SystemExit(main())
