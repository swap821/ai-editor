"""Routes Council Planner/King LLM reasoning through the Universal
Intelligence Gateway (Slice 30, organ 32) instead of an ungated direct
provider call.

Council's Planner/King LLM slots have existed since the Council runtime
shipped but were never supplied a client in production --
`aios.council.queens.planner.PlannerQueen.__init__` and
`aios.council.king_reasoning.reason_king` both default their client
parameter to `None`, and every real construction site in
`aios/api/routes/council.py` left it unset (confirmed by grep: zero
production hits for `PlannerQueen(llm=` or `king_complete=` outside tests).
This module is the first production wiring for either. It reuses Slice
26's `build_constitution_snapshot` and Slice 30's `route_intelligence_
request` unchanged -- it does not duplicate either.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from aios.logging_config import get_logger

_LOGGER = get_logger(__name__)

from aios import config
from aios.application.intelligence.gateway import route_intelligence_request
from aios.core.llm import LLMClient, OllamaClient
from aios.domain.governance.constitution import build_constitution_snapshot
from aios.infrastructure.identity.sqlite_store import IdentityStore, credential_digest

_DELEGATED_AUTHORITY_SUMMARY = (
    "Council reasoning is strictly advisory: it may only narrow scope or "
    "raise risk, never grant authority, approve itself, or execute a change."
)


class GatewayRoutedCouncilLLMClient:
    """`LLMClient`-shaped adapter: every completion goes through
    `route_intelligence_request()` -- emergency-stop gated, context-compiled,
    output-redacted -- instead of calling a provider directly.

    Council's own prompts (`_planner_prompt`, King's `_build_prompt`) are
    already fully self-contained JSON-instruction strings, not general
    conversation needing operator-preference injection, so `model_call`
    reuses the original prompt/system rather than re-deriving one from the
    compiled context. What this wiring adds is real: emergency-stop gating
    (previously absent from this call path entirely), a genuine audit-able
    `context_digest`, and one canonical entrance instead of a bare provider
    call scattered directly into Council's reasoning code.
    """

    def __init__(
        self,
        *,
        operator_identity_digest: str,
        constitution_digest: str,
        emergency_stop: Optional[Any] = None,
        provider: Optional[LLMClient] = None,
    ) -> None:
        self._operator_identity_digest = operator_identity_digest
        self._constitution_digest = constitution_digest
        self._emergency_stop = emergency_stop
        self._provider: LLMClient = provider or OllamaClient()
        #: Organ 31: the compiled context_digest from the most recent
        #: complete() call. route_intelligence_request() genuinely computes
        #: one on every call, but this adapter's own .complete() -> str
        #: return shape (required by the LLMClient protocol PlannerQueen/
        #: reason_king expect) has no room to also return it -- exposed here
        #: as a side-channel attribute, and logged unconditionally below, so
        #: it is genuinely observable rather than silently computed and
        #: discarded (a real gap the docstring above previously claimed was
        #: already closed).
        self.last_context_digest: str | None = None

    def complete(
        self, prompt: str, *, system: str | None = None, json_mode: bool = False
    ) -> str:
        request_id = f"council-{uuid.uuid4().hex}"
        result = route_intelligence_request(
            request_id=request_id,
            operator_identity_digest=self._operator_identity_digest,
            constitution_digest=self._constitution_digest,
            goal=prompt,
            desired_outcome=(
                "a single valid JSON object per the Council reasoning schema"
            ),
            target="local",
            delegated_authority_summary=_DELEGATED_AUTHORITY_SUMMARY,
            model_call=lambda _context: self._provider.complete(
                prompt, system=system, json_mode=json_mode
            ),
            emergency_stop=self._emergency_stop,
        )
        self.last_context_digest = result.context.context_digest
        _LOGGER.info(
            "council_gateway_context_compiled",
            request_id=request_id,
            context_digest=result.context.context_digest,
            secrets_redacted=result.secrets_redacted,
        )
        return result.output


def build_council_llm_client(
    *, emergency_stop: Optional[Any] = None
) -> GatewayRoutedCouncilLLMClient | None:
    """Return a gateway-routed Council LLM client, or `None` when reasoning
    should stay off: `config.COUNCIL_REASONING` is disabled, or no sovereign
    operator is enrolled yet to attribute constitutional authority to.

    A missing operator is not an error -- a fresh install with no enrolled
    operator has nothing to compile a constitution snapshot for, and Council
    reasoning staying fully deterministic in that state is the correct,
    fail-closed behaviour (matching `PlannerQueen`'s own `llm is None` path).
    """
    if not config.COUNCIL_REASONING:
        return None
    identity_store = IdentityStore(config.IDENTITY_DB_PATH)
    operator = identity_store.operator()
    if operator is None:
        return None
    operator_id = str(operator["operator_id"])
    snapshot = build_constitution_snapshot(ratified_by_operator_id=operator_id)
    return GatewayRoutedCouncilLLMClient(
        operator_identity_digest=credential_digest(operator_id),
        constitution_digest=snapshot.snapshot_digest,
        emergency_stop=emergency_stop,
    )


class _ChatBackedCompleter:
    """`LLMClient`-shaped adapter over a `chat(messages) -> message-dict`
    client (every cloud provider) -- `GatewayRoutedCouncilLLMClient`'s own
    `provider` slot expects `.complete()`, and only `OllamaClient` has one
    natively. Wraps a single prompt as a one-message user turn and returns
    the assistant's real (possibly empty) text content, never inventing one
    when the reply carries only tool calls."""

    def __init__(self, chat_client: Any) -> None:
        self._chat_client = chat_client

    def complete(
        self, prompt: str, *, system: Optional[str] = None, json_mode: bool = False
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        result = self._chat_client.chat(messages)
        return str(result.get("content") or "")


def build_dissent_llm_client(
    *, emergency_stop: Optional[Any] = None
) -> tuple[GatewayRoutedCouncilLLMClient, str, str] | None:
    """Organ 39: a genuinely independent second reviewer for multi-model
    deliberation -- a real CONFIGURED CLOUD provider, never Ollama (which
    is always the King's own provider; using it here would violate
    `verify_independence()`'s whole point). Returns `None` when reasoning
    is off, no operator is enrolled (same gating as `build_council_llm_
    client`), or no cloud provider is actually configured on this machine.

    Lazily imports `aios.api.deps` -- the same pattern `aios/core/router_
    wiring.py`'s `_provider_health_tracker()` already established, to keep
    this module free of API-layer imports at load time.
    """
    if not config.COUNCIL_REASONING:
        return None
    identity_store = IdentityStore(config.IDENTITY_DB_PATH)
    operator = identity_store.operator()
    if operator is None:
        return None

    from aios.api import deps

    for provider_name, getter in (
        ("gemini", deps.get_gemini_client),
        ("bedrock", deps.get_bedrock_client),
        ("openai", deps.get_openai_client),
        ("anthropic", deps.get_anthropic_client),
    ):
        try:
            client = getter()
        except Exception:  # noqa: BLE001 - a flaky provider lookup must not break wiring
            continue
        if client is None:
            continue
        model_id = str(getattr(client, "model", "unknown"))
        operator_id = str(operator["operator_id"])
        snapshot = build_constitution_snapshot(ratified_by_operator_id=operator_id)
        dissent_client = GatewayRoutedCouncilLLMClient(
            operator_identity_digest=credential_digest(operator_id),
            constitution_digest=snapshot.snapshot_digest,
            emergency_stop=emergency_stop,
            provider=_ChatBackedCompleter(client),
        )
        return dissent_client, provider_name, model_id
    return None


__all__ = [
    "GatewayRoutedCouncilLLMClient",
    "build_council_llm_client",
    "build_dissent_llm_client",
]
