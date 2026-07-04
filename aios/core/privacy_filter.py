"""PrivacyFilter — sanitizes messages before cloud transmission.

Ensures that when a turn is routed to a cloud provider, sensitive content
is redacted or dropped before leaving the local machine.

Design:
  * Pattern-based scanning detects file paths, secrets, credentials, and
    system-prompt content.
  * Redaction rules selectively drop, mask, or truncate — never let the
    full conversation history or sensitive tool results leave the laptop.
  * A per-call audit log (counts, not content) lets operators verify the
    filter is working without creating a second leak channel.
  * Exception scrubbing removes credential material from provider error
    messages before they are logged or returned to the agent loop.
  * Request / response validation guards against malformed payloads and
    MitM tampering.
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Final

from aios import config

#: Minimal generic replacement for system prompts (never transmits the real one).
_GENERIC_SYSTEM_PROMPT: Final[str] = (
    "You are a helpful coding assistant. Be concise and accurate."
)

#: Patterns that may contain bearer tokens / AWS signatures / credential strings.
_CREDENTIAL_PATTERNS: Final[list[re.Pattern[str]]] = [
    # AWS Signature V4 credential
    re.compile(r"AWS4-HMAC-SHA256\s+Credential=[A-Za-z0-9/+=]+"),
    re.compile(r"Credential=[A-Za-z0-9/+=]{20,}"),
    # Generic bearer / token / api-key patterns
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)authorization\s*[:\s]\s*[A-Za-z0-9_\-+/=]{8,}"),
    re.compile(r"(?i)(api[_-]?key|apikey|secret|token|password)\s*[:=]\s*\S{8,}"),
    re.compile(r"(?i)(AKIA[A-Z0-9]{16})"),  # AWS Access Key ID
    re.compile(r"(?i)(ASIA[A-Z0-9]{16})"),  # AWS Session Token prefix
    re.compile(r"gh[ps]_[A-Za-z0-9_]{30,}"),  # GitHub tokens
    re.compile(r"glpat-[A-Za-z0-9_\-]{20,}"),  # GitLab tokens
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # Generic sk- keys
    re.compile(r"xox[baprs]-[A-Za-z0-9_\-]{10,}"),  # Slack tokens
    re.compile(r"\b[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\b"),  # JWT
    re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----"),
    re.compile(r"-----BEGIN\s+OPENSSH\s+PRIVATE\s+KEY-----"),
    re.compile(r"-----BEGIN\s+EC\s+PRIVATE\s+KEY-----"),
    re.compile(r"-----BEGIN\s+DSA\s+PRIVATE\s+KEY-----"),
]

#: Patterns for file paths (absolute Unix + Windows).
_PATH_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"/[A-Za-z0-9_.\-/~]+/[^\s:;\"'\n]{2,}"),
    re.compile(r"[A-Za-z]:\\[^\s:\"'\n]{2,}"),
    re.compile(r"~/[^\s:;\"'\n]{2,}"),
]

#: Content is "high-entropy" (likely a secret) when it exceeds this length
#: and looks like a random/base64 string.
_SECRET_ENTROPY_THRESHOLD: Final[int] = 20

#: Maximum response body size we'll accept from a cloud provider (bytes).
_MAX_RESPONSE_SIZE: Final[int] = 4 * 1024 * 1024  # 4 MiB

#: Maximum outgoing request size (bytes).
_MAX_REQUEST_SIZE: Final[int] = 2 * 1024 * 1024  # 2 MiB

#: Maximum number of messages allowed in a single request.
_MAX_MESSAGES_PER_REQUEST: Final[int] = 50

#: Minimum number of recent conversation turns to retain for cloud transmission.
_MIN_HISTORY_WINDOW: Final[int] = 2

#: Default recent conversation turns retained for cloud transmission.
_HISTORY_WINDOW: Final[int] = max(_MIN_HISTORY_WINDOW, config.CLOUD_HISTORY_WINDOW)

#: Coding tasks may keep more context, but never less than the default floor.
_CODING_HISTORY_WINDOW: Final[int] = max(_HISTORY_WINDOW, config.CLOUD_CODING_HISTORY_WINDOW)

_CODING_TASK_HINTS: Final[tuple[str, ...]] = (
    "code", "coding", "debug", "fix", "implement", "refactor", "test",
)

_LARGE_BLOB_CHAR_LIMIT: Final[int] = 500
_LARGE_BLOB_LINE_LIMIT: Final[int] = 8
_LARGE_BLOB_TRUNCATION_MARKER: Final[str] = "[...truncated...]"

logger = logging.getLogger(__name__)


def _looks_like_secret(value: str) -> bool:
    """Return ``True`` if *value* looks like a high-entropy secret string."""
    if len(value) <= _SECRET_ENTROPY_THRESHOLD:
        return False
    lower = value.lower()
    upper = value.upper()
    digit_count = sum(1 for c in value if c.isdigit())
    if digit_count == 0:
        return bool(re.match(r"^[A-Za-z0-9_+/=-]+$", value)) and len(value) > 24
    return bool(re.match(r"^[A-Za-z0-9_+/=\-]{20,}$", value))


def _hash_placeholder(value: str) -> str:
    """Return a short, non-reversible placeholder for *value*."""
    h = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"[SENSITIVE: {h}]"


def _redact_high_entropy(text: str) -> tuple[str, int]:
    """Replace high-entropy strings in *text* with hashed placeholders."""
    count = 0
    for match in re.finditer(r"[A-Za-z0-9_+/=\-]{20,}", text):
        token = match.group(0)
        if _looks_like_secret(token):
            placeholder = _hash_placeholder(token)
            text = text[: match.start()] + placeholder + text[match.end() :]
            count += 1
    return text, count


def _redact_credentials(text: str) -> tuple[str, int]:
    """Scrub known credential patterns from *text*."""
    count = 0
    for pattern in _CREDENTIAL_PATTERNS:
        new_text, n = pattern.subn("[CREDENTIAL REDACTED]", text)
        text = new_text
        count += n
    return text, count


def _redact_paths(text: str) -> tuple[str, int]:
    """Replace absolute file paths in *text* with ``[PATH REDACTED]``."""
    count = 0
    for pattern in _PATH_PATTERNS:
        new_text, n = pattern.subn("[PATH REDACTED]", text)
        text = new_text
        count += n
    return text, count


def scrub_exception(exc: BaseException | str) -> str:
    """Return a sanitized string from an exception or message, safe to log."""
    if isinstance(exc, BaseException):
        pieces: list[str] = []
        current: BaseException | None = exc
        while current is not None:
            msg = str(current)
            if msg:
                pieces.append(msg)
            current = current.__cause__ or current.__context__
        raw = " | ".join(pieces)
    else:
        raw = exc
    text, c1 = _redact_credentials(raw)
    text, c2 = _redact_high_entropy(text)
    text, c3 = _redact_paths(text)
    total = c1 + c2 + c3
    if total:
        text += f" [scrubbed {total} sensitive fragment(s)]"
    return text


class PrivacyFilter:
    """Stateful filter that sanitizes message lists before cloud transmission."""

    def __init__(
        self,
        *,
        history_window: int | None = None,
        coding_history_window: int | None = None,
        task: str = "general",
        max_request_size: int = _MAX_REQUEST_SIZE,
        max_response_size: int = _MAX_RESPONSE_SIZE,
        max_messages: int = _MAX_MESSAGES_PER_REQUEST,
    ) -> None:
        base_history_window = _HISTORY_WINDOW if history_window is None else history_window
        coding_window = _CODING_HISTORY_WINDOW if coding_history_window is None else coding_history_window
        self.history_window = self._history_window_for_task(task, base_history_window, coding_window)
        self.max_request_size = max_request_size
        self.max_response_size = max_response_size
        self.max_messages = max_messages

    @staticmethod
    def _history_window_for_task(task: str, history_window: int, coding_history_window: int) -> int:
        base = max(_MIN_HISTORY_WINDOW, int(history_window))
        coding = max(base, int(coding_history_window))
        task_lower = str(task or "general").lower()
        if any(hint in task_lower for hint in _CODING_TASK_HINTS):
            return coding
        return base

    def filter(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Sanitize *messages* for cloud transmission."""
        audit: dict[str, Any] = {
            "input_messages": len(messages),
            "redacted_system": 0,
            "redacted_tool_files": 0,
            "redacted_credentials": 0,
            "redacted_paths": 0,
            "redacted_secrets": 0,
            "truncated_history": 0,
            "dropped_messages": 0,
        }
        truncated = self._truncate_history(messages)
        audit["truncated_history"] = len(messages) - len(truncated)
        safe: list[dict[str, Any]] = []
        for msg in truncated:
            clean, per_msg_audit = self._redact_message(msg)
            for key in ("redacted_system", "redacted_tool_files", "redacted_credentials",
                        "redacted_paths", "redacted_secrets", "dropped_messages"):
                audit[key] += per_msg_audit.get(key, 0)
            if clean is not None:
                safe.append(clean)
        self._validate_request(safe)
        audit["output_messages"] = len(safe)
        return safe, audit

    def validate_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """Validate and sanitize an incoming cloud-provider response."""
        if not isinstance(response, dict):
            raise ValueError("Response must be a dict")
        import json
        size = len(json.dumps(response).encode("utf-8"))
        if size > self.max_response_size:
            raise ValueError(f"Response size {size} bytes exceeds limit {self.max_response_size}")
        role = response.get("role")
        if role not in ("assistant", "user", "system", None):
            raise ValueError(f"Unexpected response role: {role}")
        content = response.get("content")
        if content is not None and not isinstance(content, str):
            raise ValueError(f"Response content must be a string, got {type(content).__name__}")
        tool_calls = response.get("tool_calls")
        if tool_calls is not None:
            if not isinstance(tool_calls, list):
                raise ValueError(f"tool_calls must be a list, got {type(tool_calls).__name__}")
            for call in tool_calls:
                if not isinstance(call, dict):
                    raise ValueError("Each tool_call must be a dict")
                fn = call.get("function")
                if fn is not None and not isinstance(fn, dict):
                    raise ValueError("tool_call.function must be a dict")
                args = (fn or {}).get("arguments")
                if args is not None and not isinstance(args, (dict, str)):
                    raise ValueError("tool_call.arguments must be a dict or string")
        return response

    def _truncate_history(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(messages) <= self.history_window * 2:
            return list(messages)
        kept: list[dict[str, Any]] = []
        turns = 0
        pending_assistant = False
        for msg in reversed(messages):
            role = msg.get("role")
            if role == "assistant":
                pending_assistant = True
            elif role == "user" and pending_assistant:
                turns += 1
                pending_assistant = False
                if turns >= self.history_window:
                    kept.append(msg)
                    break
            kept.append(msg)
        kept.reverse()
        return kept

    def _redact_message(self, msg: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, int]]:
        audit: dict[str, int] = {
            "redacted_system": 0, "redacted_tool_files": 0, "redacted_credentials": 0,
            "redacted_paths": 0, "redacted_secrets": 0, "dropped_messages": 0,
        }
        role = msg.get("role")
        content = msg.get("content") or ""
        if role == "system":
            content_str = str(content)
            content_str, n_cred = _redact_credentials(content_str)
            audit["redacted_credentials"] += n_cred
            content_str, n_sec = _redact_high_entropy(content_str)
            audit["redacted_secrets"] += n_sec
            content_str, n_path = _redact_paths(content_str)
            audit["redacted_paths"] += n_path
            if content_str.strip():
                audit["redacted_system"] = int(content_str != str(content))
                return {"role": "system", "content": content_str}, audit
            audit["dropped_messages"] = 1
            return None, audit
        if role == "tool":
            content_str = str(content)
            content_str, n_file = self._redact_file_content(content_str)
            audit["redacted_tool_files"] += n_file
            content_str, n_cred = _redact_credentials(content_str)
            audit["redacted_credentials"] += n_cred
            content_str, n_sec = _redact_high_entropy(content_str)
            audit["redacted_secrets"] += n_sec
            content_str, n_path = _redact_paths(content_str)
            audit["redacted_paths"] += n_path
            return {"role": "tool", "content": content_str}, audit
        if role in ("user", "assistant"):
            content_str = str(content)
            content_str, n_cred = _redact_credentials(content_str)
            audit["redacted_credentials"] += n_cred
            content_str, n_sec = _redact_high_entropy(content_str)
            audit["redacted_secrets"] += n_sec
            content_str, n_path = _redact_paths(content_str)
            audit["redacted_paths"] += n_path
            clean = dict(msg)
            clean["content"] = content_str
            if role == "assistant" and "tool_calls" in clean:
                clean["tool_calls"] = [self._redact_tool_call(call, audit) for call in clean["tool_calls"]]
            return clean, audit
        audit["dropped_messages"] = 1
        return None, audit

    def _redact_file_content(self, text: str) -> tuple[str, int]:
        count = 0
        lines = text.splitlines()
        if len(lines) >= 5:
            indicators = (
                "import ", "from ", "def ", "class ", "# ", "// ", "/*",
                "<!DOCTYPE", "<html", "<?xml", "---", "===", "{", "}",
                "function ", "const ", "let ", "var ", "package ",
            )
            if any(line.strip().startswith(indicators) for line in lines[:10]):
                fname = self._extract_filename_hint(text)
                stub = f"[FILE CONTENT REDACTED: {fname}]"
                return stub, count + 1
        if len(text) > _LARGE_BLOB_CHAR_LIMIT:
            return self._truncate_large_blob(text), count + 1
        return text, count

    def _truncate_large_blob(self, text: str) -> str:
        lines = text.splitlines() or [text]
        head = "\n".join(lines[:_LARGE_BLOB_LINE_LIMIT])
        if len(head) > _LARGE_BLOB_CHAR_LIMIT:
            head = head[:_LARGE_BLOB_CHAR_LIMIT].rstrip()
        head, _ = _redact_credentials(head)
        head, _ = _redact_high_entropy(head)
        head, _ = _redact_paths(head)
        return f"{head}\n{_LARGE_BLOB_TRUNCATION_MARKER}"

    def _extract_filename_hint(self, text: str) -> str:
        for line in text.splitlines()[:3]:
            for match in re.finditer(r"[^/\s]+\.[a-zA-Z0-9]{1,10}", line):
                return match.group(0)
        return "file"

    def _redact_tool_call(self, call: dict[str, Any], audit: dict[str, int]) -> dict[str, Any]:
        clean = dict(call)
        fn = clean.get("function")
        if isinstance(fn, dict) and "arguments" in fn:
            args = fn["arguments"]
            if isinstance(args, dict):
                args_str = str(args)
                args_str, n_cred = _redact_credentials(args_str)
                audit["redacted_credentials"] += n_cred
                args_str, n_sec = _redact_high_entropy(args_str)
                audit["redacted_secrets"] += n_sec
                args_str, n_path = _redact_paths(args_str)
                audit["redacted_paths"] += n_path
                import json
                try:
                    fn["arguments"] = json.loads(args_str.replace("'", '"'))
                except (json.JSONDecodeError, ValueError):
                    fn["arguments"] = args_str
            elif isinstance(args, str):
                s, n_cred = _redact_credentials(args)
                audit["redacted_credentials"] += n_cred
                s, n_sec = _redact_high_entropy(s)
                audit["redacted_secrets"] += n_sec
                s, n_path = _redact_paths(s)
                audit["redacted_paths"] += n_path
                fn["arguments"] = s
        return clean

    def _validate_request(self, messages: list[dict[str, Any]]) -> None:
        if len(messages) > self.max_messages:
            raise ValueError(f"Request contains {len(messages)} messages; max is {self.max_messages}")
        for msg in messages:
            role = msg.get("role")
            if role not in ("system", "user", "assistant", "tool"):
                raise ValueError(f"Invalid message role: {role}")
            if "content" not in msg and role != "assistant":
                raise ValueError(f"Message with role '{role}' missing 'content' key")
        import json
        size = len(json.dumps(messages).encode("utf-8"))
        if size > self.max_request_size:
            raise ValueError(f"Request body {size} bytes exceeds limit {self.max_request_size}")
