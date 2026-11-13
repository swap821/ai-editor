"""The council's Memory queen weighs only lessons about the mission's code
(2026-11-13).

The operator's second envelope sent GAGOS's first two missions, tests for
tabStore (UX-02, UX-03), to the council, and the Memory queen deferred both
("5 relevant prior failure(s) to weigh"). The five were lessons about backend
modules (aios.memory.relevance, model_calls.read_ledger, ...), matched by
shared words: the goal named ``tabStore.test.ts`` with no directory, and a
``.ts`` path named no code anyway, so D13's rule (a task that names code
recalls only lessons about that code) never applied. The queen now looks up
with the mission's own files, and frontend sources are code.
"""

from __future__ import annotations

import sqlite3

import pytest

from aios.council.queens.memory import MemoryQueen
from aios.council.reasoning import MistakeBackedRetriever
from aios.memory.mistake import MistakeMemory
from aios.memory.relevance import names_code
from aios.runtime.contracts import MissionContract

TEST = "frontend/src/superbrain/lib/tabStore.test.ts"
CODE = "frontend/src/superbrain/lib/tabStore.ts"
#: The goal as queued on 2026-11-13 (UX-02).
GOAL = "Blueprint UX-02 (the frontend acceptance ledger: workspace identity, content and focus continuity). In tabStore.test.ts add one test beside the file's others (they reset with __resetTabStoreForTests() in beforeEach). Open a content tab with showContentSurface({ code: 'print(1)', language: 'python', filepath: 'kept.py' }) and keep the returned tab's id. Close it: call beginRetractingMaterializedTab(id), read its record from getTabStoreSnapshot().tabs into a variable called retiring, expect it toBeDefined(), then call finishMaterializedTabRetraction(id, retiring!.retractionToken). Expect getTabStoreSnapshot().recoverableTabs to hold an entry with that id and the same content. Then call reopenMaterializedTab(id), expect it to return true, and expect the snapshot to hold exactly one tab with that id, with the same code, language and filepath, its focusId equal to that id, and recoverableTabs no longer holding that id. Do not call any variable by the bare word for a credential, because GAGOS's secret scanner treats that word assigned a long value as a leaked key and scrubs the answer. Change only the test file; tabStore.ts is shown so its API can be read."
#: The five lessons the queen weighed against it, as their texts read.
BACKEND = [
    (
        "tests/test_pin_relevance.py::specific_tokens",
        "In aios.memory.relevance, the module-level GENERIC set contains the word "
        "'test', so specific_tokens() excludes 'test' from its result even though "
        "'test' is a non-numeric token longer than 2 characters.",
    ),
    (
        "tests/test_pin_institutional_skills.py::is_review_ready",
        "In aios.application.memory.institutional_skills, the BIRTH_STATE constant "
        'is not equal to the string "BIRTH"; is_review_ready returns False for a '
        'record whose state is "BIRTH" even when success_count and success rate '
        "meet the defaults, and returns True only when record.state equals the "
        "imported BIRTH_STATE constant.",
    ),
    (
        "tests/test_pin_model_availability.py::is_unavailable",
        "aios.core.model_availability.is_unavailable deletes the (provider, model) "
        "entry from the module-level _unavailable dict when the entry is expired "
        "(older than UNAVAILABLE_TTL_S), so after a False-returning call on an "
        "expired entry the key no longer exists in _unavailable and cannot be "
        "deleted again.",
    ),
    (
        "tests/test_pin_model_calls.py::read_ledger",
        "aios.core.model_calls.read_ledger returns an empty list without raising "
        "when `<data_dir>/model_calls` does not exist, and this holds when `since` "
        "is an offset-naive datetime.",
    ),
    (
        "tests/test_pin_tool_handlers.py::create_file",
        "aios.agents.tool_handlers.create_file resolves the requested path against "
        "read_root itself and, for a path that escapes the root, returns exactly "
        "('[BLOCKED] Path '<path>' escapes the project root.', 'blocked', False) "
        "before any credential or approval check and without invoking snapshot or "
        "audit (both may be None on this path).",
    ),
]


@pytest.fixture()
def mistakes(tmp_path, monkeypatch) -> MistakeMemory:
    import aios.memory.mistake as mistake_module

    monkeypatch.setattr(mistake_module, "assert_learning_permitted", lambda _: None)
    from aios.memory.db import init_memory_db

    init_memory_db(tmp_path / "memory.db")
    memory = MistakeMemory(db_path=tmp_path / "memory.db")
    for task_id, lesson in BACKEND:
        memory.record(task_id, "AssertionError", "cause", "fix", lesson, -0.1)
    return memory


def _verify_all(memory: MistakeMemory) -> None:
    with sqlite3.connect(memory.db_path) as conn:
        conn.execute("UPDATE mistake_pool SET verification_status = 'verified'")


def _review(memory: MistakeMemory):
    contract = MissionContract(
        mission_id="mission-0123456789ab",
        goal=GOAL,
        worker_type="hybrid_plan_worker",
        created_by="gagos",
        workspace_root=".",
        allowed_files=[TEST, CODE],
    )
    queen = MemoryQueen(MistakeBackedRetriever(mistakes=memory))
    return queen.review(contract)


def test_frontend_source_paths_name_code() -> None:
    assert names_code(f"see {CODE}") and names_code(f"see {TEST}")
    assert names_code("frontend/src/workbench/OrganismScene.jsx")
    assert not names_code("tabStore.ts")  # a bare name: no directory, no code


def test_lessons_about_other_code_are_not_weighed(mistakes) -> None:
    _verify_all(mistakes)
    verdict = _review(mistakes)
    assert verdict.verdict == "allow", verdict.reason
    assert verdict.metadata["cautions"] == []


def test_a_lesson_about_the_missions_own_file_is_weighed(mistakes) -> None:
    mistakes.record(
        "frontend-tabstore",
        "AssertionError",
        "cause",
        "fix",
        f"In {CODE}, reopenMaterializedTab refuses when every seat is taken.",
        -0.1,
    )
    _verify_all(mistakes)
    verdict = _review(mistakes)
    assert verdict.verdict == "defer"
    assert len(verdict.metadata["cautions"]) == 1
    assert "reopenMaterializedTab" in verdict.metadata["cautions"][0]
