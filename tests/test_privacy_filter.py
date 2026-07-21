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
    blob = "plain text " * 60  # 660 chars, no secret patterns
    out, n = PrivacyFilter()._redact_file_content(blob)
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


def test_truncated_blob_scrubs_secrets_in_head() -> None:
    secret = "ghp_" + "b" * 36
    blob = f"config start\ntoken={secret}\n" + ("x " * 300)
    safe, audit = PrivacyFilter().filter([{"role": "tool", "content": blob}])
    content = safe[0]["content"]
    assert secret not in content
    assert "[...truncated...]" in content


def test_truncated_blob_scrubs_paths_in_head() -> None:
    blob = "output from /home/kumar/secret/project/data.csv\n" + ("data " * 200)
    safe, audit = PrivacyFilter().filter([{"role": "tool", "content": blob}])
    content = safe[0]["content"]
    assert "/home/kumar/secret/project/data.csv" not in content


class TestPathShapedTokensAreNotSecrets:
    """Egress fix 2026-07-07: sandbox/file paths must survive cloud egress.

    The entropy heuristic used to glue slash-separated path segments into one
    long "token" and redact it as [SENSITIVE: ...] -- blinding cloud models to
    the very filename they were asked to test (learning-loop prover runs
    20260707T035636/041713 recorded this live; the model echoed the redaction
    hash back as a filename). Scope: the PRIVACY egress filter only -- the
    security scanner's entropy backstop (which deliberately catches
    path-DISGUISED credentials) is contested-spec territory and is untouched.
    """

    def test_sandbox_path_survives_in_message_content(self) -> None:
        pf = PrivacyFilter()
        cmd = "run pytest training_ground/test_llp_buggy_20260707T035636.py -q"
        messages = [{"role": "user", "content": cmd}]
        safe, audit = pf.filter(messages)
        assert safe[0]["content"] == cmd
        assert audit["redacted_secrets"] == 0

    def test_deep_relative_path_is_never_secret_redacted(self) -> None:
        """Multi-slash paths may still hit the separate, intentional PATH
        redaction (machine-layout privacy) -- but never the SECRET one."""
        pf = PrivacyFilter()
        cmd = "open src/deeply/nested/module_with_a_rather_long_name.py"
        safe, audit = pf.filter([{"role": "user", "content": cmd}])
        assert audit["redacted_secrets"] == 0
        assert "[SENSITIVE" not in str(safe[0]["content"])

    def test_windows_separator_path_survives(self) -> None:
        pf = PrivacyFilter()
        cmd = r"run pytest training_ground\test_llp_reflex_20260707T035636.py"
        safe, _ = pf.filter([{"role": "user", "content": cmd}])
        assert safe[0]["content"] == cmd

    def test_base64_with_plus_still_redacts(self) -> None:
        pf = PrivacyFilter()
        secret = "ab12/cd34+ef56gh78ij90kl12mn34op56"
        safe, audit = pf.filter([{"role": "user", "content": f"token {secret} end"}])
        assert secret not in str(safe[0]["content"])

    def test_slashless_high_entropy_still_redacts(self) -> None:
        pf = PrivacyFilter()
        secret = "q7Zx9Kf2Lm8Rp4Tv6Wy1Bn3Cd5Gh0JkQ"
        safe, _ = pf.filter([{"role": "user", "content": f"key {secret} end"}])
        assert secret not in str(safe[0]["content"])

    def test_slash_shaped_aws_secret_key_still_redacts(self) -> None:
        """Regression for the 2026-07-07 exemption's own bypass (found 2026-07-10):
        a real AWS secret access key can be slash-shaped (base64 alphabet includes
        '/'), which used to fullmatch the path-shaped exemption and sail through
        both the credential-keyword pass and the entropy backstop with zero
        redactions. Must be caught via keyword context (aws_secret_access_key=)
        AND via bare shape alone (no keyword nearby)."""
        pf = PrivacyFilter()
        secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        with_keyword = f"aws_secret_access_key = {secret}"
        safe, audit = pf.filter([{"role": "user", "content": with_keyword}])
        assert secret not in str(safe[0]["content"])
        assert audit["redacted_credentials"] + audit["redacted_secrets"] > 0

        bare = f"here is the value: {secret}"
        safe2, audit2 = pf.filter([{"role": "user", "content": bare}])
        assert secret not in str(safe2[0]["content"])
        assert audit2["redacted_credentials"] + audit2["redacted_secrets"] > 0

    def test_slash_shaped_secret_still_redacts_when_not_exactly_40_chars(self) -> None:
        """Regression for the 2026-07-10 adversarial audit's own re-finding: the
        first fix only closed the literal 40-char AWS-key repro via a dedicated
        shape pattern. The root cause -- _in_filename_context's path-shape
        exemption having no plausibility check at all -- was untouched, so a
        differently-sized slash-bearing secret (a lopsided 43+4 char split, and
        a balanced 31+19 char split -- neither matching the 40-char pattern)
        still sailed through with zero redactions. Both are now caught by the
        per-segment length/case-transition check."""
        pf = PrivacyFilter()
        lopsided = "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEYAB12/34cD"
        safe, audit = pf.filter(
            [{"role": "user", "content": f"cloud key rejected: {lopsided} end"}]
        )
        assert lopsided not in str(safe[0]["content"])
        assert audit["redacted_credentials"] + audit["redacted_secrets"] > 0

        balanced = "sk9F2xQ7mZ4tY8bA1cD3eG6hJ0kL5nP/rS8uV2wX4yA6zB9cE1f"
        safe2, audit2 = pf.filter(
            [{"role": "user", "content": f"cloud provider returned {balanced} and closed"}]
        )
        assert balanced not in str(safe2[0]["content"])
        assert audit2["redacted_credentials"] + audit2["redacted_secrets"] > 0

    def test_short_no_digit_secret_still_redacts(self) -> None:
        """Regression: the old _looks_like_secret required len > 24 specifically
        for all-alphabetic (no-digit) strings, which a 22-char pure-alphabetic
        secret slipped under. Digit presence isn't a trustworthy signal (real
        secrets don't reliably contain digits), so the carve-out is gone."""
        pf = PrivacyFilter()
        secret = "qwertyuiopasdfghjklzxc"
        assert len(secret) == 22
        safe, audit = pf.filter([{"role": "user", "content": f"here is the key {secret} end"}])
        assert secret not in str(safe[0]["content"])
        assert audit["redacted_secrets"] > 0

    def test_pascal_case_and_camel_case_identifiers_are_not_false_positives(self) -> None:
        """The case-transition-ratio check must not flag normal camelCase/
        PascalCase code identifiers -- these have very few case transitions
        relative to real random-generated secrets, which transition on
        roughly every other character."""
        pf = PrivacyFilter()
        cases = [
            "open frontend/src/components/MyComponent.tsx for the bug",
            "check src/workbench/CodeEditor.jsx and superbrain/lib/cognitionBus.ts",
            "class MyClassName extends BaseComponent",
        ]
        for text in cases:
            safe, audit = pf.filter([{"role": "user", "content": text}])
            assert audit["redacted_secrets"] == 0, f"false positive on: {text!r}"

    def test_absolute_paths_still_redacted_as_paths(self) -> None:
        """The PATH redaction (absolute paths reveal machine layout) is separate
        and intentionally unchanged -- only the false SECRET classification of
        relative path tokens is fixed."""
        pf = PrivacyFilter()
        safe, _ = pf.filter(
            [{"role": "user", "content": r"see C:\Users\kumar\secret_project\notes.txt"}]
        )
        assert r"C:\Users\kumar" not in str(safe[0]["content"])
        assert "[PATH REDACTED]" in str(safe[0]["content"])
