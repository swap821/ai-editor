"""Strength gate extended to swarm_patterns + curriculum (roadmap Phase 1 completion).

(development's gate is the main.py recording-site downgrade of a weak verified_success
to 'unverified', reusing development's existing calibration exclusion.)
"""
from __future__ import annotations

from pathlib import Path

from aios.agents.swarm_patterns import SwarmPatternMemory
from aios.core.verification_strength import VerificationStrength
from aios.memory.curriculum import CurriculumManager

_GOAL = "improve the login page without backend changes"
PASS_STRONG = "[VERIFY PASS] 3 passed, 0 failed (exit 0) (strength=STRONG)"
PASS_WEAK = "[VERIFY PASS] 0 passed, 0 failed (exit 0) (strength=WEAK)"


# --- swarm patterns (verified only via recall) ------------------------------

def _swarm(tmp_path: Path) -> SwarmPatternMemory:
    return SwarmPatternMemory(db_path=tmp_path / "mem.db")


def test_swarm_weak_greens_never_verify(tmp_path: Path) -> None:
    sp = _swarm(tmp_path)
    for _ in range(3):
        sp.record_attempt(_GOAL, ["scout", "work"], success=True, strength=VerificationStrength.WEAK)
    assert sp.recall(_GOAL) == []  # never promoted to verified, never recalled


def test_swarm_strong_greens_verify(tmp_path: Path) -> None:
    sp = _swarm(tmp_path)
    for _ in range(2):  # min_successes=2 for swarm
        sp.record_attempt(_GOAL, ["scout", "work"], success=True, strength=VerificationStrength.STRONG)
    assert len(sp.recall(_GOAL)) == 1


def test_swarm_default_strength_promotes(tmp_path: Path) -> None:
    sp = _swarm(tmp_path)
    for _ in range(2):
        sp.record_attempt(_GOAL, ["scout", "work"], success=True)  # default STRONG
    assert len(sp.recall(_GOAL)) == 1


# --- curriculum mastery -----------------------------------------------------

def _task(cm: CurriculumManager, skill: str = "login") -> dict:
    return next(row for row in cm.list(skill))


def test_curriculum_weak_pass_does_not_advance_mastery(tmp_path: Path) -> None:
    cm = CurriculumManager(db_path=tmp_path / "mem.db")
    cm.add_task("login", 1, "do the login task")
    cm.record_matching("do the login task", passed=True, evidence=PASS_WEAK)
    row = _task(cm)
    assert row["attempts"] == 1
    assert row["successes"] == 0  # weak green recorded as attempt, not a success


def test_curriculum_strong_pass_counts_as_success(tmp_path: Path) -> None:
    cm = CurriculumManager(db_path=tmp_path / "mem.db")
    cm.add_task("login", 1, "do the login task")
    cm.record_matching("do the login task", passed=True, evidence=PASS_STRONG)
    row = _task(cm)
    assert row["attempts"] == 1
    assert row["successes"] == 1
