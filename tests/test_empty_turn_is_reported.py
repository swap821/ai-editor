"""A turn where the model produces nothing must SAY so.

The defect
----------
When the agent loop finished with no tool call, no prose and no code, the turn
still ended with `done` — a success-shaped terminal event, indistinguishable
downstream from a completed turn.

The observed shape, from the raw SSE of a real failing turn (all nine events):

    turn.started -> plan -> query_knowledge -> query_skills
                 -> alignment notice -> route -> done

It routes to the model and ends. A successful turn goes
``route -> create_file -> ... -> [VERIFY PASS]``.

Downstream this became ``unverified``: auto-verify only fires after a write, so
a turn that writes nothing produces no verification evidence. Organ 44's golden
cohort lost missions to it with **nothing in the audit trail saying the model
returned nothing**.

Why it was expensive to find
----------------------------
The failure is invisible by construction. There is no error to record, only an
absence — so every diagnostic built for failing turns (failure reasons, evidence
rows, verdict text) had nothing to attach to. Four hypotheses were tested and
rejected before the cause was seen: stale files, a mis-framing SSE parser,
position in the cohort, and accumulated memory. None of them; the model simply
returned nothing, sometimes.

What this file pins
-------------------
Both directions. The error must fire on a genuinely empty turn, and must NOT
fire on any turn where the model did something — including a text-only answer,
which is a perfectly legitimate conversational turn and must not be reported as
a failure.

The alignment notice is specifically excluded from "the model did something".
A turn that emits only that notice looks like it spoke and did not: the notice
is the system's, not the model's, and treating it as output is exactly what let
this hide.
"""

from __future__ import annotations


from fastapi.testclient import TestClient

from aios.api.deps import get_ollama_client
from aios.api.main import app

# Reuses test_api's fixture rather than rebuilding it: it already wires FakeLLM
# (so /generate never reaches live Ollama), a fake executor and a fake indexer.
from tests.test_api import _cookie_session_id, client  # noqa: F401


class _SilentModel:
    """A model that answers every turn with nothing at all."""

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(self, messages, *, tools=None, model=None) -> dict:
        return {"role": "assistant", "content": "", "tool_calls": []}


class _TalkingModel:
    """A model that answers in prose and calls no tools -- entirely valid."""

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(self, messages, *, tools=None, model=None) -> dict:
        return {
            "role": "assistant",
            "content": "Python's GIL serialises bytecode execution per process.",
            "tool_calls": [],
        }


def _events(api: TestClient, prompt: str) -> list[str]:
    """Return the SSE event names for one generate turn."""
    session = _cookie_session_id(api)
    response = api.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session,
            "approvalTokens": [],
        },
    )
    assert response.status_code == 200
    names: list[str] = []
    for raw in response.text.splitlines():
        line = raw.strip()
        if line.startswith("event:"):
            names.append(line[len("event:") :].strip())
    return names


def _error_texts(api: TestClient, prompt: str) -> list[str]:
    session = _cookie_session_id(api)
    response = api.post(
        "/api/generate",
        json={
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "modelId": "ollama.llama3.2:3b",
            "sessionId": session,
            "approvalTokens": [],
        },
    )
    texts: list[str] = []
    event: str | None = None
    for raw in response.text.splitlines():
        line = raw.strip()
        if line.startswith("event:"):
            event = line[len("event:") :].strip()
        elif line.startswith("data:") and event == "error":
            texts.append(line[len("data:") :].strip())
    return texts


def test_a_turn_that_produces_nothing_is_reported_as_an_error(
    client: TestClient,  # noqa: F811
) -> None:
    """The defect itself.

    Before this fix the stream ended `done` and the caller had no way to tell
    an empty turn from a completed one.
    """
    app.dependency_overrides[get_ollama_client] = _SilentModel
    try:
        names = _events(client, "Create a Pipeline class and tests for it.")
    finally:
        app.dependency_overrides.pop(get_ollama_client, None)

    assert "error" in names, (
        "an empty turn still ended without an error -- it is indistinguishable "
        "from a completed turn, which is the whole defect"
    )
    assert "done" in names, (
        "the stream must still terminate normally; this fix names the failure, "
        "it does not swallow the turn"
    )


def test_the_error_says_what_actually_happened(client: TestClient) -> None:  # noqa: F811  # noqa: F811
    """A diagnosable message, not just a non-zero signal.

    The cost of this bug was diagnosis time, so the message has to carry the
    finding: nothing written, nothing verified, retry.
    """
    app.dependency_overrides[get_ollama_client] = _SilentModel
    try:
        texts = " ".join(_error_texts(client, "Create a Pipeline class."))
    finally:
        app.dependency_overrides.pop(get_ollama_client, None)

    assert "no output" in texts or "produced no output" in texts, texts
    assert "verified" in texts, "the message should say nothing was verified"


def test_a_prose_only_answer_is_not_an_error(client: TestClient) -> None:  # noqa: F811  # noqa: F811
    """The over-correction guard, and the one that matters most.

    A model that answers a question in prose and calls no tools has done its
    job. Reporting that as a failed turn would break every conversational turn
    in the product to fix a coding-agent bug.
    """
    app.dependency_overrides[get_ollama_client] = _TalkingModel
    try:
        names = _events(client, "What is the GIL?")
    finally:
        app.dependency_overrides.pop(get_ollama_client, None)

    assert "done" in names
    assert "error" not in names, (
        "a prose answer was reported as an empty turn -- the check must treat "
        "model text as output, or ordinary conversation becomes a failure"
    )


def test_a_blank_reply_is_flagged_as_a_placeholder() -> None:
    """The mechanism the pipeline check depends on.

    A blank answer still gets a visible "(no answer)" stand-in, but it must be
    marked, or one layer up it is indistinguishable from a real reply — an
    empty turn appearing to have spoken while writing and verifying nothing.
    That is exactly how this reached organ 44's cohort as `unverified`.
    """
    import re

    from aios.agents import tool_loop_helpers

    fence = re.compile(r"```([a-zA-Z0-9_+-]*)\s*\n(.*?)```", re.DOTALL)
    events = list(
        tool_loop_helpers.finish_stream("   ", code_fence=fence, preview_limit=400)
    )
    texts = [e for e in events if e["type"] == "text"]

    assert texts, "the placeholder itself is unchanged and still emitted"
    assert all(e.get("placeholder") for e in texts), (
        "the blank-reply stand-in is not flagged, so the turn pipeline cannot "
        "tell it from something the model actually said"
    )


def test_a_real_reply_is_never_flagged_as_a_placeholder() -> None:
    """The other direction: genuine text must not be discarded as filler."""
    import re

    from aios.agents import tool_loop_helpers

    fence = re.compile(r"```([a-zA-Z0-9_+-]*)\s*\n(.*?)```", re.DOTALL)
    events = list(
        tool_loop_helpers.finish_stream(
            "here is the answer", code_fence=fence, preview_limit=400
        )
    )
    texts = [e for e in events if e["type"] == "text"]

    assert texts
    assert not any(e.get("placeholder") for e in texts), (
        "a real answer was flagged as a placeholder -- it would be ignored and "
        "the turn wrongly reported as empty"
    )
