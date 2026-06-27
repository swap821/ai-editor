# RESUME MANIFEST

Last updated: 2026-06-27T09:10:47Z

## Current Goal
Start Council Runtime v0.1 from the sovereign roadmap, implementing **Phase 0 only** on branch `council-runtime-v01`.

## Last Completed + Verified
- Claimed `council-runtime-phase0` as Codex builder.
- Created branch `council-runtime-v01` from synced `master`.
- Added `FOUNDATION_LOCK.md` declaring the foundation modules that Council Runtime wraps rather than rewrites.
- Added frozen v0.1 Pydantic schemas in `aios/runtime/contracts.py`:
  - `MissionContract`
  - `WorkerResult`
  - `QueenVerdict`
  - `RunLedger`
  - `KingReport`
- Added Phase 0 docstring-only stubs for runtime, council, pheromone memory, and policy modules.
- Added `tests/test_runtime_contracts.py` for imports, valid schemas, invalid schema rejection, unknown-field rejection, and default-factory isolation.
- Verified:
  - `python -m pytest tests/test_runtime_contracts.py -q` -> `4 passed`
  - direct contract import smoke passes
  - no protected foundation modules were modified

## Single Next Action
Review Phase 0. Do not continue into WorkerSpawner, WorkerRuntime behavior, Ollama, cloud, UI, or ToolAgent changes until Phase 0 is accepted.

## Open Approvals / Blockers
- The roadmap text file remains untracked local reference material: `Sovereign AI-OS Transformation Roadmap v.txt`.
- The preserved knowledge-graph WIP remains in `stash@{0}` from the prior sync task; do not drop it without explicit operator instruction.
- Phase 0 is not committed yet.

## Active Files
- `FOUNDATION_LOCK.md`
- `aios/runtime/contracts.py`
- `aios/runtime/__init__.py`
- `aios/runtime/backends.py`
- `aios/runtime/worker_api.py`
- `aios/runtime/worker_entry.py`
- `aios/runtime/spawner.py`
- `aios/runtime/run_ledger.py`
- `aios/runtime/king_report.py`
- `aios/runtime/snapshots.py`
- `aios/runtime/leases.py`
- `aios/runtime/intelligence_gateway.py`
- `aios/runtime/budget_guard.py`
- `aios/runtime/secret_policy.py`
- `aios/council/__init__.py`
- `aios/council/queen_verdict.py`
- `aios/council/council_orchestrator.py`
- `aios/council/service_definitions.py`
- `aios/council/queens/__init__.py`
- `aios/memory/pheromones.py`
- `aios/policy/__init__.py`
- `aios/policy/constitution.py`
- `aios/policy/policy_evolution.py`
- `tests/test_runtime_contracts.py`
- `.aios/state/RESUME.md`
- `.aios/memory/experiences.jsonl`
