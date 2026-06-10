# RESUME MANIFEST

## Current goal
Improve human-system communication through continuous, inspectable alignment
while keeping every action supervised, local-first, and fail-closed.

## Last completed and verified
2026-06-10 Communication Alignment slices 1-6 complete:
- `UnderstandingFrame` now makes goal, intent, outcomes, constraints,
  assumptions, unknowns, decisions, confidence, and next action inspectable.
- Model proposals are secret-scrubbed, bounded, validated, and always advisory;
  they cannot approve actions, change zones, establish facts, or count as evidence.
- `/api/generate` emits the frame over SSE and persists its latest validated form
  under a hashed session key; the frontend restores dialogue and alignment.
- The Alignment Panel exposes the frame plus explicit `direct`, `collaborative`,
  or `explanatory` communication mode.
- A deterministic `proceed` / `state_assumptions` / `ask` policy now governs
  ambiguity. Only explicit clarify-first or context-free vague requests pause
  before tools; lesser uncertainty is visibly labeled unverified.
- Active clarification wording is deterministic and never model-proposed.
- Users can directly correct interpretation fields from the Alignment Panel.
- Corrections are validated, secret-scrubbed, and provenance-labelled as
  user-authored communication context; unsupported authority-like fields fail.
- Active corrections reapply across future turns until cleared.
- Hashed-session revision history exposes active, superseded, and cleared states.
- Clear restores the latest underlying uncorrected interpretation, and stale
  simultaneous correction writes are refused rather than silently lost.

## Evidence
- Backend: `375 passed, 1 skipped`; 89% application coverage.
- Alignment module: 95% coverage.
- Focused alignment/API suite: `72 passed`.
- Frontend: eslint clean; Vitest `24 passed`; production build green.
- `compileall`, experience JSONL validation, and `git diff --check` clean.
- Isolated live FastAPI proof: health `ok`; correction became active; clear
  restored the latest base frame and recorded a cleared lifecycle revision.

## Honest limits
- The frame is an interpretation, not truth; its contents remain unverified.
- The ambiguity policy intentionally under-detects semantic ambiguity. Model
  confidence and model-proposed unknowns cannot force a blocking clarification.
- Each generated turn currently adds one local completion request for alignment.
- Corrections express intended meaning, not external truth or execution authority.

## Single next action
Run a human live review of the completed correction workflow and gather real
correction patterns before changing deterministic ambiguity thresholds.

## Open approvals/blockers
- None. Operator requested commit and push after the green release gate.

## Active files
- Communication alignment backend, persistence, frontend, tests, and docs.

## Notes not yet promoted
- Candidate: promote observed repeated correction patterns only after human review;
  do not infer stronger blocking policy from model confidence.

## Runtime
Backend: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000`
Frontend: `cd frontend; npm run dev`
Tests: `.venv\Scripts\python -m pytest -q`
