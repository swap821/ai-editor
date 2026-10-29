"""CRAG's two model calls, built once for every turn route.

Corrective RAG can ask a model twice while recalling memory:

* a local **judge** scores how relevant each recalled passage is
  (``AIOS_CRAG_LLM_JUDGE``);
* a cloud **source** answers when local recall is unsure
  (``AIOS_CRAG_EXTERNAL`` + ``AIOS_CRAG_CLOUD``).

Both are model calls, so both pass Organ 32:

* an authenticated principal bound to a constitution goes through the governed
  advisory entrance, with its context recorded;
* anyone else goes through the local-only compatibility entrance, and gets no
  cloud source, because no entrance carries an unbound call to the cloud.

Until 2026-10-29 only ``/api/generate`` built these. ``/api/v1/chat`` recalled
with neither, and recall then called the model directly (docs/ONE_GATEWAY.md).
Recall no longer has a direct path: without a judge built here it scores
lexically, and without a source built here nothing leaves.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from aios import config
from aios.application.intelligence.gateway import (
    AdvisoryChatCompletionAdapter,
    CompatibilityAdvisoryCompletionClient,
    GovernedAdvisoryCompletionClient,
)
from aios.infrastructure.identity.sqlite_store import credential_digest

CragJudge = Callable[[str, str], float]
CragSource = Callable[[str], list[str]]


def _no_judge(query: str, passage: str) -> float:
    raise RuntimeError("CRAG judge has no local chat provider at the governed boundary")


def _no_source(query: str) -> list[str]:
    return []


def crag_model_calls(
    *,
    turn_id: str,
    principal: Any | None,
    local_provider: Any | None,
    cloud_provider: Any | None,
    context_store: Any | None,
    emergency_stop: Any | None,
) -> tuple[Optional[CragJudge], Optional[CragSource]]:
    """The turn's ``(judge, cloud_source)``, each gated, or ``None`` when its
    switch is off."""
    from aios.api.turn_pipeline import _crag_cloud_source, _crag_llm_judge

    constitution = str(getattr(principal, "constitution_digest", "") or "")
    bound = principal is not None and bool(constitution)

    def governed(provider: Any, purpose: str, target: str, outcome: str) -> Any:
        return GovernedAdvisoryCompletionClient(
            provider,
            request_id=f"{turn_id}:{purpose}",
            operator_identity_digest=credential_digest(principal.principal_id),
            constitution_digest=constitution,
            target=target,  # type: ignore[arg-type]
            desired_outcome=outcome,
            context_store=context_store,
            emergency_stop=emergency_stop,
        )

    judge: Optional[CragJudge] = None
    if config.CRAG_LLM_JUDGE:
        judge = _no_judge
        if callable(getattr(local_provider, "chat", None)):
            adapter = AdvisoryChatCompletionAdapter(
                local_provider, model=config.LLM_MODEL
            )
            judgment = (
                governed(
                    adapter,
                    "crag-judge",
                    "local",
                    "bounded advisory CRAG relevance judgment",
                )
                if bound
                else CompatibilityAdvisoryCompletionClient(
                    adapter,
                    request_id=f"{turn_id}:crag-judge",
                    emergency_stop=emergency_stop,
                )
            )
            judge = lambda query, passage: _crag_llm_judge(  # noqa: E731
                query, passage, completion=judgment
            )

    source: Optional[CragSource] = None
    if config.CRAG_CLOUD:
        source = _no_source
        if bound and callable(getattr(cloud_provider, "chat", None)):
            answer = governed(
                AdvisoryChatCompletionAdapter(cloud_provider),
                "crag-cloud",
                "cloud",
                "bounded advisory CRAG external source",
            )
            source = lambda query: _crag_cloud_source(  # noqa: E731
                query, completion=answer
            )

    return judge, source


__all__ = ["CragJudge", "CragSource", "crag_model_calls"]
