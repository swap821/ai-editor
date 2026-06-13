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
NEXT = the pixel-touching work, which needs his eye + before/after screenshots
per FIDELITY laws, in two groups:
  (a) interaction VISUAL states held back from polish III: :focus-visible,
      :hover (region-pin), :active press, .fidelity-button strong transition.
  (b) the remaining lenses: glass, motion, typography, spacing, cortex-shader,
      space-shaders (recovered findings in RECOVERED_micro_detail_findings.md).
Method unchanged: recovered findings -> Opus verify vs source -> apply in lab
-> vitest+lint+build green + goldens -> commit -> port -> commit product.

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
