# RENOVATION RESUME — HUD GOAT build (live manifest)

> **Purpose:** if the 5hr usage limit pauses work, this secures exact continuity. On the operator's "resume" after the limit resets, read this + the [[frontend-harmony-direction]] memory, then CONTINUE — do not restart from scratch.
> **Updated at every wave boundary. Last update: 2026-06-14 — PAUSED at operator's 98%-usage flag, mid final-fix pass.**

## Mission
Deliver the **complete GOAT HUD renovation**: the 2D HUD overlay made honest (real backend signals, zero slop, anti-slop-critic + 8-check-rubric clean), reference-harmonized to the operator's **frozen brain + space** (his clean deep thinking, `components/canvas/**` + brain GLB/textures — NEVER touched). Soul: *"an autonomous agentic AI-OS superbrain constantly working its tools and moving forward in the deep-vast infinite space of knowledge."*

## EXACT STATE AT PAUSE (2026-06-14)
- **The full HUD renovation is BUILT in the lab and PORTED to product.** All 6 panels done honest.
- **Hard gates GREEN** on the current product tree: `npm run build` passes; canon-freeze OK (28 paths, 0 frozen); css-canon lint clean; em-dash 0/0 (HUD + superbrain.css); no decorative emoji; no fake version stamps. The frozen 3D scene is byte-identical (restored after port).
- **One fix already applied + ported this session:** removed an em-dash from the port script's generated CSS font-header comment (`GAG demo/gag-orchestrator/tools/port-to-frontend.mjs` line 66: `next/font; here` instead of `next/font — here`), then re-ported so `superbrain.css` is clean.
- **`npm test` (frontend vitest) NOT yet re-run this session** — run it on resume before/with the commit.
- **Working tree (uncommitted):** `frontend/src/superbrain/components/ui/SuperbrainHUD.tsx` + `frontend/src/superbrain/superbrain.css` modified (the full renovation). Also `GAG demo/...` is a gitignored nested repo (lab edits live there, not staged by the product repo). The em-dash fix to the port script is in the lab tree.

## THE 3 PENDING BLOCKERS (final-confirmation review wf_87c30df1-6f0 — COMPLETED; output captured below; all 3 still UNFIXED)
All three are GENUINE, in-scope, not-already-covered, and each matches a discipline already applied elsewhere in the file. **Fix all three LAB-FIRST** (`GAG demo/gag-orchestrator/src/app/globals.css` + `.../components/ui/SuperbrainHUD.tsx`), then re-port.

1. **Amber hue drift (design-taste lens).** The brain-dot fix unified privacy hues onto canon `--state-busy #e0a84f` to kill near-duplicate ambers ("one color per state"), but the LOUDEST safety surfaces still hardcode a brighter amber `#ffb454` / `rgba(255,180,84,*)`. Occurrences in `globals.css`: lines **654, 655, 1767, 1774, 1775, 2366, 2367, 2371, 2375, 2466, 2468, 2485, 2553, 2554, 2559** (secure-button HOLD, command-error/offline, command-bar approval-hold, approval-panel). Some comments even mislabel `#ffb454` as "the canon busy/fail hue." **Fix:** replace every `#ffb454` with `var(--state-busy)` (or `#e0a84f`) and every `rgba(255, 180, 84, A)` with `rgba(224, 168, 79, A)` (canon `--state-busy` = rgb 224,168,79), preserving each rule's existing alpha. Correct the mislabeling comments. (Decision: unify, per the brain-dot precedent — do NOT introduce a new distinct hold-amber.)

2. **`.secure-button` touch target < 44px (ui-ux-pro-max lens).** The security shield (Supervised / HOLD / TAMPER) is the most consequential safety control yet `.secure-button` (`globals.css` lines **440-452**: `padding:8px 14px; font-size:11px;` no min-height) computes ~28-30px tall. Its sibling `.fidelity-button` already got `min-height:44px` (WCAG 2.5.5) at lines 2395-2413. **Fix:** mirror that — add `display:inline-flex; align-items:center; min-height:44px;` to `.secure-button` (sits in a 64px `align-items:center` topbar, so the hit box grows without shifting the visible layout). Add the same WCAG-2.5.5 rationale comment.

3. **Execute arc spins during offline-error (honesty-rubric lens).** `SuperbrainHUD.tsx` applies `is-working` when `turnState !== 'idle'` (line ~**1608**), which INCLUDES `'error'`. On an offline submit `handleSubmit` (~1077-1087) sets `turnState='error'` with an explicit "DO NOT pretend a turn began" comment — but `globals.css` (lines **1976-1994**) then expands + infinitely spins `.execute-arc svg`, stopped ONLY by `.command-bar--state-done`. So a perpetual "working" arc spins next to "Offline" though nothing is in flight (cardinal honesty-law violation; the arc comment ~1620-1622 claims it "spins only while a real turn is in flight"). **Fix (cleanest):** exclude `'error'` from `is-working` in the HUD (so the arc never engages on error) AND/OR add `.command-bar--state-error .execute-arc svg { animation: none }` + collapse the arc width/opacity in the error state. Verify the arc's own comment stays truthful after the fix.

## ON RESUME (operator says "resume") — do these IN ORDER
1. Read this + [[frontend-harmony-direction]]. Restart backend/frontend if down; re-arm the supervision monitor.
2. Apply the **3 pending blocker fixes** above, LAB-FIRST (globals.css + SuperbrainHUD.tsx in `GAG demo/gag-orchestrator/`).
3. `cd "GAG demo/gag-orchestrator" && npm run port` → back at repo root `git checkout -- "frontend/src/superbrain/components/canvas/" "frontend/public/models/brain.glb" "frontend/public/textures/brain/" "frontend/public/grain.svg"` (restore the frozen 3D scene the port re-touches).
4. Re-gate: `python tools/check_canon_frozen.py` · `python tools/check_css_canon.py` · em-dash scan (HUD + superbrain.css) · emoji/stamp scan · `cd frontend && npm run build` · `npm test`.
5. Re-run a final confirmation review (small workflow, the 2 design lenses + honesty lens, briefed with the now-RESOLVED list incl. these 3) to confirm clean. The convergence bar = gate green + reviewers find no new in-scope genuine defect.
6. Commit the full HUD renovation on `feat/frontend-renovation`. Update this doc + [[frontend-harmony-direction]] + CEO_LOG.
7. **Deliver the GOAT** for the operator's eyeball at `:5173 (clean root — the official mount as of 2026-06-14; ?ui=shell kept as an alias)` (brain+space byte-identical). Push/merge only on his call.

## DOCUMENTED JUSTIFIED DECISIONS (NOT defects — do not re-litigate)
- `center-ports` div is `aria-hidden="true"` ON PURPOSE: the same 4 channel values are exposed accessibly by the KNOWLEDGE INTAKE console (`SourceRow`, `aria-label="System status"`, not hidden); hiding the floating visual duplicate avoids double-announcing to screen readers.
- The 5 inline SVG marks (HexMark/ShieldIcon/AgentIcon) are hand-rolled ON PURPOSE: the lab may not add an icon dependency (the port manifest copies an explicit file list); unified into one 24x24 stroke family. Documented exception in the file.
- The Google Fonts `@import` in `superbrain.css` is port-generated + deliberate (local-first with honest system fallbacks).
- `PHASE_COPY` / `PHASE_LABEL` prose truthfully describes the REAL derived phase (honest, not theatre). The "unit-tested" comment is TRUE (`src/test/livePhase.test.ts` exists).

## Where things are
- **Branch:** `feat/frontend-renovation` (baseline rollback tag `pre-renovation-baseline-2026-06-14`).
- **Lab (source of truth, gitignored nested repo):** `GAG demo/gag-orchestrator/` — HUD `src/components/ui/SuperbrainHUD.tsx`, tokens `src/app/globals.css`, port `tools/port-to-frontend.mjs`.
- **Key docs:** `.aios/state/HUD_REFERENCE_LANGUAGE.md` (reference + 8-check rubric), `HUD_RENOVATION_SPEC.md`, `FRONTEND_HARMONY_MAP.md`, `FRONTEND_RENOVATION_BLUEPRINT.md`, `RENOVATION_REVIEW.md`.

## Live runtime (may need restart after a long pause)
- Backend: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000 --reload`.
- Frontend: `cd frontend; npm run dev` → `:5173 (clean root — the official mount as of 2026-06-14; ?ui=shell kept as an alias)`.
- Supervision monitor (sacred-scene + liveness): re-arm after a session restart.

## Gates every wave must pass
canon-freeze (`tools/check_canon_frozen.py` — brain+space frozen) · css-canon lint (`tools/check_css_canon.py`) · em-dash 0 file-wide · no decorative emoji · no fake stamp · `npm run build` · `npm test` · anti-slop critic + the 8-check rubric (HUD_REFERENCE_LANGUAGE.md).
