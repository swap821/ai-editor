"""Per-task scope on /api/generate (aios/application/turns/task_scope.py).

A forge turn may be confined to one directory inside the declared scope roots:
declared by the client (``scopeRoot``) or the launch environment
(``AIOS_TASK_SCOPE``), never by the model, and only ever narrowing. Pinned:

* what can be bound, and that a scope that cannot be honoured is refused;
* the binding holds for every step of a streamed turn, whichever thread and
  context copy runs the step, and never between steps;
* through the real route and tool loop, the SAME model command is approvable
  in one bound scope and a scope violation in another: the binding reaches the
  containment checks inside the stream, not only the code before it.
"""

from __future__ import annotations

import contextvars
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from aios import config
from aios.api.main import app, get_executor, get_ollama_client, get_semantic_indexer
from aios.application.turns.task_scope import (
    TaskScopeError,
    resolve_task_scope,
    scoped_steps,
)
from aios.security import scope_lock
from tests.test_plan_stage import (
    FakeIndexer,
    PlanningAlignedLLM,
    _fake_executor,
    _isolate_turn_memory,
)

ROOT = Path(config.PROJECT_ROOT).resolve()


@pytest.fixture(autouse=True)
def _no_default_scope(monkeypatch) -> None:
    monkeypatch.setattr(config, "TASK_SCOPE", "")


# --------------------------------------------------------------------------- #
# What may be bound
# --------------------------------------------------------------------------- #


def test_no_scope_declared_means_no_binding() -> None:
    assert resolve_task_scope(None) is None
    assert resolve_task_scope("  ") is None


def test_a_declared_root_or_a_directory_inside_one_can_be_bound() -> None:
    declared = [Path(r).resolve() for r in scope_lock.get_scope_roots()]
    scope = resolve_task_scope(str(declared[0].relative_to(ROOT)))
    assert scope is not None and scope.roots == (declared[0],)


def test_the_launch_default_applies_and_the_request_overrides_it(monkeypatch) -> None:
    first, second = [Path(r).resolve() for r in scope_lock.get_scope_roots()][:2]
    monkeypatch.setattr(config, "TASK_SCOPE", str(first))
    assert resolve_task_scope(None).roots == (first,)
    assert resolve_task_scope(str(second)).roots == (second,)


@pytest.mark.parametrize(
    "declared",
    [
        "aios",  # a real directory, but not inside a declared root
        "aios/security",
        str(ROOT.parent),  # above the project
        "training_ground/../aios",  # out through ..
    ],
)
def test_a_scope_outside_the_declared_roots_is_refused(declared: str) -> None:
    with pytest.raises(TaskScopeError, match="not inside a declared scope root"):
        resolve_task_scope(declared)


def test_a_scope_that_is_not_a_directory_is_refused() -> None:
    with pytest.raises(TaskScopeError, match="not a directory"):
        resolve_task_scope("training_ground/__no_such_directory__")


# --------------------------------------------------------------------------- #
# The binding holds for every step, and only then
# --------------------------------------------------------------------------- #


def _observing_turn(seen: list[tuple[Path, ...]], steps: int = 3):
    for index in range(steps):
        seen.append(scope_lock.get_scope_roots())
        yield index


def test_every_step_is_bound_whichever_thread_and_context_runs_it() -> None:
    """Starlette advances a streamed turn on thread-pool threads, each step in
    a fresh copy of the request's context. A binding opened once, before the
    stream, would be gone by the second step."""
    bound = resolve_task_scope("lab")
    unbound = scope_lock.get_scope_roots()
    seen: list[tuple[Path, ...]] = []
    stream = scoped_steps(_observing_turn(seen), bound)

    with ThreadPoolExecutor(max_workers=3) as pool:
        items = []
        while True:
            step = pool.submit(contextvars.copy_context().run, next, stream, None)
            item = step.result()
            if item is None:
                break
            items.append(item)
            # Between steps, nothing is bound.
            assert scope_lock.get_scope_roots() == unbound

    assert items == [0, 1, 2]
    assert seen == [bound.roots] * 3


def test_a_stream_closed_early_is_closed_inside_its_binding() -> None:
    bound = resolve_task_scope("lab")
    at_close: list[tuple[Path, ...]] = []

    def turn():
        try:
            yield 1
            yield 2
        finally:
            at_close.append(scope_lock.get_scope_roots())

    stream = scoped_steps(turn(), bound)
    assert next(stream) == 1
    stream.close()
    assert at_close == [bound.roots]


# --------------------------------------------------------------------------- #
# Through the real route and tool loop
# --------------------------------------------------------------------------- #


class MkdirOllama:
    """Every turn asks to create ``training_ground/build``: YELLOW where
    training_ground is in scope, a scope violation where it is not."""

    def list_models(self) -> dict:
        return {"available": True, "models": ["llama3.2:3b"]}

    def chat(self, messages, *, tools: Optional[list] = None, model=None) -> dict:
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "execute_terminal",
                        "arguments": {"command": "mkdir training_ground/build"},
                    }
                }
            ],
        }


def _turn(tmp_path, scope_root: Optional[str]):
    app.dependency_overrides[get_ollama_client] = lambda: MkdirOllama()
    app.dependency_overrides[get_executor] = _fake_executor
    app.dependency_overrides[get_semantic_indexer] = lambda: FakeIndexer()
    _isolate_turn_memory(tmp_path, PlanningAlignedLLM)
    body = {
        "messages": [{"role": "user", "content": [{"text": "make the build dir"}]}],
        "modelId": "ollama.llama3.2:3b",
        "sessionId": "task-scope",
    }
    if scope_root is not None:
        body["scopeRoot"] = scope_root
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            return client.post("/api/generate", json=body)
    finally:
        app.dependency_overrides.clear()


def test_unbound_the_command_waits_for_approval(tmp_path) -> None:
    response = _turn(tmp_path, None)
    assert response.status_code == 200
    assert "event: human_required" in response.text


def test_bound_to_the_commands_own_root_it_still_waits_for_approval(tmp_path) -> None:
    response = _turn(tmp_path, "training_ground")
    assert response.status_code == 200
    assert "event: human_required" in response.text


def test_bound_elsewhere_the_same_command_is_a_scope_violation(tmp_path) -> None:
    """The positive control is the two tests above: same model, same command.
    Only the binding differs, and only it can make this one refuse."""
    response = _turn(tmp_path, "lab")
    assert response.status_code == 200
    assert "event: human_required" not in response.text
    assert "Scope violation" in response.text


def test_a_scope_the_lock_would_not_honour_is_a_400_not_an_unbound_turn(
    tmp_path,
) -> None:
    response = _turn(tmp_path, "aios")
    assert response.status_code == 400
    assert "not inside a declared scope root" in response.text


def test_a_stream_that_cannot_be_bound_is_refused_not_run_unbound() -> None:
    from aios.application.turns.task_scope import bound_stream_factory

    async def async_turn(*_):
        yield 1

    factory = bound_stream_factory(async_turn, resolve_task_scope("lab"))
    with pytest.raises(TypeError, match="only a synchronous turn stream"):
        factory(None, None)


def test_the_turn_is_prepared_inside_its_binding() -> None:
    from aios.application.turns.task_scope import bound_preparer

    bound = resolve_task_scope("lab")
    seen: list[tuple[Path, ...]] = []
    bound_preparer(lambda *_: seen.append(scope_lock.get_scope_roots()), bound)(
        None, None
    )
    assert seen == [bound.roots]


def test_a_bound_turn_tells_the_model_its_scope_and_where_commands_run() -> None:
    from aios.application.turns.task_scope import task_scope_guidance

    assert task_scope_guidance() is None
    with scope_lock.scope_context([ROOT / "lab"]):
        note = task_scope_guidance()
    assert note is not None
    # lab's parent is the project root, so lab is named as `lab`.
    assert "only inside lab." in note
    assert ROOT.as_posix() in note
