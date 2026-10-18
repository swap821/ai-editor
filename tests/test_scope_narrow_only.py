"""A bound scope may only narrow, except into a staged workspace GAGOS minted.

§VIII, applied 2026-10-18 on the operator's decision "B: workspace-as-scope"
(docs/security/PROPOSAL_SCOPE_CONTEXT_NARROW_ONLY.md;
release/section-viii/2026-10-18-scope-b-and-clerical-egress.md).

Before: `get_scope_roots` returned a bound scope's roots INSTEAD of the declared
ones, so binding any directory widened containment to it. After: a bound or
explicit scope is filtered to roots inside a declared root or inside an
admitted staged workspace; nothing else survives, and an empty scope refuses
every path AND every command.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest

from aios.security import scope_lock
from aios.security.gateway import Zone, classify
from aios.security.scope_lock import ScopeContext, ScopeLockAuthority

LEASE = "0123456789abcdef0123456789abcdef"


@pytest.fixture()
def world(tmp_path: Path) -> dict[str, Path]:
    declared = tmp_path / "declared"
    outside = tmp_path / "outside"
    staging = tmp_path / "staging"
    for p in (declared, outside, staging):
        p.mkdir()
    (declared / "sub").mkdir()
    return {"declared": declared, "outside": outside, "staging": staging}


@pytest.fixture()
def authority(world: dict[str, Path]) -> ScopeLockAuthority:
    return ScopeLockAuthority([world["declared"]], staging_roots=[world["staging"]])


@pytest.fixture()
def singleton(
    authority: ScopeLockAuthority, monkeypatch: pytest.MonkeyPatch
) -> Iterator[ScopeLockAuthority]:
    """Swap the process authority so the frozen gateway sees the test world."""
    monkeypatch.setattr(scope_lock, "_SCOPE_LOCK", authority)
    yield authority


# --------------------------------------------------------------------------- #
# Narrow-only
# --------------------------------------------------------------------------- #
def test_a_binding_inside_the_declared_scope_confines_to_it(
    world: dict[str, Path], authority: ScopeLockAuthority
) -> None:
    sub = world["declared"] / "sub"
    scope = ScopeContext.of([sub])
    assert authority.get_scope_roots(scope) == (sub.resolve(),)
    assert authority.is_path_in_scope(str(sub / "x.py"), scope=scope).in_scope
    assert not authority.is_path_in_scope(
        str(world["declared"] / "x.py"), scope=scope
    ).in_scope


def test_a_binding_outside_every_root_widens_nothing(
    world: dict[str, Path], authority: ScopeLockAuthority
) -> None:
    """The fact the proposal measured: this used to return (outside,)."""
    scope = ScopeContext.of([world["outside"]])
    assert authority.get_scope_roots(scope) == ()
    assert not authority.is_path_in_scope(
        str(world["outside"] / "x.py"), scope=scope
    ).in_scope


def test_only_the_bindable_part_of_a_mixed_binding_survives(
    world: dict[str, Path], authority: ScopeLockAuthority
) -> None:
    scope = ScopeContext.of([world["outside"], world["declared"] / "sub"])
    assert authority.get_scope_roots(scope) == ((world["declared"] / "sub").resolve(),)


def test_an_empty_scope_runs_no_command_not_even_a_pathless_one(
    world: dict[str, Path], authority: ScopeLockAuthority
) -> None:
    """Without the empty-scope refusal, `pytest -q` has no path word to fail
    on and would run in the fallback cwd: containing nothing, executing
    anything."""
    scope = ScopeContext.of([world["outside"]])
    for command in ("pytest -q", "python -c pass", f"touch {world['outside']}/x"):
        result = authority.command_stays_in_scope(command, scope=scope)
        assert not result.in_scope, command
        assert result.reason


def test_the_gateway_refuses_under_an_empty_bound_scope(
    world: dict[str, Path], singleton: ScopeLockAuthority
) -> None:
    with scope_lock.scope_context([world["outside"]]):
        assert scope_lock.get_scope_roots() == ()
        assert classify("pytest -q").zone is Zone.RED
        assert classify(f"touch {world['outside']}/x.py").zone is Zone.RED


def test_the_unbound_default_is_unchanged(
    world: dict[str, Path], authority: ScopeLockAuthority
) -> None:
    assert authority.get_scope_roots() == (world["declared"].resolve(),)
    assert authority.command_stays_in_scope("pytest -q").in_scope


# --------------------------------------------------------------------------- #
# Workspace-as-scope (B)
# --------------------------------------------------------------------------- #
def test_an_admitted_workspace_is_bindable_and_confines(
    world: dict[str, Path], authority: ScopeLockAuthority
) -> None:
    ws = world["staging"] / LEASE
    ws.mkdir()
    sibling = world["staging"] / ("f" * 32)
    sibling.mkdir()
    authority.admit_staged_workspace(ws, staging_root=world["staging"])
    scope = ScopeContext.of([ws])
    assert authority.get_scope_roots(scope) == (ws.resolve(),)
    assert authority.is_path_in_scope(str(ws / "a.py"), scope=scope).in_scope
    assert not authority.is_path_in_scope(str(sibling / "a.py"), scope=scope).in_scope
    assert not authority.is_path_in_scope(
        str(world["declared"] / "a.py"), scope=scope
    ).in_scope


def test_admission_does_not_widen_the_unbound_default(
    world: dict[str, Path], authority: ScopeLockAuthority
) -> None:
    ws = world["staging"] / LEASE
    ws.mkdir()
    authority.admit_staged_workspace(ws, staging_root=world["staging"])
    assert authority.get_scope_roots() == (world["declared"].resolve(),)
    assert not authority.is_path_in_scope(str(ws / "a.py")).in_scope


def test_retiring_a_workspace_makes_its_binding_empty(
    world: dict[str, Path], authority: ScopeLockAuthority
) -> None:
    ws = world["staging"] / LEASE
    ws.mkdir()
    authority.admit_staged_workspace(ws, staging_root=world["staging"])
    authority.retire_staged_workspace(ws)
    assert authority.get_scope_roots(ScopeContext.of([ws])) == ()
    authority.retire_staged_workspace(ws)  # idempotent


def test_a_name_sharing_a_prefix_with_an_admitted_workspace_is_not_inside_it(
    world: dict[str, Path], authority: ScopeLockAuthority
) -> None:
    ws = world["staging"] / LEASE
    ws.mkdir()
    longer = world["staging"] / (LEASE + "0")
    longer.mkdir()
    authority.admit_staged_workspace(ws, staging_root=world["staging"])
    assert authority.get_scope_roots(ScopeContext.of([longer])) == ()


def test_dot_dot_out_of_an_admitted_workspace_is_dropped(
    world: dict[str, Path], authority: ScopeLockAuthority
) -> None:
    ws = world["staging"] / LEASE
    ws.mkdir()
    authority.admit_staged_workspace(ws, staging_root=world["staging"])
    escape = ScopeContext.of([ws / ".." / ".." / "outside"])
    assert authority.get_scope_roots(escape) == ()


@pytest.mark.parametrize(
    "case",
    ["unpinned_root", "not_hex", "grandchild", "the_root_itself", "missing", "a_file"],
)
def test_admission_refuses_what_the_authority_never_mints(
    world: dict[str, Path], authority: ScopeLockAuthority, case: str
) -> None:
    staging = world["staging"]
    root = staging
    if case == "unpinned_root":
        root = world["outside"]
        target = root / LEASE
        target.mkdir()
    elif case == "not_hex":
        target = staging / "not-a-lease"
        target.mkdir()
    elif case == "grandchild":
        (staging / LEASE).mkdir()
        target = staging / LEASE / ("a" * 32)
        target.mkdir()
    elif case == "the_root_itself":
        target = staging
    elif case == "missing":
        target = staging / LEASE
    else:
        target = staging / LEASE
        target.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        authority.admit_staged_workspace(target, staging_root=root)
    assert authority._admitted_workspaces == set()


def test_a_symlinked_workspace_is_refused(
    world: dict[str, Path], authority: ScopeLockAuthority
) -> None:
    """The link targets a lease-SHAPED sibling: a link pointing outside is
    already refused by the direct-child check, so only this case shows the
    link check itself biting."""
    sibling = world["staging"] / ("e" * 32)
    sibling.mkdir()
    link = world["staging"] / LEASE
    try:
        os.symlink(sibling, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this platform/account cannot create directory symlinks")
    with pytest.raises(ValueError):
        authority.admit_staged_workspace(link, staging_root=world["staging"])
    assert authority._admitted_workspaces == set()


@pytest.mark.skipif(
    os.name != "nt" or not hasattr(os.path, "isjunction"),
    reason="Windows junctions, Python >= 3.12",
)
def test_a_junctioned_workspace_is_refused(
    world: dict[str, Path], authority: ScopeLockAuthority
) -> None:
    """Junctions need no privilege on Windows, and is_symlink() misses them."""
    import subprocess

    sibling = world["staging"] / ("e" * 32)
    sibling.mkdir()
    link = world["staging"] / LEASE
    made = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(sibling)],
        capture_output=True,
        check=False,
    )
    if made.returncode != 0:
        pytest.skip("could not create a junction here")
    with pytest.raises(ValueError):
        authority.admit_staged_workspace(link, staging_root=world["staging"])
    assert authority._admitted_workspaces == set()


def test_the_production_authority_pins_only_the_two_staging_roots() -> None:
    from aios import config

    pinned = scope_lock._SCOPE_LOCK._staging_roots
    assert pinned == frozenset(
        os.path.realpath(str(p))
        for p in (
            config.DATA_DIR / "staged_maintenance",
            config.EXECUTOR_WORKSPACE_ROOT,
        )
    )


# --------------------------------------------------------------------------- #
# The workspace authority admits what it mints, and only that
# --------------------------------------------------------------------------- #
def test_staging_admits_reload_readmits_and_cleanup_retires(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from aios.application.workspaces.staged import StagedWorkspaceAuthority

    project = tmp_path / "project"
    project.mkdir()
    (project / "m.py").write_text("x = 1\n", encoding="utf-8")
    first = ScopeLockAuthority([world["declared"]], staging_roots=[world["staging"]])
    monkeypatch.setattr(scope_lock, "_SCOPE_LOCK", first)

    manager = StagedWorkspaceAuthority(world["staging"], enrolled_roots=(project,))
    lease = manager.stage("mission-1", project)
    ws = Path(lease.workspace_path)
    assert first.get_scope_roots(ScopeContext.of([ws])) == (ws.resolve(),)

    # A restart forgets admissions (they live in memory); reloading the lease
    # re-admits it.
    second = ScopeLockAuthority([world["declared"]], staging_roots=[world["staging"]])
    monkeypatch.setattr(scope_lock, "_SCOPE_LOCK", second)
    assert second.get_scope_roots(ScopeContext.of([ws])) == ()
    StagedWorkspaceAuthority(world["staging"], enrolled_roots=(project,)).load(
        lease.lease_id
    )
    assert second.get_scope_roots(ScopeContext.of([ws])) == (ws.resolve(),)

    manager.cleanup(lease)
    assert second.get_scope_roots(ScopeContext.of([ws])) == ()


def test_a_manager_over_an_unpinned_root_admits_nothing(
    world: dict[str, Path], singleton: ScopeLockAuthority, tmp_path: Path
) -> None:
    from aios.application.workspaces.staged import StagedWorkspaceAuthority

    project = tmp_path / "project"
    project.mkdir()
    manager = StagedWorkspaceAuthority(
        tmp_path / "elsewhere", enrolled_roots=(project,)
    )
    lease = manager.stage("mission-2", project)
    assert singleton._admitted_workspaces == set()
    assert singleton.get_scope_roots(ScopeContext.of([lease.workspace_path])) == ()
