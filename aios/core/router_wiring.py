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
from aios.logging_config import get_logger

logger = get_logger(__name__)

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
    """Build the cross-provider routing policy from the active runtime profile.

    The privacy boundary is now owned by ``PolicyKernel`` via the runtime
    profile. The profile is read fresh each call so operator overrides stay
    effective; an empty ``cloud_tasks`` set means local-first (cloud off).
    """
    # Imported lazily to keep the router wiring free of API-layer imports at
    # module-load time.
    from aios.api.deps import get_policy_kernel

    return get_policy_kernel().router_policy()


def _provider_health_tracker() -> Any:
    """The process-wide provider-health circuit-breaker singleton (organ 34).

    Lazily imported for the same reason as ``_router_policy`` above. Never
    raises: a construction failure here must not break routing, so a lookup
    error yields ``None`` (the failover client stays fully functional, just
    unobserved for this one call).
    """
    try:
        from aios.api.deps import get_provider_health

        return get_provider_health()
    except Exception:  # noqa: BLE001 - observability must never break routing
        return None


def _privacy_audit_tracker_singleton() -> Any:
    """The process-wide privacy-audit tracker singleton (organ 50).

    Same fail-soft contract as ``_provider_health_tracker`` above: a lookup
    error must never break routing, so it yields ``None`` (the failover
    client stays fully functional, just unobserved for this one call).
    """
    try:
        from aios.api.deps import get_privacy_audit_tracker

        return get_privacy_audit_tracker()
    except Exception:  # noqa: BLE001 - observability must never break routing
        return None


def _build_providers(
    ollama: Any,
    bedrock: Optional[Any],
    gemini: Optional[Any],
    *,
    openai: Optional[Any] = None,
    anthropic: Optional[Any] = None,
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
            cap = catalog.cloud_capability(mid) + (
                catalog.DEFAULT_BONUS if mid == default else 0
            )
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
    # OpenAI-compatible and Anthropic direct — no multi-model catalog discovery;
    # each registers its configured default model only.
    for client, name, default, cost in (
        (openai, router.PROVIDER_OPENAI, config.OPENAI_MODEL, router.COST_LOW),
        (
            anthropic,
            router.PROVIDER_ANTHROPIC,
            config.ANTHROPIC_MODEL,
            router.COST_HIGH,
        ),
    ):
        if client is None:
            continue
        cap = catalog.cloud_capability(default) + catalog.DEFAULT_BONUS
        providers.append(
            router.Provider(
                name=name,
                privacy=router.PRIVACY_CLOUD,
                cost=cost,
                available=True,
                models=(default,),
                capability=cap,
            )
        )
    return providers


def _client_for(
    provider: str,
    ollama: Any,
    bedrock: Optional[Any],
    gemini: Optional[Any],
    *,
    openai: Optional[Any] = None,
    anthropic: Optional[Any] = None,
) -> Optional[Any]:
    """Map a router provider name back to its live chat client."""
    if provider == router.PROVIDER_BEDROCK:
        return bedrock
    if provider == router.PROVIDER_GEMINI:
        return gemini
    if provider == router.PROVIDER_OPENAI:
        return openai
    if provider == router.PROVIDER_ANTHROPIC:
        return anthropic
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
    there is a real choice — the single-candidate local path never reaches here, paying
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
            logger.warning(
                "Local LLM route picker failed; falling back to deterministic",
                exc_info=exc,
            )
            return None

    return picker


def _provider_name(
    chat_client: Any,
    bedrock: Optional[Any],
    gemini: Optional[Any],
    *,
    openai: Optional[Any] = None,
    anthropic: Optional[Any] = None,
) -> str:
    """The router provider name for the selected *chat_client* (for evidence + UI)."""
    if bedrock is not None and chat_client is bedrock:
        return router.PROVIDER_BEDROCK
    if gemini is not None and chat_client is gemini:
        return router.PROVIDER_GEMINI
    if openai is not None and chat_client is openai:
        return router.PROVIDER_OPENAI
    if anthropic is not None and chat_client is anthropic:
        return router.PROVIDER_ANTHROPIC
    return router.PROVIDER_OLLAMA


def _active_route(
    chat_client: Any,
    bedrock: Optional[Any],
    gemini: Optional[Any],
    model: str,
    *,
    openai: Optional[Any] = None,
    anthropic: Optional[Any] = None,
) -> tuple[str, str]:
    """The ``(provider, model)`` that ACTUALLY served — truthful under failover.

    A :class:`FailoverChatClient` reports the candidate currently serving the turn
    (which may differ from the top pick once it has ridden a failover), so the
    audit + the router's evidence calibration credit the model that did the work.
    """
    if isinstance(chat_client, FailoverChatClient):
        return chat_client.active_provider, chat_client.active_model
    return _provider_name(
        chat_client, bedrock, gemini, openai=openai, anthropic=anthropic
    ), model


def _route_metrics(development: Any, model_id: Optional[str]) -> dict:
    """Measured per-(provider,model,task) success rates for evidence calibration.

    Read only when it can change the route — an ``auto`` turn with cloud opted in
    and calibration on — so a common local-only or explicit-model path never pays for a
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
    openai: Optional[Any] = None,
    anthropic: Optional[Any] = None,
    task: str = "coding",
    metrics: Optional[dict] = None,
    calibration_weight: float = 0.0,
    data_classification: str = "PROJECT_INTERNAL",
) -> tuple[Any, str]:
    """Pick the ``(chat_client, model)`` for the requested UI model id.

    ``auto`` runs the **cross-provider router**: the agent picks the best model for
    *task* across local + (policy-permitted) cloud providers. The privacy boundary
    is deterministic and operator-owned (:func:`_router_policy`). The live config
    currently ships ``reasoning,coding`` cloud-eligible; setting
    ``AIOS_ROUTER_CLOUD_TASKS=""`` keeps ``auto`` local-only. ``ollama.x`` always
    runs locally on ``x``. A
    ``gemini.x`` id routes to Google Gemini; ``openai.x`` to the OpenAI-compatible
    endpoint; ``anthropic.x`` to Anthropic direct; any other explicit id routes to
    Bedrock. Each explicit cloud pick fails clearly when that provider is
    unavailable. No id means the local default.
    """
    if model_id in _AUTO_IDS:
        providers = _build_providers(
            ollama, bedrock, gemini, openai=openai, anthropic=anthropic
        )
        policy = _router_policy()
        # Enforce classification-bound routing: let the PrivacyBroker filter the
        # provider list before candidates are ranked.  Lazy import keeps the core
        # wiring module free of application-layer imports at load time.
        from aios.application.models.privacy_broker import PrivacyBroker
        from aios.domain.privacy import (
            DataClassification,
            ModelCallRequest,
            PrivacyPolicy,
        )

        try:
            dc = DataClassification(data_classification)
        except ValueError:
            dc = DataClassification.PROJECT_INTERNAL
        _broker_request = ModelCallRequest(
            request_id="routing",
            principal_id="system",
            purpose="model_routing",
            prompt="",
            data_classification=dc,
            policy=PrivacyPolicy(
                data_classification=dc,
                local_only=not bool(policy.cloud_tasks),
                allowed_providers=tuple(p.name for p in providers),
            ),
        )
        _decision = PrivacyBroker().evaluate(_broker_request)
        providers = [p for p in providers if p.name in _decision.allowed_providers]
        cands = router.candidates(
            task,
            providers,
            policy=policy,
            require_tools=True,
            metrics=metrics,
            calibration_weight=calibration_weight,
        )
        chosen = router.pick_from(
            cands, picker=_maybe_llm_picker(ollama, providers, cands, task)
        )
        if chosen is not None:
            ordered = [chosen] + [r for r in cands if r is not chosen]
            cascade = []
            for r in ordered:
                client = _client_for(
                    r.provider,
                    ollama,
                    bedrock,
                    gemini,
                    openai=openai,
                    anthropic=anthropic,
                )
                if client is not None:
                    cascade.append((client, r.model, r.provider))
            if len(cascade) == 1:
                return cascade[0][0], cascade[0][1]
            if cascade:
                return (
                    FailoverChatClient(
                        cascade,
                        provider_health=_provider_health_tracker(),
                        privacy_audit_tracker=_privacy_audit_tracker_singleton(),
                    ),
                    cascade[0][1],
                )
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
        if gemini is not None:
            return gemini, model_id[len("gemini.") :]
        raise HTTPException(
            status_code=503,
            detail="Gemini model selected but Google Gemini is not configured",
        )
    if model_id and model_id.startswith("openai."):
        if openai is not None:
            return openai, model_id[len("openai.") :]
        raise HTTPException(
            status_code=503,
            detail="OpenAI model selected but OpenAI-compatible provider is not configured",
        )
    if model_id and model_id.startswith("anthropic."):
        if anthropic is not None:
            return anthropic, model_id[len("anthropic.") :]
        raise HTTPException(
            status_code=503,
            detail="Anthropic model selected but Anthropic direct is not configured",
        )
    if model_id and bedrock is not None:
        return bedrock, model_id
    if model_id:
        raise HTTPException(
            status_code=503,
            detail="cloud model selected but AWS Bedrock is not configured",
        )
    return ollama, config.LLM_MODEL
