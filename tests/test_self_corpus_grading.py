"""A test that cannot fail is not evidence, and must not be scored as one.

Reverse-engineering the system's own source removes the obvious way an agent
games its grader — it cannot bend the code, because the code is what it is
being asked to describe. What it can still do is write `assert True`, which is
green, worthless, and exactly what a naive "did pytest pass?" reward teaches.

So the load-bearing test in this file is the one where a VACUOUS test is
correctly refused despite passing. Everything else exists to make sure that
refusal is specific rather than a blanket no.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.self_corpus import Corpus, CorpusError, provision, teardown
from tools.self_corpus_grading import (
    grade_pin_test,
    mutate_function,
    restore,
    source_is_untouched,
)

MODULE = '''\
def add(a, b):
    """Sum two numbers."""
    return a + b


class Calculator:
    def double(self, value):
        return value * 2
'''


def _run(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture()
def corpus(tmp_path):
    """A miniature stand-in for this repository: source plus an existing suite."""
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    _run_init = ["init", "-q", "-b", "main"]
    subprocess.run(
        ["git", "-C", str(repo), *_run_init], check=True, capture_output=True
    )
    _run(repo, "config", "user.email", "test@example.invalid")
    _run(repo, "config", "user.name", "test")
    (repo / "calc.py").write_text(MODULE, encoding="utf-8")
    (repo / "tests" / "test_existing.py").write_text(
        "from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    (repo / "conftest.py").write_text("", encoding="utf-8")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-qm", "corpus")

    provisioned = provision(repo, tmp_path / "wt")
    yield provisioned
    teardown(provisioned)


def _write_agent_test(corpus: Corpus, body: str) -> list[str]:
    path = corpus.root / "tests" / "test_pinned.py"
    path.write_text(body, encoding="utf-8")
    return ["tests/test_pinned.py"]


class TestTheMutationItself:
    def test_the_body_is_replaced_and_the_module_still_imports(self, corpus) -> None:
        """The break must be felt on CALL, not on import.

        A mutation that broke the import would be caught by any test that
        merely imports the module — the control would pass for the wrong
        reason, which is indistinguishable from it not working.
        """
        target = corpus.root / "calc.py"
        mutation = mutate_function(target, "add")
        try:
            source = target.read_text(encoding="utf-8")
            assert "raise NotImplementedError" in source
            assert "def add(a, b):" in source, "the signature must survive"
            assert "def double(self, value):" in source, "siblings must be untouched"
            compile(source, "calc.py", "exec")  # still importable
        finally:
            restore(mutation)
        assert target.read_text(encoding="utf-8") == MODULE

    def test_a_method_can_be_targeted(self, corpus) -> None:
        target = corpus.root / "calc.py"
        mutation = mutate_function(target, "double")
        try:
            assert "raise NotImplementedError" in target.read_text(encoding="utf-8")
        finally:
            restore(mutation)

    def test_an_unknown_target_is_refused_rather_than_silently_skipped(
        self, corpus
    ) -> None:
        """A no-op mutation would make every vacuous test look genuine."""
        with pytest.raises(CorpusError, match="no function named"):
            mutate_function(corpus.root / "calc.py", "nonexistent")


class TestGrading:
    def test_a_real_pin_test_earns_the_task(self, corpus) -> None:
        selection = _write_agent_test(
            corpus,
            "from calc import add\n\n\ndef test_add_sums():\n    assert add(2, 3) == 5\n",
        )
        verdict = grade_pin_test(
            corpus,
            new_test=selection,
            target_module="calc.py",
            target_function="add",
            guard_selection=["tests/test_existing.py"],
        )
        assert verdict.earned, verdict.notes

    def test_a_vacuous_test_is_refused_even_though_it_passes(self, corpus) -> None:
        """The whole reason this grader exists."""
        selection = _write_agent_test(corpus, "def test_nothing():\n    assert True\n")
        verdict = grade_pin_test(
            corpus,
            new_test=selection,
            target_module="calc.py",
            target_function="add",
            guard_selection=["tests/test_existing.py"],
        )
        assert verdict.passes_clean, "it does pass — that is the point"
        assert not verdict.fails_when_mutated
        assert not verdict.earned
        assert any("NEGATIVE CONTROL FAILED" in note for note in verdict.notes)

    def test_importing_without_asserting_is_also_refused(self, corpus) -> None:
        """The subtler vacuous shape: it touches the module but pins nothing."""
        selection = _write_agent_test(
            corpus,
            "import calc\n\n\ndef test_imports():\n    assert calc is not None\n",
        )
        verdict = grade_pin_test(
            corpus,
            new_test=selection,
            target_module="calc.py",
            target_function="add",
            guard_selection=["tests/test_existing.py"],
        )
        assert not verdict.earned
        assert not verdict.fails_when_mutated

    def test_editing_the_source_to_fit_the_test_is_refused(self, corpus) -> None:
        """Bending the code to match a wrong belief is the failure mode, not a pass."""
        (corpus.root / "calc.py").write_text(
            MODULE.replace("return a + b", "return a + b + 1"), encoding="utf-8"
        )
        selection = _write_agent_test(
            corpus,
            "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 6\n",
        )
        verdict = grade_pin_test(
            corpus,
            new_test=selection,
            target_module="calc.py",
            target_function="add",
            guard_selection=["tests/test_existing.py"],
        )
        assert verdict.passes_clean, "the agent made its own test pass"
        assert not verdict.source_untouched
        assert not verdict.earned

    def test_breaking_the_existing_suite_is_refused(self, corpus) -> None:
        selection = _write_agent_test(
            corpus,
            "from calc import add\n\n\ndef test_add_sums():\n    assert add(2, 3) == 5\n",
        )
        (corpus.root / "tests" / "test_existing.py").write_text(
            "from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 99\n",
            encoding="utf-8",
        )
        verdict = grade_pin_test(
            corpus,
            new_test=selection,
            target_module="calc.py",
            target_function="add",
            guard_selection=["tests/test_existing.py"],
        )
        assert not verdict.suite_still_green
        assert not verdict.earned

    def test_the_source_is_restored_even_when_grading_finds_a_failure(
        self, corpus
    ) -> None:
        """A mutation left behind would poison every later run in this corpus."""
        selection = _write_agent_test(corpus, "def test_nothing():\n    assert True\n")
        grade_pin_test(
            corpus,
            new_test=selection,
            target_module="calc.py",
            target_function="add",
            guard_selection=["tests/test_existing.py"],
        )
        assert (corpus.root / "calc.py").read_text(encoding="utf-8") == MODULE


class TestSourceIsUntouched:
    def test_a_new_test_file_alone_is_fine(self, corpus) -> None:
        _write_agent_test(corpus, "def test_x():\n    assert True\n")
        untouched, _ = source_is_untouched(corpus)
        assert untouched

    def test_a_source_edit_is_reported(self, corpus) -> None:
        (corpus.root / "calc.py").write_text(MODULE + "\nEXTRA = 1\n", encoding="utf-8")
        untouched, offenders = source_is_untouched(corpus)
        assert not untouched
        assert "calc.py" in offenders

    def test_bytecode_caches_are_not_mistaken_for_source_edits(self, corpus) -> None:
        """Otherwise the check flags its own measurement.

        Running the suite compiles the corpus, `__pycache__` appears, and a
        perfectly honest attempt is scored as having edited the source.
        """
        cache = corpus.root / "__pycache__"
        cache.mkdir(exist_ok=True)
        (cache / "calc.cpython-314.pyc").write_bytes(b"\x00")
        (corpus.root / ".pytest_cache").mkdir(exist_ok=True)
        (corpus.root / ".pytest_cache" / "CACHEDIR.TAG").write_text(
            "x", encoding="utf-8"
        )

        untouched, offenders = source_is_untouched(corpus)
        assert untouched, offenders

    def test_the_artefact_filter_does_not_wave_through_a_real_edit(
        self, corpus
    ) -> None:
        """A narrow filter, checked against the thing it must still catch."""
        (corpus.root / "__pycache__").mkdir(exist_ok=True)
        (corpus.root / "__pycache__" / "x.pyc").write_bytes(b"\x00")
        (corpus.root / "calc.py").write_text(
            MODULE + "\nSNEAKY = 1\n", encoding="utf-8"
        )

        untouched, offenders = source_is_untouched(corpus)
        assert not untouched
        assert "calc.py" in offenders
        assert ".pyc" not in offenders


class TestTheGraderIsTheAuthorityNotTheStrength:
    """pytest cannot tell a real pin test from `assert True`. Only the control can.

    A vacuous test run under pytest yields passed>0, failed==0 from a recognized
    runner at the program position, so `derive_strength` calls it STRONG — and
    it is right to, by its own definition, which is about the KIND of evidence
    and not about whether the test means anything. If the strength alone drove
    `record_attempt`, writing tests that cannot fail would be the fastest way to
    promote a skill.
    """

    def test_an_earned_pin_records_a_success(self, corpus, tmp_path) -> None:
        from aios.memory.db import init_memory_db
        from aios.memory.skills import SkillMemory
        from tools.self_corpus_grading import record_pin_outcome

        db = tmp_path / "memory.sqlite"
        init_memory_db(db)
        skills = SkillMemory(db_path=db)

        selection = _write_agent_test(
            corpus,
            "from calc import add\n\n\ndef test_add_sums():\n    assert add(2, 3) == 5\n",
        )
        verdict = grade_pin_test(
            corpus,
            new_test=selection,
            target_module="calc.py",
            target_function="add",
            guard_selection=["tests/test_existing.py"],
        )
        assert verdict.earned
        record_pin_outcome(
            skills,
            verdict,
            target_label="calc.py::add",
            model="qwen2.5-coder:7b",
            steps=["read calc.py", "verify: pytest"],
        )
        assert skills.list()[0]["success_count"] == 1

    def test_a_vacuous_pin_records_a_FAILURE_not_a_weak_success(
        self, corpus, tmp_path
    ) -> None:
        """A weak success would still say 'this arc ran cleanly'.

        That is the wrong lesson to draw from an agent that wrote a test
        incapable of failing — and it would reset the failure streak that gates
        reflex compilation, so the vacuous attempt would actively help.
        """
        from aios.memory.db import init_memory_db
        from aios.memory.skills import SkillMemory
        from tools.self_corpus_grading import record_pin_outcome

        db = tmp_path / "memory.sqlite"
        init_memory_db(db)
        skills = SkillMemory(db_path=db)

        selection = _write_agent_test(corpus, "def test_nothing():\n    assert True\n")
        verdict = grade_pin_test(
            corpus,
            new_test=selection,
            target_module="calc.py",
            target_function="add",
            guard_selection=["tests/test_existing.py"],
        )
        assert verdict.passes_clean and not verdict.earned

        record_pin_outcome(
            skills,
            verdict,
            target_label="calc.py::add",
            model="qwen2.5-coder:7b",
            steps=["read calc.py", "verify: pytest"],
        )
        row = skills.list()[0]
        assert row["success_count"] == 0
        assert row["weak_success_count"] == 0, (
            "not a weak success either — a test that cannot fail is not a "
            "below-floor success, it is a failed attempt at the task"
        )
        assert row["failure_count"] == 1


class TestATierIsItsOwnArc:
    """Who earned it is the measurement, so the tier is part of the identity.

    The ladder asks several models the same question and stops at the first
    that answers. Folding that into one per-target record loses the only thing
    the run measured -- which tier could do it -- and makes the success rate
    wrong in both directions: the frontier's win lands on an arc the small
    local model failed four times, and those failures hold the arc under the
    80% promotion rate forever. Live evidence of exactly that: four targets
    closed by the ladder, every arc stuck `candidate` at 14-40%.
    """

    def test_two_models_on_one_target_are_two_arcs(self, tmp_path) -> None:
        from aios.memory.db import init_memory_db
        from aios.memory.skills import SkillMemory
        from tools.self_corpus_grading import record_pin_outcome

        db = tmp_path / "memory.sqlite"
        init_memory_db(db)
        skills = SkillMemory(db_path=db)
        steps = ["read_file: calc.py", "create_file: test_calc.py", "verify: pytest"]

        record_pin_outcome(
            skills,
            _Earned(False),
            target_label="calc.py::add",
            model="qwen2.5-coder:7b",
            steps=steps,
        )
        record_pin_outcome(
            skills,
            _Earned(True),
            target_label="calc.py::add",
            model="bedrock.apac.anthropic.claude-sonnet-4",
            steps=steps,
        )

        rows = {row["goal_pattern"]: row for row in skills.list()}
        assert len(rows) == 2, (
            "one row means the frontier's success and the clerk's failure were "
            f"recorded against the same arc: {list(rows)}"
        )
        clerk = next(r for g, r in rows.items() if "7b" in g)
        frontier = next(r for g, r in rows.items() if "sonnet" in g)
        assert (clerk["success_count"], clerk["failure_count"]) == (0, 1)
        assert (frontier["success_count"], frontier["failure_count"]) == (1, 0)

    def test_one_tier_repeating_a_target_reinforces_one_arc(self, tmp_path) -> None:
        """Splitting by tier must not also split by run, or nothing promotes."""
        from aios.memory.db import init_memory_db
        from aios.memory.skills import SkillMemory
        from tools.self_corpus_grading import record_pin_outcome

        db = tmp_path / "memory.sqlite"
        init_memory_db(db)
        skills = SkillMemory(db_path=db)
        steps = ["read_file: calc.py", "create_file: test_calc.py", "verify: pytest"]

        for _ in range(3):
            record_pin_outcome(
                skills,
                _Earned(True),
                target_label="calc.py::add",
                model="qwen2.5-coder:7b",
                steps=steps,
            )

        rows = skills.list()
        assert len(rows) == 1
        assert rows[0]["success_count"] == 3
        assert rows[0]["status"] == "verified", (
            "three clean STRONG runs by one tier on one target is exactly the "
            "evidence the promotion floor asks for; if this stays candidate "
            "the split went too far and no tier can ever verify"
        )

    def test_folding_the_spec_to_one_token_keeps_near_names_apart(self) -> None:
        """`:` folds to `-` for the token budget; that must not merge two tiers."""
        from tools.self_corpus_grading import pin_goal

        assert pin_goal("calc.py::add", "ollama:qwen") != pin_goal(
            "calc.py::add", "ollama:qwen2"
        )

    def test_a_goal_too_long_to_key_is_refused_not_silently_merged(self) -> None:
        """Over 12 tokens the arc signature drops some -- possibly the tier.

        A dropped tier token is silent: two models quietly share one arc and
        the numbers look fine. Refusing is the only honest option, because the
        failure mode is invisible in the data it produces.
        """
        from tools.self_corpus import CorpusError
        from tools.self_corpus_grading import pin_goal

        wordy = " ".join(f"part{i}" for i in range(12))
        with pytest.raises(CorpusError, match="silently merging"):
            pin_goal(f"calc.py::{wordy}", "qwen2.5-coder:7b")

    def test_a_spec_the_secret_scanner_redacts_still_keys_its_own_arc(self) -> None:
        """Some real model ids read as high-entropy and come back redacted.

        `openai.qwen/qwen3-coder-480b-a35b-instruct` is one: the scanner
        rewrites the tail to `<REDACTED:HIGH_ENTROPY:...>` before the goal is
        stored, because a long random-looking token is exactly what a leaked
        key looks like. That is the scanner being right, and it is frozen
        (AGENTS.md VIII) -- so what has to hold is not that the name survives
        but that the ARC does: the digest is content-derived, so two specs stay
        two arcs and the same spec keys the same arc on every later run. If
        that digest were ever salted per process, every run would mint a fresh
        arc and nothing could accumulate to promotion.
        """
        from aios.security.secret_scanner import scan_and_redact
        from tools.self_corpus_grading import pin_goal

        a = scan_and_redact(
            pin_goal("calc.py::add", "openai.qwen/qwen3-coder-480b-a35b-instruct")
        ).scrubbed
        b = scan_and_redact(
            pin_goal("calc.py::add", "openai.qwen/qwen3-next-80b-a3b-instruct")
        ).scrubbed
        again = scan_and_redact(
            pin_goal("calc.py::add", "openai.qwen/qwen3-coder-480b-a35b-instruct")
        ).scrubbed

        assert "REDACTED" in a, "this test is pointless if the spec survives intact"
        assert a != b, "two frontier specs collapsed into one arc once redacted"
        assert a == again, "the arc key is not stable, so it can never accumulate"

    def test_an_unnamed_model_is_refused(self) -> None:
        from tools.self_corpus import CorpusError
        from tools.self_corpus_grading import pin_goal

        with pytest.raises(CorpusError, match="must name the model"):
            pin_goal("calc.py::add", "   ")


class _Earned:
    """The `.earned` half of a `PinVerdict` -- all `record_pin_outcome` reads."""

    def __init__(self, earned: bool) -> None:
        self.earned = earned


class TestAHollowRunIsNotAVerdict:
    """pytest producing NOTHING is the runner dying, not a test result.

    Observed live on 2026-09-21: after Ollama timed out at 300s with the
    machine under memory pressure, six consecutive attempts across two cloud
    tiers came back `rejected` in 1-4 seconds each with a completely empty
    reason. A real red prints the assertion; a collection error prints the
    traceback; even "collected 0 items" prints. Empty means the subprocess
    died before saying anything -- and all six were recorded as the models'
    failures.

    `SuiteResult.green` already refused to call a hollow run a pass. Nothing
    refused to call it a failure, and that is the half that gets attributed to
    whoever wrote the test.
    """

    def test_an_empty_run_is_hollow_and_a_red_one_is_not(self) -> None:
        from tools.self_corpus import SuiteResult

        died = SuiteResult(passed=0, failed=0, errors=0, returncode=1, tail="")
        assert died.hollow and not died.green

        really_red = SuiteResult(
            passed=0, failed=1, errors=0, returncode=1, tail="E   AssertionError"
        )
        assert not really_red.hollow, (
            "a suite that ran and failed must stay a failure -- this guard "
            "must not become a way for real reds to be waved through"
        )

        collected_nothing = SuiteResult(
            passed=0, failed=0, errors=0, returncode=5, tail="collected 0 items"
        )
        assert not collected_nothing.hollow, (
            "pytest said something, so the runner worked; an empty selection is "
            "a real (and already-defended) result, not a dead subprocess"
        )

    def test_a_hollow_clean_run_aborts_instead_of_failing_the_model(
        self, corpus, monkeypatch
    ) -> None:
        from tools.self_corpus import SuiteResult
        from tools import self_corpus_grading

        selection = _write_agent_test(
            corpus,
            "from calc import add\n\n\ndef test_a():\n    assert add(1, 1) == 2\n",
        )
        monkeypatch.setattr(
            self_corpus_grading,
            "run_suite",
            lambda *a, **k: SuiteResult(
                passed=0, failed=0, errors=0, returncode=1, tail=""
            ),
        )
        with pytest.raises(CorpusError, match="no output at all"):
            grade_pin_test(
                corpus,
                new_test=selection,
                target_module="calc.py",
                target_function="add",
                guard_selection=["tests/test_existing.py"],
            )

    def test_a_hollow_MUTATED_run_cannot_satisfy_the_negative_control(
        self, corpus, monkeypatch
    ) -> None:
        """The dangerous direction, and the less obvious one.

        `fails_when_mutated` is `not mutated.green`, so a mutated run that
        never happened satisfies the control for exactly the wrong reason: a
        test that pins nothing gets EARNED because the run meant to catch it
        died. That is a false GREEN produced by machine load.
        """
        from tools.self_corpus import SuiteResult, run_suite
        from tools import self_corpus_grading

        selection = _write_agent_test(
            corpus,
            "from calc import add\n\n\ndef test_a():\n    assert add(1, 1) == 2\n",
        )
        calls = {"n": 0}

        def only_the_mutated_run_dies(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:  # clean, MUTATED, guard
                return SuiteResult(passed=0, failed=0, errors=0, returncode=1, tail="")
            return run_suite(*args, **kwargs)

        monkeypatch.setattr(self_corpus_grading, "run_suite", only_the_mutated_run_dies)
        with pytest.raises(CorpusError, match="mutated negative control"):
            grade_pin_test(
                corpus,
                new_test=selection,
                target_module="calc.py",
                target_function="add",
                guard_selection=["tests/test_existing.py"],
            )

    def test_the_corpus_is_restored_even_when_the_run_aborts(
        self, corpus, monkeypatch
    ) -> None:
        """Otherwise the abort leaves calc.py mutated and poisons every later
        attempt in the run -- turning one dead subprocess into a whole red run."""
        from tools.self_corpus import SuiteResult, run_suite
        from tools import self_corpus_grading

        before = (corpus.root / "calc.py").read_text(encoding="utf-8")
        selection = _write_agent_test(
            corpus,
            "from calc import add\n\n\ndef test_a():\n    assert add(1, 1) == 2\n",
        )
        calls = {"n": 0}

        def only_the_mutated_run_dies(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                return SuiteResult(passed=0, failed=0, errors=0, returncode=1, tail="")
            return run_suite(*args, **kwargs)

        monkeypatch.setattr(self_corpus_grading, "run_suite", only_the_mutated_run_dies)
        with pytest.raises(CorpusError):
            grade_pin_test(
                corpus,
                new_test=selection,
                target_module="calc.py",
                target_function="add",
                guard_selection=["tests/test_existing.py"],
            )
        assert (corpus.root / "calc.py").read_text(encoding="utf-8") == before
