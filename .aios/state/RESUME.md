# RESUME MANIFEST

Last updated: 2026-06-27T10:58:41Z

## Current Goal
Build Council Runtime v0.1 from the sovereign roadmap. The roadmap remains the near-term canon: Phase 0 foundation lock, 30-day First Heartbeat, then 24-week v1.0.

## Last Completed + Verified
- Phase 2 Simulated Council Loop is implemented on branch `council-runtime-v01`.
- Added Planner, Security, Memory, and Testing Queen wrappers under `aios/council/queens/`.
- Added `CouncilOrchestrator` to draft a `MissionContract`, collect queen verdicts, block unsafe preflight, run `WorkerSpawner`, apply Testing Queen verification, rewrite `RunLedger`, and generate a verdict-aware `KingReport`.
- Updated `KingReport` generation so council `deny`/`defer` verdicts prevent approval recommendations, and report summaries expose council verdicts plus model-routing evidence.
- Added `tests/test_council_orchestrator.py` covering a full successful council loop, protected-foundation preflight denial, and Testing Queen verification failure.
- Committed Phase 2 as `4d57841b3db7cebc4a04a928428c7be4fcefeecc` and pushed `council-runtime-v01` to GitHub.
- Verified:
  - `$env:AIOS_ROUTER_CLOUD_TASKS=''; .venv\Scripts\python.exe -m pytest tests\test_council_orchestrator.py tests\test_runtime_contracts.py tests\test_runtime_worker_birth.py tests\test_runtime_intelligence_gateway.py -q` -> 16 passed.
  - `$env:AIOS_ROUTER_CLOUD_TASKS=''; .venv\Scripts\python.exe -m pytest -q` -> pass, 1 skipped, 1 known httpx warning.
  - `$env:AIOS_ROUTER_CLOUD_TASKS=''; .venv\Scripts\python.exe -m pytest -q --cov=aios --cov-report=term-missing --cov-report=xml --cov-fail-under=85` -> pass, 1 skipped, 87.01% coverage, 1 known httpx warning.
  - `git diff --check` -> pass, CRLF warnings only.
  - GitHub Actions CI run `28287110635` -> success (`frontend` 55s, `backend` 3m16s).
  - Protected foundation modules were not modified.

## Single Next Action
Begin the Dashboard-lite KingReport endpoint/panel slice: expose stored Council missions/reports through a minimal API surface, then add the ugly-useful React panel for mission, risk, verdicts, touched files, blocked attempts, verification, rollback, and model routing.

## Open Approvals / Blockers
- Local `.env` sets `AIOS_ROUTER_CLOUD_TASKS=reasoning,coding`; mask it with `$env:AIOS_ROUTER_CLOUD_TASKS=''` when testing default local-first privacy behavior.
- The roadmap proof target `frontend/src/pages/Login.jsx` is stale in the current repo, so Phase 1A/1B tests use temp workspaces with that relative path. Do not wire a real product mission to that stale path without updating the target.
- Cloud reasoning is implemented as injectable clients plus policy evidence; no live cloud provider is invoked by tests, and workers still never see provider SDKs or API keys.
- Phase 2 tests use temp workspaces and the current Python executable for pytest verification; Security Queen normalizes trusted `python -m pytest ...` commands before gateway classification but records the original command.
- The next slice touches frontend UI; load the relevant project design/frontend skill before building the panel.
- The preserved knowledge-graph WIP remains in `stash@{0}` from the prior sync task; do not drop it without explicit operator instruction.
- Kimi is currently off; proceed solo unless the operator re-enables a reviewer.

## Active Files
- `aios/council/council_orchestrator.py`
- `aios/council/queen_verdict.py`
- `aios/council/queens/planner.py`
- `aios/council/queens/security.py`
- `aios/council/queens/memory.py`
- `aios/council/queens/testing.py`
- `aios/runtime/king_report.py`
- `tests/test_council_orchestrator.py`
- `.aios/state/RESUME.md`
- `.aios/memory/experiences.jsonl`
