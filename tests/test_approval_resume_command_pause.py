"""Approval-resume continuation must also cover the COMMAND pause path.

The wiring map found exactly one ``human_required`` pause exit point inside
``ToolAgent.run`` (tool_agent.py ~912-915), reached via the single unified
``_dispatch`` dispatcher for ALL tool types -- commands, edits, and creations
alike. This test exercises that same exit point through a command
(``execute_terminal``) approval rather than a file creation, to confirm the
convo-tail stash/replay isn't accidentally scoped to writes only.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from aios import config
from aios.api.main import (
    app,
    get_executor,
    get_llm_client,
    get_ollama_client,
    get_semantic_indexer,
    get_approval_store,
)
from aios.core.executor import Executor
from aios.security import scope_lock
from aios.security.gateway import RateLimiter
from tests.test_api import FakeIndexer, FakeLLM, FakeOllamaYellow, RecordingAudit


class ScriptedCommandOllama(FakeOllamaYellow):
    """Records messages; issues the SAME YELLOW command every call so we can
    inspect whether the resume call's messages carry the paused turn's own
    assistant tool_call forward as continuation."""

    def __init__(self) -> None:
        self.calls: list[list] = []

    def chat(self, messages, *, tools=None, model=None) -> dict:
        self.calls.append(list(messages))
        if len(self.calls) >= 2:
            return {"role": "assistant", "content": "Installed and verified."}
        return super().chat(messages, tools=tools, model=model)


@pytest.fixture()
def client(monkeypatch) -> Iterator[TestClient]:
    sandbox = Path(tempfile.mkdtemp(prefix="cp")).resolve()
    monkeypatch.setattr(config, "PROJECT_ROOT", sandbox)
    original = scope_lock.get_scope_roots()
    scope_lock.set_scope_roots([sandbox])
    fake_ollama = ScriptedCommandOllama()
    app.dependency_overrides[get_llm_client] = FakeLLM
    app.dependency_overrides[get_ollama_client] = lambda: fake_ollama
    app.dependency_overrides[get_semantic_indexer] = lambda: FakeIndexer()
    _runner = lambda command, *, cwd, env, timeout_s: ("ok", "", 0)  # noqa: E731
    app.dependency_overrides[get_executor] = lambda: Executor(
        runner=_runner,
        rate_limiter=RateLimiter(),
        audit_log=RecordingAudit(),
        approved_runner=_runner,
    )
    get_approval_store().clear()
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            test_client._fake_ollama = fake_ollama  # type: ignore[attr-defined]
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


def test_command_pause_also_replays_convo_tail_on_resume(client: TestClient) -> None:
    fake_ollama: ScriptedCommandOllama = client._fake_ollama  # type: ignore[attr-defined]
    session_id = "command-pause-session"

    resp1 = client.post("/api/generate", json={
        "messages": [{"role": "user", "content": [{"text": "install flask"}]}],
        "modelId": "ollama.llama3.2:3b",
        "sessionId": session_id,
    })
    assert resp1.status_code == 200
    assert "event: human_required" in resp1.text
    token = _extract_approval_token(resp1.text)
    assert len(fake_ollama.calls) == 1

    resp2 = client.post("/api/generate", json={
        "messages": [{"role": "user", "content": [{"text": "install flask"}]}],
        "modelId": "ollama.llama3.2:3b",
        "sessionId": session_id,
        "approvalTokens": [token],
    })
    assert resp2.status_code == 200
    assert len(fake_ollama.calls) == 2

    call2_messages = fake_ollama.calls[1]
    found_own_tool_call = False
    for msg in call2_messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            if fn.get("name") == "execute_terminal":
                cmd = str(fn.get("arguments", {}).get("command", ""))
                if "pip install flask" in cmd:
                    found_own_tool_call = True
    assert found_own_tool_call, (
        "the command-approval pause must also stash and replay its own "
        f"assistant tool_call as continuation -- got: {call2_messages!r}"
    )
    assert "event: done" in resp2.text
