"""Regression: a granted (approved) write must count as a workflow step.

Found live by prove_it.py --scripted (2026-07-03), step 7 LEARNING: on an
approval-resume turn the granted creation is applied deterministically by
ToolAgent._pre_apply_grants, which historically emitted only ``tool_result``
frames — but main.py builds ``workflow_steps`` from ``tool_call`` frames
alone, and ``record_outcome`` gates ``skills.record_attempt`` on a non-empty
``workflow_steps``. Net effect: the CLEANEST supervised path (pause ->
operator approves -> grant applies -> forced auto-verify passes STRONG ->
verified_success) taught the organism nothing, ever, unless the model
happened to re-issue redundant tool calls on the resume turn.
"""
from __future__ import annotations

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
    get_skill_memory,
    get_approval_store,
)
from aios.core.executor import Executor
from aios.memory.skills import SkillMemory
from aios.security import scope_lock
from aios.security.gateway import RateLimiter
from tests.test_api import FakeIndexer, FakeLLM, RecordingAudit

_SELF_TESTING_FILE = (
    "def add(a, b):\n"
    "    return a + b\n"
    "\n"
    "\n"
    "def test_add():\n"
    "    assert add(2, 3) == 5\n"
)


class FakeOllamaConcludes:
    """After the grant pre-applies, the model simply concludes — the clean
    supervised path issues NO further tool calls on the resume turn."""

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(self, messages, *, tools=None, model=None) -> dict:
        return {"role": "assistant", "content": "The file is in place and verified."}


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    # SHORT sandbox dir on purpose (not tmp_path): pytest's test-name-derived
    # tmp dir is long enough that the gateway's HIGH_ENTROPY credential
    # detector false-positives on the auto-verify command's absolute path and
    # RED-blocks the forced verify ("Human approval cannot authorise a RED
    # action") — a real scanner defect filed separately (2026-07-03); this
    # test targets the workflow_steps seam, not that one.
    import shutil
    import tempfile
    sandbox = Path(tempfile.mkdtemp(prefix="ag"))
    monkeypatch.setattr(config, "PROJECT_ROOT", sandbox)
    original = scope_lock.get_scope_roots()
    scope_lock.set_scope_roots([sandbox])
    skills = SkillMemory(db_path=sandbox / "grant_skills.db")
    app.dependency_overrides[get_llm_client] = FakeLLM
    app.dependency_overrides[get_ollama_client] = FakeOllamaConcludes
    app.dependency_overrides[get_semantic_indexer] = lambda: FakeIndexer()
    app.dependency_overrides[get_skill_memory] = lambda: skills
    # A recognized runner reporting a genuine pass -> the forced auto-verify
    # is STRONG. approved_runner is injected too: the FORCED auto-verify runs
    # approved=True -> approved_runner, which fail-closes on the container
    # backend in this harness (no Docker); the plain runner alone only covers
    # GREEN model-issued commands.
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
            yield test_client
    finally:
        app.dependency_overrides.clear()
        scope_lock.set_scope_roots(list(original))
        shutil.rmtree(sandbox, ignore_errors=True)


def test_granted_write_mints_skill_evidence(client: TestClient) -> None:
    """Approve -> grant applies -> STRONG verify -> the skill MUST record."""
    token = get_approval_store().issue(
        "create",
        {"filepath": "test_selfcheck.py", "content": _SELF_TESTING_FILE},
        "grant-steps-session",
    )
    response = client.post("/api/generate", json={
        "messages": [{"role": "user", "content": [
            {"text": "create test_selfcheck.py with an add function and its test, then verify"}
        ]}],
        "modelId": "ollama.llama3.2:3b",
        "sessionId": "grant-steps-session",
        "approvalTokens": [token],
    })
    assert response.status_code == 200
    body = response.text
    assert "event: human_required" not in body, "token was granted; no pause expected"
    assert "event: done" in body
    sandbox: Path = client._sandbox  # type: ignore[attr-defined]
    assert (sandbox / "test_selfcheck.py").read_text(encoding="utf-8") == _SELF_TESTING_FILE
    assert "[VERIFY PASS]" in body, "the forced auto-verify must have run"

    skills: SkillMemory = client._skills  # type: ignore[attr-defined]
    rows = [r for r in skills.list() if r["status"] != "superseded"]
    assert len(rows) == 1, (
        "a STRONG-verified supervised write must mint exactly one skill "
        f"attempt; got {len(rows)} (the granted write never reached "
        "workflow_steps?)"
    )
    row = rows[0]
    assert row["success_count"] == 1
    assert row["verification_strength"] == "STRONG"
    steps = " | ".join(row["steps"])
    assert "create_file" in steps and "test_selfcheck.py" in steps, (
        f"the recipe must carry the granted write itself; got steps: {steps!r}"
    )
