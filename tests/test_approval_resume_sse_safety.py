"""SSE-safety + done-clears tests for approval-resume continuation (S2/S3).

Covers TDD items 3 and 4 from the ratified plan:
  3. "_convo_tail" never appears as a substring anywhere in any SSE response
     body across the whole pause/resume flow, and the stashed tail (inspected
     directly in the turn_state store mid-flow) never contains the issued
     approvalToken value.
  4. After the final `done`, ``turn_state.take(session)`` is None. A fresh
     token-less directive sent after a stale pause does NOT inherit tail
     context (the model sees no continuation from the abandoned pause).
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterator, Optional

import pytest
from fastapi.testclient import TestClient

from aios import config
from aios.api.main import (
    app,
    get_executor,
    get_llm_client,
    get_ollama_client,
    get_semantic_indexer,
    get_skill_memory,
    get_approval_store,
    get_cerebellum,
    get_development_tracker,
    get_swarm_pattern_memory,
    get_autonomy,
    get_curriculum_manager,
    get_memory_consolidator,
    get_conversation_state_store,
    get_alignment_evaluation_store,
    get_semantic_facts,
    get_compactor,
    get_native_planner,
)
from aios.agents.swarm_patterns import SwarmPatternMemory
from aios.core.autonomy import AutonomyLedger
from aios.core.cerebellum import Cerebellum
from aios.core.executor import Executor
from aios.core.native_planner import NativePlanner
from aios.memory.alignment_evaluation import AlignmentEvaluationStore
from aios.memory.compaction import MemoryCompactor
from aios.memory.consolidation import MemoryConsolidator
from aios.memory.conversation import ConversationStateStore
from aios.memory.curriculum import CurriculumManager
from aios.memory.development import DevelopmentTracker
from aios.memory.facts import SemanticFacts
from aios.memory.skills import SkillMemory
from aios.runtime import turn_state
from aios.security import scope_lock
from aios.security.gateway import RateLimiter
from tests.test_api import FakeIndexer, FakeLLM, RecordingAudit

_ALPHA_CONTENT = (
    "def add(a, b):\n"
    "    return a + b\n"
    "\n"
    "\n"
    "def test_add():\n"
    "    assert add(2, 3) == 5\n"
)


class ScriptedOllama:
    """Plans a create_file (pauses) only for the 'create test_alpha.py' ask;
    any other user text (e.g. an unrelated fresh directive) concludes
    immediately without touching a tool, and a replay that already carries
    its own prior tool_call also concludes."""

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(
        self,
        messages: list,
        *,
        tools: Optional[list] = None,
        model: Optional[str] = None,
    ) -> dict:
        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                return {"role": "assistant", "content": "Done, verified."}
        latest_user = ""
        for msg in messages:
            if msg.get("role") == "user":
                latest_user = str(msg.get("content", ""))
        if "create test_alpha.py" not in latest_user:
            return {"role": "assistant", "content": "Nothing to do here."}
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "create_file",
                        "arguments": {
                            "filepath": "test_alpha.py",
                            "content": _ALPHA_CONTENT,
                        },
                    }
                }
            ],
        }


@pytest.fixture()
def client(monkeypatch) -> Iterator[TestClient]:
    sandbox = Path(tempfile.mkdtemp(prefix="ss")).resolve()
    monkeypatch.setattr(config, "PROJECT_ROOT", sandbox)
    monkeypatch.setattr(config, "CORTEX_BUS", False)
    original = scope_lock.get_scope_roots()
    scope_lock.set_scope_roots([sandbox])
    db = sandbox / "test.db"
    skills = SkillMemory(db_path=sandbox / "sse_skills.db")
    facts = SemanticFacts(db_path=db)
    app.dependency_overrides[get_llm_client] = FakeLLM
    app.dependency_overrides[get_ollama_client] = lambda: ScriptedOllama()
    app.dependency_overrides[get_semantic_indexer] = lambda: FakeIndexer()
    app.dependency_overrides[get_skill_memory] = lambda: skills
    app.dependency_overrides[get_cerebellum] = lambda: Cerebellum(
        db_path=sandbox / "cerebellum.db"
    )
    app.dependency_overrides[get_semantic_facts] = lambda: facts
    app.dependency_overrides[get_development_tracker] = lambda: DevelopmentTracker(
        db_path=db, facts=facts
    )
    app.dependency_overrides[get_swarm_pattern_memory] = lambda: SwarmPatternMemory(
        db_path=db
    )
    app.dependency_overrides[get_autonomy] = lambda: AutonomyLedger(db_path=db)
    app.dependency_overrides[get_curriculum_manager] = lambda: CurriculumManager(
        db_path=db
    )
    app.dependency_overrides[get_memory_consolidator] = lambda: MemoryConsolidator(
        db_path=db
    )
    app.dependency_overrides[get_conversation_state_store] = (
        lambda: ConversationStateStore(db_path=db)
    )
    app.dependency_overrides[get_alignment_evaluation_store] = (
        lambda: AlignmentEvaluationStore(db_path=db)
    )
    app.dependency_overrides[get_compactor] = lambda: MemoryCompactor(
        db_path=db, audit_db_path=db
    )
    app.dependency_overrides[get_native_planner] = lambda: NativePlanner(
        skills=skills, patterns=SwarmPatternMemory(db_path=db), facts=facts
    )
    _runner = lambda command, *, cwd, env, timeout_s: ("1 passed", "", 0)  # noqa: E731
    app.dependency_overrides[get_executor] = lambda: Executor(
        runner=_runner,
        rate_limiter=RateLimiter(),
        audit_log=RecordingAudit(),
        approved_runner=_runner,
    )
    get_approval_store().clear()
    turn_state.clear("sse-safety-session")
    turn_state.clear("done-clears-session")
    turn_state.clear("stale-pause-session")
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            test_client._skills = skills  # type: ignore[attr-defined]
            test_client._sandbox = sandbox  # type: ignore[attr-defined]
            yield test_client
    finally:
        app.dependency_overrides.clear()
        scope_lock.set_scope_roots(list(original))
        shutil.rmtree(sandbox, ignore_errors=True)


def _extract_approval_token(body: str) -> str:
    for line in body.splitlines():
        if line.startswith("data:"):
            payload = json.loads(line[len("data:"):].strip())
            token = (payload.get("input") or {}).get("approvalToken")
            if token:
                return str(token)
    raise AssertionError(f"no approvalToken found in SSE body: {body!r}")


def test_convo_tail_key_never_appears_in_sse_body_and_token_never_in_stash(
    client: TestClient,
) -> None:
    session_id = "sse-safety-session"

    resp1 = client.post("/api/generate", json={
        "messages": [{"role": "user", "content": [{"text": "create test_alpha.py"}]}],
        "modelId": "ollama.llama3.2:3b",
        "sessionId": session_id,
    })
    assert resp1.status_code == 200
    body1 = resp1.text
    assert "_convo_tail" not in body1, "the tail key must never reach the SSE wire"
    token = _extract_approval_token(body1)
    assert token, "must have issued an approval token"

    # Inspect the stash directly, mid-flow, before it is consumed.
    stashed = turn_state._TURN_STATE._store.get(session_id)
    assert stashed is not None, "pause must have stashed a tail for this session"
    tail, _expires_at = stashed
    stashed_text = json.dumps(tail)
    assert token not in stashed_text, (
        "the stashed convo tail must never contain the issued approvalToken -- "
        "it is model context only, never an authorization vector"
    )

    resp2 = client.post("/api/generate", json={
        "messages": [{"role": "user", "content": [{"text": "create test_alpha.py"}]}],
        "modelId": "ollama.llama3.2:3b",
        "sessionId": session_id,
        "approvalTokens": [token],
    })
    assert resp2.status_code == 200
    body2 = resp2.text
    assert "_convo_tail" not in body2, "the tail key must never reach the SSE wire"
    assert "event: done" in body2


def test_done_clears_turn_state(client: TestClient) -> None:
    session_id = "done-clears-session"

    resp1 = client.post("/api/generate", json={
        "messages": [{"role": "user", "content": [{"text": "create test_alpha.py"}]}],
        "modelId": "ollama.llama3.2:3b",
        "sessionId": session_id,
    })
    token = _extract_approval_token(resp1.text)
    assert turn_state._TURN_STATE._store.get(session_id) is not None, (
        "pause must have stashed a tail for this session"
    )
    resp2 = client.post("/api/generate", json={
        "messages": [{"role": "user", "content": [{"text": "create test_alpha.py"}]}],
        "modelId": "ollama.llama3.2:3b",
        "sessionId": session_id,
        "approvalTokens": [token],
    })
    assert "event: done" in resp2.text
    assert turn_state.take(session_id) is None, (
        "after the final done, turn_state must hold nothing for this session"
    )


def test_stale_pause_then_tokenless_directive_does_not_inherit_tail(
    client: TestClient,
) -> None:
    session_id = "stale-pause-session"

    resp1 = client.post("/api/generate", json={
        "messages": [{"role": "user", "content": [{"text": "create test_alpha.py"}]}],
        "modelId": "ollama.llama3.2:3b",
        "sessionId": session_id,
    })
    assert "event: human_required" in resp1.text, (
        f"expected human_required in SSE body; got events: "
        f"{[l.split('data:')[0].strip() for l in resp1.text.splitlines() if l.startswith('event:')]}"
        f"\n\nFull response (first 800 chars):\n{resp1.text[:800]}"
    )
    # Confirm something WAS stashed (the pause happened).
    assert turn_state._TURN_STATE._store.get(session_id) is not None

    # A fresh, token-LESS directive on the SAME session must not carry the
    # stale tail forward -- it must be cleared, not replayed.
    resp2 = client.post("/api/generate", json={
        "messages": [{"role": "user", "content": [{"text": "unrelated fresh request"}]}],
        "modelId": "ollama.llama3.2:3b",
        "sessionId": session_id,
    })
    assert resp2.status_code == 200
    assert turn_state._TURN_STATE._store.get(session_id) is None, (
        "a token-less fresh directive must clear any stale stashed tail, "
        "not silently inherit it"
    )
