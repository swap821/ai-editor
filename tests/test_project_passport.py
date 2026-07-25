from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from aios.api.deps import get_project_passport_store
from aios.api.main import app
from aios.infrastructure.memory.human_representation_store import ProjectPassportStore
from aios.memory.project_passport import harvest_project_passport


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_project_passport_is_proposal_evidence_only(tmp_path: Path) -> None:
    _write(
        tmp_path / "README.md",
        "# Demo Service\n\nA small FastAPI and React project.\n",
    )
    _write(
        tmp_path / "pyproject.toml",
        "[project]\ndependencies = ['fastapi', 'pytest']\n",
    )
    _write(
        tmp_path / "package.json",
        json.dumps(
            {
                "scripts": {
                    "dev": "vite --host 127.0.0.1",
                    "build": "vite build",
                    "test": "vitest run",
                },
                "dependencies": {"@vitejs/plugin-react": "latest"},
                "devDependencies": {"vite": "latest"},
            }
        ),
    )

    passport = harvest_project_passport(tmp_path)

    assert passport.trusted_memory_activated is False
    assert passport.activation == "proposal/evidence"
    assert passport.purpose.startswith("Demo Service")
    assert "Python" in passport.stack
    assert "FastAPI" in passport.stack
    assert "Node" in passport.stack
    assert "React" in passport.stack
    assert "npm install" in passport.install_commands
    assert "npm run dev" in passport.run_commands
    assert "npm run build" in passport.build_commands
    assert "npm test" in passport.test_commands


def test_project_passport_does_not_expose_secret_files_or_values(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "README.md", "# Secret Demo\n")
    _write(tmp_path / ".env", "API_KEY=super-secret-value\n")
    _write(tmp_path / ".env.example", "PUBLIC_TOKEN=\n")
    _write(tmp_path / "app.py", "import os\nTOKEN = os.environ.get('PUBLIC_TOKEN')\n")

    passport = harvest_project_passport(tmp_path)
    payload = json.dumps(passport.as_dict())

    assert "super-secret-value" not in payload
    assert ".env" not in passport.key_files
    assert ".env" not in passport.evidence_files
    assert "PUBLIC_TOKEN" in passport.env_vars


def test_project_passport_api_returns_real_backend_scan_without_memory_activation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write(tmp_path / "README.md", "# API Passport\n")
    monkeypatch.chdir(tmp_path)

    response = TestClient(app, client=("127.0.0.1", 12345)).post(
        "/api/v1/projects/passport/scan",
        json={"root": ".", "maxFiles": 20},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["trustedMemoryActivated"] is False
    assert body["activation"] == "proposal/evidence"
    assert body["root"] == str(tmp_path.resolve())
    assert body["purpose"].startswith("API Passport")
    status = TestClient(app, client=("127.0.0.1", 12345)).get(
        "/api/v1/projects/passport/status"
    )
    assert status.status_code == 200
    status_body = status.json()
    assert status_body["localOnly"] is True
    assert status_body["trustedMemoryActivated"] is False
    assert status_body["lastScan"]["root"] == str(tmp_path.resolve())
    assert status_body["lastScan"]["purpose"].startswith("API Passport")


def test_project_passport_status_does_not_scan_or_activate_memory(
    tmp_path: Path,
) -> None:
    """A fresh store (nothing ever scanned against it) reports lastScan as
    None honestly -- the durable active-project pointer (organ 28) only
    ever gets set by a real scan, never fabricated."""
    store = ProjectPassportStore(tmp_path / "passports.db")
    app.dependency_overrides[get_project_passport_store] = lambda: store
    try:
        response = TestClient(app, client=("127.0.0.1", 12345)).get(
            "/api/v1/projects/passport/status"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["localOnly"] is True
    assert body["activation"] == "proposal/evidence"
    assert body["trustedMemoryActivated"] is False
    assert body["lastScan"] is None
    assert body["durable"] is None


def test_project_passport_scan_persists_a_real_typed_passport_durably(
    tmp_path: Path, monkeypatch
) -> None:
    """Organ 28: build_project_passport_v1()/ProjectPassportStore previously
    had zero production callers -- every real scan discarded the typed
    representation. A real scan must now durably record it, and re-scanning
    the SAME project must append a new revision to the SAME history rather
    than starting a fresh one each time."""
    project_root = tmp_path / "proj"
    _write(project_root / "README.md", "# Durable Passport Demo\n")
    monkeypatch.chdir(project_root)

    store = ProjectPassportStore(tmp_path / "passports.db")
    app.dependency_overrides[get_project_passport_store] = lambda: store
    try:
        client = TestClient(app, client=("127.0.0.1", 12345))
        first = client.post(
            "/api/v1/projects/passport/scan", json={"root": ".", "maxFiles": 20}
        )
        assert first.status_code == 200

        status = client.get("/api/v1/projects/passport/status")
        assert status.status_code == 200
        durable = status.json()["durable"]
        assert durable is not None
        assert durable["revisionCount"] == 1
        assert durable["passportDigest"]

        second = client.post(
            "/api/v1/projects/passport/scan", json={"root": ".", "maxFiles": 20}
        )
        assert second.status_code == 200

        status_after = client.get("/api/v1/projects/passport/status")
        assert status_after.json()["durable"]["revisionCount"] == 2
    finally:
        app.dependency_overrides.clear()


def test_project_passport_api_rejects_scan_outside_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    _write(workspace / "README.md", "# Workspace\n")
    _write(outside / "README.md", "# Outside\n")
    monkeypatch.chdir(workspace)

    response = TestClient(app, client=("127.0.0.1", 12345)).post(
        "/api/v1/projects/passport/scan",
        json={"root": str(outside)},
    )

    assert response.status_code == 403
    assert "current workspace" in response.json()["detail"]
