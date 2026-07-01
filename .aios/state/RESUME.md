# RESUME MANIFEST

Last updated: 2026-07-01T08:38Z

## Current Goal
Close and land the 32B audit's top stability findings before any v1.0/birth
claim, then start the grounded fusion roadmap from Claude's handoff packet.

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
- Landed rollback + swarm cleanup as `d151fc0`; GitHub CI run `28493682993`
  failed backend on rollback approval persistence because a valid Council
  `mission-<12hex>` id was high-entropy-shaped.
- Hotfixed `ApprovalStore` to normalize valid rollback `mission_id` values only
  in the scan copy (exact persisted payload unchanged; adjacent secret rejection
  still covered). Commit `27cf2e5` pushed to `origin/master`; GitHub CI run
  `28504424476` passed (backend `4m23s`, frontend `1m3s`). Fresh local backend
  coverage gate also passed at `89.11%` with 4 skips.

## Planning + CRW P0 (Claude, 2026-07-01, operator-directed)
- Verified two external architecture analyses against the tree (~60-65% accurate;
  7 phantom bugs caught) and wrote grounded specs:
  `docs/superpowers/specs/2026-07-01-cortex-core-fusion-adr.md` (sync-core + two-tier
  durable cortex; authority-stays-sync invariant),
  `docs/superpowers/specs/2026-07-01-fusion-roadmap-workorders.md` (Lane C = Codex spine; Lane K = CRW),
  `docs/superpowers/specs/2026-07-01-continuous-renovation-worker.md` (propose-only frontend worker).
- Shipped CRW Phase 0: `tools/frontend_health.py` + `tests/test_frontend_health.py`
  (unit tests green). Live quick run = FAIL on eslint (17 problems incl. `no-undef`
  in `frontend/vite.config.js`); typecheck + both canon guards clean; a11y unavailable
  (no jsx-a11y yet). Report: `.aios/state/FRONTEND_HEALTH.json`.
- Codex handoff packet: `.aios/state/CODEX_FUSION_HANDOFF.md`. RuFlo keys:
  `gagos-fusion-roadmap`, `gagos-crw-spec`.

## Single Next Action
Start the fusion roadmap only after operator go: Codex C1 = typed event schema +
additive SSE, from `.aios/state/CODEX_FUSION_HANDOFF.md` and
`docs/superpowers/specs/2026-07-01-fusion-roadmap-workorders.md`. No birth claim yet.

## Open Approvals / Blockers
- Do not declare born. Rollback + swarm cleanup are landed and GitHub-CI green,
  but the next fusion work still needs normal lease + review discipline.
- VM/cloud 32B is not needed for this fix; leave it stopped unless a later audit
  requires it.
- CRW Phase-0 detector intentionally reports a current frontend lint FAIL
  (`frontend/vite.config.js` `process`/`__dirname` plus React lint findings);
  it is a reporter, not a release gate.

## Active Files
- Next-task handoff/specs:
  `.aios/state/CODEX_FUSION_HANDOFF.md`,
  `docs/superpowers/specs/2026-07-01-{cortex-core-fusion-adr,fusion-roadmap-workorders,continuous-renovation-worker}.md`.
- CRW P0 detector/report:
  `tools/frontend_health.py`, `tests/test_frontend_health.py`,
  `.aios/state/FRONTEND_HEALTH.json`.
- Continuity:
  `.aios/state/RESUME.md`, `.aios/memory/experiences.jsonl`.

## Notes Not Yet Promoted
- The 32B audit headline was partly stale: rollback engine tests already existed
  and Council worker snapshot IDs were partly wired. The real remaining gap was
  HTTP/UI operability plus failed-worker recommendation honesty.
- RuFlo CLI still creates root `agentdb.rvf*` scratch files; `.gitignore` now
  ignores them, and local copies were removed.
- Local untracked `.agents/skills/` and `.codex/` entries are machine/tooling
  installs, not part of this landing.
