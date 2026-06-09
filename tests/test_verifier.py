"""Verifier layer tests (Blueprint stage 8).

A fake-runner Executor exercises the real security gateway, so blocking is
genuine; the runner returns scripted pytest/jest-style output to drive the
pass/fail/delta logic deterministically — no shell, no model.
"""
from __future__ import annotations

from aios.core.executor import Executor
from aios.core.verifier import Verifier
from aios.security.gateway import RateLimiter


def _executor(runner):
    return Executor(runner=runner, rate_limiter=RateLimiter(), audit_log=lambda *a, **k: None)


def test_verify_pass_has_zero_delta() -> None:
    ex = _executor(lambda command, *, cwd, env, timeout_s: ("3 passed in 0.1s", "", 0))
    res = Verifier(ex).verify("pytest", approved=True)
    assert res.passed is True
    assert res.confidence_delta == 0.0
    assert res.passed_count == 3
    assert res.failed_count == 0


def test_verify_fail_has_negative_delta_and_reflects() -> None:
    ex = _executor(lambda command, *, cwd, env, timeout_s: ("", "1 failed, 2 passed", 1))
    seen: list[tuple[str, str]] = []
    res = Verifier(ex, on_failure=lambda c, o: seen.append((c, o))).verify("pytest", approved=True)
    assert res.passed is False
    assert res.confidence_delta < 0
    assert res.failed_count == 1
    # The failed verification feeds the reflection hook with the command + output.
    assert seen and seen[0][0] == "pytest"
    assert "1 failed" in seen[0][1]


def test_verify_blocked_command_fails_closed() -> None:
    # A RED command never runs; the verifier must treat that as FAIL, not pass.
    ex = _executor(lambda *a, **k: ("should-not-run", "", 0))
    res = Verifier(ex).verify("rm -rf /")
    assert res.passed is False
    assert res.status == "BLOCKED"
    assert res.confidence_delta < 0


def test_verify_nonzero_exit_without_counts_is_fail() -> None:
    ex = _executor(lambda command, *, cwd, env, timeout_s: ("boom", "", 2))
    res = Verifier(ex).verify("pytest", approved=True)
    assert res.passed is False
    assert res.confidence_delta < 0
    assert res.exit_code == 2


def test_verify_does_not_reflect_on_pass() -> None:
    ex = _executor(lambda command, *, cwd, env, timeout_s: ("5 passed", "", 0))
    seen: list[tuple[str, str]] = []
    res = Verifier(ex, on_failure=lambda c, o: seen.append((c, o))).verify("pytest", approved=True)
    assert res.passed is True
    assert seen == [], "a passing verification must not trigger reflection"


def test_verify_blocked_command_does_not_reflect() -> None:
    # A security BLOCK is correct behaviour, not a mistake to reflect on.
    ex = _executor(lambda *a, **k: ("should-not-run", "", 0))
    seen: list[str] = []
    res = Verifier(ex, on_failure=lambda c, o: seen.append(c)).verify("rm -rf /")
    assert res.passed is False and res.status == "BLOCKED"
    assert seen == []


def test_verify_pass_not_fooled_by_incidental_error_text() -> None:
    # Exit 0 is authoritative; an incidental "error" in output must not flip it.
    ex = _executor(lambda command, *, cwd, env, timeout_s: ("5 passed; cleaned up 1 error log", "", 0))
    res = Verifier(ex).verify("pytest", approved=True)
    assert res.passed is True
    assert res.confidence_delta == 0.0
