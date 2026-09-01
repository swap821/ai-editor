# §VIII authorization — type-safety corrections to the frozen spine

**Authorized by the operator on 2026-09-01: "fix those 11 and gate mypy at zero".**

## Frozen paths changed under this authorization

- `aios/security/gateway.py`
- `aios/security/audit_logger.py`
- `aios/security/injection_shield.py`

## Observe

The first run of the new mypy gate (Ultra-plan Phase 8 / inventory item 86)
reported 11 errors across the security-critical subset. Six were inside the
frozen spine.

## Analyse — every one was read, none were silenced

| Site | Finding | Verdict |
| --- | --- | --- |
| `gateway.py:402,573` | `scope: object` passed where `ScopeContext \| None` expected | My own shortcut from the item-3 §VIII change: I typed the forwarded parameter `object` to avoid an import. The checker was right. |
| `audit_logger.py:353,665,785` | `int(cur.lastrowid)` where `lastrowid` is `int \| None` | Real gap. `Cursor.lastrowid` is None when the last statement was not an INSERT. All three sites follow an INSERT, so it is set — but nothing said so, and nothing checked it. |
| `injection_shield.py:77,91` | `"object" has no attribute "encode"` | The embedder was annotated `object`, which asserts it has NO attributes — so the module's own two `.encode(...)` calls were type errors, and the annotation verified nothing while looking like a type. |

None of the six was a live defect. The two live defects the same run found were
**outside** the frozen core and are fixed in the same PR:
`core/executor.py`'s Windows timeout-kill crash, and two unresolvable FastAPI
route annotations.

## Propose → what was applied

1. **`gateway.py`** — `scope` typed `Optional[ScopeContext]` on both `classify`
   entry points; `ScopeContext` imported alongside the existing
   `command_stays_in_scope` import. Pure annotation change.
2. **`audit_logger.py`** — `lastrowid` bound to a local and checked explicitly:

   ```python
   row_id = cur.lastrowid
   if row_id is None:      # pragma: no cover - INSERT always sets it
       raise RuntimeError("audit key INSERT returned no rowid")
   ```

   An `assert` was written first and **rejected**: `-O` strips asserts, so the
   invariant would vanish in exactly the deployment where it is least
   observable — and bandit flagged all three as B101, taking that gate from 141
   findings to 144. An explicit raise cannot be optimised away, and the bandit
   count returned to 141 with the budget unchanged.
3. **`injection_shield.py`** — embedder annotated `Any` with a comment. A
   `Protocol` was written first and **rejected**: the real `EmbeddingModel` did
   not match it structurally, so it turned 2 errors into 4. A Protocol the
   production implementation fails is worse than an honest `Any`.

### Behaviour

No behavioural change except one deliberate tightening: three impossible-in-
practice `None` rowids now raise `RuntimeError` instead of `TypeError`. Both
were already failures; the new one names the cause.

## Verify

| Check | Result |
| --- | --- |
| `scripts/check_mypy.py` | 0 errors across the checked paths |
| `scripts/check_bandit.py` | 141 findings — unchanged, budget accurate |
| `scripts/spine_mutation_probe.py --check` | **6/6 mutations caught** — the spine's fail-closed behaviour is intact |
| `tests/adversarial/` (full) | 486 passed |
| audit-integrity, audit-key-trust, gateway-bypass, security, executor | 301 passed, 1 skipped |

The spine mutation probe matters most here: it deliberately breaks the frozen
spine's fail-closed behaviour in memory and fails if anything survives. A typing
change that had quietly softened a guard would show up there, not in a unit test.

## Deploy

Merged via PR with the operator as the merging human. This document is the
authorization; the human merge is the authority.
