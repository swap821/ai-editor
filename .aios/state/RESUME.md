# RESUME MANIFEST

## Current goal
Stigmergy core COMPLETE per the operator's "100% in core" directive
(2026-06-11/12, task stigmergy-core-completion-v1): trail mechanics (landed
87fd511), loop-integrity fixes, pheromone observability, and role-pass
castes are all built and live-exercised. Working tree holds the UNCOMMITTED
completion slice awaiting the operator's commit decision. Evidence:
`.aios/state/EVIDENCE_CURRICULUM.md` (Stigmergy Core Completion section).

## Last completed and verified
2026-06-12 overnight (this session):
- Loop integrity: grant pre-apply in ToolAgent.run (approved writes land
  deterministically at replay start; dropped-grant trust bug closed); edit
  replay tolerance + `noop` write status (no redundant re-verification);
  per-target outcome classification in main.py (`_verify_target_key`,
  verify events carry `target`).
- Observability: `SkillMemory.trail_map` + GET /api/v1/development/trails +
  driver `trails` subcommand (computed strengths, quarantine flags,
  lineage, constants — the tuning evidence base).
- Role-pass castes: `aios/agents/role_pass.py` (conductor over unchanged
  ToolAgent; `system_prompt`/`allowed_tools` params; dispatch-level caste
  enforcement; stigmergic handoff with sentinel suppression + plan-artifact
  salvage; evidence-only review verdict; one bounded retry; opt-in
  `rolePass` flag, default byte-identical). LIVE: architecture proven
  (enforcement, approvals, replays, classification all correct across 6
  attempts); 7B/8B models cannot sustain the roles — honest negative
  result, castes await a stronger local model.
- Rescue parser: 4th prose shape (ReAct `Action: tool {json}`).
- Full suite: **438 passed, 1 skipped** (yesterday morning's baseline 400/1).

## Single next action
Operator: authorize commit of the completion slice (suggested: product
code + tests, then .aios state). After that: REST the codebase — Codex's
post-hoc review queue (~2026-06-16) now holds e773768, the 4 loop fixes
(eaafb70), trail mechanics (87fd511), and this slice. Remaining open fronts
are unchanged: container live-proof, premium UI (operator's deferred call).

## Open approvals/blockers
- Commit authorization PENDING for the completion slice (tree dirty).
- Codex POST-HOC reviews due ~2026-06-16 (inbox msgs 14, 15 + this slice's
  notice when committed).
- `premium-ui-v1`: still queued/deferred; operator's call.
- Role-pass live capability: gated on a stronger local model (14B+ class
  when RAM allows) — hardware/model decision, not a code task.

## Notes not yet promoted
- Castes follow-ups: per-role model routing once a role-capable local model
  exists; consider planner-skip heuristic for trivial requests.
- Quarantine watermark fix is specced if rank-thrashing is observed.
- Constant tuning (lambda, reuse Ks): data-bound; the trails surface
  accumulates the evidence — revisit after real usage.
- The rescue parser now covers 4 emission shapes; if a 5th appears, consider
  a structured grammar instead of accreting cases.

## Runtime
Brief: `.venv\Scripts\python agent_coord.py brief --agent claude`
Backend: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000`
Frontend: `cd frontend; npm run dev`
Tests: `.venv\Scripts\python -m pytest -q`
Driver: `.venv\Scripts\python curriculum_evidence_driver.py status|run|reps|plan-proof|trails`
