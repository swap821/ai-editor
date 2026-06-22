# WORKING-BRAIN CANON RESEARCH — Master Roadmap

**Demo → actual working virtual computer brain.** The whole canon (every layer of the
superbrain 3D scene) AND its tools (agentic tool-use + the workspace forge it acts in).

- Chief Architect synthesis of 6 mapping lenses + the adversarial Corrections Ledger.
- Verified against the live lab tree on **2026-06-15**. Research/plan only — NO code edited, NO builds run.
- North star (operator, his words): *"an autonomous AI-OS superbrain travelling constant into the deep-vast knowledgeable infinite space."* The brain never stops voyaging.
- The look (his "AI tree-brain" reference: cosmic cortex, glowing compute-node lattice, tree roots into cosmic space, constellation feel) is the **SKIN**. The substance is that everything shown is something the AI-OS actually **IS or DOES** — **DATA-TRUE, never decoration.**
- **The final aesthetic call is the OPERATOR'S BROWSER. WebGL cannot be verified headlessly.** Every claim here is lab-research; sign-off happens in his browser.

---

## 1. VERIFICATION LEDGER (carry these corrections; never repeat a flagged fabrication)

This is the authoritative TRUE-state. The adversarial verifier caught real fabrications in the
lenses. Where a lens claimed something the live tree refutes, the live tree wins. Every line below
is file:line-anchored against the live tree (re-confirmed this session where marked ✔).

### 1.1 The fabrications to REJECT outright (do NOT let these re-enter any synthesis)

- **❌ "Cosmic gradient cortex (GRAD_CROWN #19d4f0 → GRAD_MID #6a3bff → GRAD_BASE #e62bd4)."**
  FALSE. Lens 1 and Lens 6 both asserted this; it does not exist. The cortex bake is
  `applyRegionVertexColors` (NOT `applyCortexVertexColors`), and it bakes **per-lobe anatomical
  region colors**, not a vertical gradient. ✔ Confirmed `SuperbrainScene.tsx:238-245`:
  `REGION_FRONTAL_CORE #ff3b28`, `REGION_FRONTAL_EDGE #ff7a26`, `REGION_PARIETAL #19d4f0`,
  `REGION_TEMPORAL #36f07a`, `REGION_TEMPORAL_LIME #a8e62b`, `REGION_OCCIPITAL #9b3bff`,
  `REGION_OCCIPITAL_HOT #e62bd4`, `REGION_CEREBELLUM #6a35ff`. There are NO `GRAD_*` constants.
  **Implication for this plan:** the cortex shell already carries per-lobe anatomy. The
  operator's session note ("cortex re-baked to the cosmic gradient") describes intent; the live
  bake is anatomical per-lobe. The roadmap treats the cortex as **per-lobe anatomical**, and the
  "cosmic skin" reading is delivered by the additive layers around/inside it (lattice, aura,
  horizon, nervous roots), NOT by a non-existent gradient constant. Any cortex color change is a
  canon-RED visual edit requiring his explicit sign-off (see §5).

- **❌ "The per-lobe color moved to the lattice; the shell is now the cosmic canvas (comment at :241-244)."**
  FALSE — no such comment exists. ✔ Lines 238-245 are bare region-color definitions. Interpretive
  narrative only; do not cite it as code evidence.

- **❌ "TrailRow.superseded_by is available in the frontend."** FALSE for the TS interface.
  The `TrailRow` shape exposed to scene components does NOT carry `superseded_by`
  (`aiosAdapter.ts:496-507`). `TrailMapResponse.summary` carries an aggregate superseded count
  (`:509-512`), and the backend `trail_map()` DOES compute `superseded_by` server-side
  (`skills.py`). **So Lens 6's "superseded ghost star with lineage edge" and Lens 2's "P5 G2 lineage
  arrows" require a BACKEND payload change (add the FK to the per-row trail payload) before any
  frontend lineage rendering. Until then: render nothing for lineage.**

- **❌ "Lens 1 PostFX GradePre/GradePost pass names verified."** UNVERIFIED. PostFX.tsx was not
  read against the live tree in the lens pass. The PostFX upgrade (live grade uniforms) is real in
  *concept* but its exact pass/uniform names must be re-read from `PostFX.tsx` before any work.
  Treat PostFX internals as unverified.

- **❌ "5 wave anchors" / "5 wave slots" / "uWaveOrigins length 5."** FALSE.
  ✔ `WAVE_REGION_ANCHORS` has exactly **4** anchors (`SuperbrainScene.tsx:469-476`):
  `SIGNAL|TITAN`→occipital, `ARCHIVE|MYTHOS|MEMORY`→temporal, `CAUSAL|GRAPH|DELTA`→frontal,
  `SEMANTIC|LATTICE`→parietal crown. There is NO cerebellum anchor and NO ROUTER anchor in the
  array. `uWaveOrigins`/`uWaveTimes` are **3-slot** arrays (`:170-174`); the synapse storm uses
  `.slice(0,3)` (`:1083`). Never wire 4 or 5 simultaneous cortex waves.

- **❌ "11 (or 14) cognition bus event types."** FALSE.
  ✔ `cognitionBus.ts:13-41` defines exactly **10** named `CognitionEventType`s:
  `knowledge-acquired, directive, burst, agent-dispatch, synthesis, approval-required,
  approval-resolved, telemetry, route, voice-speaking`. Any synthesis must use 10.
  `human_required` and `earned_autonomy` are **SSE frame names, NOT bus types** — the adapter
  translates `human_required → approval-required` (`aiosAdapter.ts:262-265`) and
  `earned_autonomy → knowledge-acquired` label `AUTONOMOUS ACTION` (`:305-316`). **Do NOT add new
  bus types without explicit operator approval — the 10-type union is the contract.**

### 1.2 The real cognition-event + SSE-frame surface (the data the brain actually emits)

The brain's full real signal vocabulary, for binding every canon area. Cited from Lens 6 (the
ground-truth inventory) and re-confirmed at the bus.

- **The 10 bus types** are above. The single highest-meaning event is `approval-required` /
  `approval-resolved` — *a supervised mind visibly deferring to its operator* (the product thesis).
- **Real SSE frames** from `POST /api/generate` → bus translation (`aiosAdapter.ts:93-149, 254-356`):
  - `step(tool_call)` → `agent-dispatch`, label=TOOL, `detail: "tool engaged: <tool>"`, intensity 0.8
  - `step(tool_blocked)` → `agent-dispatch`, label `<TOOL> BLOCKED`, intensity 0.4
  - `step(tool_result, verify)` → `knowledge-acquired`, label `VERIFICATION GREEN`/`RED`, intensity 1
  - `step(tool_result, swarm|role_pass)` → `agent-dispatch`, `detail: "<role> caste online"`, intensity 0.5
  - `step(tool_result, other)` → `knowledge-acquired`, label=TOOL, intensity 0.6
  - pre-loop recall: `query_knowledge`, `reflect`, `query_skills` → `knowledge-acquired`
  - `code` → `knowledge-acquired` label `CODE EMITTED` — **the code string is DISCARDED after building the detail** (`aiosAdapter.ts:273-287`); to surface real code, store `frame.data.code` to a module var (same idiom as `knownTrails`, `lastTelemetry`, `pendingApproval`)
  - `alignment` → `agent-dispatch` label `INTENT …` (only if intent present)
  - `earned_autonomy` → `knowledge-acquired` label `AUTONOMOUS ACTION`, intensity 1
  - `error` → `synthesis` label `COGNITION FAULT`; `done` → `synthesis` label `SYNTHESIS COMPLETE`
  - `human_required` → `approval-required` + persists `PendingApproval{content, diff, filepath, command, …}`
  - `route` → `route` bus event `{provider, model, privacy, task, auto}`
- **Poll-derived events** (every 20 s, `aiosAdapter.ts`): trail reinforced → `knowledge-acquired`
  `detail: "trail #<id> reinforced — strength <x>"` (`:658`); skill mastered → `knowledge-acquired`
  label `SKILL MASTERED — TRAIL #<id>` (`:676`); trail weakened → `agent-dispatch` label
  `TRAIL WEAKENED` (`:689`, a real event NO lens described); autonomy graduation → `knowledge-acquired`
  label `CAPABILITY EARNED` (`:737-743`); telemetry snapshot → `telemetry`; audit chain broken →
  `synthesis` label `AUDIT CHAIN BROKEN`.
- **Voice:** TTS start → `voice-speaking` intensity 0.5; word-boundary → `voice-speaking` 0.32
  (`SuperbrainHUD.tsx`). Voice is a DIRECTIVE channel only — a spoken word can NEVER redeem an
  approval token.

### 1.3 The real backend capabilities (what the brain actually IS / DOES)

- **8 real tools** (`tool_agent.py`): `read_file`, `read_directory` (GREEN); `execute_terminal`
  (GREEN/YELLOW/RED-gated); `edit_file`, `create_file` (YELLOW, force auto-verify after);
  `verify` (GREEN); `plan` (GREEN, advisory, 0.72 confidence gate); `self_analyze` (GREEN, T0/T1
  read-only); `propose_fixes` (T2, read-only, never applies). **There is NO web_search / fetch_url
  tool.** The `web|fetch|grep|inspect` arm in `waveLabelForTool` (`SuperbrainScene.tsx:493`) is
  **real-but-dead-code** — it can only fire if a tool with that name is dispatched, and none exists.
  It is NOT evidence that web tools are real. ✔ Confirmed live at :493.
- **Castes:** role_pass = PLANNER{read,readdir,plan} / CODER{full write} / REVIEWER{read,readdir,verify}.
  swarm = DECOMPOSER / WORKER-N / SYNTHESIZER. Each leg emits a `caste online` agent-dispatch.
- **Multi-LLM router:** OLLAMA(local) / BEDROCK(cloud) / GEMINI(cloud); local-first by default
  (`ROUTER_CLOUD_TASKS` empty); failover cascade; `route` SSE frame emitted lazily.
- **5 memory layers (SQLite):** L2 episodic, L3 semantic (FAISS+BM25+decay), L3b approved facts
  (`facts.py` — **flat single-hop queries only; NO graph traversal — the G2 GAP is REAL**),
  L4 mistakes, L5 skills/trails (pheromone: `strength = success_rate · freshness · reuse_factor`).
- **Pheromone trails API:** `GET /api/v1/development/trails` → full `TrailRow[]`. `getKnownTrails()`
  exposes the live array (`aiosAdapter.ts:574`). Quarantine = verified trail demoted on net reuse failures.
- **Earned-autonomy ledger:** probation → earned (min verified streak) → revoked (one verified
  failure, instant). When earned, write tools bypass the human pause and emit `earned_autonomy`.
- **Audit hash-chain:** `GET /api/v1/audit/verify` → `{valid, total_entries}`. RED zone always blocked.
- **Other bindable endpoints:** `development/workspace` (forge files), `development/curriculum`
  (unlock DAG), `development/metrics`, `development/autonomy`, `memory/search`, `alignment/evaluation`.

### 1.4 Frozen / untouchable constraints (confirmed live)

- **GLB `/models/brain.glb` + textures: UNTOUCHED.** `BrainModel` `useGLTF('/models/brain.glb')`.
- **Frozen nervous-system tips:** ✔ `leftTargetX=-4.8`, `rightTargetX=+4.8` (`NervousSystem.tsx:234-235`),
  spinal tip `(0,-2.6,1.5)` (`:350`), `tabX=4.82` (`:194`). Left tip `(-4.8,-1.7,0)`,
  right tip `(+4.8,-1.5,0)`. **Only ADD geometry / change shader uniforms BEFORE these tips —
  never move them** (re-projecting them broke a past integration).
- **`uFlowDir` is scaffolded but INERT.** ✔ `WIRE_FLOW_DIR = { value: 1 }` (`NervousSystem.tsx:97`),
  multiplied into `flowTime` in the shader, wired into the material — but nothing drives it to −1.
- **SCENE_UNIFORMS is the single writer.** Children are readers only; a child-specific uniform must
  be module-level in that child (idiom: `WIRE_BURST_UNIFORM`, `WIRE_FLOW_DIR`).
- **Energy-not-matter identity:** near-black carrier + AdditiveBlending + depthWrite:false. The
  bloom knee is `luminanceThreshold ≈ 1.0`; a signal must reach `uSignalGain ≥ ~2.5` to glow.
- **Security spine is RED/untouchable; no secret persistence; voice is directive-only.**

---

## 2. THE THESIS — what "working computer brain (not demo)" means concretely

Today the canon is an **architecturally sound, partially-bound organism**: the most data-true
elements (CorticalSignals waves, AccretionCore feeding, MemoryGalaxy stars, NervousSystem
burst+hold, RegionPins metrics, NodeLattice topology) are correctly placed INSIDE/ON the brain,
and the atmosphere layers (CosmicBackground, KnowledgeHorizon, NeuralAura, PostFX) are correctly
ambient. But three things keep it reading as a *demo*: (1) the interior lattice is a **static**
skeleton — it has the right shape but does not yet fire on real events; (2) the nervous roots carry
a real *burst* and *hold* but the **directional meaning is inert** (everything flows outward, always);
(3) the brain has no visible **forge** — the slot where its create/edit/verify tool-use becomes real
file changes is empty.

A *working computer brain* means every region reads as ONE data-true machine in motion:

- **Cortex (the mind / skin).** Per-lobe anatomical shell. Already shows `uHold` (amber on a real
  approval pause) and `uTime` (alive). It is the perceptual *background*; its only honest deepening
  is the broadest behavioral states (hold; local-vs-cloud voyage) — never per-tool clutter.
- **Interior lattice (the compute).** The 5 hubs ARE the real tool-routing anatomy. Working = each
  hub **fires when its kind of work actually runs** (PLANNER→CAUSAL, read→ARCHIVE, create/edit/
  verify→LATTICE, route/security→SIGNAL, provider pick→ROUTER), and real **trails become live
  interior nodes** (brightness=strength, size=walks, red=quarantine).
- **Nervous roots (the I/O).** The three bundles ARE the tool-ports (editor / preview / command).
  Working = packets **carry real direction** — knowledge UP on intake, directives DOWN on command —
  and the form reads as **tree-roots + cosmic roots** drawing from the knowledge void it voyages
  through. Frozen tips untouched.
- **Memory / recall (the library + the act).** MemoryGalaxy = the persistent skill-field
  (constellation of all trails). CognitiveGrasp = the retrieval ACT (packets flying from the field
  into the cortex). Working = grasp fires on the **actual** recall event, not a wall-clock cycle;
  the galaxy shows maturity (verified vs candidate), freshness, mastery flashes.
- **The brain's TOOLS (agentic tool-use + the forge).** Working = the lattice/cortex/nerves
  visualize each real tool dispatch *and* the **forge** fills the empty `WorkspaceCanvas` children
  slot — an editor showing the brain's ACTUAL proposed write (`pendingApproval.content/diff`), a
  terminal showing real `execute_terminal`/`verify` output, a verdict surface showing PASS/FAIL.
- **The voyage.** Perpetual. The hold dilates it (the cosmos holds its breath for a real pending
  decision); activity can accelerate the drift. It never stops, never goes dark.

The unifying rule: **DATA-TRUE or render nothing.** Where a data source does not exist (graph
traversal, superseded FK in the row payload), the plan says *render nothing* until the backend
provides it.

---

## 3. PER-AREA PLANS

Template per area: (a) shows now · (b) real vs demo · (c) working-brain upgrade · (d) tools tie ·
(e) risks/perf/dormancy. NodeLattice phases defer to `NODE_BRAIN_RESEARCH.md` (not duplicated).

### 3.1 Cortex shell — BrainModel + applyRegionVertexColors  [ambient skin; deepen, don't clutter]

- **(a)** GLB cortex + casing clone. `onBeforeCompile` injects ONLY `uTime` + `uHold` into the
  cortex shader (`SuperbrainScene.tsx:653-654`); casing shader reads `uTime`+`uHold`
  (`:582-583`), cyan→amber on hold (`:595`). Per-lobe region colors baked CPU-side
  (`applyRegionVertexColors`, `:312`). Animated Voronoi web (27-cell loop; 2 octaves high-tier).
- **(b)** REAL: `uHold` (approval amber), `uTime` (alive). DEMO/ambient (correctly): the region
  colors as a static skin, the iridescence cycle, the Voronoi texture, cavity AO.
- **(c)** Two additive deepenings, both flagged as **canon-RED visual** (his sign-off): (1) inject
  `uBurst` — **already computed in SCENE_UNIFORMS (`:167`) but NOT plumbed into the cortex shader**
  — as a mild rim emissive boost during a real burst (patch `onBeforeCompile` + update
  `customProgramCacheKey` at `:808`). (2) add a `uCloudRoute` leaf (0 local / 1 cloud) driven by the
  real `route` event, blended faintly into the casing iridescence — "knowledge leaving the machine"
  on the shell. Keep the cortex MINIMAL; no per-tool events on the shell.
- **(d)** The cortex is the skin, not the action surface. Tool detail belongs in the lattice.
- **(e)** Voronoi is the heaviest fragment cost; tier gate already correct (frozen on low). Risk:
  `customProgramCacheKey` rebuild on mid-session tier change (already handled). Dormancy: the skin
  is always-on (correct — no data source to go dormant against).

### 3.2 NeuralAura  [most data-true atmosphere; narrow targeted adds]

- **(a)** membrane + nucleus shells + 50 orbiting sparks; reads `uBreath`/`uBurst`; mode-reactive
  spark color (observe/synthesize/orchestrate); hold-amber lerp.
- **(b)** REAL: mode color, `uHold` amber, `uBreath`/`uBurst` (indirectly data-driven), activity→
  spark size. DEMO/ambient: orbit geometry, spark count, `aTint` variety.
- **(c)** Wire the existing `voice-speaking` bus event to a `voicePulseRef` that briefly lifts
  membrane alpha (warmer/breathier than a thinking pulse) — one ref, one subscriber, no new uniform.
  Add a spark-count tier gate (high 50 / med 30 / low 15) for consistency.
- **(d)** Keep aura at mode-level granularity; leave caste detail to the lattice.
- **(e)** Cheap (memoized clones). Dormancy: always-on ambient (correct — "the brain exists").

### 3.3 CorticalSignals  [cleanest data-binding in the scene]

- **(a)** ~320 surface fireflies, colored by the baked region vertex color; blink biased by the
  shared thought-wave GLSL so synapses fire WHERE a wavefront passes (3-slot waves). Tier 320/180/80.
- **(b)** REAL: wave-biased blinking (waves are queued by real `agent-dispatch`/`knowledge-acquired`/
  `burst`), `uActivity` fire rate. DEMO/ambient: static positions, speed/size variety.
- **(c)** Optional polish (lower priority): a per-lobe **flash-color override** when a wavefront
  passes — at rest the synapse shows the shell color, on a wave it reveals the anatomical lobe color
  (FRONTAL #ff3b28 / PARIETAL #19d4f0 / TEMPORAL #36f07a / OCCIPITAL #9b3bff). Requires a second
  baked attribute; additive. Makes "which lobe a tool activated" legible.
- **(d)** Direct: `waveLabelForTool` → anchor → `uWaveOrigins` biases the synapses at that lobe.
- **(e)** ~960 Gaussian evals/frame at high tier — cheap. Honest baseline fire even with no waves.

### 3.4 AccretionCore  [knowledge ingestion; deepen the metaphor]

- **(a)** 820-particle infall disk; subscribes to `knowledge-acquired` → 1.2 s feeding pulse;
  `uBurst` spins/brightens; `uActivity` scales.
- **(b)** REAL: `knowledge-acquired` feeding pulse, `uBurst`, activity. DEMO/ambient: the 4 tint
  colors, infall geometry, fixed disk position/tilt.
- **(c)** Map the 4 existing tints to the 4 real knowledge types by parsing the event label in the
  existing subscriber: `trail #N reinforced`→amber, `VERIFICATION GREEN`→cyan, mistake/RED→rose,
  semantic→violet. One `uKnowledgeTint` uniform biasing toward the matched category for 1.2 s. Zero
  new backend signals (label already carried).
- **(d)** AccretionCore = ingestion; tool execution belongs to cortex waves. Keep `knowledge-acquired`
  as the only binding; do NOT add `agent-dispatch` here.
- **(e)** Uniform-only updates; stable. Dormancy: neutral pulse=1 at idle (correct — the universe
  feeds the brain even when idle).

### 3.5 CosmicBackground  [the voyage field; hold dilation is the key signal]

- **(a)** glyph-star streamfield; gravitational pull dissolves stars near the core; subscribes to
  `approval-required` → voyage time dilates to ~0.3×, eases back on resolve/directive/synthesis.
- **(b)** REAL and *critical*: hold → voyage dilation ("the cosmos holds its breath" for a real
  pending decision). DEMO/ambient: glyph types, star field, gravitational pull.
- **(c)** Low priority: on `knowledge-acquired`, flash the nearest absorbing star the
  knowledge-domain color (reuse `waveLabelForTool` routing); drift speed ∝ activity. The hold
  dilation already carries the most important behavioral state.
- **(d)** It is the infinite field, not the tooling. Only tool-adjacent add: absorbed-star domain color.
- **(e)** Largest vertex submission (tier 2800/1400/600). Dormancy: the field always flies (correct).

### 3.6 KnowledgeHorizon  [deep-space dome; keep ambient]

- **(a)** radius-90 dome, procedural nebula + photographic stars + volumetric depth (tier-gated) +
  parallax; `uReducedMotion` honored.
- **(b)** REAL: `uActivity` very-minor opacity bias (~3%), pointer parallax. DEMO/ambient
  (correctly): the entire nebula/stars/dust.
- **(c)** Tie drift speed to activity (`0.0006 + uActivity·0.0004`) — voyage faster when thinking.
  Keep the palette static. If a cloud-route tint is wanted, it lives HERE (faint violet far-edge)
  rather than on the cortex. **Re-read PostFX/horizon shader names before any work — unverified.**
- **(d)** None directly (correct).
- **(e)** Heaviest per-fragment cost on high tier (4-octave volumetric); tier gate is the
  mitigation. On the 16 GB box this dome is the largest atmospheric GPU risk. Dormancy: always-on.

### 3.7 PostFX  [whole-frame grade; highest "wow-per-effort" but UNVERIFIED internals]

- **(a)** EffectComposer: Bloom (knee 1.0) → CA → GradePre → AgX ToneMap → GradePost → Vignette →
  Noise. **NOTE: pass/uniform names from Lens 1 are UNVERIFIED — read `PostFX.tsx` first.**
- **(b)** Fully decorative today (constants from `constants.ts`; no live signal input).
- **(c)** Make the GradePost shadow/high tint + vibrance uniforms LIVE and drive them from the bus:
  `uHold`→amber highlights ("golden pause"); VERIFY GREEN/burst→momentary vibrance spike (the
  verified-success moment = the most saturated frame the operator ever sees); observe→cooler;
  synthesize→warmer. Whole-frame character responds to behavioral state. Additive (mutate an Effect
  instance held in a ref); no new pass.
- **(d)** Whole-frame level only: hold / burst-verify / mode. NEVER per-`agent-dispatch` (would strobe).
- **(e)** No extra pass cost. Dormancy: uniforms rest at defaults. **Blind step — verify internals.**

### 3.8 NodeLattice (interior compute) — FIRST-CLASS WORKSTREAM  [defer phases to NODE_BRAIN_RESEARCH.md]

- **(a)** P1 LIVE: 3 draw calls — InstancedMesh nodes (high 125 / med 85 / low 20), LineSegments
  edges (packet shader, ShaderMaterial), merged TubeGeometry backbone ROUTER→4 hubs. 5 hubs = 4
  real anchors + 1 `authored:true` ROUTER (✔ `NodeLattice.tsx:74-81`). 15% inward clamp; seeded;
  energy-not-matter; pure SCENE_UNIFORMS consumer (no bus subscription).
- **(b)** Data-true at the STRUCTURAL level (hubs ARE the routing anchors; colors match the brain
  palette; packets freeze on `uHold`; `uBurst` whitens all). DEMO at the per-node level (satellites
  + edge weights are seeded-random placeholder). This is the correct, honest P1 stance.
- **(c) Phased (per NODE_BRAIN_RESEARCH.md):**
  - **P2 — cognition-bus wiring (highest near-term leverage).** One `subscribeCognition` in the
    component. `agent-dispatch (tool engaged)` → resolve `waveLabelForTool(tool)` → flash that hub.
    `route` → flash ROUTER (+ optional 3 authored provider sub-nodes OLLAMA/BEDROCK/GEMINI).
    `knowledge-acquired (trail #N)` → flash the trail's hub. Per-node firing via an
    `aFireTime` InstancedBufferAttribute + `uNow`, `exp`-decay (the MemoryGalaxy flash idiom) —
    NOT the doc's "32-slot ephemeral edge pool" for node firing. Crosses static→data-true.
  - **P3 — live trail nodes** from `getKnownTrails()` on `telemetry` events. Position by
    `waveLabelForTool(goal_pattern)`; brightness=strength; size∝walks; quarantine=red. Use the
    `slotById` stable-assignment idiom (R3). Dormancy: empty trails → zero trail nodes, but KEEP the
    structural hub skeleton (unlike MemoryGalaxy which returns null).
  - **P4 — G1 knowledge-graph traversal (the one phase that creates NEW backend capability).**
    `facts.py` has only flat single-hop queries — **the G2 GAP is REAL.** Add a backend
    `traverse(start, max_depth≤3)` recursive-CTE with cycle guard + a thin route, then light the
    2-hop neighborhood on click. Backend change required; gate behind operator sign-off of P2.
  - **P5 — observability projections** (curriculum unlock DAG; router calibration edge weights).
    **G2 superseded lineage requires the backend to add `superseded_by` to the per-row trail
    payload first (see §1.1) — until then render nothing for lineage.**
- **(d)** The lattice IS the live map of tool engagement: each tool routes through `waveLabelForTool`
  to its hub; castes activate at the anatomically correct hub; P4 traversal is a genuine new tool.
- **(e)** 3 draw calls, memoized, `frustumCulled=false`. Bloom knee keeps idle nodes dark
  (`uNodeGain 0.7`); only fired nodes cross. Dormancy as above. **Corrections folded:** doc's
  `onBeforeCompile`/`customProgramCacheKey` guidance is INAPPLICABLE (live uses ShaderMaterial);
  doc's "11 events" → 10; doc's geometry-radius/ephemeral-pool details superseded by live P1.

### 3.9 NervousSystem (roots-as-real-I/O) — FIRST-CLASS WORKSTREAM  [form + directional data-true signal + cosmic roots]

- **(a)** 115-tube braided cable-tree, 3 bundles sharing a brainstem origin → 3 frozen UI-port
  tips, ONE merged-geometry draw call. Fiber-optic packet shader with `uBurst`, `uHold`,
  and the inert `uFlowDir`. Mounted OUTSIDE `<Float>` (so tips stay screen-stable). No tier prop,
  no bus subscriber yet (the `subscribeCognition` import is dormant).
- **(b)** REAL: `uBurst` (real tool-engaged events), `uHold` (real approval freeze — packets freeze
  mid-cable), `uTime`, region-correlated tints. DEMO: `uFlowDir=+1` always (the single most
  semantically important feature is inert); the form reads as cables, not roots; no per-bundle
  semantic live binding.
- **(c) Two independent tracks (per Lens 3 build sequence):**
  - **SIGNAL track (pure data-truth, no geometry/shader change).** Add `WIRE_FLOW_TARGET={value:1}`;
    a `subscribeCognition` (the import exists at `:6`) maps the 10 bus events to ±1 intent; ease
    `WIRE_FLOW_DIR` toward it in the existing `useFrame` (`MathUtils.damp`, ~2.5-3.0). Mapping:
    **UP (−1, knowledge in):** `knowledge-acquired` (trail reinforced / `SKILL MASTERED` /
    `CAPABILITY EARNED` / QUERY_KNOWLEDGE / REFLECT / QUERY_SKILLS / CODE EMITTED), `telemetry`
    (link refresh), `synthesis` (link established). **DOWN (+1, directive out):** `directive`,
    `agent-dispatch` (tool engaged / caste online), `AUTONOMOUS ACTION`, `VERIFICATION GREEN`/`RED`,
    `approval-resolved (approved)`. **HOLD:** `approval-required` — no change; `uHold` already zeros
    `flowTime` (`(1.0-uHold)`), so direction naturally freezes (elegant; no extra shader code).
    Idle default returns to +1. This is the operator-chosen "roots as real I/O (hybrid)" directional signal.
  - **FORM track (additive geometry; frozen tips untouched).** Add a 4th category of "cosmic root-tail"
    wires that share the brainstem to `spinalDrop(0,-1.2,-0.4)` then fan DOWNWARD into the void
    (free-space endpoints ~y −3 to −5, NO UI port, NOT frozen), tapering to near-zero (SPINAL_TINT).
    Add deeper-droop intermediate control points to the main bundles so the divergence reads as
    roots spreading — **only points BEFORE the frozen tips change.** Tier-gate the tails
    (high 30 / med 12 / low 0 = honest dormancy). Absorbed into the same single draw call.
- **(d)** The NervousSystem IS the tool interface as physical wiring: left tip = editor/write port,
  right tip = preview/results port, spinal tip = command bar. Direction makes intake-vs-command
  legible at the whole-organism level. (Per-bundle direction = a deferred future phase; would split
  the merged geometry into 3 draw calls — not worth the perf cost on the 16 GB box.)
- **(e)** Merged geometry → tails are free at render time (one draw call). Needs a `tier` prop added
  (same gap as NodeLattice, per NODE_BRAIN_RESEARCH correction #5); add `tier` to the `useMemo`
  deps so tail count rebuilds on tier change. Risks: CatmullRom kinks (rollback = remove the new
  intermediate points; established idiom); `mergeGeometries([])` null on low (guard: main bundles
  always present). Additive stack-up bounded by the existing sparse packet (~10% lit).

### 3.10 MemoryGalaxy  [near-fully data-true persistent skill-field]

- **(a)** ≤128 orbiting stars, one per trail; 9 attributes bind strength/walks/quarantine/flash.
  Honest dormancy `if (starCount===0) return null`. Flash on `/trail #(\d+)/` against `event.detail`.
- **(b)** FULLY data-true end-to-end (all from real `TrailRow`). No structural demo.
- **(c)** (1) `aStatus` attribute: dim candidate vs bright verified (`status` already in row).
  (2) Blend `freshness` into `aHeight` (fresh orbits high, stale drifts low). (3) Add a mastery-flash
  branch `/TRAIL #(\d+)/i` against `event.label` (the `SKILL MASTERED` label is NOT in `detail`).
  (4) Superseded ghost stars — **BLOCKED on the backend adding `superseded_by` to the row payload
  (§1.1); render nothing until then.**
- **(d)** Each star IS a learned tool-workflow; size = successful uses; quarantine-red = harmful learned behavior.
- **(e)** One Points draw call, ~4.5 KB attributes — negligible. Dormancy gold.

### 3.11 CognitiveGrasp  [the retrieval ACT; close the clock-vs-event gap]

- **(a)** 4 authored deep-space glint targets, 6 s/slot cycle; each `KnowledgeTarget` reads real
  trail fields; absorb at phase 0.82 publishes a `burst` carrying the real trail. Honest dormancy
  (null when no trails).
- **(b)** REAL: the trail DATA used per slot (`trailForSlot` cycles real trails), the absorb burst
  intensity (∝ real strength). DEMO: the TIMING (wall-clock cycle, not the actual `relevant_verified()`
  recall event) and the authored target positions.
- **(c)** Subscribe to `knowledge-acquired` trail events; when `/trail #(\d+)/` matches a known
  trail, target/accelerate a slot toward THAT trail — the animation responds to the ACTUAL recall.
  Optionally tie the 4 targets to the 4 region directions so recall returns from where the knowledge
  lives. Dampen the absorb burst for quarantined trails.
- **(d)** This IS the `relevant_verified()` recall made visible; the return packet = knowledge
  injected into the cortex; the absorb burst already lights CorticalSignals via `waveLabelForTool`.
- **(e)** All `MeshBasicMaterial`, ≤1 active slot — negligible. Dormancy clean.

### 3.12 RegionPins  [4 real metric channels; one semantic repair]

- **(a)** 4 anchored HTML chips (RESEARCH/MEMORY/TOOLS/SIGNALS) at the 4 wave anchors; live `value%`
  + click sparkline from `metricsStore`.
- **(b)** REAL: all 4 channels are real backend metrics — `research`=verified_success_rate,
  `tools`=verification_coverage, `memory`=avg verified strength, `signals`=avg freshness; sparkline
  = real poll history. Offline = labeled demo drift.
- **(c)** (1) **Semantic repair:** "TOOLS"→verification_coverage is mislabeled (a user reads it as
  tool count); rename to "VERIFY" or rewire to `average_tool_calls` (already in telemetry, unbound).
  (2) Fix the acquire-bump keyword routing in `metricsStore` (real labels are `VERIFICATION GREEN`/
  `SKILL MASTERED`/etc., which don't contain "research/memory/tools/signals" — so bumps almost never
  fire; match `verification→tools`, `skill|trail→memory`, …). (3) Optional 5th AUTONOMY pin from
  `earnedAutonomy.earned`. (4) Quarantine/chain-broken alarm tint on the relevant pin.
- **(d)** Each pin IS a real capability channel (success rate / skill reliability / verify discipline / freshness).
- **(e)** 4 `Html` instances (DOM-in-3D) — acceptable; shared store tick. Always renders (correct).

### 3.13 The brain's TOOLS — agentic tool-use visualization  [FIRST-CLASS workstream]

- **(a)** Real tool dispatch already drives: TOOLS-THIS-TURN counter, agent-card lighting, objective
  sub-steps, cortex wave origin, NervousSystem burst — a complete real chain
  (`aiosAdapter.publishStep` → `agent-dispatch` → HUD + scene).
- **(b)** REAL: dispatch narration, verify verdicts, autonomous actions, approval hold, caste
  narration, the turn tool count. DEMO/gaps: lattice hubs don't pulse yet (P1 static); `uFlowDir`
  never flips to −1; `plan`/`self_analyze`/`propose_fixes` MISSING from `waveLabelForTool` (fall to
  SIGNAL — ✔ the regex at `:492-495` covers `plan` but not `self_analy`/`propose_fix`); the
  `web|fetch|grep|inspect` arm is dead code (no such tools).
- **(c)** (1) NodeLattice P2 + NervousSystem signal track (above) ARE the core tool-use upgrade.
  (2) Add `self_analy|propose_fix` to the CAUSAL/ARCHIVE arms; **remove or leave-inert the dead
  `web|fetch|grep|inspect` arm** (do NOT cite it as a real web tool). (3) Optionally parse the real
  `plan` tool output into a true decomposition tree (replacing the 2-line recency log).
- **(d)** This is the spine of the whole "working brain" read — the scene visualizes the brain DOING.
- **(e)** P2 = 5 scalar uniforms + 1 subscriber; ensure graceful exp-decay so hubs don't stay hot.

### 3.14 The WORKSPACE FORGE — where tool-use becomes real file changes  [FIRST-CLASS; currently ABSENT]

- **(a)** `WorkspaceCanvas` has a `{children}` slot ("product-side forge ports mount here")
  (`WorkspaceCanvas.tsx:217-220`); the home route mounts it with NO children → renders nothing.
  No `ForgePorts`/editor/terminal component exists in the lab. The wiring exists
  (`pendingApproval.content/diff/filepath/command`; nerve tips at real port coordinates) but the
  consumer does not.
- **(b)** Entirely ABSENT — an architectural placeholder, not a demo.
- **(c)** Fill the `children` slot (product route or `?forge=`) with three `<Html>` surfaces wired to
  real data: **ForgeEditor** (the brain's ACTUAL proposed write — `pendingApproval.content` for
  CREATE / `.diff` for EDIT; at idle, the last `code` SSE frame — which requires storing the
  currently-DISCARDED `frame.data.code` to a module var + getter, the only adapter change needed);
  **ForgeTerminal** (filter existing `tool_result` events from terminal/verify tools into a scrolling
  log — no new bus events); **ForgePreview** (the VERIFY PASS/FAIL verdict + filepath + trail-strength
  delta). The ApprovalPanel is already the decision surface; the forge gives it surrounding context.
  No new npm deps in the lab (port-manifest) — a styled `<pre>` diff is sufficient; Monaco stays in
  the product tree.
- **(d)** `create_file`/`edit_file` = the brain's write hand; `verify` = its quality gate;
  `execute_terminal` = its shell. The forge is the spatial surface where these become VISIBLE as
  real file changes, not log lines.
- **(e)** Forge panels must be `<Html>` inside the R3F canvas; must not block the canvas render.
  **Honest dormancy is critical: render a dormant placeholder when no write is pending — never invent
  file content or replay a previous turn's content as if current.**

---

## 4. PRIORITIZED, PHASED MASTER ROADMAP

Ranked by "makes it a real working brain" leverage. Quick FIDELITY-safe wins flagged ⚡;
riskiest/blindest steps flagged ⚠. **Every phase ends at a sign-off gate in HIS browser**
(WebGL is not headlessly verifiable). Lab-first → `npm run port` → his browser → canon tag + goldens.

### PHASE 0 — FIDELITY baseline (gate, no code) ⚡
Confirm canon tag exists; capture before-goldens of `?ui=superbrain` in HIS browser.
**Real data made visible:** none (baseline). **Gate:** screenshots archived. Lab-only.

### PHASE 1 — Interior comes alive: NodeLattice P2 (bus wiring)  ★ TOP LEVERAGE
The single step that crosses the interior from "decorative skeleton" to "data-true." One
`subscribeCognition`; hubs fire on real `agent-dispatch`/`route`/`knowledge-acquired` via
`aFireTime` decay. No backend change.
**Real data visible:** which lobe/caste is working RIGHT NOW; provider pick at ROUTER.
**Risk:** low (additive, SCENE_UNIFORMS consumer). **Gate:** his browser — CAUSAL lights on plan,
ARCHIVE on read, LATTICE on create/verify, ROUTER on route; graceful decay between turns. Lab-first.

### PHASE 2 — Roots carry meaning: NervousSystem signal track (uFlowDir) ⚡  ★ HIGH LEVERAGE
Pure data-truth, no geometry/shader change (the scaffold exists). Add tier prop + `WIRE_FLOW_TARGET`
+ subscriber + eased `useFrame`.
**Real data visible:** knowledge flows UP on intake, directives DOWN on command; freezes on hold.
**Risk:** very low. **Gate:** his browser — direction reverses on a real `knowledge-acquired`, returns
to outward within ~2 s, unchanged freeze on hold. Lab-first.

### PHASE 3 — The whole frame breathes: PostFX live grade ⚡ ⚠
Highest wow-per-effort, BUT internals UNVERIFIED — **read `PostFX.tsx` first** to confirm pass/uniform
names before any change. Make GradePost tint/vibrance live; drive hold/burst-verify/mode.
**Real data visible:** golden-amber pause on hold; peak-saturation frame on VERIFY GREEN; mode grade.
**Risk:** ⚠ blind (verify internals). **Gate:** his browser — grade shifts read as intended, no
flicker/strobe. Lab-first.

### PHASE 4 — Quick atmospheric data-truth wins (bundle) ⚡
AccretionCore label→tint mapping; NeuralAura `voice-speaking` membrane swell + spark tier gate;
CorticalSignals per-lobe flash override; CosmicBackground/KnowledgeHorizon drift∝activity. All
additive, no backend.
**Real data visible:** knowledge TYPE on absorption; speech cadence; lobe identity on firing;
voyage accelerates when thinking. **Risk:** low. **Gate:** his browser per change. Lab-first.

### PHASE 5 — The brain shows its skill maturity: MemoryGalaxy + CognitiveGrasp + RegionPins
Galaxy `aStatus`/freshness-altitude/mastery-flash; Grasp event-driven retrieval; RegionPins
TOOLS→VERIFY repair + bump-routing fix (+ optional AUTONOMY pin / alarm tints).
**Real data visible:** verified vs candidate, freshness, mastery; recall responds to ACTUAL events;
honest metric labels. **Risk:** low. **Gate:** his browser. Lab-first.
*(Superseded lineage stays OUT — backend payload gap; render nothing.)*

### PHASE 6 — The roots take shape: NervousSystem FORM track (cosmic root-tails) ⚠
Additive geometry below the brainstem into the void; deeper-droop main bundles. Frozen tips
untouched. Tier-gated tails. ⚠ CatmullRom emergence can only be judged in his browser.
**Real data visible:** "travelling into the deep-vast infinite space" made literal — roots into the
void carrying the directional signal from Phase 2. **Risk:** ⚠ visual emergence; rollback = remove
new intermediate points. **Gate:** his browser — roots read organic, all 3 ports still reached
exactly, frame budget holds. Lab-first.

### PHASE 7 — Live trail nodes inside the brain: NodeLattice P3
`getKnownTrails()` → live interior trail nodes (strength/walks/quarantine), `slotById` stable.
Hub skeleton remains when empty.
**Real data visible:** the actual skill library as working interior circuitry (complementary to the
exterior galaxy — macro vs micro, never redundant). **Risk:** low-med (slot discipline). **Gate:**
his browser. Lab-first.

### PHASE 8 — The forge: where tool-use becomes real file changes  ★ BIG SUBSTANCE
Fill `WorkspaceCanvas` children with ForgeEditor/Terminal/Preview wired to `pendingApproval` +
existing `tool_result` events + (one adapter change) the stored `code` frame. Product route /
`?forge=`. Honest dormancy.
**Real data visible:** the brain's ACTUAL proposed writes, real terminal/verify output, PASS/FAIL
verdicts. **Risk:** med (new surface; must not block canvas; dormancy discipline). **Gate:** his
browser + a real generate turn showing a true diff. Lab-first (product tree may use Monaco).

### PHASE 9 — New capability, not just observability: NodeLattice P4 (G1 graph traversal) ⚠ BACKEND
Add `facts.py traverse(start, depth≤3)` recursive-CTE + route; lattice lights the 2-hop neighborhood
on click. The ONLY phase that creates a NEW reasoning capability (closes the real G2 GAP).
**Real data visible:** multi-hop fact reasoning the planner cannot do today. **Risk:** ⚠ backend +
CTE cycle-guard cost; gate behind P2 sign-off. **Gate:** backend tests green + his browser. Backend + lab.

### PHASE 10 — Observability polish: NodeLattice P5 + cortex deepenings ⚠ canon-RED
Curriculum unlock DAG; router calibration edges. Cortex `uBurst` plumb + `uCloudRoute` (canon-RED
visual — explicit sign-off). Superseded lineage ONLY if the backend adds the row FK first.
**Real data visible:** learning DAG, learned provider preferences, broadest cortex states.
**Risk:** ⚠ cortex is a visual-RED edit. **Gate:** his browser, before/after. Lab-first.

---

## 5. RISKS + MITIGATIONS · HONEST-DORMANCY · PERF BUDGET (16 GB)

**Cross-effort risks**
- **Headless-blind WebGL.** Mitigation: every phase ends at HIS browser; before/after screenshots;
  canon tag + goldens precede visual work.
- **Fabrication drift.** The lenses already fabricated a cortex gradient, 5 anchors, 11/14 events,
  a frontend `superseded_by`, and unverified PostFX passes. Mitigation: §1 ledger is authoritative;
  cite file:line; where a source doesn't exist, **render nothing**.
- **Frozen-tip regression.** Re-projecting tips broke a past integration. Mitigation: only add
  geometry / change uniforms BEFORE the tips; tips are literals, never recomputed.
- **Bus-contract creep.** 10 types is the contract. Mitigation: no new `CognitionEventType` without
  explicit operator approval; `voice-speaking` already exists (no add needed for the aura swell).
- **Canon-RED visual edits** (cortex color/`uCloudRoute`, root-tail form, PostFX grade). Mitigation:
  treat as RED — explicit per-change sign-off in his browser; rollback idioms documented per area.
- **Backend-gap honesty.** G2 graph traversal and the per-row `superseded_by` FK do NOT exist.
  Mitigation: P4 builds traversal as a real backend phase; lineage rendering waits for the payload —
  **render nothing** meanwhile.

**Honest-dormancy policy (per source)**
- Atmosphere (cortex skin, aura, cosmic field, horizon, PostFX): always-on — they represent "the
  brain exists / voyages," not "the brain is doing something." Correct to never go dark.
- Data layers: MemoryGalaxy → null on zero trails (gold standard). CognitiveGrasp → null on zero
  trails. NodeLattice → keep the structural hub skeleton, render zero TRAIL nodes when empty.
  Forge → dormant placeholder when no write pending; never invent/replay content. RegionPins →
  `--` / "no real samples yet" offline. `uFlowDir` → returns to +1 idle default.
- **Universal rule: where a data source is empty or absent, render nothing for THAT element.**

**Perf budget (16 GB shared memory; Ollama can evict the GPU)**
- One-draw-call merged-geometry idiom (NervousSystem); InstancedMesh + ShaderMaterial (NodeLattice,
  3 draw calls). New work is uniform-mutation + memoized geometry — no per-frame allocation.
- Tier-gate everything new (high/medium/low); honest low-tier dormancy (e.g. 0 root-tails, 0
  intra-cluster edges, frozen Voronoi).
- Heaviest existing costs: KnowledgeHorizon high-tier volumetric (4-octave) and CosmicBackground
  star submission — already tier-gated; add nothing per-fragment to them. PostFX adds no pass.
- The only NEW per-frame cost from the whole roadmap is ~5 scalar lattice uniforms + 1 eased
  `uFlowDir` scalar + a few subscribers — negligible. The forge is DOM (`<Html>`), off the GPU hot path.

---

## 6. TOP RECOMMENDATION + OPEN QUESTIONS

### TOP RECOMMENDATION — build NodeLattice P2 (interior bus-wiring) next.
It is the **single highest "working-brain feel per effort"** step: one `subscribeCognition` call,
no backend change, no FIDELITY-RED visual edit, pure SCENE_UNIFORMS-consumer work. It converts the
interior compute lattice from a static skeleton into a **living, event-driven diagram of what the
brain is actually doing right now** — the literal heart of "demo → working computer brain." The
hubs already ARE the real tool-routing anatomy; P2 just makes them fire on the real events that the
bus already carries. Pair it immediately with **Phase 2 (NervousSystem `uFlowDir` signal track)** —
also additive, also no backend, also FIDELITY-safe — so that in one short arc the operator sees both
the interior firing on real work AND the roots carrying real directional knowledge/command flow.
Defer the blind PostFX grade (Phase 3) until `PostFX.tsx` is read, and defer all backend/visual-RED
work until these two FIDELITY-safe wins are signed off in his browser.

### OPEN QUESTIONS FOR THE OPERATOR
1. **Cortex color reality:** the live bake is **per-lobe anatomical** colors, NOT a cosmic gradient
   (the session note "re-baked to the cosmic gradient" doesn't match the code). Do you want the
   cortex to STAY per-lobe anatomical (and let the lattice/aura/roots deliver the cosmic skin), or
   should re-baking to an actual vertical gradient be a planned (canon-RED) visual phase?
2. **ROUTER provider sub-nodes:** in P2, do you want 3 authored provider sub-nodes
   (OLLAMA/BEDROCK/GEMINI) around the ROUTER hub firing on `route`, or keep ROUTER a single node?
3. **Backend appetite (Phase 9):** approve adding `facts.py traverse()` + a graph route to close the
   real G2 gap (the only step that creates NEW reasoning capability), or stay observability-only for now?
4. **Superseded lineage:** approve adding `superseded_by` to the per-row trail payload so the galaxy/
   lattice can render trail lineage? (Until then it renders nothing.)
5. **`uFlowDir` granularity:** confirm whole-organism direction is sufficient (per-bundle direction
   would split the merged geometry into 3 draw calls — a perf cost on the 16 GB box).
6. **RegionPins "TOOLS" channel:** rename to "VERIFY" (honest to its real metric) or rewire to
   `average_tool_calls`?
7. **Forge route:** product route only, or a `?forge=` param on the superbrain route too?

---

**The final aesthetic call is, and remains, the OPERATOR'S BROWSER. Nothing in this plan is
"done" until it is signed off there. WebGL cannot be verified headlessly.**
