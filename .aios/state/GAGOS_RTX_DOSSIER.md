I now have everything load-bearing verified against source: dev hooks (`__POINTFIELD` proxy over material uniforms; `__POSTURE` = POSTURE_DIAL with brainScale/surfaceScale/inputBoost/flowScale/commit; `__materializeTab`/`__materializeApproval`/`__reabsorbMaterializedTab`), the posture tetrad map, the conversation-phase drive (`setConversationPhase` → thinking/streaming/complete/error), point counts (high: 200000 brain / 56000 spine), camera (fov 26, z=15), and the exact constants (bloomPoints {0.72, 1.08, 0.28}, toneMappingExposure 1.45, uSize 2.8, uGlowMul 2.55, vignettePoints {0.32, 0.76}). Here is the dossier.

# OPERATOR RTX AESTHETIC DOSSIER — GAGOS "the voyaging mind"

Tune live at **http://localhost:5173** (clean root, no params). Open DevTools console. Every dial below is a real, verified hook. Conventions:

- `window.__POINTFIELD.<u>` — live proxy over the **brain** point material uniforms (BrainPointField.tsx:181). Dev-only. Hot, no reload.
- `window.__POSTURE.<k>` — live `POSTURE_DIAL` (bodyPosture.ts:88, exposed SuperbrainScene.tsx:241). Hot.
- `window.__materializeTab() / __materializeApproval() / __reabsorbMaterializedTab()` — drive the lifecycle by hand (MaterializationLayer.tsx:186+).
- Code knobs (constants.ts / pointFieldMaterial.ts) need a save + Vite HMR; they survive reload, the `window.*` dials do not.
- SACRED LAW: hues are fixed (cyan #7bf5fb / purple #b06eff / green #54f0a0 / orange #ff7e40). Every dial here is **intensity / density / drama** — your RTX call. Do NOT shift a hue.

---

## PHASE 1 — ARRIVAL ("knowledge-field streams inward / particles converge")

**Current state.** On true first load the cloud explodes-then-condenses in lockstep with the CosmicBackground star funnel (BrainPointField arrival bridge, line 216). BUT the per-point inrush origin is only a **2-world-unit local scatter** (`origin = p + aScatter*2.0`, pointFieldMaterial.ts:50) — against the z=15 / fov 26 camera that reads as a brief local fuzz/bloom, not a wide gather across the void. The dedicated being-fed inflow layers (AccretionCore inflow, KnowledgeHorizon field) are **gated off in points mode** (SuperbrainScene.tsx:1617, 1653) — the only cosmos-wide convergence is the CosmicBackground glyph funnel, and it only fires on true first-load COALESCENCE (awakening returns zero the funnel, SuperbrainScene.tsx:1435-1438).

**Target (poster panel 1).** Particles condense across a LARGE void to FORM the silhouette; an external knowledge-field visibly streams inward.

**EXACT live dial.**
- Inrush amplitude (feel): edit `pointFieldMaterial.ts:50` `aScatter * 2.0` → try `* 4.0`–`* 6.0`; widen the stagger band `aBirth * 0.4` (line 51) → `* 0.7` so the gather reads sequential, not a single pop. **Code knob, aesthetic-rtx — flag before committing.**
- Arrival ignition flash brightness rides `uIgnite` (fragment weights it ×2.5, pointFieldMaterial.ts:127). Watch it on reload; it is single-shot passthrough (no live setter — re-trigger by reloading).
- Needs-decision (NOT a dial): whether to add a points-mode external inflow layer at all, or un-gate KnowledgeHorizon. That is a scene-architecture call, not a slider — record your verdict, don't hack it.

**Drive it live.** Hard-reload the tab (Ctrl+Shift+R) — first-load is the only true ARRIVAL/COALESCENCE.

---

## PHASE 2 — REST + FIRST CONTACT (idle calm brain, greeting)

**Current state.** Body sits at `rest` posture: lavender `[158,120,245]`, flow 0.16, tint 0.0 (bodyPosture.ts:36) — clean, no hue commit. Bloom in points mode is gentle: `bloomPoints {intensity 0.72, luminanceThreshold 1.08, luminanceSmoothing 0.28}` (constants.ts:199). Points vignette frames the void as "home": `vignettePoints {offset 0.32, darkness 0.76}` (constants.ts:222). Base point size `uSize 2.8`, glow `uGlowMul 2.55`.

**Target (poster panel 2).** Idle, breathing, fine dense dot-read; a calm halo hugging the body, not a wide haze; deep purple-black void.

**EXACT live dial (this is your baseline-calibration phase).**
- Overall glow hug: `window.__POINTFIELD.uGlowMul = 2.55` (try 2.2–3.0). Higher = brighter puncta that Bloom catches; too high blooms the void.
- Dot fineness/density read: `window.__POINTFIELD.uSize = 2.8` (try 2.2–3.4). Smaller = finer poster stipple; larger = denser continuous skin.
- Depth recession: `window.__POINTFIELD.uAttenK = 0.2` (0 = flat poster card; higher = more 3D falloff).
- Halo width vs haze: code knob `bloomPoints.intensity 0.72` and `luminanceThreshold 1.08` (constants.ts:199). RAISE threshold toward 1.12 to pull the halo tighter to the body (prior tuning note 2838 flags 1.0 as "everywhere-haze"); LOWER intensity to calm it. **aesthetic-rtx.**
- Void framing: `vignettePoints.darkness 0.76` / `offset 0.32` (constants.ts:222) — raise darkness for a stronger "home" pool.
- Global grade exposure: `POST_FX.toneMappingExposure 1.45` (constants.ts:190; tuning range 1.4–1.9 — crown must show rose GRADATION, not a clipped plateau).

**KNOWN DEVIATIONS to judge here (needs-decision, do NOT auto-fix):**
- Canvas background is pure `#000000` (SuperbrainScene.tsx:1641) while the DOM void is poster purple-black `#030108` (superbrain.css) — the 3D layer sits on a slightly different black than the chrome. Decide one canonical void and whether the seam is visible at :5173.
- Scene MODE_TINT / ambient substrate is indigo-blue `#10164a` / `#241145` (SuperbrainScene.tsx:207, 1642) — off-tetrad blue family under the brain. Very dark, small leak; confirm at :5173 whether it reads blue as the brain glows over it.

**Drive it live.** Just load `/` and leave it idle.

---

## PHASE 3 — AWAKENING / CONVERSATION (brain lights up on directive)

**Current state.** A chat turn calls `setConversationPhase('thinking')` → maps to `attentive` → `think` posture: purple `[176,110,255]`, flow 0.55, tint 0.46 (bodyPosture.ts:37). The cortex HEATS via `uAwaken` (cortex-weighted luminance only, scoped to attentive/intake so it never fights the work-dim, BrainPointField.tsx:238). Conversation phase has PRIORITY over idle organism phase.

**Target (poster panel 3).** Cortex brightens, nerves light from the core, the being notices.

**EXACT live dial.**
- Awaken heat is luminance from `uAwaken` (fragment ×1.0, line 127). To push drama on the whole think posture, raise tint strength: `window.__POSTURE.brainScale = 1.0` → try 1.2–1.4 (scales the 0.46 think tint).
- Commit the whole body to purple vs multiply-over-canon: `window.__POSTURE.commit = 0.5` → 1.0 = full poster hue commit, 0 = canon-preserving multiply.
- Flow speed of the "noticing" pulse: `window.__POSTURE.flowScale = 1` → 1.3–1.5 for faster nerve light.
- Brainstem intake reads a touch hotter: `window.__POSTURE.inputBoost = 1.15`.

**Drive it live.** In console: `setConversationPhase('thinking')` (import is module-singleton; if not in scope, type a real message in the chat input — a real cloud-Gemini turn publishes `thinking` then `streaming`). To force just the heat without a turn: `setConversationPhase('awakening')`.

---

## PHASE 4 — MATERIALIZATION (a work slab grows from a vertebra)

**Current state.** A code turn materializes a 3D slab on a spine vertebra seat. Phase `materializing` → `stream` posture (cyan, tint 0.7, flow 1.0). During materializing/working/conducting the brain cloud fades to `bodyTarget 0.28` (BrainPointField.tsx:206-209) so the inner memory-lattice shows through.

**Target (poster panel 4).** A nerve grows out from the silhouette, a slab is BORN at a vertebra; spine threads down into it.

**EXACT live dial.**
- Surface tint strength (how saturated the slab + conductor read): `window.__POSTURE.surfaceScale = 0.62` → 0.7–0.85 for a punchier slab. (Surfaces commit via CPU lerp; capped at 0.8 internally.)
- Brain-fade-during-work depth: code knob `bodyTarget 0.28` (BrainPointField.tsx:208). Lower = lattice shows more; higher = brain stays solid. **aesthetic-rtx.**
- Spine-into-slab pulse sharpness: `uStatePulse` drives a brain→roots bead-wave (pointFieldMaterial.ts:122-123); fragment weights it ×0.8 (line 127).

**Drive it live.** Console: `window.__materializeTab()` — materializes one stub content slab on the next free vertebra seat. Returns the surface. To grow several: call it 2–3 times.

---

## PHASE 5 — ORCHESTRATION (being docks smaller + crowns top, tabs seat on spine)

**Current state.** With workspaceCount > 1 the phase is `conducting`; the brain crowns the top, focus tab is lowered+shrunk (committed: y −0.62, scale 0.64), waiting tabs tether to vertebrae. Stays `stream` cyan. NOTE: a prior audit (obs 2994) flagged orchestration composition diverges from poster panel 5 across 7 structural patterns — that is geometry/layout, not a color dial.

**Target (poster panel 5).** Being small and crowning; focus center; multiple tabs seated on the spine; waiting tabs tethered by nerves.

**EXACT live dial.**
- Conductor/overlay + seated-tab tint: `window.__POSTURE.surfaceScale` (as phase 4).
- Spine signal-flow speed across all the tethers: `window.__POSTURE.flowScale` → 1.3+ to make the conduction visibly travel.
- Point budget that fills the crowned spine (RTX tier): high tier = **200000 brain / 56000 spine** points (SuperbrainScene.tsx:909-911). On the RTX 3050 stay at `high`; 256k is the known break point (obs 2455). Lower tiers: 60000/18000 (medium), 40000/11000 (low).

**Drive it live.** Console: call `window.__materializeTab()` **twice or more** to push workspaceCount past 1 → the being docks and conducts. Use `window.__focusMaterializedTab(id)` / `window.__conductNextMaterializedTab()` to move focus among seats.

---

## PHASE 6 — WORKING + SHOWING WORK (slab shows content, state flows down the nerves)

**Current state.** `working`/`conducting`, `stream` cyan, flow 1.0 — the strongest flow posture. State pulse travels brain→roots down the spine (`uStatePulse`, spine-weighted, pointFieldMaterial.ts:122). HOLD/approval-gate path: phase `approval_hold` → `hold` posture, orange `[255,126,64]`, flow 0.34, tint 0.5 (bodyPosture.ts:39) — this is the poster's warm channel, the human-approval pause.

**Target (poster panel 6).** Slab shows live content; status flows DOWN the nerves in real time; on a code result the being pauses ORANGE at the approval gate.

**EXACT live dial.**
- Down-spine flow intensity: `window.__POSTURE.flowScale` (1.3–1.6 for a faster, more legible "state flowing down").
- Stream tint commit: `window.__POSTURE.commit` toward 1.0 to drive the whole body cyan during work (poster look) vs 0.5 multiply.
- HOLD orange drama: `window.__POSTURE.brainScale` scales the 0.5 hold tint; `inputBoost` for the brainstem amber. Keep it ORANGE — do not let it drift toward the chrome's mic-pink.

**KNOWN DEVIATION to judge (needs-decision, do NOT recolor for taste):** the chrome mic "listening" state uses a pink-magenta red `rgba(255,90,120)` / `#ff9bb0` (GagosChrome.css:322-327, 352-354) that matches **nothing** in the tetrad — not the poster orange `#ff7e40`, not this file's offline coral `#f87171`. Three warm reds now coexist. Decide the canonical listening hue (reuse `#f87171` for file-internal consistency, adopt poster `#ff7e40`, or sanction a distinct alert red). This is a design-bible call you must make; it is not a brightness dial.

**Drive it live.** A real **cloud-Gemini code turn** is the truest path: type a code request in the chat → the turn publishes `streaming` (cyan flow), materializes a slab, and pauses at approval. To force the gate by hand: `window.__materializeApproval()` → body should go HOLD orange. To force pure stream color without a turn: `setConversationPhase('streaming')`.

---

## PHASE 7 — REABSORPTION (slab dissolves into motes up the spine into the brain)

**Current state.** `reabsorbing` → `completion_settle`/`complete` green `[84,240,160]` (poster-exact), tint 0.55. The brain INHALES: `uReabsorbGlow` adds a soft cortex-weighted glow (smoothstep 0.45→1.0 on the cortex axis, ×0.55, pointFieldMaterial.ts:126-127) as a finished tab's energy returns up the spine. NOTE: reabsorption mote path is currently straight lines, not spine-curve routed (obs 3013) — geometry, not a color dial.

**Target (poster panel 7).** Slab dissolves into motes that travel UP the spine into the brain; being eases back to rest-green-then-lavender. "Always voyaging."

**EXACT live dial.**
- Inhale-glow strength: code knob the `0.55` weight on `reabsorbGlow` (pointFieldMaterial.ts:126). **aesthetic-rtx.**
- Completion green strength: `window.__POSTURE.brainScale` (scales the 0.55 complete tint).
- Terminal-beat linger before easing to rest: `COMPLETE_HOLD_MS 2800` (conversationPhaseBus.ts:22) — how long green holds before lazy decay to idle lavender.

**Drive it live.** Console: `window.__reabsorbMaterializedTab(id)` (omit id to reabsorb the completion target) — watch the slab dissolve and the brain inhale green. Or end a real turn with `setConversationPhase('complete')` for the green settle.

---

## GOLDENS TO CAPTURE (one screenshot per poster phase, at :5173, high tier)

- [ ] **P1 Arrival** — hard-reload, capture mid-coalescence (cloud condensing from the funnel into the silhouette).
- [ ] **P2 Rest** — idle being, greeting up, calm halo on the purple-black void (your baseline-calibration golden; capture AFTER you lock uGlowMul / uSize / bloomPoints / vignettePoints).
- [ ] **P3 Awakening** — `setConversationPhase('thinking')`, capture the purple cortex-heat.
- [ ] **P4 Materialization** — `window.__materializeTab()` once, capture the slab being born at a vertebra with the brain faded to lattice.
- [ ] **P5 Orchestration** — `__materializeTab()` ×3, capture the docked crowning brain + focus tab + tethered waiting tabs.
- [ ] **P6 Working + Hold** — real Gemini code turn (or `__materializeApproval()`), capture the cyan down-spine flow AND a second frame at the orange approval HOLD.
- [ ] **P7 Reabsorption** — `__reabsorbMaterializedTab()`, capture the green motes traveling up the spine into the inhaling brain.

Store each next to `GAG demo/reference/demoplan.png` and judge side-by-side against the matching poster panel.

---

## HOW TO DRIVE EACH POSTURE LIVE (cheat sheet)

| Posture | Truest trigger | Console force | Hue (sacred) |
|---|---|---|---|
| rest / lavender | load `/`, idle | `setConversationPhase('idle')` | lavender |
| think / purple | type a chat message | `setConversationPhase('thinking')` | #b06eff |
| stream / cyan | a real cloud-Gemini code turn | `setConversationPhase('streaming')` + `__materializeTab()` | #7bf5fb |
| hold / orange | code result hits the approval gate | `window.__materializeApproval()` | #ff7e40 |
| complete / green | turn finishes | `setConversationPhase('complete')` or `__reabsorbMaterializedTab()` | #54f0a0 |
| error / warm-red | a turn errors | `setConversationPhase('error')` | warm-red |

Notes: `__POINTFIELD` and `__POSTURE` are dev-only and reset on reload — re-apply after any hard refresh. `__POINTFIELD` writes only land on uniforms that exist (`uSize, uGlowMul, uAttenK, uFogDensity, uRefDist`…); a real cloud-Gemini turn is the only way to exercise stream→hold→complete authentically (the bus auto-decays `complete`/`error` back to idle after COMPLETE_HOLD_MS / ERROR_HOLD_MS, so the being eases home on its own). Lock the P2 baseline FIRST — every other phase inherits its glow/exposure/vignette.

---

Key file paths for reference:
- `C:\Users\kumar\ai-editor\frontend\src\superbrain\lib\constants.ts` — bloomPoints, toneMappingExposure, vignettePoints, grade
- `C:\Users\kumar\ai-editor\frontend\src\superbrain\lib\pointFieldMaterial.ts` — uSize 2.8, uGlowMul 2.55, uAttenK, arrival scatter (L50), fragment weights (L127)
- `C:\Users\kumar\ai-editor\frontend\src\superbrain\lib\bodyPosture.ts` — tetrad posture map + POSTURE_DIAL (L88)
- `C:\Users\kumar\ai-editor\frontend\src\superbrain\components\canvas\BrainPointField.tsx` — `__POINTFIELD` proxy (L181), work-dim bodyTarget (L206)
- `C:\Users\kumar\ai-editor\frontend\src\superbrain\components\canvas\SuperbrainScene.tsx` — point counts (L909-911), points camera (L1594), `__POSTURE` (L241), canvas void #000000 (L1641), mode-tint indigo (L207)
- `C:\Users\kumar\ai-editor\frontend\src\superbrain\components\canvas\MaterializationLayer.tsx` — `__materializeTab` / `__materializeApproval` / `__reabsorbMaterializedTab` (L186+)
- `C:\Users\kumar\ai-editor\frontend\src\superbrain\lib\conversationPhaseBus.ts` — `setConversationPhase`, hold timings (L22-23)
- `C:\Users\kumar\ai-editor\frontend\src\workbench\GagosChrome.css` — mic listening pink deviation (L322-327, 352-354)
