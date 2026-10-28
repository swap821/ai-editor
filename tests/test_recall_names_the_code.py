"""A task that names code recalls only lessons about that code (D13).

D12's local judged run (docs/learning/PAYOFF_D12_RESULT.md) recorded which
lessons each target was shown. Recall varied by task, but was rarely about it:
27 of 150 targets saw a lesson from their own module, and one lesson, about
`plan_with_llm`, was shown on 109 of them. D9's rule recalls a lesson that
shares any specific word with the task, and a task holds a whole function's
source, so common names in code decided what was shown.

Now a task that names code (a module path or an `aios.` name) recalls a lesson
only if the lesson is about that code: its module, or a distinctive function
it was learned on. A task that names no code keeps D9's rule.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aios.memory.mistake import MistakeMemory
from aios.memory.relevance import (
    distinctive_name,
    lesson_homes,
    names_code,
    names_the_same_code,
)

# The judged task's own header (tools/reverse_engineer_gagos.py PROMPT).
TASK = """\
Module path: {module}
Import it as: from {import_path} import {function}

Here is the complete source of the function:

```python
{source}
```

Write a pytest test file that pins this function's real behaviour.
"""


def _task(module: str, function: str, source: str) -> str:
    return TASK.format(
        module=module,
        import_path=module[: -len(".py")].replace("/", "."),
        function=function,
        source=source,
    )


def _store(tmp_path: Path) -> MistakeMemory:
    from aios.memory.db import init_memory_db

    path = tmp_path / "memory.db"
    init_memory_db(path)
    return MistakeMemory(path)


def _verified(store: MistakeMemory, task_id: str, text: str, root: str = "r") -> int:
    mistake_id = store.record(task_id, "AssertionError", root, "fixed it", text, -0.1)
    store.promote(mistake_id)
    return mistake_id


def _ids(store: MistakeMemory, query: str) -> set[int]:
    return {row["mistake_id"] for row in store.relevant_verified(query, limit=5)}


PLANNER_SOURCE = (
    "def plan_steps(goal):\n    llm = get_llm()\n    return plan_with_llm(llm, goal)\n"
)
RELEVANCE_SOURCE = (
    "def signature(text):\n"
    "    normalized = ' '.join(sorted(tokens(text)))\n"
    "    return hashlib.sha256(normalized.encode()).hexdigest()\n"
)


def test_a_lesson_about_other_code_is_not_shown_however_many_words_it_shares(
    tmp_path,
) -> None:
    """The 109-of-150 lesson: it shares the task's words but is about other
    code, so a task that names its own code does not see it."""
    store = _store(tmp_path)
    loud = _verified(
        store,
        "practice:run:aios/core/planner.py::plan_with_llm#resolved",
        "plan_with_llm in aios/core/planner.py hashes the normalized goal tokens "
        "with sha256 before it calls the llm",
    )
    task = _task("aios/memory/relevance.py", "signature", RELEVANCE_SOURCE)
    # Precondition: D9's rule would have shown it (shared specific words).
    from aios.memory.relevance import specific_relevance

    assert specific_relevance(task, store.get(loud)["lesson_text"]) > 0
    assert _ids(store, task) == set()


def test_a_lesson_from_the_same_module_is_shown(tmp_path) -> None:
    store = _store(tmp_path)
    same = _verified(
        store,
        "practice:run:aios/memory/relevance.py::content_hash#resolved",
        "content_hash lower-cases and collapses whitespace before hashing",
    )
    task = _task("aios/memory/relevance.py", "signature", RELEVANCE_SOURCE)
    assert _ids(store, task) == {same}


def test_a_lesson_about_a_module_the_task_imports_is_shown(tmp_path) -> None:
    """The source names `aios.core.planner` (an import), so a lesson learned
    there is about code this task uses."""
    store = _store(tmp_path)
    # `build` is too generic to match on its own: only the module can.
    used = _verified(
        store,
        "practice:run:aios/core/planner.py::build#resolved",
        "build returns the steps the llm produced",
    )
    source = "from aios.core.planner import plan_with_llm\n" + PLANNER_SOURCE
    task = _task("aios/agents/forge.py", "plan_steps", source)
    assert _ids(store, task) == {used}


def test_a_distinctive_function_the_task_calls_is_enough(tmp_path) -> None:
    store = _store(tmp_path)
    called = _verified(
        store,
        "practice:run:aios/core/planner.py::plan_with_llm#resolved",
        "returns the steps the model produced",
    )
    task = _task("aios/agents/forge.py", "plan_steps", PLANNER_SOURCE)
    assert distinctive_name("plan_with_llm")
    assert _ids(store, task) == {called}


def test_a_short_generic_function_name_is_not_enough(tmp_path) -> None:
    store = _store(tmp_path)
    _verified(
        store,
        "practice:run:aios/cli/entry.py::run#resolved",
        "run exits with status 2 on a bad flag",
    )
    task = _task(
        "aios/agents/forge.py", "plan_steps", "def plan_steps(g):\n    run(g)\n"
    )
    assert not distinctive_name("run")
    assert _ids(store, task) == set()


def test_a_lesson_whose_text_names_the_code_is_shown_without_a_practice_task_id(
    tmp_path,
) -> None:
    """A live turn's lesson has a plain task id; its text can still name code,
    as a dotted name with the function on the end."""
    store = _store(tmp_path)
    named = _verified(
        store,
        "20260927T221713-b131ac59",
        "aios.memory.relevance.signature sorts the tokens before hashing",
    )
    task = _task("aios/memory/relevance.py", "signature", RELEVANCE_SOURCE)
    assert _ids(store, task) == {named}


def test_a_lesson_that_names_no_code_is_not_shown_to_a_task_that_does(
    tmp_path,
) -> None:
    store = _store(tmp_path)
    _verified(store, "20260927T221713-b131ac59", "sha256 digests are hex encoded")
    task = _task("aios/memory/relevance.py", "signature", RELEVANCE_SOURCE)
    assert _ids(store, task) == set()


def test_a_query_that_names_no_code_keeps_d9s_rule(tmp_path) -> None:
    """Plain chat is unchanged: a shared specific word still recalls."""
    store = _store(tmp_path)
    domain = _verified(
        store, "t1", "network calls to the deploy api must time out after 10 s"
    )
    query = "why does the deploy api hang on network calls?"
    assert not names_code(query)
    assert _ids(store, query) == {domain}


def test_a_redacted_task_id_still_yields_its_function() -> None:
    """Practice ids whose path the secret scanner redacted keep the function."""
    modules, functions = lesson_homes(
        "practice:<REDACTED:HIGH_ENTROPY:f5a6541f>/keystore.py::learning_public_key",
        [],
    )
    assert "learning_public_key" in functions
    assert names_the_same_code(
        "def f():\n    return learning_public_key(store)\n",
        "x::learning_public_key",
        [],
    )


@pytest.mark.parametrize(
    "query, expected",
    [
        ("Module path: aios/memory/relevance.py", True),
        ("from aios.memory.relevance import signature", True),
        ("what changed in the deploy api?", False),
        ("the value is 3.14", False),
    ],
)
def test_what_counts_as_naming_code(query, expected) -> None:
    assert names_code(query) is expected


def test_a_two_part_dotted_prefix_is_too_broad_to_match() -> None:
    """`aios.memory` names a package, not code a lesson is about."""
    assert not names_the_same_code(
        "from aios.memory.db import init_memory_db",
        "",
        ["aios.memory.relevance.signature sorts tokens"],
    )


def test_a_path_fragment_the_scanner_left_names_no_code(tmp_path) -> None:
    """Lesson #195's task id lost its path to redaction, all but `ce.py`, which
    sits inside `service.py`, `reference.py` and `workspace.py`. Offline, on
    D12's snapshot, it was shown on 143 of 150 judged targets until this."""
    store = _store(tmp_path)
    _verified(
        store,
        "practice:20261<REDACTED:HIGH_ENTROPY:46b537b5>ce.py::key_id#resolved",
        "key_id returns the first 16 hex characters of the digest",
    )
    task = _task(
        "aios/core/service.py", "start_service", "def start_service(x):\n    return x\n"
    )
    assert lesson_homes(
        "practice:20261<REDACTED:HIGH_ENTROPY:46b537b5>ce.py::key_id#resolved", []
    ) == (set(), {"key_id"})
    assert _ids(store, task) == set()


def test_a_bare_filename_in_prose_names_no_code(tmp_path) -> None:
    store = _store(tmp_path)
    _verified(
        store,
        "20260927T221713-b131ac59",
        "plain nouns such as the ones in auth.py are not recognised as entities",
    )
    task = _task(
        "aios/api/auth.py", "check_token", "def check_token(t):\n    return t\n"
    )
    assert _ids(store, task) == set()


def test_a_name_inside_a_longer_name_is_not_a_mention() -> None:
    lesson = ["aios.memory.provenance.key_id hashes the raw public bytes"]
    assert not names_the_same_code(
        "from aios.application.memory.provenance_policy import semantic_digest",
        "",
        lesson,
    )
    assert not names_the_same_code(
        "from aios.memory.provenance_store import open_store", "", lesson
    )
    assert names_the_same_code("from aios.memory.provenance import key_id", "", lesson)
