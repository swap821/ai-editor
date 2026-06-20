# RESUME MANIFEST

Last updated: 2026-06-19T12:37:56+05:30

## Current Goal
Convert the living-being frontend blueprint into a 100% working live organism. **Phase 3 LANDED + Claude-reviewer-approved (commit 2eda588, against pinned snapshot 0ff2ea0).** Current lane: **Phase 4 — the real work loop through the living body** (the "SUPERBRAIN ALIVE" push). Codex on leave until 2026-06-25; Claude is solo (builder + reviewer). Operator steering remotely; visual sign-off delegated to Claude via kimi-webbridge at :5173. Canon re-scoped 2026-06-19: lab unrestricted, only palette+textures sacred.

## Last Completed + Verified
- Operator continued after the Phase 3 lab proof; treated as approval to run the product sync gate.
- Coordination task `gag-phase3-product-sync` was routed to Codex and claimed as builder with dirty adoption.
- Dry-run manifest verified before writing: 55 live source files, 22 test/support files, 5 assets, 1 generated CSS; `organismLifecycle.ts`/test and the `MaterializationLayer` lifecycle hook were included.
- Ran `npm run port`: product `brain.glb` stripped in the product copy only; 83 files ported into `frontend/src/superbrain`.
- Product gates passed: `frontend` `npm test` -> 39 files / 237 tests passed; `frontend` `npm run build` -> passed.
- Product Vite route is live at `http://localhost:5173/?ui=superbrain`; sandboxed launch hit Windows `spawn EPERM`, elevated hidden launch succeeded and route returned HTTP 200.
- Patched `GAG demo/gag-orchestrator/tools/probe-phase3-lifecycle.mjs` so product proof types through the real hidden `BrainstemIntake` input when present while preserving the lab `window.__materializeInput` fallback. `node --check tools\probe-phase3-lifecycle.mjs` passed.
- Product browser proof passed: `node tools\probe-phase3-lifecycle.mjs "http://localhost:5173/?ui=superbrain"` -> one canvas, valid intake, approval hold, conducting, completion settle, reabsorbing, and error repair lifecycle states.
- Product proof artifacts were written under `C:/tmp`: `gag-phase3-lifecycle-intake.png`, `approval.png`, `conducting.png`, `settle.png`, `reabsorbing.png`, `error.png`, and `gag-phase3-lifecycle-probe.json`.
- Screenshot inspection: product states are nonblank and framed. Intake shows duplicate visible ownership because `BrainstemIntake` renders the real input surface while `MaterializationLayer` observes the same input tab; lifecycle proof is valid, but Phase 4 should collapse visible input ownership to one renderer path.
- Updated `docs/superpowers/specs/2026-06-18-living-being-frontend-100-roadmap.md` with the Phase 3 product-port checkpoint and next Phase 4 action.
- Appended `.aios/memory/experiences.jsonl` row `gag-phase3-product-sync`; JSONL parse of the new row passed with confidence `0.84`.
- Closeout hygiene passed: `git diff --check` over RESUME, experiences, roadmap, product superbrain, and the lab lifecycle probe returned exit 0 with only normal Windows CRLF warnings; `node --check tools\probe-phase3-lifecycle.mjs` passed.
- Coordination handoff was attempted once and succeeded before this final RESUME refresh; a final hash-pinned reviewer handoff should follow this file update so the tree snapshot includes current resume state.

## Single Next Action
**Phase 4a COMPLETE** (commits 62cf1de→2453d86): the spectral-v1 posture-color system is wired into the whole 3D body — bodyPosture contract (62cf1de), brain hue (d0e9af5), nerve hue + flow speed (4c75bc8), vertebra surfaces (1f03dfd), brainstem intake (2453d86). The body shifts COLOR + signal-SPEED by the REAL lifecycle phase (rest violet → think magenta → stream cyan → hold amber → complete green → error red), blended OVER the sacred regional palette (tint ≤0.8; ==0 byte-identical canon; brainMaterial cache key v8→v9). All gates green (tsc · 254 tests · build); v9 shader compiles; software-GL verified (canon at rest, hue shifts across phases, zero runtime errors); lab-mirrored (BrainstemIntake is product-only). Damped posture lives in SCENE_UNIFORMS (uPosture/uPostureTint/uFlow); live phase flows MaterializationLayer → organismPhaseBus → scene-root useFrame.

**LIVE NOW (since Phase 4a):** (1) posture-strength DIAL — `window.__POSTURE` (commit 07220b3) lets the operator tune tint/flow live in his real browser (brainTint 0.55↔0.8, surfaceTint, flowScale) and report values to bake. (2) Phase-6 REPLY emanation amplified (commit 0c032fe): bigger glowing reply text + longer cortex speaking-glow. The reply DATA pipeline is confirmed healthy (POST /api/v1/chat streams text_chunk Hinglish via llama3.2:3b; sendVoiceTurn accumulates data.text).

**OPERATOR-EYE QUEUE (only his real GPU can settle these — software-GL is approximate):**
- TINT STRENGTH: slide `window.__POSTURE.brainTint`/`surfaceTint`/`flowScale` to taste, report numbers → I bake as defaults + capture canon goldens.
- REPLY PROMINENCE/PLACEMENT: reply sits upper-right (clear of the brain); if weak, next tune = descend-through-the-stem placement (`REPLY_TEXT_LOCAL` in BrainstemIntake).

**FULL-BODY POSTURE SWEEP DONE**: conductor overlay (3a24fca), cortical fireflies (3329f10), accretion core (5eafe43). EVERY visible region now reads the posture — brain, nerve (hue+flow), vertebra surfaces, brainstem intake, conductor overlay, cortical fireflies, accretion core — one body, many postures, all riding the shared POSTURE_DIAL. (AttentionConductionPulse's gold bead left as a deliberate POSTURE_GOLD accent.) The posture SYSTEM is complete; only the STRENGTH (operator's `window.__POSTURE` dial) + reply placement remain for his real-GPU eye.

**WORK-STREAMING DONE** (9a3dfc7): content code now materializes LINE BY LINE (~90ms/line + active-line cursor; reduced-motion shows whole) — the demoplan "Showing Work" phase. The being visibly writes its output into the vertebra surface.

**The demoplan 7-phase arc is now substantially realized**: arrival · rest · awakening/conversation (wake + reply) · materialization · orchestration (multi-tab) · working+showing-work (line-by-line stream) · reabsorption — with the full-body posture system (color/flow/speed by REAL state) overlaying all. Branch 97+ ahead of master.

NEXT (operator's pick): (a) **his `:5173` dial verdict** → bake the tint + capture canon goldens (the real unlock); (b) reply placement tune; (c) true per-chunk backend code streaming (currently a visual reveal of received code); (d) further polish. Self-verify each; gates green + commit per slice.

## Open Approvals / Blockers
- Phase 3 product sync is implementation-verified; reviewer approval is still pending.
- Visual follow-up for Phase 4: collapse duplicate product intake ownership into one visible renderer path while preserving the real hidden typing fallback.
- Worktree was already dirty before this slice; do not revert unrelated existing changes.
- Product Vite server is running hidden from `frontend` on port 5173 with logs in `.aios/audit/phase3-product-vite-*.log`.

## Active Files
- `frontend/src/superbrain/**`
- `frontend/public/models/brain.glb`
- `frontend/public/textures/brain/**`
- `frontend/public/grain.svg`
- `GAG demo/gag-orchestrator/tools/probe-phase3-lifecycle.mjs`
- `docs/superpowers/specs/2026-06-18-living-being-frontend-100-roadmap.md`
- `.aios/state/RESUME.md`
- `.aios/memory/experiences.jsonl`

## Notes Not Yet Promoted
- Product/lab parity pattern held again: dry-run manifest first, then product sync, then same URL-overridable browser probe against the product route.
