"""Lesson recall is task-specific, and one lesson takes one slot (D9).

The calibration run (2026-09-27) found every task recalled the same five
lessons: relevance counted ANY shared word, and a long task and a long lesson
always share generic ones ("test", "function", "expected"). On the live store
(2026-10-12) one rule also sat in eight rows, so it alone could fill the block.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aios.memory.mistake import MistakeMemory, distinct_lessons
from aios.memory.relevance import specific_relevance, specific_tokens

TEMPLATE = (
    "Write a pytest test file that pins this function's real behaviour. "
    "Import the function exactly as shown. Assert what it returns for those "
    "arguments; do not guess the expected value.\n\n```python\n{source}\n```"
)
GENERIC_LESSON = (
    "Ensure that test cases accurately reflect the expected behavior of the "
    "function being tested, and update tests when the function's behavior changes."
)


def _store(tmp_path: Path) -> MistakeMemory:
    from aios.memory.db import init_memory_db

    path = tmp_path / "memory.db"
    init_memory_db(path)
    return MistakeMemory(path)


def _verified(store: MistakeMemory, task: str, text: str, root: str = "r") -> int:
    mistake_id = store.record(task, "AssertionError", root, "fixed it", text, -0.1)
    store.promote(mistake_id)
    return mistake_id


def test_generic_vocabulary_is_not_evidence() -> None:
    assert (
        specific_tokens("Write a pytest test: assert the function returns the value")
        == set()
    )
    assert specific_tokens("def f(x): return None if len(x) > 3 else str(x)") == set()
    kept = specific_tokens(
        "normalize_command strips the deploy api aios/agents/x.py 42"
    )
    assert {"normalize_command", "deploy", "api", "aios/agents/x.py"} <= kept
    assert "42" not in kept and "the" not in kept


def test_generic_overlap_scores_zero_and_specific_overlap_scores() -> None:
    task = TEMPLATE.format(source="def library_summary(rows):\n    return len(rows)")
    assert specific_relevance(task, GENERIC_LESSON) == 0.0
    lesson = "normalize_command returns the command with its trailing spaces stripped"
    about_it = TEMPLATE.format(source="def normalize_command(c):\n    return c.strip()")
    assert specific_relevance(about_it, lesson) > 0


def test_two_unrelated_tasks_no_longer_recall_the_same_lessons(tmp_path) -> None:
    store = _store(tmp_path)
    generic = _verified(store, "t1", GENERIC_LESSON)
    about_normalize = _verified(
        store,
        "t2",
        "normalize_command keeps internal spaces; strip only the ends",
        root="normalize_command returned 'ls  -a' with the inner double space",
    )
    about_cache = _verified(
        store, "t3", "cache_key includes the principal id", root="cache_key collided"
    )
    normalize_task = TEMPLATE.format(source="def normalize_command(c):\n    return c")
    cache_task = TEMPLATE.format(source="def cache_key(p, k):\n    return f'{p}:{k}'")
    unrelated = TEMPLATE.format(
        source="def library_summary(rows):\n    return len(rows)"
    )

    ids = lambda q: [r["mistake_id"] for r in store.relevant_verified(q, 5)]  # noqa: E731
    assert ids(normalize_task) == [about_normalize]
    assert ids(cache_task) == [about_cache]
    assert ids(unrelated) == [], "nothing specific in common: recall nothing"
    assert generic not in ids(normalize_task) + ids(cache_task) + ids(unrelated)


def test_a_plain_language_domain_match_still_recalls(tmp_path) -> None:
    store = _store(tmp_path)
    lesson = _verified(store, "s", "verify api deploy", root="api deploy failed")
    assert [r["mistake_id"] for r in store.relevant_verified("deploy the api")] == [
        lesson
    ]


def test_one_lesson_takes_one_slot() -> None:
    rows: list[dict[str, Any]] = [
        {"mistake_id": i, "lesson_text": "  Strip  the ends. "} for i in range(8)
    ] + [{"mistake_id": 99, "lesson_text": "a different rule"}]
    kept = distinct_lessons(rows, 5)
    assert [r["mistake_id"] for r in kept] == [0, 99], "case/space-normalised text"


class _Gate:
    """Admits only the ids it is told to."""

    def __init__(self, admitted: set[int]) -> None:
        self.admitted_ids = admitted

    def admits(self, table, row_id, digest, *, principal) -> bool:
        return int(row_id) in self.admitted_ids


def test_a_refused_copy_never_hides_an_admitted_twin(tmp_path) -> None:
    """The refused copy is the NEWEST, so it ranks first among equals: a
    collapse before the gate would keep it, the gate would drop it, and the
    admitted twin would never be seen."""
    from aios.application.memory.adapters import MistakeMemoryAdapter

    store = _store(tmp_path)
    admitted = _verified(store, "a", "normalize_command keeps inner spaces")
    refused = _verified(store, "b", "normalize_command keeps inner spaces")
    assert refused > admitted
    adapter = MistakeMemoryAdapter(store, gate=_Gate({admitted}))
    recalled = adapter.relevant_verified("pin normalize_command", 5, principal=None)
    assert [r["mistake_id"] for r in recalled] == [admitted]


def test_admitted_copies_take_one_slot(tmp_path) -> None:
    from aios.application.memory.adapters import MistakeMemoryAdapter

    store = _store(tmp_path)
    copies = {
        _verified(store, t, "normalize_command keeps inner spaces") for t in "abc"
    }
    other = _verified(store, "d", "normalize_command drops a trailing newline")
    adapter = MistakeMemoryAdapter(store, gate=_Gate(copies | {other}))
    recalled = adapter.relevant_verified("pin normalize_command", 5, principal=None)
    ids = [r["mistake_id"] for r in recalled]
    assert len(ids) == 2 and other in ids and len(set(ids) & copies) == 1


def test_a_pending_lesson_and_its_verified_twin_take_one_slot(tmp_path) -> None:
    from aios.application.memory.adapters import MistakeMemoryAdapter

    store = _store(tmp_path)
    text = "normalize_command keeps inner spaces"
    _verified(store, "other-task", text)
    pending = store.record("this-task", "AssertionError", "r", "f", text, -0.1)
    import sqlite3

    with sqlite3.connect(store.db_path) as conn:  # recall needs a command to prove
        conn.execute(
            "UPDATE mistake_pool SET failed_command = 'pytest -q' WHERE id = ?",
            (pending,),
        )
    adapter = MistakeMemoryAdapter(store)
    recalled = adapter.recall_relevant(
        "pin normalize_command", "this-task", 5, principal=None
    )
    assert len(recalled) == 1 and recalled[0]["verification_status"] == "pending"
