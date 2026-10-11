"""A turn the MODEL failed is a measured failure, never a broken harness.

The SSE ``error`` event carries both the backend's own failures and its honest
diagnosis of a turn the model failed. The nightly endurance run could not tell
them apart: a 0.5B model left five turns in a row empty or looping, the tester
aborted on "5 consecutive errors", and the gate reported that the harness
proved nothing. That was red on four nights (2026-10-07..10) with no backend
change: the gate's own rule -- fail on harness integrity, never on score --
broken by an error that was really a score.

What this file pins, both directions:

* the two model-failure diagnoses carry a code (``aios/core/turn_failures.py``)
  through the stream, and the stream still ends ``done``;
* the tester scores a coded error as ``model_failure`` and never aborts on it;
* an UNCODED error is still an error, and five in a row still abort the run.
"""

from __future__ import annotations

import argparse
import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aios.api.deps import get_ollama_client
from aios.api.main import app
from aios.core import turn_failures
from tools import endurance_tester

# Reuses test_api's fixture: FakeLLM, a fake executor, a fake indexer.
from tests.test_api import _cookie_session_id, client  # noqa: F401


# --------------------------------------------------------------------------- #
# The backend names who failed the turn.
# --------------------------------------------------------------------------- #


class _SilentModel:
    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(self, messages, *, tools=None, model=None) -> dict:
        return {"role": "assistant", "content": "", "tool_calls": []}


class _LoopingModel:
    """Asks for the same read, with nothing changing, every time."""

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(self, messages, *, tools=None, model=None) -> dict:
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "read_file",
                        "arguments": {"filepath": "README.md"},
                    }
                }
            ],
        }


def _frames(api: TestClient, model: Any, prompt: str) -> list[tuple[str, Any]]:
    app.dependency_overrides[get_ollama_client] = model
    try:
        response = api.post(
            "/api/generate",
            json={
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "modelId": "ollama.llama3.2:3b",
                "sessionId": _cookie_session_id(api),
                "approvalTokens": [],
            },
        )
    finally:
        app.dependency_overrides.pop(get_ollama_client, None)
    assert response.status_code == 200
    frames: list[tuple[str, Any]] = []
    event = ""
    for raw in response.text.splitlines():
        line = raw.strip()
        if line.startswith("event:"):
            event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            frames.append((event, json.loads(line[len("data:") :].strip())))
    return frames


def _error_codes(frames: list[tuple[str, Any]]) -> list[Any]:
    return [data.get("code") for event, data in frames if event == "error"]


def test_an_empty_turn_says_the_model_failed_it(client: TestClient) -> None:  # noqa: F811
    frames = _frames(client, _SilentModel, "Create a Pipeline class.")
    assert turn_failures.MODEL_NO_OUTPUT in _error_codes(frames)
    assert "done" in [event for event, _ in frames], "the stream must still end"


def test_a_looping_model_is_named_through_the_stream(client: TestClient) -> None:  # noqa: F811
    """The loop guard's code survives the pipeline: dropping it there is what
    made a looping model read as a broken backend."""
    frames = _frames(client, _LoopingModel, "Show me the README.")
    assert turn_failures.AGENT_LOOP in _error_codes(frames), frames


# --------------------------------------------------------------------------- #
# The tester scores it as a failed turn and keeps measuring.
# --------------------------------------------------------------------------- #


class _Stream:
    def __init__(self, frames: list[tuple[str, dict[str, Any]]]) -> None:
        self.lines: list[str] = []
        for event, data in frames:
            self.lines += [f"event: {event}", f"data: {json.dumps(data)}", ""]

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self, decode_unicode: bool = True):
        return iter(self.lines)


class _Session:
    def __init__(self, frames: list[tuple[str, dict[str, Any]]]) -> None:
        self.frames = frames

    def post_stream(self, path: str, body: dict, timeout: float) -> _Stream:
        return _Stream(self.frames)


def _outcome(monkeypatch, error: dict[str, Any]) -> dict[str, Any]:
    session = _Session([("error", error), ("done", {})])
    monkeypatch.setattr(endurance_tester, "_session", lambda: session)
    return endurance_tester.run_prompt("p", "s")


@pytest.mark.parametrize("code", sorted(turn_failures.MODEL_FAILURE_CODES))
def test_a_coded_model_failure_is_a_failed_turn(monkeypatch, code: str) -> None:
    result = _outcome(monkeypatch, {"code": code, "text": "the model failed"})
    assert result["outcome"] == "model_failure"
    assert result["error"]["code"] == code, "why the turn failed must reach the log"


@pytest.mark.parametrize(
    "error",
    [
        {"text": "Internal error: boom"},
        {"code": "strategy_unavailable", "text": "not production-selected"},
    ],
)
def test_any_other_error_is_still_an_error(monkeypatch, error) -> None:
    """The control: only the model-failure codes are re-scored."""
    assert _outcome(monkeypatch, error)["outcome"] == "error"


def _run(monkeypatch, outcome: str, capsys) -> tuple[int, str]:
    """Drive cmd_run with every turn returning *outcome*; touch nothing real."""
    calls: list[str] = []

    def fake_prompt(prompt: str, session_id: str, model_id: str = "auto") -> dict:
        calls.append(session_id)
        return {"outcome": outcome, "error": {"code": "x", "text": "y"}}

    monkeypatch.setattr(endurance_tester, "run_prompt", fake_prompt)
    monkeypatch.setattr(endurance_tester, "reset_files", lambda files: None)
    monkeypatch.setattr(endurance_tester, "get_process_memory_mb", lambda: None)
    monkeypatch.setattr(endurance_tester, "log_event", lambda record: None)
    # A fake clock for the tester only: one tick per read, no real sleeping.
    clock = iter(range(0, 10_000))
    monkeypatch.setattr(
        endurance_tester,
        "time",
        SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda s: None),
    )
    args = argparse.Namespace(duration_minutes=1, cooldown_s=0, model="m")
    try:
        endurance_tester.cmd_run(args)
    except SystemExit:
        pass
    return len(calls), capsys.readouterr().out


def test_model_failures_never_abort_the_run(monkeypatch, capsys) -> None:
    turns, out = _run(monkeypatch, "model_failure", capsys)
    assert "ABORT" not in out, out[-400:]
    assert turns > 5, f"the run stopped after {turns} turns"


def test_five_real_errors_in_a_row_still_abort(monkeypatch, capsys) -> None:
    """The abort still guards the case it exists for: a broken backend."""
    turns, out = _run(monkeypatch, "error", capsys)
    assert "ABORT: 5 consecutive errors" in out
    assert turns == 5
