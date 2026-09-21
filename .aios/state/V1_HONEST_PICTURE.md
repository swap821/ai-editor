# GAGOS V1 Honest Picture

**Status:** Working V1 truth dossier  
**Date:** 2026-09-21  
**Authority:** current source tree and fresh verification output; dated evidence remains historical

## Product contract

GAGOS is a local-first, supervised, memory-driven AI operating system. The
3D living being is the identity and front door. The product must be easy for a
person who does not know AI, while remaining an honest mirror for an operator
who needs to inspect the system underneath.

The governing rule is:

> Hide complexity from the user's path; never hide the truth from the user.

V1 therefore has two views of one system:

- **Beginner:** plain language, guided invitations, optional voice, safe defaults,
  clear approvals, and calm recovery guidance.
- **Expert/Mirror:** the same real state with route, memory, provenance,
  verification, governance, runtime, audit, and unavailable evidence exposed.

Beginner is the default. Expert/Mirror is an explicit switch. Voice is a
conversation channel; explicit typed/UI approval remains the only authority for
risky actions.

## Backend: what is authoritative today

| Concern | Current authority | Truth boundary |
|---|---|---|
| Risk classification and execution scope | `aios/security/*`, policy kernel, action guard | deterministic, fail-closed; frozen security spine |
| Human-directed turns | `aios/application/turns/TurnCoordinator` and the live generation routes | one supervised turn path with streamed evidence |
| Memory ownership | `aios/application/memory/MemoryAuthority` | adapters route reads/writes; unverified records never become trusted by display |
| Model/provider choice | `aios/core/router.py` and `router_wiring.py` | local-first policy, cloud-task gate, cost/availability checks, durable route metadata |
| Approval | capability authority plus action broker | exact, single-use authority; UI reflects state but does not create it |
| Verification and promotion | evidence/verifier/promotion authorities | observed exit/evidence is stronger than model prose |
| Runtime portrait | `/api/v1/mirror/snapshot`, `/governance`, `/executor`, `/stream` | read model plus replayable Cortex journal |
| V1 readiness | `aios/application/governance/v1_declaration.py` and runtime proof artifacts | source presence is not runtime proof |

The backend already has the right architectural shape for an honest mirror. The
remaining V1 work is contract currency, newcomer translation, and fresh runtime
evidence—not a second cognitive or security authority.

## Frontend: current composition

The only product entry is `frontend/src/main.jsx` → `superbrain/SuperbrainApp`.
The app mounts the preserved 3D organism, `GagosChrome` for conversation and
approval, and `LivingWorkspaceShell` for mirror/workbench surfaces.

The data spine is:

```text
backend SSE / read models
        ↓
aiosAdapter + aiosMirror
        ↓
mirrorStore / cognitionBus / livingMirrorRegistry
        ↓
3D body + GagosChrome + workbench/mirror surfaces
```

The mirror client already handles snapshot recovery, replay gaps, stale state,
unsupported events, redaction, and bounded browser history. Unknown or
unavailable values must remain unknown or unavailable.

## Shipped versus planned

### Shipped and measurable

- Supervised typed directives over the real SSE generation path.
- Conversational voice endpoint with no tool authority.
- Human-required approval surface for writes, commands, and fetches.
- Route/model events and active-brain presentation.
- Mirror snapshot and journal stream with replay handling.
- Backend-backed workbench surfaces for missions, governance, memory, skills,
  workforce, maintenance, files, and runtime evidence.
- Local-first launcher/Compose path and backend readiness/bootstrap endpoints.
- Frontend test suite, typecheck, and production build currently pass at the
  verification baseline recorded for this task.

### Not yet proven as an external V1 experience

- A first-time nontechnical user's complete journey from opening the app to a
  useful, recoverable result.
- A clean separation between a beginner surface and the full Expert/Mirror
  workbench.
- Voice-inclusive onboarding and failure recovery across supported and
  unsupported browser environments.
- Clean-machine installer/pilot evidence independent of the operator's current
  development environment.
- Visual browser sign-off for the final 3D/body experience at the V1 boundary.

## Evidence vocabulary

User-facing surfaces must use these meanings consistently:

- **Measured:** directly observed from the current backend or verified artifact.
- **Derived:** computed from measured records; the derivation is explainable.
- **Stale:** a prior observation exists, but continuity or freshness is not proven.
- **Unavailable:** no trustworthy observation exists.
- **Blocked/refused:** policy deliberately prevented the action.
- **Pending approval:** the system has paused and requires explicit human action.
- **Verified:** an independent verifier/evidence path passed.

Missing data must never be rendered as healthy, local, approved, verified,
active, or complete.

## Release sequence

1. Prove the newcomer journey locally.
2. Run a trusted private local-installer pilot.
3. Complete fresh backend runtime evidence and clean-machine checks.
4. Obtain operator visual/browser sign-off.
5. Expand exposure only after the preceding gates remain green.

Hosted multi-tenant service, federation, billing, and public internet exposure
are outside this V1 implementation.

## Protected boundaries

- The frozen security spine stays unchanged.
- Generated `frontend/src/superbrain/` files are changed only through the lab
  and port process.
- The mirror, memory, approval, routing, and verifier authorities remain single
  sources of truth.
- Historical reports are not rewritten; current-facing docs receive explicit
  superseded/current-status language instead.

