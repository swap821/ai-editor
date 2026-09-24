"""The payoff benchmark must be unable to publish a number it did not measure.

`tools/learning_payoff.py` is the number the animal's learning is judged by, so
its failure modes are not bugs in the usual sense -- they are false claims about
whether memory helps. Every test here pins one way the number could lie:

* NO NUMBER when nothing was comparable, never a confident 0%;
* ties carry no information, so a pile of both-failed pairs cannot read as a
  finding either way;
* a small one-sided result is printed as a DIRECTION, not a finding;
* "helps on repeats" (SEEN) and "helps on new work" (NOVEL) are never summed;
* the two arms differ ONLY by the recalled prefix;
* a hollow grader cannot leave one arm's file to be graded as the other's;
* a memory store that changes mid-run is detected.

None of these call a model. They pin the decision logic, which is where a
benchmark lies.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import tools.learning_payoff as payoff
from tools.self_corpus import CorpusError
from tools.self_corpus_targets import Target


def _target(module: str = "aios/agents/tool_agent.py", function: str = "build_cmd"):
    return Target(
        module=module,
        function=function,
        lineno=1,
        params=(),
        doc="",
        source="def build_cmd():\n    return 1\n",
    )


def _pair(on: bool, off: bool, *, seen: bool = False, comparable: bool = True):
    return payoff.Pair(
        target="t",
        first="on",
        on={"earned": on, "reached_model": True},
        off={"earned": off, "reached_model": True},
        comparable=comparable,
        seen=seen,
    )


class TestMcNemar:
    """Known exact values, so the test is the definition and not my arithmetic."""

    @pytest.mark.parametrize(
        ("b", "c", "expected"),
        [
            (0, 0, 1.0),  # no discordant pairs: no evidence either way
            (6, 0, 0.03125),  # 2 * (1/2)^6 -- the smallest n that can reach p<0.05
            (5, 0, 0.0625),  # one short of it
            (3, 3, 1.0),  # perfectly balanced
            (8, 2, 0.109375),  # 2 * P(X<=2 | n=10, p=.5) = 2 * 56/1024
        ],
    )
    def test_exact_values(self, b: int, c: int, expected: float) -> None:
        assert payoff.mcnemar_exact(b, c) == pytest.approx(expected)

    def test_symmetric(self) -> None:
        assert payoff.mcnemar_exact(7, 1) == payoff.mcnemar_exact(1, 7)


class TestItCannotPublishWhatItDidNotMeasure:
    def test_nothing_comparable_is_no_number_not_zero(self) -> None:
        import re

        report = payoff.render([_pair(True, True, comparable=False)])
        assert "NO NUMBER" in report
        # No SCORE line of any kind. (The prose may say "0%" -- it explains why
        # printing one would be the failure -- so the check is on score shape.)
        assert not re.search(r"payoff [+-]\d", report)
        assert "earned" not in report

    def test_an_empty_run_is_no_number(self) -> None:
        assert "NO NUMBER" in payoff.render([])

    def test_ties_are_not_a_finding(self) -> None:
        """Both arms failing every time is 'no difference', stated as such --
        and it is not dressed up as 'memory does not help'."""
        report = payoff.render([_pair(False, False) for _ in range(10)])
        assert "NO MEASURABLE DIFFERENCE" in report
        assert "HELPED" not in report and "HURT" not in report

    def test_five_one_sided_wins_are_a_direction_not_a_finding(self) -> None:
        report = payoff.render([_pair(True, False) for _ in range(5)])
        assert "NOT DISTINGUISHABLE FROM NOISE" in report
        assert "MEMORY HELPED" not in report

    def test_six_one_sided_wins_are_a_finding(self) -> None:
        """The negative control for the test above: the verdict CAN be
        reached, so its absence at n=5 means something."""
        assert "MEMORY HELPED" in payoff.render([_pair(True, False) for _ in range(6)])

    def test_significant_harm_is_reported_as_harm(self) -> None:
        report = payoff.render([_pair(False, True) for _ in range(6)])
        assert "MEMORY HURT" in report

    def test_a_not_comparable_pair_has_no_payoff(self) -> None:
        assert _pair(True, False, comparable=False).payoff is None


class TestSeenAndNovelAreNeverSummed:
    def test_novel_excludes_seen_pairs(self) -> None:
        pairs = [_pair(True, False, seen=True) for _ in range(6)] + [
            _pair(False, False, seen=False) for _ in range(4)
        ]
        summary = payoff.summarise(pairs)
        assert summary["seen"]["pairs"] == 6 and summary["seen"]["on_only"] == 6
        assert summary["novel"]["pairs"] == 4 and summary["novel"]["on_only"] == 0
        # The headline claim -- transfer to new work -- shows NO effect here,
        # however good the repeats look.
        assert summary["novel"]["payoff"] == 0

    def test_novel_is_printed_first(self) -> None:
        report = payoff.render([_pair(True, False, seen=True), _pair(False, False)])
        assert report.index("NOVEL") < report.index("SEEN")


class TestAboutThisTarget:
    """Biased toward SEEN on purpose: a false SEEN weakens the NOVEL claim, a
    false NOVEL would inflate it."""

    def test_the_full_label_is_seen(self) -> None:
        target = _target()
        item = {"goal_pattern": f"pin the behaviour of {target.label} as qwen"}
        assert payoff.about_this_target(item, target)

    def test_module_path_and_function_is_seen(self) -> None:
        item = {"lesson_text": "in aios/agents/tool_agent.py, build_cmd returns a list"}
        assert payoff.about_this_target(item, _target())

    def test_dotted_import_path_and_function_is_seen(self) -> None:
        """Lessons about failed imports name the module this way -- and the
        first version of this helper could not match it at all."""
        item = {"lesson_text": "from aios.agents.tool_agent import build_cmd failed"}
        assert payoff.about_this_target(item, _target())

    def test_a_bare_function_name_alone_is_not_seen(self) -> None:
        """`main` or `run` would otherwise match unrelated work everywhere."""
        target = _target(function="run")
        assert not payoff.about_this_target(
            {"lesson_text": "always run the tests"}, target
        )

    def test_unrelated_work_is_novel(self) -> None:
        item = {
            "goal_pattern": "pin the behaviour of aios/memory/relevance.py::relevance"
        }
        assert not payoff.about_this_target(item, _target())


class TestTheArmsDifferOnlyByThePrefix:
    def test_on_is_off_with_recall_prepended(self, tmp_path, monkeypatch) -> None:
        seen_prompts: list[str] = []
        monkeypatch.setattr(
            payoff,
            "complete_via",
            lambda client, prompt, system: seen_prompts.append(prompt) or "",
        )

        class _Corpus:
            root = tmp_path

        target = _target()
        payoff.run_arm(
            _Corpus(),
            None,
            target,
            arm="off",
            extra_context="",
            lessons=0,
            skills_count=0,
        )
        payoff.run_arm(
            _Corpus(),
            None,
            target,
            arm="on",
            extra_context="RECALLED",
            lessons=1,
            skills_count=0,
        )
        off_prompt, on_prompt = seen_prompts
        assert on_prompt != off_prompt
        assert on_prompt.endswith(off_prompt), "the arms differ by more than the prefix"
        assert on_prompt.startswith("RECALLED")


class TestAHollowGraderCannotContaminateTheOtherArm:
    def test_the_test_file_is_removed_even_when_grading_raises(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            payoff,
            "complete_via",
            lambda *a, **k: "```python\ndef test_x():\n    pass\n```",
        )

        def _hollow(*args, **kwargs):
            raise CorpusError("the suite run produced no output at all")

        monkeypatch.setattr(payoff, "grade_pin_test", _hollow)

        class _Corpus:
            root = tmp_path

        target = _target()
        with pytest.raises(CorpusError):
            payoff.run_arm(
                _Corpus(),
                None,
                target,
                arm="on",
                extra_context="x",
                lessons=1,
                skills_count=0,
            )
        written = tmp_path / payoff._test_filename(target)
        assert not written.exists(), (
            "a hollow-graded arm left its file for the next arm"
        )


class TestTheStoreGuard:
    def _db(self, tmp_path: Path) -> Path:
        db = tmp_path / "memory.sqlite"
        conn = sqlite3.connect(db)
        for table in payoff.MEMORY_TABLES:
            conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        return db

    def test_an_untouched_store_fingerprints_the_same(self, tmp_path) -> None:
        db = self._db(tmp_path)
        assert payoff.store_fingerprint(db) == payoff.store_fingerprint(db)

    def test_a_write_mid_run_is_detected(self, tmp_path) -> None:
        db = self._db(tmp_path)
        before = payoff.store_fingerprint(db)
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO mistake_pool DEFAULT VALUES")
        conn.commit()
        conn.close()
        assert payoff.store_fingerprint(db) != before

    def test_reading_the_store_does_not_write_to_it(self, tmp_path) -> None:
        db = self._db(tmp_path)
        mtime = db.stat().st_mtime_ns
        payoff.store_fingerprint(db)
        assert db.stat().st_mtime_ns == mtime
