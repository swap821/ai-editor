# FRONTEND RENOVATION BLUEPRINT

> ## SOUL ANCHOR (canonical, operator's exact words — 2026-06-14)
> **"AN AUTONOMOUS AGENTIC AI-OS CONSTANTLY WORKING WITH ITS TOOLS AND MOVING FORWARD IN DEEP-VAST INFINITE SPACE OF KNOWLEDGE."**
>
> Every renovated surface must express this: the TOOLS are the backend capabilities, so a
> capability becomes a PORT the brain visibly **works** (live/worked, never a static dashboard),
> and the voyage reads as forward **progress** (verified outcomes / learning advance the journey).
> Backend harmony IS the soul. Canon is frozen; renovation is additive PORTs through the legal
> seam only. See [[superbrain-core-theme]], [[fidelity-is-sacred-ui-laws]], [[frontend-harmony-direction]].

---

### Product frontend → 100% backend harmony, inside the operator's inviolable canon

> **One sentence:** Every real backend capability becomes an observable **PORT** plugged into the living brain through the *one legal seam* (renovatable `workbench/` + `components/` + the shell), reusing canon tokens verbatim, touching **zero** frozen files, shipped lab-first in additive waves each gated by the operator's own eyeball.

---

## 1. Mission + the ONE Hard Boundary

### Mission
The canon superbrain scene is finished and sacred. The **product scaffold around it lies**: the default face drops the assistant's reply, the marquee loops (self-analysis, curriculum, skills, autonomy, plan, memory, alignment) are invisible, and several HUD readouts are mislabeled or mocked. This blueprint renovates **only the scaffold** so that every surface tells the truth — `label == source` — and every capability the backend already exposes becomes visible **as a PORT** in the organism, with no fabrication and no new backend.

### The ONE inviolable boundary
**Never edit, never re-skin, never hand-port anything under these two roots.** They are authored in the lab, regenerated **byte-for-byte** by `npm run port`, and any edit is silently destroyed on the next port:

- **`GAG demo/gag-orchestrator/`** — the lab (separate nested git repo; authoring source of all pixels/shaders/scene/CSS/assets/adapter).
- **`frontend/src/superbrain/`** — the ported canon mirror.

**Frozen files (the complete inviolable set — both trees):**

| Category | Frozen files |
|---|---|
| **CSS / app shell (lab)** | `app/globals.css`, `app/layout.tsx`, `app/page.tsx` |
| **Libs (both)** | `lib/{constants, cognitionBus, aiosAdapter, metricsStore, soundEngine, seededRandom}.ts` |
| **Canvas / 3D (both)** | `canvas/{WorkspaceCanvas, SuperbrainScene, NervousSystem, NeuralAura, CorticalSignals, CognitiveGrasp, AccretionCore, KnowledgeHorizon, MemoryGalaxy, CosmicBackground, OrganSurface, RegionPins, PostFX, TierGovernor, WebGLErrorBoundary}.tsx` |
| **UI overlays (both)** | `ui/{SuperbrainHUD, ApprovalPanel, BootSequence(.tsx+.module.css), CyberCursor(.tsx+.module.css)}`, `QualityTierProvider.tsx` |
| **Product canon mirror** | `frontend/src/superbrain/superbrain.css` (GENERATED), `frontend/src/superbrain/SuperbrainApp.jsx` (pure canon mount), every file under `frontend/src/superbrain/lib/` and `frontend/src/superbrain/components/` |
| **Assets** | `public/models/{brain,cpu}.glb`, `public/textures/brain/{diffuse,normal,specgloss}.png`, `public/textures/{cosmic_bg,master_bg,brain_layer,fibers_layer,cosmic_math_layer}.png`, `public/grain.svg` |

**Inside the frozen set, three things are *triple*-frozen — touching them is a trust regression, not just a clobber:**
1. The **scene/brain/voyage** (the `-Z` forward motion is non-negotiable).
2. The **sovereignty row** (`SuperbrainHUD.tsx` `.system-summary` ~L883–990: FIDELITY/SKY/SURFACE/SOUND + the Supervised/HOLD/TAMPER shield) — operator-only, persisted, **no auto-degrade ever**.
3. The **truth bindings** in `aiosAdapter.ts` / `cognitionBus.ts`.

**The legal seam.** The frozen `WorkspaceCanvas` already renders `{children}` inside the single canvas (`WorkspaceCanvas.tsx:246`); `SuperbrainShell.jsx:35` already passes `<ForgePorts/>` as those children, and ForgePorts mounts `<Html>` panels at the real canon nerve world-points (`[-4.8,-1.7,0]` / `[4.8,-1.5,0]`). **All renovation lives in:** `frontend/src/workbench/*`, `frontend/src/components/*` (classic panels), `frontend/src/styles/*`, `frontend/src/App.jsx`, `frontend/src/main.jsx` (routing only), `frontend/src/superbrain/SuperbrainShell.jsx`, and brand-new files. Renovatable code **imports** the canon spine (`cognitionBus`, `aiosAdapter`, `WorkspaceCanvas`, `config`) and **never edits it**.

---

## 2. The Design-System Law (every surface reuses, none reinvents)

A renovated surface **MUST** reference the canon variables from `superbrain.css :root` — never hardcode an equivalent. (Current `forge.css` hardcodes `#6366f1`, `rgba(7,9,14,0.82)`, `blur(16px) saturate(1.4)`; **Wave 0 brings it to spec** — see §5.)

### 2.1 Tokens (reference, never duplicate)
```
COLOR   --bg #010307 · --bg-panel rgba(11,14,20,0.5) · --hairline rgba(255,255,255,0.08)
        --text-1/2/3 (.t1/.t2/.t3 vibrancy ladder)
        --accent #5ce1e6   ← THE ONE accent (status dot · Execute · active tab/item only)
TRUTH   --state-ok #58d68d · --state-busy #e0a84f · link-hold #ffb454
        tamper #ff5c5c · brain-dot local #34d399 / cloud #fbbf24
        region/fidelity #9ff0ff · diff add #7fe2a8 / del #ff8d7e
TYPE    --display (Outfit) = hero h2 ONLY — never in a port
        --mono (JetBrains) = all eyebrows/labels/stats, UPPERCASE letter-spacing 0.12em, 10px
        body (Inter); EVERY live number → font-variant-numeric: tabular-nums (mandatory)
SHAPE   glass 16px · command-bar/forge-port 14px · tabs/cards 12px · chips 8–10px · pins 7px · border-box
MOTION  --ease-out-expo (entrances 600–900ms, staggered boot)
        --ease-out-quart (hover/state-swap 200–300ms)
        --ease-in-soft (exit/dim) · --ease-loop (ambient: breathe 2.2s)
```

### 2.2 The four non-negotiable laws

1. **PAINT-TRAP LAW (most load-bearing).** Never animate a paint property (`box-shadow`, `border-color`, `background`, `top`) on a `backdrop-filter`ed element — it re-blurs every frame (~9 FPS). Instead: rim brightening toggles the static `--rim-top` var; flares/surges live on a **dedicated non-blurred child overlay** (`.forge-socket`/`.forge-link`/`.*-surge`); sweeps/meters animate `transform`/`opacity` only; truth-states are **static class swaps**. *(Current `forge.css` transitions `box-shadow`/`border-color` on the blurred `.forge-port` — a latent violation fixed in Wave 0.)*

2. **ONE-ACCENT DISCIPLINE.** `--accent` appears on *at most* one element per port (active tab / open pip / Execute). All state color comes from the **truth-state literals**, never the accent. The brain supplies color; the HUD stays neutral.

3. **GLASS RECIPE (exact).** `background: var(--bg-panel); backdrop-filter: blur(14px) saturate(140%) brightness(1.08)` (saturate capped ~140% so it pulls nebula color in, never milks out) · the canon triple inset/drop `box-shadow` · a 1px masked-gradient `::before` rim (top stop `--rim-top`) instead of a flat border · one static `.glass-grain` child (opacity 0.04, mix-blend overlay) — **grain never animated**.

4. **MOTION LAW.** Hovers brighten toward *white-alpha*, never toward a hue (only the active item gets accent). Press cancels hover lift. Magnetic pull is **Execute-only** (and reserved to the canon command bar — ports use plain tactile press). Everything collapses under `@media (prefers-reduced-motion: reduce)`.

5. **SOVEREIGNTY + NO-AUTO-DEGRADE.** No renovated surface adds a FIDELITY/SKY/SURFACE/SOUND control, flips a canon default, auto-changes, or auto-degrades. New persisted UI state uses a **fresh localStorage key** (e.g. `gag-answer-port-open-v1`) that never collides with `gag-sky-mode-v1`/`gag-brain-surface-v1`/`gag-sound-v1`/QualityTier.

---

## 3. Renovated Information Architecture — the ports compose as ONE organism

Not a dashboard. **The Anatomy of Ports:** every backend capability is a PORT plugged into the lobe that *owns* that work, and **at most two large consoles are lit at once** (the canon's two physical nerve endpoints), everything else is a dim dormant **socket-pip** on the brainstem rail. Progressive disclosure is the whole design — the organism shows only the ports relevant to what it is doing *now*, and a real directive visibly races down the nerve into the port it changes.

**Hard geometric truth (verified in source):** canon defines exactly **two** nerve sockets — left `[-4.8,-1.7,0]`, right `[4.8,-1.5,0]` (`NervousSystem.tsx`). There is **no third nerve geometry.** Therefore:
- **In-scene `<Html>` ports** may only dock at those two world-points (and the bottom-centre spinal rendezvous the shell already uses for the command line). Each becomes a **tab-stack**, not a new floating box.
- Ports with **no honest nerve to plug into** (governance: PROPOSALS, AUTONOMY, ZONE) dock as **fixed HUD-layer glass consoles** in the right rail freed by `manufacturing.css` — *not* a faked third wire.

### Anatomical assignment

| Nerve / region | Lobe owner | Ports docked there |
|---|---|---|
| **LEFT nerve** `[-4.8,-1.7,0]` | frontal / red — *directive & making* | EDITOR, CODE, PLAN, INTENT |
| **RIGHT nerve** `[4.8,-1.5,0]` | parietal·temporal — *perceiving & answering* | PREVIEW, ANSWER, MEMORY PROBE, CURRICULUM, SKILLS |
| **BRAINSTEM RAIL** (`.sb-dock-bar`, bottom-centre) | governance | AUTONOMY LEDGER, PROPOSALS, ZONE PROBE — socket-pips beside CommandLine |
| **HUD right rail** (fixed, freed by `manufacturing.css`) | governance overflow | PROPOSALS console (collapsed tab "SELF-ANALYSIS · N") |

**Disclosure rules:**
- **Auto-disclosure is SSE-driven, never a timer** (this kills the audit's MOCK cycling-timer fiction): `directive` → flash INTENT; `agent-dispatch`/`code` → EDITOR+CODE; `text_chunk` → ANSWER; `approval-required` → raise the **canon** ApprovalPanel (kept, never rebuilt) + flare the brainstem ZONE/AUTONOMY pip; `done`/`synthesis` settles.
- **One-port-open-per-nerve.** Opening a second collapses the first to its tab. Max two consoles lit.
- **Pinned overrides auto** — a turn never yanks a port the operator is reading.
- **Default idle face = canon untouched** (zero open ports; dormant pips only). `?ui=superbrain` (no flag) stays byte-identical → `SuperbrainApp`.
- The orchestrator is a **generalization of the already-shipped `ForgePorts.jsx`** into `workbench/Ports.jsx` + `workbench/ports.css`, composed by `SuperbrainShell.jsx`, re-tenanting decorative consoles via a `.sb-shell--orchestrate` scope that mirrors `manufacturing.css`.

---

## 4. Surface-by-Surface Renovation Table

> Backend paths/fields verified against the spec's source citations (`aios/api/main.py`, `aios/core/*`, `aios/memory/*`). Every "mock→real" change enforces **label == source**.

| # | Surface | Backend source (real) | Mock → Real change | Placement (renovatable) | Pri | Wave |
|---|---|---|---|---|---|---|
| 0a | **forge.css token conformance** | — | hardcoded `#6366f1`/`rgba`/`blur16 sat1.4` + paint-trap `box-shadow` transition → canon `--accent`/`--bg-panel`/`blur14 sat140 bright108` + flare on child overlay | `workbench/forge.css` | P0 | **0** |
| 0b | **`<Ports>` orchestrator** | cognitionBus + adapter getters | ForgePorts generalized to left/right nerve **tab-stacks** + SSE auto-disclosure + dormant pips | new `workbench/Ports.jsx`, `workbench/ports.css`; `SuperbrainShell.jsx`; `manufacturing.css` `.sb-shell--orchestrate` | P0 | **0** |
| 1 | **ANSWER PORT** | `text_chunk` SSE → `DirectiveResult.answer` (`aiosAdapter.streamTurn`, returned by `sendDirective`; today `CommandLine.jsx:25` discards it) | default face drops the reply (160-char terminal stub only) → full **verbatim** Q→A transcript via `MessageBubble` markdown engine; honest status pill (thinking/answered/**deferred**/fault/offline) | new `workbench/AnswerPort.jsx` + `workbench/answerStore.js` (pub/sub); right nerve tab; collapsible drawer above `.sb-dock-bar` for home face | **P0** | **1** |
| 2 | **AUTONOMY LEDGER** | `GET /api/v1/development/autonomy` (`main.py:781`) — rich fields (`failure_count`, 3 timestamps) the typed `AutonomySnapshot` drops; flares on `CAPABILITY EARNED`/`AUTONOMOUS ACTION` bus events | ⚡N badge is a black box → full ledger: earned/probation/revoked signatures, `min_successes` threshold, master-switch **readout** | new `workbench/AutonomyPort.jsx` + `autonomy.css`; brainstem rail; **direct `fetch`** (NOT the lossy adapter subset) | **P0** | **2** |
| 3 | **CODE PORT** | `code` SSE body is unreachable post-adapter → on-disk truth via `GET /api/v1/development/workspace` (`main.py:737`) | generated artifact invisible on both faces → real on-disk file the mind wrote, **`readOnly:true`** Monaco mirror (fix: CodeCanvas currently editable) | left nerve tab beside EDITOR; reuse ForgePorts `[350,1500,3500]` burst | P1 | **3** |
| 4 | **PLAN PORT** | `POST /api/v1/plan` (`main.py:869`) — `steps/approved/escalate/requires_human/calibrations`, threshold 0.72 | absent → confidence-gated tree, gate verdict from `requires_human` (green AUTO / amber HUMAN REVIEW), transform-only meter w/ 0.72 tick, collapsible calibration drawer | new `workbench/PlanPort.jsx` + `plan.css`; left nerve tab; submitted from CommandLine | P1 | **3** |
| 5 | **INTENT PORT** | `alignment` SSE = `UnderstandingFrame.as_dict()` (`alignment.py:291`); re-read via `POST /api/v1/conversation/session` (frozen adapter forwards only label/detail) | default face collapses rich frame to one line → goal/intent/confidence/`ambiguity_action`/`clarifying_question`/assumptions/unknowns; shows "DEFERRED — ASKED YOU" | left nerve tab; data via `lib/conversation.js restoreConversationSession()` re-fetched on directive/synthesis | P1 | **4** |
| 6 | **CURRICULUM PORT** | `GET /api/v1/development/curriculum` (`main.py:801`) — full `curriculum_tasks` rows; mastery **derived** by `_refresh_level` rule | absent → skill→level→task ladder, HELD-OUT pills (#9ff0ff), tabular `successes/attempts`, derived mastered-levels (no fallback formula) | new `components/CurriculumPort.jsx` + `curriculum.css`; right nerve "growth" tab; poll-only | P1 | **4** |
| 7 | **SKILLS PORT** | `GET /api/v1/development/skills?status=verified` (`main.py:718`) — `goal_pattern/status/counts/steps`; success_rate **computed by backend formula** | absent → verified-workflows list, status pills (truth literals), reuse readout, expandable steps; honest "graduate after 3@≥80%" empty state | new `workbench/SkillsPort.jsx` + `forge-skills.css`; right nerve "growth" tab; self-fetch | P1 | **5** |
| 8 | **MEMORY PROBE** | `POST /api/v1/memory/search` (`main.py:530`) — `RetrievalResult` w/ explainability `bm25/faiss/recency`; + passive recall feed from `memory-recall`/`lesson-recall`/`skill-recall` SSE | absent → star-rows w/ score + 3-segment provenance bar; passive RECALL FEED lights on real turns | new `workbench/MemoryProbe.jsx`; right nerve; read-only POST (no approval gate) | P1 | **5** |
| 9 | **PROPOSALS PORT** | `GET /self-analysis/proposals` + `apply`/`reject` (`main.py:959`) — full `self_analysis_report` row, `ApplyResult` verdict | marquee self-analysis loop is **classic-only/invisible** → canon-skinned ledger w/ DiffView; mirror backend guards (no self-approve, RED-blocked T4) | new `workbench/ProposalsPort.jsx` + `.self-port` in `forge.css`; **fixed HUD right rail** (no faked nerve); reuse `DiffView` | P1 | **6** |
| 10 | **APPROVAL PORT (self-heal)** | `getPendingApproval()` persisted truth + `result.paused`; canon endpoints `approve`/`reject` | event-only `pending` can hang on a missed bus event → single-source hook (seed-on-mount + bus + 600ms reconcile poll) | new `workbench/usePendingApproval.js`; rewire `ForgePorts.jsx` pending state; AUTHORIZE/REJECT+diff at spinal `[0,-3.0,0]` | P1 | **6** |
| 11 | **ZONE PROBE** | `POST /api/v1/security/classify` → GREEN/YELLOW/RED + reason | absent → type-and-classify probe (read-only) | brainstem socket-pip | P2 | **7** |
| 12 | **KNOWLEDGE INTAKE relabel** | `aiosAdapter.ts:566` maps channels to **mismatched** metrics (research←success-rate, tools←coverage, memory←trail-strength, signals←freshness) | **mislabeled** real numbers → relabel each channel to the metric it carries **OR** repoint to genuine Research/Memory/Tools/Signals. ⚠ *fix lands in the **lab** (`globals.css`/`SuperbrainHUD.tsx`), not the product — it is a frozen-file change, so it is a **lab task**, not a product wave.* | **LAB** `SuperbrainHUD.tsx` SOURCE_CHANNELS + `aiosAdapter.setMetricBases` | P2 | **lab** |
| 13 | **OBJECTIVE % / ACTIVE-COGNITION** | step ids / `POST /api/v1/plan` tree | fabricated `35+tools*12` bar + hardcoded MODE_RAIL prose → bind to real plan/step, or honestly label as decorative. ⚠ **lab change** (frozen HUD) | **LAB** `SuperbrainHUD.tsx` / `WorkspaceCanvas.tsx` | P2 | **lab** |

> **Surfaces #12–13 are flagged but deliberately out of the product renovation scope** — they live in frozen files and must be fixed in the **lab** then re-ported. Filing them here keeps the audit honest; they are not product waves and must not tempt a frozen-file edit.

---

## 5. Build Sequence — additive waves (lab-first where canon; product-additive otherwise)

**Per-wave loop (mandatory):** `build → test (green) → self-critique → port (if lab touched) → operator-eyeball gate`. No wave starts until the prior wave's eyeball gate passes. Every wave is **additive** (new files + one mount line); the canon default render stays byte-identical until the operator opts a port in.

> **Note on "lab-first":** all *product* waves (1–7) touch **no** lab/frozen file, so there is nothing to port — they ship straight in the product tree. The discipline "edit where authored" still binds: the only canon-conformance edits that *are* lab-first (forge token values that mirror canon, surfaces #12–13) are tracked separately and re-ported atomically.

| Wave | Deliverable | Touches | Gate artifact |
|---|---|---|---|
| **0 — Spine** | `forge.css` → token/paint-trap conformance; generalize ForgePorts → `Ports.jsx` (left/right tab-stacks, SSE disclosure, dormant pips, paint-trap-safe flare overlay); `.sb-shell--orchestrate` scope | `workbench/forge.css`, new `workbench/Ports.jsx`+`ports.css`, `SuperbrainShell.jsx`, `manufacturing.css` | before/after of existing EDITOR/PREVIEW ports proving **no visual regression** + FPS unchanged |
| **1 — ANSWER (P0)** | `answerStore.js` (Tier A: lift `result.answer`); `AnswerPort.jsx` right-nerve tab + home drawer; markdown via `MessageBubble`. *(Tier B token-streaming gated behind A.)* | `workbench/`, mount in `SuperbrainShell.jsx`, one line in `CommandLine.jsx` | screenshot: real verbatim reply on default face, deferred state honest |
| **2 — AUTONOMY (P0)** | `AutonomyPort.jsx`+`autonomy.css`, brainstem rail, direct `fetch`, flare on real events, master-switch **readout-only** | `workbench/`, `SuperbrainShell.jsx` | screenshot: empty honest state (feature ships OFF) + a seeded earned row |
| **3 — CODE + PLAN (P1)** | CODE tab (readOnly Monaco mirror, CodeCanvas `readOnly:true` fix); `PlanPort.jsx`+`plan.css` confidence tree | `components/CodeCanvas.jsx`, `workbench/` | screenshot: real on-disk file mirrored; plan tree w/ gate verdict |
| **4 — INTENT + CURRICULUM (P1)** | `INTENT` via `restoreConversationSession`; `CurriculumPort.jsx` ladder | `workbench/`, `components/`, `lib/conversation.js` | screenshot: clarifying-question deferral; mastered-levels ladder |
| **5 — SKILLS + MEMORY (P1)** | `SkillsPort.jsx` verified workflows; `MemoryProbe.jsx` probe + recall feed | `workbench/` | screenshot: probe star-rows w/ provenance bar |
| **6 — PROPOSALS + APPROVAL self-heal (P1)** | `ProposalsPort.jsx` HUD-rail console; `usePendingApproval.js` reconcile hook rewiring ForgePorts | `workbench/`, `components/DiffView` reuse | screenshot: proposal apply verdict; approval panel converges after missed event |
| **7 — ZONE + orchestration polish (P2)** | `ZONE PROBE` pip; one-port-per-nerve enforcement; `?ui=orchestrate` flag (no-flag default untouched) | `workbench/`, `main.jsx` (routing add only) | full-organism before/after; routing test |

**Routing rule:** Wave 7 adds `?ui=orchestrate` as a **new explicit flag** — the no-flag default → `SuperbrainApp` byte-untouched, `?ui=classic`/`?ui=shell` unchanged. If a port is ever promoted into the default home, it goes through a `SuperbrainHome.jsx` authored **under `workbench/`** (so `npm run port` cannot clobber it) that renders byte-equivalent to `SuperbrainApp` with the forge **default-OFF**, gated by a before/after diff in HIS browser.

---

## 6. Test + Golden + Review-Harness Plan (operator verifies fast; the agent cannot)

**Why a harness:** the agent cannot see pixels. The authoritative parity check is **FIDELITY law — proven by before/after screenshots in the operator's browser at 1920×1080.** Make that loop *fast*.

### 6.1 Automated gates (must pass before any commit)
- **Backend pytest baseline:** `.venv\Scripts\python -m pytest -q` from repo root → **516 passed, 1 skipped** (radon+coverage). Never regress; never edit the frozen security core to make anything pass.
- **Product unit tests:** `cd frontend && npm test` (vitest, jsdom). Each new port ships a `*.test.jsx` mirroring the classic precedent: **loading / empty / error / offline / honest-zero** states (e.g. ProposalsPort mirrors `ProposalsPanel.test.jsx`: loading/empty/error/RED-blocked/self-approval-guard). Assert **label == source** and **no canned data before a real response**.
- **Product build + lint:** `npm run build`, `npm run lint`.
- **Paint-trap lint (new, Wave 0):** a CI grep/rule that **fails** if any `.port-*`/`.forge-*`/`.*-port` rule animates `box-shadow|border-color|background|top` on a `backdrop-filter`ed selector. This mechanizes the most load-bearing law so a regression can't merge.

### 6.2 The fast operator-eyeball loop (per wave)
1. `cd frontend && npm run dev` → `http://localhost:5173/?ui=shell` (or `?ui=orchestrate` from Wave 7).
2. Capture **PRODUCT** parity: `node tools/capture-product.mjs <wave>` (lab puppeteer harness hits `:5173/?ui=superbrain`, writes `goldens/`).
3. Capture **LAB CANON** baseline if any canon-adjacent doubt: `cd "GAG demo/gag-orchestrator"; npm run dev`; `node tools/capture-canon.mjs` (settled HIGH-fidelity, 1920×1080, full `-idle.png` + brain crop `-brain.png`).
4. **Operator gate:** open both PNGs side-by-side in HIS browser. The pass criterion is **the canon idle frame is pixel-identical** (the brain, voyage, sovereignty row untouched) **and** the new port reads as a native lobe (canon glass, one-accent, real numbers).
5. Record the pair in `FIDELITY_BASELINE.md`. **Rollback tag:** `pre-integration-canon-v1` — restore-first if any doubt, then offer options with evidence.

### 6.3 Truth-verification (per port, manual, fast)
Run a real turn against the live backend and confirm each readout against its source:
- ANSWER → reply matches `/api/generate` `text_chunk` verbatim; deferred when `paused`.
- AUTONOMY → rows match `GET /development/autonomy` (incl. `failure_count`/timestamps the typed subset drops).
- PLAN → counts == array lengths; verdict == `requires_human`.
- CURRICULUM/SKILLS → derived mastery/success_rate recomputed by the **exact backend formula**; em-dash when `attempts==0`.
- Offline drill: kill backend → every port shows explicit `LINK OFFLINE` / dormant, **never fabricated rows**.

---

## 7. Risks + How the Frozen-Canon Boundary Is Enforced

| Risk | Enforcement |
|---|---|
| **Port-clobber** (edit under `superbrain/*` silently reverted by `npm run port`) | **Pre-commit guard:** `git diff --name-only` must show **zero** paths under `frontend/src/superbrain/` or `GAG demo/`. New shared files (e.g. `SuperbrainHome.jsx`) authored under `workbench/`, never as a ported sibling. |
| **Editing a frozen file for convenience** (e.g. widening `aiosAdapter` `AutonomySnapshot`, forwarding `code` body through the bus) | Forbidden. Read rich fields via **direct `fetch`** (ForgePorts `/workspace` precedent); read the persisted frame via REST (`restoreConversationSession`). The adapter/bus are imported, never modified. |
| **Paint-trap regression** (~9 FPS) | Paint-trap CI lint (§6.1) + every flare on a dedicated non-blurred child + `--rim-top` toggle + transform/opacity only. Verified by FPS in the eyeball gate. |
| **One-accent erosion / hue creep** | `--accent` ≤ one element/port; all state from truth literals. Caught in eyeball gate + `forge.css` Wave-0 conformance (kills `#6366f1` indigo). |
| **Faked / mislabeled data** (the audit's core sin) | `label == source` rule per port; unit tests assert empty/honest-zero before first real response; offline shows explicit state. Surfaces #12–13 (mislabeled channels, fabricated objective %) are **filed as lab tasks**, not patched in product. |
| **Faking a third nerve socket** | Only two canon nerves exist. Ports with no honest wire (PROPOSALS/AUTONOMY/ZONE) dock as **fixed HUD-rail consoles**, never an invented `<Html>` plug. |
| **Canon default drift** (repointing no-flag mount) | No-flag default stays `SuperbrainApp` byte-untouched; new experiences behind explicit `?ui=` flags; covered by routing test; `SuperbrainApp.jsx` kept frozen as the diff reference. |
| **Sovereignty / auto-degrade breach** | No port adds a FIDELITY/SKY/SURFACE/SOUND control or auto-action; new persistence uses fresh keys; TierGovernor still only whispers. |
| **Backend / security-core regression** | pytest 516/1-skip baseline before commit; never touch the frozen guardrails to make anything pass; default GREEN/propose-only if running unattended. |
| **Two-repo desync** | Product is `ai-editor` (ported files committed, reviewable as generated output); any canon change lands in the **lab** repo first then re-ports atomically so source and artifact stay in sync. |

---

### Build-order summary (the one-line plan)
**Wave 0** lay the conformant spine (forge.css + `<Ports>`) → **W1** ANSWER (P0, biggest perception gap) → **W2** AUTONOMY (P0) → **W3** CODE+PLAN → **W4** INTENT+CURRICULUM → **W5** SKILLS+MEMORY → **W6** PROPOSALS + APPROVAL self-heal → **W7** ZONE + orchestration + `?ui=orchestrate`. Every wave additive, every wave gated by the operator's eye, every line in renovatable space, the canon never touched.

---

**Key paths (all absolute):**
- Renovatable spine: `C:\Users\kumar\ai-editor\frontend\src\workbench\{ForgePorts.jsx,forge.css,manufacturing.css,shell.css,CommandLine.jsx}`, `C:\Users\kumar\ai-editor\frontend\src\superbrain\SuperbrainShell.jsx`, `C:\Users\kumar\ai-editor\frontend\src\main.jsx`, `C:\Users\kumar\ai-editor\frontend\src\config.js`
- Renovatable panels: `C:\Users\kumar\ai-editor\frontend\src\components\{CodeCanvas,LivePreview,DiffView,ProposalsPanel,MessageBubble,AlignmentPanel}.jsx`, `C:\Users\kumar\ai-editor\frontend\src\lib\{conversation.js,sse.js}`
- Inviolable roots (never edit): `C:\Users\kumar\ai-editor\GAG demo\gag-orchestrator\` and `C:\Users\kumar\ai-editor\frontend\src\superbrain\` (except the renovatable `SuperbrainShell.jsx`)
- Verification: `.venv\Scripts\python -m pytest -q` (516/1-skip); `cd frontend && npm test && npm run build`; lab `tools\capture-canon.mjs` / `tools\capture-product.mjs` → `goldens\`; rollback tag `pre-integration-canon-v1`.

---

## Safety / completeness critique (Wave 1)

```json
{
  "canon_violation_risks": [
    "FROZEN-TABLE FICTION (assets): The blueprint's frozen-file table lists assets that DO NOT EXIST in the product and are NOT copied by npm run port: public/models/cpu.glb, public/textures/{cosmic_bg,master_bg,brain_layer,fibers_layer,cosmic_math_layer}.png. Verified: frontend/public/models/ contains only brain.glb; frontend/public/textures/brain/ contains only diffuse/normal/specgloss.png; the ASSETS array in 'GAG demo/gag-orchestrator/tools/port-to-frontend.mjs' copies only brain.glb + grain.svg + 3 brain textures. An agent that 'protects' or reasons about these phantom files will be acting on a false canon map. Correct the frozen table to the 5 real assets before any wave.",
    "FROZEN-TABLE FICTION (SuperbrainApp.jsx): The blueprint claims frontend/src/superbrain/SuperbrainApp.jsx is 'regenerated byte-for-byte by npm run port' and is the frozen diff reference. FALSE \u2014 SuperbrainApp.jsx is NOT in the port-to-frontend.mjs FILES manifest (grep count 0). It is authored directly in the product tree and is NOT clobbered by the port. The port script only regenerates the 28 listed lib/component files + superbrain.css. Risk: the pre-commit guard 'git diff must show zero paths under frontend/src/superbrain/' (Risk table) would BLOCK any legitimate routing/mount edit the operator wants in SuperbrainApp.jsx, AND the 'kept frozen as the diff reference' claim has no port mechanism enforcing it. Treat SuperbrainApp.jsx as operator-canon-by-convention, not port-regenerated.",
    "PRE-COMMIT GUARD OVER-BLOCKS THE LEGAL SEAM: The blueprint's own legal seam includes editing frontend/src/superbrain/SuperbrainShell.jsx (Wave 0/1/2 all touch it). But the Risk-table enforcement says the pre-commit guard must show 'zero paths under frontend/src/superbrain/'. SuperbrainShell.jsx lives under that exact path. The guard as written would reject every wave. The guard must whitelist SuperbrainShell.jsx (and only it) under superbrain/, or be re-scoped to the actually-ported file set from the manifest.",
    "CodeCanvas readOnly is a SHARED-component change, not a CODE-PORT-local one: Wave 3 says 'CodeCanvas readOnly:true fix'. But CodeCanvas.jsx is shared \u2014 ForgePorts mounts it for the EDITOR port (which is meant to be editable, it has onChange wired at ForgePorts.jsx:188). Hardcoding readOnly:true would silently break the EDITOR port's editing. The fix must be a readOnly PROP on CodeCanvas (default false), set true only by the CODE PORT instance \u2014 not a global toggle. As written it risks degrading an existing working surface."
  ],
  "missing_surfaces": [
    "AUTONOMY REVOKE is silently dropped to read-only with no rationale gap noted: backend exposes POST /api/v1/development/autonomy/revoke (main.py:791) and the harmony map lists 'Operator force-revoke' as a real capability (P2). The blueprint's AUTONOMY LEDGER (#2) is explicitly 'master-switch READOUT-only' and never surfaces revoke. That is a defensible observability-first choice, but the blueprint should state it is deliberately deferred (it currently reads as if revoke doesn't exist).",
    "Memory CONSOLIDATE / facts COMMIT / facts RECONCILE (POST /api/v1/memory/consolidate, /facts, /facts/reconcile) \u2014 all real backend, all in the harmony map (P2), none appear anywhere in the blueprint's 13-surface table, not even as deferred. MEMORY PROBE (#8) is search-only. Note them as known-deferred so the audit stays honest.",
    "ALIGNMENT feedback / evaluation / corrections (GET /api/v1/alignment/evaluation, POST /alignment/feedback, /conversation/correction) \u2014 harmony-mapped (P2), classic-only today. INTENT PORT (#5) reads the frame but omits the feedback/correction/evaluation controls entirely. Acceptable for an observer-first port, but should be explicitly listed as deferred.",
    "MODELS readiness (GET /api/v1/models/{local,bedrock,gemini,auto}) \u2014 harmony map proposes a BRAIN PORT readiness readout (P2); superbrain hardcodes modelId:'auto'. Not in the blueprint at all. Gemini models is fully ABSENT in the UI. Worth a one-line deferral note.",
    "TERMINAL / ROLLBACK (POST /api/terminal, /api/v1/rollback) \u2014 harmony-mapped P2, classic-only. ZONE PROBE (#11) covers classify but not execute/terminal/rollback. Fine to defer, but unmentioned.",
    "Recall-feed channel relabel (#12) is filed as a LAB task touching frozen globals.css + SuperbrainHUD.tsx, yet the build sequence (\u00a75) never schedules a corresponding lab+port wave. It is 'flagged but deliberately out of scope' \u2014 which means the mislabeled-data sin the blueprint exists to fix stays unfixed on the default face. The blueprint should either schedule a lab wave or explicitly accept the mislabel persists, because #12/#13 are the ONLY surfaces on the byte-identical default home face (where ANSWER etc. are not mounted)."
  ],
  "fidelity_gaps": [
    "DEFAULT-FACE GAP IS UNADDRESSED BY WAVES 1-6: main.jsx routes no-flag \u2192 SuperbrainApp (verified). CommandLine.jsx and ForgePorts are mounted ONLY by SuperbrainShell (?ui=shell), NOT by SuperbrainApp. So ANSWER/CODE/PLAN/INTENT etc. all land in the shell face, while the blueprint's mission says 'the default face drops the assistant's reply.' The default face does not even have a command input to drop a reply from. Waves 1-7 improve ?ui=shell / ?ui=orchestrate; the no-flag default home stays exactly as-is until the Wave-7 SuperbrainHome.jsx step. Parity-in-his-browser is fine (default unchanged), but the stated mission ('every surface tells the truth on the default face') is not delivered until that final, lightly-specified step. Sequence the SuperbrainHome decision earlier or restate the mission as 'the shell face.'",
    "'orchestrate' NAME COLLISION with frozen canon: 'orchestrate' is already a CognitiveMode in the frozen scene (WorkspaceCanvas.tsx:69/192, SuperbrainScene.tsx, NeuralAura.tsx:57, SuperbrainHUD.tsx:20/47/57 \u2014 the brain's commanding/violet state). Reusing it for the routing flag ?ui=orchestrate AND the CSS scope .sb-shell--orchestrate overloads a sacred term and invites confusion/subtle CSS scoping bugs. Pick a distinct flag/scope name (e.g. ?ui=forge / .sb-shell--forge).",
    ".sb-shell--orchestrate scope has NO precedent in manufacturing.css: manufacturing.css is scoped ONLY to .sb-shell--manufacture and only display:none's 8 selectors. The blueprint says the orchestrate scope 'mirrors manufacturing.css' \u2014 but it is net-new CSS hiding/retenanting consoles in a NEW mode. Any over-broad selector here can leak into the manufacture or (worse) home face. Require the orchestrate scope to be strictly additive and verified to not alter ?ui=superbrain or ?ui=shell pixels.",
    "'fixed HUD right rail freed by manufacturing.css' is imprecise: .right-console is position:relative (superbrain.css:437), a flow-laid aside, NOT a position:fixed rail and NOT a drei-Html 3D anchor. manufacturing.css display:none's it, freeing visual space, but there is no pre-existing fixed rail container to dock PROPOSALS into \u2014 a new fixed-layer container must be authored and proven not to overlap the sovereignty row (system-summary ~L883) or the brain. The placement claim needs a concrete new-container spec + before/after.",
    "Spinal approval-port world-point mismatch: blueprint cites the self-heal AUTHORIZE/REJECT at <Html> [0,-3.0,0]; the real canon spinal plug is [0.0,-2.6,1.5] (NervousSystem.tsx:321 'Plug into TOP of chat box'), and SuperbrainShell mounts the command bar as a DOM .sb-dock-bar (no 3D projection at all). A new <Html> at [0,-3.0,0] is a third invented geometry. Reuse the canon ApprovalPanel in the existing HUD layer (as ?ui=shell already keeps it via manufacturing.css) rather than a new world-anchored plug.",
    "Paint-trap law: forge.css already partially complies \u2014 confirm before rewriting: .forge-port DOES violate (transition box-shadow/border-color on a blur(16px) element, line 30; .is-flaring line 58-64). BUT the flare already routes to non-blurred children .forge-socket (line 65) and .forge-link (line 70). Wave 0 must keep those working children intact and only move the .forge-port-level box-shadow/border animation off the blurred parent \u2014 a blanket rewrite risks losing the already-correct child-overlay behavior. before/after FPS gate is the right guard."
  ],
  "sequencing_advice": "\"Add a Wave 0 prerequisite step: correct the blueprint's own frozen-file table (drop the 5 phantom assets + cpu.glb; reclassify SuperbrainApp.jsx as authored-not-ported) and re-derive the pre-commit guard from the ACTUAL port-to-frontend.mjs FILES manifest \u2014 otherwise the guard blocks the legal seam (SuperbrainShell.jsx) and the agent reasons against a false canon map. Re-establish the real green baselines first: pytest collects 546 tests (not the blueprint's 516); run '.venv\\\\Scripts\\\\python -m pytest -q' to record the true passed/skipped count, and snapshot 'npm test' + 'npm run build' green, before claiming any gate. Build the paint-trap CI lint (\u00a76.1) and the forge.css token/paint-trap conformance as the very first commits of Wave 0 so every later wave is mechanically protected; verify the lint catches the existing forge.css:30/58-64 violation before fixing it (test the test). Make the CodeCanvas readOnly change a prop, not a global, and ship it inside Wave 3 with a test proving the EDITOR port stays editable. Promote the default-face question (SuperbrainHome.jsx) out of the Wave-7 footnote into an explicit early operator decision, since the mission's truth claims are about the default face but Waves 1-6 only touch ?ui=shell. Rename the ?ui=orchestrate flag / .sb-shell--orchestrate scope to avoid the frozen 'orchestrate' CognitiveMode collision. Keep the APPROVAL self-heal (Wave 6) reusing the canon ApprovalPanel in the HUD layer (as ?ui=shell already does) rather than a new <Html> world-anchor. Finally, schedule (or explicitly accept-and-document) the #12/#13 lab relabel: they are the only live surfaces on the byte-identical default home, so leaving them is the largest residual 'mislabeled data' sin the blueprint set out to kill.\"\n",
  "verdict": "\"STRONG blueprint, APPROVE WITH CORRECTIONS \u2014 do not start Wave 0 until the frozen-file table and pre-commit guard are fixed. The architecture is sound and almost every load-bearing source claim verifies exactly: the two nerve world-points [-4.8,-1.7,0]/[4.8,-1.5,0] (NervousSystem.tsx:292/307), WorkspaceCanvas renders {children} at :246, ForgePorts mounts <Html> at those points, all 9 backend endpoints exist at the cited line numbers (autonomy:781, curriculum:801, skills:718, workspace:737, plan:869, classify:825, proposals:959/977/988, memory/search:530), DirectiveResult.answer exists and CommandLine.jsx:24 discards it, AutonomySnapshot drops failure_count+earned_at/revoked_at/last_outcome_at that ledger_map() really returns, the forge.css paint-trap (line 30) and hardcoded #6366f1/rgba(7,9,14,0.82)/blur16-sat1.4 are real, CodeCanvas is editable, the metric-channel mislabel (#12) is real, all sovereignty localStorage keys exist as claimed, and the approval-desync defect is accurately characterized. The frozen-boundary instinct is excellent and lab-first/additive discipline is right. The blocking issues are factual errors in the blueprint's OWN canon map (5 phantom frozen assets + cpu.glb that don't exist; SuperbrainApp.jsx wrongly described as port-regenerated) and a pre-commit guard that would reject the legal seam it depends on (SuperbrainShell.jsx under superbrain/). Fix those, make CodeCanvas readOnly a prop, rename the 'orchestrate' collision, and the plan is safe to execute wave-by-wave under the operator eyeball gate.\""
}
```

---

## WAVE 0 — BINDING CORRECTIONS (from the Wave-1 safety critic; apply before any build)

The safety critic verdict was **"APPROVE WITH CORRECTIONS."** These supersede the blueprint body where they conflict:

1. **Frozen boundary is now mechanical, not prose.** `tools/check_canon_frozen.py` is the authoritative canon-freeze guard, derived from the REAL port manifest (28 lib/component files + `superbrain.css` + 5 assets: `brain.glb`, `grain.svg`, `textures/brain/{diffuse,normal,specgloss}.png`). The blueprint's frozen table had **fictions** (now void): `cpu.glb` + 5 phantom textures do NOT exist; `SuperbrainApp.jsx` is **product-authored, NOT port-regenerated**. The guard correctly whitelists the legal seam (`SuperbrainApp.jsx`, `SuperbrainShell.jsx`). Run it before every commit (verified: blocks canon, allows seam).
2. **`?ui=orchestrate` → `?ui=forge`** and `.sb-shell--orchestrate` → `.sb-shell--forge`. `orchestrate` is a FROZEN `CognitiveMode` (the brain's commanding state) — do not overload it.
3. **`CodeCanvas` `readOnly` is a PROP (default `false`)**, set `true` only by the CODE PORT instance. Never a global toggle — the EDITOR port must stay editable (ship a test proving it).
4. **Approval self-heal reuses the canon `ApprovalPanel` in the existing HUD layer** (as `?ui=shell` already does). No new `<Html>` world-anchor / invented geometry.
5. **PROPOSALS needs a real new fixed-layer container spec** — `.right-console` is flow-laid (`position:relative`), not a fixed rail. The new container must be proven not to overlap the sovereignty row (`~L883`) or the brain (before/after).
6. **forge.css paint-trap fix must PRESERVE the already-correct child overlays** (`.forge-socket`/`.forge-link`); only move the `.forge-port`-level `box-shadow`/`border` animation off the blurred parent. FPS before/after gate.
7. **Real baselines (record before claiming gates):** pytest **546** (not 516); `npm test` + `npm run build` green.
8. **Deferred-and-documented** (so the harmony audit stays honest — these are real backend capabilities intentionally NOT in the first build): autonomy `revoke`; memory `consolidate`/`facts`/`facts/reconcile`; alignment `feedback`/`evaluation`/`corrections`; models readiness (Gemini fully ABSENT); `terminal`/`rollback`; the #12/#13 recall-channel relabel (a LAB task on the byte-identical default home — the largest residual mislabel).
9. **First Wave-0 commits = the paint-trap CSS lint + this canon-freeze guard**, so every later wave is mechanically protected. Test each lint catches the existing violation before fixing it.
10. **Default-face decision is promoted to an explicit operator fork** (the mission's truth-claims are about the default home, but the ports land in the shell face). Pending operator answer before the landing surface is finalized.
