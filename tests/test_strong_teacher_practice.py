"""D12: a strong model TEACHES -- it writes every lesson -- while the student
attempts; and practice workers can run in parallel without sharing a corpus
worktree, a store or a trail.

Practice run 2 (2026-10-12) had the student write its own lessons: 4 of 19
were false. The lesson writer is the lever, so it is a parameter now.
"""

from __future__ import annotations

import json

import pytest

from tools import organic_chain_run as ocr


def _ladder():
    return [("student", object()), ("teacher", object())]


def test_without_a_teacher_the_first_model_writes_the_lessons() -> None:
    ladder = _ladder()
    assert ocr.choose_teacher(ladder, None, timeout_s=1) is ladder[0]


def test_a_teacher_in_the_ladder_is_reused_not_resolved_again() -> None:
    ladder = _ladder()

    def resolve(spec, timeout_s):
        raise AssertionError("a teacher already in the ladder must not be resolved")

    assert ocr.choose_teacher(ladder, "teacher", timeout_s=1, resolve=resolve) == (
        "teacher",
        ladder[1][1],
    )


def test_a_teacher_outside_the_ladder_is_resolved() -> None:
    teacher_client = object()
    asked: list[str] = []

    def resolve(spec, timeout_s):
        asked.append(spec)
        return teacher_client, spec

    assert ocr.choose_teacher(_ladder(), "elsewhere", timeout_s=1, resolve=resolve) == (
        "elsewhere",
        teacher_client,
    )
    assert asked == ["elsewhere"]


def test_an_unreachable_teacher_refuses_the_run_instead_of_standing_in() -> None:
    """A stand-in would write lessons attributed to a model that never wrote them."""

    def resolve(spec, timeout_s):
        raise ocr.CorpusError("not configured")

    with pytest.raises(ocr.CorpusError):
        ocr.choose_teacher(_ladder(), "elsewhere", timeout_s=1, resolve=resolve)


def test_each_worker_gets_its_own_store_corpus_and_trail(tmp_path, monkeypatch) -> None:
    # Restored at teardown: main() rebinds the module paths.
    monkeypatch.setattr(ocr, "DB", ocr.DB)
    monkeypatch.setattr(ocr, "WORKTREE", ocr.WORKTREE)
    monkeypatch.setattr(ocr, "TRAIL", ocr.TRAIL)
    seen: dict = {}

    def run_chain(**kwargs):
        seen.update(kwargs, db=ocr.DB, worktree=ocr.WORKTREE)
        raise ocr.CorpusError("stop before any model or corpus")

    monkeypatch.setattr(ocr, "run_chain", run_chain)
    store, corpus, trail = (
        tmp_path / "w1.db",
        tmp_path / "corpus-w1",
        tmp_path / "w1.jsonl",
    )
    assert (
        ocr.main(
            [
                "--models",
                "student,teacher",
                "--teacher",
                "teacher",
                "--db",
                str(store),
                "--corpus-dir",
                str(corpus),
                "--trail",
                str(trail),
            ]
        )
        == 1
    )
    assert seen["teacher"] == "teacher"
    assert seen["db"] == store.resolve()
    assert seen["worktree"] == corpus.resolve()
    rows = [json.loads(line) for line in trail.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["outcome"] == "aborted"
