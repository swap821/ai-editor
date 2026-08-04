# SUBSYSTEM_REGISTRY

## Backend Subsystems

| Name | Path | Maturity | Owner | Notes |
|------|------|----------|-------|-------|
| API main | `aios/api/main.py` | stable | core | middleware + route inclusion |
| DI deps | `aios/api/deps.py` | stable | core | test-overridable providers |
| Config | `aios/config.py` | stable | core | env single source of truth |
| Auth routes | `aios/api/routes/auth.py` | stable | auth | sessions, tokens |
| Action routes | `aios/api/routes/actions.py` | stable | executor | approval + execute + rollback |
| Council routes | `aios/api/routes/council.py` | stable | council | deliberation + verdicts |
| Security gateway | `aios/security/gateway.py` | stable | security | GREEN/YELLOW/RED classifier |
| Scope lock | `aios/security/scope_lock.py` | stable | security | frozen core |
| Secret scanner | `aios/security/secret_scanner.py` | stable | security | frozen core |
| Audit logger | `aios/security/audit_logger.py` | stable | security | frozen core |
| Injection shield | `aios/security/injection_shield.py` | stable | security | frozen core |
| Core router | `aios/core/router.py` | stable | core | multi-provider LLM routing |
| Memory engine | `aios/memory/` | stable | memory | product memory |
| Agent runtime | `aios/agents/` | stable | agents | agent execution |

## Frontend Subsystems

| Name | Path | Maturity | Notes |
|------|------|----------|-------|
| GAGOS app | `frontend/src/superbrain/SuperbrainApp.jsx` | stable | canonical UI; lazy-mounted from `frontend/src/main.jsx`. Lives **inside** the ported tree below — see the ownership note under Cross-Cutting Concerns |
| Workbench chrome | `frontend/src/workbench/` | stable | product-safe |
| Superbrain (ported) | `frontend/src/superbrain/` | stable | lab-synced; do not edit |
| Styles/tokens | `frontend/src/styles/` | stable | palette canon |

## Cross-Cutting Concerns

- CORS/origin handling, session binding and API token enforcement now live in
  `aios/interfaces/http/edge_security.py` (organ 6, `EdgeTrustAuthority`).
  The Slice 1 convergence target recorded here previously — "move these out of
  `aios/api/main.py`" — is **done**; this line was stale from 2026-07-18 until
  2026-08-04.
- **Open ownership conflict:** the canonical app shell
  `frontend/src/superbrain/SuperbrainApp.jsx` sits inside the lab-synced
  `frontend/src/superbrain/` tree that this registry marks *do not edit*, while
  product-authored code under `frontend/src/workbench/` imports into it. Edits
  to the shell can be overwritten by the next lab port. Not yet resolved.
