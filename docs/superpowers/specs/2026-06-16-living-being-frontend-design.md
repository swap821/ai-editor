# Living-Being Frontend — Design Spec

**Date:** 2026-06-16
**Status:** Locked (operator-approved via visual brainstorm, 2026-06-15→16)
**Owner:** operator (kumarswapnil82)
**Supersedes the framing of:** the current "Supermind" HUD (a 2D dashboard with a 3D brain ornament). It does **not** delete existing primitives — it re-composes them.

---

## 1. The shift in one sentence

Today the frontend is **a dashboard with a brain in it.** This spec rebuilds it into **a living being whose body *is* the interface** — you open the URL, the being arrives; you talk to it; it grows 3D tabs out of its own nervous system to do your work; and when there are many, it docks small and conducts them from its spine.

This is an **architectural change, not a reskin**: the interface moves off the 2D DOM overlay and *into* the 3D (React Three Fiber) scene.

## 2. The one law (governs every decision)

> **Everything you see is either *part of* the being or *grew out of* it. Nothing flat floats on top.**

Concretely: no 2D HUD panels, no corner chat bar, no topbar of chips layered over the canvas. Panels are 3D surfaces in space connected by nerves; text lives in the scene; status is read off the body. The current `SuperbrainHUD.tsx` (DOM/`motion/react`/`createPortal`) is the thing this law retires.

## 3. Supporting laws (the "deeper than the beat" principles)

1. **Continuity of self — one body, four postures.** Resting → attentive → working → conducting are the *same creature* re-posturing. Never a cut, never a page-swap. **The transitions ARE the product** (this is exactly what felt hollow before).
2. **Attention is the interaction model.** You don't "select a tab" — the being *looks at / pulls forward* the tab it's working. The attended thing is the active thing. This removes most conventional UI chrome.
3. **The nerve carries the status — so there is no status chrome.** A nerve's color / pulse / bead-flow *is* the state: thinking, streaming, done, errored. The body reports on itself.
4. **The spinal cord is the being's own body — and its conductor.** The spine + vertebrae are **integral anatomy of the being, not a tool that appears.** The brain and its spinal cord are **one continuous body, present in every state** — exactly as a real brain and spinal cord are a single nervous system. At rest it reads as the **brainstem** the user speaks into (coiled/short). As work begins, that same cord **extends and reveals its vertebrae**, and **each vertebra holds a tab.** The being never sprouts a separate "UI spine" — the spine *is* the being. One organ, one body, rest → conduction.
5. **Birth and reabsorption.** Tabs are *born from* the being (a nerve reaches out) and *die back into* it (nerve retracts, tab dissolves). Nothing merely "opens" or "closes."
6. **The voyage never stops.** The knowledge-field always drifts past; the being always breathes. Even docked over a workspace, it is travelling. (Honors the locked core theme: "an autonomous AI-OS superbrain travelling constant into the deep-vast knowledgeable infinite space.")

## 4. The lifecycle (the being's states + locked decisions)

### State 1 — ARRIVAL  *(decision: A first-load, C every return)*
- **A · Coalescence (first-ever load):** the voyaging knowledge-field streams inward and *condenses into a mind* — particles becoming cortex, a first ignition pulse, then settle and breathe. ~3–4s, cinematic. It is born from the data it travels through.
- **C · Awakening (every return):** the being is already there but dormant/dark; the user's arrival ignites a seed of light that spreads through the cortex, nerves lighting outward. It was asleep; the user woke it.
- Both settle into State 2.

### State 2 — REST + FIRST CONTACT  *(decision: B — brainstem intake)*
- The being floats centered, large, breathing, voyaging. Minimal scene; a quiet invitation to speak.
- **The spinal cord is present at rest** — part of the being's anatomy, reading as a short brainstem descending from the cortex (not yet extended into vertebrae). The brain and cord are one body even when idle.
- **How you talk to it (B):** a glowing **intake at the base of the brainstem**; the user's words flow **up the spine** into the mind; the reply pulses **back down** and emanates from the cortex (voice + in-scene text). The "console" is a body part, not a panel.
- Blend with A's minimalism: **voice-first; the typed input appears only when the user types**, and even then it is in-scene (light condensing at the intake), never a persistent flat bar.
- **Status (brain/model, latency, supervised/autonomous) reads off the body** — glow, color, posture — not a topbar.

### State 3 — AWAKENING / CONVERSATION
- The being notices the user (attentive lean toward pointer/voice — the existing `CURSOR_ATTENTION` micro-motion elevated), cortex brightens, nerves light from the core. It talks back *as the being*.

### State 4 — MATERIALIZATION  *(decision: A birth, re-anchor to spine for multi — "A+C")*
- On an intent that needs a workspace ("write code", "play youtube"), the being **grows a 3D tab from its nervous system**:
  - **Birth motion (A):** a nerve **grows out from the cortex** into open space; the tab **unfurls at its tip.** Clear cause→effect: "it made this for me." The nerve stays as the **umbilical** and feeds the tab (data beads flow along it).
  - **On the 2nd tab:** tabs **re-anchor onto the spine** (transition into State 5). A and C are not rivals — one tab's life flows into many tabs' orchestra.
- **Real content inside:** the tab hosts real DOM content (a real code editor, a real youtube embed) **mapped onto a 3D surface** via drei `<Html transform>` so it obeys the camera and depth. This is the bridge that makes "everything is 3D" buildable with real content.

### State 5 — ORCHESTRATION  *(decision: B + (A+C), centered — operator-corrected)*
The locked composition:
- **The being's spinal cord descends from the brain, dead-center, vertical** — it is the *same anatomy* as the rest-state brainstem, now extended. The **mini-brain docks directly on top (B)**, brain-and-cord still one continuous body. The cord is segmented into **vertebrae, and each vertebra holds a tab** (a tab is never free-floating — it is seated in a vertebra of the being's own spine).
- **The focus tab sits dead-center and forward (A)** — large, bright, readable — fed by the spine (data flows down the spine into it). It is whichever tab the being is currently working.
- **The other tabs stay nerve-connected but WAITING (C)** — small, dim, blurred, idling at depth (corners/around), each with a soft "waiting" pulse, ready to be **pulled to center** when the being turns its attention to them.
- **Attention conducts:** the being's attention slides along the spine; the attended vertebra is pulled to the center-forward stage while the previous one recedes back to waiting. The mini-brain leans toward whoever it's attending.
- **Mini-brain size is responsive** — it flexes with **tab count + screen size** (more tabs / smaller screen → smaller brain). Exact curve is a deferred tuning decision (see §8), specified as a rule, not a fixed value.

### State 6 — WORKING / SHOWING ITS WORK
- Each tab shows the being's present work *live* (code streaming into the editor, a page resolving). The user reads what it's doing **from the being itself**: the attended tab is forward+bright, its nerve flows beads; idle tabs wait. No separate progress chrome.

### State 7 — REABSORPTION
- On done/dismiss: the nerve **retracts**, the tab **dissolves back into** the being (reverse of birth), it returns toward center, breathes, waits. With multiple tabs, removing one re-balances the spine.

## 5. Architecture

- **Stack (existing, reused):** React Three Fiber + drei + three; `frontend/src/superbrain/components/canvas/*`. The cognition bus (`cognitionBus.ts`), metrics store, and AIOS adapter (`aiosAdapter.ts`) remain the data plane.
- **The core move:** retire the DOM-overlay HUD (`SuperbrainHUD.tsx`) as the primary UI; relocate its responsibilities into the scene:
  - intake/conversation → brainstem intake geometry + in-scene text.
  - status → read off the body (cortex hue/glow, posture, nerve state).
  - tabs/workspace → in-scene 3D slabs hosting real content via drei `<Html transform>`.
- **Existing primitives to re-compose (not rebuild):** cortex shaders + brain (`SuperbrainScene`, `OrganSurface`, `CorticalSignals`), space-colonization nerve tree (`NervousSystem.tsx`), packet/data beads, `CURSOR_ATTENTION` lean, `WorkspaceCanvas`/WorkspaceIDE slab, `CosmicBackground`/voyage, `MemoryGalaxy`, `RegionPins`.
- **New systems to build:** (a) the **lifecycle/posture state machine** (rest→attentive→working→conducting with continuous transitions); (b) the **materialization system** (nerve-reach → slab bloom → umbilical feed); (c) the **anatomical spinal cord** — modeled as part of the being's body (brain → brainstem → segmented vertebrae as one rig), that *extends* from the rest-state brainstem into the centered conductor; tabs are **seated in vertebrae** (center-forward focus, waiting vertebrae, responsive mini-brain), never free-floating; (d) the **DOM-on-3D-slab content bridge**.
- **Real content bridge detail:** `<Html transform occlude>` slabs positioned/oriented in the scene; the active slab is interactive (pointer events), waiting slabs are lightweight/static thumbnails to keep cost down; promote-to-interactive on focus.

## 6. Verification (operator's standing FIDELITY laws — non-negotiable)

- **Proof in HIS browser** for every visual change; the final aesthetic call is always his browser, never a test.
- **Before/after screenshots** for every visual change.
- **No auto-degrade ever** — quality tiers must never silently downgrade his canon look.
- **Canon tag + goldens before visual work**; his authored assets/textures untouched.
- All existing gates stay green (tests, tsc, lint — current baseline 80/80).
- **First proof artifact:** the **opening scene** (Arrival → Rest → first Awakening) built and shown in his browser **before** any further state is built (see §7).

## 7. Scope & phasing (build order)

Implementation will use the available design skills (`impeccable`, `frontend-design`, `design-motion-principles`, `ui-ux-pro-max`) and the Figma MCP where useful — and proceed phase-by-phase with operator sign-off in his browser between phases:

- **P1 — The Opening (proof):** Arrival (A coalescence) → Rest (breathing, brainstem intake visible) → first Awakening on speak. This is the single most important moment and the trust proof. Ship and review before P2.
- **P2 — Conversation + status-off-the-body:** talk/reply through the brainstem; retire the HUD's conversation/status panels.
- **P3 — Materialization:** one tab born from a nerve (A), real content via `<Html transform>`, umbilical feed. Reuse the WorkspaceIDE slab as the first real content.
- **P4 — Orchestration:** 2+ tabs → dock mini-brain on top, center spine conductor, center-forward focus + waiting vertebrae (B+(A+C)), responsive mini-brain, attention switching.
- **P5 — Reabsorption + polish:** dismiss/retract, edge cases, motion-detailing pass, accessibility/reduced-motion, performance tiers (without auto-degrading canon).

## 8. Deferred decisions (tune during build, not blockers)

- Exact **responsive mini-brain sizing curve** (tab count × viewport).
- Exact **camera language** for arrival/approach and for focus-switching (dolly vs. tab-moves).
- **Waiting-tab placement geometry** at high tab counts (corner cluster vs. arc vs. shallow orbit) — start with the corner/depth model from the locked mockup.
- **Voice** specifics (TTS voice, when it speaks vs. shows text).
- Reduced-motion and low-power fallbacks (must degrade *motion*, never the canon *look*).

## 9. Out of scope (YAGNI for this redesign)

- No backend protocol changes beyond what's needed to stream code/content into a tab (the existing SSE/text path is the data source; a structured `code` frame is a separate, optional backend track).
- No new product features (no new organs/ports beyond re-homing existing ones into the scene).
- No multi-user / collaboration.

## 10. Provenance

Decisions locked through a visual brainstorm on 2026-06-15→16 (storyboards under `.superpowers/brainstorm/`): Arrival **A→C**; Rest **B (brainstem)**; Materialization **A+C**; Orchestration **B+(A+C), centered** (operator correction: spine center, focus center+forward, others nerve-tethered-but-waiting/small/at-depth, mini-brain responsive).
