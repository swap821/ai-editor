"""Goals through the clerk (2026-11-11, the operator's one-system plan, phase 1).
Pinned without a model:

* each goal is asked of the clerk's own governed service -- the real one, with
  its provenance store -- triage, then briefing, each exactly as organ 37's
  qualification asks it (one builder, two callers);
* a clerk with no model granted the job leaves the goal waiting, saying why,
  and the workshop's writers still work on the goal: the clerk blocks nothing;
* an answer that is not a triage or a briefing is not used;
* a briefed goal's writer reads the clerk's briefing beside the operator's
  words, which decide; the council's request keeps HIS files, never the
  clerk's;
* the hour's bound, the off switch, a failure that is said, the report line;
* his words are scrubbed before the clerk reads them.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from aios.application.local_workforce.provenance import get_clerk_job_provenance
from aios.application.local_workforce.service import LocalWorkforceService
from aios.core.autonomy import UNGOVERNED_FIXTURE
from aios.domain.local_workforce import qualifier as q
from aios.domain.local_workforce.contracts import (
    LocalJobProfile,
    LocalJobResult,
    LocalWorkerModel,
)
from aios.domain.local_workforce.goal_jobs import (
    BRIEFING_SCHEMA,
    TRIAGE_SCHEMA,
    briefing_prompt,
    read_briefing,
    read_triage,
    triage_prompt,
)
from aios.domain.local_workforce.registry import LocalWorkforceRegistry
from aios.infrastructure.local_workforce.sqlite_store import (
    LocalWorkforceProvenanceStore,
)
from aios.maintenance import daily_work as dw
from aios.maintenance import goal_intake as gi
from tests.test_gagos_daily import REL
from tests.test_gagos_tasks_workshop import WORDS, _reply
from tests.test_gagos_workforce import _batch
from tools import gagos_daily as tool

TRIAGE = {"severity": "low", "area": "frontend", "escalate": False}
BRIEF = {
    "goal": "Rename the unused local and say why.",
    "files": [REL],
    "constraints": ["Keep the behaviour."],
    "done_when": "the lint warning is gone",
}


def _task(tid="gt-1", text=WORDS, rel=REL, also=()):
    return {"task_id": tid, "text": text, "rel": rel, "also": list(also)}


class _Clerk:
    """The clerk's service as the intake sees it: run_advisory_job only.
    Keeps every request; answers by job profile."""

    def __init__(self, triage=TRIAGE, brief=BRIEF, status="completed", why=None):
        self.requests: list = []
        self.answers = {
            LocalJobProfile.TRIAGE: triage,
            LocalJobProfile.PREPARE_BRIEFING: brief,
        }
        self.status, self.why = status, why

    def run_advisory_job(self, request):
        self.requests.append(request)
        done = self.status == "completed"
        return LocalJobResult(
            job_id=request.job_id,
            model_id="qwen2.5:3b" if done else "none",
            structured_output=self.answers[request.job_profile] if done else None,
            schema_valid=done,
            evidence_references_preserved=True,
            unsupported_claims=(),
            latency=0.1,
            status=self.status,
            failure_reason=self.why,
        )


# ------------------------------------------------- one builder, two callers


def test_qualification_asks_the_jobs_exactly_as_the_hour_does() -> None:
    cases = {c.test_id: c for c in q._cases()}
    assert cases["triage_escalates"].prompt == triage_prompt(
        "test_login_rejects_expired_token fails: an expired session token was "
        "accepted (aios/identity/service.py)"
    )
    assert cases["briefing"].prompt.startswith(
        briefing_prompt("x").split("'x'")[0]
    ) and cases["briefing"].prompt.endswith(briefing_prompt("x").split("'x'. ")[1])
    clerk = _Clerk()
    gi.intake(_task(), clerk, project_root="C:/p")
    goal = gi.goal_text(_task())
    assert [r.redacted_payload for r in clerk.requests] == [
        triage_prompt(goal),
        briefing_prompt(goal),
    ]
    assert [dict(r.required_output_schema) for r in clerk.requests] == [
        dict(TRIAGE_SCHEMA),
        dict(BRIEFING_SCHEMA),
    ]
    assert [r.job_profile for r in clerk.requests] == [
        LocalJobProfile.TRIAGE,
        LocalJobProfile.PREPARE_BRIEFING,
    ]


@pytest.mark.parametrize(
    "answer",
    [
        {**TRIAGE, "severity": "urgent"},
        {**TRIAGE, "area": "everything"},
        {**TRIAGE, "escalate": "no"},
        {"severity": "low", "area": "frontend"},
    ],
)
def test_an_answer_that_is_not_a_triage_is_refused(answer) -> None:
    assert not read_triage(answer)[0]


@pytest.mark.parametrize(
    "answer",
    [
        {**BRIEF, "files": []},
        {**BRIEF, "files": "a.ts"},
        {**BRIEF, "goal": " "},
        {**BRIEF, "constraints": [""]},
        {**BRIEF, "extra": 1},
    ],
)
def test_an_answer_that_is_not_a_briefing_is_refused(answer) -> None:
    assert not read_briefing(answer)[0]
    assert read_briefing(BRIEF)[0]


# ------------------------------------------- the clerk's real service


def _model(profiles) -> LocalWorkerModel:
    return LocalWorkerModel(
        model_id="qwen2.5:3b",
        provider="ollama",
        family="qwen2.5",
        parameter_size="3B",
        quantization="q4_K_M",
        installed=True,
        operator_approved=True,
        health="healthy",
        admission_status="approved",
        admission_reason="Passed",
        max_context=32768,
        max_output=4096,
        max_parallelism=1,
        allowed_job_profiles=frozenset(profiles),
        metadata_confidence="verified",
    )


def _service(tmp_path, models, answer):
    registry = MagicMock(spec=LocalWorkforceRegistry)
    registry.list_models.return_value = models
    registry.get_model.return_value = models[0] if models else None
    llm = MagicMock()
    llm.complete.side_effect = lambda *a, **k: answer(str(a) + str(k))
    store = LocalWorkforceProvenanceStore(tmp_path / "provenance.db")
    service = LocalWorkforceService(
        registry=registry,
        ollama=llm,
        model_client_factory=lambda model_id: llm,
        provenance_store=store,
        emergency_stop=UNGOVERNED_FIXTURE,
    )
    return service, store


def test_a_granted_clerk_briefs_the_goal_through_its_own_service(tmp_path) -> None:
    service, store = _service(
        tmp_path,
        [_model({LocalJobProfile.TRIAGE, LocalJobProfile.PREPARE_BRIEFING})],
        lambda asked: json.dumps(TRIAGE if "Triage this for" in asked else BRIEF),
    )
    out = gi.intake(_task(), service, project_root="C:/p")
    assert out["state"] == gi.BRIEFED, out
    assert out["clerk"]["triage"]["model"] == "qwen2.5:3b"
    # Each job is in the clerk's own provenance, recorded by its service.
    for job, profile in (
        ("goal-gt-1-triage", LocalJobProfile.TRIAGE),
        ("goal-gt-1-briefing", LocalJobProfile.PREPARE_BRIEFING),
    ):
        seen = get_clerk_job_provenance(store, job)
        assert seen.request.job_profile == profile.value
        assert seen.result.status == "completed"


def test_with_no_model_granted_the_goal_waits_and_says_why(tmp_path) -> None:
    service, store = _service(tmp_path, [], lambda asked: "{}")
    out = gi.intake(_task(), service, project_root="C:/p")
    assert out["state"] == gi.AWAITING_CLERK
    assert "No admitted healthy local model" in out["reason"]
    assert out["mission_request"] is None
    # Asked once, refused once, and that refusal is on the clerk's record.
    assert get_clerk_job_provenance(store, "goal-gt-1-triage").result.status == (
        "rejected"
    )
    assert get_clerk_job_provenance(store, "goal-gt-1-briefing").result is None


def test_an_invalid_answer_is_not_used() -> None:
    out = gi.intake(
        _task(), _Clerk(triage={**TRIAGE, "severity": "urgent"}), project_root="C:/p"
    )
    assert out["state"] == gi.AWAITING_CLERK
    assert "not valid" in out["reason"] and out["mission_request"] is None


# ------------------------------------------------ what the clerk produces


def test_an_escalating_triage_is_said_and_carried_to_the_writer() -> None:
    out = gi.intake(
        _task(),
        _Clerk(triage={"severity": "high", "area": "security", "escalate": True}),
        project_root="C:/p",
    )
    assert out["state"] == gi.ESCALATED
    assert "high, security" in out["reason"]
    assert out["mission_request"] is not None
    assert "escalates it (high, security)" in gi.writer_briefing(out)


def test_the_councils_request_keeps_his_files_never_the_clerks() -> None:
    task = _task(also=["frontend/src/b.tsx"])
    brief = {**BRIEF, "files": ["frontend/src/invented.tsx"]}
    out = gi.intake(task, _Clerk(brief=brief), project_root="C:/p")
    req = out["mission_request"]
    assert req["allowed_files"] == [REL, "frontend/src/b.tsx"]
    assert (req["mission_id"], req["created_by"]) == ("goal-gt-1", "gagos_clerk")
    assert req["goal"] == BRIEF["goal"]
    assert req["done_when"] == BRIEF["done_when"]
    assert "aios/security/" in req["forbidden_files"]


def test_the_writer_reads_the_briefing_only_once_the_clerk_briefed() -> None:
    assert gi.writer_briefing(None) == ""
    assert gi.writer_briefing({"state": gi.AWAITING_CLERK, "clerk": {}}) == ""
    briefed = gi.intake(_task(), _Clerk(), project_root="C:/p")
    line = gi.writer_briefing(briefed)
    assert "Constraints: Keep the behaviour." in line
    assert "Done when: the lint warning is gone" in line
    assert "escalates" not in line


def test_pending_is_new_goals_and_those_still_waiting() -> None:
    tasks = [_task(t) for t in ("a", "b", "c", "d")]
    intakes = {
        "b": {"state": gi.AWAITING_CLERK},
        "c": {"state": gi.BRIEFED},
        "d": {"state": gi.ESCALATED},
    }
    assert [t["task_id"] for t in gi.pending(tasks, intakes)] == ["a", "b"]


# ------------------------------------------------------- in the workshop


def test_the_ledger_keeps_the_latest_intake(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    tid = led.add_task(REL, WORDS, said_by="operator")
    led.record_intake(
        tid, gi.intake(_task(tid), _Clerk(status="rejected", why="x"), project_root="p")
    )
    assert led.intakes()[tid]["state"] == gi.AWAITING_CLERK
    led.record_intake(tid, gi.intake(_task(tid), _Clerk(), project_root="p"))
    (seen,) = led.intakes().values()
    assert seen["state"] == gi.BRIEFED
    assert seen["mission_request"]["allowed_files"] == [REL]
    assert seen["clerk"]["briefing"]["done_when"] == BRIEF["done_when"]


def test_the_hour_takes_in_a_bounded_number_and_scrubs_his_words(
    tmp_path, monkeypatch
) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    secret = "AKIAIOSFODNN7EXAMPLE"
    ids = [
        led.add_task(REL, f"Use the key {secret} for task {n}.", said_by="operator")
        for n in range(tool.GOALS_PER_HOUR + 1)
    ]
    clerk = _Clerk()
    tool.goals_hour(led, tmp_path, service=clerk)
    assert len(led.intakes()) == tool.GOALS_PER_HOUR
    assert set(led.intakes()) == set(ids[: tool.GOALS_PER_HOUR])
    assert clerk.requests
    assert all(secret not in r.redacted_payload for r in clerk.requests)
    # Next hour: only the one not yet taken in.
    clerk.requests.clear()
    tool.goals_hour(led, tmp_path, service=clerk)
    assert {
        r.job_id.split("-triage")[0] for r in clerk.requests if "triage" in r.job_id
    } == {f"goal-{ids[-1]}"}


def test_the_hour_can_be_switched_off(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_GAGOS_GOALS_THROUGH_CLERK", "0")
    led = dw.DailyLedger(tmp_path / "l.db")
    led.add_task(REL, WORDS, said_by="operator")
    clerk = _Clerk()
    tool.goals_hour(led, tmp_path, service=clerk)
    assert clerk.requests == [] and led.intakes() == {}


def test_a_clerk_that_cannot_be_asked_is_said_and_the_goal_waits(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    tid = led.add_task(REL, WORDS, said_by="operator")

    class Down:
        def run_advisory_job(self, request):
            raise ConnectionError("ollama is not running")

    tool.goals_hour(led, tmp_path, service=Down())
    seen = led.intakes()[tid]
    assert seen["state"] == gi.AWAITING_CLERK
    assert "could not be asked" in seen["reason"] and "ollama" in seen["reason"]


def test_a_briefed_goals_writer_reads_the_clerks_briefing(
    tmp_path, monkeypatch
) -> None:
    led, _asked, args, _ids = _batch(tmp_path, monkeypatch)
    prompts: list = []
    _reply(monkeypatch, prompts)
    tid = led.add_task(REL, WORDS, said_by="operator")
    led.record_intake(tid, gi.intake(_task(tid), _Clerk(), project_root="p"))
    args.budget = 1
    assert tool.cmd_propose(args) == 0
    ((_model, prompt, _system),) = prompts
    assert WORDS in prompt
    assert (
        "The local clerk's briefing (advisory; the operator's task above decides):"
        in prompt
    )
    assert "Done when: the lint warning is gone" in prompt
    assert led.task(tid)["status"] == "taken"


def test_a_goal_the_clerk_could_not_brief_is_still_worked_on(
    tmp_path, monkeypatch
) -> None:
    led, _asked, args, _ids = _batch(tmp_path, monkeypatch)
    prompts: list = []
    _reply(monkeypatch, prompts)
    tid = led.add_task(REL, WORDS, said_by="operator")
    led.record_intake(
        tid,
        gi.intake(
            _task(tid), _Clerk(status="rejected", why="no model"), project_root="p"
        ),
    )
    args.budget = 1
    assert tool.cmd_propose(args) == 0
    ((_model, prompt, _system),) = prompts
    assert "local clerk" not in prompt
    assert led.task(tid)["status"] == "taken"


def test_the_report_says_where_the_clerk_is_with_each_goal(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    tid = led.add_task(REL, WORDS, said_by="operator")
    led.record_intake(
        tid,
        gi.intake(
            _task(tid),
            _Clerk(
                status="rejected", why="No admitted healthy local model for profile"
            ),
            project_root="p",
        ),
    )
    lines = "\n".join(tool.task_section(led))
    assert f"`{tid}`" in lines
    assert (
        "with the clerk, awaiting_clerk (triage: No admitted healthy local model"
        in lines
    )


def test_the_intake_runs_before_the_writers_each_hour() -> None:
    import inspect

    src = inspect.getsource(tool.cmd_daily)
    assert src.index("goals_hour(led, root)") < src.index("rc = cmd_propose(")
