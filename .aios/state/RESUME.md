# RESUME MANIFEST

## Current goal
Stigmergy core: operator directed "implement it 100% in core" (2026-06-11,
scope = full stigmergy, NO concurrent agents — that verdict stands). Trail
mechanics (task stigmergy-trail-mechanics-v1) are BUILT and LIVE-PROVEN in
the working tree, awaiting the operator's commit decision. Evidence:
`.aios/state/EVIDENCE_CURRICULUM.md` (Trail Mechanics section).

## Last completed and verified
2026-06-11 evening (this session, after the curriculum evidence run landed as
eaafb70 + f2d3d63):
- Trail mechanics implemented per a 3-lens judge-panel design (the panel
  empirically tested consolidation rules against the live DB before code):
  - `aios/memory/relevance.py`: `skill_signature_v2` (goal tokens +
    argument-stripped tool sequence; `||` separator).
  - `aios/memory/schema.sql` + `aios/memory/db.py::_migrate`: 5 new
    procedural_skills columns, NULL-only backfill, verified-keeper
    consolidation (losers → 'superseded' + superseded_by lineage, never
    deleted), partial unique index on active signature_v2.
  - `aios/config.py`: 6 env-tunable SKILL_REUSE_* constants (in __all__).
  - `aios/memory/skills.py`: record_attempt keyed by signature_v2 (+
    recipe refresh on fewer redaction markers); NEW record_reuse (verified-
    only, success refreshes evaporation clock / failure does NOT, quarantine
    at net 3 reuse failures); pure `_reuse_factor` (saturating, asymmetric
    ~7:1, floored); strength = min(1.0, rate*freshness*reuse_factor).
  - `aios/api/main.py`: record_outcome threads reuse credit to recalled
    trails, excluding the direct-credited walked trail (direct_id).
- 15 new behavioral tests (incl. old-schema migration fixtures). Full suite:
  **423 passed, 1 skipped** (morning baseline 400/1; 408/1 after loop fixes).
- LIVE proofs: migration no-op on the real DB (10 rows backfilled, zero
  merges, id=10 verified 3/0 intact; backup at
  `data/backup-pre-trail-mechanics/`); negative pheromone (id=10
  reuse_failure_count=1 from a failing novel-task turn); reinforcement
  (reuse_success_count=1 from the succeeding retry); planner cap unchanged
  (plan-proof: skill_adjustment=0.2, skill_ids=[10]).

## Single next action
Operator: authorize commit of the trail-mechanics slice (suggested: product
code + tests in one commit, .aios state checkpoint in another). Then pick the
next stigmergy block: 1) role-pass castes (Slice 2 proper — needs design),
2) loop-integrity fixes (dropped-grant replay bug + per-target outcome
classification), 3) pheromone observability endpoint/panel.

## Open approvals/blockers
- Commit authorization PENDING for trail mechanics (tree dirty with it).
- Codex POST-HOC reviews queued for ~2026-06-16 (inbox msgs 14 + this
  session's trail-mechanics notice): e773768, the 4 loop fixes (eaafb70),
  the evidence run (f2d3d63), and trail mechanics.
- `premium-ui-v1`: still queued/deferred; operator's call.

## Notes not yet promoted
- Quarantine ratchet: a recovered trail re-quarantines after ONE more reuse
  failure (net stays >= 3). Intended short-leash; watermark column is the
  specced fix if rank-thrashing is observed.
- Reuse attribution is recall-based (recalled => influenced). If over-credit
  shows up in live data, gate on the model actually following the steps.
- Dropped-grant replay bug + per-target classification: still open, specced.
- SKILL_LAMBDA_DECAY + reuse constants: tune from accumulating live data.
- Backend for live runs: venv + `$env:AIOS_INTERPRET_ALIGNMENT='false'`.

## Runtime
Brief: `.venv\Scripts\python agent_coord.py brief --agent claude`
Backend: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000`
Frontend: `cd frontend; npm run dev`
Tests: `.venv\Scripts\python -m pytest -q`
Driver: `.venv\Scripts\python curriculum_evidence_driver.py status|run|reps|plan-proof`
