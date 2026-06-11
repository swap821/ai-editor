# RESUME MANIFEST

## Current goal
Stigmergy Slice 1 is LANDED on master (commit e773768, 2026-06-11) under
operator authority. Codex independent review is deferred POST-HOC: his usage
window reopens 2026-06-16; he should `git show e773768` and send findings via
inbox (the pinned handoff snapshot 194522ae is stale by design — the formal
verdict mechanism will refuse it; findings-by-message is the agreed path).
Next: operator picks the next front.

## Context: swarm decision (2026-06-11)
Operator proposed an ant-colony swarm orchestrator. Assessed via grounded
3-angle workflow; verdict: keep the stigmergy half (mostly already built),
reject concurrent agent spawning (16GB RAM, serial approval gate, one-writer
lesson). Operator accepted; Slice 1 was the agreed first concrete step.
Sequential role-pass ("castes") is the candidate Slice 2 — not started, needs
operator go.

## Last completed and verified
2026-06-11 (this session), commit e773768:
- `aios/config.py`: SKILL_LAMBDA_DECAY_PER_HOUR (0.005/hr, ~6-day half-life)
  + SKILL_CONFIDENCE_BONUS_MAX (0.2), env-overridable, in __all__.
- `aios/memory/skills.py`: relevant_verified() ranks by
  strength = success_rate * exp(-lambda * hours_since_updated_at); skills are
  never deleted, only out-competed. `now` injectable for deterministic tests.
- `aios/core/planner.py`: _calibrate() adds a verification-gated foraging
  reward capped at SKILL_CONFIDENCE_BONUS_MAX; Calibration gains
  skill_adjustment + skill_ids.
- `tests/test_brain_growth.py`: 3 new behavioral tests.
- Verified BEFORE commit: full suite 400 passed, 1 skipped (baseline 397/1 +
  3 new); git diff --check clean; compileall clean.

## Single next action
Operator picks the front: 1) curriculum evidence gathering, 2) container
live-proof (needs Docker daemon), 3) premium UI (his deferred call),
4) stigmergy Slice 2 (sequential role-pass: planner/coder/reviewer personas
over the one ToolAgent loop). Route the choice through agent_coord.py.

## Open approvals/blockers
- Codex POST-HOC reviews due when he returns 2026-06-16:
  (a) commit e773768 (this slice) — findings via inbox, not formal verdict;
  (b) `correct-resume-stale-runway` verdict, pending since 2026-06-10 — its
  pinned tree has since changed (this session's work), so that verdict will
  also fail closed; treat as findings-by-message too.
- `premium-ui-v1`: queued, DEFERRED by operator. Leave until he decides.
- No commit authorization outstanding (e773768 + state checkpoint were the
  authorized scope).

## Notes not yet promoted
- SKILL_LAMBDA_DECAY 0.005/hr is a first guess; tune from real usage evidence.
- `_hours_since` duplicated in skills.py and retrieval.py (deliberate, keeps
  skills.py off the rank-bm25 import graph); shared util = reviewer follow-up.
- Never reinforce skills on mere repetition — promotion must stay
  verification-gated or bad patterns launder into trusted status.

## Runtime
Brief: `.venv\Scripts\python agent_coord.py brief --agent claude`
Backend: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000`
Frontend: `cd frontend; npm run dev`
Tests: `.venv\Scripts\python -m pytest -q`
