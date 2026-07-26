"""Authentication boundary proof for project-passport routes."""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.testclient import TestClient

from aios.api.deps import get_authenticated_principal
from aios.api.main import app


def test_project_passport_scan_and_status_require_authenticated_operator(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "README.md").write_text("# Passport boundary\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def _deny_principal():
        raise HTTPException(status_code=401, detail="authenticated operator session required")

    app.dependency_overrides[get_authenticated_principal] = _deny_principal
    try:
        client = TestClient(app, client=("127.0.0.1", 12345))
        scan = client.post("/api/v1/projects/passport/scan", json={"root": "."})
        status = client.get("/api/v1/projects/passport/status")
    finally:
        app.dependency_overrides.clear()

    assert scan.status_code == 401
    assert status.status_code == 401