"""Failover chat client — the multi-LLM library's resilience layer.

A multi-LLM library exists so one model's failure never blocks the work: with many
models available across local + cloud, the turn should ride the next one rather
than wait. This wraps the router's **ranked candidate list** and tries them in
order — if the active candidate's ``chat()`` raises :class:`LLMError` (a provider
outage, throttle, credential lapse, bad-model id…), it falls over to the next
automatically.

Privacy-hardened behaviour (H9 mitigation):
  * **At most ONE cloud provider per turn.**  The failover loop identifies the
    first cloud provider, pre-filters messages through :class:`PrivacyFilter`,
    and may try that provider's ranked model candidates.  If they fail the turn
    falls back to a *local* (Ollama) candidate — never to a different cloud
    provider when local fallback exists.  This prevents a privacy cascade where
    the same (possibly sensitive) message list is leaked to multiple cloud
    providers in a single turn.
  * The privacy filter is applied **once**, before any cloud transmission, so
    the same redacted copy is used for the cloud attempt and any subsequent local
    fallback.
  * **No-local fallback**: when *every* candidate is a cloud provider and there
    is no local option, the code falls back to trying additional cloud providers
    (better to serve the turn with reduced privacy than to hard-fail entirely).
    A warning is emitted so operators know the deployment lacks a local fallback.

  * **Forward-only + sticky:** once a candidate fails it is not retried again this
    turn, and the one that works stays primary for subsequent tool-loop calls — so
    a persistently-failing provider costs at most one attempt per turn, not per call.
  * **Same contract:** implements ``chat(messages, *, tools, model)`` exactly like
    the underlying clients (the passed ``model`` is ignored — each candidate carries
    its own), so the agent loop is unchanged.
  * **Truthful attribution:** :attr:`active_provider` / :attr:`active_model` always
    name the candidate that actually served the last call, so the audit + the
    router's evidence calibration credit the model that did the work, not the one
    that was merely picked first.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterator, Optional

from aios.application.models.health import ProviderHealthTracker
from aios.core.llm import LLMError
from aios.core.privacy_filter import PrivacyFilter
from aios.core.stream_protocol import StreamFinished

logger = logging.getLogger(__name__)

#: Provider names that are considered *cloud* providers.  Only one is tried per
#: turn; if it fails the failover falls back to a local provider.
_CLOUD_PROVIDERS: frozenset[str] = frozenset(
    {"bedrock", "gemini", "aws", "google", "vertex"}
)

#: Provider names that are considered *local* providers.
_LOCAL_PROVIDERS: frozenset[str] = frozenset({"ollama", "local"})

#: A candidate is ``(chat_client, model_id, provider_name)``, best-first.
Candidate = tuple[Any, str, str]
#: Optional callback ``(failed_provider, failed_model, next_provider, next_model, error)``.
FailoverHook = Callable[[str, str, str, str, Exception], None]


def _is_cloud_provider(name: str) -> bool:
    """Return ``True`` if *name* identifies a cloud provider."""
    lower = name.strip().lower()
    return lower in _CLOUD_PROVIDERS or any(c in lower for c in _CLOUD_PROVIDERS)


def _is_local_provider(name: str) -> bool:
    """Return ``True`` if *name* identifies a local provider."""
    return name.strip().lower() in _LOCAL_PROVIDERS


class FailoverChatClient:
    """Try a ranked list of ``(client, model, provider)`` candidates, in order."""

    def __init__(
        self,
        candidates: list[Candidate],
        *,
        on_failover: Optional[FailoverHook] = None,
        provider_health: Optional[ProviderHealthTracker] = None,
    ) -> None:
        if not candidates:
            raise ValueError("FailoverChatClient requires at least one candidate")
        self._candidates: list[Candidate] = list(candidates)
        self._on_failover = on_failover
        self._idx = 0  # index of the current primary candidate
        #: Privacy filter — applied once before any cloud transmission this turn.
        self._privacy_filter = PrivacyFilter()
        #: Organ 34: records real outcomes so the circuit-breaker tracker
        #: actually observes production traffic. Optional and purely
        #: observational here -- this pass does not yet gate candidate
        #: selection on `is_call_allowed()`, which would change failover
        #: ordering and deserves its own reviewed pass.
        self._provider_health = provider_health

    def _record_success(self, provider: str) -> None:
        if self._provider_health is not None:
            self._provider_health.record_success(provider)

    def _record_failure(self, provider: str) -> None:
        if self._provider_health is not None:
            self._provider_health.record_failure(provider)

    @property
    def active_provider(self) -> str:
        return self._candidates[self._idx][2]

    @property
    def active_model(self) -> str:
        return self._candidates[self._idx][1]

    @property
    def candidates(self) -> list[Candidate]:
        return list(self._candidates)

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        """One chat turn, falling over to the next candidate on :class:`LLMError`.

        Tries from the current primary forward; the first to succeed becomes (and
        stays) primary. Raises :class:`LLMError` only when **every** remaining
        candidate fails — so the turn rides any single model's outage transparently.

        Privacy rule (H9): at most **one** cloud provider is attempted per turn.
        If all ranked models for that cloud provider fail, failover falls back to
        a *local* candidate (Ollama) — never to a different cloud provider when
        local fallback exists.  This prevents the same (potentially sensitive)
        message list from being exposed to multiple cloud providers in one turn.

        The optional ``on_failover`` hook is fired only after a later candidate
        *successfully* serves the turn, and it reports that successful candidate as
        the destination (never a candidate that itself immediately failed).
        """
        errors: list[tuple[str, str, Exception]] = []
        started = self._idx

        # --- Classify candidates. ---
        cloud_indices: list[int] = []
        local_indices: list[int] = []
        for i, (_client, _m, provider) in enumerate(self._candidates):
            if _is_cloud_provider(provider):
                cloud_indices.append(i)
            elif _is_local_provider(provider):
                local_indices.append(i)
            else:
                # Unknown — treat as local (never assume cloud).
                local_indices.append(i)

        has_local_fallback = bool(local_indices)

        # --- Pre-filter messages for privacy once if any cloud attempt is planned. ---
        filtered_messages = messages
        if cloud_indices:
            filtered_messages, audit = self._privacy_filter.filter(messages)
            if any(v for k, v in audit.items() if k.startswith("redacted_") and v):
                logger.info(
                    "Failover privacy filter applied (cloud candidate detected)",
                    extra={
                        "audit": audit,
                        "primary_provider": self._candidates[started][2],
                    },
                )

        attempted: set[int] = set()
        attempted_cloud_providers: set[str] = set()

        # --- 1. Try candidates from *started* forward, respecting H9. ---
        for i in range(started, len(self._candidates)):
            if i in attempted:
                continue

            client, m, provider = self._candidates[i]
            provider_key = provider.strip().lower()

            # H9: multiple ranked models from the same cloud provider are allowed;
            # a different cloud provider is skipped when a local fallback exists.
            if (
                i in cloud_indices
                and attempted_cloud_providers
                and provider_key not in attempted_cloud_providers
            ):
                if has_local_fallback:
                    continue
                # No local fallback — we have to try remaining providers as last resort.
                logger.warning(
                    "H9: no local fallback available; trying additional cloud provider %s",
                    provider,
                )

            attempted.add(i)
            if i in cloud_indices:
                attempted_cloud_providers.add(provider_key)
            use_messages = filtered_messages if i in cloud_indices else messages

            try:
                result = client.chat(use_messages, tools=tools, model=m)
                # Success — stick with this candidate.
                self._idx = i
                self._record_success(provider)
                # Fire failover hook if we changed providers.
                if self._on_failover and i != started:
                    success_provider = self._candidates[i][2]
                    success_model = self._candidates[i][1]
                    for failed_provider, failed_model, exc in errors:
                        try:
                            self._on_failover(
                                failed_provider,
                                failed_model,
                                success_provider,
                                success_model,
                                exc,
                            )
                        except Exception:  # noqa: BLE001 - a hook must never break failover
                            pass
                return result
            except LLMError as exc:
                errors.append((provider, m, exc))
                self._record_failure(provider)
                self._idx = min(i + 1, len(self._candidates) - 1)  # forward-only

        # --- 2. All candidates from started onward failed. ---
        detail = (
            "; ".join(f"{p}:{m} -> {exc}" for p, m, exc in errors) or "no candidates"
        )
        raise LLMError(
            f"all {len(self._candidates)} model candidate(s) failed: {detail}"
        )

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
    ) -> Iterator[str]:
        """Stream a no-tool chat turn with the same failover/privacy contract.

        Candidates that expose ``stream_chat`` produce real provider chunks. A
        candidate without streaming support falls back to ``chat`` and yields the
        final content as one chunk. If a provider fails before yielding the first
        chunk, failover continues to the next candidate. Once any chunk is sent,
        the stream cannot be replayed through a different model without mixing
        answers, so later provider errors surface as ``LLMError``.
        """
        if tools:
            result = self.chat(messages, tools=tools, model=model)
            content = str((result or {}).get("content", ""))
            if content:
                yield content
            return

        errors: list[tuple[str, str, Exception]] = []
        started = self._idx

        cloud_indices: list[int] = []
        local_indices: list[int] = []
        for i, (_client, _m, provider) in enumerate(self._candidates):
            if _is_cloud_provider(provider):
                cloud_indices.append(i)
            elif _is_local_provider(provider):
                local_indices.append(i)
            else:
                local_indices.append(i)

        has_local_fallback = bool(local_indices)
        filtered_messages = messages
        if cloud_indices:
            filtered_messages, audit = self._privacy_filter.filter(messages)
            if any(v for k, v in audit.items() if k.startswith("redacted_") and v):
                logger.info(
                    "Failover privacy filter applied (cloud candidate detected)",
                    extra={
                        "audit": audit,
                        "primary_provider": self._candidates[started][2],
                    },
                )

        attempted: set[int] = set()
        attempted_cloud_providers: set[str] = set()

        for i in range(started, len(self._candidates)):
            if i in attempted:
                continue
            client, m, provider = self._candidates[i]
            provider_key = provider.strip().lower()
            if (
                i in cloud_indices
                and attempted_cloud_providers
                and provider_key not in attempted_cloud_providers
            ):
                if has_local_fallback:
                    continue
                logger.warning(
                    "H9: no local fallback available; trying additional cloud provider %s",
                    provider,
                )

            attempted.add(i)
            if i in cloud_indices:
                attempted_cloud_providers.add(provider_key)
            use_messages = filtered_messages if i in cloud_indices else messages

            try:
                stream_fn = getattr(client, "stream_chat", None)
                if callable(stream_fn):
                    iterator = iter(stream_fn(use_messages, tools=None, model=m))
                    try:
                        first = next(iterator)
                    except StopIteration:
                        first = None
                    self._idx = i
                    self._record_success(provider)
                    if self._on_failover and i != started:
                        success_provider = self._candidates[i][2]
                        success_model = self._candidates[i][1]
                        for failed_provider, failed_model, exc in errors:
                            try:
                                self._on_failover(
                                    failed_provider,
                                    failed_model,
                                    success_provider,
                                    success_model,
                                    exc,
                                )
                            except Exception:  # noqa: BLE001 - a hook must never break failover
                                pass
                    if first:
                        yield str(first)
                    for chunk in iterator:
                        if chunk:
                            yield str(chunk)
                    return

                result = client.chat(use_messages, tools=None, model=m)
                self._idx = i
                self._record_success(provider)
                if self._on_failover and i != started:
                    success_provider = self._candidates[i][2]
                    success_model = self._candidates[i][1]
                    for failed_provider, failed_model, exc in errors:
                        try:
                            self._on_failover(
                                failed_provider,
                                failed_model,
                                success_provider,
                                success_model,
                                exc,
                            )
                        except Exception:  # noqa: BLE001 - a hook must never break failover
                            pass
                content = str((result or {}).get("content", ""))
                if content:
                    yield content
                return
            except LLMError as exc:
                errors.append((provider, m, exc))
                self._record_failure(provider)
                self._idx = min(i + 1, len(self._candidates) - 1)

        detail = (
            "; ".join(f"{p}:{m} -> {exc}" for p, m, exc in errors) or "no candidates"
        )
        raise LLMError(
            f"all {len(self._candidates)} model candidate(s) failed: {detail}"
        )

    def stream_chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
    ) -> Iterator[str | StreamFinished]:
        """Stream text chunks then :class:`StreamFinished` with failover + privacy.

        Unlike :meth:`stream_chat`, this does NOT short-circuit when ``tools``
        is provided — the underlying provider's ``stream_chat_with_tools`` is
        invoked so tool_calls are captured from the stream. The first-chunk
        failover logic still applies: if a provider fails before yielding the
        first chunk, the next candidate is tried.

        If a candidate lacks ``stream_chat_with_tools``, falls back to
        ``chat()`` and yields the content as one chunk plus a StreamFinished.
        """
        errors: list[tuple[str, str, Exception]] = []
        started = self._idx

        cloud_indices: list[int] = []
        local_indices: list[int] = []
        for i, (_client, _m, provider) in enumerate(self._candidates):
            if _is_cloud_provider(provider):
                cloud_indices.append(i)
            else:
                local_indices.append(i)

        has_local_fallback = bool(local_indices)
        filtered_messages = messages
        if cloud_indices:
            filtered_messages, audit = self._privacy_filter.filter(messages)
            if any(v for k, v in audit.items() if k.startswith("redacted_") and v):
                logger.info(
                    "Failover privacy filter applied (stream_chat_with_tools)",
                    extra={
                        "audit": audit,
                        "primary_provider": self._candidates[started][2],
                    },
                )

        attempted: set[int] = set()
        attempted_cloud_providers: set[str] = set()

        for i in range(started, len(self._candidates)):
            if i in attempted:
                continue
            client, m, provider = self._candidates[i]
            provider_key = provider.strip().lower()
            if (
                i in cloud_indices
                and attempted_cloud_providers
                and provider_key not in attempted_cloud_providers
            ):
                if has_local_fallback:
                    continue
                logger.warning(
                    "H9: no local fallback available; trying additional cloud provider %s",
                    provider,
                )

            attempted.add(i)
            if i in cloud_indices:
                attempted_cloud_providers.add(provider_key)
            use_messages = filtered_messages if i in cloud_indices else messages

            try:
                stream_fn = getattr(client, "stream_chat_with_tools", None)
                if callable(stream_fn):
                    iterator = iter(stream_fn(use_messages, tools=tools, model=m))
                    try:
                        first = next(iterator)
                    except StopIteration:
                        first = None
                    self._idx = i
                    self._record_success(provider)
                    if self._on_failover and i != started:
                        success_provider = self._candidates[i][2]
                        success_model = self._candidates[i][1]
                        for failed_provider, failed_model, exc in errors:
                            try:
                                self._on_failover(
                                    failed_provider,
                                    failed_model,
                                    success_provider,
                                    success_model,
                                    exc,
                                )
                            except Exception:  # noqa: BLE001
                                pass
                    if first is not None:
                        yield first
                    for chunk in iterator:
                        if chunk is not None:
                            yield chunk
                    return

                # Fallback: use blocking chat() and synthesize a StreamFinished
                result = client.chat(use_messages, tools=tools, model=m)
                self._idx = i
                self._record_success(provider)
                if self._on_failover and i != started:
                    success_provider = self._candidates[i][2]
                    success_model = self._candidates[i][1]
                    for failed_provider, failed_model, exc in errors:
                        try:
                            self._on_failover(
                                failed_provider,
                                failed_model,
                                success_provider,
                                success_model,
                                exc,
                            )
                        except Exception:  # noqa: BLE001
                            pass
                content = str((result or {}).get("content", ""))
                tool_calls = (result or {}).get("tool_calls") or []
                if content and not tool_calls:
                    yield content
                yield StreamFinished(tool_calls=tool_calls, content=content)
                return
            except LLMError as exc:
                errors.append((provider, m, exc))
                self._record_failure(provider)
                self._idx = min(i + 1, len(self._candidates) - 1)

        detail = (
            "; ".join(f"{p}:{m} -> {exc}" for p, m, exc in errors) or "no candidates"
        )
        raise LLMError(
            f"all {len(self._candidates)} model candidate(s) failed (stream_with_tools): {detail}"
        )

    def list_models(self) -> Any:
        """Delegate discovery to the primary candidate (rarely used here)."""
        return self._candidates[0][0].list_models()
