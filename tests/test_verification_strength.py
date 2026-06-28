"""Tests for the verification-strength taxonomy + the skills promotion gate (Phase 1)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from aios import config
from aios.core.verification_strength import (
    VerificationStrength,
    derive_strength,
    meets_promotion_floor,
    parse_test_counts,
    strength_from_name,
    strength_from_text,
)
from aios.memory.skills import SkillMemory


# --- derivation (deterministic + command-aware) ----------------------------

def test_strong_requires_test_runner_with_passing_assertions() -> None:
    assert derive_strength(
        passed=True, passed_count=3, failed_count=0, command="python -m pytest tests -q"
    ) is VerificationStrength.STRONG
    assert derive_strength(
        passed=True, passed_count=5, failed_count=0, command="pytest test_x.py"
    ) is VerificationStrength.STRONG


def test_bare_exit_zero_is_weak() -> None:
    assert derive_strength(
        passed=True, passed_count=0, failed_count=0, command="echo done"
    ) is VerificationStrength.WEAK


def test_recognized_checker_is_medium() -> None:
    assert derive_strength(
        passed=True, passed_count=0, failed_count=0, command="mypy ."
    ) is VerificationStrength.MEDIUM


def test_failure_is_none() -> None:
    assert derive_strength(
        passed=False, passed_count=0, failed_count=2, command="python -m pytest"
    ) is VerificationStrength.NONE


def test_stdout_spoof_cannot_forge_strong() -> None:
    """A non-test command whose 'output' claims passes must NOT be STRONG."""
    assert derive_strength(
        passed=True, passed_count=5, failed_count=0, command='echo "5 passed, 0 failed"'
    ) is VerificationStrength.WEAK


def test_runner_token_as_argument_cannot_forge_strong() -> None:
    """The HIGH bypass: a runner token in argument position must NOT be STRONG."""
    assert derive_strength(
        passed=True, passed_count=5, failed_count=0,
        command="echo running pytest now: 5 passed in 0.1s",
    ) is VerificationStrength.WEAK
    assert derive_strength(
        passed=True, passed_count=3, failed_count=0, command="grep passed pytest_notes.txt",
    ) is VerificationStrength.WEAK


def test_program_position_runners_still_strong() -> None:
    for cmd in ("pytest -q", "python -m pytest tests", f"{sys.executable} -m pytest x.py", "go test ./..."):
        assert derive_strength(
            passed=True, passed_count=2, failed_count=0, command=cmd
        ) is VerificationStrength.STRONG, cmd


def test_none_floor_is_clamped_to_strong(monkeypatch: pytest.MonkeyPatch) -> None:
    """A misconfigured NONE floor must not admit failed/weak verifications."""
    monkeypatch.setattr(config, "VERIFICATION_PROMOTION_FLOOR", "NONE")
    assert meets_promotion_floor(VerificationStrength.WEAK) is False
    assert meets_promotion_floor(VerificationStrength.NONE) is False
    assert meets_promotion_floor(VerificationStrength.STRONG) is True


def test_test_runner_with_failures_is_not_strong() -> None:
    assert derive_strength(
        passed=True, passed_count=3, failed_count=1, command="pytest"
    ) is not VerificationStrength.STRONG


def test_test_runner_that_asserted_nothing_is_not_strong() -> None:
    """The hollow-run defense: a recognized runner that collected/asserted NOTHING
    and exited 0 (``jest --passWithNoTests``, an empty ``pytest`` path, a no-op
    ``npm test`` wrapper) must stay WEAK — exit 0 with zero passes proves nothing."""
    for cmd in (
        "jest --passWithNoTests",
        "vitest run --passWithNoTests",
        "pytest -q",
        "npm test",
    ):
        assert derive_strength(
            passed=True, passed_count=0, failed_count=0, command=cmd
        ) is VerificationStrength.WEAK, cmd


# --- the gate ---------------------------------------------------------------

def test_floor_is_strong_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "VERIFICATION_PROMOTION_FLOOR", "STRONG")
    assert meets_promotion_floor(VerificationStrength.STRONG) is True
    assert meets_promotion_floor(VerificationStrength.MEDIUM) is False
    assert meets_promotion_floor(VerificationStrength.WEAK) is False
    assert meets_promotion_floor(VerificationStrength.NONE) is False


def test_floor_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "VERIFICATION_PROMOTION_FLOOR", "MEDIUM")
    assert meets_promotion_floor(VerificationStrength.MEDIUM) is True
    assert meets_promotion_floor(VerificationStrength.WEAK) is False


def test_unknown_floor_falls_back_to_strong(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "VERIFICATION_PROMOTION_FLOOR", "banana")
    assert meets_promotion_floor(VerificationStrength.MEDIUM) is False  # fail-closed


# --- parsing helpers --------------------------------------------------------

def test_strength_from_text_reads_token() -> None:
    assert strength_from_text("[VERIFY PASS] 3 passed, 0 failed (strength=STRONG)") \
        is VerificationStrength.STRONG
    assert strength_from_text("no token here") is VerificationStrength.NONE  # fail-closed


def test_strength_from_name_and_counts() -> None:
    assert strength_from_name("weak") is VerificationStrength.WEAK
    assert strength_from_name(None) is VerificationStrength.STRONG  # default
    assert parse_test_counts("3 passed, 1 failed") == (3, 1)


# --- the keystone: weak greens cannot imprint -------------------------------

def _skills(tmp_path: Path) -> SkillMemory:
    return SkillMemory(db_path=tmp_path / "mem.db")


def _status(skills: SkillMemory, skill_id: int) -> dict:
    return next(row for row in skills.list() if int(row["id"]) == skill_id)


def test_weak_greens_never_create_a_verified_skill(tmp_path: Path) -> None:
    skills = _skills(tmp_path)
    skill_id = 0
    for _ in range(3):
        skill_id = skills.record_attempt(
            "improve login", ["read", "edit"], success=True,
            strength=VerificationStrength.WEAK,
        )
    row = _status(skills, skill_id)
    assert row["status"] == "candidate"          # never promoted
    assert row["success_count"] == 0             # weak greens are not eligible
    assert row["weak_success_count"] == 3        # but they ARE recorded


def test_strong_greens_create_a_verified_skill(tmp_path: Path) -> None:
    skills = _skills(tmp_path)
    skill_id = 0
    for _ in range(3):
        skill_id = skills.record_attempt(
            "improve login", ["read", "edit"], success=True,
            strength=VerificationStrength.STRONG,
        )
    row = _status(skills, skill_id)
    assert row["status"] == "verified"
    assert row["success_count"] == 3
    assert row["weak_success_count"] == 0
    assert row["verification_strength"] == "STRONG"


def test_default_strength_preserves_existing_behavior(tmp_path: Path) -> None:
    """Callers that don't pass strength still promote (default STRONG)."""
    skills = _skills(tmp_path)
    skill_id = 0
    for _ in range(3):
        skill_id = skills.record_attempt("improve login", ["read", "edit"], success=True)
    assert _status(skills, skill_id)["status"] == "verified"


def test_medium_greens_are_ineligible_under_strong_floor(tmp_path: Path) -> None:
    skills = _skills(tmp_path)
    skill_id = 0
    for _ in range(3):
        skill_id = skills.record_attempt(
            "typecheck pass", ["edit"], success=True,
            strength=VerificationStrength.MEDIUM,
        )
    row = _status(skills, skill_id)
    assert row["status"] == "candidate"
    assert row["success_count"] == 0
    assert row["weak_success_count"] == 3
