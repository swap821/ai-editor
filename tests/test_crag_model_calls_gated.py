"""CRAG's model calls pass a gateway entrance on every turn route.

Found 2026-10-29 (docs/ONE_GATEWAY.md): ``/api/v1/chat`` recalled memory with no
CRAG judge or cloud source, so recall fell back to calling the local model
(``AIOS_CRAG_LLM_JUDGE``) and the cloud model (``AIOS_CRAG_EXTERNAL`` +
``AIOS_CRAG_CLOUD``) directly, outside every entrance. Recall has no such
fallback now; both routes build their calls in
``aios/application/turns/crag_model_calls.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional

import pytest
from fastapi.testclient import TestClient

from aios import config
from aios.api.deps import get_memory_authority, get_optional_principal
from aios.api.main import (
    app,
    get_bedrock_client,
    get_gemini_client,
    get_ollama_client,
    get_semantic_facts,
    get_semantic_indexer,
)
from aios.application.turns.crag_model_calls import crag_model_calls
from aios.core.autonomy import UNGOVERNED_FIXTURE
from aios.core.model_calls import current_entrance
from aios.domain.memory import MemoryHit


class EntranceRecordingChat:
    """A chat provider that records the gateway entrance each call ran inside."""

    def __init__(self, reply: str = "0.9") -> None:
        self.reply = reply
        self.calls: list[tuple[Optional[str], str]] = []

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(self, messages, *, tools=None, model=None) -> dict:
        self.calls.append((current_entrance(), str(messages[-1]["content"])))
        return {"role": "assistant", "content": self.reply}


class ContextSpy:
    def __init__(self) -> None:
        self.saved: list = []

    def save(self, context) -> None:  # noqa: ANN001 - test spy
        self.saved.append(context)

    def save_bundle(self, context, receipt) -> None:  # noqa: ANN001 - test spy
        self.saved.append(context)


@dataclass
class BoundPrincipal:
    principal_id: str = "operator:test"
    constitution_digest: str = "b" * 64


@pytest.fixture()
def crag_on(monkeypatch) -> None:
    monkeypatch.setattr(config, "CRAG_LLM_JUDGE", True)
    monkeypatch.setattr(config, "CRAG_CLOUD", True)


def _calls(principal, local, cloud):
    return crag_model_calls(
        turn_id="turn-1",
        principal=principal,
        local_provider=local,
        cloud_provider=cloud,
        context_store=ContextSpy(),
        emergency_stop=UNGOVERNED_FIXTURE,
    )


def test_switched_off_there_are_no_crag_model_calls(monkeypatch) -> None:
    monkeypatch.setattr(config, "CRAG_LLM_JUDGE", False)
    monkeypatch.setattr(config, "CRAG_CLOUD", False)
    assert _calls(None, EntranceRecordingChat(), EntranceRecordingChat()) == (
        None,
        None,
    )


def test_an_anonymous_judge_takes_the_compatibility_entrance(crag_on) -> None:
    local, cloud = EntranceRecordingChat("0.7"), EntranceRecordingChat("answer")
    judge, source = _calls(None, local, cloud)

    assert judge("q", "a passage") == 0.7
    assert [entrance for entrance, _ in local.calls] == ["complete_compatibility"]
    # No entrance carries an unbound call to the cloud, so none is made.
    assert source("q") == []
    assert cloud.calls == []


def test_a_bound_principal_takes_the_route_entrance(crag_on) -> None:
    local, cloud = EntranceRecordingChat("0.7"), EntranceRecordingChat("answer")
    judge, source = _calls(BoundPrincipal(), local, cloud)

    assert judge("q", "a passage") == 0.7
    assert source("q") == ["answer"]
    assert [entrance for entrance, _ in local.calls] == ["route"]
    assert [entrance for entrance, _ in cloud.calls] == ["route"]


def test_a_principal_with_no_constitution_is_treated_as_unbound(crag_on) -> None:
    local, cloud = EntranceRecordingChat("0.7"), EntranceRecordingChat("answer")
    judge, source = _calls(BoundPrincipal(constitution_digest=""), local, cloud)

    judge("q", "a passage")
    assert [entrance for entrance, _ in local.calls] == ["complete_compatibility"]
    assert source("q") == []
    assert cloud.calls == []


# --------------------------------------------------------------------------- #
# The route: /api/v1/chat's recall judge runs inside an entrance
# --------------------------------------------------------------------------- #


class VerifiedHitAuthority:
    """One verified semantic hit, so recall reaches the CRAG judge."""

    def recall(self, query, context, retrieval_fn=None):
        if tuple(getattr(context, "memory_types", ())) != ("semantic",):
            return []
        return [
            MemoryHit(
                memory_type="semantic",
                content_reference="crag-chat-1",
                text="A verified memory passage for the chat CRAG judge.",
                score=0.9,
                faiss=0.9,
                verification_status="verified",
                source="test",
            )
        ]

    def owns_store(self, name, candidate):
        return False

    def recall_skills(self, query, limit):
        return []

    def facts_search(self, query):
        return []

    def self_model(self):
        return None

    def record_episodic(self, *args, **kwargs):
        return None

    def record_semantic_chat(self, *args, **kwargs):
        return None


class _NoFacts:
    def facts_for(self, subject, predicate=None, principal_id=None):
        return []


class _NoIndex:
    def add(self, text: str) -> int:
        return 1


@pytest.fixture()
def chat_client() -> Iterator[tuple[TestClient, EntranceRecordingChat]]:
    local = EntranceRecordingChat("0.9")
    app.dependency_overrides[get_optional_principal] = lambda: None
    app.dependency_overrides[get_ollama_client] = lambda: local
    app.dependency_overrides[get_bedrock_client] = lambda: None
    app.dependency_overrides[get_gemini_client] = lambda: None
    app.dependency_overrides[get_semantic_indexer] = lambda: _NoIndex()
    app.dependency_overrides[get_semantic_facts] = lambda: _NoFacts()
    app.dependency_overrides[get_memory_authority] = lambda: VerifiedHitAuthority()
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        yield client, local
    app.dependency_overrides.clear()


def test_the_chat_routes_crag_judge_runs_inside_an_entrance(
    chat_client, monkeypatch
) -> None:
    from aios.api import turn_pipeline

    monkeypatch.setattr(config, "CRAG", True)
    monkeypatch.setattr(config, "CRAG_LLM_JUDGE", True)
    monkeypatch.setattr(config, "CRAG_EXTERNAL", False)
    # Chat's recall reads the process memory authority, not the route's.
    monkeypatch.setattr(
        turn_pipeline, "get_memory_authority", lambda: VerifiedHitAuthority()
    )
    client, local = chat_client

    response = client.post(
        "/api/v1/chat",
        json={"transcript": "tell me about the memory passage", "sessionId": "c1"},
    )

    assert response.status_code == 200
    judged = [
        entrance
        for entrance, prompt in local.calls
        if prompt.startswith("Rate how RELEVANT")
    ]
    # Positive control: the judge really ran on this route.
    assert judged, local.calls
    assert judged == ["complete_compatibility"] * len(judged)
    # And nothing else this route asked of the model went outside an entrance.
    assert all(entrance for entrance, _ in local.calls), local.calls
