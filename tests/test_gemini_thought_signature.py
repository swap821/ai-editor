"""Gemini 3.x requires its thought_signature back; 2.5 never sends one.

A gemini-3.x model returns an opaque `thought_signature` on the part carrying a
`function_call`, and rejects the next request if that signature is not replayed
with the call in history:

    400 INVALID_ARGUMENT: Function call is missing a thought_signature in
    functionCall parts. This is required for tools to work correctly.

So the first tool call succeeds and the second request 400s. Every golden
mission on gemini-3.7-flash failed ~35s in with every step unverified, which
reads exactly like a weak model and is nothing of the kind.

The signature rides on the tool-call dict, which ToolAgent stores verbatim, so
it survives the round trip without the agent knowing it exists.
"""
from __future__ import annotations

import base64
import json
from types import SimpleNamespace

from aios.core.gemini import _to_gemini, _tool_call_from_part

SIG = b"opaque-thought-signature-bytes"
SIG_B64 = base64.b64encode(SIG).decode("ascii")


def _part(name: str, args: dict, signature: object | None):
    fc = SimpleNamespace(name=name, args=args)
    return SimpleNamespace(text=None, function_call=fc, thought_signature=signature), fc


def test_a_signature_is_captured_when_the_model_sends_one() -> None:
    part, fc = _part("read_file", {"filepath": "x.py"}, SIG)

    call = _tool_call_from_part(part, fc)

    assert call["function"]["name"] == "read_file"
    assert call["thought_signature"] == SIG_B64


def test_no_key_is_invented_when_the_model_sends_nothing() -> None:
    """2.5 has no such field; emitting an empty one would be a new 400."""
    part, fc = _part("read_file", {"filepath": "x.py"}, None)

    call = _tool_call_from_part(part, fc)

    assert "thought_signature" not in call


def test_the_signature_is_replayed_on_the_request() -> None:
    """The half that actually stops the 400."""
    messages = [
        {"role": "user", "content": "go"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": None,
                    "function": {"name": "read_file", "arguments": {"filepath": "x.py"}},
                    "thought_signature": SIG_B64,
                }
            ],
        },
    ]

    _system, contents = _to_gemini(messages)

    model_parts = [p for c in contents if c["role"] == "model" for p in c["parts"]]
    fc_parts = [p for p in model_parts if "function_call" in p]
    assert fc_parts, "the function call vanished from the replayed history"
    assert fc_parts[0].get("thought_signature") == SIG, (
        "thought_signature was dropped on replay; gemini-3.x answers that with "
        "400 INVALID_ARGUMENT and every tool-using turn dies"
    )


def test_a_call_without_a_signature_replays_without_the_field() -> None:
    """2.5-era history must not grow a field the API never gave us."""
    messages = [
        {"role": "user", "content": "go"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": None, "function": {"name": "read_file", "arguments": {}}}
            ],
        },
    ]

    _system, contents = _to_gemini(messages)

    fc_parts = [
        p for c in contents if c["role"] == "model" for p in c["parts"] if "function_call" in p
    ]
    assert fc_parts and "thought_signature" not in fc_parts[0]


def test_the_conversation_stays_json_serializable() -> None:
    """The signature arrives as bytes and the conversation is serialised.

    The first version of this fix stored the raw bytes the SDK returns. That
    removed the 400 and replaced it with

        TypeError: Object of type bytes is not JSON serializable

    which killed the turn just as dead -- the conversation is streamed, audited
    and persisted, so anything living in it must survive json.dumps.
    """
    part, fc = _part("read_file", {"filepath": "x.py"}, SIG)

    call = _tool_call_from_part(part, fc)

    json.dumps({"role": "assistant", "tool_calls": [call]})


def test_the_exact_bytes_reach_the_wire() -> None:
    """Base64 in the conversation is only useful if it decodes back exactly."""
    part, fc = _part("read_file", {"filepath": "x.py"}, SIG)
    call = _tool_call_from_part(part, fc)

    _system, contents = _to_gemini(
        [{"role": "user", "content": "go"},
         {"role": "assistant", "content": "", "tool_calls": [call]}]
    )

    fc_part = [
        p for c in contents if c["role"] == "model" for p in c["parts"] if "function_call" in p
    ][0]
    assert fc_part["thought_signature"] == SIG, "signature corrupted in transit"


def test_history_never_ends_on_a_model_turn() -> None:
    """Gemini 3.x: "Requests ending with a model turn are not supported."

    Reachable whenever a tool call is blocked or refused: the assistant message
    is appended without a matching tool result, so the next request ends on
    `model`. 2.5 accepted that; 3.x returns 400 and the turn dies.
    """
    _system, contents = _to_gemini(
        [
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "I will read the file."},
        ]
    )

    assert contents[-1]["role"] == "user", (
        "history ends on a model turn; gemini-3.x answers that with 400"
    )


def test_a_normal_history_is_not_padded() -> None:
    """The guard must not append to a conversation that already ends correctly."""
    _system, contents = _to_gemini(
        [{"role": "user", "content": "go"}]
    )

    assert len(contents) == 1 and contents[-1]["role"] == "user"
