"""Pure helpers for the agentic tool-loop event stream.

These functions encapsulate the small, stateless formatting / bookkeeping
operations that shape the events yielded by :class:`~aios.agents.tool_agent.ToolAgent`.
Keeping them in a dedicated module lets the main agent focus on loop orchestration
and security dispatch while guaranteeing the SSE event contract stays stable.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, Callable, Optional

from aios.core.verification_strength import VerificationStrength, meets_promotion_floor
from aios.core.verifier import VerifierResult

#: A failure hook: given (command, error_output), return a lesson dict or None.
FailureHook = Callable[[str, str], Optional[dict[str, Any]]]
#: A confirmation hook: given a lesson's mistake id, promote it pending->verified.
ConfirmHook = Callable[[int], None]


def chunk_code(code: str, *, steps: int = 12) -> list[str]:
    """Break a complete code block into a growing sequence of prefix snapshots.

    Each snapshot is a prefix of ``code`` ending on a line boundary, and the final
    snapshot is always the whole block. This lets the UI reveal generated code
    incrementally even though the (function-calling) model returns it in one frame
    — honest "incremental reveal", not raw model tokens. A single line yields a
    single snapshot; empty input yields none.
    """
    if not code:
        return []
    lines = code.split("\n")
    if len(lines) <= 1:
        return [code]
    # Up to `steps` growing cut points spread across the lines, always ending on
    # the full block. Cutting on line boundaries keeps each snapshot a clean prefix.
    count = min(steps, len(lines))
    cut_indices = sorted(
        {max(1, round((i + 1) * len(lines) / count)) for i in range(count)}
    )
    snaps = ["\n".join(lines[:idx]) for idx in cut_indices]
    if snaps[-1] != code:
        snaps.append(code)
    return snaps


def finish_stream(
    content: str,
    *,
    code_fence: re.Pattern,
    preview_limit: int,
) -> Iterator[dict[str, Any]]:
    """Stream a final answer word-by-word, then surface any fenced code block.

    The emitted sequence is ``text`` events (one per whitespace-preserving word),
    then — for the first fenced block — a series of growing ``code_chunk`` events
    (incremental reveal) followed by the final ``code`` event, and a ``done``.
    """
    text = content.strip() or "(no answer)"
    for word in re.findall(r"\S+\s*", text):
        yield {"type": "text", "text": word}
    match = code_fence.search(text)
    if match:
        code = match.group(2).rstrip("\n")
        if code.strip():
            language = match.group(1) or "text"
            for partial in chunk_code(code):
                yield {"type": "code_chunk", "code": partial, "language": language}
            yield {"type": "code", "code": code, "language": language}
    yield {"type": "done"}


def finish_code_only(
    content: str,
    *,
    code_fence: re.Pattern,
) -> Iterator[dict[str, Any]]:
    """Emit code blocks and ``done`` — text was already streamed in real-time.

    Used by the streaming tool loop path (C4): text tokens were yielded as they
    arrived from the provider, so only code-block extraction and ``done`` remain.
    """
    text = content.strip()
    if not text:
        yield {"type": "done"}
        return
    match = code_fence.search(text)
    if match:
        code = match.group(2).rstrip("\n")
        if code.strip():
            language = match.group(1) or "text"
            for partial in chunk_code(code):
                yield {"type": "code_chunk", "code": partial, "language": language}
            yield {"type": "code", "code": code, "language": language}
    yield {"type": "done"}


def format_human_required_event(
    name: str,
    args: dict[str, Any],
    output: str,
    call_id: str,
) -> dict[str, Any]:
    """Build the ``human_required`` event that pauses a YELLOW action for approval.

    The returned dict reproduces the exact field layout the UI expects for
    commands, edits, creations, and browse requests.
    """
    event: dict[str, Any] = {
        "type": "human_required",
        "tool": name,
        "command": args.get("command", ""),
        "reason": output,
        "id": call_id,
    }
    if name == "edit_file":
        event["command"] = f"edit {args.get('filepath', '')}"
        event["filepath"] = str(args.get("filepath", ""))
        event["diff"] = output
        event["edit"] = {
            "filepath": str(args.get("filepath", "")),
            "old_string": str(args.get("old_string", "")),
            "new_string": str(args.get("new_string", "")),
        }
    elif name == "create_file":
        event["command"] = f"create {args.get('filepath', '')}"
        event["filepath"] = str(args.get("filepath", ""))
        event["diff"] = output
        event["creation"] = {
            "filepath": str(args.get("filepath", "")),
            "content": str(args.get("content", "")),
        }
    elif name == "browse":
        event["command"] = f"browse {args.get('url', '')}"
    return event


def format_earned_autonomy_event(
    name: str,
    args: dict[str, Any],
    call_id: str,
) -> dict[str, Any]:
    """Build the ``earned_autonomy`` event for an auto-granted write."""
    _target = str(args.get("filepath") or args.get("command") or "")
    return {
        "type": "earned_autonomy",
        "tool": name,
        "command": f"{name.split('_', 1)[0]} {_target}",
        "filepath": str(args.get("filepath", "")),
        "reason": "earned by verified-success evidence",
        "id": call_id,
    }


def grant_earned(
    name: str,
    args: dict[str, Any],
    approved_edits: dict[str, tuple[str, str]],
    approved_creations: dict[str, str],
) -> None:
    """Whitelist an earned write so its re-dispatch lands via the gated path.

    Mutates the same ``approved_edits`` / ``approved_creations`` dictionaries a
    human grant uses, so the re-dispatch runs the full scope-check -> snapshot ->
    audit -> write sequence unchanged. Only writes are earnable in v1.
    """
    if name == "create_file":
        approved_creations[str(args.get("filepath", ""))] = str(
            args.get("content", "")
        )
    elif name == "edit_file":
        approved_edits[str(args.get("filepath", ""))] = (
            str(args.get("old_string", "")),
            str(args.get("new_string", "")),
        )


def reflect(
    command: str,
    error_output: str,
    index: int,
    pending_lessons: list[tuple[int, str]],
    on_failure: FailureHook | None,
    *,
    preview_limit: int = 400,
) -> Iterator[dict[str, Any]]:
    """Run the failure hook, track the lesson id, and surface it as a step."""
    try:
        lesson = on_failure(command, error_output) if on_failure is not None else None
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
        "output": summary[:preview_limit],
        "id": f"reflect-{index}",
    }


def confirm(
    pending_lessons: list[tuple[int, str]],
    command: str,
    index: int,
    confirm_lesson: ConfirmHook | None,
    *,
    strength: VerificationStrength = VerificationStrength.STRONG,
    preview_limit: int = 400,
) -> Iterator[dict[str, Any]]:
    """Promote lessons only after their exact failed command succeeds."""
    promoted = [mistake_id for mistake_id, failed in pending_lessons if failed == command]
    if confirm_lesson is None or not promoted:
        return
    if not meets_promotion_floor(strength):
        return
    pending_lessons[:] = [item for item in pending_lessons if item[1] != command]
    for mistake_id in promoted:
        try:
            confirm_lesson(mistake_id)
        except Exception:  # noqa: BLE001 - confirmation must never break the loop
            pass
    yield {
        "type": "tool_result",
        "tool": "reflect",
        "output": f"Verified {len(promoted)} earlier lesson(s) — the fix worked.",
        "id": f"verify-{index}",
    }


def format_verifier_result(result: VerifierResult) -> tuple[str, str, bool]:
    """Map a pass/fail :class:`VerifierResult` to the loop's event shape.

    ``REQUIRE_APPROVAL`` and ``BLOCKED`` statuses are the caller's responsibility;
    this helper handles only the pass/fail verdict formatting.
    """
    verdict = "PASS" if result.passed else "FAIL"
    exit_str = "?" if result.exit_code is None else str(result.exit_code)
    header = (
        f"[VERIFY {verdict}] {result.passed_count} passed, "
        f"{result.failed_count} failed (exit {exit_str}) (strength={result.strength.name})"
    )
    body = result.summary.strip()
    output = f"{header}\n{body}" if body else header
    return (output, "ok", not result.passed)
