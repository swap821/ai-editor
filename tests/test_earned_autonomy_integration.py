"""End-to-end: what actually lets a write run without a human, through the real
ToolAgent turn loop.

A write is authorised by ONE thing: a human having approved exactly those bytes
at exactly that path, in this workspace. It used to be authorised by an earned
`AutonomyLedger` CLASS, whose write signatures collapse a target to
`<dir>/*<.ext>` -- so a streak on `notes.txt` authorised any content to any
`.txt` in that directory. These tests were written against that policy and now
assert the narrower one, including the case the change exists for: an earned
glob authorising nothing.

Commands still earn autonomy by class; this is about writes.

A fake chat client drives the loop deterministically; the real security gateway
and scope lock still run.
"""

from __future__ import annotations

from aios import config
from aios.agents.tool_agent import ToolAgent
from aios.core.autonomy import AutonomyLedger
from aios.core.replay_writes import (
    UNGOVERNED_FIXTURE,
    content_digest,
    is_approved_write,
    record_approval,
)
from aios.core.executor import Executor
from aios.security import scope_lock
from aios.security.gateway import RateLimiter


class _ClearStop:
    """A latch that is wired and not engaged.

    These tests used to build ledgers with no stop at all, which meant every
    write authorisation skipped the emergency-stop check -- so they passed
    while proving nothing about it. A wired, clear latch keeps them exercising
    the control.
    """

    def assert_operational(self):
        return None


class ScriptedChat:
    def __init__(self, responses):
        self._responses = list(responses)

    def chat(self, messages, *, tools=None, model=None):
        return self._responses.pop(0)


def _runner(command, *, cwd, env, timeout_s):
    return f"ran: {command}", "", 0


def _executor():
    return Executor(
        runner=_runner, rate_limiter=RateLimiter(), audit_log=lambda *a, **k: None
    )


def _create_call(filepath, content):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "function": {
                    "name": "create_file",
                    "arguments": {"filepath": filepath, "content": content},
                }
            }
        ],
    }


def _in_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "EARNED_AUTONOMY_ENABLED", True)
    original = scope_lock.get_scope_roots()
    scope_lock.set_scope_roots([tmp_path])
    return original


def test_earned_write_auto_applies_without_a_human(tmp_path, monkeypatch) -> None:
    original = _in_sandbox(tmp_path, monkeypatch)
    try:
        db = tmp_path / "mem.db"
        ledger = AutonomyLedger(
            db_path=db, min_successes=2, emergency_stop=_ClearStop()
        )
        # The human approved exactly these bytes at exactly this path.
        monkeypatch.setattr(config, "MEMORY_DB_PATH", db)
        monkeypatch.setattr(config, "REPLAY_APPROVED_WRITES_ENABLED", True)
        record_approval("notes.txt", "hello world", db_path=db)

        chat = ScriptedChat(
            [
                _create_call("notes.txt", "hello world"),
                {"role": "assistant", "content": "done"},
            ]
        )
        events = list(
            ToolAgent(chat, _executor(), max_iters=3, autonomy=ledger).run(
                [{"role": "user", "content": "write the notes"}]
            )
        )
        types = [e["type"] for e in events]

        assert "earned_autonomy" in types  # the bridge fired
        assert "human_required" not in types  # no pause
        assert (tmp_path / "notes.txt").read_text() == "hello world"  # actually landed
    finally:
        scope_lock.set_scope_roots(list(original))


def test_unearned_write_still_pauses_for_human(tmp_path, monkeypatch) -> None:
    original = _in_sandbox(tmp_path, monkeypatch)
    try:
        # A ledger with nothing earned (threshold never reached).
        ledger = AutonomyLedger(db_path=tmp_path / "mem.db", min_successes=5)
        assert not ledger.is_earned("create_file", "notes.txt")

        chat = ScriptedChat(
            [
                _create_call("notes.txt", "hello world"),
                {"role": "assistant", "content": "done"},
            ]
        )
        events = list(
            ToolAgent(chat, _executor(), max_iters=3, autonomy=ledger).run(
                [{"role": "user", "content": "write the notes"}]
            )
        )
        types = [e["type"] for e in events]

        assert "human_required" in types  # still supervised
        assert "earned_autonomy" not in types
        assert not (tmp_path / "notes.txt").exists()  # nothing written
    finally:
        scope_lock.set_scope_roots(list(original))


def test_no_ledger_means_today_behaviour(tmp_path, monkeypatch) -> None:
    """With autonomy=None (the default everywhere today) the write still pauses."""
    original = _in_sandbox(tmp_path, monkeypatch)
    try:
        chat = ScriptedChat(
            [
                _create_call("notes.txt", "hello world"),
                {"role": "assistant", "content": "done"},
            ]
        )
        events = list(
            ToolAgent(chat, _executor(), max_iters=3).run(
                [{"role": "user", "content": "write the notes"}]
            )
        )
        types = [e["type"] for e in events]
        assert "human_required" in types
        assert "earned_autonomy" not in types
    finally:
        scope_lock.set_scope_roots(list(original))


def test_earned_grant_writes_a_distinct_earned_autonomy_audit_entry(
    tmp_path, monkeypatch
) -> None:
    """The autonomous DECISION is recorded in the audit chain as its own actor,
    carrying the evidence — distinct from the write's 'tool-agent' entry."""
    original = _in_sandbox(tmp_path, monkeypatch)
    try:
        db = tmp_path / "mem.db"
        ledger = AutonomyLedger(
            db_path=db, min_successes=2, emergency_stop=_ClearStop()
        )
        monkeypatch.setattr(config, "MEMORY_DB_PATH", db)
        monkeypatch.setattr(config, "REPLAY_APPROVED_WRITES_ENABLED", True)
        record_approval("notes.txt", "hello world", db_path=db)
        audited: list[tuple] = []
        chat = ScriptedChat(
            [
                _create_call("notes.txt", "hello world"),
                {"role": "assistant", "content": "done"},
            ]
        )
        agent = ToolAgent(
            chat,
            _executor(),
            max_iters=3,
            autonomy=ledger,
            audit_log=lambda *a, **k: audited.append(a),
        )
        list(agent.run([{"role": "user", "content": "write the notes"}]))

        earned = [a for a in audited if a and a[0] == "earned-autonomy"]
        assert earned, "the autonomous grant must write an earned-autonomy audit entry"
        assert "AUTO-GRANT" in earned[0][1] and "notes.txt" in earned[0][1]
        # The line names the REASON, which is no longer a streak count: there is
        # no streak, only a human's prior decision about these exact bytes.
        assert "approved exactly these bytes" in earned[0][1]
    finally:
        scope_lock.set_scope_roots(list(original))


def test_a_weak_auto_verify_revokes_the_exact_write_decision(
    tmp_path, monkeypatch
) -> None:
    """The verifier's word withdraws authorisation. THE BAR for the convergence.

    When writes ran through `AutonomyLedger`, the forced auto-verify was the
    only writer of autonomy evidence and a bad verdict revoked the class
    instantly. Moving authorisation onto exact-decision records is a narrowing
    in every respect but this one -- the records had no revocation -- so
    without it the change would look like a tightening while deleting a
    safety mechanism.

    A `.py` write with a sibling test triggers forced auto-verify. The fake
    runner exits 0 but reports no passing assertions, so the verifier emits
    WEAK. A human approving bytes once is not a standing promise that those
    bytes still work.
    """
    original = _in_sandbox(tmp_path, monkeypatch)
    try:
        (tmp_path / "test_new.py").write_text("def test_new():\n    assert True\n")
        db = tmp_path / "mem.db"
        ledger = AutonomyLedger(
            db_path=db, min_successes=2, emergency_stop=_ClearStop()
        )
        monkeypatch.setattr(config, "MEMORY_DB_PATH", db)
        monkeypatch.setattr(config, "REPLAY_APPROVED_WRITES_ENABLED", True)
        record_approval("new.py", "x = 1\n", db_path=db)
        assert is_approved_write(
            "new.py",
            content_digest("x = 1\n"),
            db_path=db,
            enabled=True,
            emergency_stop=UNGOVERNED_FIXTURE,
        ), "precondition: the write must start out authorised"

        chat = ScriptedChat(
            [
                _create_call("new.py", "x = 1\n"),
                {"role": "assistant", "content": "done"},
            ]
        )
        events = list(
            ToolAgent(chat, _executor(), max_iters=3, autonomy=ledger).run(
                [{"role": "user", "content": "write the module"}]
            )
        )

        assert "earned_autonomy" in [e["type"] for e in events]
        assert (tmp_path / "new.py").read_text() == "x = 1\n"

        assert not is_approved_write(
            "new.py",
            content_digest("x = 1\n"),
            db_path=db,
            enabled=True,
            emergency_stop=UNGOVERNED_FIXTURE,
        ), "a write that failed its own verify is still replayable unattended"
    finally:
        scope_lock.set_scope_roots(list(original))


def test_an_earned_glob_authorises_nothing(tmp_path, monkeypatch) -> None:
    """THE BAR for the convergence.

    `AutonomyLedger._normalize` collapses a write target to `<dir>/*<.ext>`, so
    a streak on one `.txt` used to authorise ANY content to ANY `.txt` beside
    it. Earn that streak, then ask for a DIFFERENT file with DIFFERENT bytes and
    require a human pause.

    If the old key ever comes back this fails, which is the entire point of
    writing it as a separate test rather than trusting the rewritten ones above.
    """
    original = _in_sandbox(tmp_path, monkeypatch)
    try:
        db = tmp_path / "mem.db"
        ledger = AutonomyLedger(
            db_path=db, min_successes=2, emergency_stop=_ClearStop()
        )
        monkeypatch.setattr(config, "MEMORY_DB_PATH", db)
        monkeypatch.setattr(config, "REPLAY_APPROVED_WRITES_ENABLED", True)

        ledger.record_outcome("create_file", "notes.txt", success=True)
        ledger.record_outcome("create_file", "notes.txt", success=True)
        assert ledger.is_earned("create_file", "notes.txt"), (
            "precondition: the glob streak must actually be earned"
        )
        assert ledger.is_earned("create_file", "other.txt"), (
            "precondition: the glob must be as wide as the change claims"
        )

        chat = ScriptedChat(
            [
                _create_call("other.txt", "content nobody approved"),
                {"role": "assistant", "content": "done"},
            ]
        )
        events = list(
            ToolAgent(chat, _executor(), max_iters=3, autonomy=ledger).run(
                [{"role": "user", "content": "write the other notes"}]
            )
        )
        types = [e["type"] for e in events]

        assert "human_required" in types, "an earned glob authorised a write"
        assert "earned_autonomy" not in types
        assert not (tmp_path / "other.txt").exists()
    finally:
        scope_lock.set_scope_roots(list(original))


def test_an_auto_granted_write_records_no_human_approval(tmp_path, monkeypatch) -> None:
    """The machine's own decision must never become evidence of a human's.

    `_grant_earned` adds to the same `approved_creations` dict that
    `_pre_apply_grants` iterates -- and `_pre_apply_grants` is where a human
    approval gets recorded as a replayable decision. They do not collide today
    only because one runs at turn start and the other mutates later. That is
    ordering, not design, so it is pinned here: a reorder that let an
    auto-granted write reach the recorder would manufacture an approval nobody
    gave, and every later replay would cite it.
    """
    original = _in_sandbox(tmp_path, monkeypatch)
    try:
        db = tmp_path / "mem.db"
        ledger = AutonomyLedger(
            db_path=db, min_successes=2, emergency_stop=_ClearStop()
        )
        monkeypatch.setattr(config, "MEMORY_DB_PATH", db)
        monkeypatch.setattr(config, "REPLAY_APPROVED_WRITES_ENABLED", True)
        record_approval("notes.txt", "hello world", db_path=db)

        chat = ScriptedChat(
            [
                _create_call("notes.txt", "hello world"),
                {"role": "assistant", "content": "done"},
            ]
        )
        list(
            ToolAgent(chat, _executor(), max_iters=3, autonomy=ledger).run(
                [{"role": "user", "content": "write the notes"}]
            )
        )

        from aios.memory.db import get_connection

        with get_connection(db) as conn:
            rows = conn.execute(
                "SELECT COUNT(*) c FROM approved_write_decisions"
            ).fetchone()["c"]

        assert rows == 1, (
            f"expected only the human's own decision, found {rows} -- an "
            "auto-granted write was recorded as a human approval"
        )
    finally:
        scope_lock.set_scope_roots(list(original))
