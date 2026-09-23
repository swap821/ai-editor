# GAGOS 2030 Renovation Baseline

**Date:** 2026-09-22  
**Baseline commit:** `00dbf6f38956935e0c168a14c77ce5f9ed1e32cc` (`master`)  
**Worktree:** `codex/frontend-2030-v1`  
**Scope:** frontend only; the dirty operator checkout and backend were not changed.

## Source and ownership inventory

- Product root: `frontend/src/superbrain/SuperbrainApp.jsx`.
- Product-safe shell: `SuperbrainApp.jsx`, `GagosChrome.jsx/.css`, `main.jsx`,
  `index.html`, `vite.config.js`, `styles/tokens.css`, and new product-owned
  modules.
- Lab/generated ownership: managed files under `frontend/src/superbrain/` must
  be changed only through the documented `npm run port` workflow. No generated
  or lab-owned source was changed for this baseline.
- Frozen security core: `aios/security/`; no frozen file was changed.
- Existing authority/evidence owners retained: `aiosAdapter`, `aiosMirror`,
  `mirrorStore`, `livingMirrorRegistry`, `cognitionBus`, `tabStore`, and the
  existing approval/emergency-stop paths.

## Current architecture observations

- `SuperbrainApp` composes one lazy `WorkspaceCanvas`, `GagosChrome`, and
  `LivingWorkspaceShell`.
- `CortexEngine` is the current frame-loop and cognition-to-body bridge.
- `anatomicalConductor` and `tabStore` already provide spinal seats and bounded
  materialization/reabsorption lifecycles.
- `mirrorStore` distinguishes offline/online/stale transport, unknown and
  unavailable projection, measured/stale observations, approval state, worker
  entities, and verification records.
- `livingMirrorRegistry` admits worker, route, memory, approval, governance,
  verification, and reflex-related backend events into the cognition bus; the
  renovation’s product-owned semantic adapter consumes admitted mirror/tab
  state for posture and leaves raw buses to evidence-specific projections.
- Current canvas inventory: 28 files using `useFrame`, 40 `useFrame` call sites,
  and 17 lazy-import references. This is an inventory signal, not a claim that
  every loop is expensive.
- Guided vocabulary inventory: 57 internal-term matches across the current
  Guided shell and mirror surfaces. This is the starting point for compression,
  not a blanket deletion list.

## Automated baseline gates

| Gate | Result |
| --- | --- |
| Frontend tests | **PASS** — 134 files, 769 tests, serial constrained mode; 249.48s |
| TypeScript | **PASS** — `npm run typecheck` |
| Production build | **PASS** — Vite 8.3.0; 4,286 modules transformed |
| Lint | **PASS** — 0 errors, 120 warnings under configured cap |
| Port safety tests | **PASS** — 5/5 |
| CSS canon | **PASS** — 12 renovatable files, 9 canon tokens |
| Texture/canon guard | **PASS** — no protected assets touched |
| Frozen-core guard | **PASS** — no `aios/security/` paths touched |
| Whitespace | **PASS** — `git diff --check` |

Known baseline warnings remain unchanged: Vite `__dirname` native-loader
deprecation, ineffective dynamic imports for two panels, and the existing 120
lint warnings. The isolated worktree required `npm ci`; dependencies are
ignored and are not part of the product diff.

## Browser baseline

Preview: `http://127.0.0.1:5177/`, local Vite server, backend not credited as
live evidence.

Observed at desktop browser capture:

- The 3D organism loads as the focal visual and remains available while DOM
  controls render.
- The opening is a conversation dock with voice, language, send, and starter
  paths; the visible mode label is still `Beginner`.
- The current opening copy is already plain-language and states that voice does
  not approve actions.
- Emergency Stop is visible and keyboard/ARIA discoverable.
- Connection state is shown as `Connecting to GAGOS…` / `GAGOS is offline` with
  truthful setup-unavailable copy; no operational success is inferred.
- The current visual reads as a living organism, but the task/progress/result
  hierarchy is spread across the dock, top controls, mirror notice, and canvas.
- No authenticated backend journey was attempted; no mutation or approval was
  invoked.

Existing responsive evidence in the repository covers 320×568 and 375×812
overflow and basic keyboard paths. The full 320×568, 375×812, 768×1024,
1024+, and 1440+ responsive matrix, reduced-motion capture, forced renderer
failure, and frame-time comparison remain renovation work.

## Event-to-visual inventory

| Truth source | Current projection | Renovation treatment |
| --- | --- | --- |
| `approval.required` / `human_required` | Approval hold and amber body reaction | Map to `awaiting-human`; retain server-owned decision |
| `approval.resolved` / `approval.decided` | Approval resolution cognition event | Distinguish allow/deny from execution/verification |
| `worker.requested` / `admitted` / `started` / `awaiting_capability` / terminal events | Registry announcements and worker entity state | Add bounded requested → active → held → returned → dissolved presentation |
| `route.selected` | Route cognition event and technical status surfaces | Present local/cloud only when materially relevant; retain Expert detail |
| `memory.recalled` / `trusted_workflow_*` / `memory.promoted` | Knowledge/body reactions and mirror announcements | Add recall/promotion/reflex signals without fabricating model work |
| `verify_result` and registered verification events | Verification records and outcome imprint | Keep finished separate from verified |
| `governance.emergency_stop.engaged` | Stop control and mirror announcement | Make stop posture dominant and action pulses frozen |
| mirror connection/projection state | Connection notice and stale styling | Feed stale/degraded presentation only; never infer freshness |
| `tabStore` lifecycle and focused seat | Materialization/reabsorption and workspace rail | Preserve evidence receipt while surfaces contract |

## Phase 0 limitations

- The live backend was not authenticated, so no connected operational state is
  claimed.
- The reference image `GAG demo/reference/demoplan.png` is visual guidance only;
  it is not a runtime state source.
- Screenshot/video capture is session evidence from the local browser harness;
  no private user content or backend payloads were persisted.
- Human validation, operator visual approval, actual WebGL context-loss recovery,
  and p75 field metrics remain unverified.

Phase 1 may begin only from this recorded baseline and must add semantic tests
before wiring new visual behavior.
