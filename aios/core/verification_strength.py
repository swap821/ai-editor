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

    NONE = 0  # failed / blocked / un-runnable — proves nothing
    WEAK = 1  # exit 0 only — ran and returned zero, asserted no behavior
    MEDIUM = 2  # a recognized checker passed (typecheck/lint) — not a behavior suite
    STRONG = 3  # a recognized test runner asserted passing behavior


# Recognized test runners (STRONG). Matched against the command's tokens so an
# arbitrary command echoing "N passed" cannot masquerade as a test suite.
_TEST_RUNNER_TOKENS: frozenset[str] = frozenset(
    {"pytest", "py.test", "jest", "vitest", "mocha", "unittest", "phpunit", "rspec"}
)
#: Interpreters that may front a ``-m <runner>`` invocation at the program position.
_PYTHON_PROGRAMS: frozenset[str] = frozenset({"python", "python3", "py"})
#: ``-m`` modules that count as a recognized test runner (``python -m pytest``).
_DASH_M_RUNNERS: frozenset[str] = frozenset({"pytest", "unittest"})
#: Multi-word runner invocations, matched ONLY at the program position (tokens[0:]).
_TEST_RUNNER_PAIRS: tuple[tuple[str, ...], ...] = (
    ("go", "test"),
    ("cargo", "test"),
    ("npm", "test"),
    ("npm", "run", "test"),
    ("yarn", "test"),
)
_CHECKER_TOKENS: frozenset[str] = frozenset(
    {"mypy", "pyright", "tsc", "ruff", "flake8", "eslint", "pylint", "tslint"}
)
#: Multi-word checker invocations, matched ONLY at the program position.
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


def _program_starts_with(
    tokens: list[str], base: str, pairs: tuple[tuple[str, ...], ...]
) -> bool:
    """True if any *pair* sits at the PROGRAM POSITION.

    ``pair[0]`` is matched against the program BASENAME (so an absolute
    ``/usr/bin/npm`` still matches ``npm``); the remaining elements match the
    literal tokens that follow. Anchoring to the program position is the spoof
    defense: a runner token appearing in ARGUMENT position — e.g.
    ``echo go test 3 passed`` or ``echo -m pytest 1 passed`` — must NEVER
    classify, or a GREEN no-op could forge STRONG evidence (CVE-class bypass of
    the strength gate). A bare scan of all offsets is exactly that hole.
    """
    for pair in pairs:
        if (
            base == pair[0]
            and len(tokens) >= len(pair)
            and tuple(tokens[1 : len(pair)]) == pair[1:]
        ):
            return True
    return False


def _program_basename(tokens: list[str]) -> str:
    """The leaf name of the first token (e.g. C:/.../python.exe -> python.exe)."""
    if not tokens:
        return ""
    return tokens[0].rsplit("/", 1)[-1]


def _is_test_runner(command: str) -> bool:
    # A recognized runner ONLY at the program position: a bare runner basename
    # (pytest), a "python -m <runner>" front, or a multi-word runner (go test)
    # anchored at token 0 — NEVER a token anywhere, else "echo running pytest: 5
    # passed" or "echo -m pytest 1 passed" or "echo go test 3 passed" forges STRONG.
    tokens = _tokens(command)
    if not tokens:
        return False
    base = _program_basename(tokens).removesuffix(".exe")
    if base in _TEST_RUNNER_TOKENS:
        return True
    if (
        base in _PYTHON_PROGRAMS
        and len(tokens) >= 3
        and tokens[1] == "-m"
        and tokens[2] in _DASH_M_RUNNERS
    ):
        return True
    return _program_starts_with(tokens, base, _TEST_RUNNER_PAIRS)


def _is_checker(command: str) -> bool:
    tokens = _tokens(command)
    if not tokens:
        return False
    base = _program_basename(tokens).removesuffix(".exe")
    if base in _CHECKER_TOKENS:
        return True
    return _program_starts_with(tokens, base, _CHECKER_PAIRS)


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
    # STRONG = a recognized test runner that asserted PASSING behavior: it must have
    # reported at least one passing test and no failures. The ``passed_count > 0``
    # floor is load-bearing — without it a runner that collected NOTHING and exited 0
    # (``jest --passWithNoTests``, ``vitest --passWithNoTests``, ``pytest`` over an
    # empty path, an ``npm test`` wrapper whose script is a no-op) would mint STRONG
    # while asserting nothing. The command-aware program-position check is the spoof
    # defense (``echo "5 passed"`` stays WEAK); ``passed_count`` is the hollow-run
    # defense (a real runner that asserted nothing stays WEAK).
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
    floor = strength_from_name(
        config.VERIFICATION_PROMOTION_FLOOR, VerificationStrength.STRONG
    )
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
