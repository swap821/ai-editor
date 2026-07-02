"""Fuzzy (deterministic lexical) curriculum matching — the learning-loop slice.

Exact prompt equality almost never occurs on organic turns, so outside literal
replays the curriculum never accumulated attempts. Fuzzy matching attributes a
verified outcome to a curriculum task when — and only when — exactly ONE
available task clears the lexical relevance threshold. Zero or several
candidates attribute nothing (fail-closed): fuzzy can widen attempts, never
launder mastery — the STRONG promotion floor and held-out gates are untouched.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from aios.memory.curriculum import CurriculumManager

PASS_STRONG = "[VERIFY PASS] 3 passed, 0 failed (exit 0) (strength=STRONG)"
PASS_WEAK = "[VERIFY PASS] 0 passed, 0 failed (exit 0) (strength=WEAK)"

TASK_PROMPT = "write a python function that reverses a string"
# Token overlap with TASK_PROMPT: {write, python, function, string} = 4/6 ≈ 0.667
PARAPHRASE = "please write a python function reversing a string"


def _cm(tmp_path: Path, **kwargs) -> CurriculumManager:
    return CurriculumManager(db_path=tmp_path / "mem.db", **kwargs)


def test_paraphrase_attributes_to_single_clear_task(tmp_path: Path) -> None:
    cm = _cm(tmp_path)
    task_id = cm.add_task("string-ops", 1, TASK_PROMPT)
    updated = cm.record_matching(PARAPHRASE, passed=True, evidence=PASS_STRONG)
    assert updated == [task_id]
    row = cm.list("string-ops")[0]
    assert row["attempts"] == 1
    assert row["successes"] == 1


def test_unrelated_prompt_attributes_nothing(tmp_path: Path) -> None:
    cm = _cm(tmp_path)
    cm.add_task("string-ops", 1, TASK_PROMPT)
    updated = cm.record_matching(
        "summarize today's council mission ledger", passed=True, evidence=PASS_STRONG
    )
    assert updated == []
    assert cm.list("string-ops")[0]["attempts"] == 0


def test_ambiguous_candidates_attribute_nothing(tmp_path: Path) -> None:
    cm = _cm(tmp_path)
    cm.add_task("string-ops", 1, TASK_PROMPT)
    cm.add_task("string-ops", 1, "write a python function that reverses a list")
    updated = cm.record_matching(
        "write a python function that reverses things", passed=True, evidence=PASS_STRONG
    )
    assert updated == []
    for row in cm.list("string-ops"):
        assert row["attempts"] == 0


def test_fuzzy_disabled_restores_exact_only(tmp_path: Path) -> None:
    cm = _cm(tmp_path, fuzzy_matching=False)
    cm.add_task("string-ops", 1, TASK_PROMPT)
    assert cm.record_matching(PARAPHRASE, passed=True, evidence=PASS_STRONG) == []


def test_exact_match_still_wins_over_fuzzy(tmp_path: Path) -> None:
    cm = _cm(tmp_path)
    exact_id = cm.add_task("string-ops", 1, TASK_PROMPT)
    cm.add_task("list-ops", 1, "write a python function that reverses a list")
    updated = cm.record_matching(TASK_PROMPT, passed=True, evidence=PASS_STRONG)
    assert updated == [exact_id]


def test_exact_ambiguity_still_raises(tmp_path: Path) -> None:
    cm = _cm(tmp_path)
    cm.add_task("string-ops", 1, TASK_PROMPT)
    cm.add_task("other-skill", 1, TASK_PROMPT)
    with pytest.raises(ValueError):
        cm.record_matching(TASK_PROMPT, passed=True, evidence=PASS_STRONG)


def test_weak_pass_on_fuzzy_path_is_attempt_only(tmp_path: Path) -> None:
    cm = _cm(tmp_path)
    cm.add_task("string-ops", 1, TASK_PROMPT)
    updated = cm.record_matching(PARAPHRASE, passed=True, evidence=PASS_WEAK)
    assert len(updated) == 1
    row = cm.list("string-ops")[0]
    assert row["attempts"] == 1
    assert row["successes"] == 0


def test_threshold_is_respected(tmp_path: Path) -> None:
    cm = _cm(tmp_path, fuzzy_threshold=0.95)
    cm.add_task("string-ops", 1, TASK_PROMPT)
    assert cm.record_matching(PARAPHRASE, passed=True, evidence=PASS_STRONG) == []
