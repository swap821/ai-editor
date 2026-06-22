# GAGOS State Proof Harness — Design Spec (2026-06-23)

## Context

The 34-agent poster-fidelity audit is 100% complete; the living-being organism
implements all 7 poster states (arrival → rest/intake → awakening → materialization
→ orchestration → working → reabsorption), live-verified across the session. A
conformance audit against the "Convert 2D Point-Field Vision into Live 3D" spec
confirmed the states exist — but surfaced ONE real residual: **provability.**

The spec demands "browser proof for 10 states" + regression tests. Today that can't
be produced reliably:
- `__materializeTab` collapses to ONE surface unless each call passes a distinct
  `content.filepath` (showContentSurface dedups by filepath) — so multi-tab
  orchestration (State 5) isn't drivable in one obvious call.
- There are no dev hooks to put the body into `streaming` / `error` / `completion`
  (States 6/7/8) deterministically.
- Live capture is flaky: a backgrounded tab pauses R3F's RAF (animations freeze at
  init) and dev-materialized surfaces can transiently tear down.

The states are built; their **provability is the gap.** This harness closes it.

## Goal

A deterministic, persistent dev/test harness that drives the organism into each of
the spec's canonical states for (a) one capturable 10-state proof sweep and (b)
regression coverage. **Pure dev/test tooling — it composes EXISTING hooks and
invents ZERO product behavior.** No product render path changes.

## Non-goals

- No product behavior change (input purity, mobile layout = separate, operator's call).
- No new visual mechanics — the states already exist; we only DRIVE them.
- Not shipped in production bundles beyond the existing dev-hook gating
  (`process.env.NODE_ENV !== 'production'`).

## Architecture

Three units + a runbook, following the project's pure-contract discipline.

### 1. `frontend/src/superbrain/lib/demoStates.ts` (pure)

A pure descriptor of each canonical state — what store/phase setup it needs — with
no DOM/side effects. Testable in isolation.

```ts
export type DemoStateName =
  | 'rest' | 'intake' | 'awakening' | 'materialize'
  | 'orchestrate3' | 'streaming' | 'error' | 'completion' | 'reabsorbing';

export interface DemoSurfaceSpec { filepath: string; language: string; code: string; seatIndex: number; }
export interface DemoStatePlan {
  /** content surfaces to seat (distinct filepaths → no dedup collapse). */
  surfaces: DemoSurfaceSpec[];
  /** organism/metabolism phase to drive, or null to leave at rest. */
  phase: 'thinking' | 'working' | 'error' | 'complete' | null;
  /** reabsorb the focused surface (State 9). */
  reabsorbFocused?: boolean;
}
export function deriveDemoStatePlan(name: DemoStateName): DemoStatePlan;
```

- `orchestrate3` → 3 surfaces, distinct filepaths, seats `[0,2,4]`, no phase.
- `streaming`/`error`/`completion` → 1 surface + the matching phase.
- `reabsorbing` → 1 surface + `reabsorbFocused: true`.
- `rest` → no surfaces, no phase.

### 2. `window.__demo(name)` dev hook

Added in `MaterializationLayer` (where the other `__materialize*` hooks live;
dev-gated). Reads `deriveDemoStatePlan(name)` and applies it by composing the
EXISTING primitives: `showContentSurface(...)` per surface (distinct filepath →
appends), a metabolism/lifecycle phase setter for `phase`, and
`beginRetractingMaterializedTab` for reabsorb. Clears prior demo surfaces first so
each call is a clean, deterministic, persistent state.

Returns the resulting orchestration summary `{ tabs, workspaceCount, phase }` so a
caller (or the live probe) can assert it landed.

### 3. Tests `frontend/src/superbrain/lib/demoStates.test.ts`

Assert each `deriveDemoStatePlan` is well-formed:
- `orchestrate3` → 3 surfaces, all distinct filepaths, ascending seats.
- `streaming`/`error`/`completion` → exactly the matching phase.
- `reabsorbing` → `reabsorbFocused` true.
- `rest` → no surfaces, null phase.
- every name is total (no undefined plan).

(Renderer/contract behavior for each state is already covered by existing
tabStore / livingOrchestrator / organismLifecycle tests; this adds the
driver-descriptor coverage.)

### 4. `.aios/state/PROOF_SWEEP.md` runbook

The ordered `__demo(name)` calls for the 10-state sweep + what each should show,
so the proof is reproducible. Then capture the sweep live on `:5173` via
kimi-webbridge (tab foreground to avoid the RAF freeze).

## Data flow

`__demo(name)` → `deriveDemoStatePlan(name)` (pure) → compose existing tabStore /
phase hooks → store updates → existing render path draws the state → live capture +
`window.__getLivingOrchestration()` / `__getOrganismLifecycle()` confirm it.

## Error handling

- Unknown name → no-op + a console warning (dev only); `deriveDemoStatePlan` throws
  on an unknown name so the test catches typos.
- Production: the `__demo` hook is not installed (same dev gate as the siblings).

## Testing

`npm run typecheck` + `npm test` (focused demoStates + full suite ≥245) +
`npm run build`; then the live sweep on `:5173` with the tab foreground, capturing
each state. Not "done" until the sweep artifact exists.

## Success definition

One command sets the organism to any canonical state, persistently; the 10-state
proof sweep is capturable and reproducible; each driver-descriptor is unit-tested.
The spec's "browser proof + regression for 10 states" requirement is satisfiable.
