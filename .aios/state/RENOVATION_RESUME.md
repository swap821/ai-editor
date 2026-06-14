# RENOVATION RESUME — HUD GOAT build (live manifest)

> **Purpose:** if the 5hr usage limit pauses work, this secures exact continuity. On the operator's "resume" after the limit resets, read this + the [[frontend-harmony-direction]] memory, then CONTINUE — do not restart from scratch.
> **Updated at every wave boundary.** Last update: 2026-06-14, during HUD build wave 1.

## Mission
Deliver the **complete GOAT HUD renovation**: the 2D HUD overlay made honest (real backend signals, zero slop, anti-slop-critic + 8-check-rubric clean), reference-harmonized to the operator's **frozen brain + space** (his clean deep thinking, `components/canvas/**` + brain GLB/textures — NEVER touched). Soul: *"an autonomous agentic AI-OS superbrain constantly working its tools and moving forward in the deep-vast infinite space of knowledge."*

## Where things are
- **Branch:** `feat/frontend-renovation` (baseline rollback tag `pre-renovation-baseline-2026-06-14`).
- **DONE + committed:** Waves 0-9 (CSS lint + forge.css; 10 organ ports incl. Conversation/Answer; approval safety-net; CSS-debt; default-home mount); canon-freeze guard re-scoped to brain+space-only and hardened (catches untracked).
- **Key docs:** `.aios/state/HUD_REFERENCE_LANGUAGE.md` (the reference + 8-check rubric), `.aios/state/HUD_RENOVATION_SPEC.md` (the renovation spec — being revised honest by wave 1), `.aios/state/FRONTEND_HARMONY_MAP.md`, `.aios/state/FRONTEND_RENOVATION_BLUEPRINT.md`, `.aios/state/RENOVATION_REVIEW.md`.

## In flight (resume target)
- **Wave 1 — `hud-build-wave1-cognition`** · runId `wf_3497c120-f6f` · scriptPath `C:\Users\kumar\.claude\projects\C--Users-kumar-ai-editor\d72ea5c4-d65d-473c-a912-9e8b1fc978f7\workflows\scripts\hud-build-wave1-cognition-wf_3497c120-f6f.js`
  - Phases: REVISE spec honest → BUILD the LEFT "ACTIVE COGNITION" panel lab-first → port + gate (3D frozen) + rubric review.
  - **If it died mid-run:** resume with `Workflow({scriptPath, resumeFromRunId: "wf_3497c120-f6f"})` — completed agents return cached (per [[workflow-limit-recovery]]; NEVER relaunch fresh / drop work).

## Next steps (the path to GOAT, in order)
1. Gate-verify wave 1 (canvas byte-untouched, build+tests green, anti-slop critic clean, 8-check rubric pass). Commit if clean; else fix.
2. **Full build** — remaining HUD panels in one coherent honest pass: intake (KNOWLEDGE INTAKE + AGENT MESH), center ports, terminal log, topbar/sovereignty, command bar. Lab-first (`GAG demo/gag-orchestrator/src/components/ui/SuperbrainHUD.tsx` + `app/globals.css`) → `npm run port`.
3. **Convergence loop:** build → adversarial anti-slop review + 8-check rubric → fix → repeat until the critic finds nothing. That loop IS the GOAT bar.
4. Final: deliver the whole HUD on `:5173/?ui=shell`, brain+space byte-identical; commit + (operator's call) push branch.

## Live runtime (may need restart after a long pause)
- Backend: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000 --reload` (was bg `bd1vzeytl`).
- Frontend: `cd frontend; npm run dev` → `:5173/?ui=shell` (was bg `bjvun18vf`).
- Supervision monitor (sacred-scene + liveness): was `b8agz81qs` (re-arm after a session restart).

## Gates every wave must pass
canon-freeze (`tools/check_canon_frozen.py` — brain+space frozen) · css-canon lint (`tools/check_css_canon.py`) · `npm run build` · `npm test` · anti-slop critic + the 8-check rubric (HUD_REFERENCE_LANGUAGE.md).

## ON RESUME (operator says "resume")
Read this + [[frontend-harmony-direction]]. Check wave `wf_3497c120-f6f` status (resume via resumeFromRunId if incomplete). Confirm backend/frontend up (restart if needed) + re-arm the supervision monitor. Then continue at the first unchecked "Next step" above. Drive to convergence; deliver the whole.
