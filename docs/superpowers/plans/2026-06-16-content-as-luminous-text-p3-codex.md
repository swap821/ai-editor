# P3 CONTENT REWORK — the work tab shows code as LUMINOUS 3D TEXT (no IDE) — Codex Build Spec

**Date:** 2026-06-16 · **Owner:** operator · **Planner/Reviewer:** Claude · **Writer:** Codex
**Base:** current `feat/living-being-p1` working tree
**Coordination task:** `content-luminous-text-p3-codex`

## 0. Why (operator verdict — confirmed broken)

The `kind:'content'` tab currently mounts a **Monaco IDE editor via `<Html transform>`** — a full desktop editor widget (chrome, scrollbars, grey theme) pasted onto a 3D plane, rendered massively oversized (~2300×7200px) and showing a **demo stub** instead of the real code. It reads as a **foreign 2D app inside the cosmic being** — incoherent, broken. Operator approved the fix: **the tab shows the code as luminous 3D text matching the being (read-only).**

## 1. The change — replace the content fill (NOT the whole primitive)

**Keep (good, don't touch):** the materialized-surface primitive, `kind:'input'` 3D box, `kind:'approval'` 3D Approve/Reject controls, **vertebra seating** (`SEGMENT_ANCHORS` / `materializedSurfaceAnchors`), the slide-from-vertebra motion, `tabStore`.

**Replace — `kind:'content'` rendering:**
- **Remove the `<Html transform>` + lazy `CodeCanvas`/Monaco entirely for content.** No DOM editor. (After this, the ONLY DOM left in the scene is the invisible typing-capture input — everything visible is pure 3D.)
- Render the code as **luminous 3D text** with drei `<Text>`:
  - **Monospace font** (load a mono typeface for drei `<Text>` via `font=` — e.g. a bundled mono .woff/.ttf in `public/`; if none, use the default but keep it mono-ish/legible).
  - **Color = the being's palette** (the cortex/nerve luminous hues — e.g. soft cyan/green on the dark slab), emissive/glowing, matching the brain. Read-only.
  - On a **being-styled surface**: a dark slab (near-black, `~0x05070d`) with a **luminous edge frame** in the palette (reuse the input box's frame look, larger). NOT a white/grey editor.
  - **Header**: a small luminous label (filename/language) in the palette — no IDE toolbar.
- **Size sanely (critical — the current one is 7200px):** fixed readable world scale; **clamp the displayed code** to a sensible window (e.g. first ~24–30 lines; if longer, show them + a dim "+N more lines" footer, or a gentle vertical drift — do NOT render the whole file at giant size). The slab stays a **readable luminous panel**, proportionate to the being, **not occluding the spine** (offset outward from its vertebra).
- **Bind the REAL code:** use `getLastEmittedCode()` (`{code, language, filepath}`) — the actual emitted code, not a demo stub. If empty, show nothing (don't spawn a stub tab).

## 2. Constraints / gates
- **Truly all-3D now:** content = drei `<Text>` on 3D meshes. **No `<Html>`/Monaco anywhere in the materialized content.** (The invisible typing-capture input is the only DOM, and it's not visible.)
- **Cortex/brain byte-identical.** **No new npm dep** (a bundled font file in `public/` is fine; prefer reusing any mono font already present — check first).
- Keep vertebra seating + slide motion + don't occlude the spine.
- **Gates green:** `npm run typecheck` + `npm test` (TDD any new pure logic — e.g. a code→displayed-lines clamp helper). Commit files. Remove the now-unused `CodeCanvas`/Monaco import from the content path.
- **Test on `:5173`** (CORS-allowed) — NOT `:5177` (the backend CORS allowlist is `:5173/:4173/:3000`; `:5177` is blocked and was why "nothing worked"). Verify the real chain there: work intent → approval box (vertebra) → Approve → tab slides from a vertebra showing the **real code as luminous 3D text**.

## 3. Verification (operator's browser, on :5173)
1. Work intent → approval box from a vertebra → Approve → a tab **slides from a vertebra** showing the **actual emitted code** as **luminous 3D text in the being's palette** on a dark glowing slab — **no IDE chrome, no grey editor, proportionate, spine not covered.**
2. It reads as **the being's own thought made visible**, coherent with the brain's look.
3. Brain at REST identical; conversation works; 60fps; no foreign 2D widget anywhere.

## 4. Handoff
- Task `content-luminous-text-p3-codex`. Claim the lease, rework `kind:'content'` → luminous 3D text, gates green, **test on :5173**, hand to Claude. Don't invent — `// CLAUDE?:` + flag. Commit files.
