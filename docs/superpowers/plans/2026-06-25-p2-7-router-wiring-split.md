# P2-7 router wiring split — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the cohesive router-wiring helpers out of `aios/api/main.py` into `aios/core/router_wiring.py`, preserving the public import surface and all existing tests.

**Architecture:** Extract the ~260-line block (local-model resolution, policy, provider discovery, model selection, failover wiring, route evidence) into a focused core module. `main.py` re-exports the same names so tests and endpoints keep working.

**Tech Stack:** Python 3.12, FastAPI, internal `aios.core.router` / `aios.core.catalog` / `aios.core.failover` / `aios.core.model_selector` modules.

---

## File map

- Create: `aios/core/router_wiring.py`
- Modify: `aios/api/main.py` (remove lines 1396–1651, add import + re-export)

---

## Task 1: Create `aios/core/router_wiring.py`

**Files:**
- Create: `aios/core/router_wiring.py`

- [ ] **Step 1: Write the new module**

Create `aios/core/router_wiring.py` with the following contents (function bodies copied verbatim from `aios/api/main.py`):

```python
from __future__ import annotations

from typing import Any, Optional, Sequence

from fastapi import HTTPException

from aios import config
from aios.core import catalog, router
from aios.core.catalog import catalog_models
from aios.core.failover import FailoverChatClient
from aios.core.model_selector import (
    TASK_FAST,
    select_model,
    supports_tool_protocol,
)
from aios.logging_config import logger

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


def _resolve_local_model(model_id: Optional[str]) -> str:
    """Map a UI model id to a local Ollama tag (``ollama.x`` -> ``x``).

    Non-local ids (or none) fall back to the configured default local model, so
    the local-first backend always has something to run.
    """
    if model_id and model_id.startswith("ollama."):
        return model_id[len("ollama.") :]
    return config.LLM_MODEL


#: UI model ids meaning "let the agent choose the best installed local model".
_AUTO_IDS = frozenset({"auto", "auto.best", "ollama.auto"})


def _router_policy() -> router.Policy:
    """Build the cross-provider routing policy from operator config.

    The privacy boundary (``ROUTER_CLOUD_TASKS``) is read fresh each call so it
    stays operator-owned and overridable; empty -> local-first (cloud off).
    """
    return router.Policy(
        cloud_tasks=frozenset(config.ROUTER_CLOUD_TASKS),
        max_cost=config.ROUTER_MAX_COST,
        prefer_local=config.ROUTER_PREFER_LOCAL,
    )


def _build_providers(
    ollama: Any, bedrock: Optional[Any], gemini: Optional[Any]
) -> list[router.Provider]:
    """Describe the live providers as router :class:`~aios.core.router.Provider` rows.

    Local Ollama is always present (available iff it can list chat models); each
    cloud provider appears only when its client is configured. Fail-soft: a flaky
    Ollama listing yields an *unavailable* local provider rather than raising.
    """
    try:
        local_models = (ollama.list_models() or {}).get("models") or []
    except Exception as exc:  # noqa: BLE001 - discovery must never break a turn
        logger.warning("Local model discovery failed", exc_info=exc)
        local_models = []
    providers = [
        router.Provider(
            name=router.PROVIDER_OLLAMA,
            privacy=router.PRIVACY_LOCAL,
            cost=router.COST_FREE,
            available=bool(local_models),
            models=tuple(m for m in local_models if isinstance(m, str)),
        )
    ]
    # BREADTH: one candidate per model the provider actually offers (its catalog),
    # not just the configured default — so auto + failover + calibration span the
    # many models AWS/Vertex expose. Discovery is account-accurate + cached.
    for cloud, name, default in (
        (bedrock, router.PROVIDER_BEDROCK, config.BEDROCK_MODEL),
        (gemini, router.PROVIDER_GEMINI, config.GEMINI_MODEL),
    ):
        if cloud is None:
            continue
        cost = router.COST_HIGH if name == router.PROVIDER_BEDROCK else router.COST_LOW
        for mid in catalog_models(cloud, name, default):
            cap = catalog.cloud_capability(mid) + (catalog.DEFAULT_BONUS if mid == default else 0)
            providers.append(
                router.Provider(
                    name=name,
                    privacy=router.PRIVACY_CLOUD,
                    cost=cost,
                    available=True,
                    models=(mid,),
                    capability=cap,
                )
            )
    return providers


def _client_for(provider: str, ollama: Any, bedrock: Optional[Any], gemini: Optional[Any]) -> Optional[Any]:
    """Map a router provider name back to its live chat client."""
    if provider == router.PROVIDER_BEDROCK:
        return bedrock
    if provider == router.PROVIDER_GEMINI:
        return gemini
    return ollama


def _maybe_llm_picker(
    ollama: Any,
    providers: list[router.Provider],
    cands: Sequence[router.Route],
    task: str,
) -> Optional[Any]:
    """Build the HYBRID local-LLM route picker, or ``None`` to stay deterministic.

    Returns a callable only when it would actually matter: the picker is enabled
    (:data:`config.ROUTER_LLM_PICK`), there are **2+ candidates** for the task (so
    there is a real choice — the default local-only path never reaches here, paying
    zero latency), and a local model exists to make the meta-decision. *cands* is
    the already-ranked candidate list (computed once by the caller, not re-derived).
    The picker asks a small/fast local model to choose from the allow-list; its
    answer is still validated against the allowed candidates in
    :func:`aios.core.router.pick_from`, so it can prefer but never escape the policy.
    """
    if not config.ROUTER_LLM_PICK or len(cands) < 2:
        return None
    local_tags = next(
        (list(p.models) for p in providers if p.name == router.PROVIDER_OLLAMA), []
    )
    # A cheap local model just to choose — no tools needed for the meta-decision.
    meta_model = select_model(local_tags, task=TASK_FAST, require_tools=False)
    if not meta_model:
        return None  # no local model to decide with -> deterministic ranking wins

    def picker(candidates: Sequence[router.Route]) -> Optional[str]:
        try:
            resp = ollama.chat(
                [
                    {"role": "system", "content": router.PICKER_SYSTEM},
                    {"role": "user", "content": router.picker_prompt(task, candidates)},
                ],
                tools=None,
                model=meta_model,
            )
            return router.parse_pick((resp or {}).get("content", ""), candidates)
        except Exception as exc:  # noqa: BLE001 - a flaky local pick must never break routing
            logger.warning("Local LLM route picker failed; falling back to deterministic", exc_info=exc)
            return None

    return picker


def _provider_name(chat_client: Any, bedrock: Optional[Any], gemini: Optional[Any]) -> str:
    """The router provider name for the selected *chat_client* (for evidence + UI)."""
    if bedrock is not None and chat_client is bedrock:
        return router.PROVIDER_BEDROCK
    if gemini is not None and chat_client is gemini:
        return router.PROVIDER_GEMINI
    return router.PROVIDER_OLLAMA


def _active_route(
    chat_client: Any, bedrock: Optional[Any], gemini: Optional[Any], model: str
) -> tuple[str, str]:
    """The ``(provider, model)`` that ACTUALLY served — truthful under failover.

    A :class:`FailoverChatClient` reports the candidate currently serving the turn
    (which may differ from the top pick once it has ridden a failover), so the
    audit + the router's evidence calibration credit the model that did the work.
    """
    if isinstance(chat_client, FailoverChatClient):
        return chat_client.active_provider, chat_client.active_model
    return _provider_name(chat_client, bedrock, gemini), model


def _route_metrics(development: Any, model_id: Optional[str]) -> dict:
    """Measured per-(provider,model,task) success rates for evidence calibration.

    Read only when it can change the route — an ``auto`` turn with cloud opted in
    and calibration on — so the common (default, local-only) path never pays for a
    DB read. Fail-soft: any error yields ``{}`` (the router falls back to heuristic).
    """
    if (
        model_id not in _AUTO_IDS
        or not config.ROUTER_CLOUD_TASKS
        or config.ROUTER_CALIBRATION_WEIGHT <= 0
    ):
        return {}
    try:
        return development.model_task_success_rates()
    except Exception as exc:  # noqa: BLE001 - calibration metrics must never break a turn
        logger.warning("Route calibration metrics unavailable", exc_info=exc)
        return {}


def _select_chat_client(
    model_id: Optional[str],
    ollama: Any,
    bedrock: Optional[Any],
    *,
    gemini: Optional[Any] = None,
    task: str = "coding",
    metrics: Optional[dict] = None,
    calibration_weight: float = 0.0,
) -> tuple[Any, str]:
    """Pick the ``(chat_client, model)`` for the requested UI model id.

    ``auto`` runs the **cross-provider router**: the agent picks the best model for
    *task* across local + (policy-permitted) cloud providers. The privacy boundary
    is deterministic and operator-owned (:func:`_router_policy`) — with the default
    empty ``ROUTER_CLOUD_TASKS`` no task ever leaves the machine, so ``auto`` stays
    local-only exactly as before. ``ollama.x`` always runs locally on ``x``. A
    ``gemini.x`` id routes to Google Gemini; any other explicit id routes to
    Bedrock. Each explicit cloud pick fails clearly when that provider is
    unavailable and never silently changes providers. No id means the local default.
    """
    if model_id in _AUTO_IDS:
        # Cross-provider auto-route, gated by the operator privacy/cost policy. The
        # agentic loop requires tool-calling, so local candidates must be tool-capable.
        # When the policy permits a real choice (2+ candidates), a local model makes
        # the hybrid pick among them; otherwise routing is purely deterministic.
        providers = _build_providers(ollama, bedrock, gemini)
        policy = _router_policy()
        # Compute the policy-allowed candidates ONCE (ranked, optionally calibrated
        # by measured per-(provider,model,task) success), then run the (optional)
        # hybrid pick over them — no redundant gate+scoring recomputation.
        cands = router.candidates(
            task, providers, policy=policy, require_tools=True,
            metrics=metrics, calibration_weight=calibration_weight,
        )
        chosen = router.pick_from(cands, picker=_maybe_llm_picker(ollama, providers, cands, task))
        if chosen is not None:
            # FAILOVER cascade: the picked route first, then the rest of the allowed
            # candidates by rank. If the primary errors mid-turn, FailoverChatClient
            # rides the next automatically — one model's outage never blocks the work.
            ordered = [chosen] + [r for r in cands if r is not chosen]
            cascade = []
            for r in ordered:
                client = _client_for(r.provider, ollama, bedrock, gemini)
                if client is not None:
                    cascade.append((client, r.model, r.provider))
            if len(cascade) == 1:
                # Only one allowed candidate -> the raw client (nothing to ride).
                return cascade[0][0], cascade[0][1]
            if cascade:
                return FailoverChatClient(cascade), cascade[0][1]
        # Nothing the policy allows is usable (e.g. no local model + cloud not
        # opted in). Fail-soft to the local default — NEVER silently to cloud, so
        # the privacy boundary holds even on the fallback path.
        return ollama, config.LLM_MODEL
    if model_id and model_id.startswith("ollama."):
        local_model = _resolve_local_model(model_id)
        if not supports_tool_protocol(local_model):
            raise HTTPException(
                status_code=422,
                detail=f"local model '{local_model}' cannot accept the agent tool protocol",
            )
        return ollama, local_model
    if model_id and model_id.startswith("gemini."):
        # Explicit Gemini pick (``gemini.<model>``) -> the Vertex client, with the
        # provider prefix stripped to the bare model id. Fails clearly (never falls
        # through to another provider) when Gemini isn't configured.
        if gemini is not None:
            return gemini, model_id[len("gemini.") :]
        raise HTTPException(
            status_code=503,
            detail="Gemini model selected but Google Gemini is not configured",
        )
    if model_id and bedrock is not None:
        # Pass the selected Bedrock model id straight through (so each dropdown
        # choice runs that actual model).
        return bedrock, model_id
    if model_id:
        raise HTTPException(
            status_code=503,
            detail="cloud model selected but AWS Bedrock is not configured",
        )
    return ollama, config.LLM_MODEL
```

- [ ] **Step 2: Typecheck the new module**

Run: `.venv/Scripts/python -m py_compile aios/core/router_wiring.py`
Expected: exit 0.

---

## Task 2: Remove the block from `aios/api/main.py` and re-export

**Files:**
- Modify: `aios/api/main.py:1396–1651`

- [ ] **Step 1: Delete the router-wiring block**

Remove everything from `def _resolve_local_model(...)` through the end of `def _select_chat_client(...)` (lines 1396–1651). Keep the blank lines tidy so the next function (`_to_chat_messages`) still starts cleanly.

- [ ] **Step 2: Add the import + re-export**

Add this near the other `aios.*` imports at the top of `aios/api/main.py`:

```python
from aios.core.router_wiring import (
    _active_route,
    _build_providers,
    _client_for,
    _maybe_llm_picker,
    _provider_name,
    _resolve_local_model,
    _route_metrics,
    _router_policy,
    _select_chat_client,
)
```

Also add `_AUTO_IDS` to the import list:

```python
from aios.core.router_wiring import (
    _AUTO_IDS,
    _active_route,
    _build_providers,
    _client_for,
    _maybe_llm_picker,
    _provider_name,
    _resolve_local_model,
    _route_metrics,
    _router_policy,
    _select_chat_client,
)
```

No other code changes are needed; the function names remain in scope inside `main.py` because of this import.

- [ ] **Step 3: Remove now-unused imports from `main.py`**

After the move, `aios/core/model_selector` is still used elsewhere in `main.py` (line 1335 `supports_tool_protocol`, line 1387–1388 `select_model`), so keep it. `aios.core.failover` is used only by the extracted block, but verify no other references exist with:

Run: `.venv/Scripts/python -c "import aios.api.main"`
Expected: no `ImportError`.

If `FailoverChatClient` is no longer used directly in `main.py`, remove `from aios.core.failover import FailoverChatClient` from the imports. If removal causes an import error, keep it.

---

## Task 3: Verify the backend gates

- [ ] **Step 1: Run the router-related tests**

Run: `.venv/Scripts/python -m pytest tests/test_route_wiring.py tests/test_api.py tests/test_gemini.py -q`
Expected: all pass.

- [ ] **Step 2: Run the full backend suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: 654 passed, 1 skipped (or current live count), exit 0.

- [ ] **Step 3: Smoke-import the API module**

Run: `.venv/Scripts/python -c "from aios.api import main; print('ok')"`
Expected: prints `ok`.

---

## Task 4: Update continuity docs and commit

- [ ] **Step 1: Update `.aios/state/RESUME.md`**

Add a P2-7 Phase 1 row summarizing the extraction, test counts, and the deferred ToolAgent Phase 2.

- [ ] **Step 2: Commit and push**

```bash
git add -A
git commit -m "refactor: extract router wiring from main.py to aios/core/router_wiring.py

Move _resolve_local_model, _router_policy, _build_providers, _client_for,
_maybe_llm_picker, _provider_name, _active_route, _route_metrics, and
_select_chat_client into a focused core module. Re-export from main.py so
existing tests/endpoints keep working.

Verified: pytest router + api + gemini tests pass; full backend suite passes."
git push origin master
```

---

## Spec coverage check

| Spec requirement | Task covering it |
|------------------|------------------|
| Create `aios/core/router_wiring.py` | Task 1 |
| Remove block from `aios/api/main.py` | Task 2 |
| Preserve public import surface | Task 2 (re-export) |
| Full backend tests pass | Task 3 |
| Update RESUME | Task 4 |
