# §VIII authorization — per-task `ScopeContext` (inventory item 3)

**Authorized by the operator in-session on 2026-08-31**, in answer to the three
open questions in `release/organ-2/2026-08-31-scope-context-proposal.md`.

## Frozen paths changed under this authorization

- `aios/security/scope_lock.py`
- `aios/security/gateway.py`

Both are named verbatim above because `scripts/check_frozen_core.py` requires it,
and that gate is what makes this change loud rather than quiet. This is the first
change it has blocked — which is the control working, not an obstacle routed
around.

## Observe

`ScopeLockAuthority` held one process-global mutable list of scope roots behind
an `RLock`. Every containment decision in the system — `is_path_in_scope`,
`command_stays_in_scope`, `command_cwd`, and through them `gateway.classify` and
`Executor._scope_cwd` — read that single list. No per-call scope existed
anywhere.

## Analyse

Severity was downgraded on measurement before any code was written:

```
grep -rn "set_scope_roots(" aios/ tools/ scripts/ | grep -v aios/security/scope_lock.py
  ->  no matches
```

No production path mutates the scope roots. The concurrency race had no live
trigger; this was **latent**, not an open hole. What was real: ~9 test sites must
save and restore global state by hand, and a forgotten restore silently redirects
every later containment check in the process.

It blocks M2 regardless — concurrent lanes and multi-project autonomy both
require one task's declared workspace to be invisible to another's checks.

## Propose → what was actually applied

The proposal sketched threading an explicit `scope` parameter through every
signature, and **rejected** a `contextvars` override on the grounds that
`gateway.classify` would go on reading the global, giving containment two answers
that can disagree.

That objection applied to an override living in a **non-frozen** module. With
§VIII authorization the override goes *inside* `get_scope_roots` itself — the one
place the question is answered — so every caller, including the frozen
`gateway.classify`, inherits it and **no second derivation exists**. The applied
design is therefore smaller and safer than the proposal:

1. `ScopeContext` — a frozen, pre-resolved tuple of roots plus a `workspace_id`.
2. `_ACTIVE_SCOPE`, a `ContextVar`, consulted by `get_scope_roots`.
3. Precedence: explicit `scope=` → task binding → process default.
4. `scope_context(roots)` context manager; `current_scope()` to hand the object
   across a boundary the binding does not cross.
5. Optional `scope=` on `is_path_in_scope`, `command_stays_in_scope`,
   `command_cwd`, `gateway.classify`, and `Executor._scope_cwd`.

`set_scope_roots` is unchanged, so all nine test sites keep working; the
test-only migration the proposal contemplated is not part of this change.

### The invariant

**With no `scope` argument and no binding, behaviour is byte-identical.** Pinned
by `test_with_no_scope_and_no_binding_nothing_changed`. This change adds a
capability; it removes no check and weakens no guardrail.

### One place a partial change would have been an escape

Inside `command_stays_in_scope`, the token base and the containment check must
come from the SAME scope:

```python
check = self.is_path_in_scope(token, base=self.command_cwd(scope), scope=scope)
```

Passing `scope` to only one of them would resolve a token against one workspace
and check it against another — the exact base/roots mismatch that once let
`training_ground/../X` classify YELLOW while landing outside every root.

## Known limitation, stated not discovered later

`contextvars` do not propagate into a bare `threading.Thread`. A thread spawned
inside a binding sees the process default, which may be **wider** — a fail-open
direction. This is why every check also accepts an explicit `scope=`, and why
`test_a_bare_thread_does_not_inherit_the_binding` asserts the limitation
directly: if Python ever changes it, that test fails and the guidance gets
revisited deliberately rather than the caveat quietly becoming false.

## Test / Verify

| Suite | Result |
| --- | --- |
| `tests/test_scope_context.py` (new) | 12 passed |
| `tests/test_security.py`, `test_executor.py`, adversarial `path_containment`, `control_consistency`, `sandbox_escape`, `gateway_bypass` | 350 passed, 0 failed |
| Full backend suite + coverage gate | see the PR |

`test_control_consistency.py` matters most here: it is the differential suite
that exists because two layers answering the same question differently produced
two containment escapes. It passes unchanged, and the new file adds a
scope-parameterised differential of its own — under a bound scope,
`command_stays_in_scope` and `gateway.classify` must never disagree.

## Deploy

Merged via PR with the operator as the merging human. This document is the
authorization; the human merge is the authority.
