# GAGOS Physical Embodiment Baseline

Baseline captured on 2026-09-23 from the isolated branch
`codex/frontend-physical-embodiment`.

## Scope and source truth

- Runtime ref: `origin/master` /
  `ba5d433a4f074cbfab1c83b1740c4dbcd72139ee` (`feat: GAGOS 2030 Living AI-OS frontend renovation (#363)`).
- The previously referenced local `master` was stale at `00dbf6f3`; the isolated
  branch was corrected to the current `origin/master` before measurement.
- The original checkout was dirty on an unrelated learning branch and was not
  used for edits or measurements.
- Current managed anatomy is under `frontend/src/superbrain/` and is governed by
  `frontend/superbrain-source.json`. The ignored lab source is absent in this
  clean worktree, so `npm run port:check` correctly refuses to claim a clean
  managed source state.

## Current implementation inventory

The live root is:

```text
SuperbrainApp
├─ WorkspaceCanvas / R3F Canvas
│  └─ CortexEngine
│     ├─ points-mode BrainPointField (official default)
│     ├─ fused spine/conductor and workspace materialization
│     ├─ accretion/memory particles
│     ├─ cognition, posture, metabolism and lifecycle frame loops
│     └─ post-processing
├─ SuperbrainReactiveEffects
├─ GagosChrome (DOM conversation, voice, approval and workbench)
└─ LivingWorkspaceShell (Expert/Mirror)
```

The actual semantic ownership is distributed across `cognitionBus`,
`aiosAdapter`, `aiosMirror`/`mirrorStore`, `tabStore`, `organismLifecycle`,
`bodyPosture`, `conversationPhaseBus`, `anatomicalConductor`,
`anatomicalRootSystem`, `organMaterialState`, the product-owned
`livingMirror/being/*` presentation kernel, and the existing approval/
renderer-fallback components. The #363 merge contains the semantic kernel,
store adapter, motion/coherence semantics, bounded worker-effect mapping,
receipts, and renderer-fallback boundary; the physical embodiment work must
extend those seams rather than recreate them.

## Measured gates on unchanged source

Commands were run from `frontend/` unless noted.

| Gate | Result | Evidence |
| --- | --- | --- |
| Serial frontend unit suite | PASS | 163 test files, 901 tests, exit 0; 281.94 s. Vitest reported 174.83 s in jsdom setup. |
| TypeScript | PASS | `npm run typecheck`, exit 0. |
| Production build | PASS | 4,311 modules transformed; Vite build exit 0 in 3.67 s. |
| Lint | PASS under configured cap | 0 errors / 120 warnings; `--max-warnings=124`. |
| Port unit tests | PASS | 5/5 `sync-superbrain` tests. |
| Port check | BLOCKED by expected missing source | `Lab source missing: components/QualityTierProvider.tsx; deletion requires explicit migration.` |
| CSS canon | PASS | 12 renovatable files clean against 9 canon tokens. |
| Texture/GLB canon | PASS | 2 changed paths checked; no protected assets touched. |
| Whitespace | PASS | `git diff --check`, exit 0. |

The port check is recorded as a blocker, not silently converted to green. The
clean lab-source reconciliation is a prerequisite for changing managed anatomy.

## Bundle and asset baseline

The production build emitted 70 files under `frontend/dist/assets`:

- JavaScript: 15,670,875 bytes raw;
- CSS: 286,913 bytes raw;
- fonts: 490,784 bytes raw (`.ttf` 140,956 + `.woff2` 349,828);
- all assets: 16,448,572 bytes raw;
- largest JS chunks: TypeScript worker 6,913,951 bytes; Monaco vendor
  4,383,254 bytes; CSS worker 1,074,885 bytes; Three vendor 743,936 bytes;
  HTML worker 739,943 bytes; Drei/postprocessing vendor 407,544 bytes;
  `WorkspaceCanvas` 305,819 bytes; `SuperbrainApp` 179,771 bytes;
- public visual assets: `brain.glb` 155,396 bytes,
  `textures/brain/diffuse.png` 1,890,195 bytes, and
  `textures/brain/normal.png` 2,351,205 bytes.

These are raw build/file sizes, not transfer or runtime memory claims.

## Scene and resource envelope visible in source

| Resource | Current ceiling or behavior | Evidence |
| --- | --- | --- |
| Cortex point field | high 200,000 points; medium 60,000; low 40,000 | `SuperbrainScene.LEGACY.tsx` / `BrainPointField` props |
| Fused spine point field | high 56,000; medium 18,000; low 11,000 | `BrainModel` props |
| Accretion particles | 820 | `core/AccretionCore/CoreGeometry.ts` |
| Memory galaxy | 128 stars | `components/canvas/MemoryGalaxy.tsx` |
| Knowledge/node lattice | max 160 real nodes; instanced nodes and merged tube geometry | `components/canvas/NodeLattice.tsx` |
| Thought-wave queue | max 3 pending wave origins | `CortexEngine.tsx` |
| Quality DPR | high 1–1.5, medium 1–1.25, low 1 | `lib/perfBudget.ts` |
| Post FX | one composer; high tier 4x multisampling | `components/canvas/PostFX.tsx` |
| Reactive lightnings | age out after 900 ms; no unified pool | `workbench/SuperbrainReactiveEffects.jsx` |
| Worker motes | one React record per active caste; animated through React state in `useFrame` | `SuperbrainReactiveEffects.jsx` |
| Memory/trail rendering | bounded by MemoryGalaxy to 128; reactive trail overlay has no local display cap | `MemoryGalaxy.tsx`, `SuperbrainReactiveEffects.jsx` |

The point counts and asset sizes are source envelopes. They are not a measured
scene-object count, GPU allocation, or FPS result.

The current #363 source contains 36 files with `useFrame`, 41 direct
`useFrame(...)` call sites, and 23 lazy-loading references. These are static
inventory counts, not runtime frame or bundle-performance measurements.

## Runtime browser observation

An unchanged Vite development server was run at
`http://127.0.0.1:5180/` and opened in the Codex in-app browser.

Observed at the available compact viewport (`384×800` screenshot):

- WebGL2 canvas rendered the official point-field organism and spine;
- boot sequence appeared before the organism settled;
- DOM conversation remained available above/alongside the canvas;
- Beginner mode was selected by default;
- the setup readout said `Setup status is unavailable` and explained that the
  local setup endpoint did not return a trustworthy status;
- the shell said `GAGOS is offline` / `Connecting to GAGOS… Checking the local
  operational picture.` rather than presenting healthy operational state;
- voice copy explicitly said voice is conversation and actions still need
  approval;
- the accessible tree exposed skip-to-chat, Beginner/Expert mode, composer,
  voice controls, emergency stop and three safe starter paths;
- the rendered canvas screenshot was captured in-session as ephemeral evidence;
  no binary screenshot is committed by this baseline because the browser tool
  does not return a stable repository path.

This is an offline/setup-unavailable observation. It is not evidence of an
authenticated live mirror, backend worker execution, approval replay,
verification, memory promotion or cloud routing.

## Current permanent and transient anatomy

Long-lived scene entities include the cached GLB, fused brain/spine point field,
shared uniforms, background/fog/lights, the PostFX composer, conductor roots,
materialized surfaces while their tab records are live, and bounded memory
buffers. Transient entities include arrival/awakening envelopes, cognition
bursts and thought waves, approval hold interpolation, aurora and spine flash,
cloud-route lightning, active caste motes, reabsorption particles and
retracting workspace surfaces.

The baseline does not yet provide one cross-system transient-pool diagnostic.
That is an implementation requirement, not a reason to claim boundedness.

## Baseline behavior by requirement

| Requirement | Baseline status | Boundary |
| --- | --- | --- |
| One being / multiple postures | Partial | lifecycle and posture plumbing exists; physical systems are still spread across legacy scene/effect paths |
| Cortex responds to semantic phase | Partial | shared uniforms and posture tint exist; topology/coherence is not yet one state-owned system |
| Spine conducts work | Partial | roots, seats and materialized anchors exist; conductor and workspace are not one pooled physical lifecycle |
| Temporary workers | Not yet embodied | current caste motes are bounded in practice by active records but are not branch lifecycle anatomy |
| Workspace grows from being | Partial | materialized surfaces and anchors exist; DOM remains the content authority |
| Sovereign membrane | Partial | approval hold and stop surfaces exist; the 3D boundary is still an effect/overlay projection |
| Verification/recovery/reabsorption | Partial | verified/scar/reabsorbing material states and bridges exist; no unified physical recovery path |
| Memory/reflex distinction | Partial | trail/skill data and completion reflex seams exist; durable physical layers are not yet mapped end-to-end |
| Reduced motion | Contract present | tests and branches exist; full state-gallery/browser evidence remains to be captured |
| Renderer loss | Contract present | fallback boundary is tested; real `WEBGL_lose_context` recovery is not measured here |
| Responsive/accessibility | Partial evidence | compact browser tree and 44px control contracts exist; full viewport matrix and screen-reader session remain open |
| Resource boundedness | Incomplete evidence | static caps exist; runtime object/listener/heap soak metrics are not yet recorded |

## Open baseline gaps

1. Reconcile the ignored lab source so managed anatomy can be changed through
   the approved source workflow.
2. Capture actual frame-time p50/p95, draw calls, scene objects, active
   materials, particle counts, DPR and dropped-frame periods at high/medium/low
   tiers.
3. Capture idle, planning, 8-worker, materialized workspace, verification,
   reabsorption, stale and stop states without fabricating backend truth.
4. Run a 20–30 minute soak and record scene-object, listener, transient-pool
   and heap/resource trends.
5. Exercise real context loss through `WEBGL_lose_context` where the browser
   permits it; the existing boundary unit test is not equivalent evidence.
6. Run 320×568, 375×812, 768×1024, 1024×768 and 1440×900 responsive checks,
   keyboard/reduced-motion checks and a human screen-reader review.
7. Obtain operator visual review for the sacred palette and texture/GLB canon.

## Gate conclusion

The physical-embodiment RFC is now grounded in the current remote master and
the unchanged runtime. The baseline is sufficient to begin source reconciliation
and the pure physical projection slice. It is not evidence that the final
physical embodiment, performance targets, human validation or outside exposure
are complete.
