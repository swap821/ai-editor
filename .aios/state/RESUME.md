# RESUME MANIFEST

Last updated: 2026-06-27T14:20:35Z

## Current Goal
Build Council Runtime v0.1 from the sovereign roadmap. The roadmap remains the near-term canon: Phase 0 foundation lock, 30-day First Heartbeat, then 24-week v1.0.

## Last Completed + Verified
- Dashboard-lite is implemented, committed, pushed, and CI-verified on branch `council-runtime-v01`.
- Implementation commit: `852e3c89e4d0aa5b86fbdca6933a5c6659fdac8d` (`Add Council Runtime dashboard lite`).
- Added `AIOS_COUNCIL_RUNTIME_DIR` / `config.COUNCIL_RUNTIME_DIR` as the shared artifact root for stored Council missions.
- Added read endpoints:
  - `GET /api/v1/council/missions`
  - `GET /api/v1/council/missions/{mission_id}`
  - `GET /api/v1/council/reports/{mission_id}`
- Added King decision endpoints:
  - `POST /api/v1/council/approve`
  - `POST /api/v1/council/reject`
- The decision endpoints record `king_decision.json`; when a pending worker approval request is supplied, they write the matching single-use `*.response.json` file for the existing `WorkerRuntime.request_approval()` protocol.
- Added product-owned `frontend/src/workbench/CouncilDashboard.jsx` + CSS and mounted it in `GagosChrome`.
- Dashboard shows mission, risk, recommendation, approval/rollback state, Council verdicts, touched files, blocked attempts, verification state, model route, pending approval, and King approve/reject buttons.
- Added backend tests in `tests/test_council_api.py` for list/detail/report, corrupt artifact skip, path-escape rejection, King report decision recording, pending approval response writing, and single-use refusal.
- Added frontend test `frontend/src/workbench/CouncilDashboard.test.tsx` covering the report display plus approve action payload.
- Local verification:
  - `$env:AIOS_ROUTER_CLOUD_TASKS=''; .venv\Scripts\python.exe -m pytest tests\test_council_api.py tests\test_council_orchestrator.py -q` -> 8 passed.
  - `cd frontend; npm run test -- CouncilDashboard` -> 1 test passed.
  - `cd frontend; npm run typecheck` -> pass.
  - `$env:AIOS_ROUTER_CLOUD_TASKS=''; .venv\Scripts\python.exe -m pytest -q --cov=aios --cov-report=term-missing --cov-report=xml --cov-fail-under=85` -> pass, 1 skipped, 87.03% coverage, 1 known httpx warning.
  - `cd frontend; npm run test` -> 59 files passed, 359 tests passed.
  - `cd frontend; npm run build` -> pass.
  - `git diff --check` -> pass, CRLF warnings only.
  - Protected foundation modules were not modified.
- GitHub Actions CI run `28291759265` succeeded for pushed head `852e3c89e4d0aa5b86fbdca6933a5c6659fdac8d`:
  - `frontend` -> success in 58s.
  - `backend` -> success in 3m41s.

## Security Hotfix (2026-06-27, after deep review) — DONE + VERIFIED
Deep review (19-agent workflow + direct source verification) found 3 worker-isolation regressions that contradicted the project's fail-closed thesis. All three fixed on `council-runtime-v01` (no frozen-spine files touched), each with new adversarial tests:
- `worker_api.py` `run_command` was unguarded arbitrary host exec → now FAIL-CLOSED to `MissionContract.verification_commands` (argv normalized via the same `shlex.split` as `worker_entry`); command output is redacted via `SecretPolicy` + capped at 50k before persisting to the evidence ledger.
- `config.py` `load_dotenv` re-injected scrubbed secrets into the worker → now gated behind `_worker_sandbox_active()`; `backends._restricted_environment()` sets `AIOS_WORKER_SANDBOX=1` on the worker env.
- `main.py` `_validate_council_mission_id`/`_validate_council_request_id` admitted `..` → now reject `.`/`..`/`..`-substring, plus `_mission_dir` resolve-confirms inside `missions/`.
- New tests: `test_council_routes_reject_dotdot_traversal`, `test_run_command_is_fail_closed_to_verification_allowlist`, `test_restricted_environment_sets_worker_sandbox_flag`, `test_config_skips_dotenv_inside_worker_sandbox`.
- Verified: `pytest -q --cov=aios --cov-fail-under=85` → exit 0, 1156 passed / 1 skipped, 87.11%. Diff: 6 files, +166/-4. NOT yet committed (awaiting operator go).

## Single Next Action
Operator decision: commit the security hotfix to `council-runtime-v01`. Then the remaining (non-blocking) merge-gate cleanup before master: de-scope vaporware rollback from `KingReport`/`CouncilDashboard` (rollback never functional), add a 500→guard on the per-mission detail/report routes for corrupt artifacts (list route already guarded), and a concurrency/collision guard on `run_ledger`. Phase 3A-lite (durable `council_state.py` SQLite) remains the next feature after that.

## Open Approvals / Blockers
- Local `.env` sets `AIOS_ROUTER_CLOUD_TASKS=reasoning,coding`; mask it with `$env:AIOS_ROUTER_CLOUD_TASKS=''` when testing default local-first privacy behavior.
- The roadmap proof target `frontend/src/pages/Login.jsx` is stale in the current repo, so Phase 1A/1B/Dashboard tests use temp workspaces or seeded artifacts with that relative path. Do not wire a real product mission to that stale path without updating the target.
- Cloud reasoning is implemented as injectable clients plus policy evidence; no live cloud provider is invoked by tests, and workers still never see provider SDKs or API keys.
- Dashboard-lite is artifact-backed. It records report decisions and responds to file-backed worker approvals, but Phase 3A-lite must make Council verdicts/events durable and replayable.
- The preserved knowledge-graph WIP remains in `stash@{0}` from the prior sync task; do not drop it without explicit operator instruction.
- Kimi is currently off; proceed solo unless the operator re-enables a reviewer.

## Active Files
- `.aios/state/RESUME.md`
- `.aios/memory/experiences.jsonl`
