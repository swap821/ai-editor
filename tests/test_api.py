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
    get_executor,
    get_llm_client,
    get_ollama_client,
    get_approval_store,
    get_reflection_agent,
    get_rollback_engine,
    get_semantic_indexer,
    get_self_apply_engine,
)
from aios.security import scope_lock
from aios.core.executor import Executor
from aios.core.self_apply import DEFAULT_VERIFY_COMMAND
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


def test_unauthenticated_remote_client_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(config, "API_HOST", "127.0.0.1")
    monkeypatch.setattr(config, "API_TOKEN", "")

    with TestClient(app, client=("203.0.113.10", 50000)) as remote:
        response = remote.post("/api/v1/security/classify", json={"command": "echo hi"})

    assert response.status_code == 403


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
    # the fake has only llama3.2:3b, so every purpose resolves to it
    assert body["model"] == "llama3.2:3b"


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


def test_approval_req_approve_runs_yellow(client: TestClient) -> None:
    token = get_approval_store().issue("command", {"command": "pip install flask"}, "approval-test")
    response = client.post(
        "/api/v1/approval/req",
        json={"approvalToken": token, "sessionId": "approval-test", "approve": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "approved"
    assert body["executed"] is True
    assert body["result"]["status"] == "OK"


def test_approval_req_reject_does_not_run(client: TestClient) -> None:
    token = get_approval_store().issue("command", {"command": "pip install flask"}, "approval-test")
    response = client.post(
        "/api/v1/approval/req",
        json={"approvalToken": token, "sessionId": "approval-test", "approve": False},
    )
    body = response.json()
    assert body["decision"] == "rejected"
    assert body["executed"] is False


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

    monkeypatch.setattr("aios.api.main.subprocess.run", fake_run)
    engine = get_self_apply_engine(_fake_executor())

    result = engine.verifier.verify(DEFAULT_VERIFY_COMMAND, approved=True)

    assert result.passed is True
    assert calls[0]["args"] == [sys.executable, "-m", "pytest", "tests/", "-q"]
    assert calls[0]["cwd"] == str(config.PROJECT_ROOT)
    assert "shell" not in calls[0]


def test_self_apply_verifier_refuses_any_other_runner_command(monkeypatch) -> None:
    monkeypatch.setattr(
        "aios.api.main.subprocess.run",
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
