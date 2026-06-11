# RESUME MANIFEST

## Current goal
Curriculum evidence front EXECUTED 2026-06-11 (task curriculum-evidence-v1,
operator-approved). The first live brain-growth proof exists:
`.aios/state/EVIDENCE_CURRICULUM.md` (report) +
`.aios/audit/curriculum-evidence-run.jsonl` (raw frames). Working tree holds
UNCOMMITTED product fixes + evidence artifacts awaiting the operator's commit
decision. Next: operator decides commit, then picks the next front.

## Last completed and verified
2026-06-11 (this session):
- Live curriculum run: 6/6 tasks mastered (both held-out gates), level unlock
  observed, first verified procedural skill (id=10, 3/3), Slice 1 foraging
  reward live-proven (skill_adjustment=0.2 cap binding, skill_ids=[10]).
- 4 product gaps found by the run and fixed, each test-covered:
  1. `aios/agents/tool_agent.py` — prose tool-call rescue: multi-fenced-block,
     `parameters`-keyed, and bare unfenced JSON shapes; first allowlisted call
     only.
  2. `aios/agents/tool_agent.py` — `_create_file` replay tolerance:
     byte-identical existing content is a no-op success.
  3. `aios/core/executor.py` — bare argv[0] now resolves through the sanitised
     PATH (venv-first); closes Windows base-interpreter fallback AND a latent
     sandbox-binary-planting hole.
  4. `aios/api/main.py` — turn outcome = FINAL verify verdict (last evidence
     wins; operator decision 2026-06-11). Was FAIL-dominant, which made any
     task needing the verify->fix loop unmasterable.
- New driver tooling at repo root: `curriculum_seed.json`,
  `curriculum_evidence_driver.py` (fail-closed allowlist delegate; 2 live
  rejections logged).
- Full suite BEFORE closeout: **408 passed, 1 skipped** (baseline 400/1).
  Audit chain valid (182 entries, head d0ce65b4…).

## Single next action
Operator: authorize commit (suggested: slice A = product fixes + tests,
slice B = driver/seed + .aios evidence/state) — then pick the next front:
container live-proof, premium UI (his deferred call), or stigmergy Slice 2.

## Open approvals/blockers
- Commit authorization PENDING (tree is dirty with the work above).
- Codex POST-HOC reviews due ~2026-06-16 (inbox notified):
  (a) e773768 (stigmergy Slice 1) — now also LIVE-PROVEN, see evidence report;
  (b) this session's 4 product fixes (esp. the executor PATH-resolution
      security improvement and the last-evidence-wins classification change);
  (c) stale `correct-resume-stale-runway` verdict — findings-by-message.
- `premium-ui-v1`: still queued/deferred; operator's call.

## Notes not yet promoted
- Replay mechanics can DROP an approved-but-not-re-issued grant (the
  `__init__.py` case). Product follow-up: pre-apply granted writes on resume
  or surface dropped grants. This silently discards human-approved work.
- Last-evidence-wins should become per-target once evidence strings carry the
  verified file/command (noted in main.py comment).
- Skill signatures fragment across arc shapes; trail consolidation across
  near-identical workflows is an open design question.
- `record_matching` misses stay silent server-side; only the driver's
  post-turn poll catches them. Consider logging unmatched verified turns.
- Backend for live runs: start from venv with
  `$env:AIOS_INTERPRET_ALIGNMENT='false'` (RAM lever + deterministic prompts).
- `training_ground/__init__.py` now exists (agent-authored, delegate-applied):
  both package-style and plain imports pass under `python -m pytest` from the
  sandbox cwd.

## Runtime
Brief: `.venv\Scripts\python agent_coord.py brief --agent claude`
Backend: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000`
Frontend: `cd frontend; npm run dev`
Tests: `.venv\Scripts\python -m pytest -q`
Driver: `.venv\Scripts\python curriculum_evidence_driver.py status|run|reps|plan-proof`
