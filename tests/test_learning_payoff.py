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

    def test_a_distinctive_function_name_alone_is_seen(self) -> None:
        """Organic lessons rarely name the path. Over-marking SEEN is the safe
        direction: it can only weaken the NOVEL claim, never inflate it."""
        target = _target(function="build_auto_verify_command")
        item = {"lesson_text": "build_auto_verify_command drops inherited addopts"}
        assert payoff.about_this_target(item, target)

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


# --------------------------------------------------------------------------
# Added after the adversarial review of 756dd34b. Each test below would have
# FAILED against that commit -- they pin the flaws it found, not the fixes'
# happy paths.
# --------------------------------------------------------------------------


class TestTheStoreGuardSeesUpdates:
    """Four review lenses independently found the count-only guard blind to
    the writes that matter: a promotion changes what recall returns and not
    how many rows there are."""

    def test_an_in_place_update_is_detected(self, tmp_path) -> None:
        db = tmp_path / "memory.sqlite"
        conn = sqlite3.connect(db)
        for table in payoff.MEMORY_TABLES:
            conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, status TEXT)")
        conn.execute("INSERT INTO procedural_skills (status) VALUES ('candidate')")
        conn.commit()
        before = payoff.store_fingerprint(db)
        conn.execute("UPDATE procedural_skills SET status = 'verified'")
        conn.commit()
        conn.close()
        after = payoff.store_fingerprint(db)
        assert after != before, "a promotion slipped past the store guard"
        assert after["procedural_skills"] != before["procedural_skills"]
        assert after["mistake_pool"] == before["mistake_pool"], "says WHICH table moved"


class TestSeenReadsTheFullLesson:
    def _db(self, tmp_path, **row):
        db = tmp_path / "memory.sqlite"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE mistake_pool (id INTEGER PRIMARY KEY, root_cause TEXT, "
            "fix_applied TEXT, task_id TEXT, lesson_text TEXT)"
        )
        conn.execute(
            "INSERT INTO mistake_pool (id, root_cause, fix_applied, task_id, lesson_text) "
            "VALUES (7, ?, ?, ?, ?)",
            (row.get("root_cause", ""), row.get("fix_applied", ""), "", "generic"),
        )
        conn.commit()
        conn.close()
        return db

    def test_a_target_named_only_in_root_cause_is_seen(self, tmp_path) -> None:
        """The recalled dict has no root_cause. Without enrichment this repeat
        was filed NOVEL -- the one mistake the split exists to prevent."""
        target = _target()
        db = self._db(tmp_path, root_cause=f"{target.label} returned the wrong list")
        recalled = [
            {"mistake_id": 7, "lesson_text": "check list order", "error_type": "x"}
        ]
        assert not payoff.about_this_target(recalled[0], target), "precondition"
        enriched = payoff.enrich_lessons(db, recalled)
        assert payoff.about_this_target(enriched[0], target)

    def test_the_pin_test_filename_alone_is_seen(self) -> None:
        target = _target()
        item = {
            "lesson_text": f"pytest {payoff._test_filename(target)} failed: 1 failed"
        }
        assert payoff.about_this_target(item, target)

    def test_enrichment_changes_nothing_the_model_sees(self, tmp_path) -> None:
        """Classification only. The ON prompt is built from the production
        block, which never reads root_cause."""
        from aios.api.turn_pipeline import lessons_prompt_block

        db = self._db(tmp_path, root_cause="internal-only detail")
        recalled = [
            {
                "mistake_id": 7,
                "lesson_text": "check",
                "error_type": "x",
                "verification_status": "verified",
            }
        ]
        before = lessons_prompt_block(recalled)
        payoff.enrich_lessons(db, recalled)
        assert lessons_prompt_block(recalled) == before
        assert "internal-only" not in before


class TestTargetSelectionReachesNovelWork:
    def test_it_alternates_unpractised_and_practised(self) -> None:
        targets = [_target(function=f"f{i}") for i in range(6)]
        practised_names = {"f0", "f1", "f2"}
        chosen, n_fresh, n_known = payoff.select_targets(
            targets, 4, lambda t: t.function in practised_names
        )
        assert [t.function for t in chosen] == ["f3", "f0", "f4", "f1"]
        assert (n_fresh, n_known) == (2, 2)

    def test_history_blind_selection_would_have_been_all_practised(self) -> None:
        """What collect_targets alone returns when its top-N is what earlier
        runs practised: NOVEL is structurally empty."""
        targets = [_target(function=f"f{i}") for i in range(6)]
        practised_names = {"f0", "f1", "f2", "f3"}
        assert all(t.function in practised_names for t in targets[:4])
        _chosen, n_fresh, _known = payoff.select_targets(
            targets, 4, lambda t: t.function in practised_names
        )
        assert n_fresh == 2

    def test_unreadable_history_counts_as_practised(self) -> None:
        """Unknown history must never inflate NOVEL."""
        assert payoff.practised(None, _target())

    def test_a_target_in_history_is_practised(self) -> None:
        target = _target()
        assert payoff.practised(f"pin the behaviour of {target.label} via x", target)
        assert not payoff.practised("pin the behaviour of aios/other.py::g", target)


class TestOneJudgedNumber:
    def test_only_novel_carries_a_verdict(self) -> None:
        """Three uncorrected tests would let the best one be quoted."""
        pairs = [_pair(True, False, seen=True) for _ in range(6)] + [
            _pair(True, False, seen=False) for _ in range(6)
        ]
        report = payoff.render(pairs)
        judged, rest = report.split("context only -- SEEN", 1)
        assert "MEMORY HELPED" in judged
        for phrase in ("HELPED", "HURT", "NOISE", "NO MEASURABLE"):
            assert phrase not in rest, f"context section carries a verdict: {phrase}"

    def test_no_novel_pairs_means_no_judged_number(self) -> None:
        report = payoff.render([_pair(True, False, seen=True) for _ in range(6)])
        assert "NO JUDGED NUMBER" in report
        assert "MEMORY HELPED" not in report, (
            "a SEEN-only win was presented as the verdict"
        )

    def test_the_scope_travels_with_the_number(self) -> None:
        report = payoff.render([_pair(False, False)])
        assert "NOT exercised" in report and "PREPENDED" in report


class TestTheInstrumentIsProvenBeforeUse:
    """The docstring promised a green baseline; nothing ran one. A red guard
    suite then failed every arm, they tied, and the report read 'no measurable
    difference' -- a confident null from a broken instrument."""

    def _wire(self, tmp_path, monkeypatch, *, control_ok: bool, captured: list):
        from contextlib import contextmanager
        from types import SimpleNamespace

        db = tmp_path / "memory.sqlite"
        conn = sqlite3.connect(db)
        for table in payoff.MEMORY_TABLES:
            conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

        @contextmanager
        def _corpus(repo, dest, ref="HEAD"):
            yield SimpleNamespace(root=tmp_path, sha="c" * 40)

        monkeypatch.setattr(payoff, "DB", db)
        monkeypatch.setattr(payoff, "init_memory_db", lambda db: None)
        monkeypatch.setattr(payoff, "MistakeMemory", lambda db_path: object())
        monkeypatch.setattr(payoff, "SkillMemory", lambda db_path: object())
        monkeypatch.setattr(payoff, "ReflectionAgent", lambda *a, **k: object())
        monkeypatch.setattr(
            payoff, "resolve_client", lambda spec, timeout_s: (object(), spec)
        )
        monkeypatch.setattr(payoff, "self_corpus", _corpus)
        monkeypatch.setattr(
            payoff, "run_self_check", lambda corpus: (control_ok, "control detail")
        )
        monkeypatch.setattr(payoff, "collect_targets", lambda root: [_target()])
        monkeypatch.setattr(payoff, "practice_history", lambda db: "")

        def _recall(reflector, skills, query, session_id):
            captured.append(query)
            return "", [], []

        monkeypatch.setattr(payoff, "recalled_context", _recall)

    def test_a_failed_control_refuses_the_run(self, tmp_path, monkeypatch) -> None:
        captured: list = []
        self._wire(tmp_path, monkeypatch, control_ok=False, captured=captured)
        with pytest.raises(CorpusError, match="positive control"):
            payoff.run_benchmark(models="x", targets=1, model_timeout=1)
        assert captured == [], (
            "a model-facing step ran before the instrument was proven"
        )

    def test_a_passing_control_lets_the_run_proceed(
        self, tmp_path, monkeypatch
    ) -> None:
        """Negative control for the refusal above."""
        captured: list = []
        self._wire(tmp_path, monkeypatch, control_ok=True, captured=captured)
        pairs, _run, _sha = payoff.run_benchmark(models="x", targets=1, model_timeout=1)
        assert len(pairs) == 1

    def test_recall_is_queried_with_the_task_itself(
        self, tmp_path, monkeypatch
    ) -> None:
        """A live turn recalls against the user's text. The first version used
        an invented 'pin the behaviour of' label whose boilerplate matched every
        pin arc's goal_pattern."""
        captured: list = []
        self._wire(tmp_path, monkeypatch, control_ok=True, captured=captured)
        payoff.run_benchmark(models="x", targets=1, model_timeout=1)
        assert captured == [payoff.task_prompt(_target())]
        assert "pin the behaviour of" not in captured[0]


class TestTargetsMustBePositive:
    def test_zero_is_refused(self) -> None:
        """collect_targets(limit=0) means 'no cap' -- a --targets 0 dry run
        would have asked the model about every function in aios/."""
        with pytest.raises(SystemExit):
            payoff.main(["--targets", "0"])


class TestThePreregistrationBindsTheRun:
    """A judged number whose targets or hypothesis can move after the results
    are visible is a narrative, not a measurement."""

    def _wire_many(self, tmp_path, monkeypatch, targets):
        TestTheInstrumentIsProvenBeforeUse()._wire(
            tmp_path, monkeypatch, control_ok=True, captured=[]
        )
        monkeypatch.setattr(payoff, "collect_targets", lambda root: list(targets))

    def test_a_frozen_list_is_run_exactly_in_order(self, tmp_path, monkeypatch) -> None:
        targets = [_target(function=f"f{i}") for i in range(5)]
        self._wire_many(tmp_path, monkeypatch, targets)
        frozen = [targets[3].label, targets[0].label]
        pairs, _run, _sha = payoff.run_benchmark(
            models="x", targets=10, model_timeout=1, target_labels=frozen
        )
        assert [p.target for p in pairs] == frozen

    def test_a_missing_registered_target_is_refused_not_dropped(
        self, tmp_path, monkeypatch
    ) -> None:
        """A silently shorter list would change the experiment without saying so."""
        targets = [_target(function="f0")]
        self._wire_many(tmp_path, monkeypatch, targets)
        with pytest.raises(CorpusError, match="no longer exist"):
            payoff.run_benchmark(
                models="x",
                targets=10,
                model_timeout=1,
                target_labels=[targets[0].label, "aios/gone.py::vanished"],
            )

    def test_every_run_records_the_registration_hash_and_its_list(
        self, tmp_path, monkeypatch
    ) -> None:
        import hashlib

        prereg = tmp_path / "PREREG.md"
        prereg.write_text("H1: ON beats OFF on NOVEL at p<0.05\n", encoding="utf-8")
        rows: list = []
        monkeypatch.setattr(payoff, "_append", rows.append)
        monkeypatch.setattr(
            payoff,
            "run_benchmark",
            lambda **kw: ([_pair(True, False)], "run-1", "c" * 40),
        )
        monkeypatch.setattr(payoff.subprocess, "run", _NoGit())
        payoff.main(
            ["--targets", "1", "--ref", "HEAD", "--preregistration", str(prereg)]
        )
        row = rows[-1]
        assert (
            row["preregistration_sha256"]
            == hashlib.sha256(prereg.read_bytes()).hexdigest()
        )
        assert row["target_labels"] == ["t"], "the chosen list is recorded on every run"
        assert row["target_list_frozen"] is False

    def test_editing_the_registration_changes_the_recorded_hash(
        self, tmp_path, monkeypatch
    ) -> None:
        """The negative control: the hash must actually depend on the text."""
        rows: list = []
        monkeypatch.setattr(payoff, "_append", rows.append)
        monkeypatch.setattr(
            payoff, "run_benchmark", lambda **kw: ([_pair(True, False)], "r", "c" * 40)
        )
        monkeypatch.setattr(payoff.subprocess, "run", _NoGit())
        prereg = tmp_path / "PREREG.md"
        prereg.write_text("threshold p<0.05\n", encoding="utf-8")
        payoff.main(
            ["--targets", "1", "--ref", "HEAD", "--preregistration", str(prereg)]
        )
        prereg.write_text("threshold p<0.10\n", encoding="utf-8")
        payoff.main(
            ["--targets", "1", "--ref", "HEAD", "--preregistration", str(prereg)]
        )
        assert rows[0]["preregistration_sha256"] != rows[1]["preregistration_sha256"]

    def test_the_shipped_registration_exists(self) -> None:
        assert payoff.PREREGISTRATION.is_file(), (
            "the payoff benchmark is judged against a pre-registration that "
            "must be committed before any official run"
        )


class _NoGit:
    """Stands in for `subprocess.run` in main(): no fetch, a fixed HEAD."""

    def __call__(self, *args, **kwargs):
        from types import SimpleNamespace

        return SimpleNamespace(returncode=0, stdout="h" * 40 + "\n", stderr="")
