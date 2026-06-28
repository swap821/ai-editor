"""Verification-strength taxonomy (GAGOS roadmap Phase 1 keystone).

"verified" is not uniform: a behavior-asserting test suite is STRONG evidence; a
bare ``exit 0`` proves nothing. The learning loop imprints on the verification
signal, so a weak green must never calibrate the future. This module defines the
strength levels, a deterministic + COMMAND-AWARE derivation (so a command merely
printing "5 passed" cannot forge STRONG — STRONG requires a recognized test
runner), and the promotion gate other learning sites consult.
"""
from __future__ import annotations

import re
from enum import IntEnum

from aios import config


class VerificationStrength(IntEnum):
    """Ordered evidence strength. Higher binds the future; lower may not."""

    NONE = 0    # failed / blocked / un-runnable — proves nothing
    WEAK = 1    # exit 0 only — ran and returned zero, asserted no behavior
    MEDIUM = 2  # a recognized checker passed (typecheck/lint) — not a behavior suite
    STRONG = 3  # a recognized test runner asserted passing behavior


# Recognized test runners (STRONG). Matched against the command's tokens so an
# arbitrary command echoing "N passed" cannot masquerade as a test suite.
_TEST_RUNNER_TOKENS: frozenset[str] = frozenset(
    {"pytest", "py.test", "jest", "vitest", "mocha", "unittest", "phpunit", "rspec"}
)
_TEST_RUNNER_PAIRS: tuple[tuple[str, ...], ...] = (
    ("-m", "pytest"),
    ("-m", "unittest"),
    ("go", "test"),
    ("cargo", "test"),
    ("npm", "test"),
    ("npm", "run", "test"),
    ("yarn", "test"),
)
_CHECKER_TOKENS: frozenset[str] = frozenset(
    {"mypy", "pyright", "tsc", "ruff", "flake8", "eslint", "pylint", "tslint"}
)
_CHECKER_PAIRS: tuple[tuple[str, ...], ...] = (
    ("npm", "run", "typecheck"),
    ("npm", "run", "lint"),
)

_STRENGTH_IN_TEXT = re.compile(r"strength=([A-Za-z]+)")
_PASSED = re.compile(r"(\d+)\s+passed", re.IGNORECASE)
_FAILED = re.compile(r"(\d+)\s+(?:failed|error|errors)", re.IGNORECASE)


def parse_test_counts(output: str) -> tuple[int, int]:
    """Extract ``(passed, failed)`` test counts from runner output (0 if absent)."""
    passed = _PASSED.search(output or "")
    failed = _FAILED.search(output or "")
    return (
        int(passed.group(1)) if passed else 0,
        int(failed.group(1)) if failed else 0,
    )


def _tokens(command: str) -> list[str]:
    return [tok.lower() for tok in command.replace("\\", "/").split()]


def _has_pair(tokens: list[str], pairs: tuple[tuple[str, ...], ...]) -> bool:
    for pair in pairs:
        n = len(pair)
        for i in range(len(tokens) - n + 1):
            if tuple(tokens[i : i + n]) == pair:
                return True
    return False


def _program_basename(tokens: list[str]) -> str:
    """The leaf name of the first token (e.g. C:/.../python.exe -> python.exe)."""
    if not tokens:
        return ""
    return tokens[0].rsplit("/", 1)[-1]


def _is_test_runner(command: str) -> bool:
    # PROGRAM-POSITION only (basename) or a structural pair like "-m pytest" —
    # NOT a bare token anywhere, else "echo running pytest: 5 passed" forges STRONG.
    tokens = _tokens(command)
    base = _program_basename(tokens).removesuffix(".exe")
    if base in _TEST_RUNNER_TOKENS:
        return True
    return _has_pair(tokens, _TEST_RUNNER_PAIRS)


def _is_checker(command: str) -> bool:
    tokens = _tokens(command)
    base = _program_basename(tokens).removesuffix(".exe")
    if base in _CHECKER_TOKENS:
        return True
    return _has_pair(tokens, _CHECKER_PAIRS)


def derive_strength(
    *,
    passed: bool,
    passed_count: int,
    failed_count: int,
    command: str,
) -> VerificationStrength:
    """Classify a verification outcome. Fail-closed + command-aware.

    STRONG requires a recognized test runner that reported passing assertions with
    no failures — so neither a non-test command nor stdout spoofing can reach it.
    """
    if not passed:
        return VerificationStrength.NONE
    if _is_test_runner(command) and passed_count > 0 and failed_count == 0:
        return VerificationStrength.STRONG
    if _is_checker(command):
        return VerificationStrength.MEDIUM
    return VerificationStrength.WEAK


def strength_from_name(
    name: object,
    default: VerificationStrength = VerificationStrength.STRONG,
) -> VerificationStrength:
    """Parse a level name (config/string) to the enum; unknown/None -> *default*."""
    if name is None:
        return default
    try:
        return VerificationStrength[str(name).strip().upper()]
    except (KeyError, AttributeError, ValueError):
        return default


def strength_from_text(
    text: str,
    default: VerificationStrength = VerificationStrength.NONE,
) -> VerificationStrength:
    """Read a ``strength=LEVEL`` token from text (the verify-evidence header).

    Default NONE: unlabeled evidence cannot be certified, so it is ineligible to
    promote (fail-closed)."""
    match = _STRENGTH_IN_TEXT.search(text or "")
    return strength_from_name(match.group(1), default) if match else default


def promotion_floor() -> VerificationStrength:
    """The minimum strength eligible to calibrate the future (default STRONG).

    A floor below WEAK (e.g. ``NONE`` — which would admit failed verifications)
    is clamped to STRONG: misconfiguration can only ever make the gate STRICTER.
    """
    floor = strength_from_name(config.VERIFICATION_PROMOTION_FLOOR, VerificationStrength.STRONG)
    return floor if floor >= VerificationStrength.WEAK else VerificationStrength.STRONG


def meets_promotion_floor(strength: VerificationStrength) -> bool:
    """True if *strength* is strong enough to promote a skill/pattern/confidence."""
    return strength >= promotion_floor()


__all__ = [
    "VerificationStrength",
    "derive_strength",
    "meets_promotion_floor",
    "parse_test_counts",
    "promotion_floor",
    "strength_from_name",
    "strength_from_text",
]
