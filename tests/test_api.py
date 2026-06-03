"""FastAPI integration tests using Starlette's TestClient.

Collaborators are overridden via dependency injection so the suite never calls
Ollama, spawns a shell, or touches the real sandbox/ledger.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Iterator, Optional

import pytest
from fastapi.testclient import TestClient

from aios.agents.rollback_engine import RollbackEngine, RollbackError
from aios.api.main import (
    app,
    get_bedrock_client,
    get_executor,
    get_llm_client,
    get_ollama_client,
    get_reflection_agent,
    get_rollback_engine,
    get_semantic_indexer,
)
from aios.core.executor import Executor
from aios.memory.episodic import EpisodicMemory
from aios.security.gateway import RateLimiter


class FakeLLM:
    """Deterministic LLM stand-in for reflect + plan endpoints."""

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        if "planning module" in (system or ""):
            return json.dumps(
                {"steps": [
                    {"step_id": "1", "description": "scaffold project", "confidence": 0.9},
                    {"step_id": "2", "description": "risky migration", "confidence": 0.4},
                ]}
            )
        return json.dumps(
            {
                "error_type": "Timeout",
                "root_cause": "the operation exceeded its time budget",
                "fix_applied": "increased the timeout and retried",
                "lesson_text": "set explicit timeouts on network calls",
                "confidence_delta": -0.1,
            }
        )


class FakeOllama:
    """Deterministic Ollama stand-in for model discovery + agentic chat."""

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b", "nomic-embed-text:latest"]}

    def chat(
        self,
        messages: list,
        *,
        tools: Optional[list] = None,
        model: Optional[str] = None,
    ) -> dict:
        # No tool call: answer immediately with a fenced code block.
        return {
            "role": "assistant",
            "content": "Here is a button:\n```html\n<button>Hi</button>\n```",
        }


class FakeOllamaYellow:
    """Ollama stand-in whose first turn calls a YELLOW (needs-approval) command."""

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(
        self,
        messages: list,
        *,
        tools: Optional[list] = None,
        model: Optional[str] = None,
    ) -> dict:
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "execute_terminal",
                        "arguments": {"command": "pip install flask"},
                    }
                }
            ],
        }


class FakeRunner:
    """Stand-in process runner — records, never spawns."""

    def __call__(self, command, *, cwd, env, timeout_s):
        return f"ran: {command}", "", 0


class RecordingAudit:
    def __call__(self, actor, payload, zone, **kwargs):
        return None


class FakeIndexer:
    """Stand-in L3 writer — records indexed text, never loads an embedder."""

    def __init__(self) -> None:
        self.added: list[str] = []

    def add(self, text: str) -> int:
        self.added.append(text)
        return len(self.added)


def _fake_executor() -> Executor:
    return Executor(runner=FakeRunner(), rate_limiter=RateLimiter(), audit_log=RecordingAudit())


@pytest.fixture()
def client(monkeypatch) -> Iterator[TestClient]:
    # Keep model side-effects out of the test path: stub hybrid recall so a
    # populated on-disk semantic index can't pull the real embedder into a test
    # (it would otherwise load sentence-transformers/torch). Tests that need
    # recall override this in their own body via the same monkeypatch instance.
    monkeypatch.setattr("aios.api.main.hybrid_search", lambda query, top_k=3: [])
    fake_indexer = FakeIndexer()
    app.dependency_overrides[get_llm_client] = FakeLLM
    app.dependency_overrides[get_ollama_client] = FakeOllama
    app.dependency_overrides[get_executor] = _fake_executor
    app.dependency_overrides[get_semantic_indexer] = lambda: fake_indexer
    with TestClient(app) as test_client:
        test_client.fake_indexer = fake_indexer  # exposed for indexing assertions
        yield test_client
    app.dependency_overrides.clear()


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_classify_red_and_yellow(client: TestClient) -> None:
    red = client.post("/api/v1/security/classify", json={"command": "rm -rf /"})
    assert red.status_code == 200
    assert red.json()["zone"] == "RED"

    yellow = client.post("/api/v1/security/classify", json={"command": "pip install flask"})
    assert yellow.json()["zone"] == "YELLOW"


def test_memory_search_returns_list(client: TestClient) -> None:
    response = client.post("/api/v1/memory/search", json={"query": "anything", "top_k": 3})
    assert response.status_code == 200
    assert isinstance(response.json()["results"], list)


def test_audit_verify_responds(client: TestClient) -> None:
    response = client.get("/api/v1/audit/verify")
    assert response.status_code == 200
    assert "valid" in response.json()


def test_reflect_with_injected_fake_llm(client: TestClient) -> None:
    response = client.post(
        "/api/v1/reflect",
        json={"command": "fetch url", "error_output": "timed out", "task_id": "api-test"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error_type"] == "Timeout"
    assert body["mistake_id"] >= 1


def test_models_local_lists_installed(client: TestClient) -> None:
    response = client.get("/api/v1/models/local")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert "llama3.2:3b" in body["models"]


def test_generate_streams_text_code_and_done(client: TestClient) -> None:
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "make a button"}]}],
            "modelId": "ollama.llama3.2:3b",
        },
    )
    assert response.status_code == 200
    body = response.text
    # streamed prose, the extracted code event, and a terminal done frame
    assert "event: text_chunk" in body
    assert "event: code" in body
    assert "<button>Hi</button>" in body
    assert "event: done" in body


def test_generate_without_user_message_emits_error(client: TestClient) -> None:
    response = client.post("/api/generate", json={"messages": []})
    assert response.status_code == 200
    assert "event: error" in response.text


def test_terminal_green_runs_in_sandbox(client: TestClient) -> None:
    response = client.post("/api/terminal", json={"command": "echo hello"})
    assert response.status_code == 200
    body = response.json()
    assert body["isError"] is False
    assert "ran: echo hello" in body["output"]


def test_terminal_red_command_is_blocked(client: TestClient) -> None:
    response = client.post("/api/terminal", json={"command": "rm -rf /"})
    assert response.status_code == 200
    body = response.json()
    assert body["isError"] is True
    assert "BLOCKED" in body["output"]


def test_generate_persists_episodic_turns(client: TestClient) -> None:
    session_id = "test-episodic-persist"
    before = EpisodicMemory().count(session_id)
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "make a button"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session_id,
        },
    )
    assert response.status_code == 200
    assert "event: done" in response.text
    # The user turn and the assistant answer are both recorded.
    assert EpisodicMemory().count(session_id) - before >= 2


def test_generate_recalls_memory_as_step(client: TestClient, monkeypatch) -> None:
    recalled = [SimpleNamespace(text="The project serves the API on port 8000.")]
    monkeypatch.setattr("aios.api.main.hybrid_search", lambda q, top_k=3: recalled)

    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "what port?"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "test-recall-step",
        },
    )
    assert response.status_code == 200
    body = response.text
    assert "query_knowledge" in body          # the recall step is surfaced
    assert "serves the API on port 8000" in body


class FakeReflector:
    """Reflector stand-in that recalls one pending lesson for the session."""

    def recall_pending(self, task_id, limit=5):
        return [{"mistake_id": 5, "error_type": "Timeout", "lesson_text": "set a timeout"}]

    def reflect(self, *a, **k):  # pragma: no cover - not exercised here
        raise AssertionError("reflect should not be called in this test")

    def confirm_lesson(self, mistake_id):  # pragma: no cover
        return None


def test_generate_recalls_session_lessons_as_step(client: TestClient) -> None:
    app.dependency_overrides[get_reflection_agent] = lambda: FakeReflector()
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "carry on"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "test-session-lessons",
        },
    )
    assert response.status_code == 200
    body = response.text
    assert "Recalled 1 past lesson" in body     # the lesson-recall step is surfaced
    assert "event: done" in body


def test_generate_indexes_completed_turn_into_semantic(client: TestClient) -> None:
    client.fake_indexer.added.clear()
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "make a button"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "test-index-turn",
        },
    )
    assert response.status_code == 200
    assert "event: done" in response.text
    assert client.fake_indexer.added, "the completed turn should be indexed into L3"
    entry = client.fake_indexer.added[-1]
    assert "User:" in entry and "Assistant:" in entry


def test_generate_pauses_for_yellow_approval(client: TestClient) -> None:
    # When the agent hits a YELLOW command, the turn pauses and the UI is asked
    # to authorise it (resumable in-chat approval) instead of completing.
    app.dependency_overrides[get_ollama_client] = FakeOllamaYellow
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "install flask"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "test-yellow-approval",
        },
    )
    assert response.status_code == 200
    body = response.text
    assert "event: human_required" in body
    assert "pip install flask" in body          # the command to authorise is surfaced
    assert "Approval required to run: pip install flask" in body  # plain-language prompt
    # The raw classifier reason (which embeds a regex like "\bpip\s+install\b")
    # must never reach the human approval prompt — it belongs in the audit log.
    assert "Caution operation requires approval" not in body
    assert "event: done" not in body            # the paused turn does not complete


class FakeBedrockChat:
    """Bedrock stand-in for the agent loop — answers with a fenced code block."""

    def chat(self, messages, *, tools=None, model=None) -> dict:
        return {"role": "assistant", "content": "Answer from Bedrock.\n```text\ncloud\n```"}


class FakeBedrockModels:
    """Bedrock stand-in exposing model discovery for the picker endpoint."""

    def list_models(self) -> list:
        return [{"id": "amazon.nova-pro-v1:0", "name": "Amazon Nova Pro"}]


def test_models_bedrock_lists_when_configured(client: TestClient) -> None:
    app.dependency_overrides[get_bedrock_client] = lambda: FakeBedrockModels()
    response = client.get("/api/v1/models/bedrock")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["models"][0]["id"] == "amazon.nova-pro-v1:0"


def test_models_bedrock_empty_when_unconfigured(client: TestClient) -> None:
    # No override -> real get_bedrock_client returns None (Bedrock off in tests).
    response = client.get("/api/v1/models/bedrock")
    assert response.status_code == 200
    assert response.json() == {"available": False, "models": []}


def test_generate_routes_cloud_model_to_bedrock(client: TestClient) -> None:
    # A non-ollama (cloud) model id routes to the injected Bedrock client instead
    # of falling through to local Ollama.
    app.dependency_overrides[get_bedrock_client] = lambda: FakeBedrockChat()
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "hello"}]}],
            "modelId": "amazon.nova-pro-v1:0",
            "sessionId": "test-bedrock-route",
        },
    )
    assert response.status_code == 200
    body = response.text
    assert "event: done" in body
    assert "cloud" in body                      # code block from the Bedrock answer
    assert "<button>Hi</button>" not in body    # did NOT fall through to Ollama


def test_generate_runs_approved_yellow_command(client: TestClient) -> None:
    # Re-sending the turn with the command whitelisted runs it via the sandbox
    # (FakeRunner), so the turn now completes instead of pausing.
    app.dependency_overrides[get_ollama_client] = FakeOllamaYellow
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "install flask"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "test-yellow-approved",
            "approvedCommands": ["pip install flask"],
        },
    )
    assert response.status_code == 200
    body = response.text
    assert "event: human_required" not in body
    assert "ran: pip install flask" in body     # executed in the sandbox
    assert "event: done" in body


# --------------------------------------------------------------------------- #
# v1 contract routes — plan / execute / approval / rollback (Slice 1b)
# These wrappers were present but had no direct HTTP-level assertion; the tests
# below drive each route through the TestClient using the same injected fakes.
# --------------------------------------------------------------------------- #
def test_plan_endpoint_partitions_by_confidence(client: TestClient) -> None:
    response = client.post("/api/v1/plan", json={"goal": "build a thing"})
    assert response.status_code == 200
    body = response.json()
    assert body["goal"] == "build a thing"
    assert len(body["steps"]) == 2
    # FakeLLM emits a 0.9 step (approved) and a 0.4 step (escalated, < 0.72).
    assert len(body["approved"]) == 1
    assert len(body["escalate"]) == 1
    assert body["requires_human"] is True


def test_plan_endpoint_rejects_malformed_llm(client: TestClient) -> None:
    class BadLLM:
        def complete(self, prompt, *, system=None):
            return "not json at all"

    app.dependency_overrides[get_llm_client] = BadLLM
    response = client.post("/api/v1/plan", json={"goal": "x"})
    assert response.status_code == 422


def test_execute_endpoint_green_runs_and_red_blocks(client: TestClient) -> None:
    green = client.post("/api/v1/execute", json={"command": "echo hello"})
    assert green.status_code == 200
    gbody = green.json()
    assert gbody["status"] == "OK"
    assert gbody["zone"] == "GREEN"
    assert "ran: echo hello" in gbody["stdout"]

    red = client.post("/api/v1/execute", json={"command": "rm -rf /"})
    rbody = red.json()
    assert rbody["status"] == "BLOCKED"
    assert rbody["zone"] == "RED"


def test_approval_req_approve_runs_yellow(client: TestClient) -> None:
    response = client.post(
        "/api/v1/approval/req",
        json={"command": "pip install flask", "approve": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "approved"
    assert body["executed"] is True
    assert body["result"]["status"] == "OK"


def test_approval_req_reject_does_not_run(client: TestClient) -> None:
    response = client.post(
        "/api/v1/approval/req",
        json={"command": "pip install flask", "approve": False},
    )
    body = response.json()
    assert body["decision"] == "rejected"
    assert body["executed"] is False


def test_approval_req_refuses_red_even_when_approved(client: TestClient) -> None:
    # D1 invariant at the HTTP boundary: one-click approval can never run a RED
    # command — execute_approved refuses it.
    response = client.post(
        "/api/v1/approval/req",
        json={"command": "rm -rf /", "approve": True},
    )
    body = response.json()
    assert body["executed"] is False
    assert body["result"]["status"] == "BLOCKED"
    assert body["result"]["zone"] == "RED"


def test_rollback_endpoint_restores_snapshot(client: TestClient, tmp_path) -> None:
    engine = RollbackEngine(repo_dir=tmp_path)
    work = tmp_path / "work.txt"
    work.write_text("v1", encoding="utf-8")
    snap = engine.create_snapshot("v1 state")
    work.write_text("v2", encoding="utf-8")
    engine.create_snapshot("v2 state")

    app.dependency_overrides[get_rollback_engine] = lambda: engine
    response = client.post("/api/v1/rollback", json={"snapshot_id": snap.sha})
    assert response.status_code == 200
    body = response.json()
    assert body["restored"] is True
    assert work.read_text(encoding="utf-8") == "v1"


def test_rollback_endpoint_maps_error_to_500(client: TestClient) -> None:
    class BoomEngine:
        def rollback(self, sha=None):
            raise RollbackError("boom")

    app.dependency_overrides[get_rollback_engine] = lambda: BoomEngine()
    response = client.post("/api/v1/rollback", json={})
    assert response.status_code == 500
