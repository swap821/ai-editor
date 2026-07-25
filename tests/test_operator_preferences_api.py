"""Organ 27: real production route tests for OperatorPreferenceStore.

Previously OperatorPreferenceStore had zero production callers anywhere --
these tests prove the route is real (round-trips through the actual store,
not a stub), restricts capture to explicit preferences structurally, keeps
scope leak-prevention, and supports withdrawal.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aios.api.deps import get_operator_preference_store
from aios.api.main import app
from aios.infrastructure.memory.human_representation_store import (
    OperatorPreferenceStore,
)
from aios.memory.facts import SemanticFacts


def _client_with_isolated_store(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "mem.db"
    store = OperatorPreferenceStore(db_path, facts=SemanticFacts(db_path))
    app.dependency_overrides[get_operator_preference_store] = lambda: store
    return TestClient(app, client=("127.0.0.1", 12345))


def test_save_preference_persists_as_explicit_and_active(tmp_path: Path) -> None:
    client = _client_with_isolated_store(tmp_path)
    try:
        response = client.post(
            "/api/v1/preferences",
            json={
                "domain": "testing",
                "key": "prefers_pytest",
                "value": True,
                "scope": "project:ai-editor",
                "confidence": 0.9,
            },
        )
        assert response.status_code == 200
        body = response.json()
        pref = body["preference"]
        assert pref["value"] is True
        assert pref["source_type"] == "explicit_user"
        assert pref["status"] == "active"
        assert pref["scope"] == "project:ai-editor"
    finally:
        app.dependency_overrides.clear()


def test_save_preference_request_cannot_set_source_type_or_status(
    tmp_path: Path,
) -> None:
    """Capture-only-explicit-preferences holds structurally: there is no
    request field a caller can use to submit any other source_type, and no
    way to land a proposed/superseded/rejected preference through this
    route at all."""
    client = _client_with_isolated_store(tmp_path)
    try:
        response = client.post(
            "/api/v1/preferences",
            json={
                "domain": "testing",
                "key": "prefers_pytest",
                "value": True,
                "scope": "project:ai-editor",
                "sourceType": "observed_pattern",
                "status": "proposed",
            },
        )
        assert response.status_code == 200
        pref = response.json()["preference"]
        assert pref["source_type"] == "explicit_user"
        assert pref["status"] == "active"
    finally:
        app.dependency_overrides.clear()


def test_resubmitting_the_same_domain_key_scope_updates_the_same_row(
    tmp_path: Path,
) -> None:
    client = _client_with_isolated_store(tmp_path)
    try:
        first = client.post(
            "/api/v1/preferences",
            json={
                "domain": "testing",
                "key": "prefers_pytest",
                "value": True,
                "scope": "project:ai-editor",
            },
        )
        second = client.post(
            "/api/v1/preferences",
            json={
                "domain": "testing",
                "key": "prefers_pytest",
                "value": True,
                "scope": "project:ai-editor",
                "confidence": 0.5,
            },
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["preferenceId"] == second.json()["preferenceId"]

        listing = client.get(
            "/api/v1/preferences", params={"scope": "project:ai-editor"}
        )
        assert len(listing.json()["preferences"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_a_genuine_value_change_surfaces_as_a_contradiction_not_silently_applied(
    tmp_path: Path,
) -> None:
    client = _client_with_isolated_store(tmp_path)
    try:
        client.post(
            "/api/v1/preferences",
            json={
                "domain": "testing",
                "key": "prefers_pytest",
                "value": True,
                "scope": "project:ai-editor",
            },
        )
        conflicting = client.post(
            "/api/v1/preferences",
            json={
                "domain": "testing",
                "key": "prefers_pytest",
                "value": False,
                "scope": "project:ai-editor",
            },
        )
        assert conflicting.status_code == 409
        assert conflicting.json()["detail"]["reason"] == "contradiction"
    finally:
        app.dependency_overrides.clear()


def test_list_preferences_never_leaks_across_scope(tmp_path: Path) -> None:
    client = _client_with_isolated_store(tmp_path)
    try:
        client.post(
            "/api/v1/preferences",
            json={
                "domain": "editor",
                "key": "tab_width",
                "value": 2,
                "scope": "project:a",
            },
        )
        client.post(
            "/api/v1/preferences",
            json={
                "domain": "editor",
                "key": "tab_width",
                "value": 4,
                "scope": "project:b",
            },
        )

        scoped = client.get("/api/v1/preferences", params={"scope": "project:a"})
        assert scoped.status_code == 200
        values = [p["value"] for p in scoped.json()["preferences"]]
        assert values == [2]
    finally:
        app.dependency_overrides.clear()


def test_list_active_preferences_excludes_withdrawn(tmp_path: Path) -> None:
    client = _client_with_isolated_store(tmp_path)
    try:
        saved = client.post(
            "/api/v1/preferences",
            json={
                "domain": "testing",
                "key": "prefers_pytest",
                "value": True,
                "scope": "project:ai-editor",
            },
        ).json()
        preference_id = saved["preferenceId"]

        before = client.get(
            "/api/v1/preferences/active", params={"scope": "project:ai-editor"}
        )
        assert len(before.json()["preferences"]) == 1

        withdrawal = client.post(f"/api/v1/preferences/{preference_id}/withdraw")
        assert withdrawal.status_code == 200
        assert withdrawal.json()["status"] == "withdrawn"

        after = client.get(
            "/api/v1/preferences/active", params={"scope": "project:ai-editor"}
        )
        assert after.json()["preferences"] == []
    finally:
        app.dependency_overrides.clear()


def test_withdraw_unknown_preference_is_404_not_fabricated_success(
    tmp_path: Path,
) -> None:
    client = _client_with_isolated_store(tmp_path)
    try:
        response = client.post("/api/v1/preferences/no-such-id/withdraw")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
