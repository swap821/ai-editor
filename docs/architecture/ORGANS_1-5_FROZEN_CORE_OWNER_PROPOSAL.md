# Organs 1-5: frozen security-spine owner classes — DEPLOYED

**Status: Observe → Analyse → Propose → Test → Verify → Human Review →
Approve → Deploy complete (2026-07-31).** Operator gave §VIII Approve + Deploy
for additive Decision A owner classes under
`aios/security/{gateway,scope_lock,secret_scanner,audit_logger,injection_shield}.py`.
Existing module-level functions and `VectorInjectionShield` callers are
unchanged (aliases / wrappers only). Frozen spine remains forbidden from
claiming **green** until a later controlled release; class attestation now
applies to organs 1–5 like every other organ.

## Why these 5 and not the other 49

Decision A (docs/architecture/GAGOS_54_ORGANS.md, 2026-07-27) requires every
organ's `authority_owner` to be a real class defined inside that
organ's own `production_entrypoints`. Organs 6-54 already satisfied this.
Organs 1-5 required the same additive rename/alias pattern inside the
FROZEN security spine (`aios/security/{gateway,scope_lock,secret_scanner,
audit_logger,injection_shield}.py`). That edit is §VIII-gated (Tier T4 =
RED for the product agent); this document records the operator Approve +
Deploy that authorized the coding-agent apply on 2026-07-31. Green claims
for organs 1-5 remain forbidden until a later controlled release.

## What already exists (Observe)

All five modules are genuinely real, heavily tested, and already called
from dozens of production sites across the codebase (`aios/api/main.py`,
`aios/api/action_guard.py`, `aios/policy/kernel.py`,
`aios/application/capabilities/authority.py`, and many more — confirmed by
grep, not assumed). None of them currently define a class matching the
ledger's expected name; each is primarily a set of module-level functions
plus a few narrow data-carrying classes (results/enums), not one owning
class.

| Organ | Expected class | Real module | Real entrypoint functions already in production use |
|---|---|---|---|
| 1 | `SecurityGatewayAuthority` | `aios/security/gateway.py` | `classify()`, `validate_command()`, `set_injection_shield()`, `reset_sensitive_actions()`, `RateLimiter` |
| 2 | `ScopeLockAuthority` | `aios/security/scope_lock.py` | `is_path_in_scope()`, `command_stays_in_scope()`, `set_scope_roots()`, `get_scope_roots()` |
| 3 | `SecretScannerAuthority` | `aios/security/secret_scanner.py` | `scan_and_redact()` |
| 4 | `AuditLoggerAuthority` | `aios/security/audit_logger.py` | `log_action()`, `verify_chain()`, `rotate_audit_key()`, `get_anchor()`, `list_recent_entries()`, `retroactively_sign_unsinged_entries()`, `get_active_public_key()` |
| 5 | `InjectionShieldAuthority` | `aios/security/injection_shield.py` | `class VectorInjectionShield` (already a class — see below) |

## Analyse: what "owning the mechanism, not a pass-through" means for each

The established pattern across organs 6-54 (see `EmergencyStopHardWiringAuthority`
in `aios/application/capabilities/authority.py` for the fullest example) is:
rename the real class/consolidate the real functions into a class matching
the ledger's name, keep a backward-compat alias for every existing caller,
and — where a real decision is currently duplicated or scattered across
call sites — consolidate it into one method so the class owns something
beyond the label. Applied here:

- **Organ 1 (`SecurityGatewayAuthority`)**: wrap `classify()`,
  `validate_command()`, `set_injection_shield()`/`reset_sensitive_actions()`,
  and `RateLimiter` as methods/attributes of one class. Real consolidation
  opportunity: `classify()`'s `injection_shield` parameter and the module
  global `_injection_shield` set via `set_injection_shield()` are two ways
  to supply the same dependency — the class could own this as a single
  constructor-injected attribute instead of a parameter-or-global split,
  removing an ambiguity rather than just relabeling it.
- **Organ 2 (`ScopeLockAuthority`)**: wrap `is_path_in_scope()`,
  `command_stays_in_scope()`, and the `set_scope_roots()`/`get_scope_roots()`
  pair (currently module-global state) as instance state, so scope roots
  become an explicit constructor argument instead of implicit global
  mutation — the same class of improvement organ 26 made for emergency-stop
  checking.
- **Organ 3 (`SecretScannerAuthority`)**: wrap `scan_and_redact()`. This one
  is the closest to a pure rename with no consolidation opportunity found —
  the module is already a single cohesive scanning function; forcing extra
  "ownership" onto it would risk inventing complexity `EmergencyStopHardWiringAuthority`-style
  consolidation doesn't actually need here.
- **Organ 4 (`AuditLoggerAuthority`)**: wrap `log_action()`, `verify_chain()`,
  `rotate_audit_key()`, `get_anchor()`, `list_recent_entries()`, and
  `retroactively_sign_unsinged_entries()` — the class becomes the one
  object that owns "did this happen, and can I prove the record wasn't
  altered", mirroring organ 42's `RecoveryResumptionAuthority` shape
  (write side + verify side on one object) closely enough to reuse that
  template directly.
- **Organ 5 (`InjectionShieldAuthority`)**: `VectorInjectionShield` already
  exists as a real class and is already the thing `set_injection_shield()`
  installs — this is a pure rename
  (`InjectionShieldAuthority = VectorInjectionShield`, or rename the class
  itself with `VectorInjectionShield` kept as the alias), no new
  consolidation needed. This is the smallest, lowest-risk of the five.

## Propose: the concrete diff shape (NOT applied)

For each module, the proposed change is additive-then-aliased, matching
the pattern already proven safe across 40 other organs this session:

```python
# aios/security/gateway.py (illustrative — NOT applied)
class SecurityGatewayAuthority:
    """Own the fail-closed command classification and rate-limiting boundary."""

    def __init__(self, injection_shield: object | None = None) -> None:
        self._injection_shield = injection_shield

    def classify(self, command: str) -> ClassificationResult:
        return classify(command, injection_shield=self._injection_shield)

    def validate_command(self, *args, **kwargs):
        return validate_command(*args, **kwargs)

    # ... RateLimiter, reset_sensitive_actions, etc.


# Existing module-level functions (classify, validate_command, ...) are
# left exactly as they are — every current caller keeps working unchanged.
```

The equivalent shape applies to organs 2-4; organ 5 is simpler still
(a rename, not a wrapper).

Estimated blast radius if applied: touches 5 files with dozens of existing
callers each. The rename-with-alias pattern has now been proven safe across
40 organs and a full green test suite in this exact session, which is the
strongest evidence available that the *mechanism* is low-risk — but these
five files are FROZEN regardless of mechanism risk, by policy, not by
technical difficulty. That policy is the actual gate here, not engineering
judgment about the diff.

## Deploy record (2026-07-31)

Operator Approve + Deploy applied additive owner classes (and
`InjectionShieldAuthority` rename with `VectorInjectionShield` alias).
`enforce_owner_attestation` now class-checks organs 1–5; green remains
forbidden for the frozen spine. Remaining work for organs 1–5 is Phase 4–5
attestation (live evidence / SHA), not Decision A.
