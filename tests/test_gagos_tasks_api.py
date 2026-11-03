"""The counter's doors for the operator's tasks to GAGOS (2026-11-03).

The ledger is a tmp_path one, injected through the dependency; the real ledger
under data/ is never touched.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aios.api.main import app
from aios.api.routes.gagos_tasks import get_gagos_task_ledger
from aios.maintenance.daily_work import MAX_TASK_CHARS, DailyLedger

_FILE = "aios/maintenance/daily_work.py"


@pytest.fixture()
def env(tmp_path):
    ledger = DailyLedger(tmp_path / "ledger.db")
    app.dependency_overrides[get_gagos_task_ledger] = lambda: ledger
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            yield client, ledger
    finally:
        app.dependency_overrides.clear()


def _add(client, file=_FILE, text="rename the helper"):
    return client.post("/api/gagos/tasks", json={"file": file, "text": text})


def test_no_operator_is_refused(env) -> None:
    client, ledger = env
    client.cookies.clear()
    for method, path in (
        ("GET", "/api/gagos/tasks"),
        ("POST", "/api/gagos/tasks"),
        ("POST", "/api/gagos/tasks/gt-0123456789/cancel"),
    ):
        response = client.request(method, path, json={"file": _FILE, "text": "x"})
        assert response.status_code in (401, 403), (path, response.status_code)
    assert ledger.tasks() == []


def test_add_list_and_cancel(env) -> None:
    client, ledger = env
    created = _add(client)
    assert created.status_code == 201, created.text
    task = created.json()["task"]
    assert task["status"] == "open" and task["task_id"].startswith("gt-")
    assert ledger.task(task["task_id"]) == task

    listed = client.get("/api/gagos/tasks")
    assert listed.status_code == 200
    (item,) = listed.json()["tasks"]
    assert item["task_id"] == task["task_id"] and item["proposal"] is None

    cancelled = client.post(f"/api/gagos/tasks/{task['task_id']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["task"]["status"] == "cancelled"
    assert ledger.task(task["task_id"])["status"] == "cancelled"


def test_the_operator_id_is_never_echoed(env) -> None:
    client, _ledger = env
    from types import SimpleNamespace

    from aios.api.deps import require_privileged_operator

    secret = "op-secret-0f1e2d3c"
    app.dependency_overrides[require_privileged_operator] = lambda: SimpleNamespace(
        principal_id=secret, operator_id=secret
    )
    created = _add(client)
    task_id = created.json()["task"]["task_id"]
    texts = [
        created.text,
        client.get("/api/gagos/tasks").text,
        client.post(f"/api/gagos/tasks/{task_id}/cancel").text,
        client.post(f"/api/gagos/tasks/{task_id}/cancel").text,
    ]
    assert not any(secret in t for t in texts)


def test_bad_path_and_long_text_are_422_with_the_reason(env) -> None:
    client, ledger = env
    bad = _add(client, file="../outside.py")
    assert bad.status_code == 422 and bad.json()["detail"]
    long = _add(client, text="x" * (MAX_TASK_CHARS + 1))
    assert long.status_code == 422
    assert ledger.tasks() == []


def test_extra_body_field_is_422(env) -> None:
    client, ledger = env
    response = client.post(
        "/api/gagos/tasks", json={"file": _FILE, "text": "x", "said_by": "me"}
    )
    assert response.status_code == 422
    assert ledger.tasks() == []


def test_cancelling_a_taken_task_is_409(env) -> None:
    client, ledger = env
    task_id = _add(client).json()["task"]["task_id"]
    assert ledger.take_task(task_id, "p-1")
    response = client.post(f"/api/gagos/tasks/{task_id}/cancel")
    assert response.status_code == 409 and "taken" in response.json()["detail"]
    assert ledger.task(task_id)["status"] == "taken"


def test_unknown_and_malformed_ids_are_404(env) -> None:
    client, _ledger = env
    for task_id in ("gt-0123456789", "nonsense", "gt-ZZZZZZZZZZ"):
        assert client.post(f"/api/gagos/tasks/{task_id}/cancel").status_code == 404
