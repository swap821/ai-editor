# R15 Progress Ledger

## Slice 1: Canonical Intelligence Boundary Audit

- **Exact baseline SHA:** `b810d918f1556711a47ea0639025ea86b59290a2`
- **Goal:** Inventory every active local and cloud model call and establish one future canonical path (`ModelRouter`).
- **Files inspected:** `aios/api/main.py`, `aios/application/turns/generate_pipeline.py`, `aios/core/router_wiring.py`, `aios/application/models/model_router.py`, `aios/runtime/intelligence_gateway.py`
- **Files changed:** `.aios/state/INTELLIGENCE_CALL_INVENTORY.md`
- **Tests written:** `tests/architecture/test_intelligence_boundary.py`
- **Commands executed:** `pytest tests/architecture/test_intelligence_boundary.py`
- **Pass/fail counts:** 1 failed, 1 warning (Expected failure as `generate_pipeline.py` currently bypasses the architecture boundary).
- **Coverage changes:** N/A (Documentation and architecture test).
- **Runtime evidence:** N/A for audit phase.
- **Known limitations:** Architecture test currently fails on `aios/application/turns/generate_pipeline.py`. This is expected and will be addressed in Phase 1 of the intelligence migration (which maps to the broader R15 plan).
- **Security impact:** Defines a rigid canonical path for all intelligence requests, preparing the codebase to force all AI generation through the PrivacyBroker and policy engine.
- **Exact next action:** Proceed to Slice 2 (Curated Local Workforce Domain).

## Slice 2: Curated Local Workforce Domain

- **Exact baseline SHA:** `f1c1864fb38e1fbf1965bbf00aea9d4f3bdcda99`
- **Goal:** Create the minimal product model for one small local clerk, defining bounded domain types for local work.
- **Files inspected:** `aios/domain/workers/worker_contract.py`
- **Files changed:** `aios/domain/local_workforce/__init__.py`, `aios/domain/local_workforce/contracts.py`
- **Tests written:** `tests/domain/test_local_workforce_contracts.py`
- **Commands executed:** `pytest tests/domain/test_local_workforce_contracts.py`
- **Pass/fail counts:** 2 passed
- **Coverage changes:** Negligible (added purely Pydantic domain models).
- **Runtime evidence:** N/A (domain models only, no runtime impact yet).
- **Known limitations:** None. Domain types are bounded exactly as defined in the master plan.
- **Security impact:** Defines a rigid interface for local clerk interactions ensuring no execution context, capabilities, or direct state mutation can occur via the return values.
- **Exact next action:** Proceed to Slice 3 (Durable Local Workforce Registry).

## Slice 14/15: Evidence Repair Checkpoint

- **Working branch:** `antigravity/r15-sovereign-intelligence-flywheel`
- **Verified source tip before this repair:** `224d2165b3d10c82a851a2ca840d5c996d592128`
- **Goal:** Replace false-positive R15 runtime acceptance evidence with executable probes before any R16 readiness claim.
- **Files changed:** `aios/application/governance/r15_runtime_proof.py`, `aios/domain/maintenance/repository.py`, `aios/domain/maintenance/__init__.py`, R15/architecture tests, and release evidence.
- **Runtime proof:** All 12 R15 probes pass locally with behavioral evidence; no placeholder `"<name> proven"` evidence remains.
- **Backend gate:** 3,235 passed, 8 skipped, 88% coverage; exit 0 on the repaired tree.
- **Focused gate:** 56 affected R15/domain/architecture tests passed; Ruff and compile checks passed.
- **Known limitations:** Benchmark is not run, qualification is fixture-only, private Executor is unavailable locally, hosted CI/CodeQL has not been established for this dirty tree, and non-builder handoff is absent.
- **Exact next action:** Run the hosted-equivalent release/strict gates and produce a hash-pinned R15 handoff only after all release artifacts are generated from the repaired source.

## Slice 16: Cross-Platform Gate Repair

- **Working branch:** `antigravity/r15-sovereign-intelligence-flywheel`
- **Goal:** Repair the source-tip failures captured by the hosted CI matrix without weakening strict runtime gates.
- **Repairs:** Imported `Sequence` for Python 3.12 annotation evaluation in the hiring broker and registered the `architecture` pytest marker under strict marker mode; fixed six impure `Math.random()` React list-key fallbacks and cleaned adjacent frontend lint warnings.
- **Verified gates:** Full backend rerun: 3,235 passed, 8 skipped, 88% coverage, exit 0. Frontend: 104 files/600 tests passed, typecheck passed, lint passed, production build passed. Strict release validator passed every gate except the two private-Executor runtime gates.
- **Hosted evidence:** The prior source tip failed all three backend matrices during collection and frontend lint on six impure key expressions; those failures are repaired locally and require a new pushed source tip for hosted confirmation.
- **Known limitations:** Private Executor remains unavailable; benchmark and real model qualification remain fixture-only; no non-builder handoff verdict exists.
- **Exact next action:** Commit/push this verified repair and inspect the new hosted CI/CodeQL result before any R15 acceptance or public R16 readiness claim.
