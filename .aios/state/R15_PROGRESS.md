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
