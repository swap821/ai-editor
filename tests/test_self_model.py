"""The narrative self — a grounded autobiographical self-model.

A self-trait may be claimed ONLY from above-floor (STRONG) verified evidence:
the synthesizer needs >= min_attempts VERIFIED attempts, and its sources read only
verified events/lessons (Phase 1 excludes weak greens). Cold-start is silent — no
invented personality.
"""
from __future__ import annotations

from pathlib import Path

from aios.memory.db import get_connection, init_memory_db
from aios.memory.development import DevelopmentTracker
from aios.memory.mistake import MistakeMemory
from aios.memory.self_model import render, synthesize_self_model


class _FakeDev:
    def __init__(self, profile: dict) -> None:
        self._profile = profile

    def task_profile(self, **_: object) -> dict:
        return self._profile


class _FakeMistakes:
    def __init__(self, recurring: list) -> None:
        self._recurring = recurring

    def recurring(self, **_: object) -> list:
        return self._recurring


# --- synthesizer (grounded traits, fail-closed) -----------------------------

def test_strength_from_high_rate_over_min_attempts() -> None:
    model = synthesize_self_model(_FakeDev({"coding": (10, 0.9)}), _FakeMistakes([]), min_attempts=4)
    assert [t.subject for t in model.strengths] == ["coding"]
    assert model.strengths[0].kind == "strength"


def test_soft_spot_from_low_rate() -> None:
    model = synthesize_self_model(_FakeDev({"reasoning": (6, 0.33)}), _FakeMistakes([]), min_attempts=4)
    assert [t.subject for t in model.soft_spots] == ["reasoning"]
    assert model.soft_spots[0].kind == "soft_spot"


def test_no_trait_below_min_attempts() -> None:
    # Headline strength-gate: a perfect rate over too few verified attempts -> nothing.
    model = synthesize_self_model(_FakeDev({"coding": (2, 1.0)}), _FakeMistakes([]), min_attempts=4)
    assert model.is_empty


def test_mid_rate_is_neither_strength_nor_soft_spot() -> None:
    model = synthesize_self_model(
        _FakeDev({"general": (10, 0.65)}), _FakeMistakes([]),
        min_attempts=4, strong_rate=0.8, weak_rate=0.5,
    )
    assert model.is_empty


def test_caution_from_recurring_verified_lesson() -> None:
    model = synthesize_self_model(
        _FakeDev({}),
        _FakeMistakes([{"lesson_text": "re-run the failing test before claiming done", "occurrence_count": 3}]),
        min_attempts=4,
    )
    assert any("re-run the failing test" in t.detail for t in model.cautions)


def test_render_is_first_person_and_cites_evidence() -> None:
    model = synthesize_self_model(_FakeDev({"coding": (9, 0.9)}), _FakeMistakes([]), min_attempts=4)
    text = render(model)
    assert "coding" in text and "9" in text  # grounded in the evidence count
    assert "I'm" in text or "my" in text.lower()  # first-person self


def test_render_empty_model_is_empty_string() -> None:
    assert render(synthesize_self_model(_FakeDev({}), _FakeMistakes([]), min_attempts=4)) == ""


# --- store helpers (verified-only, real DB) ---------------------------------

def test_task_profile_counts_only_verified(tmp_path: Path) -> None:
    dev = DevelopmentTracker(db_path=tmp_path / "mem.db")
    for _ in range(4):
        dev.record("do the coding task", "verified_success", metadata={"task": "coding"})
    dev.record("do the coding task", "verified_failure", metadata={"task": "coding"})
    dev.record("do the coding task", "unverified", metadata={"task": "coding"})  # excluded

    attempts, rate = dev.task_profile()["coding"]
    assert attempts == 5  # 4 success + 1 failure; the unverified event is not counted
    assert rate == round(4 / 5, 6)


def test_recurring_returns_only_verified_repeated_lessons(tmp_path: Path) -> None:
    db = tmp_path / "mem.db"
    init_memory_db(db)
    rows = [
        ("verified", 3, "recurring verified lesson"),
        ("verified", 1, "verified but happened once"),
        ("pending", 5, "unverified though frequent"),
    ]
    with get_connection(db) as conn:
        for status, count, lesson in rows:
            conn.execute(
                "INSERT INTO mistake_pool (task_id, error_type, root_cause, fix_applied, "
                "lesson_text, confidence_delta, verification_status, occurrence_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("t", "E", "cause", "fix", lesson, -0.1, status, count),
            )
    texts = [row["lesson_text"] for row in MistakeMemory(db_path=db).recurring()]
    assert "recurring verified lesson" in texts
    assert "verified but happened once" not in texts  # occurrence_count == 1
    assert "unverified though frequent" not in texts  # not verified


# --- main.py recall helper (real stores, advisory) --------------------------

def test_recall_self_model_helper_integrates_real_stores(tmp_path: Path) -> None:
    from aios.api.main import _recall_self_model

    db = tmp_path / "mem.db"
    dev = DevelopmentTracker(db_path=db)
    for _ in range(5):
        dev.record("do the coding task", "verified_success", metadata={"task": "coding"})

    text = _recall_self_model(dev, MistakeMemory(db_path=db))
    assert text and "coding" in text

    empty = tmp_path / "empty.db"
    assert _recall_self_model(DevelopmentTracker(db_path=empty), MistakeMemory(db_path=empty)) is None
