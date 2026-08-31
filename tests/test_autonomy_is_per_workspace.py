"""Autonomy earned in one workspace must not grant itself in another.

Inventory item 4. `AutonomyLedger.signature()` was
`sha256(f"{action_type}|{norm}")` -- no workspace dimension at all. A streak
earned doing `create *.py` in one project silently granted the same action-shape
in any other project with the same action-shape.

This was the LIVE path, not a latent one. Both places that grant autonomy without
a human call `is_earned`, which keys on this signature:

    aios/agents/tool_agent.py:1169   auto-grant create_file / edit_file
    aios/policy/kernel.py:1014       auto-grant a REQUIRE_HUMAN command

A scoped variant -- `scoped_signature`, carrying `project_id` -- already existed
and had exactly one caller, `GovernedAutonomy`, which has NO production caller at
all (grep: only tests). So the capability was built and the path was never wired:
the seventh instance of that one mistake in this codebase.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

from aios.core.autonomy import AutonomyLedger, workspace_id
from aios.core.verification_strength import VerificationStrength
from aios.security import scope_lock


@pytest.fixture()
def restore_scope() -> Iterator[None]:
    """Scope roots are process-global (inventory item 3, still open)."""
    previous = scope_lock.get_scope_roots()
    try:
        yield
    finally:
        scope_lock.set_scope_roots(previous)


def _earn(ledger: AutonomyLedger, action: str, target: str, times: int) -> None:
    for _ in range(times):
        ledger.record_outcome(
            action, target, success=True, strength=VerificationStrength.STRONG
        )


def test_a_streak_earned_in_one_workspace_does_not_grant_in_another(
    tmp_path: Path, restore_scope: None
) -> None:
    """The whole point of item 4, asserted end to end through the real ledger."""
    workspace_a = tmp_path / "project-a"
    workspace_b = tmp_path / "project-b"
    workspace_a.mkdir()
    workspace_b.mkdir()
    ledger = AutonomyLedger(tmp_path / "autonomy.db", min_successes=2)

    scope_lock.set_scope_roots([workspace_a])
    _earn(ledger, "create_file", "project-a/app.py", times=3)
    assert ledger.is_earned("create_file", "project-a/app.py", enabled=True) is True, (
        "the class must be genuinely earned in workspace A, or this proves nothing"
    )

    # Same action shape, same relative target, different workspace.
    scope_lock.set_scope_roots([workspace_b])
    assert ledger.is_earned("create_file", "project-a/app.py", enabled=True) is False, (
        "a streak earned in workspace A granted autonomy in workspace B -- the "
        "signature is not workspace-bound"
    )


def test_returning_to_the_original_workspace_restores_the_grant(
    tmp_path: Path, restore_scope: None
) -> None:
    """Isolation, not amnesia.

    A rule that simply invalidated everything on any scope change would pass the
    test above while destroying earned autonomy permanently. The grant must come
    back when the same workspace does.
    """
    workspace_a = tmp_path / "a"
    workspace_b = tmp_path / "b"
    workspace_a.mkdir()
    workspace_b.mkdir()
    ledger = AutonomyLedger(tmp_path / "autonomy.db", min_successes=2)

    scope_lock.set_scope_roots([workspace_a])
    _earn(ledger, "create_file", "a/app.py", times=3)

    scope_lock.set_scope_roots([workspace_b])
    assert ledger.is_earned("create_file", "a/app.py", enabled=True) is False

    scope_lock.set_scope_roots([workspace_a])
    assert ledger.is_earned("create_file", "a/app.py", enabled=True) is True, (
        "returning to the workspace that earned the streak did not restore it"
    )


def test_a_failure_in_one_workspace_does_not_revoke_another(
    tmp_path: Path, restore_scope: None
) -> None:
    """Isolation must hold in the punitive direction too.

    If workspace B's failure reset workspace A's streak, one project could
    silently strip another project's earned autonomy -- a denial-of-service
    across the boundary this item exists to draw.
    """
    workspace_a = tmp_path / "a"
    workspace_b = tmp_path / "b"
    workspace_a.mkdir()
    workspace_b.mkdir()
    ledger = AutonomyLedger(tmp_path / "autonomy.db", min_successes=2)

    scope_lock.set_scope_roots([workspace_a])
    _earn(ledger, "create_file", "shared/app.py", times=3)

    scope_lock.set_scope_roots([workspace_b])
    ledger.record_outcome(
        "create_file", "shared/app.py", success=False, strength=VerificationStrength.STRONG
    )

    scope_lock.set_scope_roots([workspace_a])
    assert ledger.is_earned("create_file", "shared/app.py", enabled=True) is True, (
        "a failure recorded in workspace B revoked workspace A's earned class"
    )


def test_the_workspace_id_is_resolved_per_call_not_at_construction(
    tmp_path: Path, restore_scope: None
) -> None:
    """A long-lived ledger must follow a scope change, not its birth moment.

    `AutonomyLedger` is constructed once and injected; caching the workspace at
    __init__ would mean a process that switches workspace keeps granting against
    the old one -- exactly the leak, reintroduced through a different door.
    """
    workspace_a = tmp_path / "a"
    workspace_b = tmp_path / "b"
    workspace_a.mkdir()
    workspace_b.mkdir()

    scope_lock.set_scope_roots([workspace_a])
    ledger = AutonomyLedger(tmp_path / "autonomy.db", min_successes=2)
    signature_a = ledger.signature("create_file", "x.py")

    scope_lock.set_scope_roots([workspace_b])
    assert ledger.signature("create_file", "x.py") != signature_a, (
        "the signature did not change with the workspace; the id is cached at "
        "construction"
    )


def test_an_empty_scope_is_a_distinct_workspace_not_a_wildcard(
    tmp_path: Path, restore_scope: None
) -> None:
    """Unknown scope must not collide with a real workspace's streak.

    `set_scope_roots` refuses an empty list, so this exercises the fallback
    directly: no declared scope resolves to the project root, which is A
    workspace -- never a value that matches everything.
    """
    from aios import config
    from aios.core import autonomy as autonomy_module

    workspace_a = tmp_path / "a"
    workspace_a.mkdir()
    scope_lock.set_scope_roots([workspace_a])
    scoped = workspace_id()

    original = scope_lock.get_scope_roots
    try:
        autonomy_module.scope_lock.get_scope_roots = lambda: ()
        fallback = workspace_id()
    finally:
        autonomy_module.scope_lock.get_scope_roots = original

    assert fallback != scoped
    assert fallback == autonomy_module.hashlib.sha256(
        str(Path(config.PROJECT_ROOT).resolve())
        .replace("\\", "/")
        .rstrip("/")
        .lower()
        .encode("utf-8")
    ).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Migration
# --------------------------------------------------------------------------- #
_LEGACY_SCHEMA = """
CREATE TABLE earned_autonomy (
    signature TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    target_shape TEXT NOT NULL,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    streak INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'probation',
    earned_at TEXT,
    revoked_at TEXT,
    last_outcome_at TEXT,
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);
"""


def test_an_existing_ledger_migrates_and_its_rows_go_inert(tmp_path: Path) -> None:
    """Opening a pre-migration DB must not crash, and must not grant.

    A row that was `earned` with a streak of 9 under the old two-part signature
    is now unreachable, because its key was computed without a workspace. That is
    the SAFE direction: the class must be re-earned. Back-filling a workspace we
    cannot actually know would grant autonomy nobody ever verified there.
    """
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript(_LEGACY_SCHEMA)
    conn.execute(
        "INSERT INTO earned_autonomy (signature, action_type, target_shape, "
        "success_count, streak, status, earned_at) "
        "VALUES ('deadbeef', 'create_file', 'training_ground/*.py', 9, 9, "
        "'earned', '2026-01-01')"
    )
    conn.commit()
    conn.close()

    ledger = AutonomyLedger(db, min_successes=2)

    columns = {
        row[1] for row in sqlite3.connect(db).execute("PRAGMA table_info(earned_autonomy)")
    }
    assert "workspace_id" in columns, "the migration did not add the column"
    assert ledger.is_earned("create_file", "training_ground/x.py", enabled=True) is False, (
        "a legacy earned row still grants autonomy; the old signature is still "
        "reachable"
    )


def test_a_fresh_ledger_records_the_workspace_on_the_row(tmp_path: Path) -> None:
    """The column is record-keeping, and it has to actually be written.

    The control is the signature hash; this makes the ledger legible to an
    operator auditing WHICH workspace earned a grant, instead of leaving them to
    infer it from an opaque digest.
    """
    db = tmp_path / "fresh.db"
    ledger = AutonomyLedger(db, min_successes=2)
    ledger.record_outcome(
        "create_file", "training_ground/a.py", success=True,
        strength=VerificationStrength.STRONG,
    )

    rows = sqlite3.connect(db).execute(
        "SELECT workspace_id FROM earned_autonomy"
    ).fetchall()
    assert rows, "no ledger row was written"
    assert rows[0][0] == workspace_id(), (
        "the row does not carry the workspace that earned it"
    )
