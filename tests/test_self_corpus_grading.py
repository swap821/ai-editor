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
            goal="pin calc.add",
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
            goal="pin calc.add",
            steps=["read calc.py", "verify: pytest"],
        )
        row = skills.list()[0]
        assert row["success_count"] == 0
        assert row["weak_success_count"] == 0, (
            "not a weak success either — a test that cannot fail is not a "
            "below-floor success, it is a failed attempt at the task"
        )
        assert row["failure_count"] == 1
