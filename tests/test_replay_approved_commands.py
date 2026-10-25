"""A reflex may replay a command only if a human approved exactly that command.

Plan Phase 5 (approval provenance for commands), operator decision 2026-09-25:
"a reflex may auto-approve only a step a human approved, in a compatible scope".
`aios.core.replay_commands` is the record; `ToolAgent` writes it when a
capability-approved command runs clean, and both replay checks (the preflight
withhold and the dispatcher) read it. Without a record, every test here that
replays a YELLOW step shows the old behaviour: withheld, falls to the model.
"""

from __future__ import annotations

from typing import Any

import pytest

from aios import config
from aios.agents.tool_agent import REFLEX_AUTHORITY_WITHHELD, ToolAgent
from aios.core import replay_commands
from aios.core.autonomy import UNGOVERNED_FIXTURE
from aios.core.cerebellum import CompiledPlaybook, PlaybookStep
from aios.core.executor import Executor
from aios.memory.db import get_connection, init_memory_db
from aios.security.gateway import RateLimiter

YELLOW = "git commit -m done"
YELLOW_VERIFY = "python -m pytest -o addopts= tests -q"
PRINCIPAL = "principal:operator"


class NoLLM:
    """A chat client that fails the test if the turn ever reaches it."""

    def __init__(self) -> None:
        self.calls: list[Any] = []

    def chat(self, messages, *, tools=None, model=None) -> dict:
        self.calls.append(messages)
        return {"role": "assistant", "content": "the model was consulted"}


class Scripted:
    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.calls: list[Any] = []

    def chat(self, messages, *, tools=None, model=None) -> dict:
        self.calls.append(messages)
        return self._responses.pop(0)


def _executor(exit_code: int = 0) -> tuple[Executor, list[str]]:
    calls: list[str] = []

    def runner(command, *, cwd, env, timeout_s):
        calls.append(command)
        out = "3 passed in 0.2s" if exit_code == 0 else "1 failed in 0.2s"
        return out, "", exit_code

    return (
        Executor(
            runner=runner,
            rate_limiter=RateLimiter(),
            audit_log=lambda *a, **k: None,
            emergency_stop=UNGOVERNED_FIXTURE,
        ),
        calls,
    )


def _playbook(tool: str, command: str) -> CompiledPlaybook:
    return CompiledPlaybook(
        id=501,
        skill_id=501,
        goal_pattern="run the check",
        signature_v2="sig-approved-replay",
        compiled_at="",
        steps=[PlaybookStep(tool_name=tool, args={"command": command})],
        replay_count=0,
        consecutive_failures=0,
        status="compiled",
    )


def _replaying_cerebellum(playbook: CompiledPlaybook, captured: list) -> Any:
    class ReplayingCerebellum:
        def match(self, user_text, *, principal):
            return playbook

        def replay(self, pb, *, dispatch_fn):
            for step in pb.steps:
                result = dispatch_fn(step.tool_name, step.args)
                captured.append(result)
                _output, status, failed = result
                if status in ("blocked", "approval") or failed:
                    yield {"type": "cerebellum_abort", "reason": status}
                    return
            yield {"type": "cerebellum_done", "playbook_id": pb.id}

    return ReplayingCerebellum()


@pytest.fixture()
def db(tmp_path, monkeypatch) -> Any:
    path = tmp_path / "memory.db"
    init_memory_db(path)
    monkeypatch.setattr(config, "MEMORY_DB_PATH", path)
    return path


@pytest.fixture()
def enabled(monkeypatch) -> None:
    monkeypatch.setattr(config, "REPLAY_APPROVED_COMMANDS_ENABLED", True)


def _agent(chat, executor, **kwargs) -> ToolAgent:
    agent = ToolAgent(chat, executor, max_iters=2, **kwargs)
    # Tests have no autonomy ledger, which (correctly) reads as "no stop wired"
    # and refuses. Opt out visibly, the way replay_writes' tests do.
    agent._write_stop = lambda: UNGOVERNED_FIXTURE  # type: ignore[method-assign]
    return agent


def _record(db, command: str = YELLOW, principal: str = PRINCIPAL) -> None:
    assert replay_commands.record_command_approval(
        command, principal=principal, db_path=db, emergency_stop=UNGOVERNED_FIXTURE
    )


class EngagedStop:
    def assert_operational(self) -> None:
        raise RuntimeError("emergency stop engaged")


# --------------------------------------------------------------------------- #
# The record
# --------------------------------------------------------------------------- #
class TestTheRecord:
    def test_a_recorded_command_is_approved_only_when_opted_in(self, db) -> None:
        _record(db)
        common = dict(
            principal=PRINCIPAL, db_path=db, emergency_stop=UNGOVERNED_FIXTURE
        )
        assert replay_commands.is_approved_command(YELLOW, enabled=True, **common)
        assert not replay_commands.is_approved_command(YELLOW, enabled=False, **common)

    def test_the_default_is_off(self, db) -> None:
        _record(db)
        assert config.REPLAY_APPROVED_COMMANDS_ENABLED is False
        assert not replay_commands.is_approved_command(
            YELLOW, principal=PRINCIPAL, db_path=db, emergency_stop=UNGOVERNED_FIXTURE
        )

    @pytest.mark.parametrize(
        "command, principal",
        [
            ("git commit -m  done", PRINCIPAL),  # one extra space
            ("git commit -m done ", PRINCIPAL),
            ("git commit -m other", PRINCIPAL),
            (YELLOW, "principal:someone-else"),
            (YELLOW, None),
            (YELLOW, ""),
        ],
    )
    def test_any_drift_misses(self, db, command, principal) -> None:
        _record(db)
        assert not replay_commands.is_approved_command(
            command,
            principal=principal,
            db_path=db,
            enabled=True,
            emergency_stop=UNGOVERNED_FIXTURE,
        )

    def test_another_workspace_misses(self, db, monkeypatch) -> None:
        _record(db)
        monkeypatch.setattr(replay_commands, "workspace_id", lambda: "another-project")
        assert not replay_commands.is_approved_command(
            YELLOW,
            principal=PRINCIPAL,
            db_path=db,
            enabled=True,
            emergency_stop=UNGOVERNED_FIXTURE,
        )

    @pytest.mark.parametrize("stop", [None, EngagedStop()])
    def test_an_absent_or_engaged_stop_grants_nothing_and_records_nothing(
        self, db, stop
    ) -> None:
        _record(db)
        assert not replay_commands.is_approved_command(
            YELLOW, principal=PRINCIPAL, db_path=db, enabled=True, emergency_stop=stop
        )
        assert not replay_commands.record_command_approval(
            "git commit -m other", principal=PRINCIPAL, db_path=db, emergency_stop=stop
        )

    @pytest.mark.parametrize(
        "command",
        ["echo hi", "rm -rf /", "", "   "],
        ids=["green", "red", "empty", "blank"],
    )
    def test_only_yellow_is_ever_recorded(self, db, command) -> None:
        assert not replay_commands.record_command_approval(
            command, principal=PRINCIPAL, db_path=db, emergency_stop=UNGOVERNED_FIXTURE
        )

    def test_red_is_never_authorised_even_if_a_row_exists(self, db) -> None:
        """A row forged straight into the table still grants nothing for RED."""
        red = "rm -rf /"
        with get_connection(db) as conn:
            conn.execute(
                "INSERT INTO approved_command_decisions "
                "(signature, workspace, principal, command) VALUES (?, ?, ?, ?)",
                (
                    replay_commands.command_signature(red, PRINCIPAL),
                    "ws",
                    PRINCIPAL,
                    red,
                ),
            )
        assert not replay_commands.is_approved_command(
            red,
            principal=PRINCIPAL,
            db_path=db,
            enabled=True,
            emergency_stop=UNGOVERNED_FIXTURE,
        )

    def test_a_command_carrying_a_secret_is_not_stored(self, db, monkeypatch) -> None:
        """Defence in depth. Today the gateway already calls a command with an
        embedded credential RED, so the zone check refuses first; this pins the
        scan for the day the gateway misses one, since the command is stored
        verbatim."""
        command = "git commit -m AKIAIOSFODNN7EXAMPLE"
        monkeypatch.setattr(replay_commands, "_approvable", lambda _c: True)
        assert not replay_commands.record_command_approval(
            command, principal=PRINCIPAL, db_path=db, emergency_stop=UNGOVERNED_FIXTURE
        )
        with get_connection(db) as conn:
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM approved_command_decisions"
                ).fetchone()[0]
                == 0
            )

    def test_no_principal_cannot_withdraw_anyones_approval(self, db) -> None:
        """`f"{None}"` is "None": without the principal check, an anonymous
        revoke would key exactly like a principal literally named "None"."""
        _record(db, principal="None")
        assert not replay_commands.revoke_command_decision(
            YELLOW, principal=None, db_path=db
        )
        assert replay_commands.is_approved_command(
            YELLOW,
            principal="None",
            db_path=db,
            enabled=True,
            emergency_stop=UNGOVERNED_FIXTURE,
        )

    def test_revocation(self, db) -> None:
        _record(db)
        assert replay_commands.revoke_command_decision(
            YELLOW, principal=PRINCIPAL, db_path=db
        )
        assert not replay_commands.revoke_command_decision(
            YELLOW, principal=PRINCIPAL, db_path=db
        )
        assert not replay_commands.is_approved_command(
            YELLOW,
            principal=PRINCIPAL,
            db_path=db,
            enabled=True,
            emergency_stop=UNGOVERNED_FIXTURE,
        )


# --------------------------------------------------------------------------- #
# Where a decision comes from: a human-approved command that ran clean
# --------------------------------------------------------------------------- #
class TestRecordingFromALiveTurn:
    def _turn(self, db, *, approved: list[str], principal, exit_code=0) -> list[str]:
        chat = Scripted(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "execute_terminal",
                                "arguments": {"command": YELLOW},
                            }
                        }
                    ],
                },
                {"role": "assistant", "content": "committed"},
            ]
        )
        executor, calls = _executor(exit_code)
        list(
            _agent(chat, executor, approved_commands=approved, principal=principal).run(
                [{"role": "user", "content": "commit it"}]
            )
        )
        with get_connection(db) as conn:
            rows = conn.execute(
                "SELECT principal, command FROM approved_command_decisions"
            ).fetchall()
        return [tuple(r) for r in rows]

    def test_an_approved_command_that_ran_clean_is_recorded(self, db) -> None:
        assert self._turn(db, approved=[YELLOW], principal=PRINCIPAL) == [
            (PRINCIPAL, YELLOW)
        ]

    def test_an_approved_command_that_failed_is_not(self, db) -> None:
        assert self._turn(db, approved=[YELLOW], principal=PRINCIPAL, exit_code=1) == []

    def test_an_unapproved_command_is_not(self, db) -> None:
        assert self._turn(db, approved=[], principal=PRINCIPAL) == []

    def test_an_anonymous_approval_is_not(self, db) -> None:
        assert self._turn(db, approved=[YELLOW], principal=None) == []

    def test_a_non_command_tool_never_mints_one(self, db) -> None:
        """Only execute_terminal and verify run commands; a stray `command`
        argument on any other tool is not an approval of anything."""
        executor, _calls = _executor()
        agent = _agent(
            NoLLM(), executor, approved_commands=[YELLOW], principal=PRINCIPAL
        )
        agent._record_command_approval("read_file", {"command": YELLOW}, "ok", False)
        with get_connection(db) as conn:
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM approved_command_decisions"
                ).fetchone()[0]
                == 0
            )

    def test_a_clean_run_no_human_approved_is_not(self, db) -> None:
        """Running clean is not the qualification; a human's approval is. An
        unapproved YELLOW command pauses on the live path, so the turn above
        cannot show this -- but a command can also run clean with no human
        (earned autonomy), and that must never mint a human approval."""
        executor, _calls = _executor()
        agent = _agent(NoLLM(), executor, approved_commands=[], principal=PRINCIPAL)
        agent._record_command_approval(
            "execute_terminal", {"command": YELLOW}, "ok", False
        )
        with get_connection(db) as conn:
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM approved_command_decisions"
                ).fetchone()[0]
                == 0
            )


# --------------------------------------------------------------------------- #
# Replay
# --------------------------------------------------------------------------- #
class TestReplay:
    @pytest.mark.parametrize(
        "tool, command",
        [("execute_terminal", YELLOW), ("verify", YELLOW_VERIFY)],
    )
    def test_an_approved_reflex_serves_the_turn_with_no_model_call(
        self, db, enabled, tool, command
    ) -> None:
        """The L5 shape: a reflex whose only step is a YELLOW command a human
        approved serves a whole turn, and the model is never consulted."""
        _record(db, command)
        captured: list = []
        executor, runner_calls = _executor()
        chat = NoLLM()
        events = list(
            _agent(
                chat,
                executor,
                cerebellum=_replaying_cerebellum(_playbook(tool, command), captured),
                principal=PRINCIPAL,
            ).run([{"role": "user", "content": "run the check"}])
        )
        types = [e["type"] for e in events]
        assert "cerebellum_abort" not in types, events
        assert "cerebellum_done" in types
        assert chat.calls == [], "the model was consulted"
        assert any(command in c for c in runner_calls)
        assert [status for _o, status, _f in captured] == ["ok"]

    @pytest.mark.parametrize(
        "case", ["no_record", "flag_off", "other_principal", "stop_unwired"]
    )
    def test_without_a_matching_approval_the_old_behaviour_holds(
        self, db, monkeypatch, case
    ) -> None:
        monkeypatch.setattr(
            config, "REPLAY_APPROVED_COMMANDS_ENABLED", case != "flag_off"
        )
        if case != "no_record":
            _record(db)
        principal = "principal:someone-else" if case == "other_principal" else PRINCIPAL
        captured: list = []
        executor, runner_calls = _executor()
        chat = NoLLM()
        agent = _agent(
            chat,
            executor,
            cerebellum=_replaying_cerebellum(
                _playbook("execute_terminal", YELLOW), captured
            ),
            principal=principal,
        )
        if case == "stop_unwired":
            agent._write_stop = lambda: None  # type: ignore[method-assign]
        events = list(agent.run([{"role": "user", "content": "run the check"}]))
        [abort] = [e for e in events if e["type"] == "cerebellum_abort"]
        assert abort["preflight"] is True
        assert captured == [] and runner_calls == []
        assert len(chat.calls) == 1, "the turn falls through to the model"

    @pytest.mark.parametrize(
        "tool, command",
        [("execute_terminal", YELLOW), ("verify", YELLOW_VERIFY)],
    )
    def test_a_replay_runs_exactly_as_its_live_approval_did_and_keeps_it(
        self, db, enabled, tool, command
    ) -> None:
        """Same handler, same output, as the human-approved live call -- and a
        clean replay leaves the decision in place for the next one."""
        _record(db, command)
        live_executor, _ = _executor()
        live = _agent(
            NoLLM(), live_executor, approved_commands=[command], principal=PRINCIPAL
        )._dispatch(tool, {"command": command})
        replay_executor, _ = _executor()
        agent = _agent(NoLLM(), replay_executor, principal=PRINCIPAL)
        replayed = agent._dispatch_approved(tool, {"command": command})
        assert replayed == live
        assert agent._command_is_authorised(command), "a clean replay revoked it"

    def test_a_failed_replay_withdraws_the_decision(self, db, enabled) -> None:
        _record(db)
        executor, _calls = _executor(exit_code=1)
        agent = _agent(NoLLM(), executor, principal=PRINCIPAL)
        _output, status, failed = agent._dispatch_approved(
            "execute_terminal", {"command": YELLOW}
        )
        assert failed or status != "ok"
        assert not agent._command_is_authorised(YELLOW)
        output, status, _failed = agent._dispatch_approved(
            "execute_terminal", {"command": YELLOW}
        )
        assert status == "approval" and output.startswith(REFLEX_AUTHORITY_WITHHELD)

    def test_the_replay_does_not_leak_the_approval_into_the_turn(
        self, db, enabled
    ) -> None:
        _record(db)
        executor, _calls = _executor()
        agent = _agent(NoLLM(), executor, principal=PRINCIPAL)
        agent._dispatch_approved("execute_terminal", {"command": YELLOW})
        assert YELLOW not in agent.approved_commands

    def test_red_stays_refused_on_replay(self, db, enabled) -> None:
        executor, runner_calls = _executor()
        agent = _agent(NoLLM(), executor, principal=PRINCIPAL)
        _output, status, _failed = agent._dispatch_approved(
            "execute_terminal", {"command": "rm -rf /"}
        )
        assert status == "blocked"
        assert runner_calls == []

    @pytest.mark.parametrize(
        "tool, command",
        [
            ("execute_terminal", YELLOW),
            ("execute_terminal", "git commit -m other"),
            ("verify", YELLOW_VERIFY),
            ("execute_terminal", "echo hi"),
            ("execute_terminal", "rm -rf /"),
        ],
    )
    def test_the_preflight_and_the_dispatcher_agree_with_a_record_present(
        self, db, enabled, tool, command
    ) -> None:
        """The two replay checks ask one question, so they cannot disagree."""
        _record(db, YELLOW)
        _record(db, YELLOW_VERIFY)
        executor, _calls = _executor()
        agent = _agent(NoLLM(), executor, principal=PRINCIPAL)
        withheld = agent._withheld_reflex_step(_playbook(tool, command)) is not None
        _o, status, _f = agent._dispatch_approved(tool, {"command": command})
        assert withheld == (status == "approval"), (tool, command, status)


def _engine_down_executor() -> Executor:
    """What DockerRunner raises when the container engine is not there."""

    def runner(command, *, cwd, env, timeout_s):
        raise RuntimeError("isolated execution unavailable: failed to connect")

    return Executor(
        runner=runner,
        rate_limiter=RateLimiter(),
        audit_log=lambda *a, **k: None,
        emergency_stop=UNGOVERNED_FIXTURE,
    )


class TestOutage:
    """Operator decision 2026-10-25: a command that never ran because its
    sandbox could not start observed nothing about the command, so the human's
    exact-command approval stands. The replay still aborts; nothing runs."""

    @pytest.mark.parametrize(
        "tool, command",
        [("execute_terminal", YELLOW), ("verify", YELLOW_VERIFY)],
    )
    def test_an_outage_keeps_the_approval(self, db, enabled, tool, command) -> None:
        _record(db, command)
        agent = _agent(NoLLM(), _engine_down_executor(), principal=PRINCIPAL)
        _output, status, failed = agent._dispatch_approved(tool, {"command": command})
        assert status == "blocked" and failed, "the replay must still not succeed"
        assert agent._command_is_authorised(command), "an outage withdrew it"

    def test_a_real_failure_still_withdraws_it(self, db, enabled) -> None:
        """The control, beside the outage: the same path, a command that RAN."""
        _record(db)
        executor, _calls = _executor(exit_code=1)
        agent = _agent(NoLLM(), executor, principal=PRINCIPAL)
        agent._dispatch_approved("execute_terminal", {"command": YELLOW})
        assert not agent._command_is_authorised(YELLOW)
