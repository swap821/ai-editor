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
    :class:`~aios.core.executor.Executor`. GREEN runs immediately. A YELLOW
    command pauses the turn and asks the human; once authorised (the command is
    passed back in ``approved_commands``) it actually runs via
    ``execute_approved``. RED is always blocked. The agent never auto-runs a
    non-GREEN command.
  * ``edit_file``        — replace a unique snippet in a sandbox file. Scope-
    locked to the executor's roots; shows a unified diff and pauses for approval
    (YELLOW); an approved edit (passed back in ``approved_edits``) is snapshotted,
    written, and audited.
  * ``create_file``      — author a NEW file in the sandbox. Same human gate as
    ``edit_file``: scope-locked, shows an all-additions preview and pauses for
    approval (YELLOW); an approved creation (passed back in ``approved_creations``)
    is snapshotted + audited, then written. Refuses to overwrite an existing file
    (use ``edit_file`` for that).
  * ``verify``           — run a verification command (e.g. the test suite)
    through the SAME gated Executor and judge pass/fail by exit code + parsed
    counts (blueprint stage 8). Fail-closed — a blocked, timed-out, or non-zero
    run is a FAIL, never a silent pass — and a genuine failure feeds the same
    reflection hook, closing the execute -> verify -> reflect loop.
  * ``plan``             — decompose a multi-step goal into an ordered,
    confidence-scored plan via the Planner + the 0.72 confidence gate (blueprint
    Q4). ADVISORY only — it never executes; steps below the threshold are flagged
    for human review, and the model still routes real actions through the gate. It
    needs a completion-capable LLM (injected separately from the chat client,
    which may be cloud Bedrock with no ``.complete()``); without one it degrades
    to a graceful "unavailable" result.
  * ``self_analyze``     — read + diagnose this project's OWN codebase (the
    Self-Analysis module, Tiers T0/T1; Assessment §6). Builds an architecture map
    and a deterministic diagnostic report (missing tests, smells, TODOs,
    complexity), writes it to the report table, and returns a summary. Strictly
    READ-ONLY/GREEN — it never edits source, runs anything, or loads a model — and
    the analysed ``path`` is confined to the project root like the other reads.
  * ``propose_fixes``    — Self-Analysis Tier T2: draft candidate fix DIFFS for the
    ``open`` findings and store them (status open->proposed) for human review.
    READ-ONLY — it reads source + writes the report's ``proposed_diff``, but NEVER
    edits source and NEVER applies a diff (apply is T3, behind the full gate). Uses
    the injected completion LLM; without one it degrades to a graceful "unavailable".

Force-verify-after-write: whenever an approved ``edit_file``/``create_file``
actually lands, the loop AUTONOMOUSLY runs the written file's sibling pytest
through the same gated :class:`~aios.core.verifier.Verifier` and surfaces the
verdict — so an authoritative PASS/FAIL, not the model's narration, is what the
model and the UI see next (the weak local model otherwise gets the last word and
can confabulate success). A Python file with no sibling test is reported
UNVERIFIED; non-Python writes are left untouched. Fail-closed: an unrunnable or
failing check is a FAIL, never an implied pass.

The agent is transport-agnostic: :meth:`ToolAgent.run` *yields* plain event
dicts so the API layer can forward them as SSE and tests can assert on them
without HTTP. The chat client and executor are injected, so tests drive the full
loop with a scripted fake and touch neither Ollama nor a shell.
"""
from __future__ import annotations

import ast
import difflib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Callable, Iterator, Optional, Protocol, Any, cast

from aios import config
from aios.core.autonomy import AutonomyLedger
from aios.core.executor import Executor
from aios.core.llm import LLMClient, LLMError
from aios.core.planner import Planner, PlannerError
from aios.core.verifier import Verifier
from aios.agents.self_analysis_agent import SelfAnalysisAgent
from aios.security import scope_lock
from aios.security.audit_logger import log_action
from aios.security.gateway import Zone
from aios.security.secret_scanner import scan_and_redact

#: A reflection hook: given (command, error_output), record a lesson and return
#: a summary dict (``error_type``/``lesson_text``/``recurrence``/``mistake_id``),
#: or ``None`` if nothing was recorded. Lets the agent stay decoupled from the
#: reflection agent + Mistake DB.
FailureHook = Callable[[str, str], Optional[dict[str, Any]]]

#: A confirmation hook: given a lesson's mistake id, promote it pending->verified.
#: Called only when a command succeeds after a failure observed in the same live
#: run. Recalled pending lessons remain advisory; unrelated later success is not
#: evidence that they were fixed.
ConfirmHook = Callable[[int], None]

#: Max reason -> act turns before the loop stops for safety.
DEFAULT_MAX_ITERS = 5

#: The loop's step-cap sentinel answer. Exported so composition layers (the
#: role-pass conductor) can recognise it as a non-answer at a leg boundary.
STEP_LIMIT_TEXT = "Reached the step limit and stopped for safety."


def _atomic_write_text(target: Path, content: str, *, replace: bool) -> None:
    """Durably stage text beside *target*, then publish it atomically.

    Existing-file edits use ``os.replace`` so a failed publication leaves the
    original intact. New-file creates use a hard link as an atomic no-clobber
    operation, preserving ``create_file``'s refusal to overwrite under races.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, staged_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    staged = Path(staged_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(staged, target)
        else:
            os.link(staged, target)
            staged.unlink()
    except Exception:
        staged.unlink(missing_ok=True)
        raise
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
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Edit a file in the sandbox by replacing an exact, unique "
                "snippet. Shows a unified diff and pauses for human approval "
                "before writing (file edits are caution-level). old_string must "
                "occur exactly once — include enough surrounding context to make "
                "it unique."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": (
                            "Project-relative path of the file to edit (e.g. "
                            "training_ground/notes.txt). Edits are confined to the "
                            "sandbox playground (training_ground/); paths outside it "
                            "are blocked."
                        ),
                    },
                    "old_string": {
                        "type": "string",
                        "description": "Exact text to replace; must be unique in the file.",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "Replacement text.",
                    },
                },
                "required": ["filepath", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": (
                "Create a NEW file in the sandbox with the given content. Shows a "
                "preview and pauses for human approval before writing (caution-"
                "level); never overwrites an existing file — use edit_file to "
                "modify one. Confined to the sandbox playground (training_ground/)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": (
                            "Project-relative path of the NEW file to create (e.g. "
                            "training_ground/test_new.py). Must be inside the sandbox "
                            "playground (training_ground/); paths outside it are blocked."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": "The full text body of the new file.",
                    },
                },
                "required": ["filepath", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify",
            "description": (
                "Run a verification command (e.g. the test suite) to confirm the "
                "previous change actually worked — judged by exit code + parsed "
                "pass/fail counts. Use after edits or commands to verify success."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The verification command to run (e.g. 'pytest -q').",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan",
            "description": (
                "Decompose a complex, multi-step goal into an ordered, "
                "confidence-scored plan before acting. Steps the planner is unsure "
                "about (below the confidence threshold) are flagged for human "
                "review. Use for non-trivial requests."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "The high-level, multi-step goal to decompose.",
                    }
                },
                "required": ["goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "self_analyze",
            "description": (
                "Analyze this project's OWN codebase (read-only): build an "
                "architecture map + a diagnostic report (missing tests, smells, "
                "TODOs, complexity). Use to understand or audit the system's own "
                "code. Never edits or runs anything."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Project-relative directory to analyse. Defaults to the "
                            "'aios' package. Confined to the project root."
                        ),
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_fixes",
            "description": (
                "Generate candidate fix diffs (PROPOSALS) for open Self-Analysis "
                "findings and store them for human review. Read-only: never edits "
                "source, never applies. Self-Analysis Tier T2."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max number of open findings to propose fixes for (default 25).",
                    }
                },
                "required": [],
            },
        },
    },
]

#: Exact allowlist used by the textual-tool-call fallback. A local model that
#: emits ``{"name":"read_file","arguments":{...}}`` as prose may still use a
#: real advertised tool, but can never invent a new dispatcher route.
_TOOL_NAMES = frozenset(
    str(spec["function"]["name"]) for spec in TOOL_SPECS
)


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


def _extract_text_tool_calls(content: object) -> list[dict[str, Any]]:
    """Recover one allowlisted tool call emitted as JSON prose by a local model.

    Some otherwise-capable Ollama models print fenced JSON calls instead of
    populating the native ``tool_calls`` field — sometimes several blocks in a
    single message, and sometimes keying the arguments as ``parameters``
    (llama3.1 style) rather than ``arguments``. Candidates are the whole
    message plus each ```-fenced block, in order. Accept only a whole JSON
    object whose name is in ``TOOL_SPECS``, and recover at most the FIRST such
    call: the loop's tool result re-anchors the model before it continues, so
    the one-call-at-a-time protocol is preserved. Everything else remains
    ordinary assistant text.
    """
    if not isinstance(content, str) or not content.strip():
        return []
    candidates: list[object] = [content.strip()]
    candidates += [
        match.group(1).strip()
        for match in re.finditer(r"```[a-zA-Z0-9_+-]*\s*(.*?)```", content, re.DOTALL)
    ]
    if content.strip().startswith("{"):
        # A message that BEGINS with a JSON object is a call, not prose — some
        # models emit several bare objects back-to-back with no fences at all.
        # Decode just the first object; the loop's result re-anchors the rest.
        try:
            first, _ = json.JSONDecoder().raw_decode(content.strip())
            if isinstance(first, dict):
                candidates.append(first)
        except json.JSONDecodeError:
            pass
    for match in re.finditer(r"(?ims)^\s*action:\s*([a-z0-9_]+)\s*(\{.*)", content):
        # ReAct-style narration ("Action: create_file {…}") — the fourth prose
        # shape observed live. raw_decode stops at the first complete object.
        try:
            args_obj, _ = json.JSONDecoder().raw_decode(match.group(2))
        except json.JSONDecodeError:
            continue
        if isinstance(args_obj, dict):
            candidates.append({"name": match.group(1), "arguments": args_obj})
    for candidate in candidates:
        if isinstance(candidate, dict):
            data: object = candidate
        else:
            cleaned = str(candidate)
            if cleaned.startswith("```") and cleaned.endswith("```"):
                cleaned = re.sub(r"^```[a-zA-Z0-9_+-]*\s*", "", cleaned)
                cleaned = re.sub(r"\s*```$", "", cleaned)
            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError:
                try:
                    # Some local models emit a Python-style mapping inside a
                    # `json` fence (single-quoted string values). `literal_eval`
                    # parses only literals/containers and never executes calls
                    # or expressions.
                    data = ast.literal_eval(cleaned)
                except (SyntaxError, ValueError):
                    continue
        if not isinstance(data, dict):
            continue

        function = data.get("function")
        if isinstance(function, dict):
            name = str(function.get("name", ""))
            raw_args = function.get("arguments", function.get("parameters"))
        else:
            name = str(data.get("name") or data.get("tool") or "")
            raw_args = data.get("arguments", data.get("parameters", data.get("input")))
        if name not in _TOOL_NAMES:
            continue
        args = _coerce_args(raw_args)
        return [{"function": {"name": name, "arguments": args}}]
    return []


def _explicit_tool_requests(messages: list[dict[str, Any]]) -> set[str]:
    """Tools the latest user message explicitly says to ``use`` or ``call``.

    This is not general intent inference. It only catches literal instructions
    such as "use read_file" / "call the verify tool", which lets the loop give a
    weak local model one compliance retry without forcing tools on normal chat.
    """
    latest = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            latest = str(msg.get("content", ""))
            break
    requested: set[str] = set()
    for name in _TOOL_NAMES:
        pattern = rf"\b(?:use|call)\s+(?:the\s+)?{re.escape(name)}(?:\s+tool)?\b"
        if re.search(pattern, latest, re.IGNORECASE):
            requested.add(name)
    return requested


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
        approved_commands: Optional[list[str]] = None,
        approved_edits: Optional[list[dict[str, str]]] = None,
        approved_creations: Optional[list[dict[str, str]]] = None,
        snapshot: Optional[Callable[..., Any]] = None,
        audit_log: Optional[Callable[..., object]] = None,
        planner_llm: Optional[LLMClient] = None,
        self_analysis_llm: Optional[LLMClient] = None,
        system_prompt: Optional[str] = None,
        allowed_tools: Optional[frozenset[str]] = None,
        autonomy: Optional[AutonomyLedger] = None,
    ) -> None:
        self.llm = llm
        #: Caste view (role-pass): an alternative system prompt and a hard tool
        #: subset. ``allowed_tools`` is enforced mechanically — the specs
        #: advertised to the model are filtered AND ``_dispatch`` denies any
        #: disallowed name first-line, which also covers calls recovered from
        #: prose by ``_extract_text_tool_calls``. ``None`` -> full registry.
        self.system_prompt = system_prompt
        self.allowed_tools = allowed_tools
        #: Earned-autonomy ledger (opt-in). When a YELLOW write's action class
        #: has earned enough verifier-backed successes, the turn applies it via
        #: the SAME gated path instead of pausing for a human. None -> always
        #: pause (today's behaviour). RED never reaches this path.
        self.autonomy = autonomy
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
        #: Optional confirmation hook: promotes a pending lesson only when the
        #: same failed command later succeeds in this live run (blueprint Q6).
        self.confirm_lesson = confirm_lesson
        #: Commands a human has explicitly authorised this turn (blueprint Q5).
        #: A YELLOW command listed here runs via ``execute_approved`` instead of
        #: pausing again — this is what makes in-chat approval *resumable*. RED is
        #: still refused even if listed, because approval can't authorise RED.
        self.approved_commands = set(approved_commands or [])
        #: File edits a human has authorised this turn, keyed by **filepath** ->
        #: ``(old_string, new_string)``. Keyed by filepath (not the full triple)
        #: so an approved edit still applies when the model regenerates slightly
        #: different args on the replayed turn — we then apply exactly the edit the
        #: human approved, not the model's drifted one. An unapproved ``edit_file``
        #: pauses with a diff; an approved one is snapshotted + audited, then written.
        self.approved_edits: dict[str, tuple[str, str]] = {
            str(e.get("filepath", "")): (
                str(e.get("old_string", "")),
                str(e.get("new_string", "")),
            )
            for e in (approved_edits or [])
        }
        #: New files a human has authorised this turn, keyed by **filepath** ->
        #: ``content``. Keyed by filepath (not the full pair) for the same reason as
        #: ``approved_edits``: on the replayed turn we write exactly the content the
        #: human approved, not the model's possibly-drifted regeneration. An
        #: unapproved ``create_file`` pauses with a preview; an approved one is
        #: snapshotted + audited, then written.
        self.approved_creations: dict[str, str] = {
            str(c.get("filepath", "")): str(c.get("content", ""))
            for c in (approved_creations or [])
        }
        #: Optional pre-write snapshot hook (e.g. ``RollbackEngine.create_snapshot``)
        #: called before an approved edit is written, so it stays revertible.
        self.snapshot = snapshot
        #: Audit sink for applied edits; defaults to the tamper-evident ledger.
        self._audit: Callable[..., object] = audit_log or log_action
        #: Verifier (blueprint stage 8) built from THIS agent's OWN executor and
        #: reflection hook, so a ``verify`` runs through the same security-gated,
        #: sandboxed pipeline and a genuine failure feeds the same reflection sink.
        #: Constructed once and reused by the ``verify`` tool — we never rewrite it.
        self._verifier = Verifier(self.executor, on_failure=self.on_failure)
        #: Planner (blueprint Q4) built from an injected COMPLETION client
        #: (:meth:`LLMClient.complete`) — deliberately NOT ``self.llm``, which is a
        #: CHAT client that may be cloud Bedrock with no ``.complete()``. Built once
        #: and reused by the ``plan`` tool; ``None`` when no planner LLM is injected,
        #: in which case ``plan`` degrades gracefully. We never rewrite planner.py.
        self._planner: Optional[Planner] = (
            Planner(planner_llm) if planner_llm is not None else None
        )
        #: Completion client for the Self-Analysis T2 ``propose_fixes`` tool — the
        #: SAME kind as ``planner_llm`` (``.complete()``), deliberately NOT
        #: ``self.llm`` (the chat client, possibly cloud Bedrock). ``None`` -> the
        #: tool degrades gracefully. Never used to edit/apply source — only to draft
        #: proposal diffs stored in the report.
        self._self_analysis_llm = self_analysis_llm

    def run(self, messages: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        """Drive the loop, yielding event dicts the API maps to SSE.

        Event types: ``tool_call``, ``tool_result``, ``tool_blocked``,
        ``human_required`` (pauses the turn for YELLOW approval), ``text``,
        ``code``, ``done``, ``error``.
        """
        system = self.system_prompt or SYSTEM_PROMPT
        if self.memory_context:
            system = f"{system}\n\n{self.memory_context}"
        specs = TOOL_SPECS
        if self.allowed_tools is not None:
            specs = [
                spec for spec in TOOL_SPECS
                if str(spec["function"]["name"]) in self.allowed_tools
            ]
        convo: list[dict[str, Any]] = [{"role": "system", "content": system}]
        convo.extend(messages)
        if self.approved_creations or self.approved_edits:
            # Approved writes land deterministically BEFORE the model speaks.
            # An approval is the human deciding the write happens; it must not
            # depend on the replayed model re-issuing the same tool call (the
            # dropped-grant bug: a granted write silently vanished whenever the
            # replay chose a different path).
            yield from self._pre_apply_grants(convo)
        required_tools = _explicit_tool_requests(messages)
        nudged_tools: set[str] = set()

        #: Lesson ids awaiting corrective evidence. Only failures observed during
        #: this live run enter the list; recalled pending lessons never become
        #: verified merely because an unrelated command later succeeds.
        pending_lessons: list[tuple[int, str]] = []

        for _ in range(self.max_iters):
            try:
                msg: dict[str, Any] = self.llm.chat(convo, tools=specs, model=self.model)
            except LLMError as exc:
                yield {"type": "error", "text": f"Local inference error: {exc}"}
                return
            tool_calls: list[dict[str, Any]] = msg.get("tool_calls") or []
            if not tool_calls:
                tool_calls = _extract_text_tool_calls(msg.get("content"))
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.get("content", "")}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            convo.append(assistant_msg)

            if not tool_calls:
                pending = sorted(required_tools - nudged_tools)
                if pending:
                    # Some local models answer from memory despite a literal
                    # "use/call <tool>" request. Give one narrow retry; if the
                    # model still declines, accept its answer rather than loop.
                    nudged_tools.update(pending)
                    convo.append(
                        {
                            "role": "user",
                            "content": (
                                "The previous response did not call the explicitly "
                                f"requested tool(s): {', '.join(pending)}. Call the "
                                "tool now using the provided tool interface; do not "
                                "describe or print a tool call."
                            ),
                        }
                    )
                    continue
                yield from self._finish(str(msg.get("content", "")))
                return

            for index, call in enumerate(tool_calls):
                function = cast(dict[str, Any], call.get("function", {}))
                name = str(function.get("name", ""))
                required_tools.discard(name)
                args: dict[str, Any] = _coerce_args(function.get("arguments"))
                call_id = f"{name}-{index}"

                yield {"type": "tool_call", "tool": name, "input": args, "id": call_id}
                output, status, failed = self._dispatch(name, args)
                if status == "approval":
                    _target = str(args.get("filepath") or args.get("command") or "")
                    if (
                        self.autonomy is not None
                        and name in ("create_file", "edit_file")
                        and self.autonomy.is_earned(name, _target)
                    ):
                        # EARNED AUTONOMY: this write class has earned enough
                        # verifier-backed successes to run without a human this
                        # turn. Whitelist it and re-dispatch through the SAME gated
                        # path a human grant uses (scope check, snapshot, audit,
                        # then the forced verify whose verdict records back into the
                        # ledger and revokes on any failure). RED never reaches here
                        # (it is 'blocked'); execute_approved re-refuses RED anyway.
                        # Tamper-evident record of the autonomous DECISION itself,
                        # distinct from the write's own 'tool-agent' audit entry,
                        # carrying the evidence that earned it.
                        _ev = self.autonomy.record_for(name, _target)
                        self._audit(
                            "earned-autonomy",
                            f"AUTO-GRANT {name}: {_target}"
                            + (f" (earned, {_ev['success_count']} verified)" if _ev else " (earned)"),
                            Zone.YELLOW,
                        )
                        self._grant_earned(name, args)
                        yield {
                            "type": "earned_autonomy",
                            "tool": name,
                            "command": f"{name.split('_', 1)[0]} {_target}",
                            "filepath": str(args.get("filepath", "")),
                            "reason": "earned by verified-success evidence",
                            "id": call_id,
                        }
                        output, status, failed = self._dispatch(name, args)
                    else:
                        # A caution action the human hasn't authorised yet: pause the
                        # whole turn and ask. The turn is *resumable* — the frontend
                        # re-calls /api/generate with the command/edit whitelisted, so
                        # we return here without applying it, recording no assistant
                        # answer (the paused turn is replayed, not continued mid-stream).
                        event: dict[str, Any] = {
                            "type": "human_required",
                            "tool": name,
                            "command": args.get("command", ""),
                            "reason": output,
                            "id": call_id,
                        }
                        if name == "edit_file":
                            # Surface the edit + its unified diff for the approval UI,
                            # and the full triple so the frontend can re-send it as an
                            # approved edit (the edit analog of approved_commands).
                            event["command"] = f"edit {args.get('filepath', '')}"
                            event["filepath"] = str(args.get("filepath", ""))
                            event["diff"] = output
                            event["edit"] = {
                                "filepath": str(args.get("filepath", "")),
                                "old_string": str(args.get("old_string", "")),
                                "new_string": str(args.get("new_string", "")),
                            }
                        elif name == "create_file":
                            # Surface the new file + its all-additions diff for the UI,
                            # and the {filepath, content} pair so the frontend can re-send
                            # it as an approved creation (the create analog of an edit).
                            event["command"] = f"create {args.get('filepath', '')}"
                            event["filepath"] = str(args.get("filepath", ""))
                            event["diff"] = output
                            event["creation"] = {
                                "filepath": str(args.get("filepath", "")),
                                "content": str(args.get("content", "")),
                            }
                        yield event
                        return
                if status == "blocked":
                    yield {
                        "type": "tool_blocked",
                        "tool": name,
                        "reason": output[:_PREVIEW_LIMIT],
                        "id": call_id,
                    }
                else:
                    result_event: dict[str, Any] = {
                        "type": "tool_result",
                        "tool": name,
                        "output": output[:_PREVIEW_LIMIT],
                        "id": call_id,
                    }
                    if name == "verify":
                        # The raw verified command; the API derives a per-target
                        # classification key from it (per-target last verdict).
                        result_event["target"] = str(args.get("command", ""))
                    yield result_event
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
                        # Only a successful retry of the SAME failed command is
                        # evidence that its lesson proved itself.
                        yield from self._confirm(
                            pending_lessons, str(args.get("command", "")), index
                        )
                elif name in ("edit_file", "create_file") and status == "ok":
                    # A write actually landed. Force a verification so the
                    # AUTHORITATIVE PASS/FAIL — not the model's narration — is the
                    # next signal the model and UI see ("trust evidence, not the
                    # model"). Reuses the gated Verifier; fail-closed, and a genuine
                    # FAIL reflects exactly once (inside the Verifier).
                    yield from self._auto_verify(
                        str(args.get("filepath", "")), index, convo, action_type=name
                    )

        # Step cap reached without a final answer.
        yield {"type": "text", "text": STEP_LIMIT_TEXT}
        yield {"type": "done"}

    def _grant_earned(self, name: str, args: dict[str, Any]) -> None:
        """Whitelist an earned write so its re-dispatch lands via the gated path.

        Adds the action to the same ``approved_*`` set a human grant uses, so the
        re-dispatch runs the full scope-check -> snapshot -> audit -> write ->
        forced-verify sequence in ``_create_file``/``_edit_file`` unchanged. Only
        writes are earnable in v1.
        """
        if name == "create_file":
            self.approved_creations[str(args.get("filepath", ""))] = str(
                args.get("content", "")
            )
        elif name == "edit_file":
            self.approved_edits[str(args.get("filepath", ""))] = (
                str(args.get("old_string", "")),
                str(args.get("new_string", "")),
            )

    def _pre_apply_grants(self, convo: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        """Apply granted-but-unlanded writes through the same gated paths.

        Runs at the start of a replayed turn, before the first model call.
        Every granted creation/edit goes through ``_create_file``/``_edit_file``
        unchanged (scope check, snapshot, audit, then the forced verify), and
        the results are fed into ``convo`` so the replayed model starts
        anchored to the on-disk truth. Grants that already landed on an
        earlier replay are skipped silently; a grant that can no longer apply
        (the file drifted after approval) surfaces as ``tool_blocked`` rather
        than vanishing.
        """
        # Two phases ON PURPOSE: apply ALL granted writes first, THEN verify each.
        # A turn that creates a module AND its test grants both at once; verifying a
        # test the instant it lands — before its sibling module is applied — fails on
        # the missing import and records a FALSE verified_failure even though the
        # finished files are correct. Landing every write first means each test sees
        # its module on disk, so the verdict reflects the code, not the write order.
        applied: list[tuple[int, str, str]] = []  # (index, filepath, action_type)
        for index, (filepath, content) in enumerate(self.approved_creations.items()):
            output, status, _ = self._create_file(filepath, content)
            if status == "noop":
                continue  # landed on an earlier replay
            call_id = f"grant-create-{index}"
            if status == "ok":
                yield {"type": "tool_result", "tool": "create_file",
                       "output": output[:_PREVIEW_LIMIT], "id": call_id}
                convo.append({"role": "tool", "content": output[:_TOOL_RESULT_LIMIT]})
                applied.append((index, filepath, "create_file"))
            else:
                yield {"type": "tool_blocked", "tool": "create_file",
                       "reason": output[:_PREVIEW_LIMIT], "id": call_id}
                convo.append({"role": "tool", "content": output[:_TOOL_RESULT_LIMIT]})
        for index, (filepath, _grant) in enumerate(self.approved_edits.items()):
            # _edit_file substitutes the approved (old, new) pair itself.
            output, status, _ = self._edit_file(filepath, "", "")
            if status == "noop":
                continue  # landed on an earlier replay
            call_id = f"grant-edit-{index}"
            if status == "ok":
                yield {"type": "tool_result", "tool": "edit_file",
                       "output": output[:_PREVIEW_LIMIT], "id": call_id}
                convo.append({"role": "tool", "content": output[:_TOOL_RESULT_LIMIT]})
                applied.append((index, filepath, "edit_file"))
            else:
                yield {"type": "tool_blocked", "tool": "edit_file",
                       "reason": output[:_PREVIEW_LIMIT], "id": call_id}
                convo.append({"role": "tool", "content": output[:_TOOL_RESULT_LIMIT]})
        # Phase 2 — every granted file is now on disk; verify against the truth.
        for index, filepath, action_type in applied:
            yield from self._auto_verify(filepath, index, convo, action_type=action_type)

    def _reflect(
        self,
        command: str,
        error_output: str,
        index: int,
        pending_lessons: list[tuple[int, str]],
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
            pending_lessons.append((mistake_id, command))
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
        self, pending_lessons: list[tuple[int, str]], command: str, index: int
    ) -> Iterator[dict[str, Any]]:
        """Promote lessons only after their exact failed command succeeds."""
        promoted = [mistake_id for mistake_id, failed in pending_lessons if failed == command]
        pending_lessons[:] = [
            item for item in pending_lessons if item[1] != command
        ]
        if self.confirm_lesson is None or not promoted:
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

    def _auto_verify(
        self, filepath: str, index: int, convo: list[dict[str, Any]],
        *, action_type: str = "create_file",
    ) -> Iterator[dict[str, Any]]:
        """Force a verification after a successful write — evidence over narration.

        The live loop's real danger is a weak model *narrating* success after a
        write that never landed or never worked (it gets the last word). So when an
        approved ``edit_file``/``create_file`` actually writes, we run the file's
        sibling pytest OURSELVES, surface the authoritative verdict as a visible
        step, and feed it back into ``convo`` so the model's next turn is anchored
        to PASS/FAIL — not its own prose.

        Scope (all fail-closed — never lets an unverified change look verified):
          * a non-Python write (``.txt``/``.json``/config) has no test to run, so
            we stay silent and leave the loop exactly as it was for those;
          * a Python write with NO sibling test is reported ``[VERIFY SKIPPED] …
            UNVERIFIED``;
          * a Python write WITH a sibling test (or a written ``test_*.py`` itself)
            is run through the SAME gated :class:`Verifier` the ``verify`` tool
            uses — so a genuine FAIL reflects exactly once (inside the Verifier),
            and a refused/unrunnable command is a FAIL, never a silent pass.

        The verify command is a BARE runner (``config.VERIFY_RUNNER``) plus a
        *sandbox-relative* test path: the executor runs from the sandbox cwd, and
        the gateway classifies any absolute / ``..`` path in a command as
        out-of-scope (RED), so an absolute interpreter path would be refused.
        """
        p = Path(filepath)
        if p.suffix != ".py":
            return  # not a pytest-verifiable artifact; leave the loop untouched

        abs_file = (self.read_root / filepath).resolve()
        test_abs = (
            abs_file if p.stem.startswith("test_")
            else abs_file.with_name(f"test_{p.stem}.py")
        )
        if not test_abs.is_file():
            note = (
                f"[VERIFY SKIPPED] no sibling test for {filepath} "
                f"(looked for {test_abs.name}); the change is UNVERIFIED — "
                "do not assume it works."
            )
            yield {"type": "tool_result", "tool": "verify",
                   "output": note[:_PREVIEW_LIMIT], "id": f"autoverify-{index}"}
            convo.append({"role": "tool", "content": note})
            return

        # Express the test path relative to the executor's sandbox cwd
        # (SCOPE_ROOTS[0]) so the command carries no out-of-scope absolute path;
        # fall back to the absolute path only if it lies outside that root (then
        # the gateway's scope check judges it — still fail-closed).
        roots = config.SCOPE_ROOTS
        cwd = roots[0].resolve() if roots else self.read_root
        try:
            test_arg = test_abs.relative_to(cwd).as_posix()
        except ValueError:
            test_arg = str(test_abs)
        command = f'{config.VERIFY_RUNNER} "{test_arg}" -q'

        output, status, _failed = self._verify(command, approved=True)
        if status == "blocked":
            yield {"type": "tool_blocked", "tool": "verify",
                   "reason": output[:_PREVIEW_LIMIT], "id": f"autoverify-{index}"}
            verified_ok = False  # an unverifiable change is fail-closed
        else:
            yield {"type": "tool_result", "tool": "verify",
                   "output": output[:_PREVIEW_LIMIT], "id": f"autoverify-{index}",
                   "target": command}
            verified_ok = output.lstrip().startswith("[VERIFY PASS]")
        convo.append({"role": "tool", "content": output[:_TOOL_RESULT_LIMIT]})
        # Fold the authoritative verdict into the earned-autonomy evidence for
        # this write class: a PASS extends the streak (eventually graduating the
        # class to autonomous), a FAIL revokes it instantly. This is the ONLY
        # writer of autonomy evidence — it is the verifier's word, never the
        # model's. (Skipped/non-Python writes returned above record nothing.)
        if self.autonomy is not None:
            self.autonomy.record_outcome(action_type, filepath, success=verified_ok)

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
        if self.allowed_tools is not None and name not in self.allowed_tools:
            # Caste enforcement happens where tools execute, not where prompts
            # hope — this also catches prose-rescued calls, which flow through
            # the same dispatcher.
            return (
                f"[BLOCKED] tool '{name}' is not permitted for the current role. "
                "Complete your role with the tools you have, then give your "
                "final answer.",
                "blocked",
                False,
            )
        if name == "read_file":
            return self._read_file(str(args.get("filepath", "")))
        if name == "read_directory":
            return self._read_directory(str(args.get("path", ".")))
        if name == "execute_terminal":
            return self._execute(str(args.get("command", "")))
        if name == "edit_file":
            return self._edit_file(
                str(args.get("filepath", "")),
                str(args.get("old_string", "")),
                str(args.get("new_string", "")),
            )
        if name == "create_file":
            return self._create_file(
                str(args.get("filepath", "")),
                str(args.get("content", "")),
            )
        if name == "verify":
            return self._verify(str(args.get("command", "")))
        if name == "plan":
            return self._plan(str(args.get("goal", "")))
        if name == "self_analyze":
            return self._self_analyze(str(args.get("path", "") or "aios"))
        if name == "propose_fixes":
            return self._propose_fixes(args.get("limit", 25))
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

    def _edit_file(self, filepath: str, old_string: str, new_string: str) -> tuple[str, str, bool]:
        """Replace a unique snippet in a sandbox file, gated by human approval.

        Scope-checked against the executor's sandbox roots (tighter than reads).
        Produces a unified diff; an unapproved edit pauses the turn (``approval``)
        carrying that diff, and an approved edit (listed in ``approved_edits``) is
        snapshotted first, then written and audited. ``old_string`` must occur
        exactly once — fail-closed on zero/ambiguous matches or any escape.
        """
        approved = self.approved_edits.get(filepath)
        if approved is not None:
            # Apply EXACTLY what the human approved, not the model's possibly
            # re-generated args on the replayed turn (robust resume for long edits).
            old_string, new_string = approved

        if not old_string:
            return ("[ERROR] old_string must be non-empty.", "blocked", False)
        # Resolve project-relative (like read_file) before the scope check; the absolute
        # path makes is_path_in_scope a pure containment check, so a path that names the
        # sandbox dir (training_ground/x) no longer double-joins to
        # training_ground/training_ground/x. Sandbox confinement is unchanged.
        scope = scope_lock.is_path_in_scope(str(self.read_root / filepath))
        if not scope.in_scope:
            roots = ", ".join(str(r) for r in scope_lock.get_scope_roots())
            return (
                f"[BLOCKED] '{filepath}' is outside the editable sandbox scope ({roots}).",
                "blocked",
                False,
            )
        target = Path(scope.resolved)
        if not target.is_file():
            return (
                f"[ERROR] No such file in the sandbox scope: {filepath} "
                "(edits are confined to the sandbox, which is separate from where reads are allowed).",
                "blocked",
                False,
            )
        try:
            current = target.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - report read failures cleanly
            return (f"[ERROR] Could not read {filepath}: {exc}", "blocked", False)

        occurrences = current.count(old_string)
        if occurrences == 0:
            if new_string and new_string in current:
                # Replay tolerance (the edit analog of create_file's no-op): the
                # resumable approval flow re-runs the whole turn, so the model
                # legitimately re-issues an edit an earlier replay already
                # applied. The replacement being present (and the original
                # gone) means there is nothing left to write or approve.
                return (
                    f"{filepath} already contains the requested replacement; "
                    "nothing to change.",
                    "noop",
                    False,
                )
            return (f"[ERROR] old_string not found in {filepath}.", "blocked", False)
        if occurrences > 1:
            return (
                f"[ERROR] old_string is not unique in {filepath} "
                f"({occurrences} matches); add surrounding context.",
                "blocked",
                False,
            )

        updated = current.replace(old_string, new_string, 1)
        diff = "".join(
            difflib.unified_diff(
                current.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=f"a/{filepath}",
                tofile=f"b/{filepath}",
            )
        )
        scrubbed = scan_and_redact(diff).scrubbed

        if approved is None:
            # Unapproved: pause the turn for human approval, showing the diff.
            return (scrubbed or "(no textual change)", "approval", False)

        # Approved. Capture the pre-edit snapshot and audit the intent FIRST —
        # both fail-closed: if either fails the edit is NOT applied (no
        # unprotected and no unlogged write) — then write.
        if self.snapshot is not None:
            try:
                self.snapshot(f"pre-edit: {filepath}")
            except Exception as exc:  # noqa: BLE001 - fail-closed: no snapshot, no edit
                return (
                    f"[BLOCKED] Pre-edit snapshot failed; edit not applied: {exc}",
                    "blocked",
                    False,
                )
        try:
            self._audit("tool-agent", f"EDIT: {filepath}", Zone.YELLOW)
        except Exception as exc:  # noqa: BLE001 - fail-closed: no audit, no edit
            return (
                f"[BLOCKED] Audit failed; edit not applied: {exc}",
                "blocked",
                False,
            )
        try:
            _atomic_write_text(target, updated, replace=True)
        except Exception as exc:  # noqa: BLE001 - report write failures cleanly
            return (f"[ERROR] Could not write {filepath}: {exc}", "blocked", False)
        return (f"Edited {filepath}:\n{scrubbed}", "ok", False)

    def _create_file(self, filepath: str, content: str) -> tuple[str, str, bool]:
        """Author a NEW file in the sandbox, gated by human approval.

        Mirrors :meth:`_edit_file`'s security exactly — scope-locked to the sandbox
        roots (a ``../`` / absolute / symlink escape or any out-of-sandbox path is
        refused, never written), an unapproved create pauses the turn (``approval``)
        carrying an all-additions diff preview, and an approved create (listed in
        ``approved_creations``) is snapshotted + audited FIRST (both fail-closed),
        then written. Refuses to overwrite: ``create_file`` is for NEW paths only —
        an existing file must go through ``edit_file``.
        """
        approved = self.approved_creations.get(filepath)
        if approved is not None:
            # Write EXACTLY the content the human approved, not the model's possibly
            # re-generated content on the replayed turn (robust resume for new files).
            content = approved

        resolved = _resolve_within(self.read_root, filepath)
        if resolved is None:
            return (f"[BLOCKED] Path '{filepath}' escapes the project root.", "blocked", False)
        # Same containment check edit_file uses: resolve project-relative, then a
        # pure scope test against the sandbox roots (out-of-sandbox -> refused).
        scope = scope_lock.is_path_in_scope(str(self.read_root / filepath))
        if not scope.in_scope:
            roots = ", ".join(str(r) for r in scope_lock.get_scope_roots())
            return (
                f"[BLOCKED] '{filepath}' is outside the editable sandbox scope ({roots}).",
                "blocked",
                False,
            )
        target = Path(scope.resolved)
        if target.exists():
            try:
                existing: str | None = target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                existing = None
            if existing is not None and existing == content:
                # Replay tolerance: the resumable approval flow re-runs the whole
                # turn after each human approval, so the model legitimately
                # re-issues a create for a file an earlier replay already wrote.
                # Byte-identical content means nothing is written (and nothing
                # new needs approving); report success so the loop continues to
                # the task's remaining steps instead of dead-ending.
                # "noop" (not "ok") so the loop reports success without forcing
                # a redundant re-verification: auto-verify exists to verify a
                # write that LANDED, and nothing changed on disk here.
                return (
                    f"{filepath} already exists with exactly the requested "
                    "content; nothing to write.",
                    "noop",
                    False,
                )
            return (
                f"[ERROR] {filepath} already exists; use edit_file to modify it "
                "(create_file only authors new files).",
                "blocked",
                False,
            )

        # An all-additions unified diff ("" -> content) for the approval preview.
        diff = "".join(
            difflib.unified_diff(
                [],
                content.splitlines(keepends=True),
                fromfile="/dev/null",
                tofile=f"b/{filepath}",
            )
        )
        scrubbed = scan_and_redact(diff).scrubbed

        if approved is None:
            # Unapproved: pause the turn for human approval, showing the new content.
            return (scrubbed or "(empty file)", "approval", False)

        # Approved. Capture the pre-create snapshot and audit the intent FIRST —
        # both fail-closed: if either fails the file is NOT created (no unprotected
        # and no unlogged write). The snapshot's "before" has the file absent, so a
        # rollback correctly deletes it.
        if self.snapshot is not None:
            try:
                self.snapshot(f"pre-create: {filepath}")
            except Exception as exc:  # noqa: BLE001 - fail-closed: no snapshot, no create
                return (
                    f"[BLOCKED] Pre-create snapshot failed; file not created: {exc}",
                    "blocked",
                    False,
                )
        try:
            self._audit("tool-agent", f"CREATE: {filepath}", Zone.YELLOW)
        except Exception as exc:  # noqa: BLE001 - fail-closed: no audit, no create
            return (
                f"[BLOCKED] Audit failed; file not created: {exc}",
                "blocked",
                False,
            )
        try:
            # The helper creates parents inside the verified-in-scope target and
            # publishes without clobbering a file created during this operation.
            _atomic_write_text(target, content, replace=False)
        except Exception as exc:  # noqa: BLE001 - report write failures cleanly
            return (f"[ERROR] Could not create {filepath}: {exc}", "blocked", False)
        n_lines = content.count("\n") + (0 if content.endswith("\n") or not content else 1)
        return (
            f"Created {filepath} ({len(content)} bytes, {n_lines} line(s)):\n{scrubbed}",
            "ok",
            False,
        )

    def _verify(self, command: str, *, approved: bool = False) -> tuple[str, str, bool]:
        """Run *command* as a verification through the Verifier; map its verdict.

        Closes the execute -> verify -> reflect loop (blueprint stage 8). The
        Verifier runs *command* through the SAME gated, sandboxed Executor — so a
        RED / out-of-scope verify command is refused by the gateway and never run;
        we do NOT bypass it — and judges pass/fail by exit code + parsed counts,
        fail-closed. The Verifier fires the reflection hook itself on a genuine
        failure, so this dispatch path must NOT reflect again.

        The :class:`~aios.core.verifier.VerifierResult` maps to the loop's
        ``(output, status, failed)`` shape:

          * a security BLOCK -> ``blocked`` (a refusal is correct behaviour, not a
            mistake; ``run`` only reflects for ``execute_terminal``, so it cannot
            double-reflect a verify either way);
          * a pass or a genuine fail -> ``ok`` with a clear PASS/FAIL line, the
            pass/fail counts, exit code, and the captured summary so the model
            (and the UI) plainly see the verdict.
        """
        is_approved = approved or command in self.approved_commands
        result = self._verifier.verify(
            command,
            session_id=self.session_id,
            approved=is_approved,
        )

        if result.status == "REQUIRE_APPROVAL":
            return (result.summary, "approval", False)
        if result.status == "BLOCKED":
            return (
                result.summary or f"[BLOCKED] Verification command refused: {command}",
                "blocked",
                False,
            )

        verdict = "PASS" if result.passed else "FAIL"
        exit_str = "?" if result.exit_code is None else str(result.exit_code)
        header = (
            f"[VERIFY {verdict}] {result.passed_count} passed, "
            f"{result.failed_count} failed (exit {exit_str})"
        )
        body = result.summary.strip()
        output = f"{header}\n{body}" if body else header
        # The Verifier already fired on_failure on a genuine failure; run() reflects
        # only for execute_terminal, so `failed` here is informational (it cannot
        # re-trigger reflection) — carried for the loop's tool-result shape.
        return (output, "ok", not result.passed)

    def _plan(self, goal: str) -> tuple[str, str, bool]:
        """Decompose *goal* into a confidence-gated plan (blueprint Q4); ADVISORY.

        Runs the Planner over the injected COMPLETION client (never ``self.llm`` —
        the chat client may be cloud Bedrock with no ``.complete()``) and the 0.72
        confidence gate, then surfaces an ordered, confidence-scored summary so the
        model can plan before acting. The plan NEVER executes and is NEVER reflected
        on: real actions still pass through the security gate + approval, and a bad
        goal / unusable LLM output is a normal advisory result, not a mistake.

          * no planner configured -> a graceful "unavailable" result (never crash);
          * ``PlannerError`` (empty goal / junk LLM output) -> a clean error result;
          * success -> the ordered steps with confidences + an explicit human-review
            section listing every step the gate escalated (confidence < threshold).

        Always returns status ``ok`` with ``failed=False`` — planning is advisory,
        so it surfaces as a normal ``tool_result`` and is never a reflectable failure.
        """
        if self._planner is None:
            return ("[plan unavailable] no planner configured", "ok", False)
        try:
            plan = self._planner.plan(goal)
        except PlannerError as exc:
            return (f"[plan error] could not produce a plan: {exc}", "ok", False)
        except Exception as exc:  # noqa: BLE001 - advisory tool must never abort the turn
            # A planner-LLM failure (e.g. LLMError when the local completion model is
            # down while chatting on Bedrock) must degrade to a graceful advisory result —
            # run() does not wrap _dispatch, so an uncaught error here would abort the turn.
            return (f"[plan error] planner failed: {exc}", "ok", False)

        lines = [f"Plan for: {plan.goal}", ""]
        for step in plan.steps:
            lines.append(
                f"  {step.step_id}. {step.description} (confidence {step.confidence:.2f})"
            )
        if plan.requires_human:
            lines.append("")
            lines.append(
                f"{len(plan.escalate)} step(s) need human review "
                f"(confidence < {self._planner.threshold:.2f}):"
            )
            for item in plan.escalate:
                step = item["step"]
                lines.append(
                    f"  - step {step.step_id}: {step.description} ({step.confidence:.2f})"
                )
        return ("\n".join(lines), "ok", False)

    def _self_analyze(self, path: str) -> tuple[str, str, bool]:
        """Read + diagnose the project's own code (Self-Analysis T0/T1); READ-ONLY.

        Confines *path* to the project root with the SAME read-side resolver as
        ``read_file`` (defeating ``../`` traversal / absolute-path / symlink
        escape), runs the deterministic :class:`SelfAnalysisAgent` over it, writes
        the findings to the report table, and returns a concise summary (counts by
        finding_type + the top findings). It never edits source, runs a command, or
        loads a model — so it always returns status ``ok`` with ``failed=False``
        and is never a reflectable failure (a read-only audit is correct behaviour).
        """
        resolved = _resolve_within(self.read_root, path)
        if resolved is None:
            return (f"[BLOCKED] Path '{path}' escapes the project root.", "blocked", False)
        if not resolved.is_dir():
            return (f"[ERROR] Not a directory: {path}", "blocked", False)

        agent = SelfAnalysisAgent(
            scope_root=resolved,
            tests_root=self.read_root / "tests",
            path_root=self.read_root,
        )
        try:
            report = agent.analyze()
            res = agent.write_report(list(report.findings))
        except Exception as exc:  # noqa: BLE001 - read-only analysis must never abort the turn
            return (f"[ERROR] Self-analysis failed: {exc}", "blocked", False)

        counts: dict[str, int] = {}
        for f in report.findings:
            counts[f.finding_type] = counts.get(f.finding_type, 0) + 1
        by_type = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "none"

        lines = [
            f"Self-analysis of '{path}': {len(report.modules)} module(s), "
            f"{len(report.findings)} finding(s) [{by_type}]; "
            f"{res.open_total} open in report ({res.inserted} new, {res.closed} resolved).",
        ]
        for f in report.findings[:8]:
            lines.append(f"  - [{f.finding_type}] {f.target_path}: {f.evidence}")
        if len(report.findings) > 8:
            lines.append(f"  … and {len(report.findings) - 8} more.")
        return ("\n".join(lines), "ok", False)

    def _propose_fixes(self, limit: Any) -> tuple[str, str, bool]:
        """Self-Analysis T2: draft + store fix proposals for open findings; READ-ONLY.

        Runs :meth:`SelfAnalysisAgent.propose_open` over the own-code report (the
        same MEMORY_DB the report lives in), using the injected COMPLETION client
        (never ``self.llm``). It reads source + writes proposals (``proposed_diff``,
        ``open->proposed``) but NEVER edits source and NEVER applies a diff (apply is
        T3, behind the full gate). Always status ``ok`` / ``failed=False`` — proposing
        is advisory, never a security block and never reflected on. No client -> a
        graceful "unavailable" result.
        """
        if self._self_analysis_llm is None:
            return ("[propose unavailable] no completion model configured.", "ok", False)
        try:
            n = int(limit)
        except (TypeError, ValueError):
            n = 25
        try:
            agent = SelfAnalysisAgent(
                scope_root=self.read_root / "aios",
                tests_root=self.read_root / "tests",
                path_root=self.read_root,
                llm=self._self_analysis_llm,
            )
            count = agent.propose_open(limit=n)
        except Exception as exc:  # noqa: BLE001 - advisory tool must never abort the turn
            return (f"[propose error] could not propose fixes: {exc}", "ok", False)
        return (
            f"Proposed fixes for {count} finding(s) (status open→proposed); "
            "review with status='proposed' before any apply (T3).",
            "ok",
            False,
        )

    def _format_exec_result(self, result: Any) -> tuple[str, str, bool]:
        """Map a *resolved* ExecutionResult to ``(output, status, failed)``.

        Handles every terminal status (OK/BLOCKED/TIMEOUT/ERROR) — i.e. a command
        that actually ran or was refused — but never ``REQUIRE_APPROVAL``, which
        the caller intercepts so the turn can pause for a human.
        """
        if result.status == "OK":
            output = ((result.stdout or "") + (result.stderr or "")).strip()
            scrubbed = scan_and_redact(output or "(no output)").scrubbed
            # Ran, but a non-zero exit code is a real failure to learn from.
            return (scrubbed, "ok", bool(result.exit_code))
        if result.status in ("TIMEOUT", "ERROR"):
            return (f"[{result.status}] {result.reason}", "blocked", True)
        # BLOCKED — a security decision (incl. RED refused under approval), not a
        # mistake to reflect on.
        return (f"[{result.status}] {result.reason}", "blocked", False)

    def _execute(self, command: str) -> tuple[str, str, bool]:
        """Run a command, returning ``(output, status, failed)``.

        A command the human has authorised this turn runs through
        ``execute_approved`` (GREEN/YELLOW run; RED is still refused). Otherwise
        it goes through the normal gateway: a YELLOW escalation surfaces as the
        ``"approval"`` status so :meth:`run` can pause and ask, rather than the
        old "needs approval / not run" dead-end.
        """
        if command in self.approved_commands:
            return self._format_exec_result(self.executor.execute_approved(command))
        result = self.executor.execute(command, session_id=self.session_id)
        if result.status == "REQUIRE_APPROVAL":
            return (result.reason, "approval", False)
        return self._format_exec_result(result)
