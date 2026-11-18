"""His doors to GAGOS's standing skill envelope: read, sign, end (2026-11-18).

The authority is a tmp_path one with its own stop, injected through the
dependency; the real capability store under data/ is never touched.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aios.api.main import app
from aios.api.routes.gagos_tasks import get_gagos_skill_envelope_authority
from aios.application.capabilities.skill_envelope import SkillEnvelopeAuthority
from tests.test_gagos_envelope import _stop

_SIGN = {"days": 30, "maxActivations": 50}
_DOORS = (
    ("GET", "/api/gagos/skill-envelope"),
    ("POST", "/api/gagos/skill-envelope"),
    ("POST", "/api/gagos/skill-envelope/revoke"),
)


@pytest.fixture()
def env(tmp_path):
    authority = SkillEnvelopeAuthority(
        db_path=tmp_path / "caps.db", emergency_stop=_stop(tmp_path)
    )
    app.dependency_overrides[get_gagos_skill_envelope_authority] = lambda: authority
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            yield client, authority
    finally:
        app.dependency_overrides.clear()


def test_no_operator_is_refused(env) -> None:
    client, authority = env
    client.cookies.clear()
    for method, path in _DOORS:
        response = client.request(method, path, json=_SIGN)
        assert response.status_code in (401, 403), (path, response.status_code)
    assert authority.status()["live"] is False


def test_sign_read_and_end(env) -> None:
    client, authority = env
    assert (
        client.get("/api/gagos/skill-envelope").json()["skillEnvelope"]["live"] is False
    )

    signed = client.post("/api/gagos/skill-envelope", json=_SIGN)
    assert signed.status_code == 201, signed.text
    envelope = signed.json()["skillEnvelope"]
    assert envelope["live"] is True
    assert envelope["terms"] == {"days": 30, "max_activations": 50}
    assert envelope["activationsLeft"] == 50
    assert authority.live().envelope_id == envelope["envelopeId"]

    ended = client.post("/api/gagos/skill-envelope/revoke")
    assert ended.status_code == 200, ended.text
    assert ended.json()["ended"] is True
    assert ended.json()["skillEnvelope"] == {
        "live": False,
        "reason": "the skill envelope was ended: revoked by the operator",
    }


@pytest.mark.parametrize(
    "body",
    [
        {"days": 0, "maxActivations": 5},
        {"days": 31, "maxActivations": 5},
        {"days": 5, "maxActivations": 0},
        {"days": 5, "maxActivations": 101},
        {"days": 5, "maxActivations": 5, "extra": 1},
    ],
)
def test_terms_outside_the_bounds_are_refused(env, body) -> None:
    client, authority = env
    response = client.post("/api/gagos/skill-envelope", json=body)
    assert response.status_code == 422, response.text
    assert authority.status()["live"] is False
