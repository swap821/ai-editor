# P2-7 backend god-file split — router wiring extraction (Phase 1)

**Date:** 2026-06-25  
**Scope:** `RENOVATION_PLAN.md` P2-7 — split the two backend god-files for blast-radius. This phase extracts the router-wiring helpers from `aios/api/main.py` into `aios/core/router_wiring.py`. The `ToolAgent` split is deferred to Phase 2 because its helpers are tightly coupled to instance state and deserve its own isolated slice.

---

## Goal

`aios/api/main.py` is 2,777 LOC and concentrates the router policy, provider discovery, model selection, failover wiring, and route evidence in one file. Extracting the cohesive router-wiring block (~260 lines) into `aios/core/router_wiring.py` shrinks the API surface and isolates the cross-provider routing logic so future model/provider changes land in one focused module.

## Current state

- Router helpers live in `aios/api/main.py` lines 1396–1651.
- Functions: `_resolve_local_model`, `_AUTO_IDS`, `_router_policy`, `_build_providers`, `_client_for`, `_maybe_llm_picker`, `_provider_name`, `_active_route`, `_route_metrics`, `_select_chat_client`.
- They depend on `aios.config`, `aios.core.router`, `aios.core.catalog`, `aios.core.model_selector`, `aios.core.failover`, and `aios.memory.development`.
- Tests import them directly from `aios.api.main`:
  - `tests/test_api.py` — `_select_chat_client`
  - `tests/test_gemini.py` — `_select_chat_client`
  - `tests/test_route_wiring.py` — `_build_providers`, `_provider_name`, `_select_chat_client`

## Approach

1. Create `aios/core/router_wiring.py` containing all router-wiring functions and constants.
2. In `aios/api/main.py`, remove the extracted definitions and replace them with a single import of the public API from `aios.core.router_wiring`.
3. Keep the existing import surface working by re-exporting the names from `aios.api.main` (so the three test files do not need to change).
4. Run the backend full suite to ensure no regressions.

## Extraction details

`router_wiring.py` will expose:

```python
__all__ = [
    "_resolve_local_model",
    "_AUTO_IDS",
    "_router_policy",
    "_build_providers",
    "_client_for",
    "_maybe_llm_picker",
    "_provider_name",
    "_active_route",
    "_route_metrics",
    "_select_chat_client",
]
```

The function bodies move unchanged. Imports inside `router_wiring.py` will be the subset needed by those functions:

- `typing.Any, Optional, Sequence`
- `fastapi.HTTPException`
- `aios.config`
- `aios.core.catalog`, `aios.core.catalog.catalog_models`
- `aios.core.failover.FailoverChatClient`
- `aios.core.model_selector.TASK_FAST, select_model, supports_tool_protocol`
- `aios.core.router`
- `aios.memory.development.DevelopmentTracker`
- `aios.logging_config` for `logger`

## Files touched

- Create `aios/core/router_wiring.py`
- Modify `aios/api/main.py` (remove router block, add import + re-export)
- Update `.aios/state/RESUME.md`

## Testing plan

1. `cd C:/Users/kumar/ai-editor && .venv/Scripts/python -m pytest tests/test_route_wiring.py tests/test_api.py tests/test_gemini.py -q`
   Expected: all pass.
2. `.venv/Scripts/python -m pytest -q`
   Expected: full suite passes (654 passed, 1 skipped per current baseline).
3. `npm run typecheck` and frontend tests are unaffected (no frontend changes).

## Out of scope (Phase 2)

- Splitting `aios/agents/tool_agent.py` autonomy/verify/event helpers into companion modules.
- Any behavior change to routing, model selection, or failover.
