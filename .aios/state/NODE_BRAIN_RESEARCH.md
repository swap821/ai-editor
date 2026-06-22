# NODE-BRAIN RESEARCH — The Supercomputer Node-Lattice Inside the Brain Shape

> DEEP-RESEARCH ONLY. No code edited, no build run. Verified against the live tree on 2026-06-15.
> Operator's vision: the cherished brain GLB **silhouette stays**; the **interior** changes from
> organic cortex tissue → a living lattice of **glowing, colorful compute NODES** wired together
> (a real neurology/topology), with **signals firing node→node** and **pattern-reading** — and
> CRUCIALLY the nodes are **DATA-TRUE**: they bind to the REAL autonomous AI-OS backend and can
> genuinely **help** it (observability + the missing knowledge-graph traversal capability).
>
> Two layers researched with equal weight: (1) THE VISUAL, (2) THE BACKEND-TIE (architect layer).

---

## 0. VERIFICATION LEDGER — what I read, what is TRUE, what the concepts got WRONG

I read the actual files before ranking, because "data-true" is the whole point. The headline:
**the core claims hold**, but several specifics in the three submitted concepts are inaccurate and
would make the build *not* data-true if copied verbatim. The corrected facts below are authoritative.

### CONFIRMED TRUE (build on these)

| Claim | File / line | Verdict |
|---|---|---|
| Brain shape constants | `SuperbrainScene.tsx:70` `BRAIN_SCALE=3.02`; `:235-236` `BRAIN_MIN(-0.379,-0.222,-0.439)`, `BRAIN_MAX(0.382,0.633,0.553)` | ✅ exact |
| Region colors | `:238-245` FRONTAL_CORE `#ff3b28`, PARIETAL `#19d4f0`, TEMPORAL `#36f07a`, TEMPORAL_LIME `#a8e62b`, OCCIPITAL `#9b3bff`, OCCIPITAL_HOT `#e62bd4`, CEREBELLUM `#6a35ff` | ✅ exact |
| Shared uniforms singleton | `:185` `export const SCENE_UNIFORMS = createCognitionUniforms()` | ✅ exact |
| Approval-hold amber | `:179` `HOLD_TINT = #b96a14` | ✅ exact |
| `waveLabelForTool` routing | `:490-496` plan/skill/recall→CAUSAL, read/search→ARCHIVE, create/edit/verify→LATTICE, else→SIGNAL | ✅ exact |
| `applyRegionVertexColors` math in scope | `:312-438` fbm/smoothstep region blend | ✅ exact |
| Additive-layer flag convention | `:36` `SHOW_REGION_PINS=true`, `:48` `SHOW_MEMORY_GALAXY=true` | ✅ exact |
| WIRE_FRAGMENT packet shader | `NervousSystem.tsx:38-88` `fract(vUv.x*4.0 - flowTime + vPhase)`, `flowTime = uTime*vSpeed*(1.0-uHold)`, packet `smoothstep(0.86,0.90)*smoothstep(0.98,0.94)`, bloom note "do NOT drop uSignalGain below ~2.5", additive + `depthWrite:false` | ✅ exact |
| `mergeGeometries` one-draw-call idiom | `NervousSystem.tsx:4,347` | ✅ exact |
| MemoryGalaxy honest dormancy | `MemoryGalaxy.tsx:188` `if (starCount === 0) return null` | ✅ exact |
| `getKnownTrails()` / `TrailRow` | `aiosAdapter.ts:496-511, :574`; `TrailRow` has `skill_id, strength, quarantined, success_count, reuse_success_count, status, …` | ✅ exact |
| Stable `slotById` map for instancing | `MemoryGalaxy.tsx:122,137-139` | ✅ exact |
| Skill strength formula | `skills.py:285-286` & `:355` `strength = min(1.0, success_rate * freshness * reuse_factor)`; `:265` `freshness = exp(-SKILL_LAMBDA_DECAY_PER_HOUR * age_hours)`; `_reuse_factor` `:143-161` (asymmetric: `(0,1)≈0.708` vs `(1,0)≈1.043`) | ✅ exact |
| `trail_map()` surfaces candidates+quarantine+superseded_by | `skills.py:301-360` (`quarantined = status=='candidate' AND meets_promotion`, `superseded_by` carried) | ✅ exact |
| Quarantine demotion `verified→candidate` on net reuse failures | `skills.py:218-225` | ✅ exact |
| Castes (role-pass) | `role_pass.py:27-31` PLANNER/CODER/REVIEWER tool sets; `:105` emits `output: f"caste: {role}"`; `:157` handoff `shared.append({"role":"assistant","content":f"[{role}]\n{answer}"})` | ✅ exact |
| Router calibration | `router.py:51-53` three providers; `:198 _calibrated_score`; `:211` "calibration only ever *refines* the rank, never destabilises it"; `development.py model_task_success_rates()` feeds it | ✅ exact |
| **G2 GAP — facts have NO traversal** | `facts.py` whole file: only `find_conflict`, `add_fact`, `reconcile`, `get`, `facts_for` — all flat `WHERE subject=? AND status='active'` (`:145-154`). **No recursive CTE, no self-join, no BFS/DFS anywhere.** | ✅ GAP IS REAL |
| Facts schema is a triple-graph | `schema.sql:119-124` `(subject,predicate,object,status,approved_by)`; `:221 idx_facts_sp ON (subject,predicate)` exists (accelerates a future JOIN) | ✅ exact |
| `procedural_skills.superseded_by` lineage FK | `schema.sql:190` | ✅ exact |
| Curriculum unlock DAG is real | `curriculum.py:57-61` `prior_ready = all(prior mastered)`, `status = 'available' if level==1 or prior_ready else 'locked'`; `schema.sql:197` | ✅ exact |
| Autonomy state machine | `autonomy.py` probation/earned/revoked, `:19` "one verified failure ⇒ instant revoke (streak reset)"; `earned_autonomy` table | ✅ exact |
| Audit hash-chain validity polled | `aiosAdapter.ts:707-721` `chainValid`; backend `audit_logger.py tamper_audit_trail` | ✅ exact |

### CORRECTIONS — concept claims that are WRONG (do NOT copy verbatim)

These matter because a data-true build must not invent structure the engine doesn't have.

1. **There are FOUR wave-region anchors, not five.** `SuperbrainScene.tsx:469-476` defines exactly:
   `SIGNAL` (occipital `0.05,0.31,-0.38`), `ARCHIVE` (temporal `0.34,0.16,0.11`),
   `CAUSAL` (frontal `0,0.26,0.48`), `SEMANTIC|LATTICE` (parietal crown `0,0.61,0.11`).
   **There is NO cerebellum anchor and NO router/centroid anchor in the data.** Concept A's
   "5 fixed hubs (incl. cerebellum)" and Concept B's "ROUTER hub at brain centroid" are *fabricated
   positions*. For data-truth the hub layer must be **4 anatomical hubs = the 4 real anchors**. A
   5th "ROUTER/SECURITY" hub may be *added deliberately* but it must be labeled as a new authored
   position (e.g. occipital-interior near SIGNAL), not claimed as an existing anchor.

2. **The thought-wave uniform arrays are 3 slots, not 5.** `:170-174` `uWaveOrigins`/`uWaveTimes`
   are length-3; `:1086` cascades `WAVE_REGION_ANCHORS.slice(0,3)`. The lattice must NOT assume it
   can push 5 simultaneous waves through the existing cortex wave system. The lattice's own firing
   is independent (its own attributes), so this is fine — but any claim of "5 hubs = 5 wave origins,
   perfect co-location" is false on two counts (4 anchors, 3 wave slots).

3. **`cognitionBus` has 11 event types, not 14.** `cognitionBus.ts:13-41`: `knowledge-acquired`,
   `directive`, `burst`, `agent-dispatch`, `synthesis`, `approval-required`, `approval-resolved`,
   `telemetry`, `route`, `voice-speaking` (10 named) — and that's the whole union. There is **no
   `human_required` or `earned_autonomy` bus event type**: those are *SSE frame names* that the
   adapter (`aiosAdapter.ts:262,305`) translates INTO bus events (`approval-required`,
   `knowledge-acquired`). The lattice subscribes to the **bus** (the 10 types), and must map through
   the adapter's translation, exactly as written — not invent new bus types.

4. **MemoryGalaxy node sizing uses `success_count + reuse_success_count` capped at 12**
   (`MemoryGalaxy.tsx:147-148`), and the flash regex is `/trail #(\d+)/` against `event.detail`
   (`:172-174`). A trail node that wants the same "reinforced flash" must match that exact detail
   string the adapter emits (`aiosAdapter.ts:658` `trail #${skill_id} reinforced …`).

5. **`tier` is not a uniform prop already threaded into every canvas child.** It is used inline in
   `SuperbrainScene` (e.g. particle counts), but NervousSystem/MemoryGalaxy take no `tier` prop.
   The lattice should accept `tier` explicitly (cheap), not assume an existing thread.

Net effect of corrections: the **shape of all three concepts survives**; only the *hub count*
(4 real + optional 1 authored), the *wave-slot assumption*, and the *bus-type list* need fixing.
Every backend binding (strength, castes, router, facts gap, curriculum, autonomy, audit) is real.

---

## 1. THE VISUAL — rendering a glowing node-lattice inside the shape

**Identity (shared by every energy element in the scene, verified):** near-black diffuse + high
emissive + `AdditiveBlending` + `depthWrite:false` = *energy-not-matter*, glowing in a dark void.
The lattice adopts this identity exactly, so it **adds light to** the cortex glow rather than
occluding it — interior nodes are visible through the semi-transparent shell, and they bloom through
the existing PostFX knee (`luminanceThreshold:1.0`) only when they fire past it (same mechanism the
nervous-system packets use at `uSignalGain ≥ 2.5`).

**Three render primitives, 3 draw calls total:**

- **NODES — `THREE.InstancedMesh(IcosahedronGeometry(0.025,1), nodeMat, MAX_NODES)`.** ~80 tris each.
  Per-instance `setMatrixAt` (position/scale) + `instanceColor`, both `Float32Array` allocated once
  in `useMemo`, **never per-frame for static nodes**. Per-frame: only *firing* nodes get a scale
  bump + `instanceMatrix.needsUpdate`; `instanceColor.needsUpdate` only on a real state change
  (e.g. quarantine flip). Node shader = `onBeforeCompile` injection (same pattern as the cortex
  shader): near-black base, emissive = per-instance color × activation, fresnel rim
  `pow(1-dot(V,N),~2.5..3.0)` for the energy-sphere halo. `customProgramCacheKey: () =>
  'nodelattice_v1_'+tier`.

- **EDGES — ONE `THREE.LineSegments`.** Per-edge vertex attributes: two positions, `aU` (0→1 along
  the edge = the `vUv.x` the packet travels), `aPhase`, `aSpeed`, `aColor`, `aStrength`. The
  fragment shader **copies WIRE_FRAGMENT verbatim** so a lattice packet and a nervous-bus packet are
  the *same visual language*. Because `SCENE_UNIFORMS.uHold` is the same ref, edges **freeze
  automatically during approval** — no extra wiring. `uBurst` whitens; the carrier stays near-black
  so ~90% of each edge is dark at any frame (mitigates additive stack-up).

- **BACKBONE — merged `TubeGeometry` wires** (radius ~0.003) between the hubs, `mergeGeometries`
  into one draw call. Thicker, always slowly pulsing = the "major compute bus."

**Placement (data-true, inside the shape):** static nodes (castes/memory/security/router) use the
real anchor positions + the in-scope `applyRegionVertexColors` region math; trail/fact nodes hash
their id into the lobe chosen by `waveLabelForTool(goal_pattern)` and land in that lobe's sub-volume
of `[BRAIN_MIN,BRAIN_MAX]`. **Risk R1 (clipping through the non-box mesh): shrink the placement
bounds ~15% inward** for Phase 1; add a `three-mesh-bvh` inside-test in a later phase if the operator
sees leaks. The brain is not a box, so the inward margin is the cheap, honest first move.

**Distinct from the old cortex tissue (3 ways):** (1) *geometric* — discrete glowing icospheres vs.
a continuous Voronoi surface web; (2) *spatial* — inside the volume vs. on the shell; (3) *semantic*
— labeled compute entities (PLANNER, Skill#3, FACT:project→uses→FastAPI) vs. unlabeled organic
tissue. The cortex (`OrganSurface`, `BrainModel`, `CorticalSignals`, `NeuralAura`, `RegionPins`)
is **untouched**.

**Cohesive with the world:** same WIRE_FRAGMENT as the external fiber-optic bus (internal circuit +
external spinal bundle read as one nervous infrastructure); same additive-on-black as the synaptic
dust; same bloom budget as god-rays (no PostFX change); same dark-cosmic energy identity throughout.

---

## 2. THE BACKEND-TIE — every node/edge/signal maps to a real file & field

(Authoritative inventory; all references verified above. **Honest dormancy everywhere**: if a data
source is empty, render nothing for it — never a fabricated node.)

### Hub layer (the anatomical backbone) — 4 REAL anchors (+1 optional authored)
- **CAUSAL hub** (frontal, `#ff3b28`) — plan/skill/recall/memory/lesson work (`waveLabelForTool`).
- **ARCHIVE hub** (temporal, `#36f07a`) — read/search/list/web/fetch/grep work.
- **LATTICE hub** (parietal crown, `#19d4f0`) — create/edit/write/exec/verify/run/build work.
- **SIGNAL hub** (occipital, `#9b3bff`) — signal/route/security work.
- *(optional authored)* **ROUTER/SECURITY hub** — a new interior position near SIGNAL; label it as
  authored, do not claim it's an existing anchor (correction #1).

### Node types → backend
- **Caste nodes** — `role_pass.py:27-31` (PLANNER/CODER/REVIEWER) and `swarm.py` (DECOMPOSER /
  WORKER-N / SYNTHESIZER). Activation = bus `agent-dispatch` published by `aiosAdapter.ts publishStep`
  off SSE `step` frames carrying `role` / `caste: {role}`. Dormant (dim, smaller) between turns;
  swarm workers are ephemeral (dissolve when the leg ends).
- **Memory-tier nodes** — Episodic (`episodic_memory`), Semantic (`semantic_memory`), Facts
  (`semantic_facts`), Mistakes (`mistake_pool`), Skills/Trails (`procedural_skills`), Curriculum
  (`curriculum_tasks`), Autonomy (`earned_autonomy`). Always-warm; brightness from telemetry counts.
- **Skill-trail nodes (the deepest live layer)** — one node per `TrailRow` from `getKnownTrails()`.
  **brightness = `trail.strength`**, **size = base·(1 + min(success+reuse_success,12)·k)** (mirrors
  MemoryGalaxy), verified = full color, candidate = ~40-60%, **quarantined = red pulse**, superseded
  = near-black ghost with a dim lineage edge to its keeper (`superseded_by`).
- **Security nodes** — Gateway (`gateway.py classify()` GREEN/YELLOW/RED), Audit Chain
  (`chainValid` poll; white when valid, red when broken), Verifier (`verifier.py`; green burst on
  `[VERIFY PASS]`, red on FAIL — adapter publishes `knowledge-acquired` "VERIFICATION GREEN/RED").
- **Router node** — three provider sub-nodes (OLLAMA/BEDROCK/GEMINI). The `route` bus event
  (`aiosAdapter.ts:339-352`) lights the winning provider.
- **Autonomy node** — gold burst on the adapter's `earned_autonomy`→`knowledge-acquired` translation.

### Edge types → backend
- **Pheromone trail edge** (skill→hub), weight = `strength` — `skills.py record_attempt`.
- **Reuse deposit** (recalled skill→turn), weight = `reuse_factor` — `record_reuse` (success refreshes
  `updated_at`/stays fresh; failure does **not**/evaporates faster).
- **Supersession** (old trail→keeper) — `superseded_by` FK, dim directed lineage arrow.
- **Caste handoff** PLANNER→CODER→REVIEWER (`role_pass.py:157`) / DECOMPOSER→WORKER→SYNTHESIZER
  (`swarm.py`): a bright temporary edge pulses each leg, then decays.
- **Memory promotion** L4→L3, L3b(approved)→L3 — `consolidation.py`.
- **Recall** L3→agent context — `retrieval.py hybrid_search` (BM25+FAISS+decay).
- **Classification** action→Gateway→zone; **Routing** router→provider; **Calibration** dev-events→
  router (`development.py model_task_success_rates`).
- **Fact-graph traversal** subject→object via predicate — **MISSING (the G2 gap, see §4).**
- **Curriculum unlock** level-N→level-N+1 — `curriculum.py:57-61`.
- **Autonomy streak** signature→earned — `autonomy.py`.

### Signal sequence (one verified turn, from SSE → bus)
`route → alignment → step(query_knowledge) → step(reflect) → step(query_skills) →
[step(tool_call) → step(tool_result)]×N → text_chunk×M → step(verify) → done`.
Variants: `human_required` → `approval-required` (uHold=1, everything freezes amber);
`earned_autonomy` → gold autonomy burst; swarm inserts `caste: …` boundaries.

---

## 3. PATTERN-READING — three REAL recognition capabilities made visible

1. **Stigmergy (reinforcement over time)** — `skills.py`. `strength = success_rate·freshness·
   reuse_factor` is computed per trail at every recall. Visual: node brightness/size = strength;
   well-walked paths glow and grow, disused paths decay (freshness `exp(-λ·age)`), harmful paths flip
   to **quarantine-red** on net reuse-failures. The operator literally watches learned knowledge
   strengthen and weaken. **This is the single most legible, most honest pattern-read in the system.**

2. **Memory recall (hybrid pattern matching)** — `retrieval.py` + `skills.py relevant_verified`.
   A `knowledge-acquired`/`query_skills` event flashes the matched trail/fact nodes (the recall path
   lit), then a pulse travels match→hub→caste (recalled knowledge injected into context). Frontend
   matches `event.detail` against `goal_pattern` via the existing `relevance()` — no new backend.

3. **Router calibration (pattern-based routing)** — `router.py _calibrated_score` blends heuristic
   with measured `(provider,model,task)` success rates. Provider sub-node edge weights = those rates;
   the `route` event brightens the winner. Over turns the consistently-best provider keeps the
   brightest edge — the router's learned preference becomes visible geometry. (The only case where the
   backend's own learning *changes which node/edge wins*.)

---

## 4. HOW THE LATTICE GENUINELY HELPS THE BACKEND (the architect layer)

This is what separates "pretty telemetry" from "the node/graph thinking feeds real capability."

**G1 — KNOWLEDGE-GRAPH TRAVERSAL (the real, confirmed gap; the lattice's flagship capability).**
`facts.py` stores `(subject,predicate,object)` triples but **only ever queries one hop**
(`facts_for` = flat `WHERE subject=?`). There is no recursive CTE, self-join, or BFS anywhere — so
the agent **cannot** derive transitive knowledge today. Rendering the fact-graph in 3D *requires
building the adjacency structure*, and that same structure is exposed as a new method:
```python
# aios/memory/facts.py  (NEW — ~20 lines, no new dependency; idx_facts_sp already exists)
def traverse(self, start: str, max_depth: int = 2) -> list[sqlite3.Row]:
    sql = """
    WITH RECURSIVE fact_graph(subject, predicate, object, depth, path) AS (
      SELECT subject, predicate, object, 0, subject
      FROM semantic_facts WHERE subject = :start AND status = 'active'
      UNION ALL
      SELECT f.subject, f.predicate, f.object, g.depth+1, g.path || ' → ' || f.subject
      FROM semantic_facts f JOIN fact_graph g ON f.subject = g.object
      WHERE g.depth < :max_depth AND f.status = 'active'
        AND g.path NOT LIKE '%' || f.subject || '%'   -- cycle guard
    ) SELECT * FROM fact_graph ORDER BY depth;
    """
```
Plus a thin `GET /api/v1/memory/facts/graph?start=…&depth=2` route. This is a **genuinely new
reasoning capability** (multi-hop inference the planner cannot do now), and the 3D graph is what makes
the gap *findable* and *drives its implementation*. **Keep `max_depth ≤ 3`** (cycle-guard path
concat is O(depth²) on the string; trivial at depth 2-3, quadratic beyond — risk R5).

**G2 — COGNITION-TOPOLOGY OBSERVABILITY.** Caste handoffs, trail **supersession lineage**
(`superseded_by`), the curriculum unlock DAG, and the autonomy streak are today only flat API rows.
The lattice renders them as a live, inspectable topology (e.g. watch procedural memory consolidate as
a ghost node + lineage arrow appears). Diagnostic value flat endpoints cannot give — and it adds **no
new DB reads** (the `/development/trails` payload already carries this).

**G3 — CURRICULUM DAG VISIBILITY.** `curriculum_tasks` has implicit level-N→N+1 unlock edges
(`curriculum.py:57-61`). Render the partially-mastered DAG (locked=dark, available=dim, mastered=
bright) so the operator sees what's on deck — planning-relevant info that currently needs manual SQL.

**G4 — ROUTER-CALIBRATION FEEDBACK / GOVERNANCE.** `model_task_success_rates()` feeds the router
silently. A bipartite task↔provider sub-graph (edge weight = success rate) makes the learned
preference **auditable**: BEDROCK's edge to "coding" visibly thicker than OLLAMA's = calibration is
working; all edges equal = not enough evidence yet. Governance observability that doesn't exist today.

**G5 (bonus) — CONTRADICTION SURFACE.** `add_fact` already returns `reason='contradiction'`
(`facts.py:80-87`) but it's never shown. Render conflicting fact nodes joined by a red contradiction
edge → the operator sees a knowledge conflict that needs his `reconcile()` approval.

---

## 5. THE THREE SUBMITTED CONCEPTS (corrected) + a 4th synthesis

- **Concept A — AGENT-MESH LATTICE (Supercomputer Node-Brain).** Three-layer hierarchy (hubs →
  caste/memory → live skill-trail nodes), heaviest on *agent mesh + castes*, most node types,
  richest "live thinking" choreography. Correction: 4 anchors not 5; the cerebellum hub is authored,
  not real.
- **Concept B — KNOWLEDGE-GRAPH BRAIN (Data-True Node Lattice).** Same primitives, **leads with the
  semantic-fact graph + G1 traversal** as the spine, strongest "helps-the-backend" framing, cleanest
  honest-dormancy story, ephemeral edge pool. Correction: ROUTER hub is authored (no centroid anchor);
  recommends `three-mesh-bvh` (offer the bounds-clamp fallback for zero new deps).
- **Concept C — LAYERED NEURAL-NET TOPOLOGY.** Feed-forward INTAKE→COGNITION→VERIFY layers mapping
  the *turn pipeline*; most legible "watch a forward-pass travel the layers" read. Risk R5: the
  layered look can be mis-read as ML gradient training — needs INTAKE/COGNITION/VERIFY labels.
- **Concept D — SYNTHESIS (recommended graft, see §7).** A + B's data spine, with C's pipeline
  *flow direction* as the signal-pulse choreography along the edges.

---

## 6. RANKING

Weights: supercomputer-feel, **DATA-TRUE backend-tie**, distinct-yet-cohesive, pattern-reading
legibility, feasibility/perf (16GB), FIDELITY/canon cost, **backend-HELP** (observability + G1).
Scores 1-10.

| Criterion (weight) | A: Agent-Mesh | B: Knowledge-Graph | C: Neural-Net Layers |
|---|---|---|---|
| Supercomputer-brain feel (1.0) | 9 | 9 | 8 |
| **DATA-TRUE backend-tie (1.5)** | 8 | **10** | 8 |
| Distinct-from-tissue + cohesive (1.0) | 9 | 9 | 8 |
| Pattern-reading legibility (1.0) | 8 | 9 | **9** |
| Feasibility / perf on 16GB (1.0) | 8 | 8 | 8 |
| FIDELITY / canon cost (1.0) | 9 | 9 | 9 |
| **Backend HELP (observability + G1) (1.5)** | 8 | **10** | 7 |
| **Weighted total / 80** | 65.5 | **73.0** | 63.5 |

**Winner: Concept B — Knowledge-Graph Brain (Data-True Node Lattice).** It scores highest on the two
1.5× criteria the operator stressed (DATA-TRUE + genuinely-helps-backend): it treats the lattice as
*the data structure*, makes honest dormancy first-class, and its spine (semantic-fact graph) is the
one that forces the G1 capability to exist. A is a near-tie and contributes the richest caste/agent
choreography; C contributes the clearest pipeline-flow read. So the recommendation **grafts**.

---

## 7. RECOMMENDATION — build Concept B as the spine; graft A's castes + C's flow

**One component, additive, flag-gated, lab-first, FIDELITY-signed in HIS browser.**
New file: `GAG demo/gag-orchestrator/src/components/canvas/NodeLattice.tsx` (and the byte-identical
canonical copy lives in `frontend/src/superbrain/components/canvas/` — note: a **new canvas file is
NOT in `src/superbrain/*` of the orchestrator**, so the lab `npm run port` overwrite convention does
not clobber it; keep the two trees in sync by hand). Toggle `const SHOW_NODE_LATTICE = true` beside
the existing `SHOW_REGION_PINS`/`SHOW_MEMORY_GALAXY`. Mount inside the `BrainModel` group so it rides
the brain's drift/banking. Read `SCENE_UNIFORMS` (uTime/uBurst/uHold) — pure consumer, no new uniform.

**Hubs = the 4 REAL anchors** (CAUSAL/ARCHIVE/LATTICE/SIGNAL) + 1 clearly-authored ROUTER/SECURITY
interior node. Backbone = merged tubes (1 draw call). Nodes = 1 InstancedMesh. Edges = 1 LineSegments
(WIRE_FRAGMENT verbatim) + a 32-slot pre-allocated **ephemeral edge pool** (B's idea) for live event
pulses. Tier-gate node count (corrected, conservative for a 16GB box):
`{ high: ~128, medium: ~85, low: 17 }`, edges `{ high:'k3-local+backbone', medium:'k2+backbone',
low:'backbone-only' }`. **Strict intra-region edges only** (cross-region = backbone only) so each
lobe reads as a distinct cluster (risk R2). Idle emissive **below** the bloom knee; only firing nodes
bloom (risk R4). Coexist with MemoryGalaxy (independent flags): galaxy = exterior macro skill-field,
lattice = interior micro graph-structure — complementary, not redundant.

### PHASED BUILD OUTLINE (what visualizes which real data; what backend work it unlocks)

- **PHASE 1 — Static lattice (no backend; prove the SHAPE & glow).** NodeLattice.tsx: 4 real hubs +
  authored router hub, anatomical node placement (15% inward margin), InstancedMesh node shader,
  LineSegments WIRE_FRAGMENT copy, merged-tube backbone, SCENE_UNIFORMS wired, flag added. Zero deps,
  zero backend change. **FIDELITY sign-off in HIS browser on placement + glow + distinct-from-tissue
  before anything else.** ~1-2 sessions.

- **PHASE 2 — Cognition-bus wiring (events drive firing).** `subscribeCognition` (the 10 real bus
  types). Map: `agent-dispatch`→caste node; `knowledge-acquired` VERIFICATION GREEN/RED→verifier
  node; `route`→provider sub-node; `approval-required`→uHold already freezes packets + ambers edges
  (inherited free); `directive`→all-hub pulse. No backend change. ~1 session.

- **PHASE 3 — Live trail nodes (`getKnownTrails()` → interior nodes).** Same interface MemoryGalaxy
  uses; stable `slotById`; brightness=strength, size=walks(cap 12), quarantine-red, superseded ghost
  + lineage edge. Flash on the adapter's `trail #N reinforced` detail. No backend change. ~½ session.

- **PHASE 4 — G1 capability (the real backend win).** Add `SemanticFacts.traverse(start, max_depth≤3)`
  (recursive CTE + cycle guard, `idx_facts_sp` already present) and `GET /api/v1/memory/facts/graph`.
  Lattice fetches on demand (click-to-expand a fact node → light the 2-hop neighborhood). Graceful
  degrade: 404 → no fact nodes (honest dormancy). Pure-Python addition, existing module, no new dep.
  **This is the phase where the visualization stops being observability and becomes capability.**
  ~1-2 sessions.

- **PHASE 5 (optional) — G2/G3/G4 observability projections.** Render supersession lineage, the
  curriculum unlock DAG, and the router-calibration bipartite weights from already-polled data. No new
  DB reads. Surface G5 contradiction edges from `add_fact`'s existing `reason='contradiction'`.

### Risks carried forward (verified-aware)
R1 clipping → 15% inward margin now, BVH later. R2 edge-noise → strict intra-region edges. R3 slot
misfire → stable `slotById` rebuilt only on count change. R4 bloom stack-up → idle below knee, storms
intentional. R5 CTE cycles/quadratic path → cycle guard + `max_depth ≤ 3`. **+ the §0 corrections**:
use 4 real anchors (label the 5th), don't assume 5 wave slots, subscribe to the 10 real bus types.

---

## 8. BACKEND-ARCHITECTURE NOTE (for the eventual build)

The node-lattice is the first UI surface that treats the AI-OS's **own cognition as a graph**, and
that reframing surfaces one true architectural gap and several latent ones:

1. **`SemanticFacts` is a triple store with no graph operation.** The data is graph-shaped
   (`subject,predicate,object`, indexed `(subject,predicate)`) but the access layer is strictly
   single-hop. Adding `traverse()` (recursive CTE, ~20 lines, zero deps) converts a flat fact table
   into a real **knowledge graph the planner can reason over** — multi-hop transitive inference that
   is impossible today. This is the highest-leverage backend addition in the whole proposal, and it is
   *driven into existence* by the visualization rather than bolted on.

2. **Rich relational structure is computed-then-hidden.** `superseded_by` lineage, curriculum unlock
   gating, and `model_task_success_rates()` calibration are all real directed relationships the system
   maintains internally but never exposes as topology. A thin **graph-projection layer** over the
   already-returned data (no new DB reads) turns these into inspectable, debuggable, governable
   structure — and gives the router/curriculum/skill subsystems their first real observability.

3. **Contradiction detection is implemented but invisible.** `add_fact`'s `reason='contradiction'`
   path is a dead-end to the UI; surfacing it on the lattice closes a real loop (detect → show →
   `reconcile()` with operator approval).

4. **Bus discipline is sound and should be preserved.** The SSE→bus translation (`aiosAdapter.ts`)
   already normalizes raw frames into 10 stable cognition events with try/catch listener isolation
   (`cognitionBus.ts:68-76`). The lattice should be **one more pure subscriber** — never publish, never
   add bus types — so it cannot perturb the existing organism. (Concept claims of 14 types / a
   `human_required` bus type are wrong; the real surface is 10 types + adapter translation.)

Net: the lattice is honestly **additive on the frontend** (one flagged file, canon untouched, brain
GLB/textures untouched) and honestly **capability-adding on the backend** (one new method + one route
unlocks multi-hop reasoning; everything else is projection of existing data). It satisfies the
operator's two non-negotiables at once — DATA-TRUE and genuinely-helps-the-backend — without touching
the cherished silhouette.

---

*Research only. Verified against the live tree (frontend `src/superbrain/*` canonical mirror and
`GAG demo/gag-orchestrator/*` lab; backend `aios/*`) on 2026-06-15. No code edited, no build run.
Final aesthetic call is HIS browser, lab-first, FIDELITY sign-off, brain GLB/textures untouched.*
