# GAGOS 10-State Proof Sweep — runbook

The `window.__demo(name)` harness drives the organism into each canonical poster
state deterministically + persistently (see `lib/demoStates.ts`). Use it to capture
the proof sweep and to reproduce any state for review.

## How to run (dev, `:5173`, tab foreground)

A hidden tab pauses R3F's RAF (animations freeze) — keep the tab foreground while
capturing. In the browser console:

```js
window.__demo('rest')          // 1. bare voyaging body at rest
window.__demo('intake')        // 2. attending to input (awakening conversation)
window.__demo('awakening')     // 3. cortex brightens (thinking → attentive)
window.__demo('materialize')   // 4. one surface born on a vertebra + cortex nerve
window.__demo('orchestrate3')  // 5. three surfaces seated on vertebrae (conducting)
window.__demo('streaming')     // 6. working: reply rise + cortex heat (cyan)
window.__demo('error')         // 7. error scar (error_repair, red restraint)
window.__demo('completion')    // 8. completion settle (green)
window.__demo('reabsorbing')   // 9. surface dissolves, energy up the spine
window.__demo('rest')          //    return to rest
```

Each call returns `{ name, surfaces, workspaceCount, conversation }` so you can
assert it landed. Read the live contracts to confirm:

```js
window.__getLivingOrchestration()   // workspaceCount, focusId, surfaces
window.__getOrganismLifecycle()     // derived phase
window.__getTurnMetabolism()        // tint (single-sourced from bodyPosture)
```

## State 10 — compact/mobile (NOT covered by this harness)

`deriveBrainPresenceLayout` is viewport-aware, but the narrow-viewport render is
unverified and can't be driven via `__demo` (it needs a real window resize, which
the kimi bridge can't do). Tracked as a separate residual; verify on a real narrow
window or a follow-up resize harness.

## Notes

- The harness composes EXISTING primitives only (`showContentSurface` with distinct
  filepaths, `setConversationPhase`, `beginRetractingMaterializedTab`). It invents
  no product behavior — it makes the already-built states reliably DRIVABLE.
- Multi-surface needs distinct `filepath`s (showContentSurface dedups by filepath);
  the harness handles this so `orchestrate3` reliably seats three.
- Dev-only: the hook is not installed in production bundles.
