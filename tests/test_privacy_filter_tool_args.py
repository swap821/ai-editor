"""Redacting tool-call arguments must leave valid JSON behind.

`_redact_tool_call` took `str(dict)` -- a single-quoted Python repr -- and tried
to recover JSON with `args_str.replace("'", '"')`. That swaps EVERY single
quote, including the ones inside string values. Tool arguments carry code, and
code is full of them, so `print('hello')` corrupted the swap, `json.loads`
failed, and the except branch shipped the REPR STRING onward.

`_to_openai_messages` passes a str through untouched (it assumes a str is
already JSON), so the provider received single-quoted "JSON" and answered

    400 "Expected a valid JSON object in the request"

-- a message that names neither the tool call nor the filter. Measured on Vertex
MaaS; it applies to every OpenAI-compatible provider.
"""
from __future__ import annotations

import json

import pytest

from aios.core.privacy_filter import PrivacyFilter

BS = chr(92)


def _args_after_filter(arguments: dict) -> object:
    safe, _audit = PrivacyFilter().filter(
        [
            {"role": "user", "content": "go"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "c1", "function": {"name": "create_file", "arguments": arguments}}
                ],
            },
        ]
    )
    carrier = [m for m in safe if m.get("tool_calls")]
    assert carrier, "the assistant message with tool_calls was dropped entirely"
    return carrier[0]["tool_calls"][0]["function"]["arguments"]


@pytest.mark.parametrize(
    "content",
    [
        "print('hello')",
        "x = 'single' and " + chr(34) + "double" + chr(34),
        "p = 'C:" + BS + BS + "tmp'",
        "re.compile(r'" + BS + "d+')",
        "d = {'k': 'v'}",
        "",
    ],
    ids=["single-quotes", "mixed-quotes", "windows-path", "regex", "dict-literal", "empty"],
)
def test_arguments_survive_as_json(content: str) -> None:
    """The shapes an agent actually writes. Each one broke the quote swap."""
    args = _args_after_filter({"filepath": "training_ground/a.py", "content": content})

    assert isinstance(args, dict), (
        f"arguments came back as {type(args).__name__}; a str here is passed "
        "through to the provider verbatim and is not valid JSON"
    )
    json.dumps(args)  # must be serialisable


def test_redaction_still_happens() -> None:
    """The fix must not buy valid JSON by skipping the redaction."""
    args = _args_after_filter(
        {"filepath": "a.py", "content": "p = 'C:" + BS + BS + "secret" + BS + BS + "path'"}
    )

    assert "REDACTED" in json.dumps(args), "the path was not redacted"


def test_a_dict_is_never_replaced_by_a_repr_string() -> None:
    """The specific regression: the except branch used to emit str(dict)."""
    args = _args_after_filter({"filepath": "a.py", "content": "print('x')"})

    assert not isinstance(args, str), "arguments degraded to a string"
    text = json.dumps(args)
    assert not text.lstrip().startswith('"{'), "arguments were double-encoded"
