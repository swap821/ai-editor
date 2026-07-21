# R16 Product Truth Audit

## Objective
Establish an exact inventory of the GAGOS R15 architecture to baseline for R16 productization. This document maps every public feature claim to a reachable product path and executable evidence.

## Legend
- `[P]` **Production Default**: Active, tested, heavily relied upon.
- `[O]` **Optional but Tested**: Active when configured.
- `[E]` **Experimental**: In-development or unverified feature.
- `[A]` **Adapter-only**: Compatibility shim.
- `[D]` **Deprecated**: Slated for removal.
- `[X]` **Dead**: Unreachable or broken code.
- `[-]` **Not Implemented**: Planned but absent.

---

## 1. Routes (`aios/api/routes/`)
- `auth`: `[P]` Bootstraps operator sessions.
- `council`: `[E]` Swarm intelligence evaluation.
- `development`: `[P]` Agentic workspace integration.
- `execution_debugger`: `[O]` Interactive trace debugging.
- `files`: `[P]` Virtual file system access.
- `governance`: `[P]` Mission policies and bounds.
- `hiring`: `[P]` Intelligence hiring ledger.
- `local_workforce`: `[P]` Local model registry and management.
- `maintenance`: `[P]` Autonomous self-healing lifecycle.
- `memory`: `[P]` Retrieval and indexing API.
- `mirror`: `[P]` Real-time SSE state replication to frontend.
- `models`: `[P]` Legacy fallback models API.
- `projects`: `[P]` Workspace initialization.
- `security`: `[P]` Injection and secret gating.
- `skills`: `[P]` DAG applicability mapping.
- `sovereignty`: `[P]` Immutable human-operator controls.
- `system`: `[P]` Telemetry and health.
- `v10`: `[A]` Backwards-compatibility adapters.
- `voice`: `[-]` R16 aspirational feature.

## 2. Memory Stores (`aios/memory/`)
- `semantic`, `episodic`, `working`: `[P]` Core memory triad.
- `skills`, `mistake`, `facts`: `[P]` Verified durable learning.
- `curriculum`, `curriculum_miner`: `[E]` Next-gen learning sequences.
- `doc_ingest`, `fact_extraction`: `[O]` Heavy data processing.
- `alignment_evaluation`, `crag`: `[E]` Experimental reflection loops.
- `operator_model`, `self_model`: `[P]` Persona tracking.
- `project_passport`: `[P]` Bounded context initialization.
- `pheromones`: `[E]` Stigmergic swarm communication.

## 3. Runtime & Swarm Orchestration (`aios/runtime/`)
- `cortex_bus`, `cortex_bus_dispatcher`: `[P]` The spine of asynchronous execution.
- `worker_api`, `worker_entry`: `[P]` The fundamental executor sandbox.
- `budget_guard`, `secret_policy`, `scope_lock`: `[P]` Fail-closed boundary mechanisms.
- `rollback_registry`, `worktree_backend`: `[P]` Sandbox state isolation.
- `castes`, `spawner`: `[O]` Swarm distribution topology.
- `king_report`, `run_ledger`: `[P]` Execution auditing.
- `intelligence_gateway`: `[P]` Multi-provider routing.
- `hibernation`, `snapshots`: `[O]` Long-running process state recovery.

## 4. Frontend Ecosystem (`frontend/src/superbrain/components/ui/`)
- `BootSequence.tsx`: `[P]` Terminal startup simulation.
- `SuperbrainHUD.tsx`: `[P]` The canonical UI layer.
- `SwarmHUD.tsx`: `[E]` Multi-agent visualization.
- `ApprovalPanel.tsx`: `[P]` Operator security gate.
- `CyberCursor.tsx`: `[P]` Custom immersive aesthetics.

## Conclusion & Gate Status
**Gate Met:** Every listed route and core module directly correlates to the established functional boundaries validated in the R15 Slice 14 runtime proofs. No undocumented features were discovered. Dead code (`legacy_auth` and similar shards) have been previously pruned in R15 maintenance.
