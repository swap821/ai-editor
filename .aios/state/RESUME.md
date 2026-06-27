# RESUME MANIFEST

Last updated: 2026-06-27T14:13:00Z

## Current Goal
Build Council Runtime v0.1 from the sovereign roadmap. The roadmap remains the near-term canon: Phase 0 foundation lock, 30-day First Heartbeat, then 24-week v1.0.

## Last Completed + Verified
- Dashboard-lite is implemented locally on branch `council-runtime-v01`.
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
- Verified:
  - `$env:AIOS_ROUTER_CLOUD_TASKS=''; .venv\Scripts\python.exe -m pytest tests\test_council_api.py tests\test_council_orchestrator.py -q` -> 8 passed.
  - `cd frontend; npm run test -- CouncilDashboard` -> 1 test passed.
  - `cd frontend; npm run typecheck` -> pass.
  - `$env:AIOS_ROUTER_CLOUD_TASKS=''; .venv\Scripts\python.exe -m pytest -q --cov=aios --cov-report=term-missing --cov-report=xml --cov-fail-under=85` -> pass, 1 skipped, 87.03% coverage, 1 known httpx warning.
  - `cd frontend; npm run test` -> 59 files passed, 359 tests passed.
  - `cd frontend; npm run build` -> pass.
  - `git diff --check` -> pass, CRLF warnings only.
  - Protected foundation modules were not modified.

## Single Next Action
Commit Dashboard-lite, push `council-runtime-v01`, and watch GitHub Actions for the pushed head.

## Open Approvals / Blockers
- Local `.env` sets `AIOS_ROUTER_CLOUD_TASKS=reasoning,coding`; mask it with `$env:AIOS_ROUTER_CLOUD_TASKS=''` when testing default local-first privacy behavior.
- The roadmap proof target `frontend/src/pages/Login.jsx` is stale in the current repo, so Phase 1A/1B/Dashboard tests use temp workspaces or seeded artifacts with that relative path. Do not wire a real product mission to that stale path without updating the target.
- Cloud reasoning is implemented as injectable clients plus policy evidence; no live cloud provider is invoked by tests, and workers still never see provider SDKs or API keys.
- Dashboard-lite is artifact-backed. It records report decisions and responds to file-backed worker approvals, but it does not yet add durable SQLite Council verdict/event replay.
- The preserved knowledge-graph WIP remains in `stash@{0}` from the prior sync task; do not drop it without explicit operator instruction.
- Kimi is currently off; proceed solo unless the operator re-enables a reviewer.

## Active Files
- `aios/api/main.py`
- `aios/config.py`
- `frontend/src/workbench/CouncilDashboard.jsx`
- `frontend/src/workbench/CouncilDashboard.css`
- `frontend/src/workbench/CouncilDashboard.test.tsx`
- `frontend/src/workbench/GagosChrome.jsx`
- `tests/test_council_api.py`
- `.aios/state/RESUME.md`
- `.aios/state/PLAN.md`
- `.aios/memory/experiences.jsonl`
