# RESUME MANIFEST

Last updated: 2026-06-27T10:38:05Z

## Current Goal
Build Council Runtime v0.1 from the sovereign roadmap. The roadmap remains the near-term canon: Phase 0 foundation lock, 30-day First Heartbeat, then 24-week v1.0.

## Last Completed + Verified
- Phase 1B Hybrid Intelligence Worker Birth is implemented on branch `council-runtime-v01`.
- Added `aios/runtime/intelligence_gateway.py` with frozen request/response schemas, injectable local/cloud reasoning clients, local Ollama default, cloud opt-in routing, secret redaction, budget fallback, and plan-only responses.
- Added `aios/runtime/secret_policy.py` to redact persisted reasoning text and centralize worker secret-env filtering.
- Added `aios/runtime/budget_guard.py` to enforce `MissionContract.metadata["model_policy"]` controls for cloud calls, token limits, and fallback behavior.
- Updated `WorkerRuntime.request_plan()` to call `IntelligenceGateway`, record provider/fallback/secret/budget evidence, and return text only.
- Updated deterministic `worker_entry` so hybrid missions can request a plan before still acting only through `read_file` / `write_file` / `run_command`.
- Added `tests/test_runtime_intelligence_gateway.py` covering cloud opt-in, budget fallback, secret fallback/redaction, runtime plan-only evidence, and hybrid worker-entry plan requests.
- Committed Phase 1B as `3efdfb4` and pushed `council-runtime-v01` to GitHub.
- Verified:
  - `.venv\Scripts\python.exe -m pytest tests\test_runtime_contracts.py tests\test_runtime_worker_birth.py tests\test_runtime_intelligence_gateway.py -q` -> 13 passed.
  - `$env:AIOS_ROUTER_CLOUD_TASKS=''; .venv\Scripts\python.exe -m pytest -q` -> pass, 1 skipped, 1 known httpx warning.
  - `$env:AIOS_ROUTER_CLOUD_TASKS=''; .venv\Scripts\python.exe -m pytest -q --cov=aios --cov-report=term-missing --cov-report=xml --cov-fail-under=85` -> pass, 1 skipped, 87.01% coverage, 1 known httpx warning.
  - `git diff --check` -> pass, CRLF warnings only.
  - GitHub Actions CI run `28286656641` -> success (`backend` 3m14s, `frontend` 56s).
  - Protected foundation modules were not modified.

## Single Next Action
Begin Phase 2 simulated Council wrappers: Planner Queen, Security Queen wrapper, Testing Queen wrapper, Memory Queen basic wrapper, `CouncilOrchestrator`, and a full loop into `WorkerSpawner` / `KingReport`.

## Open Approvals / Blockers
- Local `.env` sets `AIOS_ROUTER_CLOUD_TASKS=reasoning,coding`; mask it with `$env:AIOS_ROUTER_CLOUD_TASKS=''` when testing default local-first privacy behavior.
- The roadmap proof target `frontend/src/pages/Login.jsx` is stale in the current repo, so Phase 1A/1B tests use temp workspaces with that relative path. Do not wire a real product mission to that stale path without updating the target.
- Cloud reasoning is implemented as injectable clients plus policy evidence; no live cloud provider is invoked by tests, and workers still never see provider SDKs or API keys.
- The preserved knowledge-graph WIP remains in `stash@{0}` from the prior sync task; do not drop it without explicit operator instruction.
- Kimi is currently off; proceed solo unless the operator re-enables a reviewer.

## Active Files
- `aios/runtime/intelligence_gateway.py`
- `aios/runtime/secret_policy.py`
- `aios/runtime/budget_guard.py`
- `aios/runtime/worker_api.py`
- `aios/runtime/worker_entry.py`
- `aios/runtime/backends.py`
- `tests/test_runtime_intelligence_gateway.py`
- `.aios/state/RESUME.md`
- `.aios/memory/experiences.jsonl`
