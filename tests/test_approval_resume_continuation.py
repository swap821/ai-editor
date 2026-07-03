"""RED-first integration test for approval-resume continuation (ratified option A).

Today, a turn that pauses for YELLOW approval (``human_required``) discards the
model context it built up so far -- the tail of ``convo`` beyond the initial
``[system] + messages`` prefix (the paused assistant's own tool_call, any tool
results, etc). When the human approves and the turn resumes, the model starts
from a blank ``[system] + messages`` slate all over again, with no memory of
the tool call it just paused on.

This test scripts a fake Ollama client that RECORDS every ``messages`` array it
receives across a two-pause chain:
  1. Plans ``create_file`` for ``test_alpha.py`` -> the turn pauses.
  2. Resume with token 1: the fake's SECOND call must see, in its own messages,
     its OWN turn-1 assistant tool_call for file A (the continuation -- this is
     the RED assertion) PLUS the applied-grant tool result anchor. It then
     plans ``create_file`` for ``test_beta.py`` -> the turn pauses AGAIN
     (supervision authority is unchanged: a second write still needs its own
     token).
  3. Resume with token 2: the fake's THIRD call sees the full history and
     concludes with a text answer (no further tool calls).

Assertions: exactly 2 ``human_required`` pauses total, both files land on
disk, the outcome chain completes with ``done``, and the final turn mints
exactly one skill whose recorded recipe carries both writes.
"""
from __future__ import annotations

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
)
from aios.core.executor import Executor
from aios.memory.skills import SkillMemory
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
_BETA_CONTENT = (
    "def sub(a, b):\n"
    "    return a - b\n"
    "\n"
    "\n"
    "def test_sub():\n"
    "    assert sub(5, 3) == 2\n"
)


class ScriptedRecordingOllama:
    """Records every ``messages`` array it is called with; scripts a 2-pause chain."""

    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(
        self,
        messages: list,
        *,
        tools: Optional[list] = None,
        model: Optional[str] = None,
    ) -> dict:
        # Record a deep-ish copy (dicts are not mutated downstream in a way
        # that matters for this test, but list() keeps the outer list stable).
        self.calls.append(list(messages))
        call_index = len(self.calls)
        if call_index == 1:
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
        if call_index == 2:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "create_file",
                            "arguments": {
                                "filepath": "test_beta.py",
                                "content": _BETA_CONTENT,
                            },
                        }
                    }
                ],
            }
        return {
            "role": "assistant",
            "content": "Both files are in place and verified.",
        }


@pytest.fixture()
def client(monkeypatch) -> Iterator[TestClient]:
    # SHORT sandbox dir on purpose (not tmp_path): pytest's test-name-derived
    # tmp dir is long enough that the gateway's HIGH_ENTROPY credential
    # detector false-positives on the auto-verify command's absolute path and
    # RED-blocks the forced verify -- see test_grant_workflow_steps.py's
    # fixture for the same precedent.
    sandbox = Path(tempfile.mkdtemp(prefix="ar"))
    monkeypatch.setattr(config, "PROJECT_ROOT", sandbox)
    original = scope_lock.get_scope_roots()
    scope_lock.set_scope_roots([sandbox])
    skills = SkillMemory(db_path=sandbox / "resume_skills.db")
    fake_ollama = ScriptedRecordingOllama()
    app.dependency_overrides[get_llm_client] = FakeLLM
    app.dependency_overrides[get_ollama_client] = lambda: fake_ollama
    app.dependency_overrides[get_semantic_indexer] = lambda: FakeIndexer()
    app.dependency_overrides[get_skill_memory] = lambda: skills
    _runner = lambda command, *, cwd, env, timeout_s: ("1 passed", "", 0)  # noqa: E731
    app.dependency_overrides[get_executor] = lambda: Executor(
        runner=_runner,
        rate_limiter=RateLimiter(),
        audit_log=RecordingAudit(),
        approved_runner=_runner,
    )
    get_approval_store().clear()
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            test_client._skills = skills  # type: ignore[attr-defined]
            test_client._sandbox = sandbox  # type: ignore[attr-defined]
            test_client._fake_ollama = fake_ollama  # type: ignore[attr-defined]
            yield test_client
    finally:
        app.dependency_overrides.clear()
        scope_lock.set_scope_roots(list(original))
        shutil.rmtree(sandbox, ignore_errors=True)


def _extract_approval_token(body: str) -> str:
    import json as _json
    for line in body.splitlines():
        if line.startswith("data:"):
            payload = _json.loads(line[len("data:"):].strip())
            token = (payload.get("input") or {}).get("approvalToken")
            if token:
                return str(token)
    raise AssertionError(f"no approvalToken found in SSE body: {body!r}")


SESSION_ID = "resume-continuation-session"


def test_two_pause_chain_replays_convo_tail_and_teaches_one_skill(
    client: TestClient,
) -> None:
    fake_ollama: ScriptedRecordingOllama = client._fake_ollama  # type: ignore[attr-defined]
    sandbox: Path = client._sandbox  # type: ignore[attr-defined]

    # --- Turn 1: fresh directive, no tokens -> plans file A -> pauses. ---
    resp1 = client.post("/api/generate", json={
        "messages": [{"role": "user", "content": [
            {"text": "create test_alpha.py, then create test_beta.py, then verify both"}
        ]}],
        "modelId": "ollama.llama3.2:3b",
        "sessionId": SESSION_ID,
    })
    assert resp1.status_code == 200
    body1 = resp1.text
    assert "event: human_required" in body1
    token1 = _extract_approval_token(body1)
    assert len(fake_ollama.calls) == 1

    # --- Turn 2: resume with token 1. ---
    resp2 = client.post("/api/generate", json={
        "messages": [{"role": "user", "content": [
            {"text": "create test_alpha.py, then create test_beta.py, then verify both"}
        ]}],
        "modelId": "ollama.llama3.2:3b",
        "sessionId": SESSION_ID,
        "approvalTokens": [token1],
    })
    assert resp2.status_code == 200
    body2 = resp2.text

    # RED ASSERTION (today this fails): the fake's SECOND call must see its
    # OWN turn-1 assistant tool_call for file A as CONTINUATION -- i.e. an
    # assistant message whose tool_calls include create_file/test_alpha.py --
    # somewhere in the messages array it receives on this second invocation.
    assert len(fake_ollama.calls) == 2, "the model must be re-invoked on resume"
    call2_messages = fake_ollama.calls[1]
    found_own_tool_call = False
    for msg in call2_messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            if fn.get("name") == "create_file":
                fp = str(fn.get("arguments", {}).get("filepath", ""))
                if "test_alpha.py" in fp:
                    found_own_tool_call = True
    assert found_own_tool_call, (
        "resume call must replay the paused turn's OWN assistant tool_call "
        "for test_alpha.py as convo-tail continuation, not start fresh -- "
        f"got messages: {call2_messages!r}"
    )

    # The turn must ALSO still require approval for file B -- authority is
    # unchanged; the tail is context only, never an authorization bypass.
    assert "event: human_required" in body2
    token2 = _extract_approval_token(body2)

    # --- Turn 3: resume with token 2 -> model concludes. ---
    resp3 = client.post("/api/generate", json={
        "messages": [{"role": "user", "content": [
            {"text": "create test_alpha.py, then create test_beta.py, then verify both"}
        ]}],
        "modelId": "ollama.llama3.2:3b",
        "sessionId": SESSION_ID,
        "approvalTokens": [token2],
    })
    assert resp3.status_code == 200
    body3 = resp3.text
    assert "event: done" in body3
    assert len(fake_ollama.calls) == 3

    # Exactly 2 human_required pauses total across the whole chain.
    total_pauses = body1.count("event: human_required") + body2.count("event: human_required")
    assert total_pauses == 2, f"expected exactly 2 pauses, counted {total_pauses}"
    assert "event: human_required" not in body3

    # Both files landed on disk.
    assert (sandbox / "test_alpha.py").read_text(encoding="utf-8") == _ALPHA_CONTENT
    assert (sandbox / "test_beta.py").read_text(encoding="utf-8") == _BETA_CONTENT

    # The final turn mints exactly one skill whose recipe carries both writes.
    skills: SkillMemory = client._skills  # type: ignore[attr-defined]
    rows = [r for r in skills.list() if r["status"] != "superseded"]
    assert len(rows) == 1, f"expected exactly one minted skill, got {len(rows)}"
    steps = " | ".join(rows[0]["steps"])
    assert "test_alpha.py" in steps, f"recipe missing file A: {steps!r}"
    assert "test_beta.py" in steps, f"recipe missing file B: {steps!r}"
