"""POST /api/v1/plan reaches the model only through Organ 32's gateway.

Found 2026-10-12 by tools/model_call_inventory.py: the route handed the raw
LLM client to the Planner, so its model call passed no gateway entrance --
no emergency-stop check, no redaction, no context record. The forge's own
planner and /api/v1/reflect already went through the gateway.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterator, Optional

import pytest
from fastapi.testclient import TestClient

from aios.api.deps import get_llm_client, get_optional_principal
from aios.api.main import app
from aios.core import model_calls
from aios.domain.identity.models import Principal, PrincipalType


class EntranceRecordingLLM:
    """A planner model that records which gateway entrance asked it."""

    entrances: list[Optional[str]] = []

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        type(self).entrances.append(model_calls.current_entrance())
        return json.dumps(
            {"steps": [{"step_id": "1", "description": "do it", "confidence": 0.9}]}
        )


def _principal(constitution_digest: str) -> Principal:
    return Principal(
        principal_id="operator:plan-test",
        principal_type=PrincipalType.OPERATOR,
        display_name="plan test",
        session_id="s-plan",
        authentication_level="operator",
        authenticated_at=datetime.now(timezone.utc),
        constitution_digest=constitution_digest,
    )


@pytest.fixture
def plan_client() -> Iterator[TestClient]:
    EntranceRecordingLLM.entrances = []
    app.dependency_overrides[get_llm_client] = EntranceRecordingLLM
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "principal,entrance",
    [
        (lambda: _principal("c" * 64), "route"),
        (lambda: None, "complete_compatibility"),
        (lambda: _principal(""), "complete_compatibility"),
    ],
    ids=["authenticated", "anonymous", "no-constitution-binding"],
)
def test_the_plan_model_call_passes_a_gateway_entrance(
    plan_client: TestClient, principal, entrance: str
) -> None:
    app.dependency_overrides[get_optional_principal] = principal
    response = plan_client.post("/api/v1/plan", json={"goal": "do a thing"})
    assert response.status_code == 200, response.text
    assert EntranceRecordingLLM.entrances == [entrance]
