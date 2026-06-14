# RENOVATION RESUME — HUD GOAT build (live manifest)

> **Purpose:** if the 5hr usage limit pauses work, this secures exact continuity. On the operator's "resume" after the limit resets, read this + the [[frontend-harmony-direction]] memory, then CONTINUE — do not restart from scratch.
> **Updated at every wave boundary. Last update: 2026-06-14 — PAUSED at operator's 98%-usage flag, mid final-fix pass.**

## Mission
Deliver the **complete GOAT HUD renovation**: the 2D HUD overlay made honest (real backend signals, zero slop, anti-slop-critic + 8-check-rubric clean), reference-harmonized to the operator's **frozen brain + space** (his clean deep thinking, `components/canvas/**` + brain GLB/textures — NEVER touched). Soul: *"an autonomous agentic AI-OS superbrain constantly working its tools and moving forward in the deep-vast infinite space of knowledge."*

## STATUS: DELIVERED (2026-06-14) — GOAT HUD renovation complete
The full HUD renovation is BUILT (lab), PORTED to product, and CONVERGED. The GOAT bar is met: every hard gate green AND three independent review lenses returned `verdict:"clean"`.

- **Hard gates GREEN** (product tree): `npm run build` passes; canon-freeze OK (28 paths, 0 frozen — 3D scene byte-identical); css-canon lint clean; em-dash 0/0 (HUD + superbrain.css); no decorative emoji; no fake version stamps; **65/65 frontend tests pass**.
- **Official mount:** the clean root `localhost:5173` mounts the integration Shell (commit `74c3b68`); `?ui=shell` is a kept alias, `?ui=classic` the fallback, `?ui=home` the bare canon home.
- **Committed:** checkpoint `84dbf53` (full renovation, hard gates green) → official-root `74c3b68` → final-fix `<this commit>` (3 blockers + dead-CSS cleanup).

### The 3 final blockers — ALL FIXED + reviewer-confirmed clean (review wf_ae3a62f4-ffb: design-taste + ui-ux-pro-max + honesty, all `clean`, all three fixesConfirmed true)
1. **Amber hue drift — FIXED.** Every `#ffb454` → `var(--state-busy)` and every `rgba(255,180,84,A)` → `rgba(224,168,79,A)` across all safety surfaces (secure-button HOLD, command-error/offline, command-bar approval-hold, approval-panel). Link-down dot, approval-hold, offline-error, and FAIL verdict now share ONE canon amber (`#e0a84f`). (The lighter `#ffcf8a`/`#ffd9a0` approval-panel TEXT inks are intentional legibility foreground, AA ~10.8:1, not drift — left as-is. The only remaining `#ffb454` is in the frozen 3D `NeuralAura.tsx`, out of scope.)
2. **`.secure-button` 44px — FIXED.** Added `display:inline-flex; align-items:center; min-height:44px;` (WCAG 2.5.5), mirroring `.fidelity-button`. Topbar is 64px align-center, so no layout shift.
3. **Execute-arc honesty — FIXED.** `is-working` now excludes `turnState 'error'` (HUD) so the arc never engages on an offline submit (no turn began), plus belt-and-suspenders `.command-bar--state-error .execute-arc svg { animation:none }` (CSS). The ring cannot spin next to "Offline".
- Plus removed a dead/orphan `.command-search` selector (reviewer-flagged, zero visual effect).

### Deliberately deferred (documented, non-blocking — reviewers affirmed)
- `.execute-button` is 42px tall (clears the applicable WCAG 2.5.8 AA 24px; 44px is only AAA). Raising it is a discretionary *visual* change to the command bar I will not make without the operator's eye ([[fidelity-is-sacred-ui-laws]]).
- DEFERRED-AND-DOCUMENTED product capabilities (observe-before-operate, from the earlier waves): autonomy revoke, proposal apply/reject, memory consolidate/facts, alignment feedback/corrections, terminal/rollback.

## IF MORE WORK IS REQUESTED (this is a living manifest)
Lab-first always: edit `GAG demo/gag-orchestrator/src/...` → `npm run port` → at repo root `git checkout -- "frontend/src/superbrain/components/canvas/" "frontend/public/models/brain.glb" "frontend/public/textures/brain/" "frontend/public/grain.svg"` (restore the frozen 3D scene) → re-gate (`python tools/check_canon_frozen.py` · `python tools/check_css_canon.py` · em-dash + emoji scans · `cd frontend && npm run build && npm test`) → final confirmation review workflow → commit. Push/merge only on the operator's call.

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
