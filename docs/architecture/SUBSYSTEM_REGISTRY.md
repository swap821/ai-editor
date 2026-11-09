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
| Core router | `aios/core/router.py` | stable | core | multi-provider LLM routing; `PROVIDERS` is the one registry of brains every layer derives from |
| Memory engine | `aios/memory/` | stable | memory | product memory |
| Agent runtime | `aios/agents/` | stable | agents | agent execution |
| Worker swarm (ant colony) | `aios/agents/swarm.py`, `aios/application/workers/swarm_foundry.py` | stable | agents | since 2026-11-09 every caste leg is a worker the Worker Foundry admits (emergency stop at each admission, lifecycle on the cortex bus); worker legs run side by side on a cloud or plan brain (`AIOS_SWARM_CLOUD_CONCURRENCY`) and one at a time on the local one. Asked for per turn (the face's SWARM button). The role pass is still refused |
| Consistency register | `.aios/state/CONSISTENCY_REGISTER.json`, `scripts/consistency_audit.py` | stable | core | every fact two systems share, its source and the guard that fails when its places disagree; the doc is `docs/architecture/CONSISTENCY_REGISTER.md` |

## Frontend Subsystems

| Name | Path | Maturity | Notes |
|------|------|----------|-------|
| GAGOS app | `frontend/src/superbrain/SuperbrainApp.jsx` | stable | canonical UI; lazy-mounted from `frontend/src/main.jsx`. Lives **inside** the ported tree below — see the ownership note under Cross-Cutting Concerns |
| Workbench chrome | `frontend/src/workbench/` | stable | product-safe |
| Superbrain (ported) | `frontend/src/superbrain/` | stable | lab-synced; do not edit |
| Styles/tokens | `frontend/src/styles/` | stable | palette canon |

Two stores share the name `activeCastes` and are different things: `superbrain/lib/mirrorStore.ts` derives it from the Worker Foundry's worker lifecycle on the cortex bus, and `superbrain/lib/swarmHUDStore.ts` from the swarm's per-turn `caste_start`/`caste_end` stream frames. Since 2026-11-09 the swarm's legs are Foundry workers too, so a swarm turn may now reach both; whether it does, and under which names, is to be observed on the first live swarm turn.

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
