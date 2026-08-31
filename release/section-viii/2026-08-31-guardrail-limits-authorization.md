# §VIII authorization — guardrail constants behind the freeze (inventory item 5)

**Authorized by the operator in-session on 2026-08-31.**

## Frozen paths added/changed under this authorization

- `aios/security/limits.py` *(new file, inside the frozen prefix)*

Named verbatim because `scripts/check_frozen_core.py` requires it. A *new* file
under `aios/security/` is a §VIII event for the same reason an edit is: from the
moment it lands, its contents are part of the security spine and can only change
with ceremony. Creating one quietly would be a way to grow the spine without
anyone deciding to.

## Observe

Six constants decided how far the system may reach and how much it may do
unattended, and all six lived in `aios/config.py`, which is not frozen:

| Constant | What it governs |
| --- | --- |
| `SCOPE_ROOTS` | where the system may act at all |
| `EARNED_AUTONOMY_ENABLED` | whether it may act without asking |
| `EARNED_AUTONOMY_MIN_SUCCESSES` | how much verified evidence that takes |
| `ROUTER_CLOUD_TASKS` | what may leave the machine |
| `MAX_RED_ACTIONS_PER_SESSION` | how much destructive work one session may propose |
| `AUDIT_GENESIS_HASH` | the anchor the tamper-evident chain hangs from |

An agent with ordinary edit rights could widen its own sandbox, lower its own
evidence bar, or re-anchor the audit chain, with a human PR review as the only
backstop and no automated one.

## Analyse — and two places the catalogue was out of date

Item 5 also asked for the CORS/Bearer block in `aios/api/main.py` to move to
`aios/security/http_guard.py`. **That premise is stale.** The logic already left
`main.py`: `_validate_cors_origins` is now a one-line delegation to
`aios/interfaces/http/edge_security.py`, a cohesive module with a real authority
class. Relocating a well-factored 400-line security module purely to change its
directory would be churn with real regression risk and no security gain that
widening the frozen prefix would not also achieve. **Not done, deliberately** —
recorded as an open decision rather than silently dropped.

Item 5's other clause — "widen `frozen_subdirs`" — turned out to be the more
valuable half, and it is done, though not the way the wording suggested. There
were **three independent answers** to "is this path frozen?":

1. `aios/policy/constitution.py::FROZEN_PATH_PREFIXES` — used by
   `ConstitutionEnforcer._is_frozen` and by `scripts/check_frozen_core.py`
2. `aios/core/self_apply.py::classify_target(frozen_subdirs=("security",))` —
   used by the self-apply zone gate
3. AGENTS.md prose naming five files

(1) and (2) agreed only by coincidence of content. Widening one list would have
left the other behind — the exact shape behind two containment escapes already
found in this repo. `classify_target` now derives from `FROZEN_PATH_PREFIXES`, so
there is one derivation with three callers.

## Propose → applied

* `aios/security/limits.py` holds the definitions.
* `aios/config.py` re-exports every name, so **no caller changes** and
  `config.SCOPE_ROOTS` behaves exactly as before.
* `limits` imports nothing from `config` (config imports *it*), so its env
  helpers are local and `PROJECT_ROOT` is derived from its own location.

### The one real cost, pinned rather than trusted

That second derivation of `PROJECT_ROOT` is a consistency risk in miniature.
`test_project_root_agrees_between_the_two_derivations` asserts equality with
`config.PROJECT_ROOT`: path arithmetic that silently disagreed would root the
scope checks and the documented scope in different places, and a base/roots
mismatch has already been a containment escape here once.

### Guarding against a quiet reversal

`test_config_does_not_redefine_a_guardrail` parses `config.py`'s AST and requires
each name's right-hand side to be a `_limits.` attribute read. If someone
restores `SCOPE_ROOTS = _env_scope_roots(...)`, the values still match on a
default machine and every value-comparison test passes — while the definition has
moved back outside the freeze. Only a structural check catches that.

## Test / Verify

| Suite | Result |
| --- | --- |
| `tests/test_guardrail_limits.py` (new) | 19 passed |
| self_apply / config / router / autonomy / audit suites | 388 passed, 0 failed |
| Full backend suite + coverage gate | see the PR |

`classify_target` verified by behaviour: RED for `aios/security/gateway.py` and
for the newly added `aios/security/limits.py`; YELLOW for `aios/core/executor.py`,
`aios/config.py`, and `aios/security_notes.py` (no over-broad prefix match).

## Deploy

Merged via PR with the operator as the merging human. This document is the
authorization; the human merge is the authority.
