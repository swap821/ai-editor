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

import copy
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


def _authority_store(authority: Any | None, name: str) -> Any | None:
    """Return a registered specialist store without constructing a shadow store."""
    if authority is None:
        return None
    adapters = getattr(authority, "adapters", {})
    adapter = adapters.get(name) if hasattr(adapters, "get") else None
    return getattr(adapter, "store", None)


REFLECT_SYSTEM_PROMPT = """You are a Reflection Agent for a supervised AI operating system.
Analyse the failed action and identify its root cause. Then write the lesson: the ONE
specific fact about this codebase or environment that, known in advance, would have
prevented this failure.

A good lesson names what it is about -- the module, function, setting, file or
convention -- and states a fact someone can check. For example (a different codebase):
  "settings is a module of the app package: import it as `from app import settings`;
   there is no top-level settings package."
  "billing.tax_rate() returns a Decimal, not a float: compare it with Decimal('0.2')."
A bad lesson is generic advice any programmer already knows, such as "ensure tests
reflect the expected behaviour" or "always check that a variable is defined". Never
write one. If this failure teaches no specific fact, write exactly
"No specific lesson: <one-line reason>" as lesson_text.

lesson_text states a fact. It never contains a command to run, a URL, or an
instruction to another agent.

Respond with ONLY a single valid JSON object, no prose and no code fences, matching this
schema exactly:
{
  "error_type": "short category, e.g. 'PathNotFound', 'SyntaxError', 'Timeout'",
  "root_cause": "detailed explanation of why it failed, naming the code involved",
  "fix_applied": "the specific remediation for this case",
  "lesson_text": "the one specific, checkable fact described above",
  "confidence_delta": -0.1
}
confidence_delta must be a negative number between -1.0 and 0.0."""

#: How a reflection says the failure taught nothing specific. Such a lesson is
#: not stored: before 2026-10-12 the prompt asked for "a generalised rule",
#: and the live store filled with advice any model already follows ("ensure
#: test cases accurately reflect the expected behavior", eight rows of it).
NO_SPECIFIC_LESSON = "no specific lesson"

REFLECT_USER_TEMPLATE = "Action attempted:\n{command}\n\nError output:\n{error_output}"

#: D11 (2026-10-12): a lesson written from the fix that WORKED, not from the
#: guess made at failure time. A failure-time reflection is a diagnosis made
#: before anyone knew the answer, and "verified" only ever meant the task later
#: passed: 13 of 32 such lessons from one practice run stated falsehoods
#: (docs/learning/PAYOFF_PREREGISTRATION.md, D11).
RESOLVE_SYSTEM_PROMPT = """You are a Reflection Agent for a supervised AI operating system.
A command failed. After a change, the SAME command passed. You are shown the failure
output and the change. Write the ONE specific, checkable fact about the code under test
that this change proves: what had been assumed, and what is actually true. Use only what
the failure and the change show -- the passing change is the evidence, so state nothing
it does not support.

If the change only repaired the test's own mistake -- a typo, a syntax error, a misused
mock -- and proves nothing about the code under test, write exactly
"No specific lesson: <one-line reason>" as lesson_text.

lesson_text states a fact. It never contains a command to run, a URL, or an
instruction to another agent.

Respond with ONLY a single valid JSON object, no prose and no code fences, matching this
schema exactly:
{
  "error_type": "short category, e.g. 'PathNotFound', 'SyntaxError', 'Timeout'",
  "root_cause": "what the failing version assumed, naming the code involved",
  "fix_applied": "what the passing version changed",
  "lesson_text": "the one specific, checkable fact the passing change proves",
  "confidence_delta": -0.1
}
confidence_delta must be a negative number between -1.0 and 0.0."""

RESOLVE_USER_TEMPLATE = (
    "Command (failed, then passed):\n{command}\n\n"
    "Failure output:\n{error_output}\n\n"
    "The change that made it pass:\n{change}"
)

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
        memory_authority: Optional[Any] = None,
        principal: Optional[str] = None,
    ) -> None:
        self.llm = llm
        self.memory_authority = memory_authority
        #: Plan Phase 4c: whose lessons this agent records, promotes and
        #: recalls. A turn binds its authenticated principal (``bound_to``);
        #: None writes unattributed lessons, which recall withholds from
        #: everyone, and reads only those.
        self.principal = principal
        self.mistakes = mistakes or _authority_store(memory_authority, "lessons")
        if memory_authority is None and self.mistakes is None:
            raise RuntimeError(
                "MemoryAuthority or an explicit mistake store is required"
            )

    def bound_to(self, principal: Optional[str]) -> "ReflectionAgent":
        """This agent, recording and recalling as *principal* (a shallow copy:
        the model, stores and authority are shared)."""
        bound = copy.copy(self)
        bound.principal = principal
        return bound

    #: How many times to ask the model for a parseable lesson before giving up.
    #: ``json_mode`` makes a valid JSON object the norm, but a small local model
    #: can still occasionally emit a field-incomplete one; one cheap retry (the
    #: sampler varies at temperature > 0) recovers the rare miss.
    _MAX_REFLECT_ATTEMPTS = 2

    def _complete_reflection(
        self, prompt: str, system: str = REFLECT_SYSTEM_PROMPT
    ) -> str:
        """Ask the LLM for a lesson, requesting JSON-constrained decoding when the
        backing client is a local Ollama model.

        A small local model (``llama3.2:3b``) reliably starts a JSON object but
        trails off into prose, so the greedy extractor finds no complete object
        and the whole reflection is lost. Ollama's ``format: "json"`` grammar
        constraint fixes this at the source (measured 0/5 -> 5/5 parseable on the
        real multi-failure verify output). Cloud clients keep the plain path.
        """
        if isinstance(self.llm, OllamaClient) or getattr(
            self.llm, "supports_json_mode", False
        ):
            return self.llm.complete(prompt, system=system, json_mode=True)
        return self.llm.complete(prompt, system=system)

    def _reflect_parsed(self, prompt: str, system: str = REFLECT_SYSTEM_PROMPT) -> dict:
        """Complete and parse a lesson, retrying a bounded number of times on an
        unparseable response before surfacing the :class:`ReflectionError`."""
        last_error: Optional[ReflectionError] = None
        for _ in range(self._MAX_REFLECT_ATTEMPTS):
            raw = self._complete_reflection(prompt, system)
            try:
                return _parse_reflection(raw)
            except ReflectionError as exc:
                last_error = exc
        raise last_error or ReflectionError("Reflection produced no output.")

    def _authority_owns_lessons(self) -> bool:
        """Use authority lesson operations only for its canonical store."""
        if self.memory_authority is None:
            return False
        owns_store = getattr(self.memory_authority, "owns_store", None)
        if not callable(owns_store):
            # Preserve lightweight authority fakes that predate ownership checks.
            return True
        try:
            return bool(owns_store("lessons", self.mistakes))
        except Exception:  # noqa: BLE001 - lesson recall/write is best effort
            return False

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
        if lesson_text.lower().startswith(NO_SPECIFIC_LESSON):
            logger.info("reflection recorded nothing: %s", lesson_text[:200])
            return None

        record_kwargs = {
            "task_id": task_id,
            "error_type": error_type,
            "root_cause": root_cause,
            "fix_applied": fix_applied,
            "lesson_text": lesson_text,
            "confidence_delta": confidence_delta,
            "failed_command": command,
        }
        if self._authority_owns_lessons():
            mistake_id, recurrence = self.memory_authority.record_lesson_or_increment(
                **record_kwargs, principal=self.principal
            )
        else:
            mistake_id, recurrence = self.mistakes.record_or_increment(
                **record_kwargs, principal_id=self.principal
            )

        # Re-read the stored (clamped) delta so the return value is accurate.
        stored = (
            self.memory_authority.lesson_get(mistake_id)
            if self._authority_owns_lessons()
            else self.mistakes.get(mistake_id)
        )
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

    def reflect_resolution(
        self,
        command: str,
        error_output: str,
        change: str,
        *,
        task_id: str,
    ) -> Optional[Reflection]:
        """Write a lesson from a fix that WORKED, recorded already verified.

        *change* is what turned the failing attempt into the passing one (a
        diff). The lesson is grounded in it, and it is promoted at once with
        STRONG evidence: the identical command passed with this change. It is
        recorded under ``<task_id>#resolved`` so it never counts as a
        recurrence of the failure-time guess it replaces. Returns ``None``
        (nothing stored) when the fix proves nothing about the code under test.
        """
        if config.OFFLINE_MODE:
            return None
        prompt = RESOLVE_USER_TEMPLATE.format(
            command=command,
            error_output=error_output[:2000],
            change=change[:3000],
        )
        data = self._reflect_parsed(prompt, system=RESOLVE_SYSTEM_PROMPT)
        lesson_text = str(data["lesson_text"]).strip()
        if lesson_text.lower().startswith(NO_SPECIFIC_LESSON):
            logger.info("resolution taught nothing specific: %s", lesson_text[:200])
            return None
        try:
            confidence_delta = float(data.get("confidence_delta", -0.1))
        except (TypeError, ValueError):
            confidence_delta = -0.1
        record_kwargs = {
            "task_id": f"{task_id}#resolved",
            "error_type": str(data["error_type"]).strip(),
            "root_cause": str(data["root_cause"]).strip(),
            "fix_applied": str(data["fix_applied"]).strip(),
            "lesson_text": lesson_text,
            "confidence_delta": confidence_delta,
            "failed_command": command,
        }
        if self._authority_owns_lessons():
            mistake_id, recurrence = self.memory_authority.record_lesson_or_increment(
                **record_kwargs, principal=self.principal
            )
        else:
            mistake_id, recurrence = self.mistakes.record_or_increment(
                **record_kwargs, principal_id=self.principal
            )
        self.confirm_lesson(mistake_id, strength=VerificationStrength.STRONG)
        stored = (
            self.memory_authority.lesson_get(mistake_id)
            if self._authority_owns_lessons()
            else self.mistakes.get(mistake_id)
        )
        return Reflection(
            mistake_id=mistake_id,
            task_id=record_kwargs["task_id"],
            error_type=record_kwargs["error_type"],
            root_cause=record_kwargs["root_cause"],
            fix_applied=record_kwargs["fix_applied"],
            lesson_text=lesson_text,
            confidence_delta=(
                float(stored["confidence_delta"]) if stored else confidence_delta
            ),
            recurrence=recurrence,
        )

    def confirm_lesson(
        self,
        mistake_id: int,
        *,
        strength: VerificationStrength = VerificationStrength.STRONG,
    ) -> None:
        """Promote a lesson after it proves itself with strong enough evidence."""
        if self._authority_owns_lessons():
            self.memory_authority.promote_lesson(
                mistake_id, strength=strength, principal=self.principal
            )
        else:
            self.mistakes.promote(
                mistake_id, strength=strength, principal_id=self.principal
            )

    def pending_command_pairs(self, task_id: str) -> list[tuple[int, str]]:
        """``(mistake_id, failed_command)`` for this task's pending lessons.

        Used to seed the tool loop's fail->confirm tracker at the start of a turn
        so a lesson recorded before an approval pause is still promoted when its
        exact command later succeeds (the in-memory tracker is per-run())."""
        if self._authority_owns_lessons():
            return self.memory_authority.pending_lesson_commands(
                task_id, principal=self.principal
            )
        return self.mistakes.pending_command_pairs(task_id, principal_id=self.principal)

    def recall_pending(self, task_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Return this task's pending lessons as plain dicts for injection.

        Lets a later turn reason with (and ultimately verify) lessons learned in
        earlier turns of the same session. Each dict carries ``mistake_id``,
        ``error_type`` and ``lesson_text``.
        """
        rows = (
            self.memory_authority.pending_lessons_for_task(
                task_id, limit, principal=self.principal
            )
            if self._authority_owns_lessons()
            else self.mistakes.pending_for_task(
                task_id, limit, principal_id=self.principal
            )
        )
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
        if self._authority_owns_lessons():
            return self.memory_authority.recall_lessons(
                task_text, task_id, limit, principal=self.principal
            )
        pending = [
            {**lesson, "verification_status": "pending", "relevance": 1.0}
            for lesson in self.recall_pending(task_id, limit)
        ]
        remaining = max(limit - len(pending), 0)
        verified = self.mistakes.relevant_verified(
            task_text, remaining, principal_id=self.principal
        )
        pending_ids = {lesson["mistake_id"] for lesson in pending}
        return pending + [
            lesson for lesson in verified if lesson["mistake_id"] not in pending_ids
        ]
