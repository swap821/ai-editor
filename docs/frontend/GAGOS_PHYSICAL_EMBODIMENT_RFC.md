# GAGOS Physical Embodiment RFC

Status: proposed architecture for the physical-embodiment phase  
Baseline ref: `origin/master` at `ba5d433a4f074cbfab1c83b1740c4dbcd72139ee` (`#363`)  
Owner: Codex builder worktree `codex/frontend-physical-embodiment`

## Decision summary

GAGOS should keep one semantic nervous system and add one physical projection
layer above it. The physical layer will be a bounded, ref-driven scene made of
five systems: cortex field, spinal conductor, temporary branch pool, memory /
cerebellar field, and sovereign membrane. Existing `cognitionBus`, mirror
snapshot/replay admission, `tabStore`, `organismLifecycle`, `bodyPosture`, and
approval APIs remain the sources of truth. The renderer may interpolate a
measured state, but it may not manufacture a new lifecycle or authority state.

The first implementation slice must reconcile the missing lab source before
editing managed anatomy. The accepted product files under
`frontend/src/superbrain/` are governed by `frontend/superbrain-source.json`;
the clean `origin/master` worktree contains the manifest but not the ignored
`GAG demo/gag-orchestrator/src` source. `npm run port:check` therefore fails
closed. No generated product file will be hand-edited to bypass that boundary.

## 1. Current physical scene graph

The current root is `SuperbrainApp.jsx`:

```text
SuperbrainApp
├─ BootSequence
├─ .lm-scene
│  └─ WorkspaceCanvas
│     ├─ QualityTierProvider
│     └─ Canvas
│        ├─ background + fog
│        ├─ TierGovernor / PerfProbe / DPR relief
│        ├─ CortexEngine
│        │  ├─ points-mode camera + OrbitControls + OrganismFraming
│        │  │  or mesh-mode CameraDrift
│        │  ├─ optional KnowledgeHorizon
│        │  ├─ CosmicBackground
│        │  ├─ CommandNerve3D in points mode
│        │  ├─ CognitiveGrasp and MemoryGalaxy
│        │  ├─ lights
│        │  ├─ Float
│        │  │  ├─ BrainModel / GLB or BrainPointField
│        │  │  └─ AccretionCore / MemoryParticles
│        │  ├─ PointerBrainClone in non-low mesh mode
│        │  ├─ NervousSystem in mesh mode
│        │  ├─ BodySpeech in points mode
│        │  └─ PostFX / one EffectComposer
│        ├─ SuperbrainReactiveEffects
│        │  ├─ cloud-route lightning
│        │  ├─ verification aurora
│        │  ├─ spine flash bead
│        │  ├─ caste orbit motes
│        │  └─ stigmergy trail/scar arcs
│        └─ product children / materialized work ports
├─ main: GagosChrome
│  ├─ conversation and voice
│  ├─ approval and sovereignty controls
│  ├─ Beginner / Expert-Mirror mode
│  └─ workbench panels
└─ LivingWorkspaceShell
   └─ backend-backed Expert/Mirror surfaces
```

The official runtime substrate is points mode. `?being=mesh` is retained as an
internal escape hatch. The scene still imports the large
`SuperbrainScene.LEGACY.tsx` module for `BrainModel`, `PointerBrainClone`,
camera helpers, shared uniforms, material factories, and constants. That file
is an important ownership and migration seam, not evidence that the product
has two runtime organisms.

## 2. Current semantic-state sources

| Source | Measured responsibility | Physical consumers |
| --- | --- | --- |
| `aiosAdapter.ts` | SSE turn, approval, route, verification, voice and backend errors | `cognitionBus`, chrome, posture and effects |
| `aiosMirror.ts` + `mirrorStore.ts` | authenticated snapshot/replay/live continuity and stale/unavailable state | mirror shell and product status |
| `cognitionBus.ts` | admitted transient cognition signals; not authority | CortexEngine and bounded reactions |
| `tabStore.ts` + `livingOrchestrator.ts` | input, workspace, approval and retracting surfaces | `BrainModel`, `MaterializationLayer`, conductor |
| `organismLifecycle.ts` | pure phase, posture, body role, conductor order and invariant violations | physical posture and workspace ownership |
| `organismPhaseBus.ts` / `conversationPhaseBus.ts` | latest derived phase, including pure-chat priority | scene frame loop and posture tint |
| `bodyPosture.ts` | single posture palette, flow and tint mapping | shared shader uniforms and conductor |
| `turnMetabolism.ts` | measured turn phase, breath gain, root excitation and tint | CortexEngine frame loop |
| `anatomicalConductor.ts` / `anatomicalRootSystem.ts` | vertebra seats, roots, waiting/active/held/reabsorbing overlays | `AnatomicalConductorOverlay` and materialized surfaces |
| `organMaterialState.ts` | presentation-only material state for active, waiting, verified, scarred and reabsorbing surfaces | materialized work surfaces |
| `swarmHUDStore.ts`, `verifyAuroraBridge`, `spineFlashBridge` | existing event-specific projections | current reactive effects |

The #363 merge now contains the handoff's product-owned semantic seams:
`livingMirror/being/semanticKernel.ts`, `presentationFromStores.ts`,
`semanticEffects.ts`, `coherenceSemantics.ts`, `motionSemantics.ts`, plus the
related receipt, approval, workspace-visibility, and renderer-fallback
boundaries. These are the canonical presentation inputs for this phase. The
physical implementation must extend them and the existing R3F seam, not
create duplicate kernels or rename them to fit an older branch snapshot.

## 3. Current anatomical ownership

Managed anatomy is the product mirror described by `frontend/superbrain-source.json`:

- managed: `frontend/src/superbrain/components/**`, `core/**`, and `lib/**`
- authoritative authoring source: `GAG demo/gag-orchestrator/src/**`
- product-only: `SuperbrainApp.jsx`, `GagosChrome.jsx`,
  `SuperbrainReactiveEffects.jsx`, `livingMirror/**`, and product CSS/config
- protected: backend security spine, generated assets and palette/texture canon

The clean worktree intentionally has no lab source. The manifest names
`components/QualityTierProvider.tsx`, so the port guard reports a missing lab
source and refuses to proceed. A source-reconciliation step is required before
managed anatomy changes. It must be reversible, preserve the manifest, and be
verified with `test:port` and `port:check`.

## 4. Current expensive render paths

The baseline exposes several cost centers:

- `BrainPointField`: up to 200,000 cortex points plus 56,000 fused spine
  points at high tier; 60,000 + 18,000 at medium; 40,000 + 11,000 at low.
- `AccretionCore/CoreGeometry.ts`: an 820-particle point field with custom
  shader animation.
- `MemoryGalaxy.tsx`: one bounded 128-star buffer, populated from known trails.
- `NodeLattice.tsx`: a capped 160-real-node graph using an instanced node mesh
  and merged tube geometry, mounted in points mode.
- `SuperbrainScene.LEGACY.tsx` and `CortexEngine.tsx`: multiple continuous
  `useFrame` loops for posture, breathing, camera, pointer attention, arrival,
  thought-wave scheduling, and DOM anchor projection.
- `PostFX.tsx`: one composer with AgX grading, bloom, vignette, noise and
  chromatic aberration; high tier enables 4x composer multisampling.
- `MaterializedTab.tsx` and `AnatomicalConductorOverlay.tsx`: per-surface tube
  geometry for umbilical/conductor paths and live DOM/3D workspace anchoring.
- `SuperbrainReactiveEffects.jsx`: bounded event-state records feed transient
  `<Line>` and mesh projections, while the continuous `useFrame` path mutates
  refs and pooled geometry. It no longer calls React setters from the frame
  loop, but it still mixes semantic worker effects, route lightning, aurora,
  spine flash and trail projections; it remains the clearest first candidate
  for consolidation behind one physical snapshot and pool budget.
- build/runtime payload: production output contains a 6.91 MB TypeScript worker,
  4.38 MB Monaco vendor chunk, 744 KB Three vendor chunk, 408 KB Drei/
  postprocessing vendor chunk, and a 306 KB `WorkspaceCanvas` chunk.

## 5. Current permanent vs transient scene entities

Permanent or long-lived entities are the loaded brain GLB, the fused point
field, shared scene uniforms, background/fog, lights, post-processing, the
quality governor, the conductor/spine geometry, and bounded memory/trail
buffers. Materialized work surfaces are long-lived only while their `tabStore`
record is live; their DOM content remains the legibility authority.

Transient entities are thought waves (three pending slots), arrival/awakening
envelopes, approval hold interpolation, verification aurora, spine flash,
cloud-route arcs, active caste motes, reabsorption particles, and retracting
workspaces. The current reactive effect maps do not expose one unified hard
pool or one scene-object budget. Stigmergy trails are rendered from the current
known-trail collection and need an explicit display cap in the physical layer.

## 6. What already satisfies this phase

The current product is stronger than a blank redesign in several important
ways:

- one root combines the being, conversation and Expert/Mirror shell;
- the official points body fuses cortex and spine rather than drawing a detached
  decorative spine;
- lifecycle derivation already distinguishes intake, materializing, working,
  conducting, approval hold, repair, completion settle and reabsorption;
- conductor tests cover empty, active, waiting, held and retracting seats;
- materialized surfaces use real tab/workspace records and preserve DOM text,
  selection and approval controls;
- posture color and flow are centralized through `bodyPosture` and shared
  uniforms;
- reduced-motion support is present in scene loops, point fields, fallback and
  materialized surfaces;
- quality tiers and DPR relief are explicit, measured by a canvas-side probe,
  and do not silently change the operator-selected structural tier;
- WebGL failure is contained with a truthful accessible fallback that preserves
  conversation and workspace availability;
- the browser baseline shows offline/setup-unavailable language rather than a
  fabricated healthy state;
- frontend contracts already test verified/unverified, stale, approval,
  reabsorption, renderer fallback and bounded node/trail structures.

## 7. Where embodiment is currently simulated by effects

The current body still relies on several effects that are not yet one physical
grammar:

1. Provider-colored lightning is a route flash, not a bounded branch that
   originates at an admitted worker, stops at a membrane, returns evidence and
   dissolves.
2. Caste orbit motes remain the legacy marker layer. The product-owned slice
   now augments semantic worker slots with bounded branch lines, but the
   renderer does not yet have a fully instanced branch material/pool system or
   a runtime resource diagnostic.
3. Verification is expressed through a transient green aurora bridge. It is
   useful feedback, but it is not yet the conductor's secondary verification
   field or a durable distinction between verified, unverified and failed
   material.
4. Memory trails and scars are floating arcs/boxes around the cortex. The
   product-owned slice now adds a bounded static cue for recalled, promoted and
   reflex layers, but it does not yet distinguish every persistence depth or
   provide a loaded-scene resource diagnostic.
5. Workspace materialization has real anchors and DOM content, and the
   product-owned `physicalMaterialization.ts` now projects canonical surface
   continuity into the conductor seat markers. The scene still mixes old
   mesh/point paths and managed overlay components rather than one fully pooled
   conductor-to-surface lifecycle.
6. `SuperbrainReactiveEffects` now keeps the physical branch/conductor/memory
   frame path ref-driven and bounded; the remaining legacy route, aurora,
   spine-flash and trail effects still need a unified runtime resource budget.
7. The current mesh/points split and the `SuperbrainScene.LEGACY` ownership seam
   make it difficult to prove one physical scene graph across quality tiers.

## 8. Proposed physical architecture

### 8.1 One pure physical snapshot

The product-owned `derivePhysicalSnapshot` seam now exists adjacent to the
semantic kernel; a managed-source version remains disallowed until the lab
source is reconciled and the port gate is green. It consumes the existing
presentation projection and returns:

- body phase/posture and coherence (`fresh`, `stale`, `degraded`, `offline`);
- cortex attention/convergence values;
- conductor seats and selected seat;
- bounded branch records with lifecycle and evidence posture;
- workspace anchors and connection posture;
- memory/reflex presentation records only when persistence is measured;
- membrane state (`clear`, `held`, `refused`, `stopped`);
- renderer and quality status.

The separate product-owned `physicalMaterialization.ts` projection consumes
canonical tab/conductor records for bounded seat continuity, focus, anchors and
reabsorption posture. It never owns lifecycle, DOM mounting, approval, or
execution.

This is a projection, not a new event bus, semantic kernel or authority
mechanism. It must be pure and fixture-testable.

### 8.2 Five physical systems

1. **CortexField**: shared point/GLB substrate and a small number of shader
   uniforms for rest, attention, understanding, planning, verification,
   learning and reflex. It must not animate council disagreement unless a real
   council signal is admitted.
2. **SpinalConductor**: one stable spine/root coordinate system. Seat state is
   `empty`, `waiting`, `active`, `held`, `reabsorbing`, `verified`, `stale` or
   `failed` as presentation overlays over existing records; no backend states
   are added.
3. **TemporaryBranchPool**: fixed-cap instanced branch/bud geometry. A branch
   follows `requested → admitted → active → awaiting capability → returned →
   dissolved`, or `failed/killed → retracting`; no historical event becomes a
   permanent mesh.
4. **MemoryCerebellarField**: bounded traces whose depth is derived from
   measured memory layer. Recall may reconnect a trace; only verified promotion
   can settle it; reflex visuals require real no-model-call/reflex evidence.
5. **SovereignMembrane**: a visual boundary around a held/refused/stopped
   conduction path. Approval and stop stay in the existing authority surfaces;
   the membrane cannot authorize anything.

### 8.3 Frame-loop rule

React owns semantic snapshots and DOM. R3F frame loops own mutable refs,
uniforms, pooled transforms and time interpolation. No `setState` from a
`useFrame` path. Transient records are admitted/retired at event boundaries;
the frame loop only advances them and writes instance buffers.

### 8.4 Workspace rule

Keep `MaterializedTab` and other readable work content in DOM. The 3D layer
provides the origin anchor, nerve/root connection, membrane, focus transition
and reabsorption posture. Arrival of an approval, refusal, stop, error or
verification result updates the DOM immediately; physical easing may catch up
after truth is visible.

## 9. Proposed shader and material architecture

Use at most three major families:

- **organism**: shared cortex/point/GLB material inputs for intelligence,
  attention, coherence and posture;
- **conductor**: shared spine, roots and temporary branches with state-driven
  flow, hold cutoff and return/reabsorption cues;
- **membrane/evidence**: restrained warm human-control surfaces and precise
  verification/receipt accents, mostly DOM for text.

Reuse geometries and materials. Prefer instancing and buffer attributes for
branches, pulses and memory traces. Centralize semantic colors in existing
posture/tokens sources; provider names must not become Guided-mode color
semantics. No new rainbow telemetry, gradient text, generic glowing sphere or
literal brain anatomy.

## 10. Proposed animation/control architecture

The state transition is event-driven and interruptible. Each transition has a
semantic timestamp, a target posture and a maximum visual duration. The visual
system may settle early when truth changes and never delays approval, failure,
verification, stop, result or focus.

- reading/approval: stable camera, local emphasis, no travel across text;
- system transition: short ease-out, bounded materialization;
- emergency stop: immediate conduction halt and high-priority DOM announcement;
- reduced motion: state changes, opacity, local highlights and static branch
  shapes; no travel-heavy motion, parallax, orbiting or large scaling.

## 11. Proposed quality degradation

The quality tier changes physical fidelity, never truth:

| Tier | 3D body | transient anatomy | post FX | fallback |
| --- | --- | --- | --- | --- |
| High | full point field / shared shader | up to 8 bounded branches, memory traces and conductor pulses | full approved chain, 4x composer MSAA | not used |
| Medium | reduced point field, same identity and spine | up to 4 branches, fewer secondary traces | bloom/grade without optional extras | not used |
| Low | compact point field or static body posture | static branch/seat indicators, no travel-heavy effects | minimal grade, no expensive optional layers | available |
| Operational fallback | no WebGL | DOM state, conversation, approval, stop and receipts | none | authoritative control plane |

The existing measured point counts are ceilings for migration, not a target to
increase. The final caps must be derived from profiling and kept in one budget
module.

## 12. Proposed performance budgets

These are acceptance targets, not baseline claims:

- high normal idle/working: p95 frame time ≤20 ms where hardware supports it;
- low tier: p95 frame time ≤33 ms and stable 30+ FPS;
- no monotonic scene-object, listener or transient-pool growth after warm-up;
- DOM typing, focus, approval, stop and result receipt remain responsive while
  the GPU is overloaded;
- LCP ≤2.5 s, INP ≤200 ms, CLS ≤0.1 at p75 where field measurement is
  available;
- 8-worker stress, rapid create/dissolve, stop-while-active and 20–30 minute
  soak must report frame-time distribution and pool/object trends.

Every optimization report must contain before measurement, change, after
measurement and the tier/viewport used. A screenshot is not an FPS claim.

## 13. Migration plan and gates

0. **Baseline**: this RFC and `GAGOS_PHYSICAL_BASELINE.md`; reconcile managed
   source; capture scene and runtime evidence. No anatomy rewrite before this
   gate.
1. **Body architecture**: pure physical snapshot, five-system scene contract,
   deterministic state fixtures and shared budgets. Semantic and authority
   tests unchanged.
2. **Cortex/coherence**: rest, listening, understanding, planning, stale,
   degraded and stopped postures. No worker/workspace rewrite.
3. **Spinal conductor**: seat focus, waiting, active, held, conduction,
   verification and reabsorption overlays.
4. **Temporary branches**: replace/augment motes with a fixed-cap pooled
   lifecycle; prove 8 workers and rapid dissolution.
5. **Workspace materialization**: preserve DOM editor/approval/accessibility;
   unify nerve/root anchors and focus/reabsorption.
6. **Sovereign membrane**: make hold/refusal/stop visually legible without
   changing approval or emergency-stop authority.
7. **Verification/recovery**: pass, fail, rollback, unverified completion and
   reabsorption; no unverified visual may settle as trusted memory.
8. **Memory/reflex**: only measured memory and reflex records receive durable
   physical treatment.
9. **Cinematic polish**: camera, lighting, materials and choreography after
   semantic and resource gates are green.
10. **Hardening**: profiles, pooling, instancing, asset/DPR changes backed by
    before/after data.
11. **Accessibility/responsive**: 320×568, 375×812, 768×1024, 1024×768,
    1440×900; keyboard, focus, reduced motion, screen reader and renderer loss.
12. **Human validation**: use the existing protocol with at least three
    non-builders; do not fabricate evidence.

At every stable checkpoint run focused tests, the constrained frontend suite,
typecheck, lint, build, CSS/texture canon, protected-path checks, diff checks,
responsive/reduced-motion checks and renderer-loss checks where applicable.

## 14. Explicit non-goals

- no second semantic kernel or event bus;
- no frontend authority, approval inference or backend contract changes;
- no generated-file bypass or security-spine edits;
- no literal human brain, humanoid face, generic orb or dashboard-with-Three.js;
- no model/provider/worker IDs in Guided mode;
- no 3D code glyphs replacing DOM editor content;
- no animation delay of truth;
- no WebGPU requirement;
- no particle growth with history and no optimization without measurement;
- no merge to `master` without explicit operator instruction.

## 15. Files likely to change

Initial source-reconciliation and physical projection work is expected in:

- authoritative lab anatomy sources corresponding to
  `frontend/src/superbrain/core/**`, `components/canvas/**` and `lib/**`;
- `frontend/src/superbrain/SuperbrainApp.jsx` only for product composition;
- `frontend/src/workbench/SuperbrainReactiveEffects.jsx` as the first product
  effect adapter to retire or narrow;
- product-owned pure projections under
  `frontend/src/livingMirror/being/physicalSnapshot.ts` and
  `physicalMaterialization.ts`, plus the test/dev-only physical state gallery;
- managed-source physical projection/budget modules only after source
  reconciliation;
- focused tests for physical snapshots, branch pools, budgets and lifecycle;
- `docs/frontend/GAGOS_PHYSICAL_BASELINE.md` and the later implementation
  report.

The following remain product truth owners and must not be replaced by visual
code: `aiosAdapter`, mirror admission, approval APIs, `tabStore`, backend
security, and DOM work/receipt surfaces.

## 16. Risks

| Risk | Guard |
| --- | --- |
| Managed lab source is absent | Reconcile before touching managed anatomy; keep `port:check` fail-closed |
| Physical snapshot becomes a second semantic kernel | Purely derive from existing stores; no new backend state |
| Pool identity leaks worker/provider details into Guided | Expert-only evidence mapping and plain Guided copy |
| Renderer cost starves controls | DOM control plane, measured tier budgets, DPR relief and operational fallback |
| Animation upgrades truth | Terminal events set DOM state first; every visual target is interruptible |
| Branch/memory history leaks GPU resources | fixed caps, instancing, disposal tests and soak diagnostics |
| Existing canon is accidentally changed | CSS/texture guards and protected-path review at each phase |
| Visual improvement is mistaken for evidence | deterministic state gallery plus measured runtime and human validation |
