# FULL GREEN AUDIT — Verified Bug Ledger

> **Purpose:** drive the codebase to FULL GREEN (correctness) BEFORE building the alive-being marquee.
> The operator's instinct is right: give the living brain a sound body first.
> **This ledger is fix-ready.** Every entry is DATA-TRUE — verified against the live tree with file:line + a concrete repro.
> **Scope:** correctness only (no aesthetics — FIDELITY + his eyes own visual calls).
> **Method:** 4 finders → adversarial verification pass. 27 raw candidates collapsed to **7 confirmed bugs**; 13 over-claims/false-positives rejected.
>
> Authored: 2026-06-15 · Chief Architect audit · READ-ONLY (no code edits, no builds)

---

## 1. SUMMARY

### Confirmed bugs by severity

| Severity | Count | IDs |
|----------|-------|-----|
| **P0 — correctness / data-integrity** | 2 | BUG-G (pheromone corruption), BUG-A (mastery-flash dead) |
| **P1 — feature dead / compile / drift** | 3 | BUG-C (NervousSystem drift), BUG-D (voice-speaking type), BUG-E (NodeLattice missing) |
| **P2 — logic / leak** | 2 | BUG-B (metric routing), BUG-F (`_CHAT_HITS` leak) |
| **P3 — stale comment / dead code** | 0 confirmed as fix-priority (see §REJECTED + §4 hygiene) |

> Severity mapping note: the verifier labeled BUG-A/C/D/E "HIGH" and BUG-B/F/G "MEDIUM". For fix sequencing I split HIGH into **P0** (silent data-integrity corruption or a marquee event permanently dead) vs **P1** (a feature dead/compile-broken in one tree). BUG-G is promoted to P0 because it silently corrupts the pheromone routing substrate — the thing the whole brain runs on.

### Confirmed bugs by area

| Area | Count | IDs |
|------|-------|-----|
| **Backend** (`aios/`) | 2 | BUG-F, BUG-G |
| **Frontend-data** (lib: adapters/bus/stores) | 3 | BUG-B, BUG-D, (BUG-A spans data+component) |
| **Frontend-components** (canvas) | 2 | BUG-A, BUG-C, BUG-E |
| **Cross-cutting / lab↔frontend DRIFT** | 4 | BUG-A, BUG-B, BUG-C, BUG-D, BUG-E (all but the two backend bugs are drift or dual-copy) |

### Headline themes

1. **Lab↔frontend DRIFT is the dominant failure mode.** 5 of 7 confirmed bugs are either byte-identical-in-both-copies (so BOTH break) or a stale product mirror that the lab already fixed. The product `frontend/src/superbrain/*` mirror has fallen behind the lab `GAG demo/gag-orchestrator/src/*` on `NervousSystem.tsx`, `cognitionBus.ts`, and the entirely-missing `NodeLattice.tsx`. **The single highest-leverage action is re-establishing lab→product byte-parity** for the drifted canvas/lib files — but with a tripwire (see BUG-C/E fix + §3 port-clobber gotcha).
2. **Event-field wiring is fragile.** Two of the worst bugs (BUG-A mastery-flash, BUG-B metric routing) are the SAME class: a consumer reads the wrong field / matches the wrong substring against labels the adapter actually emits. The adapter's label/detail contract is not enforced by any test — every consumer re-implements its own ad-hoc parse and they drift apart.
3. **Silent failure paths corrupt persistent state.** BUG-G (pheromone reuse credit on a swallowed `record_attempt` exception) and BUG-F (`_CHAT_HITS` never evicts) are both "the happy path is fine, the failure/edge path quietly degrades the system over time." These are the most dangerous because they leave no error and accumulate.

---

## 2. THE LEDGER

Grouped by fix-priority. Each entry: id · severity · area · file:line (+ which copy) · defect · repro/why-wrong · fix · locking test.
Drift items are flagged **[DRIFT — fix BOTH copies]** or **[DRIFT — product stale, port from lab]**.
Security-spine touchpoints are flagged **[SECURITY-SPINE]**.

---

### P0 — Correctness / Data-Integrity

---

#### BUG-G | P0 | Backend | `direct_id is None` guard fails — every recalled skill gets spurious pheromone reuse credit

> **STATUS (2026-07-10): FIXED.** Commit `0fe0fbd` (2026-06-19, four days after
> this audit) added the `direct_id is None or ...` guard described below —
> `aios/api/main.py:2108-2117` today has the exact fix, with an inline
> comment documenting the intent. Never annotated back to this ledger, so
> this entry silently read as an open P0 for 3+ weeks. The other 6 entries
> in this doc were NOT re-verified in this pass — do not assume they're
> fixed or still open without checking the live code first.

- **File:** `aios/api/main.py:2000–2019` (assignment + filter ~line 2014)
- **Class:** Logic/correctness error — silent persistent-state corruption
- **Defect:** `direct_id` is assigned inside a `try` from `skills.record_attempt(...)`. When `record_attempt` raises (empty goal / empty arc signature / DB error), the `except` swallows it and `direct_id` stays `None`. The downstream reuse filter is:
  ```python
  reused_ids = [int(s["skill_id"]) for s in recalled_skills if int(s["skill_id"]) != direct_id]
  ```
  In Python `int != None` is **always `True`**, so on the failure path **every** skill in `recalled_skills` is passed to `record_reuse(skill_id, success=True)` — pheromone credit for skills that were never actually re-walked.
- **Repro / why wrong:** Trigger a generate call whose goal produces an empty arc signature (e.g. a goal of only stop-words) so `record_attempt` raises. Inspect the trails table: every previously recalled trail gains reuse credit regardless of outcome. Over time this inflates the strength of routinely-recalled trails and corrupts routing quality — silently, with no error surfaced.
- **Severity:** P0 — corrupts the pheromone substrate the whole brain routes on; no error, accumulates.
- **Fix:**
  ```python
  reused_ids = [
      int(s["skill_id"])
      for s in recalled_skills
      if direct_id is not None and int(s["skill_id"]) != direct_id
  ]
  ```
  (i.e. when `record_attempt` failed and `direct_id is None`, skip the reuse loop entirely.)
- **Locking test:** `tests/` pytest — mock `skills.record_attempt` to raise; call the generate path; assert `record_reuse` is **never** called when `direct_id` would be `None`. Add a positive case (record_attempt succeeds, `direct_id=7`) asserting only skills `!= 7` get reuse.

---

#### BUG-A | P0 | Frontend-components | MemoryGalaxy mastery-flash reads the wrong event field — star never flashes on mastery **[DRIFT — fix BOTH copies]**

- **Files (byte-identical, both broken):**
  - `GAG demo/gag-orchestrator/src/components/canvas/MemoryGalaxy.tsx:172`
  - `frontend/src/superbrain/components/canvas/MemoryGalaxy.tsx:172`
  - Producer: `aiosAdapter.ts:686` (both copies)
- **Class:** Data-true wiring mismatch (CONFIRMED SEED).
- **Defect:** The SKILL-MASTERED event (aiosAdapter.ts:686) puts the trail number in `event.label` (`"SKILL MASTERED — TRAIL #5"`) and the lowercased goal string in `event.detail` (`"write a test"`). MemoryGalaxy line 172 reads ONLY detail:
  ```ts
  const match = /trail #(\d+)/.exec(event.detail ?? '');
  ```
  On mastery the regex never matches → the slot is never found → `flash.setX()` is never called. Reinforcement/failure events (adapter:701) correctly put `"trail #N ..."` in `detail` and DO flash, which is why this looks like it works — but **mastery, the rarest and most important event, is permanently silent.** (Note: the SuperbrainScene synapse burst DOES fire on mastery because it reads `event.label` — so only the galaxy star flash is dead.)
- **Repro:** Promote any trail to `verified` with the galaxy mounted → corresponding star does not flash; console `match = null`. A reinforcement on the same trail DOES flash.
- **Severity:** P0 — a marquee visual event is silently dead on every mastery; this is exactly the "alive-being" signal the operator wants sound first.
- **Fix (both copies, one line — reader-side, search both fields):**
  ```ts
  const haystack = `${event.label ?? ''} ${event.detail ?? ''}`;
  const match = /trail #(\d+)/.exec(haystack);
  ```
  (Reader-side fix preferred over the adapter-side alternative so reinforcement AND mastery both keep working through one code path.)
- **Locking test:** vitest (both suites) — mock a `knowledge-acquired` event with `label: "SKILL MASTERED — TRAIL #3"`, `detail: "write a test"`; assert `slotById.get(3)` receives a `setX` call. Second case: `detail: "trail #3 reinforced — strength 0.812"` (label empty) still flashes slot 3.

---

### P1 — Feature dead / compile-broken / drift

---

#### BUG-C | P1 | Frontend-components | Product NervousSystem is a pre-refactor copy — data-true flow direction + hold-freeze + additive compositing all absent **[DRIFT — product stale, port from lab]**

- **Files:**
  - Regressed (product): `frontend/src/superbrain/components/canvas/NervousSystem.tsx` (~348 lines)
  - Canonical (lab): `GAG demo/gag-orchestrator/src/components/canvas/NervousSystem.tsx` (~401 lines)
- **Class:** Lab↔frontend drift — an entire behavior class missing in the port.
- **Defect (verified line-by-line, four concrete correctness regressions):**
  1. **No live data binding.** Product line 6 has no `subscribeCognition` import; no `flowReverseUntil` ref; no bus-subscription `useEffect` (lab lines 186–197). Flow direction never changes — packets always travel one way regardless of whether the brain is receiving knowledge (`knowledge-acquired` → should reverse to `uFlowDir=-1`) or dispatching (`directive`/`agent-dispatch` → `+1`).
  2. **No `uFlowDir` / `uSignalGain` uniforms** in the product GLSL (lab WIRE_FRAGMENT lines 43–44 have both; product 39–42 lacks them). The `material` useMemo passes only `uTime/uBurst/uHold`.
  3. **Hold-freeze broken.** Lab freezes packet *position* via `flowTime = uTime * vSpeed * (1.0 - uHold) * uFlowDir`. Product only *dims color* (`mix(1.0, 0.3, uHold)`) while packets keep moving — the "waiting on you" approval-hold signature is broken.
  4. **Wrong compositing contract.** Product uses `THREE.NormalBlending + depthWrite:true` with `gl_FragColor = vec4(finalColor, 0.95)` (product line 81). Lab uses `AdditiveBlending + depthWrite:false`. NormalBlending composites the wires as near-opaque matter that occludes the accretion disc / horizon / cosmic background behind them — the fiber-optic light identity is broken. (Confirmed by Finder 3 BUG-09 as a separable compositing-correctness defect.)
- **Repro:** In product, fire `knowledge-acquired` → packets do not reverse. Toggle approval hold → packets keep moving (only dim). Wires occlude additive layers behind them.
- **Severity:** P1 — the data-true flow-direction feature is completely dead in the product; approval-hold signature broken; compositing contract violated. (Approaches P0 since it's the literal nervous system of the alive-being, but it's a port/parity recovery, not a new defect.)
- **Fix:** Port the lab `NervousSystem.tsx` to the product path verbatim (manual copy or `npm run port` — but see §3 port-clobber gotcha re: the `surface` prop). Confirm product file is ~401 lines and byte-identical to lab afterward.
- **Locking test:** vitest render test (product) — mount product NervousSystem, fire a `knowledge-acquired` bus event, assert the flow-direction uniform transitions toward `-1`; assert `AdditiveBlending` on the material; assert `uFlowDir` uniform exists.

---

#### BUG-D | P1 | Frontend-data | Product `cognitionBus` type union missing `'voice-speaking'` — compile error + dead voice→3D pulse **[DRIFT — product stale, port from lab]**

- **Files:**
  - Product (broken): `frontend/src/superbrain/lib/cognitionBus.ts:36` — union ends at `| 'route'`
  - Lab (correct): `GAG demo/gag-orchestrator/src/lib/cognitionBus.ts:41` — has `| 'voice-speaking'`
- **Class:** Lab↔frontend drift — type union truncated in the port.
- **Defect:** The lab HUD's `speakVoiceReply` publishes `type: 'voice-speaking'` (HUD lines ~1079/1087). The product `CognitionEventType` union omits it. Any product code that publishes/subscribes to `'voice-speaking'` is a TypeScript compile error in strict mode; any scene `switch (event.type)` has a dead branch and the 3D scene cannot statically type or react to voice cadence.
- **Repro:** In the product tree, `publishCognition({ type: 'voice-speaking', label: 'test', source: 'hud' })` fails to type-check.
- **Severity:** P1 — compile error if voice-speaking is used in the product; voice-pulse to the 3D scene is dead.
- **Fix:** In `frontend/src/superbrain/lib/cognitionBus.ts` line 36, change
  ```ts
    | 'route';
  ```
  to
  ```ts
    | 'route'
    | 'voice-speaking';
  ```
- **Locking test:** TypeScript compile (product `tsc --noEmit` / vitest typecheck) passes with a `publishCognition({ type: 'voice-speaking', ... })` call present in the product tree.

---

#### BUG-E | P1 | Frontend-components | Product `NodeLattice.tsx` does not exist — the neurology layer is silently absent **[DRIFT — product stale, port from lab + wire into scene]**

- **Files:**
  - Product: `frontend/src/superbrain/components/canvas/NodeLattice.tsx` — **DOES NOT EXIST** (Glob confirmed no match)
  - Product `SuperbrainScene.tsx` — does NOT import NodeLattice (Grep confirmed no reference)
  - Lab: `GAG demo/gag-orchestrator/src/components/canvas/NodeLattice.tsx` exists; lab scene mounts it via `{SHOW_NODE_LATTICE && <NodeLattice uniforms={uniforms} tier={tier} />}`.
- **Class:** Lab↔frontend drift — missing component file.
- **Defect:** The glowing compute-node lattice (the "neurology" layer inside the brain silhouette) is present in the lab but the file is absent from the product canvas dir, and the product scene never imports it. **Not** a runtime crash (the import was never added), but the entire visual layer is silently missing from the product.
- **Repro:** Navigate to the product superbrain — no node lattice inside the brain silhouette.
- **Severity:** P1 — an entire visual feature layer silently absent from the product.
- **Fix:** Port `NodeLattice.tsx` from lab → `frontend/src/superbrain/components/canvas/NodeLattice.tsx`, then add the import and mount to the product `SuperbrainScene` matching the lab's `{SHOW_NODE_LATTICE && <NodeLattice uniforms={uniforms} tier={tier} />}` pattern (and confirm `SHOW_NODE_LATTICE` exists in the product scene constants).
- **Locking test:** Product build compiles with NodeLattice imported; render test confirms the node-lattice mesh is present in the scene tree.

---

### P2 — Logic / leak

---

#### BUG-B | P2 | Frontend-data | metricsStore bump routing always round-robins — semantic channel routing is permanently dead **[DRIFT — fix BOTH copies]**

- **Files (byte-identical, both broken):**
  - `GAG demo/gag-orchestrator/src/lib/metricsStore.ts:113`
  - `frontend/src/superbrain/lib/metricsStore.ts:113`
- **Class:** Logic/correctness error — silent wrong-branch (CONFIRMED SEED).
- **Defect:** `METRIC_KEYS = ['research','memory','tools','signals']`; routing is `const matched = METRIC_KEYS.find((key) => label.includes(key))`. Real labels from the adapter — `"SKILL MASTERED — TRAIL #3"`, `"TRAIL WEAKENED"`, `"VERIFICATION GREEN"`, `"CODE EMITTED"`, `"CAPABILITY EARNED"`, tool names like `"READ_FILE"` — contain **none** of the literal substrings `research/memory/tools/signals`. `matched` is always `undefined`; every bump falls to `METRIC_KEYS[rotation++ % 4]`. The four HUD channels receive equal round-robin distribution regardless of what the brain is doing. Aggregate volume is correct; per-channel semantics are permanently wrong (research activity bumps Tools, a mastery bumps a random bar). Note: `SuperbrainHUD.tsx` already has the correct keyword/regex mapping (`SOURCE_MATCH_ORDER` / `matchSourceRow`) — the metricsStore subscriber just doesn't use it.
- **Repro:** Fire `knowledge-acquired` with `label: "SKILL MASTERED — TRAIL #1"`. Expected: memory bar bumps. Actual: whichever rotation index is current.
- **Severity:** P2 — bars move (so it looks alive) but lie about which cognitive function fired.
- **Fix (both copies — replace the `find` line with a semantic regex map, reusing the HUD's intent semantics):**
  ```ts
  const matched =
    label.match(/trail|skill|mastered|weakened|reinforced|memory|recall|episodic/) ? 'memory'
  : label.match(/research|archive|causal|graph|scan/)                              ? 'research'
  : label.match(/tool|runtime|lattice|mesh|semantic|code|emit|verification/)        ? 'tools'
  : label.match(/signal|telemetry|ambient|capability|autonomy|route|dispatch/)      ? 'signals'
  : undefined;
  const key = matched ?? METRIC_KEYS[rotation++ % METRIC_KEYS.length];
  ```
  (Keep the round-robin fallback ONLY for truly unknown future labels.)
- **Locking test:** vitest (both suites) — assert `"SKILL MASTERED — TRAIL #1"` → `'memory'`; `"VERIFICATION GREEN"` → `'tools'`; `"CAPABILITY EARNED"` → `'signals'`; an unknown label (e.g. `"ZZZ"`) still falls to round-robin.

---

#### BUG-F | P2 | Backend | `_CHAT_HITS` never evicts empty session keys — unbounded dict growth (slow leak) **[SECURITY-SPINE — rate limiter]**

- **File:** `aios/api/main.py:2210–2230` (`_enforce_chat_rate_limit`)
- **Class:** State/lifecycle bug — memory leak.
- **Defect:** The limiter prunes timestamps older than the window but reassigns the key even when the pruned list is empty:
  ```python
  hits = [t for t in _CHAT_HITS.get(session_id, ()) if t > cutoff]
  # ...
  hits.append(now)
  _CHAT_HITS[session_id] = hits   # empty-list keys never removed
  ```
  One dead dict entry accumulates per unique `session_id` ever seen — never evicted.
- **Repro:** Run the server for 7+ days with many unique tabs/sessions; `len(_CHAT_HITS)` grows monotonically and never shrinks. Material on high-session deployments (>100k unique sessions).
- **Severity:** P2 — slow leak; benign in dev, material in production. Touches the security spine (this IS the chat rate limiter) — the fix must NOT weaken the limit, only evict dead keys.
- **Fix (preserve the limit; pop the key only when the post-append set is empty):**
  ```python
  hits = [t for t in _CHAT_HITS.get(session_id, ()) if t > cutoff]
  if len(hits) >= _CHAT_RATE_MAX:
      _CHAT_HITS[session_id] = hits
      raise HTTPException(...)        # limit unchanged
  hits.append(now)
  if hits:
      _CHAT_HITS[session_id] = hits
  else:
      _CHAT_HITS.pop(session_id, None)
  ```
  (In practice `hits` is non-empty after `append`, so the real eviction is: prune → if empty after prune AND no new hit added on a rejected/edge path, pop. Simplest safe form: after the whole function, `if not _CHAT_HITS.get(session_id): _CHAT_HITS.pop(session_id, None)`.)
- **Locking test:** pytest — call `_enforce_chat_rate_limit("x")` once; advance monotonic time past the window (monkeypatch `time.monotonic`); call again under the limit; assert `"x"` is NOT a lingering empty-list key. Add a test asserting the limit still raises `HTTPException` at `_CHAT_RATE_MAX` within the window (no weakening).

---

### P3 — stale comment / dead code (documented, NOT fix-priority)

No P3 entry was promoted to the fix batch. All stale-comment / dead-code candidates were examined and either (a) rejected as zero-runtime-impact hygiene, or (b) already self-resolved in the live tree. They are recorded in §REJECTED so a future pass doesn't re-litigate them. If a hygiene sweep is desired, the two real stale comments are: NervousSystem "115 wires" (actual 125) and PostFX "1.6" exposure (actual 1.45) — both in BOTH copies, both documentation-only.

---

### REJECTED — false positives / over-claims (do NOT re-file)

| Candidate | Verdict |
|-----------|---------|
| Finder 1 BUG-03 (stale aiosAdapter comments) | REJECTED — no runtime failure; doc debt only. |
| Finder 1 BUG-04 (curriculum.record_matching exact-match) | REJECTED — by design: curriculum is a teacher-controlled evaluation harness; exact `WHERE prompt = ?` with `.strip()` is correct for its intent. The evidence `ValueError` IS caught by the outer `except Exception: pass` (main.py ~2023) and documented "unmatched/invalid curriculum is harmless." A design question, not a correctness bug. |
| Finder 2 BUG-05/06 (surface-prop port tripwire) | REJECTED as a code bug — it's the documented `port-clobber gotcha` (process risk), not a runtime defect. Surface prop works in the product today. See §3 — it gates the BUG-C/E port. |
| Finder 2 BUG-08 (`NEXT_PUBLIC_AIOS_URL` not injected by Vite) | REJECTED — `vite.config.js:34` does `'process.env.NEXT_PUBLIC_AIOS_URL': JSON.stringify(AIOS_BASE)`; Vite `define` is a literal build-time text substitution. The adapter resolves correctly. The "Vite never injects process.env" claim is wrong. |
| Finder 2 BUG-09/10 (rotation/`__resetMetricsStoreForTests`) | REJECTED as bugs against working code — real test-isolation hygiene gaps but no metricsStore tests exist yet; folded into §4 TEST-GAP, not the ledger. |
| Finder 3 BUG-07 (useMemo deps include module-level consts) | REJECTED — module-level `const` strings are stable references; React dep compare is by reference; no-op. Only matters if `exhaustive-deps` is set to error — linter config, not runtime. |
| Finder 3 BUG-08 (CognitiveGrasp 5s poll) | REJECTED — cleanup is correct; the 5s dead window is UX latency, not correctness. Bus-subscription is a valid improvement, not a bug fix. |
| Finder 3 BUG-11 (refreshPendingApproval redundant) | REJECTED — no-op in the success path; the subscription already handles state. Redundant, not wrong. |
| Finder 4 BUG-03 / Finder 2 BUG-11 (PostFX "1.6" comment) | REJECTED as fix-priority — stale comment, zero runtime effect. (Hygiene note only.) |
| All "115 wires" stale-comment candidates | REJECTED as fix-priority — comment says 115, count is 125; documentation-only. (Hygiene note only.) |
| Finder 1 BUG-07 (`BEGIN IMMEDIATE` inside get_connection) | WITHDRAWN by its own finder — `get_connection` is a plain `@contextmanager` with manual commit/rollback; no auto-transaction wrapper; `BEGIN IMMEDIATE` is valid. No bug. |

---

## 3. THE FIX BATCH PLAN

**Guiding order:** data-integrity first → quick high-value one-liners → drift parity recovery → leak → tests. Group the dual-copy edits so BOTH copies land in the same pass.

### Pass 1 — Backend data-integrity + quick wins (remotely test-verifiable)
1. **BUG-G** (`main.py:2014`) — add `direct_id is not None` guard. **P0.** Pytest-verifiable. *(Quick win + highest data-integrity value — do first.)*
2. **BUG-F** (`main.py:~2219–2230`) — evict empty `_CHAT_HITS` keys. **P2, [SECURITY-SPINE]** — preserve the limit. Pytest-verifiable.

### Pass 2 — Frontend wiring one-liners, BOTH copies (remotely test-verifiable)
3. **BUG-A** (`MemoryGalaxy.tsx:172` × **both** copies) — search `label + detail` haystack. **P0.** vitest-verifiable.
4. **BUG-D** (`frontend/.../cognitionBus.ts:36`) — add `| 'voice-speaking'`. **P1.** tsc/vitest-verifiable. *(Trivial, unblocks any voice→scene work.)*
5. **BUG-B** (`metricsStore.ts:113` × **both** copies) — semantic regex map. **P2.** vitest-verifiable.

### Pass 3 — Drift parity recovery (needs care + operator's eyes for the visual confirm)
6. **BUG-E** (port `NodeLattice.tsx` + wire into product `SuperbrainScene`). **P1.** Build-verifiable; visual confirm needs his browser.
7. **BUG-C** (port lab `NervousSystem.tsx` → product). **P1.** Render-test-verifiable for the data wiring (uFlowDir/AdditiveBlending); the **visual** result (additive compositing, teal palette, hold-freeze) needs **his browser** per FIDELITY laws.

> **PORT-CLOBBER GOTCHA (read before Pass 3):** `npm run port` overwrites `frontend/src/superbrain/*` byte-for-byte from the lab. The product currently carries a `surface` (web/organ) prop in `WorkspaceCanvas`/`SuperbrainScene`/`SuperbrainHUD` that the lab removed. A blind `npm run port` would silently DELETE that surface-sovereignty wiring (a confirmed regression risk, per memory's `superbrain-integration-plan` + `port-clobber gotcha`). **For BUG-C/E, prefer a TARGETED manual copy of just `NervousSystem.tsx` + `NodeLattice.tsx` + the `cognitionBus.ts` one-liner**, NOT a full `npm run port`. If a full port is ever run, re-apply the `surface` prop afterward (or back-port `surface` into the lab first). This is a process gate, not a code bug.

### Gates to run after each pass
- **Backend (Pass 1):** `pytest` (the `tests/` suite — 89 tests baseline) must stay green; add the two new locking tests.
- **Frontend lab (Pass 2/3):** vitest in `GAG demo/gag-orchestrator` + `npm run build` (or `tsc --noEmit`).
- **Frontend product (Pass 2/3):** vitest in `frontend` + `npm run build` (Vite) — BUG-D and BUG-E specifically need the product build to compile.
- **Both vitest suites** must be run because BUG-A and BUG-B are dual-copy.
- **Visual confirm (Pass 3 only):** operator opens the product superbrain in his browser — NervousSystem flow-reversal on knowledge intake, hold-freeze on approval, node lattice present. NO auto-degrade; before/after per FIDELITY laws.

### Remotely test-verifiable vs needs-his-eyes
- **Fully remote (test/build green = done):** BUG-G, BUG-F, BUG-A, BUG-D, BUG-B, BUG-E (build/import), BUG-C (uniform/blending render assertions).
- **Needs his browser (visual correctness):** BUG-C and BUG-E final visual confirm (compositing, palette, lattice glow) — correctness of the *data wiring* is testable; the *look* is his call.

---

## 4. TEST-GAP LIST (load-bearing logic lacking tests — add alongside fixes)

| # | Load-bearing logic | Where | Gap | Test to add |
|---|--------------------|-------|-----|-------------|
| TG-1 | Adapter label/detail contract for `knowledge-acquired` (mastery vs reinforcement vs failure) | `aiosAdapter.ts:668/686/701` (both) | No test pins which field holds `trail #N`; every consumer re-parses → BUG-A/B class. | A contract test asserting mastery → `label` has `TRAIL #N`, reinforcement/failure → `detail` has `trail #N`. Pins the source of BUG-A. |
| TG-2 | metricsStore bump routing | `metricsStore.ts` (both) | No test file exists at all; round-robin fallback + rotation counter untested. | The BUG-B locking test + a `__resetMetricsStoreForTests()` seam so `bases/history/bumps/linkUp/rotation/tickerStarted` reset between tests (folds in Finder 2 BUG-09/10). |
| TG-3 | Chat rate-limiter eviction + enforcement | `main.py` `_enforce_chat_rate_limit` | Eviction path untested; risk a fix weakens the limit. | BUG-F locking test (eviction) + a still-enforces-at-max test. |
| TG-4 | Pheromone reuse-credit guard on `record_attempt` failure | `main.py:2000–2019` | Failure path (direct_id None) untested → BUG-G shipped silently. | BUG-G locking test (mock raise → no reuse) + positive case. |
| TG-5 | NervousSystem flow-direction subscription | `NervousSystem.tsx` (product, post-port) | No render test asserts `uFlowDir` reverses on `knowledge-acquired`. | BUG-C render test (uniform → -1; AdditiveBlending; uFlowDir exists). |
| TG-6 | cognitionBus event-type union completeness | `cognitionBus.ts` (both) | No test pins lab↔product union parity → BUG-D drift went unnoticed. | A parity test (or `tsc`) asserting both unions contain `'voice-speaking'`. |
| TG-7 | MemoryGalaxy flash slot lookup | `MemoryGalaxy.tsx` (both) | No test exercises the flash path for any event class. | BUG-A locking test (mastery + reinforcement both flash). |

---

## 5. IS FULL GREEN REACHABLE?

**Yes — and the path is short.** Only 7 confirmed bugs, none architectural. The dominant theme is drift, not rot: the lab is largely correct; the product mirror fell behind on 3 files, and 2 dual-copy wiring bugs + 2 backend failure-path bugs round it out.

**Realistic fix-pass count: 3 passes.**
- **Pass 1 (backend, ~1 sitting):** BUG-G + BUG-F + their pytest locks. Fully remote.
- **Pass 2 (frontend one-liners ×both copies, ~1 sitting):** BUG-A + BUG-D + BUG-B + vitest locks. Fully remote.
- **Pass 3 (drift parity, ~1 sitting + 1 operator visual confirm):** targeted port of NervousSystem + NodeLattice (NOT full `npm run port`) + scene wiring + render tests. Code is remotely verifiable; the *look* needs his browser once.

After Pass 3 with all 7 locking tests green and one operator visual confirm, the body is sound and the alive-being marquee can be built on a green base. The only standing non-code risk is the **port-clobber gotcha** (§3) — address by preferring targeted copies and/or back-porting the `surface` prop before any future full `npm run port`.

**Recommended sequence:** BUG-G → BUG-F → BUG-A → BUG-D → BUG-B → BUG-E → BUG-C.
