"""A task can bind its own scope without any other task seeing it.

Inventory item 3, applied under §VIII with operator authorization.

`ScopeLockAuthority` held ONE process-global mutable list of scope roots, so
there was no way for a lane to declare a workspace without every other lane's
containment check observing it. Measured before the change: `set_scope_roots`
had ZERO production callers -- every caller was a test -- so the race was latent
rather than live, but it blocks concurrent lanes and multi-project autonomy
outright, and it is why ~9 test sites must save and restore global state by hand.

## Why the resolution moved INSIDE the frozen module

The proposal (`release/organ-2/2026-08-31-scope-context-proposal.md`) rejected a
contextvars override in a NON-frozen module, because `gateway.classify` would go
on reading the global and "what is in scope?" would have two answers that can
disagree -- the shape behind two containment escapes already found here.

With §VIII authorization the override goes inside `get_scope_roots` itself, which
is the single place the question is answered. Every caller -- including the
frozen `gateway.classify` -- inherits it for free, and no second derivation
exists. The objection in the proposal applied to the workaround, not to this.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Iterator

import pytest

from aios.security import scope_lock
from aios.security.gateway import Zone, classify


@pytest.fixture()
def restore_scope() -> Iterator[None]:
    previous = scope_lock.get_scope_roots()
    try:
        yield
    finally:
        scope_lock.set_scope_roots(previous)


@pytest.fixture()
def workspaces(tmp_path: Path) -> tuple[Path, Path]:
    a = tmp_path / "project-a"
    b = tmp_path / "project-b"
    a.mkdir()
    b.mkdir()
    return a, b


# --------------------------------------------------------------------------- #
# The invariant that protects every existing caller
# --------------------------------------------------------------------------- #
def test_with_no_scope_and_no_binding_nothing_changed() -> None:
    """The whole change must be additive.

    Item 3 adds a capability; it removes no check. If this fails, the frozen-core
    edit changed behaviour for callers that never asked for it -- which is the
    one thing a §VIII change must not do.
    """
    assert scope_lock.get_scope_roots() == scope_lock.get_scope_roots(None)
    assert scope_lock.current_scope() is None
    assert classify("touch training_ground/x.py").zone is Zone.YELLOW
    assert classify("rm -rf /").zone is Zone.RED


# --------------------------------------------------------------------------- #
# Binding
# --------------------------------------------------------------------------- #
def test_a_bound_scope_confines_containment_and_then_releases(
    workspaces: tuple[Path, Path], restore_scope: None
) -> None:
    a, _ = workspaces
    default = scope_lock.get_scope_roots()

    with scope_lock.scope_context([a]):
        assert scope_lock.get_scope_roots() == (a.resolve(),)
        assert classify("touch training_ground/x.py").zone is Zone.RED

    assert scope_lock.get_scope_roots() == default
    assert classify("touch training_ground/x.py").zone is Zone.YELLOW


def test_the_binding_is_released_even_when_the_block_raises(
    workspaces: tuple[Path, Path], restore_scope: None
) -> None:
    """A scope that leaked because a task raised is a containment bug.

    The failure mode is silent: every later check in the process would run
    against a workspace nobody declared for it.
    """
    a, _ = workspaces
    default = scope_lock.get_scope_roots()

    with pytest.raises(RuntimeError):
        with scope_lock.scope_context([a]):
            raise RuntimeError("boom")

    assert scope_lock.get_scope_roots() == default


def test_an_empty_scope_is_refused_rather_than_treated_as_everything(
    tmp_path: Path,
) -> None:
    """Fail-closed, matching `set_scope_roots`. An empty scope is a mistake."""
    with pytest.raises(ValueError):
        scope_lock.ScopeContext.of([])
    with pytest.raises(ValueError):
        with scope_lock.scope_context([]):
            pass


def test_an_explicit_scope_beats_the_binding(
    workspaces: tuple[Path, Path], restore_scope: None
) -> None:
    """Explicit beats ambient, so a caller can always be unambiguous."""
    a, b = workspaces
    explicit = scope_lock.ScopeContext.of([b])
    with scope_lock.scope_context([a]):
        assert scope_lock.get_scope_roots(explicit) == (b.resolve(),)
        assert classify(f"touch {b}/x.py", scope=explicit).zone is Zone.YELLOW
        assert classify(f"touch {a}/x.py", scope=explicit).zone is Zone.RED


# --------------------------------------------------------------------------- #
# The actual point: isolation between concurrent tasks
# --------------------------------------------------------------------------- #
def test_two_concurrent_tasks_do_not_observe_each_others_scope(
    workspaces: tuple[Path, Path], restore_scope: None
) -> None:
    """The defect item 3 exists to fix, exercised rather than described.

    Both tasks interleave deliberately (each awaits after binding) so a
    process-global implementation would fail: task B's binding would be visible
    to task A when it resumes.
    """
    a, b = workspaces
    observed: dict[str, tuple[Path, ...]] = {}

    async def lane(name: str, root: Path) -> None:
        with scope_lock.scope_context([root]):
            await asyncio.sleep(0)  # yield, letting the other lane bind
            await asyncio.sleep(0)
            observed[name] = scope_lock.get_scope_roots()

    async def both() -> None:
        await asyncio.gather(lane("a", a), lane("b", b))

    asyncio.run(both())

    assert observed["a"] == (a.resolve(),)
    assert observed["b"] == (b.resolve(),)


def test_a_bound_scope_does_not_leak_into_the_process_default(
    workspaces: tuple[Path, Path], restore_scope: None
) -> None:
    """Unlike `set_scope_roots`, binding mutates nothing others can see."""
    a, _ = workspaces
    default = scope_lock.get_scope_roots()

    async def bind_and_check() -> tuple[Path, ...]:
        with scope_lock.scope_context([a]):
            return scope_lock.get_scope_roots()

    assert asyncio.run(bind_and_check()) == (a.resolve(),)
    assert scope_lock.get_scope_roots() == default


# --------------------------------------------------------------------------- #
# The caveat, pinned rather than left to be discovered
# --------------------------------------------------------------------------- #
def test_a_bare_thread_does_not_inherit_the_binding(
    workspaces: tuple[Path, Path], restore_scope: None
) -> None:
    """Documented limitation, asserted so it cannot silently change.

    `contextvars` do NOT propagate into a bare `threading.Thread`. The thread
    falls back to the process default, which may be WIDER than the binding --
    a fail-OPEN direction. That is exactly why every check also takes an
    explicit `scope=`: work crossing a thread boundary must pass the context
    rather than assume it follows.

    If Python ever changes this, this test fails and the guidance gets revisited
    deliberately instead of the caveat quietly becoming false.
    """
    a, _ = workspaces
    default = scope_lock.get_scope_roots()
    seen: dict[str, tuple[Path, ...]] = {}

    with scope_lock.scope_context([a]) as ctx:
        def in_thread() -> None:
            seen["ambient"] = scope_lock.get_scope_roots()
            seen["explicit"] = scope_lock.get_scope_roots(ctx)

        thread = threading.Thread(target=in_thread)
        thread.start()
        thread.join()

    assert seen["ambient"] == default, (
        "a bare thread now inherits the binding -- good news, but the explicit "
        "`scope=` guidance in scope_lock's docstring must be revisited"
    )
    assert seen["explicit"] == (a.resolve(),), (
        "handing the ScopeContext across the thread boundary must work; it is "
        "the supported way to cross one"
    )


# --------------------------------------------------------------------------- #
# Consistency: the layers must agree under the same scope
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "command_template, expect_in_scope",
    [
        ("touch {a}/inside.py", True),
        ("touch {b}/outside.py", False),
        ("touch training_ground/elsewhere.py", False),
    ],
)
def test_the_gateway_and_the_scope_check_agree_under_a_bound_scope(
    workspaces: tuple[Path, Path],
    restore_scope: None,
    command_template: str,
    expect_in_scope: bool,
) -> None:
    """Differential, in the spirit of tests/adversarial/test_control_consistency.py.

    Two containment escapes in this repo came from two layers answering the same
    question differently. A bound scope must never make `command_stays_in_scope`
    say contained while `gateway.classify` says otherwise.
    """
    a, b = workspaces
    command = command_template.format(a=a, b=b)

    with scope_lock.scope_context([a]):
        scoped = scope_lock.command_stays_in_scope(command)
        zone = classify(command).zone

    assert scoped.in_scope is expect_in_scope
    # RED is exactly how the gateway expresses a scope violation.
    assert (zone is not Zone.RED) is expect_in_scope, (
        f"gateway said {zone.name} while the scope check said "
        f"in_scope={scoped.in_scope} for {command!r}"
    )


def test_the_executor_cwd_follows_the_same_scope(
    workspaces: tuple[Path, Path], restore_scope: None
) -> None:
    """The base that is CHECKED and the base that is EXECUTED must not drift.

    That pair has drifted once already and the drift was an escape. Item 3 adds
    a second way for them to disagree -- one carrying a scope and the other not
    -- so it is pinned here.
    """
    from aios.core.executor import Executor

    a, _ = workspaces
    ctx = scope_lock.ScopeContext.of([a])

    executor = Executor.__new__(Executor)  # no __init__ side effects needed
    assert executor._scope_cwd(ctx) == scope_lock.command_cwd(ctx)
    assert executor._scope_cwd(ctx) == a.resolve().parent

    with scope_lock.scope_context([a]):
        assert executor._scope_cwd() == scope_lock.command_cwd()
        assert executor._scope_cwd() == a.resolve().parent
