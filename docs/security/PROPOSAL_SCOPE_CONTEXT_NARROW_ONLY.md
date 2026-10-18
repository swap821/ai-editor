# Proposal (§VIII): a bound scope may only narrow

> **APPLIED 2026-10-18 — design B (workspace-as-scope), with three hardenings the
> proposal did not have:** the admissible staging roots are pinned inside the
> scope lock, not passed by the caller; an empty scope refuses every command;
> junctions are refused like symlinks. Record:
> `release/section-viii/2026-10-18-scope-b-and-clerical-egress.md`. The text below
> is the proposal as written on 2026-10-12.

*Status: PROPOSED 2026-10-12, not applied. `aios/security/scope_lock.py` is
frozen core, so only the operator applies a change to it.*

## The fact

`scope_context(roots)` binds a per-task scope (a contextvar), and
`ScopeLockAuthority.get_scope_roots` then returns **the bound roots instead of
the process roots**:

```python
active = _ACTIVE_SCOPE.get()
if active is not None:
    return active.roots          # replaces SCOPE_ROOTS; does not intersect
```

So binding a root outside `SCOPE_ROOTS` **widens** containment for that task.
Today nothing outside `aios/security` binds `scope_context`, so nothing is
widened yet. But the natural next step is to bind each mission's staged
workspace, which lives under `data/`. That would widen it, because the
default `SCOPE_ROOTS` are `training_ground` and `lab`.

## The two designs

**A. Narrow-only (recommended).** The effective scope is the bound roots that
lie within the process roots: `bound ∩ SCOPE_ROOTS`. A bound root outside every
process root contributes nothing.
- To let missions act in staging, the operator adds the staging root to
  `AIOS_SCOPE_ROOTS`, explicitly, by configuration.
- Then each mission binds its own lease and is confined to it, a strict
  narrowing.
- This is the same shape as the one-law decision for cloud egress (2026-10-11):
  the ceiling is constitutional, and the runtime can only narrow inside it.

**B. Workspace-as-scope.** A bound root outside `SCOPE_ROOTS` is accepted when
it is a workspace minted by `StagedWorkspaceAuthority`, proven by its lease.
- Missions work in staging with no configuration change.
- The cost: the frozen spine must trust and verify the workspace authority's
  leases, so a widening path into the containment core exists by design.
- A forged or misplaced lease becomes a containment question.

## The change for A

```python
# ScopeLockAuthority.get_scope_roots
active = _ACTIVE_SCOPE.get()
if active is not None:
    with self._lock:
        ceiling = tuple(self._scope_roots)
    return tuple(r for r in active.roots if any(_is_within(r, c) for c in ceiling))
```

`_is_within` must canonicalise both sides, as the existing containment checks
already do.

**Tests to land with it:**
- A bound root inside a process root confines the task to it.
- A bound root outside every process root yields an empty scope, so every
  check refuses.
- Binding never changes what another task sees.
- On exit, the process scope is restored, including after an exception.

## Decision needed

A or B. With A, decide whether to add the staging root to `AIOS_SCOPE_ROOTS`
now or when the first mission needs to run commands in its workspace.
Maintenance repairs do not need either today: the executor's registered
operation canonicalises paths inside the staged workspace itself.
