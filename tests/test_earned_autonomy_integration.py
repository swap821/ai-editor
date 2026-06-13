"""End-to-end: the earned-autonomy bridge through the real ToolAgent turn loop.

Proves the seam, not just the ledger: an earned write CLASS auto-applies via the
same gated path (``earned_autonomy`` event, file actually lands, no human pause),
while an un-earned write still pauses for a human (``human_required``, nothing
written). A fake chat client drives the loop deterministically; the real security
gateway + scope-lock still run.
"""
from __future__ import annotations

from aios import config
from aios.agents.tool_agent import ToolAgent
from aios.core.autonomy import AutonomyLedger
from aios.core.executor import Executor
from aios.security import scope_lock
from aios.security.gateway import RateLimiter


class ScriptedChat:
    def __init__(self, responses):
        self._responses = list(responses)

    def chat(self, messages, *, tools=None, model=None):
        return self._responses.pop(0)


def _runner(command, *, cwd, env, timeout_s):
    return f"ran: {command}", "", 0


def _executor():
    return Executor(runner=_runner, rate_limiter=RateLimiter(), audit_log=lambda *a, **k: None)


def _create_call(filepath, content):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "create_file", "arguments": {"filepath": filepath, "content": content}}}
    ]}


def _in_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "EARNED_AUTONOMY_ENABLED", True)
    original = scope_lock.get_scope_roots()
    scope_lock.set_scope_roots([tmp_path])
    return original


def test_earned_write_auto_applies_without_a_human(tmp_path, monkeypatch) -> None:
    original = _in_sandbox(tmp_path, monkeypatch)
    try:
        ledger = AutonomyLedger(db_path=tmp_path / "mem.db", min_successes=2)
        # Earn the create_file '*.txt' class with two verified successes.
        ledger.record_outcome("create_file", "notes.txt", success=True)
        ledger.record_outcome("create_file", "notes.txt", success=True)
        assert ledger.is_earned("create_file", "notes.txt")

        chat = ScriptedChat([
            _create_call("notes.txt", "hello world"),
            {"role": "assistant", "content": "done"},
        ])
        events = list(ToolAgent(chat, _executor(), max_iters=3, autonomy=ledger).run(
            [{"role": "user", "content": "write the notes"}]
        ))
        types = [e["type"] for e in events]

        assert "earned_autonomy" in types       # the bridge fired
        assert "human_required" not in types     # no pause
        assert (tmp_path / "notes.txt").read_text() == "hello world"  # actually landed
    finally:
        scope_lock.set_scope_roots(list(original))


def test_unearned_write_still_pauses_for_human(tmp_path, monkeypatch) -> None:
    original = _in_sandbox(tmp_path, monkeypatch)
    try:
        # A ledger with nothing earned (threshold never reached).
        ledger = AutonomyLedger(db_path=tmp_path / "mem.db", min_successes=5)
        assert not ledger.is_earned("create_file", "notes.txt")

        chat = ScriptedChat([
            _create_call("notes.txt", "hello world"),
            {"role": "assistant", "content": "done"},
        ])
        events = list(ToolAgent(chat, _executor(), max_iters=3, autonomy=ledger).run(
            [{"role": "user", "content": "write the notes"}]
        ))
        types = [e["type"] for e in events]

        assert "human_required" in types         # still supervised
        assert "earned_autonomy" not in types
        assert not (tmp_path / "notes.txt").exists()  # nothing written
    finally:
        scope_lock.set_scope_roots(list(original))


def test_no_ledger_means_today_behaviour(tmp_path, monkeypatch) -> None:
    """With autonomy=None (the default everywhere today) the write still pauses."""
    original = _in_sandbox(tmp_path, monkeypatch)
    try:
        chat = ScriptedChat([
            _create_call("notes.txt", "hello world"),
            {"role": "assistant", "content": "done"},
        ])
        events = list(ToolAgent(chat, _executor(), max_iters=3).run(
            [{"role": "user", "content": "write the notes"}]
        ))
        types = [e["type"] for e in events]
        assert "human_required" in types
        assert "earned_autonomy" not in types
    finally:
        scope_lock.set_scope_roots(list(original))


def test_earned_grant_writes_a_distinct_earned_autonomy_audit_entry(tmp_path, monkeypatch) -> None:
    """The autonomous DECISION is recorded in the audit chain as its own actor,
    carrying the evidence — distinct from the write's 'tool-agent' entry."""
    original = _in_sandbox(tmp_path, monkeypatch)
    try:
        ledger = AutonomyLedger(db_path=tmp_path / "mem.db", min_successes=2)
        ledger.record_outcome("create_file", "notes.txt", success=True)
        ledger.record_outcome("create_file", "notes.txt", success=True)
        audited: list[tuple] = []
        chat = ScriptedChat([
            _create_call("notes.txt", "hello world"),
            {"role": "assistant", "content": "done"},
        ])
        agent = ToolAgent(
            chat, _executor(), max_iters=3, autonomy=ledger,
            audit_log=lambda *a, **k: audited.append(a),
        )
        list(agent.run([{"role": "user", "content": "write the notes"}]))

        earned = [a for a in audited if a and a[0] == "earned-autonomy"]
        assert earned, "the autonomous grant must write an earned-autonomy audit entry"
        assert "AUTO-GRANT" in earned[0][1] and "notes.txt" in earned[0][1]
        assert "verified" in earned[0][1]  # carries the evidence that earned it
    finally:
        scope_lock.set_scope_roots(list(original))
