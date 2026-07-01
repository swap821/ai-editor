"""Unit coverage for the PrivacyFilter class — the secret-redaction boundary that
sanitizes messages before they leave the machine for a cloud provider.

The module-level helpers were exercised indirectly (via the cloud clients), but the
filter ENGINE (per-role redaction, file-content stubbing, tool-call arg redaction,
history truncation, request/response validation) was unit-untested. These pin the
real redaction + validation behavior.
"""
from __future__ import annotations

import pytest

from aios.core.privacy_filter import PrivacyFilter

_GH_TOKEN = "ghp_" + "a" * 36  # matches the GitHub-token credential pattern


# ── filter(): per-role redaction ─────────────────────────────────────────────

def test_filter_redacts_credentials_in_user_message() -> None:
    safe, audit = PrivacyFilter().filter([{"role": "user", "content": f"key is {_GH_TOKEN} ok"}])
    assert _GH_TOKEN not in safe[0]["content"]
    assert audit["redacted_credentials"] >= 1


def test_filter_redacts_paths() -> None:
    safe, audit = PrivacyFilter().filter(
        [{"role": "user", "content": "open /home/kumar/secret/config.yaml now"}]
    )
    # The path is scrubbed — by the path redactor or the secret redactor (a long
    # path reads as high-entropy); either way the real path never leaves.
    assert "/home/kumar/secret/config.yaml" not in safe[0]["content"]
    assert audit["redacted_paths"] + audit["redacted_secrets"] >= 1


def test_filter_keeps_clean_system_message() -> None:
    safe, _ = PrivacyFilter().filter(
        [{"role": "system", "content": "You are a helpful assistant working here."}]
    )
    assert any(m["role"] == "system" for m in safe)  # survives (line 260-261)


def test_filter_redacts_string_tool_call_arguments() -> None:
    msg = {
        "role": "assistant",
        "content": "x",
        "tool_calls": [{"function": {"name": "r", "arguments": f"cmd={_GH_TOKEN}"}}],
    }
    safe, _ = PrivacyFilter().filter([msg])
    assert _GH_TOKEN not in str(safe[0]["tool_calls"])  # string-args branch


def test_validate_request_rejects_oversize_body() -> None:
    with pytest.raises(ValueError):
        PrivacyFilter(max_request_size=10)._validate_request(
            [{"role": "user", "content": "x" * 100}]
        )


def test_filter_redacts_tool_file_content() -> None:
    code = "import os\nimport sys\ndef f():\n    return 1\nclass A:\n    pass\n"
    safe, audit = PrivacyFilter().filter([{"role": "tool", "content": code}])
    assert "FILE CONTENT REDACTED" in safe[0]["content"]
    assert audit["redacted_tool_files"] >= 1


def test_filter_redacts_tool_call_arguments() -> None:
    msg = {
        "role": "assistant",
        "content": "running it",
        "tool_calls": [
            {"function": {"name": "run", "arguments": {"cmd": f"export T={_GH_TOKEN}"}}}
        ],
    }
    safe, _ = PrivacyFilter().filter([msg])
    assert _GH_TOKEN not in str(safe[0]["tool_calls"])


def test_filter_drops_unknown_role() -> None:
    safe, audit = PrivacyFilter().filter(
        [{"role": "weird", "content": "x"}, {"role": "user", "content": "hello there friend"}]
    )
    assert all(m["role"] != "weird" for m in safe)
    assert audit["dropped_messages"] >= 1


def test_filter_drops_empty_system_message() -> None:
    safe, _ = PrivacyFilter().filter(
        [{"role": "system", "content": ""}, {"role": "user", "content": "hello there now"}]
    )
    assert all(m["role"] != "system" for m in safe)


def test_filter_truncates_old_history() -> None:
    msgs = []
    for i in range(6):
        msgs.append({"role": "user", "content": f"user message {i} here now"})
        msgs.append({"role": "assistant", "content": f"assistant reply {i} ok now"})
    safe, audit = PrivacyFilter(history_window=1).filter(msgs)
    assert audit["truncated_history"] > 0
    assert len(safe) < len(msgs)


def test_history_window_has_floor_and_coding_can_keep_more_turns() -> None:
    general = PrivacyFilter(history_window=1, coding_history_window=5, task="general")
    coding = PrivacyFilter(history_window=1, coding_history_window=5, task="coding")
    assert general.history_window == 2
    assert coding.history_window == 5


# ── validate_response() ──────────────────────────────────────────────────────

def test_validate_response_accepts_valid() -> None:
    resp = {"role": "assistant", "content": "hi", "tool_calls": [{"function": {"arguments": {"a": 1}}}]}
    assert PrivacyFilter().validate_response(resp) is resp


def test_validate_response_rejects_non_dict() -> None:
    with pytest.raises(ValueError):
        PrivacyFilter().validate_response(["not a dict"])  # type: ignore[arg-type]


def test_validate_response_rejects_oversize() -> None:
    with pytest.raises(ValueError):
        PrivacyFilter(max_response_size=10).validate_response({"role": "assistant", "content": "x" * 100})


def test_validate_response_rejects_bad_role_and_content_and_tool_calls() -> None:
    pf = PrivacyFilter()
    with pytest.raises(ValueError):
        pf.validate_response({"role": "hacker", "content": "x"})
    with pytest.raises(ValueError):
        pf.validate_response({"role": "assistant", "content": 123})
    with pytest.raises(ValueError):
        pf.validate_response({"role": "assistant", "content": "x", "tool_calls": "nope"})
    with pytest.raises(ValueError):
        pf.validate_response({"role": "assistant", "content": "x", "tool_calls": ["not a dict"]})
    with pytest.raises(ValueError):
        pf.validate_response({"role": "assistant", "content": "x", "tool_calls": [{"function": "x"}]})
    with pytest.raises(ValueError):
        pf.validate_response({"role": "assistant", "content": "x", "tool_calls": [{"function": {"arguments": 1}}]})


# ── _validate_request() raise paths ──────────────────────────────────────────

def test_validate_request_rejects_too_many_messages() -> None:
    pf = PrivacyFilter(max_messages=2)
    with pytest.raises(ValueError):
        pf._validate_request([{"role": "user", "content": "a"}] * 3)


def test_validate_request_rejects_bad_role_and_missing_content() -> None:
    pf = PrivacyFilter()
    with pytest.raises(ValueError):
        pf._validate_request([{"role": "bad", "content": "a"}])
    with pytest.raises(ValueError):
        pf._validate_request([{"role": "user"}])  # missing content (non-assistant)


# ── _redact_file_content() ───────────────────────────────────────────────────

def test_redact_file_content_stubs_code() -> None:
    code = "import os\nx = 1\ny = 2\nz = 3\nw = 4\n"
    out, n = PrivacyFilter()._redact_file_content(code)
    assert "FILE CONTENT REDACTED" in out and n == 1


def test_redact_file_content_extracts_filename_hint() -> None:
    code = "# see config.yaml\nimport os\ndef f():\n    pass\nclass C:\n    pass\n"
    out, _ = PrivacyFilter()._redact_file_content(code)
    assert "config.yaml" in out


def test_redact_file_content_truncates_large_blob() -> None:
    out, n = PrivacyFilter()._redact_file_content("A" * 600)
    assert out.startswith("A" * 500)
    assert out.endswith("[...truncated...]")
    assert n == 1


def test_filter_truncates_large_multiline_non_code_tool_blob() -> None:
    line = "plain words repeated for safe context " * 4
    blob = "\n".join(f"line {i} {line}" for i in range(12))
    safe, audit = PrivacyFilter().filter([{"role": "tool", "content": blob}])
    content = safe[0]["content"]
    assert "[...truncated...]" in content
    assert "line 11" not in content
    assert audit["redacted_tool_files"] == 1


def test_redact_file_content_leaves_short_text() -> None:
    out, n = PrivacyFilter()._redact_file_content("just a short normal note")
    assert out == "just a short normal note" and n == 0
