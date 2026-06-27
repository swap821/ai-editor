# Foundation Lock

The existing security gateway, executor, verifier, approvals, audit ledger, and self-apply engine are foundation modules.
Council Runtime v0.1 wraps them. It does not rewrite them.

## Protected Modules
- `aios/security/*`
- `aios/core/executor.py`
- `aios/core/approvals.py`
- `aios/core/verifier.py`
- `aios/core/self_apply.py`

Any change to these files requires explicit human approval and a written reason.

## Phase 0 Rule

Do not refactor the foundation while building Council Runtime v0.1.
