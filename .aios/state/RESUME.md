# RESUME MANIFEST

Last updated: 2026-07-01T03:58Z

## Current Goal
Close the 32B audit's top stability findings before any v1.0/birth claim:
real Council rollback recovery plus confirmed orphaned swarm-code cleanup.

## Last Completed + Verified
- Adopted Claude/RuFlo handoff docs:
  `.aios/state/CLOUD_32B_HANDOFF.md` and
  `.aios/state/DEEP_AUDIT_REMAINING_REPORT.md`.
- Implemented mission-scoped Council rollback:
  `SnapshotManager.rollback_snapshot(...)`,
  `POST /api/v1/council/missions/{mission_id}/rollback`, mission+snapshot-bound
  approval tokens, rolled-back ledger/report persistence, and dashboard recovery
  controls.
- Tightened KingReport honesty: failed executed workers with touched files and a
  rollback snapshot now recommend `rollback`, not only `revise`.
- Claude non-builder review passed in
  `.aios/state/ROLLBACK_HARDENING_REVIEW.md`.
- Used RuFlo memory/hooks to verify the next audit item: the live swarm surface is
  `aios/agents/swarm.py` + `aios/agents/swarm_patterns.py`; the large helper
  modules were unimported and untested.
- Removed confirmed orphaned product code:
  `aios/agents/swarm_{adaptive,conflict,parallel,scout}.py`,
  `aios/memory/pheromones.py`, `aios/policy/*`, and
  `aios/runtime/leases.py`; added `tests/test_dead_code_hygiene.py` and ignored
  RuFlo root scratch files `agentdb.rvf*`.
- Applied Claude's dead-code review follow-up by pruning the now-stale
  `.coveragerc` omit block for the deleted swarm files.
- Fresh local gates passed after the cleanup:
  backend full coverage gate (`89.11%`, 4 skips); frontend `npm run typecheck`;
  frontend full Vitest (`63` files / `377` tests); frontend `npm run build`;
  `tools/check_css_canon.py`; `tools/check_canon_frozen.py`; `git diff --check`.

## Single Next Action
Handoff the combined tree for review/landing approval, then commit/push only if
the operator asks. No birth claim yet.

## Open Approvals / Blockers
- Do not declare born. Rollback is review-passed locally; swarm cleanup is
  locally gated but still needs reviewer/operator landing approval.
- VM/cloud 32B is not needed for this fix; leave it stopped unless a later audit
  requires it.

## Active Files
- `.gitignore`
- `.coveragerc`
- `aios/api/main.py`
- `aios/runtime/{snapshots.py,king_report.py}`
- deleted: `aios/agents/swarm_{adaptive,conflict,parallel,scout}.py`,
  `aios/memory/pheromones.py`, `aios/policy/*`, `aios/runtime/leases.py`
- `frontend/src/workbench/CouncilDashboard.{jsx,css,test.tsx}`
- `tests/test_{runtime_worker_birth.py,council_orchestrator.py,council_origination.py,dead_code_hygiene.py}`
- `.aios/state/{CLOUD_32B_HANDOFF.md,DEEP_AUDIT_REMAINING_REPORT.md,ROLLBACK_HARDENING_REVIEW.md,RESUME.md}`
- `.aios/memory/experiences.jsonl`

## Notes Not Yet Promoted
- The 32B audit headline was partly stale: rollback engine tests already existed
  and Council worker snapshot IDs were partly wired. The real remaining gap was
  HTTP/UI operability plus failed-worker recommendation honesty.
- RuFlo CLI still creates root `agentdb.rvf*` scratch files; `.gitignore` now
  ignores them, and local copies were removed.
