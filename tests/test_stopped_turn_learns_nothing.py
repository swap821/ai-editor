"""A turn the tool loop stopped is not learned from (2026-10-30).

Found on the operator's daily backend. In 5 of 14 turns the local model
repeated a verify that had already passed, and the agent-loop guard stopped the
turn. Each such turn was still recorded as a verified success, so the skill
library learned the stopped turn's tool sequence ("verify; verify") as a
procedure, and one such arc reached review-ready. Measured on master before
this change, with this file's model: outcome ``verified_success``, a skill
attempt ``[verify, verify]`` credited as a success, and a curriculum match.

Pinned: a turn that ends in a loop error records ``unverified``, credits no
skill attempt and advances no curriculum. The positive control is
``tests/test_api.py::test_generate_records_verifier_backed_development_and_skill_evidence``:
the same verify, once, with the same STRONG runner, IS recorded as a success.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from aios.api.deps import (
    get_curriculum_manager,
    get_development_tracker,
    get_executor,
    get_ollama_client,
    get_skill_memory,
)
from aios.api.main import app
from aios.core.autonomy import UNGOVERNED_FIXTURE
from aios.core.executor import Executor
from aios.security.gateway import RateLimiter
from tests.test_api import (  # noqa: F401 - the client fixture
    RecordingAudit,
    RecordingCurriculum,
    RecordingDevelopment,
    RecordingSkills,
    _cookie_session_id,
    _issue_generate_capability,
    client,
)


class RepeatsAPassingVerify:
    """Asks for the same verify every time, as the local model did."""

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(self, messages, *, tools=None, model=None) -> dict:
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "verify", "arguments": {"command": "pytest -q"}}}
            ],
        }


def test_a_turn_stopped_as_a_loop_learns_nothing(client: TestClient) -> None:  # noqa: F811
    development = RecordingDevelopment()
    skills = RecordingSkills()
    curriculum = RecordingCurriculum()
    app.dependency_overrides[get_ollama_client] = RepeatsAPassingVerify
    # A STRONG pass every time, exactly as the live turns had.
    app.dependency_overrides[get_executor] = lambda: Executor(
        runner=lambda command, *, cwd, env, timeout_s: ("1 passed", "", 0),
        rate_limiter=RateLimiter(),
        audit_log=RecordingAudit(),
        emergency_stop=UNGOVERNED_FIXTURE,
    )
    app.dependency_overrides[get_development_tracker] = lambda: development
    app.dependency_overrides[get_skill_memory] = lambda: skills
    app.dependency_overrides[get_curriculum_manager] = lambda: curriculum
    session_id = _cookie_session_id(client)
    token = _issue_generate_capability(client, "command", {"command": "pytest -q"})

    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "verify the project"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session_id,
            "approvalTokens": [token],
        },
    )

    assert response.status_code == 200
    body = response.text
    assert "agent_loop" in body, "the guard stopped the turn"
    assert "[VERIFY PASS]" in body, "the verifier passed along the way"
    assert development.records[-1][1] == "unverified"
    assert skills.attempts == [], "a stopped turn's tool sequence is not a procedure"
    assert curriculum.matches == []
    assert "event: done" in body, "the stream still ends normally"
