"""The powered payoff design: samples, a placebo arm, disjoint targets, retries.

Research: `docs/learning/PAYOFF_POWER_RESEARCH.md`. The operator decided
(2026-09-27) to judge a Bedrock cohort alongside the 7B, Holm-corrected. Each
addition here is a new way the number could lie, so each is pinned:

* K samples of one target are never counted as K independent pairs;
* the exact sign-flip test IS exact McNemar when there is one sample;
* the placebo is the production recall for OTHER work, never an item ON saw;
* calibration and judged targets cannot overlap;
* only a provider's "not now" is retried, and every retry is recorded;
* with more than one judged test, no raw p is printed as a verdict.
"""

from __future__ import annotations

import itertools
from types import SimpleNamespace

import pytest

import tools.learning_payoff as payoff
from tests.test_learning_payoff import (
    TestTheInstrumentIsProvenBeforeUse,
    _git_corpus,
    _target,
)
from aios.core.llm import LLMError
from tools.self_corpus import CorpusError


def _lesson(mistake_id: int) -> dict:
    """A recalled lesson with the fields the production block formats."""
    return {
        "mistake_id": mistake_id,
        "error_type": "AssertionError",
        "lesson_text": f"lesson {mistake_id}",
    }


def _arm(earned: bool, *, reached: bool = True, retries: int = 0) -> dict:
    return {"earned": earned, "reached_model": reached, "transport_retries": retries}


class TestTheExactTests:
    @pytest.mark.parametrize("b,c", list(itertools.product(range(8), range(8))))
    def test_sign_flip_is_mcnemar_with_one_sample(self, b: int, c: int) -> None:
        diffs = [1] * b + [-1] * c + [0] * 5
        assert payoff.sign_flip_exact(diffs) == pytest.approx(
            payoff.mcnemar_exact(b, c)
        )

    def test_known_value(self) -> None:
        # Three targets, each ON 2 samples ahead: sums {+-6, +-2}, 2 of 8 as extreme.
        assert payoff.sign_flip_exact([2, 2, 2]) == pytest.approx(0.25)

    def test_no_information_is_p_one(self) -> None:
        assert payoff.sign_flip_exact([]) == 1.0
        assert payoff.sign_flip_exact([0, 0, 0]) == 1.0

    def test_holm(self) -> None:
        adjusted = payoff.holm_adjust({"a": 0.01, "b": 0.04, "c": 0.03})
        assert adjusted == pytest.approx({"a": 0.03, "c": 0.06, "b": 0.06})

    def test_holm_never_rejects_more_than_raw(self) -> None:
        raw = {"x": 0.049, "y": 0.02}
        adjusted = payoff.holm_adjust(raw)
        assert all(adjusted[k] >= raw[k] for k in raw)
        assert adjusted["x"] > 0.05 or adjusted["y"] > 0.02


class TestTheTargetIsTheUnit:
    def _pair(self, on: list[bool], off: list[bool]) -> payoff.Pair:
        pair = payoff.Pair(
            target="t", first="on", on=_arm(on[0]), off=_arm(off[0]), comparable=True
        )
        pair.samples = {"on": [_arm(e) for e in on], "off": [_arm(e) for e in off]}
        return pair

    def test_k_samples_of_one_target_are_not_k_pairs(self) -> None:
        """Counted per sample, 3 wins would read as 3 discordant pairs. It is
        one target, and one target cannot be significant."""
        stats = payoff.summarise([self._pair([True] * 3, [False] * 3)])["novel"]
        assert stats["pairs"] == 1 and stats["samples"] == 3
        assert stats["on_only"] == 1
        assert stats["p_value"] == 1.0

    def test_six_targets_all_one_way_is_significant(self) -> None:
        pairs = [self._pair([True, True, False], [False] * 3) for _ in range(6)]
        stats = payoff.summarise(pairs)["novel"]
        assert stats["on_earned"] == 12 and stats["off_earned"] == 0
        assert stats["p_value"] == pytest.approx(2 / 64)

    def test_a_one_sample_run_keeps_its_old_numbers(self) -> None:
        pair = payoff.Pair(
            target="t", first="on", on=_arm(True), off=_arm(False), comparable=True
        )
        stats = payoff.summarise([pair])["novel"]
        assert (stats["samples"], stats["on_earned"], stats["on_only"]) == (1, 1, 1)
        assert "content_novel" not in payoff.summarise([pair])


class TestNovelOnly:
    def test_it_selects_unpractised_targets_alone(self) -> None:
        targets = [_target(function=f"f{i}") for i in range(6)]
        chosen, fresh, known = payoff.select_targets(
            targets, 10, lambda t: t.function in ("f0", "f2"), novel_only=True
        )
        assert [t.function for t in chosen] == ["f1", "f3", "f4", "f5"]
        assert (fresh, known) == (4, 0)

    def test_positive_control_default_still_alternates(self) -> None:
        targets = [_target(function=f"f{i}") for i in range(4)]
        chosen, _fresh, known = payoff.select_targets(
            targets, 4, lambda t: t.function in ("f0", "f2")
        )
        assert known == 2 and chosen[1].function == "f0"


class TestThePlacebo:
    """Deviation D5: recall gave every task the same 5 of 7 verified lessons,
    so the placebo is other STORED lessons recall did not pick."""

    def _store(self, tmp_path):
        import sqlite3

        db = tmp_path / "memory.sqlite"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE mistake_pool (id INTEGER PRIMARY KEY, error_type TEXT, "
            "lesson_text TEXT, verification_status TEXT)"
        )
        rows = [(i, "E", f"lesson {i}", "verified") for i in range(1, 8)]
        rows += [(i, "E", f"pending {i}", "pending") for i in range(8, 12)]
        rows += [(i, "E", f"retired {i}", "superseded") for i in range(12, 40)]
        conn.executemany("INSERT INTO mistake_pool VALUES (?,?,?,?)", rows)
        conn.commit()
        conn.close()
        return db

    def test_the_pool_is_verified_and_pending_never_retired(self, tmp_path) -> None:
        pool = payoff.placebo_pool(self._store(tmp_path))
        assert [item["mistake_id"] for item in pool] == list(range(1, 12))
        assert {item["verification_status"] for item in pool} == {"verified", "pending"}

    def test_it_never_shows_a_lesson_on_saw(self, tmp_path) -> None:
        pool = payoff.placebo_pool(self._store(tmp_path))
        own = [_lesson(i) for i in (1, 2, 3, 4, 5)]
        text, picked, matched = payoff.placebo_context(
            pool, own_lessons=own, own_skills=[], target_label="aios/x.py::f"
        )
        assert matched is True and len(picked) == 5
        assert not {item["mistake_id"] for item in picked} & {1, 2, 3, 4, 5}
        assert all(f"lesson {i}]" not in text for i in (1, 2, 3, 4, 5))

    def test_labels_are_the_stored_truth(self, tmp_path) -> None:
        pool = payoff.placebo_pool(self._store(tmp_path))
        own = [_lesson(i) for i in (1, 2, 3, 4, 5)]
        text, picked, _ = payoff.placebo_context(
            pool, own_lessons=own, own_skills=[], target_label="aios/x.py::f"
        )
        pending = [item for item in picked if item["verification_status"] == "pending"]
        assert pending, "only 2 verified remain, so pending lessons must appear"
        assert text.count("[pending;") == len(pending), "a pending lesson relabelled"

    def test_the_skills_block_is_on_s_own(self, tmp_path) -> None:
        pool = payoff.placebo_pool(self._store(tmp_path))
        skills = [
            {
                "skill_id": 9,
                "goal_pattern": "pin a function",
                "steps": ["verify: pytest"],
                "success_rate": 1.0,
                "strength": 1.0,
            }
        ]
        text, _picked, matched = payoff.placebo_context(
            pool,
            own_lessons=[_lesson(1)],
            own_skills=skills,
            target_label="aios/x.py::f",
        )
        assert matched and payoff.skills_prompt_block(skills) in text

    def test_it_is_seeded_per_target(self, tmp_path) -> None:
        pool = payoff.placebo_pool(self._store(tmp_path))
        own = [_lesson(1), _lesson(2)]

        def pick(label):
            return [
                item["mistake_id"]
                for item in payoff.placebo_context(
                    pool, own_lessons=own, own_skills=[], target_label=label
                )[1]
            ]

        assert pick("aios/a.py::f") == pick("aios/a.py::f"), "not reproducible"
        assert any(pick(f"aios/{i}.py::f") != pick("aios/a.py::f") for i in range(8))

    def test_the_boundary_is_exact_and_short_is_never_padded(self, tmp_path) -> None:
        pool = payoff.placebo_pool(self._store(tmp_path))  # 11 lessons
        # ON's lessons from outside the pool: all 11 remain candidates.
        exactly = [_lesson(100 + i) for i in range(11)]
        _t, picked, matched = payoff.placebo_context(
            pool, own_lessons=exactly, own_skills=[], target_label="t"
        )
        assert matched is True and len(picked) == 11
        _t, picked, matched = payoff.placebo_context(
            pool, own_lessons=exactly + [_lesson(200)], own_skills=[], target_label="t"
        )
        assert matched is False and picked == []

    def test_no_recalled_lesson_is_unmatched_not_a_copy_of_on(self, tmp_path) -> None:
        pool = payoff.placebo_pool(self._store(tmp_path))
        _t, _p, matched = payoff.placebo_context(
            pool, own_lessons=[], own_skills=[{"skill_id": 1}], target_label="t"
        )
        assert matched is False


class TestTransportRetry:
    @pytest.fixture()
    def arm(self, tmp_path, monkeypatch):
        corpus = _git_corpus(tmp_path)
        waits: list = []
        monkeypatch.setattr(payoff.time, "sleep", waits.append)
        monkeypatch.setattr(
            payoff,
            "grade_pin_test",
            lambda *a, **k: SimpleNamespace(
                earned=True, passes_clean=True, fails_when_mutated=True, notes=[]
            ),
        )

        def run(replies: list):
            def complete(client, prompt, *, system):
                reply = replies.pop(0)
                if isinstance(reply, Exception):
                    raise reply
                return reply

            monkeypatch.setattr(payoff, "complete_via", complete)
            return payoff.run_arm(
                corpus,
                object(),
                _target(),
                arm="on",
                extra_context="",
                lessons=0,
                skills_count=0,
            )

        return run, waits

    CODE = "```python\ndef test_x():\n    assert True\n```"

    def test_throttling_is_retried_and_recorded(self, arm) -> None:
        run, waits = arm
        result = run([LLMError("An error occurred (ThrottlingException)"), self.CODE])
        assert result.reached_model and result.earned
        assert result.transport_retries == 1 and waits == [15]

    def test_a_validation_error_is_never_retried(self, arm) -> None:
        run, waits = arm
        result = run([LLMError("ValidationException: bad model id"), self.CODE])
        assert result.outcome == "model_error" and not result.reached_model
        assert result.transport_retries == 0 and waits == []

    def test_retries_are_bounded(self, arm) -> None:
        run, waits = arm
        throttled = LLMError("ThrottlingException")
        result = run([throttled] * 4 + [self.CODE])
        assert result.outcome == "model_error"
        assert result.transport_retries == 3 and waits == [15, 45, 90]


class TestTheRunLoop:
    def _wire(self, tmp_path, monkeypatch, targets, outcome):
        TestTheInstrumentIsProvenBeforeUse()._wire(
            tmp_path, monkeypatch, control_ok=True, captured=[]
        )
        monkeypatch.setattr(payoff, "collect_targets", lambda root: list(targets))
        ids = itertools.count(100)

        def recall(reflector, skills, query, session_id):
            lessons = [_lesson(next(ids)), _lesson(next(ids))]
            return "remembered", lessons, []

        monkeypatch.setattr(payoff, "recalled_context", recall)
        # Classification only; the stub store has no lesson columns to read.
        monkeypatch.setattr(payoff, "enrich_lessons", lambda db, lessons: lessons)
        monkeypatch.setattr(
            payoff, "placebo_pool", lambda db: [_lesson(i) for i in range(1, 60)]
        )
        calls: list = []

        def run_arm(
            corpus, client, target, *, arm, extra_context, lessons, skills_count
        ):
            calls.append((target.function, arm, extra_context))
            return payoff.ArmResult(
                arm=arm, reached_model=True, earned=outcome(target, arm, len(calls))
            )

        monkeypatch.setattr(payoff, "run_arm", run_arm)
        return calls

    def test_samples_and_a_rotating_placebo(self, tmp_path, monkeypatch) -> None:
        targets = [_target(function=f"f{i}") for i in range(3)]
        calls = self._wire(
            tmp_path, monkeypatch, targets, lambda t, arm, n: arm == "on"
        )
        pairs, _run, _sha = payoff.run_benchmark(
            models="x", targets=3, model_timeout=1, samples=2, placebo=True
        )
        assert len(calls) == 3 * 3 * 2
        firsts = [p.first for p in pairs]
        assert firsts == ["on", "off", "placebo"], "arm order rotates by target"
        for pair in pairs:
            assert {arm: len(runs) for arm, runs in pair.samples.items()} == {
                "on": 2,
                "off": 2,
                "placebo": 2,
            }
            assert pair.comparable and pair.placebo_comparable
        placebo_contexts = {c[2] for c in calls if c[1] == "placebo"}
        assert placebo_contexts and all(c for c in placebo_contexts)
        summary = payoff.summarise(pairs)
        assert summary["content_novel"]["pairs"] == 3
        assert summary["content_novel"]["on_earned"] == 6
        assert summary["content_novel"]["off_earned"] == 0

    def test_excluded_targets_are_never_selected(self, tmp_path, monkeypatch) -> None:
        targets = [_target(function=f"f{i}") for i in range(4)]
        self._wire(tmp_path, monkeypatch, targets, lambda t, arm, n: False)
        pairs, _run, _sha = payoff.run_benchmark(
            models="x",
            targets=4,
            model_timeout=1,
            exclude_labels=[targets[0].label, targets[2].label],
        )
        assert [p.target for p in pairs] == [targets[1].label, targets[3].label]

    def test_a_frozen_list_overlapping_the_excluded_set_is_refused(
        self, tmp_path, monkeypatch
    ) -> None:
        targets = [_target(function=f"f{i}") for i in range(2)]
        self._wire(tmp_path, monkeypatch, targets, lambda t, arm, n: False)
        with pytest.raises(CorpusError, match="disjoint"):
            payoff.run_benchmark(
                models="x",
                targets=2,
                model_timeout=1,
                target_labels=[targets[0].label],
                exclude_labels=[targets[0].label],
            )

    def test_an_unreached_sample_makes_the_target_not_comparable(
        self, tmp_path, monkeypatch
    ) -> None:
        targets = [_target(function="f0")]
        self._wire(tmp_path, monkeypatch, targets, lambda t, arm, n: True)

        seen_off: list = []

        def run_arm(
            corpus, client, target, *, arm, extra_context, lessons, skills_count
        ):
            # Only OFF's SECOND sample fails to reach the model: checking the
            # first sample alone would call this target comparable.
            if arm == "off":
                seen_off.append(1)
            reached = not (arm == "off" and len(seen_off) == 2)
            return payoff.ArmResult(arm=arm, reached_model=reached, earned=True)

        monkeypatch.setattr(payoff, "run_arm", run_arm)
        pairs, _run, _sha = payoff.run_benchmark(
            models="x", targets=1, model_timeout=1, samples=3, placebo=True
        )
        assert pairs[0].comparable is False
        assert pairs[0].placebo_comparable is False

    def test_an_unreached_placebo_leaves_on_off_standing(
        self, tmp_path, monkeypatch
    ) -> None:
        """Positive control for the placebo's own exclusion: ON vs OFF is still
        scored, but the content comparison is not, and it says why."""
        targets = [_target(function="f0")]
        self._wire(tmp_path, monkeypatch, targets, lambda t, arm, n: True)

        def run_arm(
            corpus, client, target, *, arm, extra_context, lessons, skills_count
        ):
            return payoff.ArmResult(
                arm=arm, reached_model=(arm != "placebo"), earned=True
            )

        monkeypatch.setattr(payoff, "run_arm", run_arm)
        pairs, _run, _sha = payoff.run_benchmark(
            models="x", targets=1, model_timeout=1, samples=2, placebo=True
        )
        assert pairs[0].comparable is True
        assert pairs[0].placebo_comparable is False
        assert "never reached" in pairs[0].placebo_reason
        assert payoff.summarise(pairs)["content_novel"]["pairs"] == 0


class TestAFamilyIsNeverOneRawP:
    def test_with_a_placebo_no_raw_p_is_printed_as_a_verdict(self, monkeypatch) -> None:
        pairs = []
        for _ in range(8):
            pair = payoff.Pair(
                target="t",
                first="on",
                on=_arm(True),
                off=_arm(False),
                placebo=_arm(False),
                comparable=True,
                placebo_comparable=True,
            )
            pairs.append(pair)
        monkeypatch.setattr(payoff, "summarise", payoff.summarise)
        text = payoff.render(pairs)
        assert "HELPED" not in text, "a raw p printed as a verdict in a family"
        assert text.count("NOT a verdict on its own") == 2
        assert "ON vs PLACEBO does" in text

    def test_positive_control_a_single_test_still_gets_a_verdict(self) -> None:
        pairs = [
            payoff.Pair(
                target="t", first="on", on=_arm(True), off=_arm(False), comparable=True
            )
            for _ in range(8)
        ]
        assert "MEMORY HELPED" in payoff.render(pairs)


class TestTheTrailRecordsTheDesign:
    def test_samples_placebo_and_exclusions_are_recorded(
        self, tmp_path, monkeypatch
    ) -> None:
        import hashlib

        from tests.test_learning_payoff import _NoGit

        excluded = tmp_path / "calibration.txt"
        excluded.write_text("aios/a.py::f\n# note\naios/b.py::g\n", encoding="utf-8")
        rows: list = []
        seen_kwargs: dict = {}
        monkeypatch.setattr(payoff, "_append", rows.append)

        def bench(**kwargs):
            seen_kwargs.update(kwargs)
            pair = payoff.Pair(
                target="t", first="on", on=_arm(True), off=_arm(False), comparable=True
            )
            return [pair], "run-1", "c" * 40

        monkeypatch.setattr(payoff, "run_benchmark", bench)
        monkeypatch.setattr(payoff.subprocess, "run", _NoGit())
        payoff.main(
            [
                "--targets",
                "1",
                "--ref",
                "HEAD",
                "--samples",
                "3",
                "--placebo",
                "--novel-only",
                "--exclude-targets",
                str(excluded),
            ]
        )
        row = rows[-1]
        assert (row["samples"], row["placebo"], row["novel_only"]) == (3, True, True)
        assert row["excluded_targets"] == {
            "count": 2,
            # LF-normalised, as every text hash a run records (payoff
            # text_sha256): Windows writes this file with CRLF.
            "sha256": hashlib.sha256(
                excluded.read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest(),
        }
        assert seen_kwargs["exclude_labels"] == ["aios/a.py::f", "aios/b.py::g"]
        assert seen_kwargs["samples"] == 3 and seen_kwargs["placebo"] is True

    def test_zero_samples_is_refused(self) -> None:
        with pytest.raises(SystemExit):
            payoff.main(["--samples", "0"])
