"""Reflection Agent — converts a failure into a structured, queryable lesson.

On an execution failure, :meth:`ReflectionAgent.reflect` asks the local LLM for
a structured post-mortem, validates and clamps it, then writes it to the L4
Mistake pool. Repeated failures of the same kind on the same task increment an
occurrence counter instead of duplicating. Lessons are written ``pending`` and
promoted to ``verified`` via :meth:`confirm_lesson` once they prove themselves
on a later task.

Safeguards (Blueprint Q6):
  * Malformed or incomplete LLM output is rejected *before* any DB write.
  * ``confidence_delta`` is clamped to ``[-1.0, 0.0]`` by the storage layer, so
    a lesson can only reduce the planner's confidence, never inflate it.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from aios import config
from aios.core.llm import LLMClient, OllamaClient
from aios.core.verification_strength import VerificationStrength
from aios.memory.mistake import MistakeMemory

logger = logging.getLogger(__name__)

REFLECT_SYSTEM_PROMPT = """You are a Reflection Agent for a supervised AI operating system.
Analyse the failed action, identify the root cause, and formulate a generalised lesson so
the primary agent does not repeat the mistake.

Respond with ONLY a single valid JSON object, no prose and no code fences, matching this
schema exactly:
{
  "error_type": "short category, e.g. 'PathNotFound', 'SyntaxError', 'Timeout'",
  "root_cause": "detailed explanation of why it failed",
  "fix_applied": "the specific remediation for this case",
  "lesson_text": "a generalised rule to avoid this class of error in future",
  "confidence_delta": -0.1
}
confidence_delta must be a negative number between -1.0 and 0.0."""

REFLECT_USER_TEMPLATE = "Action attempted:\n{command}\n\nError output:\n{error_output}"

#: Fields that must be present and non-empty for a lesson to be accepted.
_REQUIRED_KEYS = ("error_type", "root_cause", "lesson_text")
#: Greedy match to pull the JSON object out of otherwise-noisy LLM text.
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class ReflectionError(RuntimeError):
    """Raised when the LLM output cannot be parsed into a valid lesson."""


@dataclass(frozen=True)
class Reflection:
    """The structured outcome of a reflection, as written to the Mistake pool."""

    mistake_id: int
    task_id: str
    error_type: str
    root_cause: str
    fix_applied: str
    lesson_text: str
    confidence_delta: float
    recurrence: bool


def _parse_reflection(raw: str) -> dict:
    """Extract and validate the JSON lesson object from raw LLM text."""
    if not raw or not raw.strip():
        raise ReflectionError("Empty LLM response.")
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    match = _JSON_OBJECT.search(cleaned)
    if not match:
        raise ReflectionError("No JSON object found in LLM response.")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ReflectionError(f"Malformed JSON in LLM response: {exc}") from exc
    if not isinstance(data, dict):
        raise ReflectionError("LLM response JSON is not an object.")

    # Accept the legacy 'suggested_fix' alias for 'fix_applied'.
    if "fix_applied" not in data and "suggested_fix" in data:
        data["fix_applied"] = data["suggested_fix"]
    data.setdefault("fix_applied", "")

    missing = [key for key in _REQUIRED_KEYS if not str(data.get(key, "")).strip()]
    if missing:
        raise ReflectionError(f"Lesson missing required field(s): {', '.join(missing)}")
    return data


class ReflectionAgent:
    """Analyses failures and records structured lessons in the Mistake pool."""

    def __init__(
        self,
        llm: LLMClient,
        *,
        mistakes: Optional[MistakeMemory] = None,
        db_path: Path = config.MEMORY_DB_PATH,
    ) -> None:
        self.llm = llm
        self.mistakes = mistakes or MistakeMemory(db_path)

    #: How many times to ask the model for a parseable lesson before giving up.
    #: ``json_mode`` makes a valid JSON object the norm, but a small local model
    #: can still occasionally emit a field-incomplete one; one cheap retry (the
    #: sampler varies at temperature > 0) recovers the rare miss.
    _MAX_REFLECT_ATTEMPTS = 2

    def _complete_reflection(self, prompt: str) -> str:
        """Ask the LLM for a lesson, requesting JSON-constrained decoding when the
        backing client is a local Ollama model.

        A small local model (``llama3.2:3b``) reliably starts a JSON object but
        trails off into prose, so the greedy extractor finds no complete object
        and the whole reflection is lost. Ollama's ``format: "json"`` grammar
        constraint fixes this at the source (measured 0/5 -> 5/5 parseable on the
        real multi-failure verify output). Cloud clients keep the plain path.
        """
        if isinstance(self.llm, OllamaClient):
            return self.llm.complete(
                prompt, system=REFLECT_SYSTEM_PROMPT, json_mode=True
            )
        return self.llm.complete(prompt, system=REFLECT_SYSTEM_PROMPT)

    def _reflect_parsed(self, prompt: str) -> dict:
        """Complete and parse a lesson, retrying a bounded number of times on an
        unparseable response before surfacing the :class:`ReflectionError`."""
        last_error: Optional[ReflectionError] = None
        for _ in range(self._MAX_REFLECT_ATTEMPTS):
            raw = self._complete_reflection(prompt)
            try:
                return _parse_reflection(raw)
            except ReflectionError as exc:
                last_error = exc
        raise last_error or ReflectionError("Reflection produced no output.")

    def reflect(
        self,
        command: str,
        error_output: str,
        *,
        task_id: Optional[str] = None,
    ) -> Optional[Reflection]:
        """Analyse one failure and persist a structured lesson.

        Args:
            command: The action/command that failed.
            error_output: Captured error text (truncated to 2000 chars for the prompt).
            task_id: Stable task identifier. Reusing it across calls enables
                recurrence detection; a random id is generated when omitted.

        Returns:
            The :class:`Reflection` that was written (or whose occurrence count
            was incremented on a recurrence).

        Raises:
            ReflectionError: If the LLM output is unparseable or incomplete.
        """
        if config.OFFLINE_MODE:
            logger.info("reflection skipped: offline mode")
            return None
        task_id = task_id or uuid.uuid4().hex
        prompt = REFLECT_USER_TEMPLATE.format(
            command=command, error_output=error_output[:2000]
        )
        data = self._reflect_parsed(prompt)

        try:
            confidence_delta = float(data.get("confidence_delta", -0.1))
        except (TypeError, ValueError):
            confidence_delta = -0.1

        error_type = str(data["error_type"]).strip()
        root_cause = str(data["root_cause"]).strip()
        fix_applied = str(data["fix_applied"]).strip()
        lesson_text = str(data["lesson_text"]).strip()

        mistake_id, recurrence = self.mistakes.record_or_increment(
            task_id=task_id,
            error_type=error_type,
            root_cause=root_cause,
            fix_applied=fix_applied,
            lesson_text=lesson_text,
            confidence_delta=confidence_delta,
            failed_command=command,
        )

        # Re-read the stored (clamped) delta so the return value is accurate.
        stored = self.mistakes.get(mistake_id)
        stored_delta = float(stored["confidence_delta"]) if stored else confidence_delta

        return Reflection(
            mistake_id=mistake_id,
            task_id=task_id,
            error_type=error_type,
            root_cause=root_cause,
            fix_applied=fix_applied,
            lesson_text=lesson_text,
            confidence_delta=stored_delta,
            recurrence=recurrence,
        )

    def confirm_lesson(
        self,
        mistake_id: int,
        *,
        strength: VerificationStrength = VerificationStrength.STRONG,
    ) -> None:
        """Promote a lesson after it proves itself with strong enough evidence."""
        self.mistakes.promote(mistake_id, strength=strength)

    def pending_command_pairs(self, task_id: str) -> list[tuple[int, str]]:
        """``(mistake_id, failed_command)`` for this task's pending lessons.

        Used to seed the tool loop's fail->confirm tracker at the start of a turn
        so a lesson recorded before an approval pause is still promoted when its
        exact command later succeeds (the in-memory tracker is per-run())."""
        return self.mistakes.pending_command_pairs(task_id)

    def recall_pending(self, task_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Return this task's pending lessons as plain dicts for injection.

        Lets a later turn reason with (and ultimately verify) lessons learned in
        earlier turns of the same session. Each dict carries ``mistake_id``,
        ``error_type`` and ``lesson_text``.
        """
        rows = self.mistakes.pending_for_task(task_id, limit)
        return [
            {
                "mistake_id": int(row["id"]),
                "error_type": str(row["error_type"]),
                "lesson_text": str(row["lesson_text"]),
            }
            for row in rows
        ]

    def recall_relevant(
        self, task_text: str, task_id: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Recall same-task pending lessons plus verified cross-session lessons."""
        pending = [
            {**lesson, "verification_status": "pending", "relevance": 1.0}
            for lesson in self.recall_pending(task_id, limit)
        ]
        remaining = max(limit - len(pending), 0)
        verified = self.mistakes.relevant_verified(task_text, remaining)
        pending_ids = {lesson["mistake_id"] for lesson in pending}
        return pending + [
            lesson for lesson in verified if lesson["mistake_id"] not in pending_ids
        ]
