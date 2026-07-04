"""Agentic tool loop -- lets the chat actually act, under the security gateway.

SECURITY FIX (H2): Prose tool-call recovery is now STRICT tiered:
  Tier 1: Exact JSON array/object at start of text
  Tier 2: Markdown code block with JSON
  Tier 3: Python-literal object/array from local models (literal_eval only)
  Tier 4: ReAct Action pattern (validated through the same allowlist)
  NO heuristic/fuzzy parsing

SECURITY FIX (H3): Agent loop detection prevents runaway execution:
  - Repeated identical tool calls are detected
  - Alternating patterns (A->B->A->B) are detected
  - Hard ceiling on iteration count


The agent runs a bounded reason -> act -> observe loop on the local model via
Ollama's function-calling chat API. Each turn the model may call a tool; the
agent executes it through the same security-gated, audited subsystems the rest
of the OS uses, feeds the (secret-scrubbed) result back, and loops until the
model produces a final answer or a step cap is reached.

Tools exposed to the model:

  * ``read_file``        -- read a project file. Reads are GREEN/safe, but the
    path is canonicalised and must stay within the project root (no traversal,
    no symlink escape), and content is secret-scrubbed before the model sees it.
  * ``read_directory``   -- list a project directory (same scope rule).
  * ``execute_terminal`` -- run a shell command through the gateway + sandbox
    :class:`~aios.core.executor.Executor`. GREEN runs immediately. A YELLOW
    command pauses the turn and asks the human; once authorised (the command is
    passed back in ``approved_commands``) it actually runs via
    ``execute_approved``. RED is always blocked. The agent never auto-runs a
    non-GREEN command.
  * ``edit_file``        -- replace a unique snippet in a sandbox file. Scope-
    locked to the executor's roots; shows a unified diff and pauses for approval
    (YELLOW); an approved edit (passed back in ``approved_edits``) is snapshotted,
    written, and audited.
  * ``create_file``      -- author a NEW file in the sandbox. Same human gate as
    ``edit_file``: scope-locked, shows an all-additions preview and pauses for
    approval (YELLOW); an approved creation (passed back in ``approved_creations``)
    is snapshotted + audited, then written. Refuses to overwrite an existing file
    (use ``edit_file`` for that).
  * ``verify``           -- run a verification command (e.g. the test suite)
    through the SAME gated Executor and judge pass/fail by exit code + parsed
    counts (blueprint stage 8). Fail-closed -- a blocked, timed-out, or non-zero
    run is a FAIL, never a silent pass -- and a genuine failure feeds the same
    reflection hook, closing the execute -> verify -> reflect loop.
  * ``plan``             -- decompose a multi-step goal into an ordered,
    confidence-scored plan via the Planner + the 0.72 confidence gate (blueprint
    Q4). ADVISORY only -- it never executes; steps below the threshold are flagged
    for human review, and the model still routes real actions through the gate. It
    needs a completion-capable LLM (injected separately from the chat client,
    which may be cloud Bedrock with no ``.complete()``); without one it degrades
    to a graceful "unavailable" result.
  * ``self_analyze``     -- read + diagnose this project's OWN codebase (the
    Self-Analysis module, Tiers T0/T1; Assessment §6). Builds an architecture map
    and a deterministic diagnostic report (missing tests, smells, TODOs,
    complexity), writes it to the report table, and returns a summary. Strictly
    READ-ONLY/GREEN -- it never edits source, runs anything, or loads a model -- and
    the analysed ``path`` is confined to the project root like the other reads.
  * ``propose_fixes``    -- Self-Analysis Tier T2: draft candidate fix DIFFS for the
    ``open`` findings and store them (status open->proposed) for human review.
    READ-ONLY -- it reads source + writes the report's ``proposed_diff``, but NEVER
    edits source and NEVER applies a diff (apply is T3, behind the full gate). Uses
    the injected completion LLM; without one it degrades to a graceful "unavailable".

Force-verify-after-write: whenever an approved ``edit_file``/``create_file``
actually lands, the loop AUTONOMOUSLY runs the written file's sibling pytest
through the same gated :class:`~aios.core.verifier.Verifier` and surfaces the
verdict -- so an authoritative PASS/FAIL, not the model's narration, is what the
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
import json
import re
from pathlib import Path
from typing import Callable, Iterator, Optional, Protocol, Any, cast

from aios import config
from aios.agents import tool_handlers, tool_loop_helpers
from aios.core.autonomy import AutonomyLedger
from aios.core.cerebellum import Cerebellum
from aios.core.executor import Executor
from aios.core.llm import LLMClient, LLMError
from aios.core.stream_protocol import StreamFinished
from aios.core.planner import Planner
from aios.core.verification_strength import (
    VerificationStrength,
    derive_strength,
    parse_test_counts,
    strength_from_text,
)
from aios.core.verifier import Verifier
from aios.security.audit_logger import log_action
from aios.security.gateway import Zone

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


class AgentLoopError(Exception):
    """Raised when the agent is detected in a repetitive loop.

    This is a safety mechanism: if the model repeatedly makes the same
    tool call(s) without making progress, we stop the loop rather than
    letting it consume resources or potentially cause harm.
    """
    pass


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
                "occur exactly once -- include enough surrounding context to make "
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
                "level); never overwrites an existing file -- use edit_file to "
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
                "previous change actually worked -- judged by exit code + parsed "
                "pass/fail counts. Use after edits or commands to verify success. "
                "Commands run FROM the sandbox directory, so give test paths "
                "sandbox-relative: write 'pytest test_x.py', NOT "
                "'pytest training_ground/test_x.py' (the latter double-nests and "
                "collects 0 tests)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": (
                            "The verification command to run, with any test path "
                            "sandbox-relative (e.g. 'pytest -q' or 'pytest test_x.py')."
                        ),
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browse",
            "description": (
                "Fetch a public web page and return its main text content. This "
                "tool leaves the local machine, so each URL requires human approval "
                "(caution-level). Use it to learn from public internet sources."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Public http(s) URL to fetch.",
                    }
                },
                "required": ["url"],
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


def _validate_tool_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate extracted tool calls against the allowlist.

    SECURITY: Every tool call recovered from prose MUST pass through this
    validator before dispatch. It enforces:
      * Tool name is in the advertised allowlist
      * Arguments are primitive values only (str, int, float, bool)
        -- no nested objects that could carry injection payloads
    """
    validated: list[dict[str, Any]] = []
    for call in calls:
        name = ""
        raw_args: object = None

        function = call.get("function")
        if isinstance(function, dict):
            name = str(function.get("name", ""))
            raw_args = function.get("arguments", function.get("parameters"))
        else:
            name = str(call.get("name") or call.get("tool") or "")
            raw_args = call.get("arguments", call.get("parameters", call.get("input")))

        if name not in _TOOL_NAMES:
            # Audit-log the block attempt
            log_action(
                "tool-agent",
                f"Blocked prose-recovered tool call to non-allowlisted tool: {name}",
                zone=Zone.YELLOW,
            )
            continue

        args = _coerce_args(raw_args)
        # Validate arguments are primitives only -- no nested objects
        if not all(isinstance(v, (str, int, float, bool, type(None))) for v in args.values()):
            log_action(
                "tool-agent",
                f"Blocked tool call '{name}' with non-primitive arguments",
                zone=Zone.YELLOW,
            )
            continue
        validated.append({"function": {"name": name, "arguments": args}})
    return validated


def _parse_structured_tool_payload(payload: str) -> object:
    """Parse a model-emitted tool payload without executing code.

    Only dicts/lists are accepted from the ast.literal_eval fallback —
    scalar literals (strings, ints) would pass literal_eval but are not
    valid tool-call payloads and could mask injection attempts.
    """
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        result = ast.literal_eval(payload)
        if not isinstance(result, (dict, list)):
            raise ValueError(f"unexpected literal type: {type(result).__name__}")
        return result


def _validated_from_structured_payload(payload: str) -> list[dict[str, Any]]:
    """Parse and validate one object/array-shaped recovered tool-call payload."""
    try:
        parsed = _parse_structured_tool_payload(payload)
    except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError):
        return []
    if isinstance(parsed, list):
        if all(isinstance(item, dict) for item in parsed):
            return _validate_tool_calls(parsed)
    elif isinstance(parsed, dict):
        return _validate_tool_calls([parsed])
    return []


def _extract_text_tool_calls(
    content: object,
    *,
    enable_react_recovery: bool = True,
) -> list[dict[str, Any]]:
    """Extract tool calls from model prose -- STRICT TIERED recovery.

    SECURITY: This function implements a deliberately restrictive tiered
    recovery to prevent models from hiding tool calls in normal-looking
    text. Each tier is more permissive but still bounded.

    Tier 1: Exact JSON array/object at start of text (safest)
    Tier 2: Markdown code block with JSON (moderate safety)
    Tier 3: Python-literal object/array from local models. This uses
        ast.literal_eval only; it does not execute calls/attributes/imports.
    Tier 4: ReAct Action pattern (validated through the same allowlist)
    NO fuzzy matching.

    If none of the tiers match, the model did not intend a tool call and
    the content is treated as ordinary assistant text.

    Every recovered call passes through :func:`_validate_tool_calls` for
    allowlist + argument validation before being returned.
    """
    if not isinstance(content, str) or not content.strip():
        return []

    text_stripped = content.strip()

    # ---- TIER 1: Exact JSON array/object at start of text ----
    # A message that BEGINS with [ or { is a structured call, not prose.
    if text_stripped.startswith("[") or text_stripped.startswith("{"):
        calls = _validated_from_structured_payload(text_stripped)
        if calls:
            return calls
        # Not valid JSON/Python literal as a whole -- try raw_decode for the
        # first JSON object so a second printed JSON object stays unexecuted until
        # the loop re-anchors on the first result.
        try:
            first, _ = json.JSONDecoder().raw_decode(text_stripped)
            if isinstance(first, dict):
                return _validate_tool_calls([first])
            if isinstance(first, list):
                return _validate_tool_calls(first)
        except json.JSONDecodeError:
            pass

    # ---- TIER 2: Markdown code block with JSON ----
    code_block_match = re.search(
        r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL
    )
    if code_block_match:
        cleaned = code_block_match.group(1).strip()
        calls = _validated_from_structured_payload(cleaned)
        if calls:
            return calls

    # ---- TIER 3: ReAct Action pattern ----
    # ReAct parses prose narration, so keep it restricted to an explicit
    # "Action:" line plus JSON args, then the normal allowlist/primitive filter.
    if enable_react_recovery:
        for match in re.finditer(
            r"(?ims)^\s*action:\s*([a-z0-9_]+)\s*(\{.*)", content
        ):
            try:
                args_obj, _ = json.JSONDecoder().raw_decode(match.group(2))
            except json.JSONDecodeError:
                continue
            if isinstance(args_obj, dict):
                return _validate_tool_calls(
                    [{"name": match.group(1), "arguments": args_obj}]
                )

    # No heuristic/fuzzy parsing. If the model did not produce one of the
    # structured forms above, it did not intend a tool call.
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


def build_auto_verify_command(test_arg: str) -> str:
    """The forced auto-verify command for one sandbox test file.

    Shared by :meth:`ToolAgent._auto_verify` and the real-subprocess
    regression test so the tested command can never drift from the one
    production runs.

    ``-o addopts=`` is load-bearing: pytest discovers ini config upward
    from its cwd, and this repo's own pytest.ini addopts contribute a
    second ``-q`` (stacking into ``-qq``, which suppresses the "N passed"
    summary line the Verifier's count parser requires for STRONG) plus
    ``--cov=aios`` (coverage of an unrelated tree slowing a sandbox-scoped
    run). Emptying inherited addopts keeps the verify scoped to the
    artifact and keeps a genuine pass STRONG-parseable. The flag sits
    AFTER the runner tokens, so the strength taxonomy's program-position
    anchoring is unaffected. (Found live by prove_it.py, 2026-07-03.)
    """
    return f'{config.VERIFY_RUNNER} -o addopts= "{test_arg}" -q'


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
        resume_tail: Optional[list[dict[str, Any]]] = None,
        cerebellum: Optional[Cerebellum] = None,
        native_planner: Optional[Any] = None,
        stream_fn: Optional[Callable[..., Iterator[Any]]] = None,
    ) -> None:
        self.llm = llm
        self.stream_fn = stream_fn
        #: Caste view (role-pass): an alternative system prompt and a hard tool
        #: subset. ``allowed_tools`` is enforced mechanically -- the specs
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
        #: Compiled-experience engine (sovereignty S1). When a user message
        #: matches a compiled playbook, the cerebellum replays the tool
        #: sequence through _dispatch (full gateway) without an LLM call.
        #: None -> always use the LLM (today's behaviour).
        self.cerebellum = cerebellum
        self.executor = executor
        self.model = model
        self.max_iters = max_iters
        #: Reads are confined to this tree (the project). Writes/exec remain
        #: confined to the executor's own (tighter) sandbox scope roots.
        self.read_root = (read_root or config.PROJECT_ROOT).resolve()
        self.session_id = session_id
        #: Optional recalled-memory block injected into the system prompt
        #: (blueprint stage 4 -- the agent reasons with relevant past knowledge).
        self.memory_context = memory_context
        #: Optional reflection hook fired when a command genuinely fails (not when
        #: it is merely blocked by the gateway) -- blueprint stage 9.
        self.on_failure = on_failure
        #: Optional confirmation hook: promotes a pending lesson only when the
        #: same failed command later succeeds in this live run (blueprint Q6).
        self.confirm_lesson = confirm_lesson
        #: Commands a human has explicitly authorised this turn (blueprint Q5).
        #: A YELLOW command listed here runs via ``execute_approved`` instead of
        #: pausing again -- this is what makes in-chat approval *resumable*. RED is
        #: still refused even if listed, because approval can't authorise RED.
        self.approved_commands = set(approved_commands or [])
        #: File edits a human has authorised this turn, keyed by **filepath** ->
        #: ``(old_string, new_string)``. Keyed by filepath (not the full triple)
        #: so an approved edit still applies when the model regenerates slightly
        #: different args on the replayed turn -- we then apply exactly the edit the
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
        #: Constructed once and reused by the ``verify`` tool -- we never rewrite it.
        self._verifier = Verifier(self.executor, on_failure=self.on_failure)
        #: Planner (blueprint Q4) built from an injected COMPLETION client
        #: (:meth:`LLMClient.complete`) -- deliberately NOT ``self.llm``, which is a
        #: CHAT client that may be cloud Bedrock with no ``.complete()``. Built once
        #: and reused by the ``plan`` tool; ``None`` when no planner LLM is injected,
        #: in which case ``plan`` degrades gracefully. We never rewrite planner.py.
        self._planner: Optional[Planner] = (
            Planner(planner_llm, native=native_planner)
            if planner_llm is not None
            else None
        )
        #: Completion client for the Self-Analysis T2 ``propose_fixes`` tool -- the
        #: SAME kind as ``planner_llm`` (``.complete()``), deliberately NOT
        #: ``self.llm`` (the chat client, possibly cloud Bedrock). ``None`` -> the
        #: tool degrades gracefully. Never used to edit/apply source -- only to draft
        #: proposal diffs stored in the report.
        self._self_analysis_llm = self_analysis_llm
        #: Approval-resume continuation (ratified option A). The convo tail a
        #: PRIOR turn on this same session accumulated before it paused for
        #: YELLOW approval (assistant tool_calls, tool results, everything
        #: appended on top of the initial [system]+messages prefix). Spliced
        #: onto ``convo`` right after the prefix and BEFORE the replayed
        #: grant-anchor messages, so the model sees: its own prior ask -> the
        #: now-applied grant -> continue. MODEL CONTEXT ONLY -- carries no
        #: authority; everything it induces still flows through the same
        #: gated dispatch loop. ``None`` -> today's behaviour unchanged.
        self.resume_tail = resume_tail

        # ---- Loop safety: detect repetitive tool-call patterns ----
        #: All tool calls made in this run, as (name, arg_signature) tuples,
        #: for loop detection. Reset each run() invocation.
        self._tool_call_history: list[tuple[str, str]] = []
        #: How many consecutive identical calls before we consider it a loop.
        self._repeated_tool_threshold = 3
        #: Enable validated ReAct prose recovery for local models.
        self._enable_react_recovery = True

    def _detect_agent_loop(self, tool_calls: list[dict[str, Any]]) -> bool:
        """Detect if the agent is stuck in a repetitive loop.

        Returns True when:
          * The last N tool calls are identical (stuck repeating one action)
          * The last 4 calls form an A->B->A->B alternating pattern
            (oscillating between two actions with no progress)

        These patterns indicate the model is not making progress and
        continuing the loop would waste resources or potentially cause
        harm (e.g., repeated file reads, repeated failed commands).
        """
        current = [
            (str(c.get("function", {}).get("name", "")), str(c.get("function", {}).get("arguments", {})))
            for c in tool_calls
        ]
        self._tool_call_history.extend(current)

        # Check 1: last N calls are all identical (repeating the same action)
        if len(self._tool_call_history) >= self._repeated_tool_threshold:
            last_n = self._tool_call_history[-self._repeated_tool_threshold:]
            if len(set(last_n)) == 1:
                return True

        # Check 2: alternating A->B->A->B pattern (oscillation)
        if len(self._tool_call_history) >= 4:
            last_4 = self._tool_call_history[-4:]
            if (
                last_4[0] == last_4[2]
                and last_4[1] == last_4[3]
                and last_4[0] != last_4[1]
            ):
                return True

        return False

    def _reset_loop_safety(self) -> None:
        """Reset loop-detection state at the start of each run."""
        self._tool_call_history = []

    def run(self, messages: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:

        """Event types: ``tool_call``, ``tool_result``, ``tool_blocked``,
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
        # Reset loop-safety tracking at the start of each fresh run.
        self._reset_loop_safety()

        convo: list[dict[str, Any]] = [{"role": "system", "content": system}]
        convo.extend(messages)
        if self.resume_tail:
            # Continuation (ratified option A, S3): splice in the PRIOR turn's
            # tail (this session's own last pause -- assistant tool_call(s) +
            # tool results) BEFORE the grant anchor below, so ordering reads:
            # the model's own prior ask -> approved+applied -> continue.
            convo.extend(self.resume_tail)
        if self.approved_creations or self.approved_edits:
            # Approved writes land deterministically BEFORE the model speaks.
            # An approval is the human deciding the write happens; it must not
            # depend on the replayed model re-issuing the same tool call (the
            # dropped-grant bug: a granted write silently vanished whenever the
            # replay chose a different path).
            yield from self._pre_apply_grants(convo)
        # -- Cerebellum short-circuit (sovereignty S1) --------------------------
        # If a compiled playbook matches this turn's user message AND there are
        # no pending approvals (this is a fresh turn, not a continuation), replay
        # the playbook through _dispatch (full gateway, same audit) without an
        # LLM call. A successful replay returns immediately; an aborted replay
        # falls through to the LLM loop below.
        if (
            self.cerebellum is not None
            and not self.approved_commands
            and not self.approved_edits
            and not self.approved_creations
            and not self.resume_tail
        ):
            _user_text = next(
                (str(m.get("content", "")) for m in reversed(messages)
                 if m.get("role") == "user"),
                "",
            )
            try:
                _playbook = self.cerebellum.match(_user_text) if _user_text else None
            except Exception:
                _playbook = None
            if _playbook is not None:
                _replay_ok = True
                for _ev in self.cerebellum.replay(
                    _playbook, dispatch_fn=self._dispatch,
                ):
                    yield _ev
                    if _ev.get("type") == "cerebellum_abort":
                        _replay_ok = False
                if _replay_ok:
                    yield {
                        "type": "cerebellum_done",
                        "goal": _playbook.goal_pattern,
                        "playbook_id": _playbook.id,
                        "replay_count": _playbook.replay_count,
                    }
                    yield from self._finish(
                        f"Completed from compiled experience: "
                        f"{_playbook.goal_pattern}"
                    )
                    return
                # Aborted — fall through to the LLM loop below.

        # -- Offline guard (sovereignty S4) ----------------------------------------
        if config.OFFLINE_MODE:
            yield from self._finish(
                "I'm running in offline mode — no LLM is available. "
                "I matched no compiled playbook for this request, so I "
                "can't handle it natively yet. I need either a model to "
                "be available, or to have completed this type of task "
                "successfully before so I can replay from experience."
            )
            return

        required_tools = _explicit_tool_requests(messages)
        nudged_tools: set[str] = set()

        #: Lesson ids awaiting corrective evidence. Only failures observed during
        #: this live run enter the list; recalled pending lessons never become
        #: verified merely because an unrelated command later succeeds.
        pending_lessons: list[tuple[int, str]] = []

        for _ in range(self.max_iters):
            # --- C4: streaming path (real-time cloud tokens) ---
            streamed_text: bool = False
            if self.stream_fn is not None:
                try:
                    msg, streamed_text = yield from self._stream_iteration(
                        convo, specs
                    )
                except LLMError as exc:
                    yield {"type": "error", "text": f"Local inference error: {exc}"}
                    return
            else:
                try:
                    msg = self.llm.chat(convo, tools=specs, model=self.model)
                except LLMError as exc:
                    yield {"type": "error", "text": f"Local inference error: {exc}"}
                    return

            tool_calls: list[dict[str, Any]] = msg.get("tool_calls") or []
            if not tool_calls:
                tool_calls = _extract_text_tool_calls(
                    msg.get("content"),
                    enable_react_recovery=self._enable_react_recovery,
                )

            # ---- Loop safety: detect repetitive patterns ----
            if tool_calls and self._detect_agent_loop(tool_calls):
                log_action(
                    "tool-agent",
                    "Agent loop detected: stopping for safety",
                    zone=Zone.YELLOW,
                )
                yield {
                    "type": "error",
                    "text": (
                        "Agent loop detected: the model repeated the same action(s) "
                        "without making progress. Stopped for safety. "
                        "Try rephrasing your request."
                    ),
                }
                yield {"type": "done"}
                return
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
                if streamed_text:
                    yield from self._finish_streamed(str(msg.get("content", "")))
                else:
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
                        yield tool_loop_helpers.format_earned_autonomy_event(
                            name, args, call_id
                        )
                        output, status, failed = self._dispatch(name, args)
                    else:
                        # A caution action the human hasn't authorised yet: pause the
                        # whole turn and ask. The turn is *resumable* -- the frontend
                        # re-calls /api/generate with the command/edit whitelisted, so
                        # we return here without applying it, recording no assistant
                        # answer (the paused turn is replayed, not continued mid-stream).
                        pause_event = tool_loop_helpers.format_human_required_event(
                            name, args, output, call_id
                        )
                        # S2 (approval-resume continuation, ratified option A):
                        # attach the CONVO TAIL -- everything this turn appended
                        # on top of the initial [system]+messages prefix -- so
                        # main.py can stash it for replay on resume. The prefix
                        # length is exactly 1 (system) + len(messages) BEFORE any
                        # resume_tail/grant-anchor splicing, since those are
                        # themselves prior-turn history the resumed turn should
                        # carry forward too (multi-pause chains compose: each
                        # pause stashes the FULL current tail). The assistant
                        # message carrying THIS tool_call was already appended
                        # to convo above (line ~861) before this per-call dispatch
                        # loop began, so the slice already ends with it -- no
                        # synthetic re-append needed. Popped off the event by
                        # main.py before it reaches the SSE payload -- this key
                        # must NEVER be emitted to the client.
                        pause_event["_convo_tail"] = list(convo[1 + len(messages):])
                        yield pause_event
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
                        result_event["target"] = str(args.get("command", ""))
                    yield result_event
                    if name == "plan" and getattr(self, "_last_native_source", None) is not None:
                        ns = self._last_native_source
                        yield {
                            "type": "native_plan",
                            "goal": ns.goal_pattern,
                            "source": ns.source,
                            "source_id": ns.source_id,
                            "relevance": ns.relevance_score,
                            "evidence_confidence": ns.evidence_confidence,
                            "preconditions_met": ns.preconditions_met,
                            "step_count": len(ns.steps),
                        }
                        self._last_native_source = None
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
                            pending_lessons, str(args.get("command", "")), output, index
                        )
                elif name in ("edit_file", "create_file") and status == "ok":
                    # A write actually landed. Force a verification so the
                    # AUTHORITATIVE PASS/FAIL -- not the model's narration -- is the
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
        tool_loop_helpers.grant_earned(
            name, args, self.approved_edits, self.approved_creations
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
        # test the instant it lands -- before its sibling module is applied -- fails on
        # the missing import and records a FALSE verified_failure even though the
        # finished files are correct. Landing every write first means each test sees
        # its module on disk, so the verdict reflects the code, not the write order.
        applied: list[tuple[int, str, str]] = []  # (index, filepath, action_type)
        for index, (filepath, content) in enumerate(self.approved_creations.items()):
            output, status, _ = self._create_file(filepath, content)
            call_id = f"grant-create-{index}"
            if status in ("ok", "noop"):
                # The applied (or previously-landed) grant IS a step of this
                # workflow. Without a tool_call frame the resume turn's
                # workflow_steps stays empty and record_outcome never calls
                # skills.record_attempt -- the clean supervised path (pause ->
                # approve -> grant applies -> STRONG verify) could never mint
                # a skill. noop replays yield it too so the FINAL (done)
                # replay's recipe carries every write of the approval chain.
                yield {"type": "tool_call", "tool": "create_file",
                       "input": {"filepath": filepath}, "id": call_id}
            if status == "noop":
                # Already landed on an earlier replay -- STILL queue it for verify so
                # the FINAL (done) replay carries the verdict. Skipping it loses the
                # evidence recorded on the apply-replay and the turn reads 'unverified'.
                applied.append((index, filepath, "create_file"))
                continue
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
            call_id = f"grant-edit-{index}"
            if status in ("ok", "noop"):
                # Same workflow-step accounting as granted creations above.
                yield {"type": "tool_call", "tool": "edit_file",
                       "input": {"filepath": filepath}, "id": call_id}
            if status == "noop":
                applied.append((index, filepath, "edit_file"))  # verify on the done-replay too
                continue
            if status == "ok":
                yield {"type": "tool_result", "tool": "edit_file",
                       "output": output[:_PREVIEW_LIMIT], "id": call_id}
                convo.append({"role": "tool", "content": output[:_TOOL_RESULT_LIMIT]})
                applied.append((index, filepath, "edit_file"))
            else:
                yield {"type": "tool_blocked", "tool": "edit_file",
                       "reason": output[:_PREVIEW_LIMIT], "id": call_id}
                convo.append({"role": "tool", "content": output[:_TOOL_RESULT_LIMIT]})
        # Phase 2 -- every granted file is now on disk; verify against the truth.
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
        yield from tool_loop_helpers.reflect(
            command,
            error_output,
            index,
            pending_lessons,
            self.on_failure,
            preview_limit=_PREVIEW_LIMIT,
        )

    def _confirm(
        self,
        pending_lessons: list[tuple[int, str]],
        command: str,
        output: str,
        index: int,
    ) -> Iterator[dict[str, Any]]:
        """Promote lessons only after their exact failed command succeeds."""
        passed_count, failed_count = parse_test_counts(output)
        strength = derive_strength(
            passed=True,
            passed_count=passed_count,
            failed_count=failed_count,
            command=command,
        )
        yield from tool_loop_helpers.confirm(
            pending_lessons,
            command,
            index,
            self.confirm_lesson,
            strength=strength,
            preview_limit=_PREVIEW_LIMIT,
        )

    def _auto_verify(
        self, filepath: str, index: int, convo: list[dict[str, Any]],
        *, action_type: str = "create_file",
    ) -> Iterator[dict[str, Any]]:
        # Force a verification after a successful write -- evidence over narration.
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
                f"(looked for {test_abs.name}); the change is UNVERIFIED -- "
                "do not assume it works."
            )
            yield {"type": "tool_result", "tool": "verify",
                   "output": note[:_PREVIEW_LIMIT], "id": f"autoverify-{index}"}
            convo.append({"role": "tool", "content": note})
            return

        # Express the test path relative to the executor's sandbox cwd
        # (SCOPE_ROOTS[0]) so the command carries no out-of-scope absolute path;
        # fall back to the absolute path only if it lies outside that root (then
        # the gateway's scope check judges it -- still fail-closed).
        roots = config.SCOPE_ROOTS
        cwd = roots[0].resolve() if roots else self.read_root
        try:
            test_arg = test_abs.relative_to(cwd).as_posix()
        except ValueError:
            test_arg = str(test_abs)
        command = build_auto_verify_command(test_arg)

        output, status, _failed = self._verify(command, approved=True)
        if status == "blocked":
            yield {"type": "tool_blocked", "tool": "verify",
                   "reason": output[:_PREVIEW_LIMIT], "id": f"autoverify-{index}"}
            verified_ok = False  # an unverifiable change is fail-closed
            verify_strength = VerificationStrength.NONE
        else:
            yield {"type": "tool_result", "tool": "verify",
                   "output": output[:_PREVIEW_LIMIT], "id": f"autoverify-{index}",
                   "target": command}
            verified_ok = output.lstrip().startswith("[VERIFY PASS]")
            verify_strength = strength_from_text(output)
        convo.append({"role": "tool", "content": output[:_TOOL_RESULT_LIMIT]})
        # Fold the authoritative verdict into the earned-autonomy evidence for
        # this write class: a PASS extends the streak (eventually graduating the
        # class to autonomous), a FAIL revokes it instantly. This is the ONLY
        # writer of autonomy evidence -- it is the verifier's word, never the
        # model's. (Skipped/non-Python writes record nothing.)
        if self.autonomy is not None:
            self.autonomy.record_outcome(
                action_type, filepath, success=verified_ok, strength=verify_strength
            )

    # ----------------------------------------------------------------- finish
    def _finish(self, content: str) -> Iterator[dict[str, Any]]:
        """Stream a final answer word-by-word, then surface any code block."""
        yield from tool_loop_helpers.finish_stream(
            content,
            code_fence=_CODE_FENCE,
            preview_limit=_PREVIEW_LIMIT,
        )

    def _finish_streamed(self, content: str) -> Iterator[dict[str, Any]]:
        """Emit code blocks and done — text was already streamed in real-time."""
        yield from tool_loop_helpers.finish_code_only(
            content,
            code_fence=_CODE_FENCE,
        )

    def _stream_iteration(
        self,
        convo: list[dict[str, Any]],
        specs: list[dict[str, Any]],
    ) -> Iterator[dict[str, Any]]:
        """Run one streaming LLM iteration, yielding text events in real-time.

        Text tokens are buffered during the stream. Only if the response has
        NO tool_calls (i.e. this is the final answer) are the buffered tokens
        flushed as ``text`` events. This prevents intermediate reasoning from
        leaking into the client's answer accumulator.

        Returns ``(msg_dict, streamed_text_bool)`` via generator return value.
        The caller uses ``msg, streamed = yield from self._stream_iteration(...)``
        to both forward events AND receive the structured result.
        """
        assert self.stream_fn is not None
        content_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        for chunk in self.stream_fn(convo, tools=specs, model=self.model):
            if isinstance(chunk, StreamFinished):
                tool_calls = chunk.tool_calls
                if not content_parts:
                    content_parts.append(chunk.content)
                break
            text = str(chunk)
            if text:
                content_parts.append(text)

        content = "".join(content_parts)
        msg: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
            return msg, False  # type: ignore[return-value]

        # Final answer — flush buffered tokens as real-time text events
        for part in content_parts:
            yield {"type": "text", "text": part}
        return msg, bool(content_parts)  # type: ignore[return-value]

    # --------------------------------------------------------------- dispatch
    def _dispatch(self, name: str, args: dict[str, Any]) -> tuple[str, str, bool]:
        """Route a tool call to its handler. Returns ``(output, status, failed)``.

        ``failed`` marks a genuine execution failure worth reflecting on (a
        non-zero exit, timeout, or launch error) -- never a security block or a
        scope denial, which are correct behaviour rather than mistakes.
        """
        if self.allowed_tools is not None and name not in self.allowed_tools:
            # Caste enforcement happens where tools execute, not where prompts
            # hope -- this also catches prose-rescued calls, which flow through
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
        if name == "browse":
            return self._browse(str(args.get("url", "")))
        if name == "plan":
            return self._plan(str(args.get("goal", "")))
        if name == "self_analyze":
            return self._self_analyze(str(args.get("path", "") or "aios"))
        if name == "propose_fixes":
            return self._propose_fixes(args.get("limit", 25))
        return (f"Unknown tool '{name}'.", "blocked", False)

    def _read_file(self, filepath: str) -> tuple[str, str, bool]:
        return tool_handlers.read_file(
            filepath,
            read_root=self.read_root,
            file_read_limit=_FILE_READ_LIMIT,
        )

    def _read_directory(self, path: str) -> tuple[str, str, bool]:
        return tool_handlers.read_directory(path, read_root=self.read_root)

    def _edit_file(self, filepath: str, old_string: str, new_string: str) -> tuple[str, str, bool]:
        return tool_handlers.edit_file(
            filepath,
            old_string,
            new_string,
            read_root=self.read_root,
            approved_edits=self.approved_edits,
            snapshot=self.snapshot,
            audit=self._audit,
        )

    def _create_file(self, filepath: str, content: str) -> tuple[str, str, bool]:
        return tool_handlers.create_file(
            filepath,
            content,
            read_root=self.read_root,
            approved_creations=self.approved_creations,
            snapshot=self.snapshot,
            audit=self._audit,
        )

    def _normalise_sandbox_paths(self, command: str) -> str:
        """Thin wrapper around :func:`tool_handlers._normalise_sandbox_paths`.

        Kept as a method because existing tests exercise it directly on the
        agent instance; the implementation itself lives in ``tool_handlers``.
        """
        return tool_handlers._normalise_sandbox_paths(command)

    def _verify(self, command: str, *, approved: bool = False) -> tuple[str, str, bool]:
        """Thin wrapper around :func:`tool_handlers.verify_command`."""
        return tool_handlers.verify_command(
            command,
            approved=approved,
            approved_commands=self.approved_commands,
            verifier=self._verifier,
            session_id=self.session_id,
        )

    def _browse(self, url: str) -> tuple[str, str, bool]:
        """Thin wrapper around :func:`tool_handlers.browse_url`."""
        return tool_handlers.browse_url(url, approved_commands=self.approved_commands)

    def _plan(self, goal: str) -> tuple[str, str, bool]:
        """Thin wrapper around :func:`tool_handlers.plan_task`."""
        result = tool_handlers.plan_task(goal, planner=self._planner)
        self._last_native_source = (
            getattr(self._planner, "_last_native_source", None)
            if self._planner is not None
            else None
        )
        return result

    def _self_analyze(self, path: str) -> tuple[str, str, bool]:
        """Thin wrapper around :func:`tool_handlers.self_analyze`."""
        return tool_handlers.self_analyze(
            path,
            read_root=self.read_root,
            tests_root=self.read_root / "tests",
            path_root=self.read_root,
        )

    def _propose_fixes(self, limit: Any) -> tuple[str, str, bool]:
        """Thin wrapper around :func:`tool_handlers.propose_fixes`."""
        return tool_handlers.propose_fixes(
            limit,
            read_root=self.read_root,
            tests_root=self.read_root / "tests",
            path_root=self.read_root,
            self_analysis_llm=self._self_analysis_llm,
        )

    def _execute(self, command: str) -> tuple[str, str, bool]:
        """Thin wrapper around :func:`tool_handlers.execute_terminal`."""
        return tool_handlers.execute_terminal(
            command,
            approved_commands=self.approved_commands,
            executor=self.executor,
            session_id=self.session_id,
        )
