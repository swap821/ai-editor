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
