# RESUME MANIFEST

## Current goal
MICRO-DETAIL POLISH LADDER of the superbrain frontend (standing mandate:
deep micro-detailing of every aspect, ultracode reviews, NEVER redesign;
FIDELITY IS SACRED). Work happens in the LAB (`GAG demo/gag-orchestrator/src`),
then ports to product `frontend/src/superbrain` via `npm run port`.

## Last completed and verified
- 2026-06-12/13 overnight: a 9-lens micro-detail audit ran on FABLE
  (workflow wf_846e66ec-ec8, ~1M tokens). It completed the REVIEW phase for
  all 9 lenses (132 unique findings) and shipped the POSTFX lens as
  **Polish I** (lab 64e2923 / product dc5d056: MSAA un-double-pay,
  luma-neutral highTint, corrected bloom-knee comments; 18/18 tests,
  canon-identical golden). The 5-hour usage limit killed the run at 01:11
  mid-verify; Fable is no longer available.
- 2026-06-13 (this session, Opus): RECOVERED the full audit from the dead
  session's agent transcripts. Durable artifacts written:
  `.aios/state/RECOVERED_micro_detail_findings.md` (all 132 findings, evidence
  + fix, per lens) and `.aios/state/recovered_846e66ec.json` (raw). Fable
  verified 17 findings before dying: 15 confirmed (real + canon-safe),
  2 rejected. The other ~115 are UNVERIFIED — Opus must re-verify each
  against the live lab source before applying.

## Single next action
LANDED so far: POLISH II = SOUND (lab d6096b4 / product e2552e1); recovery+
checkpoint 547cd6b (recovered findings committed — loss-proof); POLISH III =
INTERACTION a11y SEMANTICS (lab 47ec263 / product pending this commit):
RegionPins keyboard+aria-expanded, SOUND/mode aria-pressed, link role=status,
shield aria-live, ghost-plus tabIndex=-1, source-list aria-live flood removed.
Dropped the recovered stray-brace 'could' finding — the Next build REFUTED it
(needed closer; unverified findings must pass the build, not just sound right).
BACKEND FULLY RUNNING (verified 2026-06-13): uvicorn :8000 up (CORS incl
localhost:3000, model-load flags off), Ollama up (llama3.1:8b + gallery),
438 passed/1 skipped, REAL supervised turn proven end-to-end via POST
/api/generate — query_knowledge recall + create_file tool_call + human_required
approval gate (diff+token). Agent self-approval correctly BLOCKED (human
authority enforced). To complete a write, operator approves in the UI.
POLISH VII = chrome alignment LANDED (lab 06626d1 / product b18ca15): topbar
baselines, numeral tracking, console/spine/Execute-ring/spark/terminal spacing.
POLISH VIII = glass LANDED (lab b57ffa1 / product 0d6fd12): command-bar rim
restored (::before->::after), approval-panel canon glass recipe (saturate+
brightness+webkit, radius 14, grain, position:relative), hairline tokens.
REMAINING (all in vetted_polish_findings.json, operator live on :3000, full
trust, apply-in-groups mode): console-glow rim restoration (CSS selector +
console-glow JSX in both asides); GALAXY resting-frame (color-space sRGB->linear,
weak-star floor, glyph-atlas mip gutter); CORTEX VII casing (IGN dither,
approval-hold amber on casing, BRAIN_SCALE single-source, comments); spacing
approval-panel anchoring; 2 HELD (approval-panel entrance, objective scaleX);
section-label-weight taste call. Goldens need RECAPTURE once the look settles.
HISTORICAL:
POLISH VI = signal + galaxy lifts LANDED (lab 61460c0 / product 253ff17):
firefly cutoff smoothstep, aFlash mount-flash suppress, galaxy/quarantine
twinkle frequency separation. NEXT = POLISH VII = cortex casing (SuperbrainScene
.tsx, needs careful read): casing IGN dither, approval-hold amber on casing,
hold-amber + ladder COMMENTS, BRAIN_SCALE single-source. THEN operator-eye phase
(he's live on :3000, gave full trust): 25 resting-frame findings + 2 held
(approval-panel entrance, objective-bar scaleX) — all catalogued in
vetted_polish_findings.json. KNOWN DEBT: MemoryGalaxy has 3 pre-existing
react-hooks/immutability lint errors (r3f useFrame pattern, not build-blocking).
BACKEND: not running (:8000 down); superbrain shows honest LINK OFFLINE on the
:3000 preview. Binding is real + proven; start uvicorn (+ CORS localhost:3000)
to see live data.
HISTORICAL:
POLISH V = motion + token hygiene LANDED (lab 648291e / product 66deae3):
ease-loop token, mono hygiene, tabular-nums, interaction-only transitions,
hover-hairline unify, region-pin open spacing. Verify workflow wf_81181352
output persisted to .aios/state/vetted_polish_findings.json (49 apply-ready,
6 rejected). NEXT = POLISH VI = safe shader/galaxy lifts (zero-pixel/interaction
-only from cortex-shader + space-shaders): casing dither, firefly cutoff
smoothstep, approval-hold amber on casing, BRAIN_SCALE single-source, hold-amber
+ ladder COMMENTS, galaxy twinkle freq separation, aFlash mount-flash suppress.
THEN the operator-eye phase (he's live on :3000): 25 resting-frame findings +
2 held (approval-panel entrance, objective-bar scaleX). 6 rejected stay dropped.
HISTORICAL:
POLISH IV = interaction VISUAL states LANDED (lab 576cd0c / product 2c23235):
focus-visible (white-alpha), region-pin hover/active, mode-button active,
fidelity-button strong transition + active, approval-actions press. Interaction
lens now COMPLETE. Operator delegated full trust ("100% trust") for the rest +
authorized workflow fan-out; lab dev server running on :3000 for live preview.
NEXT = remaining pixel lenses: glass(18) motion(23) typography(19) spacing(10)
cortex-shader(7) space-shaders(7). Running a READ-ONLY verify workflow first
(the verify phase the limit killed) -> apply each lens MYSELF (single writer)
from the vetted list -> lab build+goldens green -> commit -> port -> product
build -> commit. KEY LESSON: verify every finding vs LIVE source by content,
never trust cited line numbers (the stray-brace finding was wrong).

--- (historical) POLISH II detail ---
POLISH II = SOUND was DONE in the lab working tree (now committed), verified:
rewrote `src/lib/soundEngine.ts` + added `src/test/soundEngine.test.ts`
(8 tests). Fixes: VERIFICATION RED bug (no longer the success tick),
release-then-stop pop fix, tick-stagger + safety compressor, audible reject
thud (+hum duck), suspend/reopen/auto-resume guards, real ambient beat, and
an ADDITIVE dark-event palette (TRAIL WEAKENED / LINK LOST+ESTABLISHED /
AUDIT CHAIN BROKEN tamper alarm). Full vitest 26 passed, lint clean, `npm run
build` green. Zero-visual-cost so goldens unaffected (no screenshots needed).
NEXT: (1) operator decision — commit+port sound now? keep the additive
palette? (2) then INTERACTION/a11y lens (also zero-visual-cost: keyboard,
focus-visible, aria). Then the pixel-touching lenses (glass, motion,
typography, spacing, cortex-shader, space-shaders) — each REQUIRES
before/after screenshots in HIS browser + his pick per FIDELITY laws.
METHOD (operator-confirmed): drive from the recovered findings on disk
(`.aios/state/RECOVERED_micro_detail_findings.md`), Opus verifies + applies
each lens; do NOT spend tokens on a new review workflow.

## Open approvals/blockers
- Applying any lens = YELLOW: needs operator go. Visual lenses additionally
  need before/after screenshots in his browser (FIDELITY IS SACRED).
- Commit only when the operator asks (per AGENTS.md §XI).
- Stale parent-tree checkpoint pending (.gitignore for GAG demo/ + state).
- Codex POST-HOC reviews due ~2026-06-16 (inbox msgs 14,15,16).

## Notes not yet promoted
- Recovered findings include limit-retry semantic duplicates (e.g. postfx
  "MSAA double-pay" == "Composer MSAA is 0"); consolidate per lens when working.
- 2 Fable-rejected: postfx vibrance>1.0 overshoot, glass approval-panel shadow
  recipe — re-judge, don't assume.
- Recovery method (reusable): parse `subagents/workflows/<wf>/agent-*.jsonl`,
  extract StructuredOutput tool_use inputs (see `.aios/tmp/recover_846e66ec.cjs`).
  resumeFromRunId is same-session only; cross-session = salvage from jsonl.

## Runtime
Brief: `.venv\Scripts\python agent_coord.py brief --agent claude`
Backend: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000`
Frontend: `cd frontend; npm run dev`
Tests: `.venv\Scripts\python -m pytest -q`  (baseline 438 passed, 1 skipped)
Lab build/goldens: `cd "GAG demo/gag-orchestrator"; npm run build`; goldens in `goldens/`
Port lab->product: `npm run port` (manifest-drift tripwired)
Recovered findings: `.aios/state/RECOVERED_micro_detail_findings.md`
