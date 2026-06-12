# RESUME MANIFEST

## Current goal
PREMIUM UI FRONT IS LIVE (task premium-ui-v1, claimed 2026-06-12): the
operator built a 3D "superbrain" demo (`GAG demo/gag-orchestrator`, own
nested git repo, gitignored from this tree). Four-lens review verdict:
signature-grade visual ideas, architecture sound, extract-into-Vite is the
adoption path, perf fixable. P0 fixes + the AI-OS cognition adapter are
LANDED in the lab repo (41ace3e on top of baseline be68d2f): duplicate
EffectComposer deleted, cortex Voronoi halved, and the demo now binds to
the REAL backend - live pheromone map + metrics on the HUD, command bar
drives real supervised turns via SSE, 'approval-required' event exists.
Verified end-to-end live (two real turns from the demo UI; backend needs
AIOS_CORS_ORIGINS to include localhost:3000).

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
Operator + Claude continue the UI roadmap from the review (full plan in the
gag-demo-review workflow output, pinned in experiences): next blocks are
P1 quality-tier autodetect + LLM-aware degrade, the approval-pause visual
choreography (amber hold), curating one canon (mount KnowledgeHorizon,
archive dead eras), and binding CognitiveGrasp shards to real trails.
Extraction into frontend/ (Vite) comes after the lab look stabilizes.

## Open approvals/blockers
- Parent-tree commit PENDING: `.gitignore` (GAG demo/ exclusion) + this
  state checkpoint — small; ask the operator.
- Codex POST-HOC reviews due ~2026-06-16 (inbox msgs 14, 15, 16).
- Role-pass live capability: gated on a stronger local model (14B+ class
  when RAM allows) — hardware/model decision, not a code task. The same
  upgrade benefits the UI (caste visuals bound to real role-pass state).

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
