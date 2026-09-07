#!/usr/bin/env python3
"""What actually happens when replayed writes are turned ON, against real files.

Everything claimed about stage 2 so far is a claim about code. This is the
first thing that runs it: `AIOS_REPLAY_APPROVED_WRITES` on, a real sandbox on
disk, dispatch through the real `ToolAgent` into the real `create_file` /
`edit_file` handlers. **No mocks anywhere.**

Eight cases, four of which are refusals. That balance is the point -- a matrix
that only walks success paths proves the feature can work, not that it is
bounded, and bounded is the harder claim.

    create  missing + approved        -> written, bytes match the approval
    create  present + identical       -> confirmed, no write, mtime unchanged
    create  present + differs         -> abstained (create_file cannot overwrite)
    create  not approved              -> blocked
    edit    already applied           -> confirmed, no write
    edit    applicable + approved     -> applied
    edit    applicable + not approved -> blocked
    edit    neither side present      -> abstained

Run:  python scripts/replay_live_matrix.py
Exit: 0 when every case lands where it should, 1 otherwise.

This measures MECHANICS. It says nothing about how often confirmations succeed
in real use -- that needs sustained real usage, which does not exist yet.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aios import config  # noqa: E402
from aios.agents.tool_agent import ToolAgent  # noqa: E402
from aios.core.executor import Executor  # noqa: E402
from aios.core.replay_writes import (  # noqa: E402
    content_digest,
    record_approval,
    record_edit_approval,
    store_content,
)
from aios.memory.db import init_memory_db  # noqa: E402
from aios.security import scope_lock  # noqa: E402

_CONTENT = "def add(a, b):\n    return a + b\n"
_OTHER = "def add(a, b):\n    return a - b\n"
_OLD = "return a + b"
_NEW = "return a * b"


class _Runner:
    def run(self, *a, **k):  # pragma: no cover - no command should run here
        raise AssertionError("the matrix must not execute commands")


class _ClearStop:
    """A latch that is wired and NOT engaged."""

    def assert_operational(self):
        return None


class _EngagedStop:
    """A latch the human has pulled."""

    def assert_operational(self):
        raise RuntimeError("emergency stop engaged")


def _agent(sandbox: Path, db: Path, *, stop=None) -> ToolAgent:
    """An agent whose ledger carries a REAL emergency stop.

    This used to set `agent.autonomy = None`. That made
    `getattr(self.autonomy, "emergency_stop", None)` yield None, and the
    authorisation check then SKIPPED the stop entirely -- so all eight cases
    below passed while the control was never consulted once. The matrix proved
    the digest and credential guards and nothing about the stop, while reading
    as though it had proved both.

    Found by external review 2026-09-07. The ninth case exists because of it.
    """
    from aios.core.autonomy import AutonomyLedger

    agent = ToolAgent(
        None,
        Executor(runner=_Runner(), audit_log=lambda *a, **k: None),
        read_root=sandbox,
    )
    agent.autonomy = AutonomyLedger(
        db_path=db, emergency_stop=stop if stop is not None else _ClearStop()
    )
    return agent


class Matrix:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, bool]] = []

    def check(self, case: str, expected: str, actual: str, extra: str = "") -> None:
        ok = expected == actual
        self.rows.append((case, expected, actual + (f"  {extra}" if extra else ""), ok))

    def report(self) -> int:
        width = max(len(r[0]) for r in self.rows)
        print()
        print(f"{'case'.ljust(width)}  {'expected'.ljust(11)}  actual")
        print("-" * (width + 40))
        for case, expected, actual, ok in self.rows:
            mark = "ok  " if ok else "FAIL"
            print(f"{case.ljust(width)}  {expected.ljust(11)}  {actual}   [{mark}]")
        failed = [r for r in self.rows if not r[3]]
        print()
        print(f"{len(self.rows) - len(failed)}/{len(self.rows)} cases as expected")
        if failed:
            print("FAILED: " + ", ".join(r[0] for r in failed))
        return 1 if failed else 0


def _outcome(status: str) -> str:
    """Collapse a handler result to the vocabulary the matrix speaks."""
    if status == "blocked":
        return "blocked"
    if status in ("ok", "noop"):
        return "written" if status == "ok" else "confirmed"
    return status


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="replay-matrix-"))
    sandbox = root / "sandbox"
    sandbox.mkdir()
    db = root / "matrix.db"
    init_memory_db(db)

    # The real thing being tested: the flag ON, and a real scope root.
    config.REPLAY_APPROVED_WRITES_ENABLED = True
    config.MEMORY_DB_PATH = db
    scope_lock._SCOPE_LOCK = scope_lock.ScopeLockAuthority()
    scope_lock.set_scope_roots([sandbox])

    print(f"sandbox : {sandbox}")
    print(
        f"flag    : AIOS_REPLAY_APPROVED_WRITES = {config.REPLAY_APPROVED_WRITES_ENABLED}"
    )
    print(f"scope   : {[str(p) for p in scope_lock.get_scope_roots()]}")

    m = Matrix()
    agent = _agent(sandbox, db)

    # ---------------------------------------------------------------- creates
    record_approval("a_missing.py", _CONTENT, db_path=db)
    _, status, _ = agent._replay_create_file(
        {
            "filepath": "a_missing.py",
            "content": _CONTENT,
            "content_sha256": content_digest(_CONTENT),
        }
    )
    landed = (sandbox / "a_missing.py").exists() and (
        sandbox / "a_missing.py"
    ).read_text(encoding="utf-8") == _CONTENT
    m.check(
        "create  missing + approved",
        "written",
        _outcome(status),
        "bytes match" if landed else "BYTES DO NOT MATCH",
    )

    target = sandbox / "b_identical.py"
    target.write_text(_CONTENT, encoding="utf-8")
    before = target.stat().st_mtime_ns
    record_approval("b_identical.py", _CONTENT, db_path=db)
    _, status, _ = agent._replay_create_file(
        {
            "filepath": "b_identical.py",
            "content": _CONTENT,
            "content_sha256": content_digest(_CONTENT),
        }
    )
    m.check(
        "create  present + identical",
        "confirmed",
        _outcome(status),
        "mtime unchanged" if target.stat().st_mtime_ns == before else "FILE TOUCHED",
    )

    target = sandbox / "c_differs.py"
    target.write_text(_OTHER, encoding="utf-8")
    record_approval("c_differs.py", _CONTENT, db_path=db)
    _, status, _ = agent._replay_create_file(
        {
            "filepath": "c_differs.py",
            "content": _CONTENT,
            "content_sha256": content_digest(_CONTENT),
        }
    )
    kept = target.read_text(encoding="utf-8") == _OTHER
    m.check(
        "create  present + differs",
        "blocked",
        _outcome(status),
        "original intact" if kept else "ORIGINAL OVERWRITTEN",
    )

    store_content(_CONTENT, db_path=db)  # bytes available, NO approval recorded
    _, status, _ = agent._replay_create_file(
        {
            "filepath": "d_unapproved.py",
            "content": _CONTENT,
            "content_sha256": content_digest(_CONTENT),
        }
    )
    m.check(
        "create  not approved",
        "blocked",
        _outcome(status),
        "absent" if not (sandbox / "d_unapproved.py").exists() else "FILE APPEARED",
    )

    # ------------------------------------------------------------------ edits
    applied = sandbox / "e_applied.py"
    applied.write_text("def f(a, b):\n    " + _NEW + "\n", encoding="utf-8")
    before = applied.stat().st_mtime_ns
    record_edit_approval("e_applied.py", _OLD, _NEW, db_path=db)
    _, status, _ = agent._replay_edit_file(
        {
            "filepath": "e_applied.py",
            "old_string": _OLD,
            "new_string": _NEW,
            "old_sha256": content_digest(_OLD),
            "new_sha256": content_digest(_NEW),
        }
    )
    m.check(
        "edit    already applied",
        "confirmed",
        _outcome(status),
        "mtime unchanged" if applied.stat().st_mtime_ns == before else "FILE TOUCHED",
    )

    live = sandbox / "f_applicable.py"
    live.write_text("def f(a, b):\n    " + _OLD + "\n", encoding="utf-8")
    record_edit_approval("f_applicable.py", _OLD, _NEW, db_path=db)
    _, status, _ = agent._replay_edit_file(
        {
            "filepath": "f_applicable.py",
            "old_string": _OLD,
            "new_string": _NEW,
            "old_sha256": content_digest(_OLD),
            "new_sha256": content_digest(_NEW),
        }
    )
    m.check(
        "edit    applicable + approved",
        "written",
        _outcome(status),
        "new snippet present"
        if _NEW in live.read_text(encoding="utf-8")
        else "NOT APPLIED",
    )

    unapproved = sandbox / "g_unapproved.py"
    body = "def f(a, b):\n    " + _OLD + "\n"
    unapproved.write_text(body, encoding="utf-8")
    _, status, _ = agent._replay_edit_file(
        {
            "filepath": "g_unapproved.py",
            "old_string": _OLD,
            "new_string": _NEW,
            "old_sha256": content_digest(_OLD),
            "new_sha256": content_digest(_NEW),
        }
    )
    m.check(
        "edit    applicable, unapproved",
        "blocked",
        _outcome(status),
        "unchanged"
        if unapproved.read_text(encoding="utf-8") == body
        else "EDIT APPLIED",
    )

    # Neither side present: the confirm layer decides this, not the dispatcher,
    # so ask the layer that owns the question.
    from aios.core.cerebellum import Cerebellum, PlaybookStep

    neither = sandbox / "h_neither.py"
    neither.write_text("def f(a, b):\n    return 0\n", encoding="utf-8")
    store_content(_OLD, db_path=db)
    store_content(_NEW, db_path=db)
    outcome = Cerebellum(db)._confirm_edit(
        PlaybookStep(
            "edit_file",
            {
                "filepath": "h_neither.py",
                "old_sha256": content_digest(_OLD),
                "new_sha256": content_digest(_NEW),
            },
        )
    )
    m.check(
        "edit    neither side present",
        "abstained",
        "abstained" if not outcome.confirmed and not outcome.missing else "other",
        "not permanent" if not outcome.permanent else "PERMANENT (wrong)",
    )

    # ---- 9. the control the first eight never consulted -------------------
    record_approval("i_stopped.py", _CONTENT, db_path=db)
    stopped = _agent(sandbox, db, stop=_EngagedStop())
    _, status, _ = stopped._replay_create_file(
        {
            "filepath": "i_stopped.py",
            "content": _CONTENT,
            "content_sha256": content_digest(_CONTENT),
        }
    )
    m.check(
        "write   approved + STOPPED",
        "blocked",
        _outcome(status),
        "absent" if not (sandbox / "i_stopped.py").exists() else "FILE WRITTEN",
    )

    code = m.report()
    shutil.rmtree(root, ignore_errors=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
