# SHELL_REDESIGN.md — Manufacturing-page redesign verdict

**Scope:** only the `?ui=shell` MANUFACTURING form. HOME (`?ui=superbrain`) and CLASSIC are perfect and stay byte-untouched. Every change is product-only (a new `manufacturing.css` + edits to `SuperbrainShell.jsx` / `shell.css`, optional new product components). No ported file under `frontend/src/superbrain/` from the port manifest is edited.

**Theme anchor (sacred):** *"AN AUTONOMOUS AI-OS SUPERBRAIN TRAVELLING CONSTANT INTO THE DEEP-VAST KNOWLEDGEABLE INFINITE SPACE."* The brain must keep VOYAGING (never frozen, never a screenshot) even in the work form; the editor + preview must float IN that same infinite space, never read as a flat IDE bolted on.

---

## Verification (grounded, not assumed)

I read the real files before scoring. Confirmed:

- **Current dock is the broken approach.** `frontend/src/workbench/shell.css:33-42` docks the brain into `height:42vh` with `transform:translateZ(0)` — the thin wide strip that crops the camera and crams the HUD. This is what we are replacing.
- **The `100vw` command-bar escape is real.** `superbrain.css:1217` → `width: min(880px, calc(100vw - 56px))`, and the `<900px` media rule at `:1561` rewrites it to `calc(100vw - 28px)`. Inside a transform-docked box this still sizes to the FULL window — must be overridden product-side. (Confirmed the lab itself rewrites this width, proving it is overridable.)
- **The two side consoles are NOT in the portal.** `SuperbrainHUD.tsx:1046` `<Html position={[-4.8,-1.7,0]}>` (left-console) and `:1097` `<Html position={[4.8,-1.5,0]}>` (right-console) are drei-Html 3D-anchored — they track brain world-points and clip in a small box; their wrapper transform is not CSS-targetable. They must be HIDDEN in any dock, not repositioned. The portal HUD (`#hud-portal-root`, `SuperbrainHUD.tsx:1036`) is the part that follows the box.
- **Camera framing is wide-hero.** `SuperbrainScene.tsx:967` `targetZ = 7.5` ("hero framing"), fixed FOV, `lookAt(brainDriftX*0.35, 0.62, -1.2)` (`:976`), 60s orbit radius 0.35 (`:945-957`), `BRAIN_SCALE = 3.02` (`:70`). A thin/short box crops top+bottom; a TALLER or SQUARER box, or keeping fullscreen, frames the 3.02-scale brain correctly. Camera is un-editable.
- **Boot gating is real.** `superbrain.css:1403+` keys HUD visibility off `.is-booting`/`.is-booted` on `.superbrain-experience` — must not be stripped when wrapping.
- **Live-data exports — one correction that changes the scoring.** `aiosAdapter.getLastTelemetry()` exists (`aiosAdapter.ts:488`) and `chainValid` (`:431/607`) + approval state are real → rebuilding the **Supervised/HOLD/TAMPER** shield product-side is feasible. **BUT `metricsStore.useMetric` does NOT exist** — `metricsStore.ts` exposes `subscribeMetrics` + `getMetricsSnapshot` (`:132/141`), not a `useMetric` hook. `cognitionBus.subscribeCognition` is real. **Consequence:** every direction that REBUILDS the topbar/status/command-bar as product UI must wire LATENCY/AUTONOMY via `subscribeMetrics`+`getMetricsSnapshot` (e.g. `useSyncExternalStore`), not the named-but-nonexistent `useMetric`. That is a real, non-trivial wiring + divergence-risk tax. Directions that KEEP the ported `.topbar` thinned-in-place pay ZERO of that tax — the telemetry stays wired for free.
- **`SuperbrainShell.jsx` already** holds ONE persistent `<WorkspaceCanvas/>` in `.sb-brain-stage`, toggles `.sb-shell--manufacture` on a stable ancestor, and conditionally mounts only the workbench — so the single-canvas / no-boot-re-run constraint is already structurally satisfied. We keep that.

The `useMetric` gap is the hinge of this whole review: it splits the field into **"keep-and-thin the ported topbar" (cheap, low-risk, telemetry free)** vs **"rebuild a product topbar" (more faithful chrome, but real wiring + a trust-divergence risk where the rebuilt Supervised pill could disagree with the brain's own HUD).**

---

## Scoring (1-5 per axis; weighted total /50)

Axes & weights: **Theme(a)** ×2 · **Still-voyaging(b)** ×2 · **Fidelity/scene-unchanged(c)** ×1.5 · **Port-safety/feasibility(d)** ×2 · **Fixes-the-clutter(e)** ×2 · **GPU(f)** ×1.

| # | Direction | a Theme | b Voyaging | c Fidelity | d Port-safe | e Fixes clutter | f GPU | **Total /50** |
|---|-----------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| 1 | **CINEMATIC SPLIT-HORIZON** | 5 | 5 | 5 | 4 | **5** | 3 | **44.5** |
| 2 | **CONTINUUM** | 5 | 5 | 5 | **5** | 4 | 2 | **43.5** |
| 3 | **VOYAGE COCKPIT (left rail)** | 4 | 5 | 4 | 4 | **5** | **4** | **43.0** |
| 4 | **VOID WORKBENCH** | 5 | 5 | 5 | 5 | 4 | 2 | **43.0** |
| 5 | **SUMMONED FOCUS** | 4.5 | 5 | 5 | 4 | 3.5 | 2 | **40.5** |
| 6 | **VOYAGER ORB (corner)** | 3 | 5 | 4 | 4 | **5** | **5** | **41.5** |

(1, 2 and 4 cluster within a point — the operator's aesthetic call decides among them; my recommendation breaks the tie on *clarity + GPU realism* together.)

Why the close ones land where they do:
- **SPLIT-HORIZON wins on the single most important axis: it actually FIXES the clutter (e) the cleanest while staying fully faithful.** It docks the brain into a *camera-friendly* taller band (`clamp(340px,52vh,560px)`) instead of the broken 42vh strip — so the crop pitfall is designed out, not hoped away — hides every cramming element, and gives the workbench a real, generous, un-overlapped field below. It is the most *legible* answer to "the cluttered-crammed-HUD problem," which is literally the brief.
- **CONTINUUM and VOID WORKBENCH are the most theme-pure** (brain stays full-field, work floats inside it) and the most port-safe (CONTINUUM keeps the ported topbar thinned-in-place → zero rebuild tax, perfect `d`). They lose to SPLIT-HORIZON only on `f` **GPU**: both keep the brain rendering at fullscreen pixel count + a blurred-glass workbench composited over a live WebGL canvas, on a 16GB laptop already running Ollama + Monaco + a preview iframe. They honestly admit this and lean on the FIDELITY/SKY tier lever as the escape hatch — but they bank *no* pixel saving by construction, while SPLIT-HORIZON's docked band genuinely renders ~45-55% of fullscreen pixels (fill-rate is the dominant cost: PostFX/MSAA/nebula).
- **VOYAGE COCKPIT** is the strongest pixel-saver among the dock-the-brain directions (tall narrow rail ≈ a quarter of fullscreen pixels, native-res, real saving) and its tall-narrow box is the *most camera-safe* shape for the fixed-FOV camera (full vertical height, no top/bottom crop). It drops on `d` and `a` because it (i) rebuilds the topbar → pays the `useMetric` tax + Supervised-divergence risk, and (ii) reads slightly more "companion beside an IDE" than "work inside the voyage." Still an excellent, buildable runner-up — and the **best fallback if GPU proves tight on his machine.**
- **VOYAGER ORB** is the GPU champion (corner orb ≈ 5-7% of fullscreen pixels) and unambiguously keeps the brain voyaging — but it demotes the brain from protagonist to a HUD widget, which fights the soul ("the brain is the LEAD character"). It also requires rebuilding the command-bar AND the sovereignty cluster product-side (full `useMetric` tax). Right answer only if the laptop genuinely can't afford a larger brain.
- **SUMMONED FOCUS** keeps the brain fullscreen+dimmed under a floating workbench. It's elegant and the most trivially port-safe on the canvas side (no dock at all). But it scores lower on `e` because it deliberately keeps the two drei-Html side consoles *visible-but-dimmed* at fullscreen — which can peek out from behind the inset workbench on wide screens (its own listed risk #3), reintroducing exactly the kind of edge-clutter we're trying to kill — and its fullscreen-blur veil is a real GPU cost with no pixel saving.

---

## RECOMMENDED → CINEMATIC SPLIT-HORIZON (The Voyage Above, The Forge Below)

**Why this one.** It is the sharpest, most *honest* fix to the actual stated problem. The clutter came from cramming a fullscreen HUD into a 42vh strip; SPLIT-HORIZON (1) raises the band to a height the *real* camera can frame (kills the crop), (2) hides every element the brief catalogued as un-dockable — the two drei-anchored consoles, the centered terminal-log, the decoration — using only sanctioned lab-precedent drops, and (3) relocates the few sacred controls into product chrome with *room to breathe*. The brain keeps voyaging across a clean horizon (resize, never freeze, boot never re-runs), and the workbench gets a large, calm, un-overlapped field below with a soft nebula-bleed seam so it reads as one continuous deep space, not an IDE bolted on. It is the only direction that both **(e) fixes the clutter decisively** AND **(f) banks a real GPU saving** while staying **(c) canon-faithful**.

**The one caveat I'm putting on the table up front:** the exact band height is a judgment call the camera owns, not me. 52vh is my estimate for keeping the `z=7.5` framing whole; it may need to land 48-58vh after eyeballing it in HIS browser. If even the tallest comfortable band crops the brain badly, the **honest fallback inside the same family is a SIDE dock (VOYAGE COCKPIT's tall left rail)** — which is *more* camera-safe by construction. I will NOT ship a thin strip.

### Mockup
```
┌──────────────────────────────────────────────────────────────────────┐
│ ◇ GAGOS  ●ONLINE LAT 38ms AUTONOMY 0.81  FID·SKY·SURF·SND   ▣Supervis.│ ← product ShellTopBar (thin, full width)
├──────────────────────────────────────────────────────────────────────┤
│                  · ·  *   the VOYAGING brain   *  · ·                  │
│              (canon scene, still moving — a clean horizon)             │   band: clamp(340px,52vh,560px)
│                     ·   knowledge-as-stars   ·                         │   transform-containing-block dock
│ ## CORE ONLINE · LAT 38ms · AUTONOMY 0.81 ## (status ribbon)          │ ← rides band's bottom edge
│ ::::::: soft gradient scrim — nebula bleeds down behind slabs :::::::: │ ← seam, no hard IDE divider
│ ┌─ index.html · style.css · app.js ─┐  ┌─ ●●● preview://localhost ──┐ │
│ │  Monaco editor (.wb-editor)        │  │   live preview            │ │
│ │  glass slab floating in the void   │  │   (.wb-preview, sandbox)  │ │   .sb-workbench-stage
│ └────────────────────────────────────┘  └───────────────────────────┘ │
│  [Voyage]   ┌──── >_ Direct the Supermind…        [Execute] ────┐      │ ← product command line, floats
└──────────────────────────────────────────────────────────────────────┘   (100vw escape eliminated)
```

### Concrete product-only build plan

**New product files**
1. `frontend/src/workbench/manufacturing.css` — the override sheet. Imported in `SuperbrainShell.jsx` AFTER `./superbrain.css`, **UNLAYERED** (so it beats the `@layer components` ported rules — confirmed the experience rules live in that layer; unlayered author CSS wins regardless of specificity). Every selector scoped under `.sb-shell--manufacture`. Contents:
   - HIDE: `.command-bar, .left-console, .right-console, .terminal-log, .topbar, .core-readout, .hud-footer, .bottom-scrim { display:none }` — each verified sanctioned by an existing lab media-query drop (`.right-console` <900px `:1526`, `.left-console`/`.build-tag` <620px `:1573`, `.terminal-log`/`.hud-footer` <1100px `:1509`). Hiding `.command-bar` is what *eliminates the `100vw` escape entirely* — we re-provide its function as a product command line, so no width fight at all.
   - The seam scrim (≈80px gradient between band and workbench) and the band-bottom status ribbon mounts.
2. `frontend/src/workbench/ShellTopBar.jsx` — slim full-width header: small GAGOS mark (drop the build-tag), OBSERVE/SYNTHESIZE/ORCHESTRATE segmented control (the one real control rescued from the hidden left-console), FIDELITY/SKY/SURFACE/SOUND buttons, and the **Supervised/HOLD/TAMPER** pill. Bind to `aiosAdapter.getLastTelemetry()` (`chainValid`/approval). **Wire LATENCY/AUTONOMY via `subscribeMetrics`+`getMetricsSnapshot` (NOT `useMetric` — it doesn't exist).** Sky/Surface must read/write the SAME state WorkspaceCanvas owns (mirror `SKY_STORAGE_KEY`/`SURFACE_STORAGE_KEY`) so the rebuilt levers stay the real ones.
3. `frontend/src/workbench/StatusRibbon.jsx` — CORE ONLINE / LATENCY / AUTONOMY pinned to band bottom edge, same metric source.
4. `frontend/src/workbench/CommandLine.jsx` — the unified directive input; on submit it must call the **same `sendDirective` path** the ported command-bar uses (shared handler passed down), so there is ONE directive pipeline, not two divergent ones.

**Edits (all product-only)**
- `SuperbrainShell.jsx`: `import './workbench/manufacturing.css'`; render `<ShellTopBar/>`/`<StatusRibbon/>`/`<CommandLine/>` only when `manufacturing`; keep the SINGLE `<WorkspaceCanvas/>` exactly as-is; keep `.sb-shell--manufacture` toggling on the stable `.sb-shell`. Do not strip `.is-booting`/`.is-booted`.
- `shell.css`: raise `.sb-shell--manufacture .sb-brain-stage` height `42vh → clamp(340px,52vh,560px)` (keep the `transform` containing-block trick — it is the only viable dock per the constraint); set `.sb-workbench-stage { top: clamp(340px,52vh,560px) }`; add the floating command-line + ribbon boxes. The product chrome lives OUTSIDE `.sb-brain-stage` (plain shell DOM), so no element can ride a `100vw`/fixed escape.
- `#hud-portal-root` left exactly where it is (inside `.superbrain-experience`).

**Ship gate (FIDELITY-IS-SACRED):** before/after screenshots in HIS browser; confirm HOME and `?ui=superbrain`/`?ui=classic` render byte-identical to goldens (the `.sb-shell--manufacture` scoping is what protects them — prove it, don't assume). Tune band height by eye. Verify the rebuilt Supervised pill never disagrees with the brain's own audit posture (it reads the same `chainValid` — keep it that way).

---

## Strongest runners-up

**CONTINUUM (best if he wants maximum theme-purity + minimum new code).** Brain stays full-field, workbench floats inset inside it, ported `.topbar` kept thinned-in-place → **zero topbar-rebuild tax, no Supervised-divergence risk, telemetry stays wired for free** (its biggest edge over SPLIT-HORIZON on feasibility). The cost is honest: **no GPU saving** — fullscreen brain + blurred glass over live WebGL during local inference; relies entirely on the FIDELITY/SKY tier lever. Pick this if his GPU has headroom and he wants the boldest "work happens inside the voyage" read with the least surface area.

**VOYAGE COCKPIT (best if GPU is tight OR the camera won't frame a top band).** Tall left rail ≈ quarter-pixel cost (real native-res saving), and tall-narrow is the **most camera-safe shape** for the fixed-FOV camera. Downsides: rebuilds the topbar (pays the `useMetric` tax + divergence risk) and reads a touch more "companion beside an IDE." This is my designated fallback if SPLIT-HORIZON's band crops in his browser.

**VOYAGER ORB (only if the laptop genuinely can't afford a larger brain).** Cheapest by far (~5-7% pixels) and clearly still voyaging, but demotes the brain from LEAD to a corner widget — fights the soul — and rebuilds both command-bar and sovereignty cluster (full wiring tax). Keep in pocket as the GPU-emergency option.

---

## Honest tradeoffs / things that can still bite

- **GPU is the real axis of disagreement, and it's a hardware question I can't settle on paper.** SPLIT-HORIZON and COCKPIT bank real pixel savings; CONTINUUM/VOID/SUMMONED/ORB-aside do not (ORB does). If the 16GB laptop stutters under concurrent Ollama + Monaco + iframe, the no-saving directions survive only via a FIDELITY tier drop — which is operator-controlled, never auto-degrade (FIDELITY law).
- **`metricsStore.useMetric` is a phantom in four of the six write-ups.** Any rebuild-the-topbar direction MUST use `subscribeMetrics`/`getMetricsSnapshot` instead. The keep-and-thin directions (CONTINUUM, and SPLIT-HORIZON's relocation only needs it for the *product* ribbon) minimize this exposure. It blocks nothing but is real work and a real divergence risk.
- **Camera crop is the make-or-break for top-band docks.** No product-side camera edit is possible; band height must be tuned by eye, and a side dock is the honest fallback.
- **A rebuilt Supervised pill that drifts from the real `chainValid` is a trust-story bug**, not a cosmetic one. Whichever direction rebuilds it must read the same telemetry, not a copy.
- **Two divergent directive pipelines** (rebuilt command line vs hidden ported one) is the main wiring risk in SPLIT-HORIZON/COCKPIT/ORB — one shared `sendDirective` handler is mandatory.
- **No constraint is violated by the recommendation:** ported files untouched, one persistent canvas, brain scene byte-identical and still voyaging, all overrides scoped to `.sb-shell--manufacture`.
