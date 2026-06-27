# RESUME MANIFEST

Last updated: 2026-06-27T10:15:45Z

## Current Goal
Build Council Runtime v0.1 from the sovereign roadmap. The roadmap remains the near-term canon: Phase 0 foundation lock, 30-day First Heartbeat, then 24-week v1.0.

## Last Completed + Verified
- Phase 1A deterministic worker birth is implemented on branch `council-runtime-v01`.
- Added `WorkerBackend` / `ControlledSubprocessBackend` in `aios/runtime/backends.py`.
- Added policy-only `WorkerRuntime` in `aios/runtime/worker_api.py` enforcing workspace bounds, allowed/forbidden files, allowed/forbidden tools, max steps, blocked-attempt recording, evidence, approval-request JSON, and `shell=False` command execution.
- Added deterministic worker entrypoint in `aios/runtime/worker_entry.py`: forbidden probe -> allowed-file read/write -> verification command -> `WorkerResult` -> exit.
- Added `SnapshotManager`, `RunLedgerStore`, `KingReportStore`, and `WorkerSpawner.run()` orchestration.
- Added `tests/test_runtime_worker_birth.py` proving forbidden backend access is blocked, only the allowed file is touched, verification runs, result/ledger/report JSON are persisted, the worker dies, and cloud/API-key env values are not passed to workers.
- Committed Phase 1A as `bcec6e1` and pushed `council-runtime-v01` to GitHub.
- Verified:
  - `.venv\Scripts\python.exe -m pytest tests\test_runtime_contracts.py tests\test_runtime_worker_birth.py -q` -> 8 passed.
  - `$env:AIOS_ROUTER_CLOUD_TASKS=''; .venv\Scripts\python.exe -m pytest -q --cov=aios --cov-report=term-missing --cov-report=xml --cov-fail-under=85` -> pass, 1 skipped, 86.28% coverage, 1 known httpx warning.
  - `git diff --check` -> pass, CRLF warnings only.
  - GitHub Actions CI run `28286158676` -> success (`backend` 3m33s, `frontend` 58s).
  - Protected foundation modules were not modified.

## Single Next Action
Begin Phase 1B Hybrid Intelligence Worker Birth: `IntelligenceGateway`, local Ollama route, `SecretPolicy`, `BudgetGuard`, and plan-only model output through `WorkerRuntime.request_plan()`. Do not give workers direct model SDK access, API keys, approval authority, or execution authority.

## Open Approvals / Blockers
- Local `.env` sets `AIOS_ROUTER_CLOUD_TASKS=reasoning,coding`; mask it with `$env:AIOS_ROUTER_CLOUD_TASKS=''` when testing default local-first privacy behavior.
- The deterministic roadmap proof target `frontend/src/pages/Login.jsx` is stale in the current repo, so Phase 1A tests use a temp workspace with that relative path. Do not wire a real product mission to that stale path without updating the target.
- The preserved knowledge-graph WIP remains in `stash@{0}` from the prior sync task; do not drop it without explicit operator instruction.
- Kimi is currently off; proceed solo unless the operator re-enables a reviewer.

## Active Files
- `aios/runtime/backends.py`
- `aios/runtime/worker_api.py`
- `aios/runtime/worker_entry.py`
- `aios/runtime/spawner.py`
- `aios/runtime/snapshots.py`
- `aios/runtime/run_ledger.py`
- `aios/runtime/king_report.py`
- `tests/test_runtime_worker_birth.py`
- `.aios/state/RESUME.md`
- `.aios/memory/experiences.jsonl`
