"""GAGOS's brains on the operator's own plans, for the counter (2026-11-03).

The operator chose, for the counter where he talks to GAGOS: "connect codex
models to counter also and C" -- Claude through Claude Code on his Pro plan
(option C) and the GPT models through Codex on his OpenAI plan. No API key: the
two command-line tools he is signed in to are the transport.

One client, :class:`PlanCliClient`, behind one router provider (``plan``). A
``claude-*`` model goes to ``claude -p``, a ``gpt-*`` model to ``codex exec``,
each sealed as GAGOS's workshop already runs them: no tools of their own, no
session kept, none of his MCP servers or plugins, in an empty directory. What
leaves the machine passes the same :class:`PrivacyFilter` every cloud client
applies, and every call is recorded through :func:`model_calls.observe`.

The agent's tools are offered as text and answered through each tool's
structured output (``--json-schema`` / ``--output-schema``): the model fills
``content`` and, to act, ``tool_calls`` with each call's arguments as a JSON
string. Nothing the model asks for runs here; the agent loop and its gates
decide, as for every provider.

Not streamed: :meth:`PlanCliClient.stream_chat` yields the whole answer once.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, Sequence

from aios.application.models.privacy_audit import PrivacyAuditTracker
from aios.core import model_calls
from aios.core.llm import LLMError
from aios.core.privacy_filter import PrivacyFilter, scrub_exception

logger = logging.getLogger(__name__)

#: Codex features that let a session act, all switched off: it judges or
#: answers the text it is given, nothing more (Codex's review of #566: a
#: read-only sandbox still ran shell commands and his MCP servers).
CODEX_ACTING_FEATURES = (
    "shell_tool",
    "unified_exec",
    "unified_exec_tty",
    "apps",
    "plugins",
    "remote_plugin",
    "browser_use",
    "browser_use_external",
    "in_app_browser",
    "skill_search",
    "tool_suggest",
)

#: Claude Code, asked so it cannot act: one answer as JSON, no tools, nothing
#: remembered, no MCP servers. The counter's plan client and the workshop's
#: reviewer launch it with exactly these (2026-11-04: each wrote its own copy).
CLAUDE_SEALED: tuple[str, ...] = (
    "-p",
    "--output-format",
    "json",
    "--tools",
    "",
    "--no-session-persistence",
    "--strict-mcp-config",
)

#: Codex, asked so it cannot act: a read-only sandbox, nothing kept, none of the
#: operator's config or rules, every feature that acts turned off. Shared the
#: same way as :data:`CLAUDE_SEALED`.
CODEX_SEALED: tuple[str, ...] = (
    "exec",
    "-s",
    "read-only",
    "--skip-git-repo-check",
    "--ephemeral",
    "--ignore-user-config",
    "--ignore-rules",
    *(arg for feature in CODEX_ACTING_FEATURES for arg in ("--disable", feature)),
)

#: The answer every tool-offering call is held to: what to say, and the tools
#: to call with their arguments as a JSON object in a string (a free-form
#: object is not allowed by strict structured output).
TURN_SCHEMA = {
    "type": "object",
    "properties": {
        "content": {"type": "string"},
        "tool_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "arguments_json": {"type": "string"},
                },
                "required": ["name", "arguments_json"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["content", "tool_calls"],
    "additionalProperties": False,
}


def claude_executable() -> Optional[str]:
    """The real Claude Code binary, never an npm .cmd shim: cmd.exe would mangle
    a JSON schema argument."""
    found = shutil.which("claude")
    if found and found.lower().endswith((".cmd", ".bat")):
        native = (
            Path(found).parent
            / "node_modules"
            / "@anthropic-ai"
            / "claude-code"
            / "bin"
            / "claude.exe"
        )
        return str(native) if native.is_file() else None
    return found


def codex_executable() -> Optional[str]:
    """The real Codex binary; a .cmd or .bat shim is refused, as for Claude Code:
    cmd.exe would re-read its arguments."""
    found = shutil.which("codex")
    if found and found.lower().endswith((".cmd", ".bat")):
        return None
    return found


def family(model: str) -> str:
    """Which tool serves *model*: ``claude`` or ``codex``."""
    if model.startswith("claude-"):
        return "claude"
    if model.startswith("gpt-"):
        return "codex"
    raise LLMError(f"no plan serves the model '{model}'")


def _transcript(
    messages: Sequence[dict[str, Any]], tools: Optional[Sequence[dict[str, Any]]]
) -> tuple[str, str]:
    """``(system, prompt)``: the conversation as one prompt, the agent's tools
    described when offered."""
    system: list[str] = []
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role")
        content = str(msg.get("content") or "")
        if role == "system":
            if content.strip():
                system.append(content)
        elif role == "user":
            lines += ["### The operator", content, ""]
        elif role == "assistant":
            lines += ["### You (earlier)", content]
            for call in msg.get("tool_calls") or []:
                fn = call.get("function", {}) if isinstance(call, dict) else {}
                args = fn.get("arguments")
                if not isinstance(args, str):
                    args = json.dumps(args or {}, sort_keys=True)
                lines.append(f"[you called the tool {fn.get('name', '')} with {args}]")
            lines.append("")
        elif role == "tool":
            lines += ["### A tool's result", content, ""]
    if tools:
        lines += [
            "### Tools you may call",
            "To call a tool, list it in tool_calls with its arguments as one JSON "
            "object in arguments_json; leave tool_calls empty when you answer. "
            "Nothing runs until the system's own gates allow it.",
        ]
        for tool in tools:
            fn = tool.get("function", {}) if isinstance(tool, dict) else {}
            lines.append(
                f"- {fn.get('name', '')}: {fn.get('description', '')} "
                f"Parameters: {json.dumps(fn.get('parameters') or {}, sort_keys=True)}"
            )
        lines.append("")
    lines.append("### Your reply")
    return "\n\n".join(system), "\n".join(lines)


def _turn(answer: Any, tools: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The agent's message from a structured answer; a call to a tool not
    offered, or with arguments that are not a JSON object, is dropped."""
    if not isinstance(answer, dict):
        raise LLMError("the plan model gave no structured answer")
    offered = {
        str((t.get("function") or {}).get("name", ""))
        for t in tools
        if isinstance(t, dict)
    }
    calls = []
    for i, call in enumerate(answer.get("tool_calls") or []):
        if not isinstance(call, dict) or call.get("name") not in offered:
            continue
        try:
            args = json.loads(call.get("arguments_json") or "{}")
        except (ValueError, TypeError):  # not a JSON string: the call is dropped
            continue
        if isinstance(args, dict):
            calls.append(
                {
                    "id": f"plan_{i}",
                    "function": {"name": call["name"], "arguments": args},
                }
            )
    result: dict[str, Any] = {
        "role": "assistant",
        "content": str(answer.get("content") or ""),
    }
    if calls:
        result["tool_calls"] = calls
    if not result["content"] and not calls:
        raise LLMError("the plan model's answer was empty")
    return result


class PlanCliClient:
    """A chat client (``complete``/``chat``/``stream_chat``) over the operator's
    plans: Claude through Claude Code, GPT through Codex."""

    def __init__(
        self,
        *,
        claude_models: Sequence[str] = (),
        codex_models: Sequence[str] = (),
        timeout_s: float = 300,
        codex_effort: str = "medium",
        privacy_audit_tracker: Optional[PrivacyAuditTracker] = None,
        run: Callable[..., Any] = subprocess.run,
        claude: Optional[str] = None,
        codex: Optional[str] = None,
        identifiers_shown: bool = False,
    ) -> None:
        """*identifiers_shown*: GAGOS's workshop sending its own tracked code
        (the operator's decision of 2026-11-11; see :class:`PrivacyFilter`).
        The counter, which carries his words, keeps the full filter."""
        self.claude = claude if claude is not None else claude_executable()
        self.codex = codex if codex is not None else codex_executable()
        # A plan whose tool is not installed offers nothing.
        self.claude_models = tuple(claude_models) if self.claude else ()
        self.codex_models = tuple(codex_models) if self.codex else ()
        self.timeout_s = timeout_s
        self.codex_effort = codex_effort
        self._run = run
        self._privacy_filter = PrivacyFilter(identifiers_shown=identifiers_shown)
        self._privacy_audit_tracker = privacy_audit_tracker
        # The configured default, offered or not: a missing tool is said by
        # name when the model is asked for, not as an empty model (CI, 11-03).
        self.model = (tuple(claude_models) + tuple(codex_models) + ("",))[0]

    def models(self) -> tuple[str, ...]:
        return self.claude_models + self.codex_models

    # egress
    def _filtered_for_egress(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        safe, audit = self._privacy_filter.filter(messages)
        if any(v for k, v in audit.items() if k.startswith("redacted_") and v):
            logger.info("Plan privacy filter applied", extra=audit)
        if self._privacy_audit_tracker is not None:
            self._privacy_audit_tracker.record("plan", audit)
        return safe

    def _ask(self, model: str, system: str, prompt: str, schema: Optional[dict]) -> Any:
        if model not in self.models():
            if model.startswith("claude-") and not self.claude:
                raise LLMError("the Claude Code CLI is not installed here")
            if model.startswith("gpt-") and not self.codex:
                raise LLMError("the Codex CLI is not installed here")
            raise LLMError(f"the plan model '{model}' is not offered here")
        model_calls.observe("plan", model, "chat")
        with tempfile.TemporaryDirectory(prefix="gagos-plan-") as tmp:
            if family(model) == "claude":
                argv = [self.claude, *CLAUDE_SEALED, "--model", model]
                if system:
                    argv += ["--system-prompt", system]
                if schema:
                    argv += ["--json-schema", json.dumps(schema)]
                proc = self._call(argv, prompt, tmp)
                try:
                    data = json.loads(proc.stdout or "")
                except ValueError:
                    data = {}
                if proc.returncode != 0 or data.get("is_error"):
                    # Scrubbed whole, then shortened: a cut could split a secret.
                    said = scrub_exception(str(data.get("result") or proc.stderr or ""))
                    raise LLMError(
                        f"Claude Code exited {proc.returncode}: {said[-300:]}"
                    )
                return data.get("structured_output") if schema else data.get("result")
            out = Path(tmp, "answer.txt")
            argv = [
                self.codex,
                *CODEX_SEALED,
                "-o",
                str(out),
                "-m",
                model,
                "-c",
                f"model_reasoning_effort={self.codex_effort}",
            ]
            if schema:
                path = Path(tmp, "schema.json")
                path.write_text(json.dumps(schema), encoding="utf-8")
                argv += ["--output-schema", str(path)]
            text = f"{system}\n\n{prompt}" if system else prompt
            proc = self._call([*argv, "-"], text, tmp)
            answer = out.read_text(encoding="utf-8") if out.is_file() else ""
            if proc.returncode != 0 or not answer.strip():
                errors = [
                    line
                    for line in ((proc.stdout or "") + (proc.stderr or "")).splitlines()
                    if "ERROR" in line and "rmcp" not in line
                ]
                said = errors[-1] if errors else f"no answer (exit {proc.returncode})"
                raise LLMError(f"Codex: {scrub_exception(said)[:300]}")
            if not schema:
                return answer
            try:
                return json.loads(answer)
            except ValueError as exc:
                raise LLMError("Codex's answer is not the JSON asked for") from exc

    def _call(self, argv: list, text: str, cwd: str) -> Any:
        try:
            return self._run(
                argv,
                input=text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMError(
                f"the plan model timed out after {self.timeout_s:.0f}s"
            ) from exc
        except OSError as exc:
            raise LLMError(
                f"the plan tool could not run: {scrub_exception(exc)}"
            ) from exc

    # the chat-client contract
    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        """One prompt, sent as written (after the privacy filter): the
        workshop's writers use this, with their own answer format."""
        outbound = [{"role": "system", "content": system}] if system else []
        outbound.append({"role": "user", "content": prompt})
        safe = self._filtered_for_egress(outbound)
        sys_text = "\n\n".join(
            str(m["content"]) for m in safe if m["role"] == "system" and m["content"]
        )
        body = next(str(m["content"]) for m in safe if m["role"] == "user")
        answer = str(self._ask(self.model, sys_text, body, None) or "")
        if not answer.strip():
            raise LLMError("the plan model's answer was empty")
        return answer

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        del max_tokens  # the tools hold their own output bounds
        safe = self._filtered_for_egress(messages)
        sys_text, body = _transcript(safe, tools)
        chosen = model or self.model
        if tools:
            result = _turn(self._ask(chosen, sys_text, body, TURN_SCHEMA), tools)
        else:
            text = str(self._ask(chosen, sys_text, body, None) or "")
            if not text.strip():
                raise LLMError("the plan model's answer was empty")
            result = {"role": "assistant", "content": text}
        self._privacy_filter.validate_response(result)
        return result

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
    ) -> Iterator[str]:
        """Not streamed: the whole answer, once."""
        yield self.chat(messages, tools=tools, model=model)["content"]
