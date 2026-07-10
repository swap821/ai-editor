"""HTTP-level coverage for aios/api/routes/files.py — GET /files/tree, POST
/files/read, POST /files/edit had zero test coverage prior to 2026-07-10
despite being an arbitrary-path file-read/tree/edit surface gated only by
``is_path_in_scope``. These pin the traversal-rejection behavior so a future
refactor that drops the scope check fails CI instead of shipping silently.
"""
from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from aios.api.main import app
from aios.security import scope_lock


@pytest.fixture()
def client() -> Iterator[TestClient]:
    # Loopback client IP required: unauthenticated API access is loopback-only.
    with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
        yield test_client


@pytest.fixture()
def scoped_workspace(tmp_path):
    """Point scope_lock at an isolated tmp_path workspace for the duration
    of the test, then restore the original scope roots."""
    original = scope_lock.get_scope_roots()
    scope_lock.set_scope_roots([tmp_path])
    try:
        yield tmp_path
    finally:
        scope_lock.set_scope_roots(list(original))


def test_read_file_rejects_traversal_outside_scope(client, scoped_workspace) -> None:
    secret = scoped_workspace.parent / "secret_outside_scope.txt"
    secret.write_text("top secret", encoding="utf-8")
    escaping_path = str(scoped_workspace / ".." / "secret_outside_scope.txt")

    resp = client.post("/api/v1/files/read", json={"path": escaping_path})

    assert resp.status_code == 403
    assert "out of bounds" in resp.json()["detail"].lower()


def test_read_file_allows_legit_path_in_scope(client, scoped_workspace) -> None:
    target = scoped_workspace / "ok.txt"
    target.write_text("hello world", encoding="utf-8")

    resp = client.post("/api/v1/files/read", json={"path": str(target)})

    assert resp.status_code == 200
    assert resp.json()["content"] == "hello world"


def test_read_file_404s_on_missing_file_in_scope(client, scoped_workspace) -> None:
    missing = scoped_workspace / "does_not_exist.txt"

    resp = client.post("/api/v1/files/read", json={"path": str(missing)})

    assert resp.status_code == 404


def test_file_tree_rejects_traversal_outside_scope(client, scoped_workspace) -> None:
    escaping_path = str(scoped_workspace / "..")

    resp = client.get("/api/v1/files/tree", params={"root": escaping_path})

    assert resp.status_code == 403
    assert "out of bounds" in resp.json()["detail"].lower()


def test_file_tree_lists_legit_directory_in_scope(client, scoped_workspace) -> None:
    (scoped_workspace / "a.py").write_text("x = 1", encoding="utf-8")
    (scoped_workspace / "sub").mkdir()

    resp = client.get("/api/v1/files/tree", params={"root": str(scoped_workspace)})

    assert resp.status_code == 200
    names = {node["name"] for node in resp.json()}
    assert {"a.py", "sub"} <= names


def test_file_tree_404s_on_missing_directory_in_scope(client, scoped_workspace) -> None:
    missing = scoped_workspace / "no_such_dir"

    resp = client.get("/api/v1/files/tree", params={"root": str(missing)})

    assert resp.status_code == 404


def test_edit_file_rejects_traversal_outside_scope(client, scoped_workspace) -> None:
    escaping_path = str(scoped_workspace / ".." / "secret_outside_scope.txt")

    resp = client.post(
        "/api/v1/files/edit",
        json={"path": escaping_path, "content": "malicious"},
    )

    assert resp.status_code == 403
    assert "out of bounds" in resp.json()["detail"].lower()


def test_edit_file_proposes_for_legit_path_in_scope(client, scoped_workspace) -> None:
    target = scoped_workspace / "editable.txt"
    target.write_text("v1", encoding="utf-8")

    resp = client.post(
        "/api/v1/files/edit",
        json={"path": str(target), "content": "v2"},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "proposed"
