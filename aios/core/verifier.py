"""Verifier layer (Blueprint stage 8): run a test command, judge pass/fail.

Sits after the Executor in the pipeline and embodies the "Trust Evidence, Not the
Model" principle — never assume an action worked because the LLM said so. The
Verifier runs a verification command (``pytest``, ``npm test``, …) through the
same security-gated, scope-constrained :class:`~aios.core.executor.Executor` the rest of
the OS uses, then judges the outcome by exit code and, when present, parsed
pass/fail counts. A failure yields a bounded negative confidence delta and — when
a reflection hook is wired — feeds the failure to it, closing the
execute → verify → reflect loop.

Fail-closed: a blocked, timed-out, or un-launchable verification counts as a
FAIL, never a silent pass.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from aios.core.executor import Executor

#: Reflection hook: ``(command, error_output) -> optional lesson summary``. The
#: same shape the agentic loop uses, so the verifier can drive reflection too.
FailureHook = Callable[[str, str], Optional[dict[str, Any]]]

#: pytest/jest-style summary fragments ("3 passed", "1 failed", "2 errors").
_PASSED = re.compile(r"(\d+)\s+passed", re.IGNORECASE)
_FAILED = re.compile(r"(\d+)\s+(?:failed|error|errors)", re.IGNORECASE)


@dataclass(frozen=True)
class VerifierResult:
    """Structured verdict from verifying an execution."""

    passed: bool
    summary: str
    confidence_delta: float  # 0.0 on pass; in [-1.0, 0.0) on fail
    passed_count: int = 0
    failed_count: int = 0
    exit_code: Optional[int] = None
    status: str = "OK"  # the underlying ExecutionResult.status


def _parse_counts(output: str) -> tuple[int, int]:
    """Extract ``(passed, failed)`` test counts from runner output (0 if absent)."""
    passed = _PASSED.search(output)
    failed = _FAILED.search(output)
    return (int(passed.group(1)) if passed else 0, int(failed.group(1)) if failed else 0)


class Verifier:
    """Runs a verification command and judges pass/fail (Blueprint stage 8)."""

    def __init__(self, executor: Executor, *, on_failure: Optional[FailureHook] = None) -> None:
        self.executor = executor
        #: Optional reflection hook fired on a genuine verification failure.
        self.on_failure = on_failure

    def verify(
        self,
        command: str,
        *,
        session_id: Optional[str] = None,
        approved: bool = False,
    ) -> VerifierResult:
        """Run *command* in the sandbox and return a structured verdict.

        Exit code 0 with no parsed failures => pass (delta 0.0). A non-zero exit,
        parsed failures, or a non-OK execution status (BLOCKED/TIMEOUT/ERROR) =>
        fail, fail-closed, with a bounded negative delta. On failure a reflection
        hook (if wired) is invoked with the command and captured output.
        """
        result = (
            self.executor.execute_approved(command)
            if approved
            else self.executor.execute(command, session_id=session_id)
        )
        output = ((result.stdout or "") + (result.stderr or "")).strip()

        if result.status != "OK":
            # Could not even run to completion (blocked / timeout / launch error):
            # cannot prove success, so fail-closed. A security BLOCK is correct
            # behaviour, not a mistake — only genuine run failures feed reflection.
            summary = f"[{result.status}] {result.reason}".strip()
            if result.status != "BLOCKED":
                self._maybe_reflect(command, summary or result.status)
            return VerifierResult(
                passed=False,
                summary=summary,
                confidence_delta=-0.1,
                exit_code=result.exit_code,
                status=result.status,
            )

        passed_count, failed_count = _parse_counts(output)
        # Trust the runner's exit code as the authoritative pass/fail signal
        # (pytest/jest exit non-zero on failures); the parsed counts only enrich
        # the summary/delta, so an incidental "error" in a passing run's output
        # cannot flip the verdict to FAIL.
        passed = result.exit_code == 0

        if passed:
            return VerifierResult(
                passed=True,
                summary=output[-500:] or "verification passed",
                confidence_delta=0.0,
                passed_count=passed_count,
                failed_count=failed_count,
                exit_code=result.exit_code,
                status="OK",
            )

        # Ran, but failed: bounded negative delta, scaled mildly by failure count.
        delta = max(-1.0, -0.1 * max(1, failed_count))
        self._maybe_reflect(command, output)
        return VerifierResult(
            passed=False,
            summary=output[-500:] or "verification failed",
            confidence_delta=delta,
            passed_count=passed_count,
            failed_count=failed_count,
            exit_code=result.exit_code,
            status="OK",
        )

    def _maybe_reflect(self, command: str, error_output: str) -> None:
        """Fire the reflection hook on failure; never let it break verification."""
        if self.on_failure is None:
            return
        try:
            self.on_failure(command, error_output)
        except Exception:  # noqa: BLE001 - reflection must never break verification
            pass
