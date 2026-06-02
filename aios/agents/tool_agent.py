"""Agentic tool loop — lets the chat actually act, under the security gateway.

The agent runs a bounded reason -> act -> observe loop on the local model via
Ollama's function-calling chat API. Each turn the model may call a tool; the
agent executes it through the same security-gated, audited subsystems the rest
of the OS uses, feeds the (secret-scrubbed) result back, and loops until the
model produces a final answer or a step cap is reached.

Tools exposed to the model:

  * ``read_file``        — read a project file. Reads are GREEN/safe, but the
    path is canonicalised and must stay within the project root (no traversal,
    no symlink escape), and content is secret-scrubbed before the model sees it.
  * ``read_directory``   — list a project directory (same scope rule).
  * ``execute_terminal`` — run a shell command through the gateway + sandbox
    :class:`~aios.core.executor.Executor`. RED is blocked and YELLOW is reported
    as needing human approval; only GREEN actually runs. The agent never
    auto-runs a non-GREEN command.

The agent is transport-agnostic: :meth:`ToolAgent.run` *yields* plain event
dicts so the API layer can forward them as SSE and tests can assert on them
without HTTP. The chat client and executor are injected, so tests drive the full
loop with a scripted fake and touch neither Ollama nor a shell.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Iterator, Optional, Protocol, Any, cast

from aios import config
from aios.core.executor import Executor
from aios.core.llm import LLMError
from aios.security.secret_scanner import scan_and_redact

#: A reflection hook: given (command, error_output), record a lesson and return
#: a summary dict (``error_type``/``lesson_text``/``recurrence``/``mistake_id``),
#: or ``None`` if nothing was recorded. Lets the agent stay decoupled from the
#: reflection agent + Mistake DB.
FailureHook = Callable[[str, str], Optional[dict[str, Any]]]

#: A confirmation hook: given a lesson's mistake id, promote it pending->verified.
#: Called when a command succeeds after an earlier failure in the same task —
#: evidence the recorded lesson proved itself (blueprint Q6).
ConfirmHook = Callable[[int], None]

#: Max reason -> act turns before the loop stops for safety.
DEFAULT_MAX_ITERS = 5
#: Cap on tool output fed back to the model (keeps context small on local models).
_TOOL_RESULT_LIMIT = 4000
#: Cap on a single file read.
_FILE_READ_LIMIT = 20_000
#: Cap on the step-preview surfaced to the UI.
_PREVIEW_LIMIT = 400

#: First fenced code block in a final answer -> (language, code).
_CODE_FENCE = re.compile(r"```([a-zA-Z0-9_+-]*)\s*\n(.*?)```", re.DOTALL)

SYSTEM_PROMPT = (
    "You are a local coding agent embedded in an IDE workspace. You can call "
    "tools to inspect files and run commands before you answer. Prefer reading "
    "files and directories over guessing. When you have enough information, give "
    "a concise final answer. If you produce code, put it in a single fenced "
    "block with a language tag (```html ... ```), with no prose inside the fence."
)

#: OpenAI-style function tool specs advertised to the model.
TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the full text of a file inside the project so you can "
                "analyse it before answering or editing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Project-relative path of the file to read.",
                    }
                },
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_directory",
            "description": (
                "List the files and folders in a project directory before "
                "reading or creating files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Project-relative directory to list.",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_terminal",
            "description": (
                "Run a shell command in the sandboxed workspace (builds, tests, "
                "file setup). Destructive or out-of-scope commands are blocked "
                "automatically; package installs and git ops need human approval."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to run.",
                    }
                },
                "required": ["command"],
            },
        },
    },
]


class ChatClient(Protocol):
    """Anything that can run one tool-aware chat turn (see ``OllamaClient.chat``)."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        ...


def _coerce_args(raw: object) -> dict[str, Any]:
    """Normalise a tool-call ``arguments`` value (dict or JSON string) to a dict."""
    if isinstance(raw, dict):
        return cast(dict[str, Any], raw)
    if not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return cast(dict[str, Any], parsed) if isinstance(parsed, dict) else {}


def _resolve_within(root: Path, candidate: str) -> Optional[Path]:
    """Canonicalise *candidate* under *root*; return it only if it stays inside.

    Defeats ``../`` traversal, absolute paths, and symlink escape via
    :meth:`pathlib.Path.resolve`. Fail-closed: any error yields ``None``.
    """
    if not candidate:
        return None
    try:
        resolved = (root / candidate).resolve()
    except Exception:  # noqa: BLE001 - fail-closed on any resolution error
        return None
    if resolved == root:
        return resolved
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


class ToolAgent:
    """Bounded, security-gated reason -> act -> observe loop over a local model."""

    def __init__(
        self,
        llm: ChatClient,
        executor: Executor,
        *,
        model: Optional[str] = None,
        max_iters: int = DEFAULT_MAX_ITERS,
        read_root: Optional[Path] = None,
        session_id: Optional[str] = None,
        memory_context: Optional[str] = None,
        on_failure: Optional[FailureHook] = None,
        confirm_lesson: Optional[ConfirmHook] = None,
    ) -> None:
        self.llm = llm
        self.executor = executor
        self.model = model
        self.max_iters = max_iters
        #: Reads are confined to this tree (the project). Writes/exec remain
        #: confined to the executor's own (tighter) sandbox scope roots.
        self.read_root = (read_root or config.PROJECT_ROOT).resolve()
        self.session_id = session_id
        #: Optional recalled-memory block injected into the system prompt
        #: (blueprint stage 4 — the agent reasons with relevant past knowledge).
        self.memory_context = memory_context
        #: Optional reflection hook fired when a command genuinely fails (not when
        #: it is merely blocked by the gateway) — blueprint stage 9.
        self.on_failure = on_failure
        #: Optional confirmation hook: promotes a pending lesson to verified once
        #: a later command succeeds within the same task (blueprint Q6).
        self.confirm_lesson = confirm_lesson

    def run(self, messages: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        """Drive the loop, yielding event dicts the API maps to SSE.

        Event types: ``tool_call``, ``tool_result``, ``tool_blocked``, ``text``,
        ``code``, ``done``, ``error``.
        """
        system = SYSTEM_PROMPT
        if self.memory_context:
            system = f"{SYSTEM_PROMPT}\n\n{self.memory_context}"
        convo: list[dict[str, Any]] = [{"role": "system", "content": system}]
        convo.extend(messages)

        #: Lesson ids recorded from failures this task, awaiting a success to
        #: confirm them (blueprint Q6: a lesson is verified once a later command
        #: succeeds, showing the fix was applied).
        pending_lessons: list[int] = []

        for _ in range(self.max_iters):
            try:
                msg: dict[str, Any] = self.llm.chat(convo, tools=TOOL_SPECS, model=self.model)
            except LLMError as exc:
                yield {"type": "error", "text": f"Local inference error: {exc}"}
                return
            tool_calls: list[dict[str, Any]] = msg.get("tool_calls") or []
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.get("content", "")}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            convo.append(assistant_msg)

            if not tool_calls:
                yield from self._finish(str(msg.get("content", "")))
                return

            for index, call in enumerate(tool_calls):
                function = cast(dict[str, Any], call.get("function", {}))
                name = str(function.get("name", ""))
                args: dict[str, Any] = _coerce_args(function.get("arguments"))
                call_id = f"{name}-{index}"

                yield {"type": "tool_call", "tool": name, "input": args, "id": call_id}
                output, status, failed = self._dispatch(name, args)
                if status == "blocked":
                    yield {
                        "type": "tool_blocked",
                        "tool": name,
                        "reason": output[:_PREVIEW_LIMIT],
                        "id": call_id,
                    }
                else:
                    yield {
                        "type": "tool_result",
                        "tool": name,
                        "output": output[:_PREVIEW_LIMIT],
                        "id": call_id,
                    }
                convo.append({"role": "tool", "content": output[:_TOOL_RESULT_LIMIT]})

                if name == "execute_terminal":
                    if failed and self.on_failure is not None:
                        # Self-correction (blueprint stage 9): a genuine command
                        # failure becomes a structured lesson. Security blocks are
                        # correct behaviour, not mistakes, so they never reflect.
                        yield from self._reflect(
                            args.get("command", ""), output, index, pending_lessons
                        )
                    elif not failed and status == "ok" and pending_lessons:
                        # A command succeeded after an earlier failure this task:
                        # the recorded lesson(s) proved themselves (blueprint Q6).
                        yield from self._confirm(pending_lessons, index)

        # Step cap reached without a final answer.
        yield {"type": "text", "text": "Reached the step limit and stopped for safety."}
        yield {"type": "done"}

    def _reflect(
        self,
        command: str,
        error_output: str,
        index: int,
        pending_lessons: list[int],
    ) -> Iterator[dict[str, Any]]:
        """Run the failure hook, track the lesson id, and surface it as a step."""
        try:
            lesson = self.on_failure(command, error_output)  # type: ignore[misc]
        except Exception:  # noqa: BLE001 - reflection must never break the loop
            lesson = None
        if not lesson:
            return
        mistake_id = lesson.get("mistake_id")
        if isinstance(mistake_id, int):
            pending_lessons.append(mistake_id)
        summary = f"{lesson.get('error_type', 'Error')}: {lesson.get('lesson_text', '')}".strip()
        if lesson.get("recurrence"):
            summary = f"(recurring) {summary}"
        yield {
            "type": "tool_result",
            "tool": "reflect",
            "output": summary[:_PREVIEW_LIMIT],
            "id": f"reflect-{index}",
        }

    def _confirm(
        self, pending_lessons: list[int], index: int
    ) -> Iterator[dict[str, Any]]:
        """Promote pending lessons to verified after a corrective success."""
        promoted = list(pending_lessons)
        pending_lessons.clear()
        if self.confirm_lesson is None:
            return
        for mistake_id in promoted:
            try:
                self.confirm_lesson(mistake_id)
            except Exception:  # noqa: BLE001 - confirmation must never break the loop
                pass
        yield {
            "type": "tool_result",
            "tool": "reflect",
            "output": f"Verified {len(promoted)} earlier lesson(s) — the fix worked.",
            "id": f"verify-{index}",
        }

    # ----------------------------------------------------------------- finish
    def _finish(self, content: str) -> Iterator[dict[str, Any]]:
        """Stream a final answer word-by-word, then surface any code block."""
        text = content.strip() or "(no answer)"
        for word in re.findall(r"\S+\s*", text):
            yield {"type": "text", "text": word}
        match = _CODE_FENCE.search(text)
        if match:
            code = match.group(2).rstrip("\n")
            if code.strip():
                yield {"type": "code", "code": code, "language": match.group(1) or "text"}
        yield {"type": "done"}

    # --------------------------------------------------------------- dispatch
    def _dispatch(self, name: str, args: dict[str, Any]) -> tuple[str, str, bool]:
        """Route a tool call to its handler. Returns ``(output, status, failed)``.

        ``failed`` marks a genuine execution failure worth reflecting on (a
        non-zero exit, timeout, or launch error) — never a security block or a
        scope denial, which are correct behaviour rather than mistakes.
        """
        if name == "read_file":
            return self._read_file(str(args.get("filepath", "")))
        if name == "read_directory":
            return self._read_directory(str(args.get("path", ".")))
        if name == "execute_terminal":
            return self._execute(str(args.get("command", "")))
        return (f"Unknown tool '{name}'.", "blocked", False)

    def _read_file(self, filepath: str) -> tuple[str, str, bool]:
        resolved = _resolve_within(self.read_root, filepath)
        if resolved is None:
            return (f"[BLOCKED] Path '{filepath}' escapes the project root.", "blocked", False)
        if not resolved.is_file():
            return (f"[ERROR] Not a file: {filepath}", "blocked", False)
        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - report read failures cleanly
            return (f"[ERROR] Could not read {filepath}: {exc}", "blocked", False)
        # Never let credentials (e.g. from a .env) reach the model or UI.
        return (scan_and_redact(text[:_FILE_READ_LIMIT]).scrubbed, "ok", False)

    def _read_directory(self, path: str) -> tuple[str, str, bool]:
        resolved = _resolve_within(self.read_root, path or ".")
        if resolved is None:
            return (f"[BLOCKED] Path '{path}' escapes the project root.", "blocked", False)
        if not resolved.is_dir():
            return (f"[ERROR] Not a directory: {path}", "blocked", False)
        try:
            entries = sorted(
                p.name + ("/" if p.is_dir() else "") for p in resolved.iterdir()
            )
        except Exception as exc:  # noqa: BLE001 - report listing failures cleanly
            return (f"[ERROR] Could not list {path}: {exc}", "blocked", False)
        return ("\n".join(entries) if entries else "(empty)", "ok", False)

    def _execute(self, command: str) -> tuple[str, str, bool]:
        result = self.executor.execute(command, session_id=self.session_id)
        if result.status == "OK":
            output = ((result.stdout or "") + (result.stderr or "")).strip()
            scrubbed = scan_and_redact(output or "(no output)").scrubbed
            # Ran, but a non-zero exit code is a real failure to learn from.
            return (scrubbed, "ok", bool(result.exit_code))
        if result.status == "REQUIRE_APPROVAL":
            return (f"[NEEDS HUMAN APPROVAL - not run] {result.reason}", "blocked", False)
        if result.status in ("TIMEOUT", "ERROR"):
            return (f"[{result.status}] {result.reason}", "blocked", True)
        # BLOCKED — a security decision, not a mistake.
        return (f"[{result.status}] {result.reason}", "blocked", False)
