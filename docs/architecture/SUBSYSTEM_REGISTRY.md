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
| GAGOS app | `frontend/src/SuperbrainApp.jsx` | stable | canonical UI |
| Workbench chrome | `frontend/src/workbench/` | stable | product-safe |
| Superbrain (ported) | `frontend/src/superbrain/` | stable | lab-synced; do not edit |
| Styles/tokens | `frontend/src/styles/` | stable | palette canon |

## Cross-Cutting Concerns

- CORS/origin handling: currently in `aios/api/main.py`.
- Session binding: currently in `aios/api/main.py`.
- API token enforcement: currently in `aios/api/main.py`.
- **Convergence target:** move these to `aios/interfaces/http/edge_security.py` in Slice 1.
