# GAGOS Slices 9–24 Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task with a verification checkpoint after every slice.

**Goal:** Implement the supplied GAGOS Slices 9–24 candidate as one causal, supervised control plane with independent slice commits, green focused/full gates, and truthful GitHub evidence.

**Architecture:** Use the supplied cumulative patch only as an implementation candidate. Validate live production callers, authority boundaries, event/read-model flow, and frontend mounting. Commit each slice on its own cumulative branch, carrying forward only code already validated by the preceding slice; the supplied patch has no recoverable historical commits, so any recreated commits use current timestamps and actual local SHAs.

**Tech Stack:** Python 3.14 in the pinned `.venv`, pytest/coverage, FastAPI, SQLite migrations, React/TypeScript/Vite, npm, Docker, GitHub Actions, and the existing GAGOS policy/security spine.

## Global Constraints

- Preserve RED refusal, isolated-executor refusal, capability binding, evidence provenance, rollback checks, secret scrubbing, and frontend/backend authority separation.
- Do not edit `aios/security/{gateway,scope_lock,secret_scanner,audit_logger,injection_shield}.py`.
- Keep one Turn Coordinator, one Policy Kernel, one Action Broker, one MissionContract authority, one Cortex observation bus, one Memory Authority, and one Living Mirror reaction registry.
- No model output, Queen output, worker output, pheromone, or frontend state may grant authority.
- Every slice requires focused tests, the applicable full backend/frontend gates, a ledger/RESUME checkpoint, and a real commit before the next slice.
- The supplied patch is cumulative; assign shared integration files to the first slice that activates their contract and record any unavoidable cumulative-commit limitation in the slice report.
- Do not merge to `master` or claim production readiness; `gagos v1-check --strict` is expected to remain blocked when identity, exact capabilities, or isolated execution are unavailable.

## Slice Map

### Task 1: Slice 9 — Worker Foundry unification

**Files:** `aios/application/workers/**`, `aios/domain/workers/**`, `aios/application/workers/strategies/**`, `aios/council/council_orchestrator.py` integration hunks, `tests/test_worker_foundry.py`.

**Invariant:** All temporary execution strategies are selected and bounded by Worker Foundry/MissionContract; legacy ToolAgent, role-pass, swarm, research, code, test, and inspection behavior is strategy-backed rather than a competing authority path.

**Verification:** `python -m pytest -q -o addopts='' tests/test_worker_foundry.py tests/test_mission_contract_v1.py`; backend coverage gate; frontend typecheck/lint/test/build; `git diff --check`.

**Commit/branch:** `feat(workers): unify bounded worker foundry`; `kimi/gagos-s09-worker-foundry`.

### Task 2: Slice 10 — Privacy Broker and model routing

**Files:** `aios/application/models/**`, `aios/domain/privacy/**`, `aios/core/router.py` and `router_wiring.py` integration hunks, `tests/test_privacy_broker.py`.

**Invariant:** Data classification, local-only policy, allowed providers/models, fallback policy, cost, and routing are deterministic and cannot be widened by model output.

**Verification:** `python -m pytest -q -o addopts='' tests/test_privacy_broker.py tests/test_router.py tests/test_bedrock.py tests/test_gemini.py`; full gates; route/evidence assertions.

**Commit/branch:** `feat(privacy): enforce classification-bound model routing`; `kimi/gagos-s10-privacy-routing`.

### Task 3: Slice 11 — Isolated Executor Service

**Files:** `aios/application/executor/**`, `aios/domain/executor/**`, `aios/infrastructure/executor/**`, `aios/executor_service.py`, `Dockerfile.executor`, `aios/api/deps.py` integration, `tests/test_executor_service.py`.

**Invariant:** Approved actions cross one execution broker into an isolated backend; unavailable isolation fails closed and never falls back to a host subprocess.

**Verification:** `python -m pytest -q -o addopts='' tests/test_executor_service.py tests/test_executor.py tests/test_runtime_worker_container.py`; Dockerfile contract checks; full gates.

**Commit/branch:** `feat(executor): add isolated execution service boundary`; `kimi/gagos-s11-executor-service`.

### Task 4: Slice 12 — Staged workspaces

**Files:** `aios/application/workspaces/**`, `aios/domain/workspaces/**`, `aios/runtime/worktree_backend.py` integration, `tests/test_staged_workspaces.py`.

**Invariant:** Missions operate in collision-safe staged workspaces with explicit baseline/snapshot/digest ownership; project roots are never implicitly overwritten.

**Verification:** `python -m pytest -q -o addopts='' tests/test_staged_workspaces.py tests/test_worktree_backend.py`; path-containment/adversarial tests; full gates.

**Commit/branch:** `feat(workspaces): add collision-safe staged mission workspaces`; `kimi/gagos-s12-staged-workspaces`.

### Task 5: Slice 13 — Evidence and Verification Authorities

**Files:** `aios/application/evidence/**`, `aios/domain/evidence/**`, `aios/core/verification_strength.py` integration, `tests/test_evidence_verification.py`.

**Invariant:** Workers emit canonical evidence bound to mission/action/workspace/environment/tool/command/output digests; verification is target-specific and stale/weak evidence cannot promote.

**Verification:** `python -m pytest -q -o addopts='' tests/test_evidence_verification.py tests/test_verification_strength.py tests/test_auto_verify_strength_regression.py`; adversarial verification tests; full gates.

**Commit/branch:** `feat(evidence): add provenance-bound verification authorities`; `kimi/gagos-s13-evidence-verification`.

### Task 6: Slice 14 — Atomic Promotion and Recovery

**Files:** `aios/application/promotion/**`, `aios/application/governance/emergency_stop.py` integration, `aios/operations/recovery.py`, `tests/test_promotion_authority.py`, `tests/test_rollback.py`, `tests/test_audit_recovery.py`.

**Invariant:** Promotion confirms state/capability/baseline/contract/verification, checkpoints before mutation, smoke-tests, and restores exact recovery state on failure.

**Verification:** focused promotion/rollback/recovery tests; dirty-tree and stale-scope cases; full gates.

**Commit/branch:** `feat(promotion): make promotion atomic and recoverable`; `kimi/gagos-s14-promotion-recovery`.

### Task 7: Slice 15 — Durable Cortex consumer semantics

**Files:** `aios/runtime/cortex_bus.py`, `aios/runtime/cortex_bus_dispatcher.py`, `tests/test_cortex_consumers.py`, `tests/test_cortex_bus.py`, `tests/test_stream_protocol.py`.

**Invariant:** Cortex remains observation-only with independent durable cursors, bounded replay/SSE queues, idempotent delivery, retry/quarantine, and authority-family blocking.

**Verification:** focused Cortex/SSE tests; bounded-queue and replay tests; full gates.

**Commit/branch:** `feat(cortex): add durable independent consumer semantics`; `kimi/gagos-s15-cortex-consumers`.

### Task 8: Slice 16 — Incremental system read models

**Files:** `aios/application/read_models/**`, `aios/domain/read_models/**`, `frontend/src/superbrain/lib/mirrorStore.ts`, `tests/test_read_model_projection.py`.

**Invariant:** System portrait and active-state projections update incrementally from canonical events/authorities; production metrics are measured/derived/unavailable/stale rather than synthetic.

**Verification:** `python -m pytest -q -o addopts='' tests/test_read_model_projection.py tests/test_mirror.py tests/test_live_surface.py`; frontend gates; projection rebuild test.

**Commit/branch:** `feat(read-models): add incremental system projections`; `kimi/gagos-s16-read-models`.

### Task 9: Slice 17 — One Memory Authority

**Files:** `aios/application/memory/**`, `aios/domain/memory/**`, `aios/infrastructure/memory/**`, `aios/infrastructure/storage/migrations/0002_memory_provenance.py`, `aios/infrastructure/storage/migrations/__init__.py`, `aios/api/routes/memory.py`, `tests/test_memory_authority.py`.

**Invariant:** Specialized memories remain physically distinct but share one provenance, verification, promotion, supersession, compaction, and rebuild authority; pheromones stay advisory.

**Verification:** focused memory/migration tests; fresh-install/upgrade migration tests; full gates.

**Commit/branch:** `feat(memory): centralize provenance and promotion authority`; `kimi/gagos-s17-memory-authority`.

### Task 10: Slice 18 — Governed learning and autonomy

**Files:** `aios/application/autonomy/**`, `aios/domain/autonomy/**`, `aios/core/autonomy.py`, `tests/test_governed_autonomy.py`, `tests/test_earned_autonomy_integration.py`.

**Invariant:** Learning follows attempt→evidence→verification→outcome→proposal→promotion; trust is per action class/project and failure/policy/tool/model changes decay or invalidate it. Production autonomy remains gated.

**Verification:** focused governed-autonomy tests; adversarial autonomy safety tests; full gates.

**Commit/branch:** `feat(autonomy): govern earned learning by verified outcomes`; `kimi/gagos-s18-governed-autonomy`.

### Task 11: Slice 19 — Four product spaces

**Files:** `frontend/src/workbench/ProductSpaces.jsx`, `frontend/src/workbench/ProductSpaces.css`, `frontend/src/workbench/ProductSpaces.test.jsx`, `frontend/src/superbrain/SuperbrainApp.jsx`.

**Invariant:** Living Mind, Workbench, Governance, and History expose the real backend Council/mission/evidence/capability/recovery state without granting authority or opening every panel by default.

**Verification:** frontend typecheck/lint/test/build; non-WebGL governance interaction tests; backend unaffected gate.

**Commit/branch:** `feat(frontend): add truthful four-space product shell`; `kimi/gagos-s19-product-spaces`.

### Task 12: Slice 20 — Constitutionally truthful Living Mirror

**Files:** `frontend/src/superbrain/lib/aiosMirror.ts`, `frontend/src/superbrain/lib/livingMirrorRegistry.ts`, `frontend/src/superbrain/lib/livingMirrorRegistry.test.ts`, `frontend/src/superbrain/lib/mirrorStore.ts`, `aios/api/routes/mirror.py`, `tests/test_mirror.py`.

**Invariant:** Operational reactions trace to canonical backend events; narrative, ambient, and interaction state cannot claim operational activity. Unknown events are safely logged/ignored and accessibility text mirrors operational truth.

**Verification:** living-mirror registry tests; backend mirror/read-model tests; frontend gates; texture/CSS canon checks.

**Commit/branch:** `feat(mirror): bind organism reactions to canonical events`; `kimi/gagos-s20-living-mirror`.

### Task 13: Slice 21 — Operations, observability, and recovery

**Files:** `aios/operations/**`, `aios/launcher.py` operational paths, `docker-compose.yml`, `gateway/nginx.conf`, `tests/test_operations.py`, `tests/test_launcher.py`.

**Invariant:** Local operations are understandable and recoverable with loopback/internal observability, redacted support data, correlated IDs, emergency stop visibility, and no default public credentials.

**Verification:** operations/launcher tests; compose topology/config checks; security scan; full gates.

**Commit/branch:** `feat(operations): add doctor recovery and traceable control plane`; `kimi/gagos-s21-operations`.

### Task 14: Slice 22 — CI as release authority

**Files:** `.github/workflows/ci.yml`, `scripts/security_scan.py`, `scripts/generate_sbom.py`, `scripts/check_frontend_warning_budget.mjs`, `.aios/state/FRONTEND_WARNING_BUDGET.json`, `pyproject.toml`, `tests/test_release_conformance.py`.

**Invariant:** CI exercises production-relevant backend/frontend/security/container/SBOM/conformance gates and the warning budget only decreases.

**Verification:** local workflow-equivalent commands; release-conformance tests; `git diff --check`; push and wait for GitHub Actions before continuing.

**Commit/branch:** `ci(release): make production gates explicit`; `kimi/gagos-s22-ci-release-authority`.

### Task 15: Slice 23 — Package the single-developer product

**Files:** `aios/__main__.py`, `aios/launcher.py`, `gagos`, `gagos.cmd`, `Dockerfile.frontend`, `docs/operations/PACKAGED_PRODUCT.md`, `frontend/vite.config.js`, `tests/test_launcher.py`.

**Invariant:** `gagos start/stop/status/open` and clean-machine bootstrap preserve projects, use one local origin in production, and expose upgrade/rollback boundaries.

**Verification:** launcher/bootstrap/release tests; frontend build; package/compose checks; push and wait for GitHub Actions.

**Commit/branch:** `feat(packaging): add single-developer product launcher`; `kimi/gagos-s23-packaged-product`.

### Task 16: Slice 24 — Controlled autonomy and v1 declaration

**Files:** `aios/application/governance/**`, `aios/domain/governance/**`, `docs/architecture/V1_RELEASE_DECLARATION.md`, `tests/test_governance.py`, `tests/test_v1_declaration.py`, `tests/test_release_conformance.py`.

**Invariant:** L0–L4 autonomy, emergency stop, capability revocation, worker cancellation, evidence preservation, and truthful v1 blockers are explicit and fail closed.

**Verification:** focused governance/release tests; full backend coverage; frontend gates; security scan; `python -m aios.launcher v1-check --json`; `python -m aios.launcher v1-check --strict` with its real exit status; push final branch and wait for GitHub Actions.

**Commit/branch:** `feat(governance): add emergency stop and truthful v1 declaration`; `kimi/gagos-s24-controlled-autonomy`.

## Checkpoint Protocol

After every slice, record the exact command outputs and SHA in `.aios/state/RESUME.md`, append one experience object to `.aios/memory/experiences.jsonl`, update `.aios/state/PRODUCTION_CONVERGENCE_LEDGER.md`, run `git diff --check`, and stop advancing if any focused test, full gate, or remote CI check is red. The final PR is draft-only; no merge to `master` is authorized.
