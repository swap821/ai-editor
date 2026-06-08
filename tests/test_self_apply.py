"""Tests for the Self-Analysis T3a apply engine (aios.core.self_apply).

The engine is driven directly with a seeded temp DB + a tiny temp ``project_root``
containing a fake ``aios/`` file, a fake audit sink (a list), and a fake verifier
whose verdict is parametrizable — so no real shell, model, or test suite runs. The
single REAL operation under test is the file write itself (``git apply``), against
the throwaway temp root.
"""
from __future__ import annotations

import pytest

from aios.core.self_apply import SelfApplyEngine
from aios.core.verifier import VerifierResult
from aios.memory.db import connect, get_connection, init_memory_db

_TARGET = "aios/widget.py"
_BEFORE = "def f():\n    return 1\n"
_AFTER = "def f():\n    return 2\n"
_GOOD_DIFF = (
    "--- a/aios/widget.py\n"
    "+++ b/aios/widget.py\n"
    "@@ -1,2 +1,2 @@\n"
    " def f():\n"
    "-    return 1\n"
    "+    return 2\n"
)


class _FakeVerifier:
    def __init__(self, *, passed: bool = True, summary: str = "fake verify") -> None:
        self._passed = passed
        self.summary = summary
        self.calls: list[str] = []

    def verify(self, command: str, *, session_id=None) -> VerifierResult:
        self.calls.append(command)
        return VerifierResult(
            passed=self._passed, summary=self.summary,
            confidence_delta=0.0 if self._passed else -0.2,
        )


class _FakeAudit:
    """Records (actor, payload, zone) and returns an entry with a unique entry_id."""

    def __init__(self) -> None:
        self.entries: list[tuple] = []
        self._next = 1

    def __call__(self, actor, payload, zone):
        entry = type("E", (), {"entry_id": self._next})()
        self.entries.append((actor, payload, zone))
        self._next += 1
        return entry


def _seed(
    tmp_path,
    *,
    target_rel: str = _TARGET,
    content: str = _BEFORE,
    diff: str = _GOOD_DIFF,
    proposed_by: str = "self_analysis_agent",
    proposed_zone: str = "YELLOW",
    status: str = "proposed",
):
    """Create project_root/<target> + a seeded report row; return (root, db, id)."""
    from pathlib import Path

    project_root = tmp_path / "proj"
    target = project_root / target_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    db_path = tmp_path / "report.db"
    init_memory_db(db_path)
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO self_analysis_report "
            "(target_path, finding_type, evidence, proposed_diff, proposed_zone, proposed_by, status) "
            "VALUES (?, 'complexity', 'e', ?, ?, ?, ?)",
            (target_rel, diff, proposed_zone, proposed_by, status),
        )
        pid = int(cur.lastrowid)
    return project_root, db_path, pid


def _engine(project_root, db_path, *, verifier=None, audit=None) -> SelfApplyEngine:
    return SelfApplyEngine(
        verifier=verifier or _FakeVerifier(passed=True),
        db_path=db_path,
        project_root=project_root,
        audit_log=audit or _FakeAudit(),
        verify_command="fake-verify",
    )


def _row(db_path, pid):
    with get_connection(db_path) as conn:
        return conn.execute(
            "SELECT status, applied_audit_id, approved_by FROM self_analysis_report WHERE id = ?",
            (pid,),
        ).fetchone()


# --------------------------------------------------------------------------- #
def test_apply_happy_path(tmp_path) -> None:
    pr, db, pid = _seed(tmp_path)
    audit = _FakeAudit()
    res = _engine(pr, db, verifier=_FakeVerifier(passed=True), audit=audit).apply(
        pid, approved_by="alice"
    )
    assert res.status == "applied"
    assert (pr / _TARGET).read_text(encoding="utf-8") == _AFTER
    row = _row(db, pid)
    assert row["status"] == "applied"
    assert row["applied_audit_id"] is not None
    assert row["approved_by"] == "alice"
    assert audit.entries, "the applied change must be audited"
    assert res.audit_id is not None


def test_apply_verify_fail_rolls_back(tmp_path) -> None:
    pr, db, pid = _seed(tmp_path)
    audit = _FakeAudit()
    res = _engine(pr, db, verifier=_FakeVerifier(passed=False, summary="1 failed"), audit=audit).apply(
        pid, approved_by="alice"
    )
    assert res.status == "rolled_back"
    assert (pr / _TARGET).read_text(encoding="utf-8") == _BEFORE  # restored byte-identical
    assert _row(db, pid)["status"] == "rolled_back"
    # Both the apply and the rollback are on the ledger.
    payloads = " ".join(p for _, p, _ in audit.entries)
    assert "APPLY" in payloads and "ROLLBACK" in payloads


@pytest.mark.parametrize("approver", ["", "self_analysis_agent"])
def test_apply_no_self_approval_refused(tmp_path, approver) -> None:
    pr, db, pid = _seed(tmp_path)
    fake_v = _FakeVerifier(passed=True)
    res = _engine(pr, db, verifier=fake_v).apply(pid, approved_by=approver)
    assert res.status == "refused"
    assert (pr / _TARGET).read_text(encoding="utf-8") == _BEFORE  # untouched
    assert _row(db, pid)["status"] == "proposed"
    assert fake_v.calls == [], "verify must never run when approval is refused"


def test_apply_red_frozen_core_refused(tmp_path) -> None:
    # A proposal under aios/security/ is RED -> refused (that is T4); verify never runs.
    diff = _GOOD_DIFF.replace("aios/widget.py", "aios/security/gate.py")
    pr, db, pid = _seed(tmp_path, target_rel="aios/security/gate.py", diff=diff, proposed_zone="RED")
    fake_v = _FakeVerifier(passed=True)
    res = _engine(pr, db, verifier=fake_v).apply(pid, approved_by="alice")
    assert res.status == "refused" and "RED" in res.reason
    assert (pr / "aios/security/gate.py").read_text(encoding="utf-8") == _BEFORE
    assert fake_v.calls == []


def test_apply_diff_does_not_apply_cleanly_refused(tmp_path) -> None:
    # A diff whose context doesn't match the file -> git apply --check fails -> refused,
    # the row stays 'proposed', the file is untouched.
    stale = _GOOD_DIFF.replace("    return 1", "    return 999")
    pr, db, pid = _seed(tmp_path, diff=stale)
    res = _engine(pr, db).apply(pid, approved_by="alice")
    assert res.status == "refused" and "apply" in res.reason.lower()
    assert (pr / _TARGET).read_text(encoding="utf-8") == _BEFORE
    assert _row(db, pid)["status"] == "proposed"


def test_apply_multi_file_diff_refused(tmp_path) -> None:
    multi = _GOOD_DIFF + "--- a/aios/other.py\n+++ b/aios/other.py\n@@ -1 +1 @@\n-a\n+b\n"
    pr, db, pid = _seed(tmp_path, diff=multi)
    res = _engine(pr, db).apply(pid, approved_by="alice")
    assert res.status == "refused" and "exactly" in res.reason
    assert (pr / _TARGET).read_text(encoding="utf-8") == _BEFORE


def test_apply_foreign_path_diff_refused(tmp_path) -> None:
    # The diff's single file differs from the row's target_path -> refused.
    foreign = _GOOD_DIFF.replace("aios/widget.py", "aios/elsewhere.py")
    pr, db, pid = _seed(tmp_path, diff=foreign)
    res = _engine(pr, db).apply(pid, approved_by="alice")
    assert res.status == "refused"
    assert (pr / _TARGET).read_text(encoding="utf-8") == _BEFORE


def test_apply_escaping_target_refused(tmp_path) -> None:
    # A target_path that escapes the project root is refused (and the diff agrees).
    diff = _GOOD_DIFF.replace("aios/widget.py", "../escape.py")
    pr, db, pid = _seed(tmp_path, target_rel="aios/widget.py", diff=diff)
    # The row's target_path is the legit file, but the diff references ../escape.py,
    # so single-file confinement (paths != {target}) refuses it.
    res = _engine(pr, db).apply(pid, approved_by="alice")
    assert res.status == "refused"
    assert (pr / _TARGET).read_text(encoding="utf-8") == _BEFORE


@pytest.mark.parametrize("status", ["open", "applied", "rejected", "rolled_back"])
def test_apply_non_proposed_refused(tmp_path, status) -> None:
    pr, db, pid = _seed(tmp_path, status=status)
    res = _engine(pr, db).apply(pid, approved_by="alice")
    assert res.status == "refused" and "not 'proposed'" in res.reason
    assert (pr / _TARGET).read_text(encoding="utf-8") == _BEFORE


def test_apply_missing_proposal_refused(tmp_path) -> None:
    pr, db, _pid = _seed(tmp_path)
    res = _engine(pr, db).apply(99999, approved_by="alice")
    assert res.status == "refused" and "no proposal" in res.reason


def test_apply_blocked_when_audit_fails(tmp_path) -> None:
    # Fail-closed: the APPLY is audited BEFORE the write, so an audit failure must
    # refuse and leave the file untouched + the row 'proposed' + verify never run.
    pr, db, pid = _seed(tmp_path)

    def boom_audit(*a, **k):
        raise RuntimeError("ledger locked")

    fake_v = _FakeVerifier(passed=True)
    res = _engine(pr, db, verifier=fake_v, audit=boom_audit).apply(pid, approved_by="alice")
    assert res.status == "refused" and "audit failed" in res.reason
    assert (pr / _TARGET).read_text(encoding="utf-8") == _BEFORE  # never written
    assert _row(db, pid)["status"] == "proposed"
    assert fake_v.calls == [], "verify must never run when the apply is refused"


def test_apply_two_snapshot_integrity_mismatch_refused(tmp_path, monkeypatch) -> None:
    # If the on-disk bytes after the write don't equal the independently-computed
    # before+diff, the integrity check restores and refuses (catches unintended edits).
    pr, db, pid = _seed(tmp_path)
    eng = _engine(pr, db, verifier=_FakeVerifier(passed=True))
    monkeypatch.setattr(eng, "_expected_after", lambda *a, **k: b"SOMETHING ELSE")
    res = eng.apply(pid, approved_by="alice")
    assert res.status == "refused" and "integrity" in res.reason.lower()
    assert (pr / _TARGET).read_text(encoding="utf-8") == _BEFORE  # restored
    assert _row(db, pid)["status"] == "proposed"


def test_approved_by_migration_on_legacy_db(tmp_path) -> None:
    # A legacy self_analysis_report without approved_by gains it via _migrate.
    db_path = tmp_path / "legacy.db"
    conn = connect(db_path)
    conn.executescript(
        "CREATE TABLE self_analysis_report ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " target_path TEXT NOT NULL, finding_type TEXT NOT NULL, evidence TEXT NOT NULL,"
        " status TEXT NOT NULL DEFAULT 'open');"
        "INSERT INTO self_analysis_report (target_path, finding_type, evidence, status) "
        "VALUES ('aios/x.py', 'smell', 'e', 'proposed');"
    )
    conn.commit()
    conn.close()

    init_memory_db(db_path)  # runs the migration

    with get_connection(db_path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(self_analysis_report)")}
    assert "approved_by" in cols and "proposed_by" in cols
