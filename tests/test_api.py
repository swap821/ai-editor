"""FastAPI integration tests using Starlette's TestClient.

Collaborators are overridden via dependency injection so the suite never calls
Ollama, spawns a shell, or touches the real sandbox/ledger.
"""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from typing import Iterator, Optional

import pytest
from fastapi.testclient import TestClient

from aios import config
from aios.agents.rollback_engine import RollbackEngine, RollbackError
from aios.api.main import (
    app,
    get_bedrock_client,
    get_edit_snapshot,
    get_curriculum_manager,
    get_development_tracker,
    get_executor,
    get_llm_client,
    get_ollama_client,
    get_approval_store,
    get_reflection_agent,
    get_rollback_engine,
    get_semantic_indexer,
    get_self_apply_engine,
    get_skill_memory,
    get_memory_consolidator,
)
from aios.security import scope_lock
from aios.core.executor import Executor
from aios.core.self_apply import DEFAULT_VERIFY_COMMAND
from aios.memory.episodic import EpisodicMemory
from aios.memory.facts import FactWriteResult
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
        return {
            "available": True,
            "models": ["llama3.2:3b", "deepseek-r1:8b", "nomic-embed-text:latest"],
        }

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


class CapturingOllama(FakeOllama):
    """Chat fake that exposes the system context received by the live pipeline."""

    def __init__(self) -> None:
        self.calls: list[list] = []

    def chat(
        self,
        messages: list,
        *,
        tools: Optional[list] = None,
        model: Optional[str] = None,
    ) -> dict:
        self.calls.append(messages)
        return super().chat(messages, tools=tools, model=model)


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
    # No hybrid_search stub needed: tests/conftest.py isolates AIOS_DATA_DIR to a
    # fresh temp dir, so the semantic index is empty and hybrid_search short-
    # circuits to [] WITHOUT loading the embedder (sentence-transformers/torch) —
    # see test_data_isolation.py, which enforces that contract. Tests that need
    # recall still override hybrid_search in their own body via `monkeypatch`.
    fake_indexer = FakeIndexer()
    app.dependency_overrides[get_llm_client] = FakeLLM
    app.dependency_overrides[get_ollama_client] = FakeOllama
    app.dependency_overrides[get_executor] = _fake_executor
    app.dependency_overrides[get_semantic_indexer] = lambda: fake_indexer
    get_approval_store().clear()
    with TestClient(app) as test_client:
        test_client.fake_indexer = fake_indexer  # exposed for indexing assertions
        yield test_client
    app.dependency_overrides.clear()


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_workspace_lists_training_ground_text_files(
    client: TestClient, monkeypatch, tmp_path
) -> None:
    """The forge workspace endpoint returns training_ground text files + content,
    strictly confined to training_ground, skipping caches/binaries."""
    tg = tmp_path / "training_ground"
    tg.mkdir()
    (tg / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    (tg / "note.txt").write_text("a note", encoding="utf-8")
    (tg / "skip.bin").write_bytes(b"\x00\x01")  # non-text ext -> skipped
    cache = tg / "__pycache__"
    cache.mkdir()
    (cache / "x.pyc").write_text("cached", encoding="utf-8")
    monkeypatch.setattr("aios.config.PROJECT_ROOT", tmp_path)

    response = client.get("/api/v1/development/workspace")
    assert response.status_code == 200
    data = response.json()
    assert data["root"] == "training_ground"
    by_path = {f["path"]: f["content"] for f in data["files"]}
    assert by_path["hello.py"] == "print('hi')\n"
    assert "note.txt" in by_path
    assert "skip.bin" not in by_path  # binary ext skipped
    assert not any("__pycache__" in p for p in by_path)  # caches skipped
    # confined to training_ground: no traversal, no absolute paths
    assert all(".." not in p and not p.startswith("/") for p in by_path)


def test_configured_api_token_protects_api_routes(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "API_TOKEN", "release-test-token")

    denied = client.get("/api/v1/models/local")
    allowed = client.get(
        "/api/v1/models/local",
        headers={"Authorization": "Bearer release-test-token"},
    )

    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert client.get("/health").status_code == 200


def test_non_loopback_api_host_requires_token(monkeypatch) -> None:
    monkeypatch.setattr(config, "API_HOST", "0.0.0.0")
    monkeypatch.setattr(config, "API_TOKEN", "")

    with pytest.raises(RuntimeError, match="AIOS_API_TOKEN is required"):
        with TestClient(app):
            pass


def test_non_loopback_api_host_requires_strong_token(monkeypatch) -> None:
    monkeypatch.setattr(config, "API_HOST", "0.0.0.0")
    monkeypatch.setattr(config, "API_TOKEN", "too-short")

    with pytest.raises(RuntimeError, match="at least 32 characters"):
        with TestClient(app):
            pass


def test_unauthenticated_remote_client_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(config, "API_HOST", "127.0.0.1")
    monkeypatch.setattr(config, "API_TOKEN", "")

    with TestClient(app, client=("203.0.113.10", 50000)) as remote:
        response = remote.post("/api/v1/security/classify", json={"command": "echo hi"})

    assert response.status_code == 403


def test_unauthenticated_remote_client_cannot_read_api_schema(monkeypatch) -> None:
    monkeypatch.setattr(config, "API_HOST", "127.0.0.1")
    monkeypatch.setattr(config, "API_TOKEN", "")

    with TestClient(app, client=("203.0.113.10", 50000)) as remote:
        assert remote.get("/openapi.json").status_code == 403
        assert remote.get("/docs").status_code == 403
        assert remote.get("/health").status_code == 200


def test_authenticated_deployment_allows_cors_preflight(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(config, "API_TOKEN", "release-test-token")

    response = client.options(
        "/api/v1/security/classify",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200


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
    assert "deepseek-r1:8b" not in body["models"]
    assert "nomic-embed-text:latest" not in body["models"]


def test_models_auto_picks_best_local(client: TestClient) -> None:
    # The agent's auto-pick endpoint excludes the embedder and returns the best
    # installed chat model (here llama3.2:3b is the only one) plus a human reason —
    # so the UI can show "Auto · <model>" and the user never has to choose.
    response = client.get("/api/v1/models/auto")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["model"] == "llama3.2:3b"
    assert body["reason"]


def test_select_chat_client_auto_prefers_coder_and_falls_back() -> None:
    # The agent's selection is the source of truth, not the user: 'auto' picks the
    # best local model and runs it on the local client; with nothing usable it
    # fails soft to the configured default (never crashes a turn).
    from aios import config
    from aios.api.main import _select_chat_client

    class _O:
        def __init__(self, models: list) -> None:
            self._m = models

        def list_models(self) -> dict:
            return {"available": True, "models": self._m}

    ollama = _O(["llama3.1:8b", "qwen2.5-coder:3b", "nomic-embed-text:latest"])
    chat_client, model = _select_chat_client("auto", ollama, None)
    assert chat_client is ollama and model == "qwen2.5-coder:3b"

    empty = _O(["nomic-embed-text:latest"])
    fb_client, fb_model = _select_chat_client("auto", empty, None)
    assert fb_client is empty and fb_model == config.LLM_MODEL

    # An omitted model id preserves the local-first contract even when Bedrock
    # happens to be configured; only an explicit cloud id changes providers.
    default_client, default_model = _select_chat_client(None, ollama, object())
    assert default_client is ollama and default_model == config.LLM_MODEL


def test_select_chat_client_routes_by_task() -> None:
    # The agent routes by PURPOSE: a coder for code, a strong general for chat,
    # and — because the loop needs tools — the best TOOL-CAPABLE model for
    # reasoning (the non-tool reasoner is skipped, never breaking the loop).
    from aios.api.main import _select_chat_client

    class _O:
        def __init__(self, models: list) -> None:
            self._m = models

        def list_models(self) -> dict:
            return {"available": True, "models": self._m}

    o = _O(["qwen2.5-coder:7b", "qwen2.5:7b", "deepseek-r1:8b", "llama3.2:3b"])
    assert _select_chat_client("auto", o, None, task="coding")[1] == "qwen2.5-coder:7b"
    assert _select_chat_client("auto", o, None, task="general")[1] == "qwen2.5:7b"
    assert _select_chat_client("auto", o, None, task="reasoning")[1] == "qwen2.5:7b"
    assert _select_chat_client("auto", o, None, task="fast")[1] == "llama3.2:3b"


def test_models_auto_returns_by_task_map(client: TestClient) -> None:
    # The discovery endpoint surfaces how the agent routes by purpose.
    response = client.get("/api/v1/models/auto?task=reasoning")
    assert response.status_code == 200
    body = response.json()
    assert body["task"] == "reasoning"
    assert set(body["by_task"]) == {"coding", "reasoning", "general", "fast"}
    # The fake's deepseek reasoner cannot accept tool specs, so every actual
    # agent-loop purpose resolves to the sole tool-capable model.
    assert body["model"] == "llama3.2:3b"


def test_generate_refuses_local_model_without_tool_protocol(client: TestClient) -> None:
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "hello"}]}],
            "modelId": "ollama.deepseek-r1:8b",
        },
    )
    assert response.status_code == 422
    assert "tool protocol" in response.json()["detail"]


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


def test_generate_stream_emits_active_brain_route_event(client: TestClient) -> None:
    # The turn announces which provider/model served it (the UI 'active brain' badge).
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "hello"}]}],
            "modelId": "ollama.llama3.2:3b",
        },
    )
    assert response.status_code == 200
    body = response.text
    assert "event: route" in body
    assert '"provider": "ollama"' in body
    assert '"privacy": "local"' in body
    assert '"model": "llama3.2:3b"' in body


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


def test_terminal_yellow_issues_capability_and_runs_after_approval(client: TestClient) -> None:
    pending = client.post(
        "/api/terminal",
        json={"command": "pip install flask", "sessionId": "terminal-approval"},
    )
    assert pending.status_code == 200
    body = pending.json()
    assert body["requiresApproval"] is True
    assert body["approvalToken"]

    approved = client.post(
        "/api/v1/approval/req",
        json={
            "approvalToken": body["approvalToken"],
            "sessionId": "terminal-approval",
            "approve": True,
        },
    )
    assert approved.status_code == 200
    assert approved.json()["result"]["status"] == "OK"


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


def test_generate_injects_validated_advisory_understanding_frame(client: TestClient) -> None:
    chat = CapturingOllama()
    app.dependency_overrides[get_ollama_client] = lambda: chat

    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "start implementation"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "test-understanding-frame",
        },
    )

    assert response.status_code == 200
    assert "event: alignment" in response.text
    system = chat.calls[0][0]["content"]
    assert "UNVERIFIED ADVISORY UNDERSTANDING FRAME" in system
    assert "never authorization" in system
    assert '"intent": "execute"' in system
    assert '"ambiguity_action": "proceed"' in system


def test_generate_asks_before_agent_tools_when_policy_finds_blocking_ambiguity(
    client: TestClient,
) -> None:
    chat = CapturingOllama()
    app.dependency_overrides[get_ollama_client] = lambda: chat

    response = client.post(
        "/api/generate",
        json={
            "messages": [
                {"role": "user", "content": [{"text": "Do not assume; ask me first"}]}
            ],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "test-clarify-first",
        },
    )

    assert response.status_code == 200
    assert '"ambiguity_action": "ask"' in response.text
    assert "What should I clarify before proceeding?" in response.text
    assert "event: done" in response.text
    assert chat.calls == []


def test_generate_states_unverified_assumptions_then_runs_normal_agent(
    client: TestClient,
) -> None:
    class AssumptionLLM:
        def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
            return json.dumps(
                {
                    "intent": "execute",
                    "assumptions": ["Use the existing API shape"],
                    "unknowns": ["Preferred response length"],
                    "confidence": 0.72,
                }
            )

    chat = CapturingOllama()
    app.dependency_overrides[get_llm_client] = AssumptionLLM
    app.dependency_overrides[get_ollama_client] = lambda: chat

    response = client.post(
        "/api/generate",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": "Implement the endpoint using your best judgment"}],
                }
            ],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "test-state-assumptions",
        },
    )

    assert response.status_code == 200
    assert '"ambiguity_action": "state_assumptions"' in response.text
    assert "Unverified assumptions before proceeding: Use the existing API shape" in response.text
    assert "event: code" in response.text
    assert len(chat.calls) == 1


def test_conversation_session_restores_alignment_and_recent_dialogue(client: TestClient) -> None:
    session_id = "test-conversation-restore"
    generated = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "start implementation"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session_id,
        },
    )
    assert generated.status_code == 200

    restored = client.post(
        "/api/v1/conversation/session",
        json={"sessionId": session_id},
    )

    assert restored.status_code == 200
    body = restored.json()
    assert body["alignment"]["intent"] == "execute"
    assert body["alignment"]["communication"]["ambiguity_action"] == "proceed"
    assert [message["role"] for message in body["messages"]] == ["user", "assistant"]
    assert body["messages"][0]["content"][0]["text"] == "start implementation"


def test_user_correction_persists_reapplies_and_can_be_cleared(client: TestClient) -> None:
    session_id = "test-conversation-correction"
    generated = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "plan the API"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session_id,
        },
    )
    assert generated.status_code == 200

    corrected = client.post(
        "/api/v1/conversation/correction",
        json={
            "sessionId": session_id,
            "corrections": {
                "goal": "Review only the public API",
                "intent": "review",
                "communication_mode": "collaborative",
                "unknowns": [],
            },
        },
    )
    assert corrected.status_code == 200
    corrected_body = corrected.json()
    assert corrected_body["alignment"]["goal"] == "Review only the public API"
    assert corrected_body["alignment"]["correction"]["active"] is True
    assert corrected_body["activeCorrection"]["fields"] == [
        "communication_mode",
        "goal",
        "intent",
        "unknowns",
    ]
    assert corrected_body["correctionHistory"][0]["status"] == "active"

    chat = CapturingOllama()
    app.dependency_overrides[get_ollama_client] = lambda: chat
    continued = client.post(
        "/api/generate",
        json={
            "messages": [
                {"role": "user", "content": [{"text": "plan the API"}]},
                {"role": "assistant", "content": [{"text": "A plan"}]},
                {"role": "user", "content": [{"text": "continue"}]},
            ],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session_id,
        },
    )
    assert continued.status_code == 200
    assert '"goal": "Review only the public API"' in continued.text
    assert "USER-AUTHORED INTERPRETATION CORRECTIONS" in chat.calls[0][0]["content"]

    cleared = client.post(
        "/api/v1/conversation/correction/clear",
        json={"sessionId": session_id},
    )
    assert cleared.status_code == 200
    cleared_body = cleared.json()
    assert cleared_body["alignment"]["goal"] != "Review only the public API"
    assert cleared_body["alignment"]["correction"]["active"] is False
    assert cleared_body["activeCorrection"] is None
    assert cleared_body["correctionHistory"][0]["status"] == "cleared"


def test_alignment_evaluation_records_feedback_and_correction_evidence(
    client: TestClient,
) -> None:
    before = client.get("/api/v1/alignment/evaluation").json()["total_turns"]
    session_id = "test-alignment-evaluation"
    generated = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "plan the API"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session_id,
        },
    )
    assert generated.status_code == 200
    alignment_event = next(
        line[6:]
        for line in generated.text.splitlines()
        if line.startswith("data: ") and '"evaluation"' in line
    )
    observation_id = json.loads(alignment_event)["evaluation"]["observation_id"]

    feedback = client.post(
        "/api/v1/alignment/feedback",
        json={
            "sessionId": session_id,
            "observationId": observation_id,
            "outcome": "misaligned",
            "issues": ["wrong_goal"],
        },
    )
    corrected = client.post(
        "/api/v1/conversation/correction",
        json={"sessionId": session_id, "corrections": {"goal": "Review the API"}},
    )
    summary = client.get("/api/v1/alignment/evaluation")

    assert feedback.status_code == 200
    assert feedback.json()["automaticPolicyUpdates"] is False
    assert corrected.status_code == 200
    assert corrected.json()["alignment"]["evaluation"]["observation_id"] == observation_id
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_turns"] == before + 1
    assert body["recent"][0]["corrected"] is True
    assert body["recent"][0]["human_outcome"] == "misaligned"
    assert body["recent"][0]["issues"] == ["wrong_goal"]

    wrong_session = client.post(
        "/api/v1/alignment/feedback",
        json={
            "sessionId": "another-session",
            "observationId": observation_id,
            "outcome": "aligned",
        },
    )
    assert wrong_session.status_code == 404


def test_alignment_feedback_requires_observation_and_supported_outcome(
    client: TestClient,
) -> None:
    missing = client.post(
        "/api/v1/alignment/feedback",
        json={"sessionId": "missing-observation", "outcome": "aligned"},
    )
    unsupported = client.post(
        "/api/v1/alignment/feedback",
        json={"sessionId": "missing-observation", "outcome": "approved"},
    )

    assert missing.status_code == 404
    assert unsupported.status_code == 422


def test_alignment_interpreter_flag_off_skips_frame_and_observation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "INTERPRET_ALIGNMENT", False)
    before = client.get("/api/v1/alignment/evaluation").json()["total_turns"]

    generated = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "plan the API"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "alignment-flag-off",
        },
    )

    assert generated.status_code == 200
    assert "event: alignment" not in generated.text
    assert "event: done" in generated.text
    summary = client.get("/api/v1/alignment/evaluation")
    assert summary.status_code == 200
    assert summary.json()["total_turns"] == before


def test_conversation_correction_rejects_authority_and_requires_current_frame(
    client: TestClient,
) -> None:
    missing = client.post(
        "/api/v1/conversation/correction",
        json={"sessionId": "missing-frame", "corrections": {"goal": "anything"}},
    )
    assert missing.status_code == 404

    client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "review the API"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "reject-authority-correction",
        },
    )
    rejected = client.post(
        "/api/v1/conversation/correction",
        json={
            "sessionId": "reject-authority-correction",
            "corrections": {"approval": "granted"},
        },
    )

    assert rejected.status_code == 422
    assert "unsupported correction fields" in rejected.json()["detail"]


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


def test_generate_redacts_secrets_before_memory_persistence(client: TestClient) -> None:
    session_id = "test-secret-redaction"
    secret = "sk-" + "a" * 40
    client.fake_indexer.added.clear()

    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": f"explain {secret}"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session_id,
        },
    )

    assert response.status_code == 200
    assert secret not in client.fake_indexer.added[-1]
    assert "REDACTED" in client.fake_indexer.added[-1]
    assert all(secret not in row["content"] for row in EpisodicMemory().recent(session_id))


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
    assert "approvalToken" in body
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
    assert body["configured"] is True
    assert body["available"] is True
    assert body["models"][0]["id"] == "amazon.nova-pro-v1:0"


def test_apply_endpoint_refuses_red_frozen_core(client: TestClient) -> None:
    # T4 capstone (full stack): the apply endpoint REFUSES a proposal whose target is
    # the frozen security core (aios/security/*) — applying it is RED/T4, blocked — and
    # the real frozen file is never touched (refused at the zone gate, before any write).
    import hashlib

    from aios.memory.db import get_connection, init_memory_db

    target = "aios/security/gateway.py"
    gateway = config.PROJECT_ROOT / target
    before = hashlib.sha256(gateway.read_bytes()).hexdigest()

    diff = (
        "--- a/aios/security/gateway.py\n"
        "+++ b/aios/security/gateway.py\n"
        "@@ -1 +1 @@\n-x\n+y\n"
    )
    init_memory_db()
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO self_analysis_report "
            "(target_path, finding_type, evidence, proposed_diff, proposed_zone, proposed_by, status) "
            "VALUES (?, 'smell', 'frozen core', ?, 'RED', 'self_analysis_agent', 'proposed')",
            (target, diff),
        )
        pid = int(cur.lastrowid)

    resp = client.post(
        f"/api/v1/self-analysis/proposals/{pid}/apply", json={"approvedBy": "operator"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "refused"
    assert "RED" in body["reason"]

    # The frozen-core file is byte-identical, and the row is left 'proposed'.
    assert hashlib.sha256(gateway.read_bytes()).hexdigest() == before
    with get_connection() as conn:
        row = conn.execute(
            "SELECT status FROM self_analysis_report WHERE id = ?", (pid,)
        ).fetchone()
    assert row["status"] == "proposed"


def test_models_bedrock_empty_when_unconfigured(client: TestClient) -> None:
    # Force Bedrock OFF (independent of the dev .env, which may have it enabled) so
    # this pins the unconfigured path hermetically.
    app.dependency_overrides[get_bedrock_client] = lambda: None
    response = client.get("/api/v1/models/bedrock")
    assert response.status_code == 200
    assert response.json() == {"configured": False, "available": False, "models": []}


def test_generate_refuses_explicit_cloud_model_when_bedrock_unconfigured(
    client: TestClient,
) -> None:
    app.dependency_overrides[get_bedrock_client] = lambda: None  # force unconfigured
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "hello"}]}],
            "modelId": "amazon.nova-pro-v1:0",
        },
    )
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


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
    token = get_approval_store().issue(
        "command", {"command": "pip install flask"}, "test-yellow-approved"
    )
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "install flask"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "test-yellow-approved",
            "approvalTokens": [token],
        },
    )
    assert response.status_code == 200
    body = response.text
    assert "event: human_required" not in body
    assert "ran: pip install flask" in body     # executed in the sandbox
    assert "event: done" in body


def test_generate_rejects_client_authored_approval_payload(client: TestClient) -> None:
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "install flask"}]}],
            "sessionId": "raw-approval",
            "approvedCommands": ["pip install flask"],
        },
    )
    assert response.status_code == 400
    assert "raw approved payloads are not accepted" in response.json()["detail"]


def test_generate_rejects_replayed_or_cross_session_token(client: TestClient) -> None:
    store = get_approval_store()
    cross = store.issue("command", {"command": "pip install flask"}, "session-a")
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "install flask"}]}],
            "sessionId": "session-b",
            "approvalTokens": [cross],
        },
    )
    assert response.status_code == 400

    replay = store.issue("command", {"command": "pip install flask"}, "session-a")
    payload = {
        "messages": [{"role": "user", "content": [{"text": "install flask"}]}],
        "sessionId": "session-a",
        "approvalTokens": [replay],
    }
    assert client.post("/api/generate", json=payload).status_code == 200
    assert client.post("/api/generate", json=payload).status_code == 400


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


def test_execute_issues_capability_then_approval_runs_yellow(client: TestClient) -> None:
    escalated = client.post(
        "/api/v1/execute",
        json={"command": "pip install flask", "sessionId": "approval-test"},
    )
    assert escalated.status_code == 200
    pending = escalated.json()
    assert pending["status"] == "REQUIRE_APPROVAL"
    assert pending["sessionId"] == "approval-test"
    assert pending["approvalToken"]

    response = client.post(
        "/api/v1/approval/req",
        json={
            "approvalToken": pending["approvalToken"],
            "sessionId": "approval-test",
            "approve": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "approved"
    assert body["executed"] is True
    assert body["result"]["status"] == "OK"


def test_execute_yellow_requires_session_for_approval_capability(client: TestClient) -> None:
    response = client.post("/api/v1/execute", json={"command": "pip install flask"})
    assert response.status_code == 400
    assert "sessionId is required" in response.json()["detail"]


def test_execute_over_rate_limit_still_issues_fresh_human_capability(
    client: TestClient,
) -> None:
    session_id = "rate-limit-reauthorisation"
    stable_executor = _fake_executor()
    app.dependency_overrides[get_executor] = lambda: stable_executor
    responses = [
        client.post(
            "/api/v1/execute",
            json={"command": "pip install flask", "sessionId": session_id},
        ).json()
        for _ in range(config.MAX_RED_ACTIONS_PER_SESSION + 1)
    ]

    assert all(body["status"] == "REQUIRE_APPROVAL" for body in responses)
    assert all(body["approvalToken"] for body in responses)
    assert "re-authorisation required" in responses[-1]["reason"]


def test_approval_req_reject_does_not_run(client: TestClient) -> None:
    token = get_approval_store().issue("command", {"command": "pip install flask"}, "approval-test")
    response = client.post(
        "/api/v1/approval/req",
        json={"approvalToken": token, "sessionId": "approval-test", "approve": False},
    )
    body = response.json()
    assert body["decision"] == "rejected"
    assert body["executed"] is False


def test_approval_req_reject_consumes_non_command_capability(client: TestClient) -> None:
    token = get_approval_store().issue(
        "edit",
        {"filepath": "x.py", "old_string": "a", "new_string": "b"},
        "approval-test",
    )
    response = client.post(
        "/api/v1/approval/req",
        json={"approvalToken": token, "sessionId": "approval-test", "approve": False},
    )
    assert response.status_code == 200
    assert response.json()["actionType"] == "edit"
    replay = client.post(
        "/api/v1/approval/req",
        json={"approvalToken": token, "sessionId": "approval-test", "approve": False},
    )
    assert replay.status_code == 400


def test_approval_req_refuses_red_even_when_approved(client: TestClient) -> None:
    # D1 invariant at the HTTP boundary: one-click approval can never run a RED
    # command — execute_approved refuses it.
    token = get_approval_store().issue("command", {"command": "rm -rf /"}, "approval-test")
    response = client.post(
        "/api/v1/approval/req",
        json={"approvalToken": token, "sessionId": "approval-test", "approve": True},
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


def test_self_apply_verifier_runs_fixed_suite_from_project_root(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_run(args, **kwargs):
        calls.append({"args": args, **kwargs})
        return SimpleNamespace(stdout="1 passed", stderr="", returncode=0)

    monkeypatch.setattr("aios.api.main._bounded_run", fake_run)
    engine = get_self_apply_engine(_fake_executor())

    result = engine.verifier.verify(DEFAULT_VERIFY_COMMAND, approved=True)

    assert result.passed is True
    assert calls[0]["args"] == [sys.executable, "-m", "pytest", "tests/", "-q"]
    assert calls[0]["cwd"] == str(config.PROJECT_ROOT)
    assert "shell" not in calls[0]


def test_self_apply_verifier_refuses_any_other_runner_command(monkeypatch) -> None:
    monkeypatch.setattr(
        "aios.api.main._bounded_run",
        lambda *args, **kwargs: pytest.fail("unexpected subprocess"),
    )
    engine = get_self_apply_engine(_fake_executor())

    result = engine.verifier.verify("echo hello")

    assert result.passed is False
    assert result.status == "ERROR"
    assert "fixed project test command" in result.summary


# --------------------------------------------------------------------------- #
# /api/generate — file-edit diff approval + apply (Slice 4a)
# --------------------------------------------------------------------------- #
class FakeOllamaEdit:
    """Ollama stand-in: proposes a file edit on turn 1, then answers on turn 2."""

    def __init__(self) -> None:
        self.calls = 0

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(self, messages, *, tools=None, model=None) -> dict:
        self.calls += 1
        if self.calls == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "edit_file", "arguments": {
                        "filepath": "note.txt", "old_string": "world", "new_string": "there",
                    }}}
                ],
            }
        return {"role": "assistant", "content": "Applied the edit."}


def test_generate_pauses_with_edit_diff(client: TestClient, tmp_path, monkeypatch) -> None:
    (tmp_path / "note.txt").write_text("hello world\n", encoding="utf-8")
    # edit_file resolves under read_root (= config.PROJECT_ROOT); point it at the sandbox
    # so the bare "note.txt" the model edits resolves in scope.
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    original = scope_lock.get_scope_roots()
    scope_lock.set_scope_roots([tmp_path])
    app.dependency_overrides[get_ollama_client] = FakeOllamaEdit
    try:
        response = client.post("/api/generate", json={
            "messages": [{"role": "user", "content": [{"text": "edit the note"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "test-edit-pause",
        })
        assert response.status_code == 200
        body = response.text
        assert "event: human_required" in body
        assert "-hello world" in body and "+hello there" in body   # the diff is surfaced
        assert "event: done" not in body                            # paused, not completed
        assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "hello world\n"  # unwritten
    finally:
        scope_lock.set_scope_roots(list(original))


def test_generate_applies_approved_edit_with_snapshot(client: TestClient, tmp_path, monkeypatch) -> None:
    (tmp_path / "note.txt").write_text("hello world\n", encoding="utf-8")
    snaps: list[str] = []
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    original = scope_lock.get_scope_roots()
    scope_lock.set_scope_roots([tmp_path])
    app.dependency_overrides[get_ollama_client] = FakeOllamaEdit
    app.dependency_overrides[get_edit_snapshot] = lambda: (lambda message="": snaps.append(message))
    try:
        token = get_approval_store().issue(
            "edit",
            {"filepath": "note.txt", "old_string": "world", "new_string": "there"},
            "test-edit-apply",
        )
        response = client.post("/api/generate", json={
            "messages": [{"role": "user", "content": [{"text": "edit the note"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "test-edit-apply",
            "approvalTokens": [token],
        })
        assert response.status_code == 200
        body = response.text
        assert "event: human_required" not in body                  # authorised -> no pause
        assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "hello there\n"  # applied
        assert snaps, "a pre-edit snapshot must be taken before the write"
        assert "event: done" in body
    finally:
        scope_lock.set_scope_roots(list(original))


# --------------------------------------------------------------------------- #
# Brain Growth Loop v1 — evidence-backed live integration + API surfaces
# --------------------------------------------------------------------------- #
class FakeOllamaVerify:
    def __init__(self) -> None:
        self.calls = 0

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(self, messages, *, tools=None, model=None) -> dict:
        self.calls += 1
        if self.calls == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "verify", "arguments": {"command": "pytest -q"}}}
                ],
            }
        return {"role": "assistant", "content": "Verified."}


class RecordingDevelopment:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict]] = []

    def record(self, task_text, outcome, **kwargs):
        self.records.append((task_text, outcome, kwargs))
        return len(self.records)

    def summary(self):
        return {"tasks": len(self.records)}


class RecordingSkills:
    def __init__(self) -> None:
        self.attempts: list[tuple[str, list[str], bool]] = []

    def relevant_verified(self, query, limit=3):
        return []

    def record_attempt(self, goal, steps, *, success):
        self.attempts.append((goal, steps, success))
        return 1

    def list(self, *, status=None):
        return [{"status": status or "verified"}]


class RecordingCurriculum:
    def __init__(self) -> None:
        self.matches: list[tuple[str, bool, str]] = []
        self.tasks: list[dict] = []

    def record_matching(self, prompt, *, passed, evidence):
        self.matches.append((prompt, passed, evidence))
        return [1]

    def add_task(self, skill_name, level, prompt, *, held_out=False):
        self.tasks.append(
            {"skill_name": skill_name, "level": level, "prompt": prompt, "held_out": held_out}
        )
        return len(self.tasks)

    def list(self, skill_name=None):
        return self.tasks


class RecordingConsolidator:
    def run(self):
        return {"verified_lessons_consolidated": 2, "active_facts_consolidated": 1}

    def consolidate_lesson(self, mistake_id):
        return mistake_id

    def promote_fact(self, subject, predicate, obj, *, approved_by):
        return FactWriteResult(True, 7, "committed")

    def reconcile_fact(self, subject, predicate, obj, *, approved_by):
        return FactWriteResult(True, 8, "reconciled")


def test_generate_records_verifier_backed_development_and_skill_evidence(
    client: TestClient,
) -> None:
    development = RecordingDevelopment()
    skills = RecordingSkills()
    curriculum = RecordingCurriculum()
    app.dependency_overrides[get_ollama_client] = FakeOllamaVerify
    app.dependency_overrides[get_development_tracker] = lambda: development
    app.dependency_overrides[get_skill_memory] = lambda: skills
    app.dependency_overrides[get_curriculum_manager] = lambda: curriculum
    token = get_approval_store().issue(
        "command", {"command": "pytest -q"}, "growth-verification"
    )

    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "verify the project"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "growth-verification",
            "approvalTokens": [token],
        },
    )

    assert response.status_code == 200
    assert "[VERIFY PASS]" in response.text
    assert development.records[-1][1] == "verified_success"
    assert skills.attempts[-1][2] is True
    assert curriculum.matches[-1][1] is True


class FakeOllamaVerifySequence:
    """Calls verify once per configured command, then answers."""

    commands: tuple[str, ...] = ("pytest -q", "pytest -q")

    def __init__(self) -> None:
        self.calls = 0

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(self, messages, *, tools=None, model=None) -> dict:
        self.calls += 1
        if self.calls <= len(self.commands):
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "verify",
                            "arguments": {"command": self.commands[self.calls - 1]},
                        }
                    }
                ],
            }
        return {"role": "assistant", "content": "Verification rounds complete."}


class FlakyThenGreenRunner:
    """Fails the first spawned command, passes every later one."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, command, *, cwd, env, timeout_s):
        self.calls += 1
        if self.calls == 1:
            return "", "1 failed", 1
        return "1 passed", "", 0


class GreenThenFlakyRunner:
    """Passes the first spawned command, fails every later one."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, command, *, cwd, env, timeout_s):
        self.calls += 1
        if self.calls == 1:
            return "1 passed", "", 0
        return "", "1 failed", 1


class BrokenFileRunner:
    """Fails any command mentioning 'broken'; passes everything else."""

    def __call__(self, command, *, cwd, env, timeout_s):
        if "broken" in command:
            return "", "1 failed", 1
        return "1 passed", "", 0


def test_generate_self_corrected_turn_counts_as_verified_success(
    client: TestClient,
) -> None:
    # Per-target last verdict: a turn that fails verification, self-corrects,
    # and re-verifies the SAME target green is a verified_success —
    # fail-dominant classification would make every task that needs the
    # verify->fix loop unmasterable.
    development = RecordingDevelopment()
    skills = RecordingSkills()
    curriculum = RecordingCurriculum()
    app.dependency_overrides[get_ollama_client] = FakeOllamaVerifySequence
    app.dependency_overrides[get_executor] = lambda: Executor(
        runner=FlakyThenGreenRunner(), rate_limiter=RateLimiter(), audit_log=RecordingAudit()
    )
    app.dependency_overrides[get_development_tracker] = lambda: development
    app.dependency_overrides[get_skill_memory] = lambda: skills
    app.dependency_overrides[get_curriculum_manager] = lambda: curriculum
    session = "growth-self-correction"
    tokens = [
        get_approval_store().issue("command", {"command": "pytest -q"}, session),
    ]

    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "verify the project"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session,
            "approvalTokens": tokens,
        },
    )

    assert response.status_code == 200
    assert "[VERIFY FAIL]" in response.text and "[VERIFY PASS]" in response.text
    assert development.records[-1][1] == "verified_success"
    assert skills.attempts[-1][2] is True
    assert curriculum.matches[-1][1] is True


class ReuseRecordingSkills:
    """Recalls two verified trails; records direct attempts and reuse credit."""

    def __init__(self) -> None:
        self.attempts: list[tuple[str, list[str], bool]] = []
        self.reuse_calls: list[tuple[list[int], bool]] = []

    def relevant_verified(self, query, limit=3):
        return [
            {
                "skill_id": 1,
                "goal_pattern": "verify the project",
                "steps": ["verify: pytest -q"],
                "success_rate": 1.0,
                "strength": 1.0,
                "relevance": 1.0,
            },
            {
                "skill_id": 2,
                "goal_pattern": "verify the project thoroughly",
                "steps": ["read_file: a", "verify: pytest -q"],
                "success_rate": 1.0,
                "strength": 1.0,
                "relevance": 0.9,
            },
        ]

    def record_attempt(self, goal, steps, *, success):
        self.attempts.append((goal, steps, success))
        return 1  # same id as the first recalled trail: the re-walked arc

    def record_reuse(self, skill_ids, *, success):
        self.reuse_calls.append((list(skill_ids), success))
        return list(skill_ids)

    def list(self, *, status=None):
        return []


def test_record_outcome_threads_reuse_credit_excluding_direct_trail(
    client: TestClient,
) -> None:
    skills = ReuseRecordingSkills()
    app.dependency_overrides[get_ollama_client] = FakeOllamaVerify
    app.dependency_overrides[get_skill_memory] = lambda: skills
    token = get_approval_store().issue(
        "command", {"command": "pytest -q"}, "reuse-threading"
    )

    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "verify the project"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "reuse-threading",
            "approvalTokens": [token],
        },
    )

    assert response.status_code == 200
    # The walked trail (direct_id == 1) got direct credit; only the OTHER
    # recalled trail receives a reuse tick — no double-crediting.
    assert len(skills.attempts) == 1 and skills.attempts[0][2] is True
    assert skills.reuse_calls == [([2], True)]

    # An unverified turn (no verify evidence) must credit nothing.
    app.dependency_overrides[get_ollama_client] = FakeOllama
    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "verify the project"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "reuse-threading-2",
        },
    )
    assert response.status_code == 200
    assert len(skills.attempts) == 1
    assert skills.reuse_calls == [([2], True)]


def test_generate_turn_ending_in_failure_stays_verified_failure(
    client: TestClient,
) -> None:
    # The mirror case: the SAME target passing first and failing last is a
    # verified_failure — the final verdict per target wins in both directions.
    development = RecordingDevelopment()
    app.dependency_overrides[get_ollama_client] = FakeOllamaVerifySequence
    app.dependency_overrides[get_executor] = lambda: Executor(
        runner=GreenThenFlakyRunner(), rate_limiter=RateLimiter(), audit_log=RecordingAudit()
    )
    app.dependency_overrides[get_development_tracker] = lambda: development
    session = "growth-regression"
    tokens = [
        get_approval_store().issue("command", {"command": "pytest -q"}, session),
    ]

    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "verify the project"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session,
            "approvalTokens": tokens,
        },
    )

    assert response.status_code == 200
    assert development.records[-1][1] == "verified_failure"


def test_final_pass_on_one_target_cannot_mask_anothers_failure(
    client: TestClient,
) -> None:
    # PASS(test_ok.py) -> FAIL(test_broken.py) -> PASS(test_ok.py): the LAST
    # evidence in the turn is green, but test_broken.py was never resolved —
    # the turn must classify verified_failure (per-target, not global-last).
    development = RecordingDevelopment()

    class FakeOllamaThreeVerifies(FakeOllamaVerifySequence):
        commands = (
            "pytest test_ok.py -q",
            "pytest test_broken.py -q",
            "pytest test_ok.py -q",
        )

    app.dependency_overrides[get_ollama_client] = FakeOllamaThreeVerifies
    app.dependency_overrides[get_executor] = lambda: Executor(
        runner=BrokenFileRunner(), rate_limiter=RateLimiter(), audit_log=RecordingAudit()
    )
    app.dependency_overrides[get_development_tracker] = lambda: development
    session = "growth-cross-target"
    tokens = [
        get_approval_store().issue("command", {"command": "pytest test_ok.py -q"}, session),
        get_approval_store().issue("command", {"command": "pytest test_broken.py -q"}, session),
    ]

    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "verify the project"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session,
            "approvalTokens": tokens,
        },
    )

    assert response.status_code == 200
    assert response.text.count("[VERIFY PASS]") >= 2
    assert "[VERIFY FAIL]" in response.text
    assert development.records[-1][1] == "verified_failure"


def test_generate_role_pass_flag_runs_castes(client: TestClient) -> None:
    # Opt-in castes: with rolePass true the turn streams the role markers and
    # each caste's answer; one done; one development row. (The flag absent is
    # covered by every other /api/generate test — byte-identical default.)
    development = RecordingDevelopment()

    class FakeOllamaTalkOnly:
        def __init__(self) -> None:
            self.calls = 0

        def list_models(self) -> dict:
            return {"available": True, "models": ["llama3.2:3b"]}

        def chat(self, messages, *, tools=None, model=None) -> dict:
            self.calls += 1
            return {"role": "assistant", "content": f"caste answer {self.calls}"}

    app.dependency_overrides[get_ollama_client] = FakeOllamaTalkOnly
    app.dependency_overrides[get_development_tracker] = lambda: development

    response = client.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": "assess the request"}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": "role-pass-api",
            "rolePass": True,
        },
    )

    assert response.status_code == 200
    assert "caste: planner" in response.text
    assert "caste: coder" in response.text
    assert "caste: reviewer" not in response.text        # nothing written -> no review
    answer_text = "".join(
        json.loads(line[len("data: "):]).get("text", "")
        for line in response.text.splitlines()
        if line.startswith("data: ") and '"text"' in line
    )
    assert "caste answer 1" in answer_text and "caste answer 2" in answer_text
    assert response.text.count("event: done") == 1
    assert len(development.records) == 1                 # one development row per turn
    assert development.records[-1][1] == "unverified"


def test_growth_api_surfaces_are_non_autonomous(client: TestClient) -> None:
    development = RecordingDevelopment()
    skills = RecordingSkills()
    curriculum = RecordingCurriculum()
    consolidator = RecordingConsolidator()
    app.dependency_overrides[get_development_tracker] = lambda: development
    app.dependency_overrides[get_skill_memory] = lambda: skills
    app.dependency_overrides[get_curriculum_manager] = lambda: curriculum
    app.dependency_overrides[get_memory_consolidator] = lambda: consolidator

    assert client.get("/api/v1/development/metrics").json()["tasks"] == 0
    assert client.get("/api/v1/development/skills").status_code == 200
    created = client.post(
        "/api/v1/development/curriculum",
        json={"skillName": "python", "level": 1, "prompt": "write a parser"},
    ).json()
    assert created == {"id": 1, "executed": False}
    assert client.get("/api/v1/development/curriculum").json()["tasks"]
    assert client.post("/api/v1/memory/consolidate").json()["active_facts_consolidated"] == 1
    fact = client.post(
        "/api/v1/memory/facts",
        json={
            "subject": "user",
            "predicate": "prefers",
            "object": "concise output",
            "approvedBy": "operator",
        },
    )
    assert fact.status_code == 200
    assert fact.json()["fact_id"] == 7
    reconciled = client.post(
        "/api/v1/memory/facts/reconcile",
        json={
            "subject": "user",
            "predicate": "prefers",
            "object": "detailed output",
            "approvedBy": "operator",
        },
    )
    assert reconciled.status_code == 200
    assert reconciled.json()["fact_id"] == 8
