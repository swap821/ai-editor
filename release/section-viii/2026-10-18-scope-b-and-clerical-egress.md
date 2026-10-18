# §VIII authorization: a bound scope only narrows, except into a staged workspace GAGOS minted

**Authorized by the operator in-session on 2026-10-18.**
- He chose **"B: workspace-as-scope"** for the scope proposal
  (`docs/security/PROPOSAL_SCOPE_CONTEXT_NARROW_ONLY.md`, merged as #494).
- He asked for the clerk egress proposal (`docs/security/PROPOSAL_CLERICAL_EGRESS_CLASS.md`,
  #486) to be applied.
- His first instruction was denied by the session's safety classifier ("Security
  Weaken"), and both edits were reverted untouched. He then chose "I'll allow it"
  and approved the frozen edits.

## Frozen paths changed under this authorization

- `aios/security/scope_lock.py`

They are named verbatim because `scripts/check_frozen_core.py` requires it.

## 1. Scope: narrow-only, plus admitted staged workspaces (B)

### Observe

`ScopeLockAuthority.get_scope_roots` returned a bound or explicit scope's roots
**instead of** the declared roots. So binding any directory widened containment
to it.

Nothing in production binds a scope today (measured: no `scope_context(` or
`ScopeContext(` outside `aios/security`), so the widening was latent. The
natural next step, binding each mission's staged workspace under `data/`, would
have widened it, because the declared roots are `training_ground` and `lab`.

### Change

**`get_scope_roots` filters a bound or explicit scope.** A root survives only if
it lies inside a declared root or inside an admitted staged workspace. If none
survives, the scope is empty.

**Admission** (`admit_staged_workspace`; module-level wrapper of the same name)
accepts only the shape the workspace authority mints:
- the staging root is one the scope lock **pinned at construction**:
  `DATA_DIR/staged_maintenance` and `EXECUTOR_WORKSPACE_ROOT`. It is not taken
  from the caller. If the caller named it, naming any directory would admit any
  32-hex child of it.
- the workspace is a real directory, not a symlink and not a Windows junction;
- it is a **direct** child of that staging root, never the root itself;
- its name is a 32-hex lease id, which is what `uuid4().hex` produces.

`retire_staged_workspace` withdraws an admission. Admissions live in memory.

**An empty scope runs no command.** `command_stays_in_scope` refuses when no
root is in force. Without this, a command with no path words (`pytest -q`)
passes every path check and runs in the fallback cwd: the empty scope would
contain nothing but execute anything. This was not in the proposal. It exists
only because B can now produce an empty scope.

**Non-frozen side, `aios/application/workspaces/staged.py` (organ 14):**
- `stage()` admits the workspace it mints, and retires it if staging fails;
- `load()` re-admits, because a restart forgets admissions;
- `cleanup()` retires before removing.

A manager over any other root (a test's tmp dir, the runtime proof's scratch)
admits nothing.

**Unchanged:** the unbound default; the process roots; every check with no
binding.

### Cost, stated as the proposal stated it

The spine now trusts the workspace authority's minting. A widening path into the
containment core exists by design: a process that can create a 32-hex directory
directly under a pinned staging root, and call `admit_staged_workspace`, can
make that directory bindable. It cannot make anything else bindable.

### Tests

`tests/test_scope_narrow_only.py` (new), 22 tests:
- the proposal's four tests;
- each admission refusal;
- the prefix-sibling and `..` escapes;
- the empty-scope command refusal through the frozen gateway;
- the production pin;
- the workspace authority's admit, re-admit and retire.

Mutation check on 2026-10-18: each guard was removed in turn and the suite was
re-run. **9/9 mutants were killed:** narrow-only filter, empty-scope refusal,
pinned root, direct child, lease name, is-dir, link check, retire, junction. The
link check is killed by the junction test on Windows and by the symlink test on
Linux CI.

`tests/test_scope_context.py`: its fixtures bound `tmp_path` directories outside
the declared roots, which is exactly the widening this removes. The fixture now
declares the tmp root, so each binding is a narrowing inside it. One assertion
that depended on the real default (`training_ground`) now uses the two
workspaces instead. Its other 11 tests are unchanged.

## 2. `clerical` cloud-egress class: withdrawn from this change

He also asked for the clerk egress proposal (#486) to be applied, and the first
push of this PR did apply it. CI's routing-reachability guard then failed
(`tests/test_fleet_routing_is_task_aware.py::TestEveryRouterTaskIsReachable`).
Every class the router accepts must be producible by some input, and must not
be normalised into another class. Nothing produces `clerical` until the
cloud-clerk escalation exists.

Exempting it would weaken a guard written on purpose ("a declared-but-unreachable
branch is not a feature"). So `aios/security/limits.py` is unchanged here, and
`clerical` ships together with the escalation that produces it, under its own
§VIII record.

## What still needs the operator

1. **Review and merge.** Frozen core: a human merges.
2. **Re-sign organs 1-5.** `scope_lock.py` is organ 2's entrypoint, so organ 2's
   evidence goes stale. Re-gathering it changes the spine evidence digest, and
   only his key can re-sign that, in a terminal no agent is attached to:

   ```
   AIOS_SPINE_RELEASE_KEY=<private-hex> python scripts/spine_release_attest.py sign --organs 1,2,3,4,5
   ```

   The attestation must name a commit reachable from master, so he signs after
   the merge, at master's tip.
