"""Per-task scope: one forge turn confined to one directory.

The declared scope roots (``AIOS_SCOPE_ROOTS``: ``training_ground``, ``lab``,
``work``) are where the system may act at all, for every turn alike. A turn
about one project could still create files in, or run commands against,
another. ``aios/security/scope_lock.py`` has had narrow-only per-task binding
since 2026-10-18 (§VIII, "B"): a bound root is honoured only inside a declared
root, so a binding can narrow containment and never widen it. Nothing in
production used it. This wires it into ``/api/generate``.

Where a turn's scope comes from, in order:

1. the request's ``scopeRoot``, which the client declares;
2. ``AIOS_TASK_SCOPE``, set in the backend's launch environment;
3. neither: the turn is not bound, exactly as before.

Never from the model: a scope the model could pick would be a sandbox it
chose for itself. A declared scope that cannot be honoured (no such
directory, or not inside a declared root) is refused, never run unbound.

What a binding changes: every containment check on the turn's path
(``gateway.classify``, the file tools, the executor's working directory and
its writable mounts) reads the bound roots. So do the keys that approvals,
earned autonomy and reflexes are filed under (``autonomy.workspace_id``,
``reflex_contract.scope_identity``). Something earned in one scope does not
apply in another, which is the point of per-workspace earning. Reads are not
narrowed: the file tools read anywhere in the project, as before.

How it is bound: the scope is a context variable. The turn coordinator
advances the forge's synchronous stream with ``iterate_in_threadpool``, each
step on a thread-pool thread with a fresh copy of the request's context. A
binding opened in one step and closed in another would be lost in between and
could not be reset. So the turn is prepared inside the binding
(:func:`bound_preparer`), and its stream opens and closes the binding around
each step, inside that step (:func:`bound_stream_factory`,
:func:`scoped_steps`).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any, Optional, TypeVar

from aios import config
from aios.security import scope_lock
from aios.security.scope_lock import ScopeContext

_T = TypeVar("_T")


class TaskScopeError(ValueError):
    """A declared task scope that cannot be honoured."""


def resolve_task_scope(requested: Optional[str]) -> Optional[ScopeContext]:
    """The scope this turn is confined to, or ``None`` for no binding.

    A relative path is taken from the project root. Raises
    :class:`TaskScopeError` for a scope that is declared but cannot be
    honoured.
    """
    raw = (requested or "").strip() or str(config.TASK_SCOPE or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path(config.PROJECT_ROOT) / path
    path = path.resolve()
    if not path.is_dir():
        raise TaskScopeError(f"task scope {raw!r} is not a directory")
    scope = ScopeContext.of([path])
    # The frozen authority's own rule decides, so the check and every later
    # containment decision cannot disagree: it keeps a bound root only inside
    # a declared root (or an admitted staged workspace).
    if not scope_lock.get_scope_roots(scope):
        raise TaskScopeError(f"task scope {raw!r} is not inside a declared scope root")
    return scope


def scoped_steps(events: Iterable[_T], scope: ScopeContext) -> Iterator[_T]:
    """Advance *events* with *scope* bound for each step, and only then.

    The binding opens and closes inside each step, so it holds whichever
    thread runs the step, and a consumer's own work between steps is never
    bound. When the stream ends early, the inner stream is closed inside the
    binding too, so its cleanup sees the scope it ran in.
    """
    iterator: Optional[Iterator[_T]] = None
    try:
        while True:
            with scope_lock.scope_context(scope.roots):
                if iterator is None:
                    iterator = iter(events)
                try:
                    item = next(iterator)
                except StopIteration:
                    return
            yield item
    finally:
        close = getattr(iterator, "close", None)
        if callable(close):
            with scope_lock.scope_context(scope.roots):
                close()


def bound_preparer(
    preparer: Callable[..., None], scope: ScopeContext
) -> Callable[..., None]:
    """*preparer*, run inside the binding (the reflex match reads the scope)."""

    def prepare(*args: Any, **kwargs: Any) -> None:
        with scope_lock.scope_context(scope.roots):
            preparer(*args, **kwargs)

    return prepare


def bound_stream_factory(
    factory: Callable[..., Iterable[_T]], scope: ScopeContext
) -> Callable[..., Iterator[_T]]:
    """*factory*'s stream, bound step by step.

    Only a synchronous stream can be bound this way. Anything else is refused
    rather than returned unbound: a turn that silently ran wider than its
    declared scope is the failure this module exists to prevent.
    """

    def stream(*args: Any, **kwargs: Any) -> Iterator[_T]:
        with scope_lock.scope_context(scope.roots):
            events = factory(*args, **kwargs)
        if (
            hasattr(events, "__aiter__")
            or inspect.isawaitable(events)
            or not (hasattr(events, "__iter__"))
        ):
            raise TypeError("a task scope can bind only a synchronous turn stream")
        return scoped_steps(events, scope)

    return stream


def task_scope_guidance() -> Optional[str]:
    """What the model is told when its turn is bound, or ``None`` when not.

    The tool descriptions name only ``training_ground/``, and a bound turn runs
    its commands from the parent of its root (``scope_lock.command_cwd``), so
    without this a model would name files from the wrong place and every
    command would fail its scope check.
    """
    bound = scope_lock.current_scope()
    if bound is None:
        return None
    roots = scope_lock.get_scope_roots()
    if not roots:
        return None
    cwd = scope_lock.command_cwd()
    shown = []
    for root in roots:
        try:
            shown.append(Path(root).relative_to(cwd).as_posix())
        except ValueError:
            shown.append(Path(root).as_posix())
    first = shown[0]
    return (
        "TASK SCOPE: this turn may create files, edit files and run commands "
        f"only inside {', '.join(shown)}. Commands run from {cwd.as_posix()}, "
        f"so name files from there, for example `pytest {first}/tests/` or "
        f"`{first}/path/to/file.py`. Anything outside is refused."
    )


__all__ = [
    "TaskScopeError",
    "bound_preparer",
    "bound_stream_factory",
    "resolve_task_scope",
    "scoped_steps",
    "task_scope_guidance",
]
