# CURRENT_RUNTIME_MAP — Verified Baseline

**Captured:** 2026-07-12  
**Method:** direct code inspection + gate runs  

> **Currency banner (2026-08-04).** The measurements below are a dated
> Slice 0 baseline and are **not** re-verified at tip; they are kept
> verbatim per this repo's append-only evidence convention. Two known
> corrections since capture:
>
> 1. **App shell path was wrong.** The table said
>    `frontend/src/SuperbrainApp.jsx`; no such file has existed. The real
>    shell is `frontend/src/superbrain/SuperbrainApp.jsx`, lazy-mounted
>    from `frontend/src/main.jsx:17`. Corrected in the table below.
> 2. **Coverage numbers are stale.** "92% backend / ~39-46% frontend" was
>    true on 2026-07-12 and has not been re-measured here. Do not cite
>    these figures as current; read the CI run instead.
>
> Machine-readable organ status is `.aios/state/ORGAN_GREEN_LEDGER.json`,
> never this file.

## Backend Runtime

| Layer | Entry Point | Key Responsibility |
|-------|-------------|-------------------|
| HTTP server | `aios/__main__.py` | parses env, calls `uvicorn.run` |
| FastAPI app | `aios/api/main.py` | app factory, middleware, route inclusion |
| DI providers | `aios/api/deps.py` | singletons injected via `Depends` |
| Config | `aios/config.py` | single source of env-driven config |
| Security classifier | `aios/security/gateway.py` | GREEN/YELLOW/RED zone decisions |
| Routes | `aios/api/routes/*.py` | HTTP surface for auth, actions, council, memory, etc. |
| Core systems | `aios/core/` | router, registry, execution |
| Memory engine | `aios/memory/` | product memory subsystem |
| Agents | `aios/agents/` | agent runtime |
| Security spine | `aios/security/` | frozen core; RED to modify |

## Frontend Runtime

| Layer | Location | Responsibility |
|-------|----------|----------------|
| Entry | `frontend/index.html` + `main.jsx` | boot GAGOS |
| App shell | `frontend/src/superbrain/SuperbrainApp.jsx` | top-level GAGOS chrome (corrected 2026-08-04, see banner) |
| Product superbrain | `frontend/src/superbrain/` | **ported from lab; do not hand-edit** |
| Chrome | `frontend/src/workbench/GagosChrome.{jsx,css}` | product-safe chrome |
| Design tokens | `frontend/src/styles/tokens.css` | canonical palette |
| Config | `frontend/src/config.js` | runtime config |

## Data Flow

1. Browser loads `/` → GAGOS initializes WebSocket/SSE to backend.
2. Backend `bind_request_context` reads `session_id` cookie or body fallback.
3. `require_api_token` checks loopback / token presence / proxy headers.
4. Routes validate with Pydantic models, call services injected via `deps`.
5. Services may consult `security/gateway.py` for YELLOW/RED classification.
6. Audit logger writes decisions; memory engine records experiences.

## Verified Baseline (Slice 0)

- Backend pytest: **passing**, 92% coverage.
- Frontend typecheck: **passing**.
- Frontend lint: **passing** (124 warning budget).
- Frontend tests: **102 files, 584 tests passing**.
- Frontend build: **passing**.
- CI workflow: `ci.yml` enforces backend 85% coverage + frontend gates.

## Known Skews

- Local Python runtime may be 3.14; CI pins 3.12.
- Frontend coverage is ~39-46% — well below backend; profile work should prioritize it.
- Body-session fallback exists in `bind_request_context`; Slice 1 will restrict it.
