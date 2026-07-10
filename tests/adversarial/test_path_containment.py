"""Direct unit coverage for the shared path-containment primitives introduced
by the 2026-07-10 CWE-22 CodeQL remediation. Nothing previously asserted that
``path_sanitizer.sanitize_path`` (and the KingReportStore/RunLedgerStore
``path_for`` methods routed through it) actually reject an escaping id —
only that the live API's upstream regex gate (``_validate_council_mission_id``)
prevents such an id from ever reaching them. That upstream gate is real, but
these direct tests exist so a regression in either layer fails on its own,
independent of the other.
"""
from __future__ import annotations

import pytest

from aios.api.routes.council import _mission_dir, _validate_council_mission_id
from aios.runtime.king_report import KingReportStore
from aios.runtime.run_ledger import RunLedgerStore
from aios.security.path_sanitizer import sanitize_path
from fastapi import HTTPException


# ── path_sanitizer.sanitize_path ─────────────────────────────────────────────

def test_sanitize_path_rejects_dotdot_escape(tmp_path) -> None:
    base = tmp_path / "missions"
    base.mkdir()
    with pytest.raises(ValueError):
        sanitize_path(base, "../../etc/passwd")


def test_sanitize_path_rejects_absolute_escape(tmp_path) -> None:
    base = tmp_path / "missions"
    base.mkdir()
    outside = tmp_path.parent / "outside"
    with pytest.raises(ValueError):
        sanitize_path(base, str(outside))


def test_sanitize_path_allows_legit_child(tmp_path) -> None:
    base = tmp_path / "missions"
    base.mkdir()
    result = sanitize_path(base, "mission-123")
    assert result == (base / "mission-123").resolve()


def test_sanitize_path_allows_base_itself(tmp_path) -> None:
    base = tmp_path / "missions"
    base.mkdir()
    result = sanitize_path(base, ".")
    assert result == base.resolve()


# ── KingReportStore / RunLedgerStore.path_for ───────────────────────────────

@pytest.mark.parametrize("escaping_id", ["../../evil", "..", "..\\..\\evil"])
def test_king_report_path_for_rejects_escape(tmp_path, escaping_id) -> None:
    store = KingReportStore(tmp_path)
    with pytest.raises(ValueError):
        store.path_for(escaping_id)


def test_king_report_path_for_allows_legit_mission_id(tmp_path) -> None:
    store = KingReportStore(tmp_path)
    path = store.path_for("mission-abc")
    assert path == (tmp_path / "missions" / "mission-abc" / "king_report.json").resolve()


@pytest.mark.parametrize("escaping_id", ["../../evil", "..", "..\\..\\evil"])
def test_run_ledger_path_for_rejects_escape(tmp_path, escaping_id) -> None:
    store = RunLedgerStore(tmp_path)
    with pytest.raises(ValueError):
        store.path_for(escaping_id)


def test_run_ledger_path_for_allows_legit_mission_id(tmp_path) -> None:
    store = RunLedgerStore(tmp_path)
    path = store.path_for("mission-abc")
    assert path == (tmp_path / "missions" / "mission-abc" / "run_ledger.json").resolve()


# ── council.py's own mission-id containment (defense in depth) ─────────────

def test_validate_council_mission_id_rejects_traversal_shapes() -> None:
    for bad_id in ("../../evil", "..", "a/b", "a\\b", ""):
        with pytest.raises(HTTPException):
            _validate_council_mission_id(bad_id)


def test_validate_council_mission_id_allows_legit_id() -> None:
    assert _validate_council_mission_id("mission-abc_123") == "mission-abc_123"


def test_mission_dir_rejects_escape_even_bypassing_upstream_regex(tmp_path) -> None:
    """Direct call to _mission_dir (skipping _validate_council_mission_id) proves
    the function's own containment check is real, not just relying on the
    upstream regex gate every live route already applies first."""
    with pytest.raises(HTTPException):
        _mission_dir(tmp_path, "../../evil")


def test_mission_dir_allows_legit_mission_id(tmp_path) -> None:
    result = _mission_dir(tmp_path, "mission-abc")
    assert result == (tmp_path / "missions" / "mission-abc").resolve()
