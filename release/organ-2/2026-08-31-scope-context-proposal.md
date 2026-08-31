# §VIII proposal — per-task `ScopeContext` (inventory item 3)

**Status: PROPOSAL. Not applied. Requires operator authorization.**

This document is a *proposal*, not an authorization. It deliberately does not
live in `release/section-viii/`, because that directory is what
`scripts/check_frozen_core.py` reads to let a frozen-path edit through CI. A
proposal that authorized itself would be ceremony in name only.

---

## Observe

`aios/security/scope_lock.py` holds one process-global, mutable list of scope
roots behind an `RLock`:

```python
self._scope_roots: list[Path] = [Path(p).resolve() for p in initial]   # :175

def set_scope_roots(self, roots):                                      # :177
    with self._lock:
        self._scope_roots.clear()
        self._scope_roots.extend(resolved)
```

Every containment decision in the system reads that one list:
`is_path_in_scope` (:217), `command_stays_in_scope` (:265), and `command_cwd`
(:192) — the last of which is the single source for the directory a sandboxed
command runs in, and therefore for the executor's bind mounts.

There is no per-call scope parameter anywhere in `gateway.classify()`,
`command_stays_in_scope()`, or `Executor._scope_cwd()`. All three read the
global.

## Analyse

### The race the catalog describes cannot happen today

Measured, not assumed:

```
grep -rn "set_scope_roots(" aios/ tools/ scripts/ --include=*.py
  | grep -v aios/security/scope_lock.py
  -> no matches
```

**No production code path mutates the scope roots.** They are set once from
config at import and never re-declared. Every caller of `set_scope_roots` in the
repository is a test. So the concurrency hazard — "task A's mutation is visible
to task B mid-flight" — has no live trigger, and this is a *latent* defect
rather than an open hole.

That is a downgrade of the catalog's framing, and it should be recorded as one
rather than quietly inherited.

### It is nevertheless real, and the evidence is the test suite

Because the state is global, every test that needs a different scope must save
and restore it by hand. There are at least nine such sites, and two were written
today while closing other items:

```
tests/test_api.py:1431,2132,2162        tests/test_agents_pkg_gaps.py:131
tests/test_approval_resume_*.py:141,55  tests/e2e/test_yellow_approval_*.py:175
```

A test that forgets the restore silently redirects every later test's containment
check at a temp directory. That is precisely the failure mode a per-task context
removes, and the manual save/restore discipline is the smell that says so.

### It blocks the next milestone

M2 requires concurrent lanes and, eventually, multi-project autonomy. Both need
one task's declared workspace to be invisible to another's checks. Item 4
(per-workspace autonomy, applied 2026-08-31) derives its workspace id from the
*active* scope roots — correct today precisely because there is exactly one
active set per process, and not correct the moment two lanes run at once.

## Why this is not applied

`AGENTS.md` §VIII: `aios/security/{gateway,scope_lock,secret_scanner,audit_logger,injection_shield}.py`
is FROZEN. Applying a change is RED.

The threading this item requires crosses two of those files:

| Hop | File | Frozen |
| --- | --- | --- |
| `gateway.classify(command, scope=...)` | `aios/security/gateway.py` | **yes** |
| `command_stays_in_scope(..., scope=...)` | `aios/security/scope_lock.py` | **yes** |
| `Executor._scope_cwd(scope=...)` | `aios/core/executor.py` | no |

Two of three hops are frozen, so there is no honest way to deliver item 3 as a
non-frozen change.

### The workaround that was considered and rejected

A `contextvars`-based override in a non-frozen module, which non-frozen callers
consult first and fall back to the global. Rejected: `gateway.classify` would go
on reading the global, so the same question — "what is in scope?" — would have
two answers that can disagree. That is the exact shape behind two containment
escapes already found in this repo, and `tests/adversarial/test_control_consistency.py`
exists because differential testing caught two more that ~450 payload attacks
missed. A second derivation here would be worse than the defect it patches.

## Propose

1. Add a frozen `ScopeContext` value object: an immutable tuple of resolved
   roots plus a stable `workspace_id`.
2. Give `is_path_in_scope`, `command_stays_in_scope`, and `command_cwd` an
   optional `scope: ScopeContext | None = None` parameter. `None` keeps today's
   behaviour exactly — read the process default — so no existing caller changes
   meaning.
3. Thread the same optional parameter through `gateway.classify(command, scope=...)`
   and `Executor._scope_cwd(scope=...)`.
4. Hold the process default in a `contextvars.ContextVar` seeded from config, so
   a task can bind its own scope for the duration of its work without mutating
   anything another task can observe.
5. Retire `set_scope_roots` in favour of a context manager. It has no production
   caller, so this is a test-only migration.
6. Derive `AutonomyLedger.workspace_id()` from the active `ScopeContext` rather
   than the global, closing the item-4 caveat noted above.

**Invariant that must hold:** with no `scope` argument anywhere, behaviour is
byte-identical to today. The parameter adds a capability; it removes no check.

## Test

* Two concurrent tasks with different bound scopes: neither observes the other's
  roots, asserted by running them in real threads rather than by inspecting state.
* Differential test in the spirit of `test_control_consistency.py`: for a matrix
  of paths and commands, `gateway.classify` and `command_stays_in_scope` must
  agree on containment under the same `ScopeContext` — a bound context must never
  make one layer say in-scope while the other says out.
* Every existing containment test passes unchanged with no `scope` argument.
* `spine_mutation_probe.py --check` still fails when the fail-closed behaviour is
  broken in memory.
* The executor's bind-mount set, derived from `command_cwd`, is unchanged for the
  default context — the containment fix applied earlier this session must not
  regress.

## Verify

Merge-gated by `scripts/check_frozen_core.py`, which will fail this change until
a `release/section-viii/` record naming both frozen files is added in the same
diff. That gate went in today; this proposal is the first change it would block,
which is the system working rather than an obstacle to route around.

## Human review

Open questions for the operator, which are the reason this is a proposal:

1. **Is item 3 wanted now?** It is latent, not live — no production caller
   mutates scope. It could reasonably wait until the first concurrent lane
   actually exists, so the design is driven by a real second consumer rather
   than an imagined one.
2. **Two frozen files in one §VIII action, or two?** `scope_lock.py` carries the
   substance; `gateway.py` only forwards a parameter. Splitting them makes each
   diff smaller to review; bundling them keeps the system consistent at every
   commit, since a forwarded parameter with nothing to forward to is dead code.
3. **Should `set_scope_roots` be removed or kept as a deprecated shim?** Removal
   touches nine test sites; a shim leaves a global mutator alive next to the
   context that replaced it.

No part of this is applied. `aios/security/` is untouched by the commit that
adds this document.
