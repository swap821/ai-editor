# Living-Being Frontend 100% Working Blueprint

**Date:** 2026-06-18  
**Status:** Roadmap v2; Phase 1 product port verified; Phase 2 anatomical root-system product port verified; Phase 3 lifecycle lab proof verified; Phase 3 product sync next after operator acceptance  
**Owner:** operator (kumarswapnil82)  
**Builder note:** This document turns the current 60-70% living-being lab into a concrete build reference for reaching the operator's intended 100% working organism.

---

## 0. Why this document exists

The current living-being frontend direction is correct, but it is not finished. The written vision in `2026-06-16-living-being-frontend-design.md` is roughly 85-90% aligned with the operator's imagination. The live lab is closer to 60-70% because some visible pieces still read as UI objects attached to a being instead of functions of one continuous body.

This blueprint is the frontend equivalent of the backend true-picture docs: it states what is real, what is missing, and what must be built next. It is the reference future agents should read before starting any new living-being mechanism.

---

## 1. North star

The product is not a dashboard, a canvas demo, or a 3D skin over an IDE. It is a local-first AI-OS that appears as a living nervous being.

The user talks to the being through its body. The being thinks through its brain. Work moves through its spinal cord. Tabs are seated in vertebrae. Roots conduct state. Outcomes leave marks. Finished work is reabsorbed into memory.

The user should feel: "this thing is alive and working with me", not "this app has a cool brain background."

---

## 2. One law

Everything visible must satisfy one of these conditions:

1. It is part of the being's anatomy.
2. It grew out of the being's anatomy.
3. It is state moving through the being's anatomy.
4. It is memory left inside the being's anatomy.

If a visible element cannot pass one of those four tests, it does not belong in the primary experience.

---

## 3. What 100% means

100% is not "more glow." 100% means the interface works as a complete organism under real product use.

| Area | 100% requirement |
|---|---|
| Body ownership | No visible floating DOM chrome, no detached panels, no foreign editor, no UI object that does not belong to the body. |
| State truth | Thinking, working, approval, error, completion, route, memory, and autonomy state are read from the body itself. |
| Anatomy | Brain, brainstem, spine, vertebrae, bilateral roots, root fan, and cauda-equina spray are one continuous system. |
| Work surfaces | Input, approval, content, previews, and corrections are born from anatomical anchors and reabsorbed after use. |
| Orchestration | Multi-tab work is conducted through vertebra order. The active work is pulled forward by attention, not selected by chrome. |
| Real data | All non-ambient reactions bind to real backend or lab state. No fake activity, no demo stub passed off as product truth. |
| Motion | Every motion communicates a body event: notice, intake, conduction, grip, hold, release, pain, repair, memory, or rest. |
| Aesthetic | Surfaces, roots, text, and controls share the brain's dark point-field flesh and restrained luminous palette. |
| Ergonomics | Readable work, responsive layouts, keyboard/touch access, reduced-motion path, and stable frame rate. |
| Proof | Unit contracts, full test/build gates, browser screenshots, WebGL proof hooks, and final operator browser approval. |

The agent can verify code and browser signals. The operator is the final judge of aesthetic completion.

---

## 4. Current honest state

**Overall live lab:** 60-70%.

### What is real and strong

| Built capability | Status |
|---|---|
| Real human-brain aesthetic and point-field material family | Strong. This is the canon look to preserve. |
| Deep spine and vertebral structure | Strong base. It reads as anatomical, not just abstract rings. |
| Brainstem intake and in-scene conversational path | Good direction. It obeys the body-first law. |
| Vertebra-seated materialized surfaces | Good direction. Earlier cortex-panel mistake was corrected. |
| Luminous 3D text direction for code | Correct direction. It removes the foreign IDE feel. |
| Living orchestration contract | Strong architecture. State can be derived before rendering. |
| Attention conduction, posture, docking, metabolism, outcome imprint, reabsorption, root actuator | Good mechanism library in the lab. These are the right building blocks. |
| Reference folder direction | Correctly points toward a point-field anatomical conductor, not a static spine model. |

### What still keeps it below 100%

| Gap | Why it matters |
|---|---|
| Some surfaces still read as panels first, organs second | The illusion breaks when a rectangular slab feels pasted onto the being. |
| The root fan is only partly integrated into all work states | Roots must be a live tool, not only a pretty anatomical background. |
| Mechanisms exist slice-by-slice, but not yet as one body grammar | The user must feel one organism, not a stack of successful effects. |
| Product sync is not the trusted source yet | Lab mechanisms must land through a safe port path before the product can claim them. |
| Real backend turn choreography is incomplete in the organism | The body should visibly process the full cycle: ask, approve, work, verify, correct, finish. |
| Camera language is not yet cinematic enough | The being should guide attention with posture and shot framing, not rely on the user hunting the scene. |
| Mobile and compact states are not fully proven | A living organism must recompose, not shrink into an unreadable desktop scene. |
| Accessibility and reduced-motion behavior are not yet treated as first-class organism states | The look can stay sacred while motion reduces and input remains usable. |
| Verification is still per-mechanism, not full journey | The 100% proof must run an end-to-end living workflow. |

---

## 5. Design read and dials

Reading this as: an immersive 3D AI-OS organism for a technical operator, with anatomical sci-fi nervous-system language, leaning toward React Three Fiber, tested pure state contracts, and browser-verified motion.

| Dial | Target |
|---|---|
| Design variance | 8/10. Anatomical and asymmetric, but always centered around the brain-spine body. |
| Motion intensity | 9/10. Cinematic, fluid, and constant, but every motion must express state. |
| Visual density | 6/10. Rich organism detail, but work must remain readable. |

---

## 6. Hard bans

These patterns are not allowed in the 100% version:

1. Visible 2D HUD chrome as the primary interface.
2. Panels floating over the being without an anatomical origin.
3. White, grey, or bright editor chrome inside a work surface.
4. Broad amber/red/green surface washes that hide the brain material.
5. Static roots that do not respond to work state.
6. Decorative motion that does not encode a cause.
7. Fake metrics, fake files, fake progress, or demo content presented as real.
8. Auto-degrading the canon look without operator choice.
9. Building directly in product `frontend/src/superbrain/` when the lab source must be used.
10. Reporting visual work as done without browser proof.

---

## 7. Architecture rules

### Rule A - Pure contract before renderer

Every mechanism starts as a pure helper or store:

- input state in
- anatomical role/state out
- unit tests first
- renderer consumes it without inventing semantics

Examples already following this pattern: `livingOrchestrator`, `anatomicalConductor`, `spinalRootActuator`, `turnMetabolism`, `outcomeImprint`, `completionReflex`.

### Rule B - One body grammar

Mechanisms must compose through the same vocabulary:

| Grammar term | Meaning |
|---|---|
| Intake | User intent entering through the brainstem. |
| Conduction | State moving through spine/roots. |
| Seat | A vertebral address that owns work. |
| Grip | Roots tense around an active surface. |
| Hold | Approval or correction keeps the surface forward. |
| Pain | Error state returns through roots as a scar, not a full-panel alarm. |
| Repair | The being keeps the scarred work available for correction. |
| Completion | Green outcome settles, dissolves, and reabsorbs. |
| Memory | A persistent but subtle trace inside spine, galaxy, or cortex. |
| Rest | The body returns to breathing voyage, not a blank idle screen. |

### Rule C - Material family lock

All new visible parts must inherit the brain family:

- dark flesh core
- cyan-white nervous light
- soft gold signal beads
- restrained magenta/error scar
- point-field texture or puncta
- no default UI whites
- no generic glass panels

### Rule D - Product truth

The GAG lab may prototype quickly. The product only receives a mechanism when:

1. The lab contract has focused unit tests.
2. The lab visual has browser screenshots.
3. The port manifest is reviewed.
4. Product sync is deliberate.
5. Product build/test gates pass.

---

## 8. Roadmap to 100%

### Phase 0 - Canon and proof baseline

**Goal:** make the current 60-70% state measurable before more building.

| Work | Acceptance |
|---|---|
| Create a visual gap ledger from current lab screenshots | Each gap is tagged as anatomy, surface, motion, data truth, readability, mobile, or performance. |
| Capture baseline screenshots for rest, typing, approval, content, multi-tab, error, completion | Stored under a dated proof folder. |
| Confirm dev URL and browser probe recipe | `http://localhost:3000/` for lab proof unless changed and documented. |
| Review `npm run port` manifest before product sync | No blind sync from lab to product. |
| Define full journey probe | One scripted path: type intent, show intake, approval hold, content work, verify green, reabsorb. |

**Exit:** We know exactly what the remaining 30-40% is in pixels.

### Phase 1 - Organ material unification

**Goal:** make every surface look like the being's own living tissue.

| Work | Acceptance |
|---|---|
| Replace remaining panel-like material cues with dark brain-flesh surfaces | No visible light chrome, no foreign panel headers, no default editor look. |
| Create one material token map for input, approval, content, preview, correction | Every surface color/emissive value comes from the same organism palette. |
| Add point-field texture/puncta to surface borders, roots, and clamps | Surfaces read as the same material family as the brain. |
| Make luminous text the bright element, not the surface frame | Code and user text are readable without turning the container into a UI panel. |

**Exit:** A screenshot without motion still reads as an organism, not an app window.

### Phase 2 - Anatomical root system completion

**Goal:** roots become a full live actuator for work.

| Work | Acceptance |
|---|---|
| Promote spinal-root actuator behavior across all visible root fans | Active, waiting, holding, error, and reabsorbing roots visibly differ. |
| Make bilateral roots grip active vertebral seats | The root fan participates in work, not just tab wires. |
| Tune cauda-equina spray for state memory | Lower root spray carries settling or reabsorption traces without becoming noisy. |
| Add browser proof for each state | Screenshots include conducting, holding, error return, and reabsorption. |

**Exit:** The operator's spinal-root reference is alive in the working UI.

**2026-06-19 checkpoint - Phase 2 anatomical root-system lab proof complete:**

- Added `anatomicalRootSystem`, a pure scene-level contract that derives bilateral root strands, role/flow, seat summaries, clamp opacity, memory traces, and cauda-equina traces from orchestrated surfaces, metabolism, and outcome imprint state.
- `AnatomicalConductorOverlay` now consumes the root-system snapshot so active, waiting/sensing, holding, error, and reabsorbing root fans visibly differ instead of sharing one generic wire treatment.
- `MaterializationLayer` derives the root-system snapshot every frame and exposes `window.__getAnatomicalRootSystem` for browser proof.
- Added `tools/probe-phase2-root-system.mjs` with SwiftShader Chromium flags, state-specific assertions, screenshots, and JSON capture for conducting+waiting, holding, error return, and reabsorbing memory.
- Browser proof generated:
  - `C:/tmp/gag-phase2-root-conducting-waiting.png`
  - `C:/tmp/gag-phase2-root-holding.png`
  - `C:/tmp/gag-phase2-root-error-return.png`
  - `C:/tmp/gag-phase2-root-reabsorbing-memory.png`
  - `C:/tmp/gag-phase2-root-system-probe.json`
- Verified after the slice: focused tests passed 4 files / 21 tests, full lab `npm test` passed 31 files / 206 tests, lab `npm run build` passed, `node --check tools/probe-phase2-root-system.mjs` passed, and `node tools/probe-phase2-root-system.mjs` passed against `http://localhost:3000/`.
- Visual check: screenshots are nonblank and framed; holding shows amber clamp tension, error returns as magenta/red root scarring, and reabsorption leaves a cyan memory trace.

**2026-06-19 checkpoint - Phase 2 product port verified:**

- Operator approved the Phase 2 lab proof, then `npm run port -- --dry-run` confirmed the product manifest included `anatomicalRootSystem.ts` and `anatomicalRootSystem.test.ts`.
- `npm run port` copied 54 live source files, 21 test/support files, 5 assets, and generated CSS into `frontend/src/superbrain`; product `brain.glb` was stripped only in the product copy.
- Product gates passed: `frontend` `npm test` passed 38 files / 228 tests and `npm run build` passed.
- Product browser proof passed against `http://localhost:5173/?ui=superbrain`: `tools/probe-phase2-root-system.mjs http://localhost:5173/?ui=superbrain` verified one canvas plus conducting+waiting, holding, error return, and reabsorbing memory root-system snapshots.
- Product screenshots generated and visually checked:
  - `C:/tmp/gag-phase2-root-conducting-waiting.png`
  - `C:/tmp/gag-phase2-root-holding.png`
  - `C:/tmp/gag-phase2-root-error-return.png`
  - `C:/tmp/gag-phase2-root-reabsorbing-memory.png`
  - `C:/tmp/gag-phase2-root-system-probe.json`

**Remaining for full Phase 2 exit:** reviewer approval of the product-sync handoff.

### Phase 3 - Full body lifecycle orchestration

**Goal:** one state machine owns the whole visible lifecycle.

| Work | Acceptance |
|---|---|
| Collapse mechanism slices into one orchestration layer | Intake, work, approval, error, done, and rest are derived coherently. |
| Add lifecycle contracts for full user journeys | Tests cover transitions, stale state, replacement, and reabsorption. |
| Ensure old surfaces never overlap new active work | No stale intake/content collision. |
| Expose a single debug hook for current organism state | Browser proof can read the body state without probing many separate stores. |

**Exit:** The body has one authoritative nervous-system state.

**2026-06-19 checkpoint - Phase 3 lifecycle orchestration lab proof complete:**

- Added `organismLifecycle`, a pure scene-level contract that composes living orchestration, turn metabolism, outcome imprint, completion reflex, and anatomical roots into one authoritative organism snapshot.
- The snapshot exposes phase, posture, body event, active/intake/approval/completion/reabsorbing/stale IDs, conductor order, surface body roles, root/metabolism/outcome/completion summaries, and a fail-closed invariant with a corruption signature.
- Covered the contract with focused tests for rest, intake, materializing, conducting, approval hold, error repair, completion settle, reabsorption, stale intake overlap, and duplicate filepath replacement detection.
- `MaterializationLayer` now exposes `window.__getOrganismLifecycle()` beside the lower-level debug hooks so browser proof reads one body state without probing many separate stores.
- Added `tools/probe-phase3-lifecycle.mjs`, which drives the lab browser through intake, approval hold, conducting, completion settle, explicit reabsorbing surface state, and error repair.
- Browser proof generated:
  - `C:/tmp/gag-phase3-lifecycle-intake.png`
  - `C:/tmp/gag-phase3-lifecycle-approval.png`
  - `C:/tmp/gag-phase3-lifecycle-conducting.png`
  - `C:/tmp/gag-phase3-lifecycle-settle.png`
  - `C:/tmp/gag-phase3-lifecycle-reabsorbing.png`
  - `C:/tmp/gag-phase3-lifecycle-error.png`
  - `C:/tmp/gag-phase3-lifecycle-probe.json`
- Verified after the slice: focused tests passed 3 files / 27 tests, full lab `npm test` passed 32 files / 215 tests, `node --check tools/probe-phase3-lifecycle.mjs` passed, lab `npm run build` passed, and `node tools/probe-phase3-lifecycle.mjs` passed against `http://localhost:3000/`.
- Visual check: screenshots are nonblank and framed. Intake, approval, conducting, settle, and error states show the expected surface/body relationship; reabsorbing is visually subtle after pullback, with the lifecycle hook proving the retracting surface frame.

**Remaining for full Phase 3 exit:** operator aesthetic approval of the lab screenshots, then deliberate product sync through the port manifest plus product tests/build/browser proof.

### Phase 4 - Real work loop through the body

**Goal:** real backend work becomes visible as body behavior.

| Work | Acceptance |
|---|---|
| Route work intent through the living intake | User intent rises through the stem before any surface appears. |
| Approval is a vertebral hold reflex | Approval surfaces are born from a seat, root-held, and released on decision. |
| Content work streams as luminous thought | Code/content appears as in-body luminous text, not editor chrome. |
| Verification green and red map to body outcomes | Green settles/reabsorbs; red scars/holds for correction. |
| Backend offline/error path has an in-body cue | No crash, no disconnected foreign error panel. |

**Exit:** A real supervised work turn is understandable from the organism alone.

### Phase 5 - Multi-work conductor

**Goal:** many simultaneous work surfaces feel orchestrated, not cluttered.

| Work | Acceptance |
|---|---|
| Vertebra order controls focus movement | Attention moves through anatomical addresses. |
| Active work is center-forward and readable | No hunting for the current task. |
| Waiting work remains alive but subordinate | Waiting tabs breathe at depth without visual competition. |
| Mini-brain docks and scales with load | Brain, cord, and surfaces remain one composition on desktop and compact viewports. |
| Camera participates in attention | Shot framing reinforces the being turning to work. |

**Exit:** Two to seven work items feel conducted by one spinal system.

### Phase 6 - Sensory and voice completion

**Goal:** the being talks and listens through its body.

| Work | Acceptance |
|---|---|
| Voice or typed input uses the same intake grammar | No separate voice HUD competing with the body. |
| Reply text emanates from the cortex or descends through the stem | The answer is spoken by the being, not printed by a chat widget. |
| `voice-speaking` or equivalent signal pulses the brain and cord | The body visibly speaks. |
| Mic denied, unsupported browser, and text-only fallback are body states | Accessibility and fallback stay in-world. |

**Exit:** Conversation feels like talking to the being.

### Phase 7 - Memory, truth, and autonomy made visible

**Goal:** the being shows what the AI-OS actually knows and did.

| Work | Acceptance |
|---|---|
| Memory star birth binds to real facts/skills/trails | New memory is visible only when real data changes. |
| Route privacy state gets a subtle body mark | Local vs cloud-permitted work is visible without badge chrome. |
| Earned autonomy has a distinct pulse | Self-action looks different from human-approved action. |
| Swarm/role-pass work appears as transient satellite cognition | Multi-agent activity becomes body truth, not terminal narration. |
| Audit health stains or cleans the spine | Trust state becomes visceral without becoming alarmist. |

**Exit:** The organism reflects the real AI-OS, not a decorative brain.

### Phase 8 - Product landing

**Goal:** the lab organism becomes the actual product surface.

| Work | Acceptance |
|---|---|
| Reconcile lab and product file ownership | Product-safe files stay product-safe; lab-owned files port cleanly. |
| Update port manifest | No stale assumptions about overwritten files. |
| Port only accepted mechanisms | Lab screenshots and operator notes travel with the sync. |
| Product tests/build pass | `npm test`, `npm run build`, and relevant product tests pass. |
| Backend optionality is clean | Backend-offline behavior is expected and not noisy. |

**Exit:** The default product mount matches the accepted lab direction.

### Phase 9 - Hardening and polish

**Goal:** make the 100% organism reliable.

| Work | Acceptance |
|---|---|
| Reduced motion is a first-class path | Motion reduces, look and meaning remain. |
| Mobile/compact layouts are designed, not auto-shrunk | No overlapping text, no unreadable work, no hidden controls. |
| Keyboard and touch flows are usable | Critical actions have accessible controls and state labels where needed. |
| Performance budget is measured | Desktop and compact screenshots are nonblank, framed, and stable. |
| Golden/proof routine is repeatable | Future visual edits can be compared against known-good states. |

**Exit:** The organism is not only impressive. It is usable and maintainable.

---

## 9. Near-term build lane

The next concrete lane should not add a new organ. It should unify the existing ones.

### Next mechanism: Organ Material Harmonizer

**Purpose:** remove the remaining "panel attached to organism" feeling by making all materialized surfaces and their roots share one body material grammar.

**Scope:**

1. Add a pure `organMaterialState` contract that derives surface material roles from kind, lifecycle, metabolism, outcome, and actuator state.
2. Replace per-component color constants with one material token map.
3. Darken/de-chrome input, approval, and content surfaces.
4. Keep luminous text readable.
5. Add point-field puncta and low-amplitude tissue aura consistently across surface edge, roots, and clamp points.
6. Browser-proof rest, input, approval hold, content work, error scar, and green reabsorption.

**Why this first:** until the material family is unified, every new mechanism risks looking like another good effect attached to a not-quite-living panel.

**2026-06-18 checkpoint - slice 1 complete:**

- Inspected `GAG demo/assets-source`: current contents are full UE 5.8, Twinmotion 2026.1, and RealityScan 2.1 application/tool trees, not optimized web runtime assets.
- Added `GAG demo/assets-source/AIOS_ASSET_SOURCE.md` to record the integration rule: these folders are reference/provenance only until specific `.glb`, `.gltf`, `.ktx2`, `.webp`, `.png`, `.jpg`, `.hdr`, or `.exr` exports are selected and optimized.
- Added pure `organMaterialState` contract plus tests in the GAG lab.
- Materialized input, approval, content, waiting, scar, and memory roles now derive one shared dark brain-family material state with point-field/source-texture/root-grip multipliers.
- `MaterializedTab` consumes the contract for surface body, plate, frame, membrane, roots, clamps, scars, and deterministic point-field puncta.
- `MaterializationLayer` exposes `window.__getOrganMaterialStates()` for browser proof.
- Browser proof generated:
  - `C:/tmp/gag-organ-material-input-check.png`
  - `C:/tmp/gag-organ-material-approval-check.png`
  - `C:/tmp/gag-organ-material-content-check.png`
  - `C:/tmp/gag-organ-material-scar-check.png`
  - `C:/tmp/gag-organ-material-probe.json`
- Verified after the slice: `npm test` passed 29 files / 193 tests, `npm run build` passed, and `node tools/probe-organ-material.mjs` passed against `http://localhost:3000/`.

**Remaining for full Phase 1 exit:** operator aesthetic approval, further de-panel shaping if requested, green completion/reabsorption screenshot proof, compact/mobile proof, and product sync only after port-manifest review.

**2026-06-19 checkpoint - shape grammar gate complete in lab:**

- Added pure `surfaceShapeGrammar` contract plus tests in the GAG lab.
- The contract derives surface class, anatomical attachment, Bezier tension offsets, attachment-to-free-edge thickness gradient, attachment-biased puncta falloff, and root/stem grip indentation from kind, lifecycle, focus, material role, actuator state, origin, and target pose.
- `MaterializedTab` now consumes the contract for the slab contour, membrane overlay, thickness bands, root/stem grip deformation marks, and non-uniform point-field puncta distribution.
- `MaterializationLayer` exposes `window.__getSurfaceShapeGrammars()` for browser proof using the same posed target logic as the renderer.
- Added `tools/probe-surface-shape-grammar.mjs` with SwiftShader Chromium flags and contract assertions for input, approval, content, and correction scar surfaces.
- Browser proof generated:
  - `C:/tmp/gag-surface-shape-input-check.png`
  - `C:/tmp/gag-surface-shape-approval-check.png`
  - `C:/tmp/gag-surface-shape-content-check.png`
  - `C:/tmp/gag-surface-shape-scar-check.png`
  - `C:/tmp/gag-surface-shape-probe.json`
- Verified after the slice: focused tests passed 3 files / 16 tests, full `npm test` passed 30 files / 198 tests, `npm run build` passed, and `node tools/probe-surface-shape-grammar.mjs` passed against `http://localhost:3000/`.

**2026-06-19 checkpoint - completion and compact proof complete in lab:**

- Added `tools/probe-phase1-completion-compact.mjs` with SwiftShader Chromium flags, screenshot capture, PNG canvas-region pixel checks, and assertions for the green completion journey.
- The browser proof now verifies: focused content receives `VERIFICATION GREEN`, completion reflex enters `settling`, target content enters `reabsorbing`, the target tab becomes `retracting`, the reabsorbing surface carries memory material + memory shape grammar, the tab clears, and desktop/compact/mobile canvases are nonblank.
- Tightened memory material so verified/retracting work remains visibly readable after focus is released during reabsorption.
- Made materialized workspace pose viewport-aware so compact/mobile scenes pull active work inward/up and scale it down instead of letting work text drift offscreen.
- Browser proof generated:
  - `C:/tmp/gag-phase1-green-settle-check.png`
  - `C:/tmp/gag-phase1-green-reabsorb-check.png`
  - `C:/tmp/gag-phase1-green-cleared-check.png`
  - `C:/tmp/gag-phase1-compact-check.png`
  - `C:/tmp/gag-phase1-mobile-check.png`
  - `C:/tmp/gag-phase1-completion-compact-probe.json`
- Verified after the slice: focused tests passed 5 files / 30 tests, full `npm test` passed 30 files / 200 tests, `npm run build` passed, and `node tools/probe-phase1-completion-compact.mjs` passed against `http://localhost:3000/`.

**2026-06-19 checkpoint - Phase 1 product port verified:**

- Reviewed and upgraded `tools/port-to-frontend.mjs` so `--dry-run` prints the exact port manifest, recursively discovers the live runtime import graph, and carries matching sibling test contracts for that live graph.
- `npm run port` copied 53 live source files, 20 test/support files, 5 assets, and generated CSS into `frontend/src/superbrain`; product-safe wrappers stayed outside the lab-managed tree and the product `brain.glb` strip still applies only to the product copy.
- Product gates passed: `frontend` `npm test` passed 37 files / 222 tests and `npm run build` passed.
- Product browser proof passed against `http://localhost:5173/?ui=superbrain`: `tools/capture-product.mjs phase1-product-port` generated `GAG demo/gag-orchestrator/goldens/phase1-product-port-idle.png`, and `tools/probe-phase1-completion-compact.mjs http://localhost:5173/?ui=superbrain` passed desktop, compact, and mobile reduced-motion canvas-region pixel checks.
- Tooling note: `tools/probe-phase1-completion-compact.mjs` now accepts an optional target URL while preserving `http://localhost:3000/` as the lab default.

**Remaining for full Phase 1 exit:** operator aesthetic approval of the lab/product screenshots and reviewer approval of the product-sync handoff.

---

## 10. Clinical death and recovery

**Goal:** define what the organism does when its own body fails.

The living-being UI must never fail as a blank dead canvas. If WebGL, backend state, or internal orchestration fails, the product must enter a visible injured state with recovery affordances.

### 10.1 Failure taxonomy

| Failure class | Trigger | Body response |
|---|---|---|
| Renderer death | WebGL context lost, R3F unmount error, shader compile fail | Immediate cut to `recoveryStem` (see 10.2). Log to `window.__organismDeathLog`. |
| Backend silence | No response in 15s, 5xx, or connection drop | Spine enters `suspendedConduction`: low amber pulse, roots relax, surfaces dim but remain readable. Retry with exponential backoff shown as slow stem breath. |
| State corruption | Orchestrator derives impossible state, such as intake and completion simultaneously | Body freezes in last known good frame. `window.__organismState` exposes `corruptionSignature`. Auto-reset to rest after 30s unless the user holds. |
| Memory pressure | Tab memory above 500 MB where measurable, estimated texture/object budget breach, or FPS below 10 for 5s | `metabolicSlowdown`: reduce point-field density, pause non-essential animations, notify through stem glow. |
| Script error | Unhandled exception in render loop | Error boundary catches. Body displays scar at nearest vertebra. It does not blank. |

### 10.2 Recovery stem

`recoveryStem` is a minimal non-WebGL fallback owned by the app shell, not by the Three.js scene. It proves the organism is still alive when the renderer is injured.

| Requirement | Contract |
|---|---|
| Visual continuity | Dark background with one slowly breathing cyan ellipse: the stem. |
| Text continuity | Text surfaces render as plain DOM with brain-family CSS: dark flesh, luminous text, restrained scar/accent colors. |
| Input continuity | User can type. Input is captured and queued while the renderer is down. |
| Recovery motion | When WebGL recovers, transition through a 1.5s rehydration: stem expands into full body and surfaces materialize from their DOM positions. |

### 10.3 Acceptance

| Proof | Acceptance |
|---|---|
| Unit/integration | `npm test` includes renderer-kill simulation and verifies queued input survives fallback. |
| Browser proof | Screenshot of recovery stem after forced context loss. |
| Operator approval | The fallback still feels like the same being, just injured. |

---

## 11. Shape grammar for surfaces

**Goal:** make the panel ban structural, not only chromatic.

The Organ Material Harmonizer cannot stop at color. A surface becomes anatomical only when its contour, attachment, thickness, puncta distribution, and root grip all imply living tissue.

### 11.1 The panel ban, positively stated

A surface is anatomical when it satisfies at least three of these rules:

| Rule | Implementation |
|---|---|
| Membrane attachment | One edge is visually continuous with a vertebra or root fan. No free-floating rectangle. |
| Tension curve | At least one border follows a quadratic Bezier with control point offset 8-24px from the chord midpoint. Straight edges must be anchored by clamps at both ends. |
| Thickness gradient | Surface body is thicker near attachment, thinner at the free edge: 2px to 0.5px in screen space. |
| Puncta field | Point-field density is higher at attachment and lower at free edge, never uniform. |
| Root grip marks | Where roots meet the surface, visible clamp geometry deforms the surface edge locally with a 2-6px indentation. |

### 11.2 Per-surface type rules

| Surface kind | Primary attachment | Tension direction | Special rule |
|---|---|---|---|
| Input | Brainstem inferior | Vertical, stem-to-cortex | Lower edge is free and curves upward at the corners. |
| Approval | Vertebra anterior | Horizontal, bilateral | Both sides are gripped by roots; top and bottom curve. |
| Content | Vertebra anterior or lateral | Contextual | May stack. Lower content surfaces partially occlude upper ones with membrane overlap. |
| Preview | Root terminus | Radial | Smallest surface; often circular or lens-shaped. |
| Correction scar | Same seat as original | Same as original | Surface retains original shape but gains puncta disruption and magenta edge bleed. |

### 11.3 Acceptance

| Proof | Acceptance |
|---|---|
| Browser proof | Screenshot grid of each surface type with attachment and tension curves visible. |
| Operator approval | No surface reads as a card, panel, or modal. |

---

## 12. Latency choreography

**Goal:** define what the body does while waiting.

Latency must not make the organism look dead or stuck. Waiting is a body state.

### 12.1 Backend round-trip states

| Phase | Duration | Body behavior |
|---|---|---|
| Intent rise | 0-300ms | User input travels up brainstem. Stem pulses once. No surface yet. |
| Intake hold | 300ms-approval | Surface materializes at stem-vertex, anchored, with grip animation. Roots tense toward it. |
| Approval wait | Human decision | Surface breathes slowly. Roots hold tension. Brain emits low-amplitude theta wave. |
| Work dispatch | 0-500ms | Surface slides to vertebral seat. Roots release stem, grip vertebra. Brief conduction flash down spine. |
| Backend think | 500ms-15s | Active vertebra enters `metabolicWork`: surface glows softly, point-field puncta drift slowly, roots maintain grip with micro-tremor. Spine shows slow peristaltic pulse toward the work seat. |
| Streaming result | Chunked arrival | Content appears as luminous text inside the surface, line by line, with a soft birth flash per line. No jump scroll. |
| Verify hold | Human decision | Surface brightens. Roots tense to hold. Green signal beads accumulate at clamps. |
| Completion | 0-500ms | Green wash travels from clamps inward. Surface dissolves to membrane. Roots release. Cauda-equina spray receives reabsorption trace. |
| Error return | Any phase | Magenta edge bleed at surface. Roots do not release; they scar-grip. Surface remains for correction. Spine shows brief pain pulse. |

### 12.2 Timeout degradation

| Overrun | Behavior |
|---|---|
| 5s | Micro-tremor on roots increases. Surface gains subtle amber edge. |
| 10s | Stem emits slow amber pulse. Surface text dims 20%. |
| 15s | Enter `suspendedConduction` (see 10.1). User can cancel or hold. |

### 12.3 Acceptance

| Proof | Acceptance |
|---|---|
| Unit tests | Each phase transition is covered with mocked latency. |
| Browser proof | Video or screenshot sequence of 5s, 10s, and 15s wait states. |
| Operator approval | The body never looks dead or stuck. |

---

## 13. Performance budget

**Goal:** make reliability measurable with numbers, not feelings.

### 13.1 Targets

| Device class | GPU | FPS | Draw calls | Texture memory | Notes |
|---|---|---:|---:|---:|---|
| Desktop primary | Dedicated, 2022+ | 60 | <= 120 | <= 256 MB | Full effects, max puncta density. |
| Desktop fallback | Integrated, 2020+ | 45 | <= 80 | <= 128 MB | Reduce puncta, simplify root geometry. |
| Tablet | iPad Pro / flagship Android | 45 | <= 80 | <= 128 MB | Same as desktop fallback. |
| Mobile | Mid-range phone | 30 | <= 50 | <= 64 MB | Compact layout, reduced scene depth, no cauda-equina spray. |
| Reduced motion | Any | 30 | <= 50 | <= 64 MB | Disable continuous animation; use luminosity shifts only. |

### 13.2 Measurement hooks

Expose `window.__organismPerformance` with:

- `fps`: rolling 1s average.
- `drawCalls`: per frame.
- `textureMemoryMB`: measured when available, estimated otherwise.
- `activePunctaCount`.
- `surfaceCount`.
- `lastFrameTimeMs`.

### 13.3 Enforcement

| Gate | Contract |
|---|---|
| Unit/perf contract | Simulate seven surfaces and verify desktop profile decisions keep intended draw calls below 120. |
| Browser proof | Full journey probe records `window.__organismPerformance` after rest, one surface, and seven surfaces. |
| Runtime protection | If FPS stays below target for 5s, auto-trigger `metabolicSlowdown` (see 10.1). |

### 13.4 Acceptance

| Proof | Acceptance |
|---|---|
| Browser proof | `window.__organismPerformance` readout at rest, one surface, and seven surfaces. |
| Operator approval | No visible stutter on target hardware. |

---

## 14. Epistemic anatomy

**Goal:** make truth, uncertainty, and autonomy visible in the body.

### 14.1 Confidence states

| State | Body mark | Meaning |
|---|---|---|
| Certain | Steady cyan-white glow at surface core | Model is confident and output is verified against constraints. |
| Probable | Slow gold pulse at surface edge | Model is confident, but no external verification has been performed. |
| Uncertain | Slow magenta-cyan alternation at edge | Model expresses uncertainty; user should verify. |
| Hallucination risk | Rapid magenta micro-flash at clamps | Output contradicts known facts or constraints; surface is scarred preemptively. |

### 14.2 Autonomy audit

When the AI-OS acts without approval:

1. A transient satellite, a small orbiting surface, appears near the acting vertebra.
2. The satellite shows the action type as a glyph with a brief flash.
3. On completion, the satellite either merges into a memory star on success or falls as a scar fragment on failure.
4. User can click or tap the satellite to expand an audit trail in a memory surface.

### 14.3 Acceptance

| Proof | Acceptance |
|---|---|
| Unit tests | Confidence derivation from model output metadata is covered. |
| Browser proof | Screenshots of each confidence state. |
| Operator approval | User can distinguish certain from uncertain without reading text. |

---

## 15. Verification ladder

Each phase must pass this ladder:

1. **Contract proof:** focused tests for pure helpers.
2. **Renderer proof:** component or browser hook exposes the derived state.
3. **Full lab gate:** full lab `npm test` and `npm run build`.
4. **Browser proof:** screenshots in the operator's browser path, not just JSON.
5. **Operator eye:** the operator approves or names the visual gap.
6. **Resume currency:** update `RESUME.md`, append an experience object, update touched specs.
7. **Product sync gate:** only after lab acceptance.

Visual work is not done at step 3. Step 5 is the real aesthetic gate.

---

## 16. Scorecard

Use this score after every mechanism:

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| Anatomy | Detached UI | Connected to body | Body-owned organ |
| Motion | Decorative | State-related | Cause-effect body event |
| Material | Generic UI | On-palette | Brain-family tissue |
| Data truth | Fake/static | Partly real | Bound to real product/lab state |
| Truth | No confidence signal | Confidence shown in text/state only | Confidence is visible as body anatomy |
| Readability | Hard to use | Usable in one view | Usable across states/viewports |
| Reabsorption | Disappears | Animates out | Returns into body memory |

A mechanism is accepted only at 12/14 or higher, with no zero in anatomy, data truth, truth, or readability. When comparing to older notes, 12/14 is the expanded equivalent of the old 10/12 threshold.

---

## 17. Operating model

1. Read this roadmap before any living-being frontend work.
2. Read the 2026-06-16 design spec before touching the lab.
3. Work lab-first in `GAG demo/gag-orchestrator`.
4. Use pure contracts before renderer edits.
5. Keep the brain material family sacred unless the operator explicitly changes it.
6. Do not sync to product until the operator accepts the lab proof.
7. Keep docs current after each accepted mechanism.

---

## 18. Feature freeze trigger

**Goal:** define when to stop adding and start shipping.

### 18.1 Ship condition

The organism ships when:

1. All Phase 0-9 acceptance criteria are met.
2. Expanded scorecard average across all mechanisms is >= 12/14, equivalent to the original 10/12 bar.
3. No mechanism scores 0 in anatomy, data truth, truth, or readability.
4. Operator approves Phase 9 proof.
5. 48-hour stability hold passes: no P1 bugs, no memory leaks, no renderer deaths in continuous operation.

### 18.2 Post-freeze rule

After freeze, only these changes are allowed:

1. Bug fixes that prevent clinical death (see Section 10).
2. Performance regressions that drop below budget (see Section 13).
3. Accessibility failures that block input or output.
4. Security or trust surface corrections (see Section 14).

No new organs. No new motion. No new surfaces. The being is alive; do not add another limb.

### 18.3 How these additions slot in

| Roadmap area | Addition | Purpose |
|---|---|---|
| Near-term material work | Clinical death and recovery, shape grammar | Make Phase 1 structural, not just chromatic. |
| Verification | Latency choreography, performance budget | Make browser proof measurable under real conditions. |
| Scorecard | Epistemic anatomy | Add truth as a scored dimension. |
| Operating model | Feature freeze trigger | Prevent infinite polish and scope creep. |

---

## 19. Single next action

Review the Phase 3 lifecycle lab proof with the operator. If accepted, run the lab-to-product port manifest, sync the accepted Phase 3 files into `frontend/src/superbrain`, then verify product tests/build/browser proof before continuing Phase 4.
