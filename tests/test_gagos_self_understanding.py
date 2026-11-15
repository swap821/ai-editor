"""GAGOS understands itself through organ 28 (2026-11-15, the operator:
"honestly understand itself first"). Pinned here:

* the hour scans GAGOS's own code into organ 28's store once per commit, and
  a commit already scanned costs nothing;
* the passport is GAGOS's own: the project an operator's conversations are
  bound to is never replaced by it;
* the council plans each mission with the passport's summary in its trail,
  and the mission records which passport that was.
"""

from __future__ import annotations

import json
from pathlib import Path

from aios.application.memory.authorities import ProjectUnderstandingAuthority
from aios.infrastructure.memory.human_representation_store import ProjectPassportStore
from aios.operations import self_understanding as su
from tests.test_gagos_council_origination import Council, _envelope, _originate
from tools import gagos_daily as tool


def _project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("# GAGOS\n\nA governed AI OS.\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\ndependencies = ['fastapi']\n", encoding="utf-8"
    )
    (root / "frontend").mkdir()
    (root / "frontend" / "package.json").write_text(
        json.dumps(
            {"scripts": {"test": "vitest run"}, "devDependencies": {"vitest": "1"}}
        ),
        encoding="utf-8",
    )
    return root


def _authority(tmp_path: Path) -> ProjectUnderstandingAuthority:
    return ProjectUnderstandingAuthority(ProjectPassportStore(tmp_path / "pp.db"))


def test_gagos_scans_itself_once_per_commit(tmp_path) -> None:
    root, authority = _project(tmp_path / "gagos"), _authority(tmp_path)
    first, scanned = su.understand_self(root, "a" * 40, authority=authority)
    assert scanned and first.verified_at_commit == "a" * 40
    again, scanned = su.understand_self(root, "a" * 40, authority=authority)
    assert not scanned and again.passport_digest == first.passport_digest
    _later, scanned = su.understand_self(root, "b" * 40, authority=authority)
    assert scanned
    assert su.own_passport(authority=authority).verified_at_commit == "b" * 40


def test_the_operators_project_stays_his(tmp_path) -> None:
    """Organ 28 keeps ONE active project; a scan of GAGOS's own code once
    replaced the operator's (found by this test's first run)."""
    root, authority = _project(tmp_path / "gagos"), _authority(tmp_path)
    authority.store.set_active(
        "his-project", {"root": "C:/his"}, operator_identity_digest="operator"
    )
    su.understand_self(root, "a" * 40, authority=authority)
    assert authority.store.get_active_for_operator("operator")[0] == "his-project"
    assert authority.store.get_active()[0] == "his-project"
    assert su.own_passport(authority=authority).project_id == su.GAGOS_PROJECT_ID


def test_the_passport_reads_as_the_councils_trail(tmp_path) -> None:
    root, authority = _project(tmp_path / "gagos"), _authority(tmp_path)
    passport, _ = su.understand_self(root, "c" * 40, authority=authority)
    lines = su.passport_hints(passport)
    assert lines[0].startswith(
        "GAGOS's own passport (organ 28, its code at cccccccccccc)"
    )
    assert "Vitest" in lines[0] and "FastAPI" in lines[0]
    assert any("npm --prefix frontend test" in line for line in lines)
    assert su.passport_hints(None) == []


def test_the_council_plans_with_gagos_passport(tmp_path, monkeypatch) -> None:
    root, authority = _project(tmp_path / "gagos"), _authority(tmp_path)
    passport, _ = su.understand_self(root, "d" * 40, authority=authority)
    monkeypatch.setattr(su, "own_passport", lambda **kw: passport)
    council = Council()
    out = _originate(tmp_path, _envelope(tmp_path), council)
    assert out["state"] == "awaiting_approval"
    (request,) = council.asked
    assert request.pheromone_context[0].startswith("GAGOS's own passport (organ 28")
    assert request.metadata["project_passport"] == {
        "digest": passport.passport_digest,
        "verified_at_commit": "d" * 40,
    }


def test_no_passport_yet_plans_as_before(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(su, "own_passport", lambda **kw: None)
    council = Council()
    _originate(tmp_path, _envelope(tmp_path), council)
    (request,) = council.asked
    assert not any("passport" in line for line in request.pheromone_context)
    assert request.metadata["project_passport"] is None


def test_the_hour_says_what_it_understood(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(tool, "_git", lambda root, *a: "e" * 40)
    seen = []

    def understand(root, head):
        seen.append(head)
        return (
            type(
                "P",
                (),
                {"architecture_summary": "stack: Python, Vitest; folders: aios/"},
            )(),
            True,
        )

    tool.understanding_hour(tmp_path, understand=understand)
    assert seen == ["e" * 40]
    out = capsys.readouterr().out
    assert "understanding: GAGOS's own passport at eeeeeeeeeeee, scanned" in out
    assert "stack: Python, Vitest" in out
