"""HTTP-level coverage for /api/v1/projects/scope-hints — the first live
caller of aios/cognition/repo_map.py's scan_symbol_repo_map/
scope_hints_for_contract, which previously had zero callers anywhere in the
codebase outside their own tests.
"""
from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from aios.api.main import app


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
        yield test_client


def test_scope_hints_recommends_files_within_allowed_scope(client, tmp_path, monkeypatch) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "login.py").write_text(
        "def handle_login():\n    '''fix the login bug'''\n    pass\n", encoding="utf-8"
    )
    monkeypatch.chdir(project)

    resp = client.post(
        "/api/v1/projects/scope-hints",
        json={"goal": "fix the login bug", "allowedFiles": ["login.py"]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["authority"] == "proposal/evidence"
    assert body["canWidenScope"] is False
    assert isinstance(body["recommendedFiles"], list)
    assert isinstance(body["outOfScopeMatches"], list)


def test_scope_hints_never_recommends_files_outside_allowed_list(client, tmp_path, monkeypatch) -> None:
    project = tmp_path / "proj2"
    project.mkdir()
    (project / "other.py").write_text(
        "def unrelated_symbol_for_the_goal_text():\n    pass\n", encoding="utf-8"
    )
    monkeypatch.chdir(project)

    resp = client.post(
        "/api/v1/projects/scope-hints",
        json={"goal": "unrelated_symbol_for_the_goal_text", "allowedFiles": ["login.py"]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "other.py" not in body["recommendedFiles"]


def test_scope_hints_rejects_traversal_outside_workspace(client, tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    resp = client.post(
        "/api/v1/projects/scope-hints",
        json={"goal": "anything", "root": "../outside"},
    )

    assert resp.status_code == 403
