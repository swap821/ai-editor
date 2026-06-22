# NERVE FORM RESEARCH — Evolving the Nervous System into an ALIVE Branching Nerve TREE

**Chief Architect synthesis.** Status: research + phased plan. NO code, NO build runs.
Authored 2026-06-15. Source-verified first-hand against the live tree (every coordinate,
uniform, and bus event below was read from the actual files, not from the lenses).

> **The final aesthetic call is, and remains, the OPERATOR'S BROWSER.** Every geometric
> and shader number here is *reasoned from the live code*, not measured. WebGL cannot be
> verified headlessly. Nothing in this document is "done" until it is signed off in HIS
> browser with before/after goldens.

---

## 1. VERIFICATION LEDGER (TRUE with file:line — read first-hand 2026-06-15)

### 1.1 FROZEN TIPS — verbatim, immutable (NervousSystem.tsx)

These are the hard constraint. They are the **last control point** of each bundle's
`CatmullRomCurve3`. Re-projecting them broke a past integration. NEVER move them.

| Constant / vector | Value | Line |
|---|---|---|
| `leftTargetX` | `-4.8` | NervousSystem.tsx:257 |
| `rightTargetX` | `4.8` | NervousSystem.tsx:258 |
| Left bundle final ctrl-pt | `new THREE.Vector3(leftTargetX, -1.7, 0.0)` → (-4.8, -1.7, 0) | NervousSystem.tsx:340 |
| Right bundle final ctrl-pt | `new THREE.Vector3(rightTargetX, -1.5, 0.0)` → (4.8, -1.5, 0) | NervousSystem.tsx:357 |
| Spinal bundle final ctrl-pt | `new THREE.Vector3(0.0, -2.6, 1.5)` | NervousSystem.tsx:373 |
| `tabX` | `4.82` (hardcoded; prevents 60fps geometry rebuild) | NervousSystem.tsx:212 |

The IDE ports sit EXACTLY on the left/right tips: `PORT_EDITOR = [-4.8, -1.7, 0]`
(ForgePorts.jsx:23), `PORT_PREVIEW = [4.8, -1.5, 0]` (ForgePorts.jsx:24). The nerves
already REACH the IDE. The form work is to make them branch/extend richly, NOT to re-aim them.

> **STALE-COMMENT WARNING (do not be misled):** ForgePorts.jsx:22 cites the port source
> as "NervousSystem.tsx:292,307". Those line numbers are WRONG (the live `leftTargetX`/
> `rightTargetX` are 257/258, the tip vectors 340/357). The **coordinate VALUES are correct**;
> ignore the stale line numbers in that comment.

### 1.2 Brainstem shared control points (the trunk confluence) — NervousSystem.tsx:323-327

All three bundles share these five points as their first control points, then diverge:

```
deepCore   = (0.0,  0.5,  -0.4)   line 323
rootSwell  = (0.0,  0.35, -0.42)  line 324  "soft organic bulge"
rootPinch  = (0.0,  0.1,  -0.45)  line 325  "pinch into the stem"
stemExit   = (0.0, -0.5,  -0.5)   line 326
spinalDrop = (0.0, -1.2,  -0.4)   line 327
```

These are the **same `const` THREE.Vector3 instances** reused across all three
`addWireBundle` calls (lines 333-340, 350-357, 367-373). A build-time detail with no
runtime implication (CatmullRom reads them once at construction). There is an explicit
in-code RISK LEVER at lines 320-322: "if CatmullRom emergence looks wrong in-browser,
drop rootPinch and keep rootSwell only."

### 1.3 Intermediate (NON-frozen) swoop points — editable

- Left: `(leftTargetX + 2.0, -2.2, -0.2)` = **(-2.8, -2.2, -0.2)** (line 338), then `(-4.8, -2.4, -0.05)` (line 339).
- Right: `(rightTargetX - 2.0, -2.2, -0.2)` = **(2.8, -2.2, -0.2)** (line 355), then `(4.8, -2.4, -0.05)` (line 356).
- Spinal: `(0.0, -2.0, 0.2)` (line 372) before the final tip.

> **LENS CORRECTION:** Lens 3 Part A wrote the left swoop as "(-2.6,-2.2,-0.2)". WRONG.
> `leftTargetX + 2.0 = -4.8 + 2.0 = -2.8`. The correct x is **-2.8**.

### 1.4 addWireBundle mechanics — VERIFIED (NervousSystem.tsx:260-317)

- Signature: `addWireBundle(numWires, controlPoints, baseSpread, bundleColor)` (line 260).
- `angleOffset = (i/numWires) * Math.PI * 2 * 3.0` (line 271).
- `layerRadius = baseSpread * (0.2 + 0.8 * Math.sqrt(i/numWires))` — sqrt packing (line 275).
- `twists = 4.0` constant (line 278).
- `thickness = 0.006 + (i % 3) * 0.002` → {0.006, 0.008, 0.010} (line 283).
- `new THREE.TubeGeometry(curve, 100, thickness, 6, false)` — 100 seg, 6-sided (line 285).
- Per-vertex attributes baked: `aWireColor`, `aPhase` (seeded `random()*2π`), `aSpeed`
  (`0.5 + random()*1.5`), `aPulse` (`random()>0.5 ? 1 : 0`) (lines 297-313).
- Seeded RNG: `createSeededRandom(0x57495245)` (line 254). House rule — NEVER `Math.random()`.
- `baseSpread = 0.07` for all three bundles (lines 342, 359, 375).

### 1.5 WIRE COUNT — authoritative = **125**, NOT 115

- Left = 45 (line 330), Right = 45 (line 347), Spinal = 35 (line 364). **Sum = 125.**
- NervousSystem.tsx:379 comment reads "Merge all 115 TubeGeometries" — **STALE COMMENT.**
  Every lens that says 115 is repeating a stale comment. Use **125**.

### 1.6 SpiralWireCurve power-law taper — VERIFIED (NervousSystem.tsx:153-161)

Four-zone taper of the *tube radius `r`* (NOT position — the tip POSITION is governed
solely by the curve control points; line 149-151 comment confirms this):

- `t < 0.2` brain root: `lerp(radius*2.8, radius*0.5, t/0.2) * (1 - (t/0.2)^2.2)` (line 154).
- `t 0.2-0.5` stem: `radius*0.5 * (1 - 0.6*((t-0.2)/0.3)^1.8)` (line 156).
- `t 0.5-0.8` peripheral swell: `lerp(radius*0.5, radius*1.8, (t-0.5)/0.3) * (1 - 0.5*((t-0.5)/0.3)^1.5)` (line 158).
- `t > 0.8` port pinch: `radius*1.8 * (1 - ((t-0.8)/0.2)^2.5)` → needle-sharp at tip (line 160).

### 1.7 Shader / uniform surface — VERIFIED (NervousSystem.tsx:39-90, 214-236)

- `WIRE_BURST_UNIFORM = { value: 0 }` — module-level leaf (line 93).
- `WIRE_FLOW_DIR = { value: 1 }` — module-level leaf (line 97).
- carrier = `vColor * 0.08` (line 56).
- `flowTime = uTime * vSpeed * (1.0 - uHold) * uFlowDir` (line 61).
- packet = `smoothstep(0.86, 0.90, flow) * smoothstep(0.98, 0.94, flow)` (line 67).
- signal = `mix(vec3(0,1,1), vec3(1), uBurst)` (line 73).
- `finalColor *= (1.0 + uBurst * 2.5)` (line 78); `finalColor *= mix(1.0, 0.2, uHold)` (line 82).
- Hard discard: `if (vUv.x < 0.005 || vUv.x > 0.995) discard;` (line 85).
- `uSignalGain = 3.5` (line 224); comment: do NOT drop below ~1.3 / ~2.5 or packet won't bloom.
- Material: `AdditiveBlending`, `depthWrite:false`, `transparent:true` (lines 230-235).
- `uFlowDir` is in WIRE_FRAGMENT only (line 44); NOT in WIRE_VERTEX (lines 9-37).

> **MATERIAL CORRECTION — `uFlowDir` is NOT inert.** Multiple lenses (and the inline
> comment at lines 225-228, "nothing drives it to -1 yet") are WRONG. The live
> `useEffect` at NervousSystem.tsx:186-197 subscribes to the cognition bus and sets
> `flowReverseUntil` on `knowledge-acquired` (+1800ms) / resets on `directive`|`agent-dispatch`.
> The frame loop at lines 243-247 eases `WIRE_FLOW_DIR.value` toward the target by 0.08/frame.
> The directional flow is **already LIVE and data-bound.** Plan accordingly — do not "build" it.

> **DEAD-CODE CORRECTION — `vPulse`/`aPulse` is inert.** WIRE_VERTEX declares + passes
> `vPulse` (lines 23, 30) and `aPulse` is baked (lines 299, 307, 313), but WIRE_FRAGMENT
> never declares or reads `vPulse`. "Some wires breathe" (line 299 comment) is FALSE in the
> shader today. `aPulse` is a dormant attribute available for future use — it is NOT a
> functioning behavior.

### 1.8 Group motion — VERIFIED (NervousSystem.tsx:199-207)

- `position.x = Math.sin(time*0.16)*0.24 + Math.cos(time*0.09)*0.1` (line 204) — mirrors brainDriftX.
- `position.y = 0.12 + Math.cos(time*0.2)*0.14 + Math.sin(time*0.14)*0.07` (line 205) — **note the persistent +0.12 offset**, not in any lens analysis.
- `position.z = -1.2` hardcoded (line 206) — **persistent z offset**, also not factored by lenses.

The nerve group rides this sway so the tips stay locked under the `<Html>` port panels.
The mesh is `frustumCulled={false}` (line 396). NervousSystem mounts OUTSIDE `<Float>`.

### 1.9 useMemo dependency surface — VERIFIED

- `mergedGeometry` useMemo deps: `[tabX]` (line 386). **`tier` is absent** — a tier prop
  must be added to props (line 171-177 currently take only `burst`, `uniforms`) and to deps.
- `material` useMemo deps: `[uniforms]` (line 237).
- Disposal: individual geoms disposed after merge (line 383); merged geom disposed on unmount (lines 388-392).

### 1.10 Cognition bus — VERIFIED (cross-checked against NodeLattice cohesion mandate)

- The lattice's WIRE_FRAGMENT is a **VERBATIM copy** of NervousSystem's, with an explicit
  "KEEP IN SYNC" mandate (NodeLattice.tsx:249-253, 277-281). It deliberately omits `uFlowDir`
  (one-directional) and adds `uCarrierGain` (line 287). **Any change to WIRE_FRAGMENT in the
  nerve must be mirrored into NodeLattice's copy or the two systems visually diverge.**
- Hubs/routing (NodeLattice.tsx:76-83): CAUSAL `#ff3b28` (plan/skill/recall/memory),
  ARCHIVE `#36f07a` (read/search/list/web/fetch), LATTICE `#19d4f0` (create/edit/write/exec/verify),
  SIGNAL `#9b3bff` (signal/route/security), ROUTER `#6a35ff` (authored, not a data anchor).
- Tier budgets (the established idiom to copy): `SATELLITES_PER_HUB = {high:24, medium:16, low:3}`
  (line 86), `EDGE_K = {high:3, medium:2, low:0}` (line 88).

> **BUS-PUBLISH CORRECTION (cited by lenses, relevant if per-bundle routing is attempted):**
> The lenses claim the typed-command path publishes `directive`. Per the corrections ledger,
> `sendDirective` does NOT publish a `directive` event — only the VOICE path (`sendVoiceTurn`)
> does. The typed path publishes `agent-dispatch` (per tool call) and `synthesis` (on done).
> The nerve's existing subscription (line 192) already handles `agent-dispatch`, so this does
> not block anything — but any "wait for a `directive` event on typed commands" assumption is WRONG.
> (aiosAdapter.ts line numbers in the lenses are approximate; verify against the live file before wiring.)

### 1.11 What the lenses got materially wrong (consolidated)

1. **Wire count is 125, not 115** (stale line-379 comment).
2. **Left swoop x is -2.8, not -2.6** (Lens 3).
3. **`uFlowDir` is LIVE and data-bound**, not inert (Lenses 2, 4 + the stale inline comment).
4. **`aPulse`/`vPulse` is dead shader code** — no breathing behavior exists today.
5. **The group has persistent z=-1.2 and y+=0.12 offsets** — uncredited by all lenses; relevant to any spatial reasoning.
6. **ForgePorts.jsx:22 line numbers are stale** (coordinate values are correct).
7. **The lattice carries a verbatim WIRE_FRAGMENT copy with a KEEP-IN-SYNC mandate** — a shader change to the nerve is a TWO-file change.

---

## 2. THE FORM — The Branching Nerve-Tree Geometry Plan

### 2.1 The anatomical mapping (operator's reference → existing geometry)

The reference is a human CNS+PNS: brain at top → spinal cord descending → a dense,
fractal, tapering peripheral nerve tree. The existing geometry already has the right
skeleton: the **brainstem confluence** (deepCore→spinalDrop) is the spinal cord; the
three bundles are the major nerve roots. What is MISSING is everything below "three thick
cables": no sub-fascicle divergence, no tapering filament density, no hierarchy, no tree.

### 2.2 The core safety principle — the tips are just the last array element

The frozen-tip constraint is narrow and exact: **the final control point of the
port-connected bundles must not change.** Everything UPSTREAM of that point, and ALL
new geometry that does not connect to a port, is open. New richness is purely ADDITIVE
`addWireBundle`-style calls pushed into `geometries[]` (line 315 pattern) BEFORE the single
`mergeGeometries` call (line 380). One BufferGeometry, one material, ONE draw call — always.

### 2.3 The three additive layers (the tree)

**LAYER A — Convergent secondary fascicles (the branching upgrade; THE point of the work).**
Anatomically, peripheral nerves are bundles of many fibers that *converge* toward the cord.
Model it that way: add secondary wires that originate within ±0.3 scatter of the brainstem
root zone (deepCore/rootSwell), trace *different* organic arcs through 3D space (seeded-random
offsets on their intermediate control points), and **converge to the SAME frozen tip
coordinate** as the primary bundle they belong to. The tip is the confluence — many fibers,
one endpoint. This is anatomically honest, visually rich, and **never invents a new
termination point**. The primary 45/45/35 wires are untouched; the new fascicles are
*additional* `addWireBundle` calls whose last control point is the identical frozen vector.

   - Per-fascicle params (finer than the trunk so they read as filaments, not cables):
     `numWires` 6-12, `baseSpread` 0.02-0.03 (vs 0.07), `twists` ~2.0 (vs 4.0),
     `thickness` 0.003-0.005 (vs 0.006-0.010), `TubeGeometry(curve, 60, ...)` for cheaper
     decorative tubes. Same bundle tint (LEFT/RIGHT/SPINAL) so they read as family.
   - They MUST share the t>0.8 port-pinch taper (lines 159-161) so they arrive needle-thin
     at the confluence — otherwise the port connection looks bulky.

**LAYER B — Cosmic root-tails into the void (idle organic depth).**
A fourth category of wires sharing deepCore→spinalDrop that then fan downward into empty
space (free endpoints around y -3 to -5, no UI port). These are "roots into the knowledge
void the brain voyages through." Because they have no port terminus, their taper can run to
true zero radius at the free end. They carry the SAME real bus packets (uBurst/uFlowDir/uHold)
— honest dormancy: they respond to real events identically, they are simply anatomically
unbound. Tier-gated: high 30 / medium 12 / low 0.

**LAYER C — Brainstem crown fan (the crown of the tree).**
The current root is a single 4-point emergence. A nerve tree has a visible crown — short,
thin nerves radiating from deepCore before collecting into the trunk. Add ~12 short thin
wires (layerRadius 0.03-0.05) from deepCore arcing outward to free endpoints, tapering to
zero. **Cohesion guard:** keep these from penetrating deeper than the lattice's 15% inward
margin (NodeLattice INWARD=0.85, line 57) so they don't read as interior lattice. Tier-gated:
high 12 / medium 6 / low 0.

### 2.4 Recursive-branch idiom (how to author the arcs without hand-placing every point)

`SpiralWireCurve` wraps a `CatmullRomCurve3`. A child fascicle's first control points can be
sampled from a parent path via `parentPath.getPoint(t)` at t≈0.4/0.5/0.6, giving G1-continuous
(tangent-matched) peel-off — the same mechanism the three bundles already use. CatmullRom
handles arbitrary control-point counts, so adding intermediate points between spinalDrop and
the (frozen or free) endpoint is safe. This is the procedural-branch technique; it must use the
seeded RNG continued from position 125+ (so trunk baselines stay byte-identical across mounts).

### 2.5 Why this is the right form (vs alternatives)

- **L-systems** produce rule-symmetric plant trees; the human PNS is asymmetric and
  fascicle-bundled. L-systems add coding tax for the wrong aesthetic. Rejected.
- **Convergent fascicles (Layer A)** are the lowest-risk, highest-fidelity move: they reuse
  the exact `addWireBundle` idiom, never touch a tip, and read as the anatomical reference.
- The hierarchy trunk → fascicles → filaments → void-tails is exactly the anatomical density
  gradient and is also a natural perf-tier gradient (drop the finest layers first).

### 2.6 Perf envelope (16GB box)

- Each `TubeGeometry(curve, 100, thickness, 6, false)` ≈ 707 vertices. Current 125 tubes ≈ 88K
  verts, one VBO, zero per-frame CPU cost.
- Full high-tier additions (Layer A fascicles + Layer B tails + Layer C crown ≈ +80-150 tubes,
  many at 60 seg = ~427 verts) add ~40-80K verts → still well under 200K in ONE draw call.
  Modern WebGL handles 1M+ verts/mesh on a 16GB box.
- The only real cost is the one-time `useMemo` rebuild (CatmullRom + Frenet frames for ~200
  curves). It runs on mount and on tier change ONLY — never per-frame. If a mount frame-hitch
  is visible in HIS browser, mitigate by chunking the build; measure first.
- Fragment risk = additive stack-up where ~200 tubes co-locate at deepCore. The sparse packet
  (90% of each wire dark per frame, carrier luma ≈0.02 « 1.0 bloom knee) bounds it, but a
  `uBurst=1` surge with coincident packets could over-brighten the root. Mitigations (all
  fragment-only, no geometry change): stagger new-wire `aPhase` (offset ~π from primaries so
  they rarely light together); tighten the packet window; or fade carrier over `vUv.x < 0.15`.
  **Measure in HIS browser before sign-off.**

---

## 3. THE ALIVE BEHAVIOR — Idle → Working → Settling Choreography

Every transition is keyed to a REAL bus event. No fabricated timers drive "work."

### 3.1 What is ALREADY built and live (do not re-build)

- **Directional flow** (knowledge up / directives down): the bus subscription
  (lines 186-197) + frame easing (lines 243-247) already drive `uFlowDir`. On
  `knowledge-acquired` packets reverse inward for 1.8s; on `agent-dispatch`/`directive`
  they return outward. LIVE.
- **Burst surge**: `WIRE_BURST_UNIFORM` is driven each frame from `burst.current.intensity`
  (line 244). Whitens + doubles packets (lines 73, 78). LIVE.
- **Hold/freeze**: `uHold` (shared `SCENE_UNIFORMS.uHold`) freezes packets mid-cable and dims
  the carrier (lines 61, 82) — the "waiting on you" approval state. LIVE.
- **Drift sync**: the group rides brainDriftX (lines 204-206). LIVE.

### 3.2 The NEW behavior worth building — the extend/grow-on-summon

The forge's pure-summon model: IDLE (brain alone) → WAKING (first real `agent-dispatch`) →
WORKING (IDE materializes AT the frozen tips) → SETTLING. The nerves already REACH the tips,
so the IDE *blooms where the nerves have always terminated*. The "organism grows nerves to
act" read is achieved by a **shader-driven progressive reveal**, not geometry animation:

   - Add a `uGrowth` uniform (0 = root-only/hidden, 1 = full). In WIRE_FRAGMENT replace the
     upper discard bound: `if (vUv.x < 0.005 || vUv.x > uGrowth) discard;` (vUv.x already runs
     root→tip; it is the same coordinate the packet flow uses, line 62). At `uGrowth=0.01` only
     the root shows; eased 0→1 over ~600ms-2s the nerve visually grows tip-forward. The packet
     stream is automatically clamped to the revealed section, so packets appear to PUSH the
     growth front to the tip, arriving exactly as the IDE blooms.
   - **Per-layer stagger (reads alive, not mechanical):** bake an `aGrowthOffset` per-vertex
     attribute (primaries 0.0; fascicles 0.15-0.25; filament tips / void-tails 0.30-0.40) and
     gate on `vUv.x > (uGrowth - aGrowthOffset)`. Trunk extends first, fascicles peel off, the
     finest filaments last — the embryological nerve-growth order.
   - **Recede on dismiss:** ease `uGrowth` 1→0 (filaments first, trunk last) — nerves retract
     into the brain after the IDE closes. (Alternative gate `vUv.x < (1.0 - uGrowth)` retracts
     toward deepCore.)
   - **uGrowth must default to 1.0** at steady state so the discard at `vUv.x > uGrowth`
     reduces to the existing `> 0.995` behavior — zero fragment-cost difference when not in transition.

   This `uGrowth` add is a WIRE_FRAGMENT change → it is a FIDELITY-gated canon edit AND must
   be mirrored into NodeLattice's verbatim copy (or guarded so the lattice keeps `>0.995`).

### 3.3 The "brain operating its tools" read — the exact causal chain (data-true)

This is the product thesis made spatial. It is NOT metaphor — one bus event drives all of it:

1. Operator types a directive → SSE stream → `step(tool_call)` →
   `publishCognition({type:'agent-dispatch', detail:'tool engaged: <tool>'})` (aiosAdapter, ~line 98-104).
2. NervousSystem subscription (line 192) sees `agent-dispatch` → flow stays outward (+1);
   `WIRE_BURST_UNIFORM` rises from `burst.current.intensity`.
3. WIRE_FRAGMENT whitens/brightens packets (lines 73, 78); they race deepCore→tip in vUv time.
4. ForgePorts `editorFlaring` fires on the SAME `isWriteEvt` (`agent-dispatch`, ForgePorts.jsx:40)
   — the editor port at (-4.8,-1.7,0) glows exactly where the packet arrives.
5. The workspace polls at 350/1500/3500ms (ForgePorts.jsx:155-157) — the file appears in the editor.

   The packet that races the wire IS the command that wrote the file. On verification,
   `tool_result [VERIFY PASS]` → `knowledge-acquired` → flow reverses inward (1.8s) and the
   preview port flares on `isRenderEvt` (ForgePorts.jsx:41) — the verdict carried back up the roots.

### 3.4 Per-bundle directional brightening — OPTIONAL, costed, deferred

A richer read ("the LEFT nerve lights for writes, the RIGHT for verification") needs per-bundle
gain. Two options:
   - **Cheap (recommended if pursued):** bake an `aBundle` attribute (0/1/2) + add
     `uBurstLeft/Right/Spinal` uniforms; the fragment selects per-bundle gain. Same single
     draw call. ~3 extra float uniforms. Routing keyed to `waveLabelForTool` (LATTICE→left,
     SIGNAL→right, CAUSAL/ARCHIVE→spinal). Lab-first, FIDELITY-gated.
   - **Forbidden:** splitting the merged geometry into 3 meshes to brighten per-bundle —
     destroys the one-draw-call idiom. Do NOT.

   This is a P3+ polish item, not core. The whole-organism burst is the accepted baseline.

### 3.5 Honest dormancy

With no backend (`linkUp=false`), the bus emits only the scene's own autonomous pulses; the
nerves tick at ambient packet trickle, void-tails carry slow currents, fascicles carry sparse
packets. NO fabricated "work" events. The organism breathes; it does not pretend to work. For
an empty data source, render the calm idle form — never invent activity.

---

## 4. INTEGRATION + FIDELITY

### 4.1 Distinct-yet-cohesive (one nervous infrastructure, not a blur)

Four systems must read as one organism with four distinct subsystems:
   - **Cortex** = breathing MASS (GLB + NeuralAura, rim/fresnel/SSS/breath, NormalBlending). In place.
   - **NodeLattice** = INTERIOR compute graph (region-colored InstancedMesh nodes + edges,
     inside the brain group, INWARD=0.85). Fires node-by-node.
   - **NervousSystem** = EXTERIOR directed conduit (dark teal carrier + cyan packets, additive),
     radiating below/outside the brain to the IDE ports. Transmits directionally.
   - **MemoryGalaxy** = orbiting discrete star Points.

   Separation axes that keep them distinct: **spatial** (cortex surface / lattice interior /
   nerves exterior-below / galaxy orbit), **motion** (pulse / node-fire / directional transmit
   / orbit), **form** (mesh / nodes+lines / tubes / points), **scale** (nerve trunk 0.07 →
   fascicle 0.02-0.03 → filament 0.003-0.005; lattice edges 0.0034, backbone 0.005). Cohesion
   axis: the **shared fiber-optic packet language** (cyan→white bead, additive) — explicitly
   mandated identical between nerve and lattice (NodeLattice.tsx:249-253).

   **The new branches must stay below the brain silhouette** (free endpoints in the -y void,
   crown fan within the inward margin) so they enrich the EXTERIOR nerve read without bleeding
   into the interior lattice. They ADD light (additive, depthWrite:false) — never occlude the cortex.

### 4.2 FIDELITY discipline (non-negotiable; per FIDELITY-IS-SACRED laws)

1. **GLB/textures untouched.** No edits to BrainModel, applyRegionVertexColors, cortex shader, SuperbrainScene.
2. **Frozen tips immutable** (§1.1). Only the last control points of port bundles are sacred;
   add geometry / add uniforms only.
3. **Canon-tag + goldens BEFORE any visual change.** Capture before-goldens of TODAY's nerve
   form in HIS browser (multiple angles, with packets flowing, and with uHold frozen).
4. **Lab-first.** Edit only `GAG demo/gag-orchestrator/src/components/canvas/NervousSystem.tsx`.
   The product copy (`frontend/src/superbrain/...`) is byte-identical and CLOBBERED by `npm run port`.
   Never edit the product copy.
5. **Two-file shader rule:** any WIRE_FRAGMENT change must be mirrored into NodeLattice's
   verbatim copy (lines 277-328) or the two visually diverge (KEEP-IN-SYNC mandate).
6. **`npm run port`, then verify in HIS browser** with after-goldens. The before/after pair is
   the sign-off artifact. WebGL cannot be verified headlessly — HIS browser is the final call.
7. **No auto-degrade.** Tier-gating drops the finest LAYERS honestly (fewer tubes), it never
   silently lowers fidelity of what is shown.
8. **uSignalGain ≥ ~2.5** must hold (bloom-knee crossing; line 222-224 comment).

### 4.3 Reduced motion

The nerve does not consume `prefers-reduced-motion` today. Add a check in the easing frame:
if reduced-motion, `uGrowth` jumps to 1.0 (no animated grow), `uFlowDir` stays +1 (no reversal),
and new-branch blooms hold at idle. The low-frequency packet trickle may stay (non-vestibular).
`uHold` freeze already respects this implicitly.

### 4.4 Perf gating

Add `tier?: QualityTier` to props (line 171-177) and to the `mergedGeometry` useMemo deps
(currently `[tabX]`, line 386) so branch/tail/crown counts rebuild on tier change. Follow the
established budget idiom (SATELLITES_PER_HUB pattern, NodeLattice.tsx:86): e.g.
`FASCICLES_PER_BUNDLE {high:4, medium:2, low:0}`, `ROOT_TAILS {high:30, medium:12, low:0}`,
`CROWN {high:12, medium:6, low:0}`. Low tier = today's exact 125-tube form (honest dormancy).

---

## 5. PHASED BUILD PLAN (importance-ranked)

Each phase: what it adds · FIDELITY gate · lab-first vs canon · riskiest/blind step.
**[FORGE-PAIRED]** marks phases that pair with the forge pure-summon work (its "P1").

### P0 — Tier prop + before-goldens + canon tag (PREREQUISITE, no visual change)
- **Adds:** `tier` prop + useMemo dep; capture today's before-goldens in HIS browser; git canon tag.
- **Gate:** none (no visual change) — but the goldens ARE the gate for everything after.
- **Lab/canon:** lab-only plumbing; zero rendered change.
- **Blind step:** confirming the ported product copy is byte-identical so goldens are valid.

### P1 — Convergent secondary fascicles (Layer A) — THE FORM UPGRADE
- **Adds:** finer convergent fascicles per primary bundle, terminating at the SAME frozen tips;
  the first real "branching nerve tree" read. Tier-gated.
- **Gate:** full FIDELITY (new rendered geometry) — canon tag, before/after goldens, HIS sign-off.
- **Lab/canon:** lab-first → port → HIS browser. Canon visual change.
- **Riskiest/blind:** CatmullRom overshoot/kinks on new arcs (line 320-322 risk lever applies);
  additive stack-up at the root under burst. Rollback is clean (remove the addWireBundle calls).

### P2 — Cosmic root-tails (Layer B) + crown fan (Layer C) — organic density
- **Adds:** void-tails into the -y space and the brainstem crown — the dense fractal periphery
  + tree crown of the reference. Tier-gated; honest dormancy at low.
- **Gate:** full FIDELITY. Watch the "reads as decoration not anatomy" risk — mitigate by
  binding them to the SAME real bus packets (they already would, via the shared material).
- **Lab/canon:** lab-first → port → HIS browser. Canon visual change.
- **Riskiest/blind:** crown wires bleeding into the interior lattice read (keep within INWARD margin);
  tail endpoints reading as MemoryGalaxy stars (form differs — tubes vs points — but verify in browser).

### P3 — Extend/grow-on-summon (`uGrowth` + `aGrowthOffset`) — **[FORGE-PAIRED]**
- **Adds:** the alive idle→working extension: nerves grow tip-forward as the IDE materializes,
  retract on dismiss; per-layer stagger. This is the headline alive behavior.
- **Gate:** full FIDELITY (WIRE_FRAGMENT change) + **mirror into NodeLattice's copy** (or guard
  it). Reduced-motion path required (jump to 1.0). Must default to 1.0 at steady state.
- **Lab/canon:** lab-first → port → HIS browser. Canon shader change (two files).
- **Riskiest/blind:** the grow timing vs the forge's IDE-bloom timing — they must feel
  choreographed in HIS browser; the easing curve is the tuning lever, not a hardcoded constant.
  Pairs directly with the forge summon state machine (its WAKING→WORKING transition fires the grow).

### P4 — Per-bundle directional brightening (`aBundle` + per-bundle burst) — POLISH (optional)
- **Adds:** "the correct nerve lights for the work" (LATTICE→left write port, SIGNAL→right verify port).
- **Gate:** full FIDELITY. Routing keyed to `waveLabelForTool`. Confirm no `Math.random`.
- **Lab/canon:** lab-first → port → HIS browser.
- **Riskiest/blind:** whether per-bundle brightening reads as intentional vs noisy — HIS call.
  Forbidden alternative (3-mesh split) must NOT be used.

> **Pairing note:** P3 is the explicit forge-paired phase (the nerve extension complements the
> IDE summon). P1/P2 are independent form work that can land before or alongside the forge.

---

## 6. RISKS + MITIGATIONS · TOP RECOMMENDATION · OPEN QUESTIONS

### 6.1 Risks + mitigations
- **R1 — Moving a frozen tip (CRITICAL, broke a past integration).** Mitigation: only ever add
  NEW addWireBundle calls; convergent fascicles reuse the IDENTICAL frozen vector as last point;
  never edit lines 340/357/373, 257/258, 212. In-browser confirm the primaries still reach the ports.
- **R2 — Additive stack-up at deepCore under burst (~200 coincident tubes).** Mitigation:
  fragment-only — stagger new-wire aPhase (~π offset), tighten packet window, fade carrier
  over vUv.x<0.15. Measure in HIS browser.
- **R3 — CatmullRom kinks on new arcs.** Mitigation: the in-code risk lever (drop rootPinch);
  test each new path; clean rollback by removing calls.
- **R4 — WIRE_FRAGMENT drift from NodeLattice's verbatim copy.** Mitigation: treat any shader
  change as a two-file edit; mirror or guard `uGrowth`.
- **R5 — Branches read as decoration / blur with lattice or galaxy.** Mitigation: bind to real
  bus packets; keep crown within INWARD=0.85; keep nerves exterior-below; verify the 4-system
  read in HIS browser.
- **R6 — Mount frame-hitch from ~200-curve useMemo rebuild.** Mitigation: it's mount/tier-change
  only; chunk the build if a hitch is visible. Measure first.
- **R7 — Drift formula divergence from BrainModel.** Mitigation: re-verify lines 204-206 mirror
  brainDriftX whenever BrainModel's drift changes (not elevated by this work, but a standing tie).

### 6.2 TOP RECOMMENDATION
Build **P0 then P1 (convergent secondary fascicles) first.** P1 is the single highest-value,
lowest-risk move: it delivers the actual "alive branching nerve tree" form using the exact
proven `addWireBundle`/`mergeGeometries` idiom, never touches a frozen tip (fibers converge TO
the existing tips), stays one draw call, and is cleanly reversible. Land P0+P1, get HIS browser
sign-off, THEN layer P2 density and P3 the forge-paired grow. P3 is the headline "alive"
behavior but it is a two-file shader change — sequence it after the form is signed off so the
grow is tuned against a settled tree.

### 6.3 Open questions for the operator
1. **Convergence vs divergence:** do you want the fascicles to *converge to the existing tips*
   (anatomically the cord, keeps tips sacred — my recommendation), or also have *free-ended*
   branches fanning past the tips into space? (The latter is fine geometrically — they just
   carry no port.)
2. **Grow direction on dismiss:** retract toward the brain (nerves recede into deepCore) or fade
   at the tips? Both are one-line gate choices.
3. **Per-bundle brightening (P4):** worth the extra `aBundle` attribute + 3 uniforms, or is the
   whole-organism burst enough? (Your eye, in browser.)
4. **Void-tail count at high tier (30?):** how dense should the "roots into the knowledge void"
   read — sparse and elegant, or a thick fractal mat?
5. **Should the crown fan exist at all,** or does it risk competing with the interior NodeLattice?
6. **Reduced-motion:** keep the low-frequency idle packet trickle on, or freeze fully?

---

**Final reminder: the final aesthetic call is the OPERATOR'S BROWSER.** All numbers above are
reasoned from the live code, not measured; WebGL cannot be verified headlessly; canon-tag +
goldens + HIS sign-off gate every visual phase.
