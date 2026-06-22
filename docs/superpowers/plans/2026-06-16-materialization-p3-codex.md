# P3 — Materialization — Codex Build Spec

**Date:** 2026-06-16 · **Owner:** operator · **Planner/Reviewer:** Claude · **Writer:** Codex (sole frontend writer)
**Base (hash-pin):** `ba4434a` on `feat/living-being-p1` (P1 form + P2 conversation landed & approved)
**Coordination task:** `materialization-p3-codex`
**Master plan:** `docs/superpowers/specs/2026-06-16-living-being-frontend-design.md` §4 State 4 (MATERIALIZATION, decision A birth) + §5 (content bridge).

---

## 0. Goal

On a **work intent** ("write code…"), the being **grows a 3D tab out of a nerve**: a nerve reaches from the cortex into open space, a **3D slab unfurls at its tip**, the nerve stays as an **umbilical feeding it**, and **real content** (the code the being produces) appears **on a 3D surface** via drei `<Html transform>`. Start with **ONE** tab (the proof). The loved brain/cortex stays **byte-identical**; P1 growth + P2 conversation stay intact.

## 1. What already exists — REUSE, do not rebuild (cited)

- **DOM-on-3D bridge:** `@react-three/drei` `Html` (v10.7.7). Used in `frontend/src/workbench/ForgePorts.jsx:2,173,245` — but **projection-pinned** (`position` + `zIndexRange`), NOT `transform`. P3 must use **`<Html transform occlude>`** (drei supports it; not yet used) so the content obeys camera depth/rotation = a true 3D surface.
- **Real content:** `frontend/src/components/CodeCanvas.jsx` (Monaco editor) + `LivePreview.jsx` (iframe), both wired inside `ForgePorts.jsx` (editor line 230, preview line 255) with real workspace sync (`GET /api/v1/development/workspace`, ForgePorts:107–138). **Mounted only in the manufacturing shell** (`SuperbrainShell.jsx:46`), NOT the pure-3D home. Reuse `CodeCanvas` as the slab's fill.
- **Code data path:** `frontend/src/superbrain/lib/aiosAdapter.ts` — `sendDirective(text)` (line 373) streams `POST /api/generate` SSE; on a **`code`** frame (line 273) it stores the artifact and publishes cognition `knowledge-acquired` + label `'CODE EMITTED'` (line 280–286). `getLastEmittedCode()` (line 583) returns `{ code, language, filepath }`. (Chat path `sendVoiceTurn` = P2, no tools — leave it.)
- **Nerve-growth pattern:** `NervousSystem.tsx` `uGrow`+`aBirth` reveal (the spine birth) — a proven "grow a tube from a birth point" technique to **mirror** for the per-tab nerve. (Do NOT reuse the one-shot `NERVE_GROW_UNIFORM` itself — it's global/one-shot.)
- **Spine seats:** `SEGMENT_ANCHORS` exported from `NervousSystem.tsx:165` (12 anchors) — **for P4 multi-tab seating; not needed for P3.1.**
- **Canvas root:** `WorkspaceCanvas.tsx` renders `<SuperbrainScene>` (+ optional children). The new materialization mounts **inside the scene** (a child of the being's group or the scene), not as DOM chrome. `SuperbrainApp.jsx` passes **no** DOM children (pure-3D law) — keep it that way.

## 2. What's missing — the P3 build

Dynamic single-nerve spawn (on demand, not the one-shot spine), umbilical line, tab-birth tween, a reusable 3D slab (mesh + `<Html transform occlude>`), a tab-instance state store, and the content binding. All **additive** — a new component + a small store; do not modify the cortex or the existing spine/conversation.

## 3. Build — phased (each sub-phase is an operator browser-gate)

### P3.1 — ONE tab born from a nerve (the proof)
1. **Tab store** (`frontend/src/superbrain/lib/tabStore.ts`, new): a tiny store (plain module + `useSyncExternalStore`, or zustand if already a dep — check package.json; prefer no new dep) holding `tabs: [{ id, lifecycle: 'reaching'|'unfurling'|'live'|'retracting', originLocal: Vec3 (a cortex point), targetLocal: Vec3 (center-forward), content: {code,language,filepath}|null, bornAt }]`. P3.1 supports a **single** tab (array of length ≤1); P4 generalizes.
2. **Trigger (P3.1, keep simple):** subscribe to cognition `knowledge-acquired` with label `'CODE EMITTED'` (the existing signal) → if no live tab, **spawn one** and fill its `content` from `getLastEmittedCode()`. (Intent routing — which prompts call `sendDirective` vs `sendVoiceTurn` — see §4; for P3.1 you may also expose a dev trigger to spawn a tab with a stub file so the visual can be built/reviewed before the backend round-trip.)
3. **`MaterializedTab` component** (`frontend/src/superbrain/components/canvas/MaterializedTab.tsx`, new), mounted in `SuperbrainScene` (or a `MaterializationLayer` it renders):
   - **Nerve reach (`reaching`):** grow a thin `TubeGeometry` from `originLocal` (a point on the cortex surface, e.g. a frontal-lobe anchor) out to `targetLocal`, animated 0→1 over ~0.8–1.2s (tween a reveal like the spine's `aBirth`/`uGrow`, or scale the tube length). Wear a **nerve-family material** (reuse `makeBrainMaterial({bodyMode:'nerve', ...})` or a thin emissive line in the palette) so it reads as the being's own nerve. Cool→warm hue as it reaches.
   - **Slab unfurl (`unfurling`):** at the nerve tip (`targetLocal`), a 3D slab — a rounded-rect plane mesh (subtle emissive frame in the palette) — scales/opacity 0→1 (unfurl) over ~0.5s. Center-forward, camera-facing (billboard or fixed slight tilt).
   - **Umbilical (`live`):** the nerve **stays** as a thin tube between cortex and slab, with **data beads** flowing along it toward the slab (reuse the flow-band/particle idea or a few small emissive sprites tweened along the curve) — "it's feeding the tab."
   - **Content:** inside the slab, a `<Html transform occlude="blending" distanceFactor={…}>` hosting the reused **`CodeCanvas`** bound to `content.code`. Active tab = interactive (pointer events on); keep it lightweight.
4. **Camera:** optionally a gentle dolly/lookAt bias toward the slab when it's live (reuse `CameraDrift` focus, additively) — don't fight the canon framing; small.

### P3.2 — Live content streaming
- Bind the slab editor to the directive's **streamed** output so code appears **as the being writes it** (not just the final artifact). The current `code` frame arrives whole; if per-chunk streaming is needed, extend `aiosAdapter` to expose a `subscribe`-style hook for the active directive's `text_chunk`/`code` frames (additive export; don't change existing behavior). Beads on the umbilical pulse with each chunk.
- `LivePreview` (iframe) as a second surface is **optional/stretch** for P3.2.

## 4. Intent routing (chat vs work) — design point, simple default
- P2 sends every turn via `sendVoiceTurn` (chat). A **work intent** must instead go via `sendDirective` (tools → emits `code`). For P3.1 use a **simple heuristic** in the intake submit (e.g. leading verb match `/^(write|build|create|make|code|implement|fix|add|generate)\b/i` → `sendDirective`; else `sendVoiceTurn`), and **flag it `// CLAUDE?: intent-routing heuristic — refine later`**. Do not build a classifier. The operator will refine which intents materialize.

## 5. Constraints / gates (non-negotiable)
- **Cortex/brain byte-identical** — no edits to the cortex material/path. Materialization is a new layer; any shader reuse is the **nerve** path.
- **All-3D law** — the slab is a 3D surface via `<Html transform>` (obeys camera depth), NOT a flat 2D overlay/`zIndexRange` panel. No DOM chrome floating on the canvas. Waiting/blurred tabs (later) are static/cheap; the one active tab is interactive.
- **Don't regress P1/P2** — the spine growth, conversation flow, steady glow, 4-draw-call nerve bundles all stay. Materialization mounts additively.
- **Reuse** `CodeCanvas`/`getLastEmittedCode()`/`cognitionBus`; no second content/data stack. Prefer **no new npm dep** (use `useSyncExternalStore` for the store).
- **Perf:** one `<Html transform>` slab is fine; watch that the editor mounts only when a tab is live (lazy). Reduced-motion: shorten/skip the reach/unfurl tween, keep the slab.
- **Gates green** before each handoff: `cd frontend && npm run typecheck` + `npm test` (currently 128/128; TDD any new pure logic — e.g. the tabStore reducer + a reach-tween helper). Changed-file lint clean.
- **Final aesthetic = operator's browser** (`http://127.0.0.1:5177/`). Don't declare done — hand to Claude per sub-phase.

## 6. Verification (operator's browser, per sub-phase)
1. Issue a work intent (or dev-trigger) → a nerve **visibly reaches** out from the cortex, a **slab unfurls** at its tip, the **umbilical stays + beads flow**.
2. **Real code** shows in the slab (3D surface, obeys camera — tilt/orbit and it stays mapped to the plane, not a flat overlay).
3. Brain at REST identical to `ba4434a`; conversation (P2) still works; 60fps high-tier feel.
4. No 2D chrome; reduced-motion degrades motion not look.

## 7. Handoff protocol
- Task `materialization-p3-codex`, base `ba4434a`. Claim the writer lease, build **P3.1 → P3.2** (operator-gated between), run gates, hand to Claude (`agent_coord.py message`/`handoff`). The `verdict` CLI rejects on worktree-snapshot drift — a coordination `message` is the approval-of-record fallback. Don't invent on ambiguity — `// CLAUDE?:` + flag it. **Commit your new files** (don't leave them untracked — the P2 intake was untracked and nearly shipped dangling).
