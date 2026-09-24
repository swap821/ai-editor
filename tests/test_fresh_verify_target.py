"""L4 must be able to witness a NEW compile, or it can only ever be proven once.

The verify-only arc used to be hardcoded to tests/test_code_chunking.py. Its
playbook was compiled on the first run, and `try_compile_all` is idempotent, so
every later run earned an arc that compiled NOTHING new. When #359's squash
erased the one run that had witnessed the compile, L4 could not be re-earned at
all: the harness had spent its only opportunity.

`_fresh_verify_target` picks a real corpus suite whose arc has never been a
reflex. These tests pin the two ways that choice could quietly cheat:

* a DECOMPILED playbook is not "fresh" -- recompiling a retired reflex is
  recovery (conformance M5), a different claim from compiling a new one;
* a suite is only chosen if it is green, because an arc on a red suite can
  never verify and would read as the loop failing to learn.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

import tools.organic_chain_run as chain
import tools.self_corpus as self_corpus_mod


def _corpus(tmp_path, *names_and_sizes):
    root = tmp_path / "ai-editor-selfcorpus"
    (root / "tests").mkdir(parents=True)
    for name, size in names_and_sizes:
        (root / "tests" / name).write_text("x" * size)
    return SimpleNamespace(root=root)


def _db(tmp_path, *playbooks):
    db = tmp_path / "memory.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE compiled_playbooks (goal_pattern TEXT, status TEXT)")
    for goal, status in playbooks:
        conn.execute("INSERT INTO compiled_playbooks VALUES (?, ?)", (goal, status))
    conn.commit()
    conn.close()
    return db


def _goal(corpus, rel):
    return chain.VERIFY_ONLY_PROMPT.format(
        command=chain.verify_command(corpus.root, rel)
    )


@pytest.fixture()
def all_green(monkeypatch):
    ran: list[list[str]] = []

    def _run(corpus, selection, timeout=0):
        ran.append(list(selection))
        return SimpleNamespace(green=True, passed=3)

    monkeypatch.setattr(self_corpus_mod, "run_suite", _run)
    return ran


def test_a_compiled_suite_is_skipped(tmp_path, all_green) -> None:
    corpus = _corpus(tmp_path, ("test_a.py", 10), ("test_b.py", 20))
    db = _db(tmp_path, (_goal(corpus, "tests/test_a.py"), "compiled"))
    assert chain._fresh_verify_target(corpus, db) == "tests/test_b.py"


def test_a_decompiled_suite_is_not_fresh_either(tmp_path, all_green) -> None:
    """Recompiling a retired reflex is recovery, not a new compile."""
    corpus = _corpus(tmp_path, ("test_a.py", 10), ("test_b.py", 20))
    db = _db(tmp_path, (_goal(corpus, "tests/test_a.py"), "decompiled"))
    assert chain._fresh_verify_target(corpus, db) == "tests/test_b.py"


def test_a_red_suite_is_never_chosen(tmp_path, monkeypatch) -> None:
    corpus = _corpus(tmp_path, ("test_a.py", 10), ("test_b.py", 20))
    db = _db(tmp_path)
    verdicts = {"tests/test_a.py": False, "tests/test_b.py": True}
    monkeypatch.setattr(
        self_corpus_mod,
        "run_suite",
        lambda corpus, selection, timeout=0: SimpleNamespace(
            green=verdicts[selection[0]], passed=1
        ),
    )
    assert chain._fresh_verify_target(corpus, db) == "tests/test_b.py"


def test_an_already_compiled_suite_is_never_even_run(tmp_path, all_green) -> None:
    """Checked against the table FIRST, so the corpus only runs what is used."""
    corpus = _corpus(tmp_path, ("test_a.py", 10), ("test_b.py", 20))
    db = _db(tmp_path, (_goal(corpus, "tests/test_a.py"), "compiled"))
    chain._fresh_verify_target(corpus, db)
    assert all_green == [["tests/test_b.py"]]


def test_exhaustion_is_reported_not_papered_over(tmp_path, all_green) -> None:
    corpus = _corpus(tmp_path, ("test_a.py", 10))
    db = _db(tmp_path, (_goal(corpus, "tests/test_a.py"), "compiled"))
    assert chain._fresh_verify_target(corpus, db) is None
