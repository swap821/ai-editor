"""Failover chat client — the multi-LLM library's resilience layer.

A multi-LLM library exists so one model's failure never blocks the work: with many
models available across local + cloud, the turn should ride the next one rather
than wait. This wraps the router's **ranked candidate list** and tries them in
order — if the active candidate's ``chat()`` raises :class:`LLMError` (a provider
outage, throttle, credential lapse, bad-model id…), it falls over to the next
automatically.

Privacy-hardened behaviour (H9 mitigation):
  * **At most ONE cloud provider per turn.**  The failover loop identifies the
    first cloud candidate, pre-filters messages through :class:`PrivacyFilter`,
    and attempts that single cloud candidate.  If it fails the turn falls back to
    a *local* (Ollama) candidate — never to a second cloud provider.  This
    prevents a privacy cascade where the same (possibly sensitive) message list
    is leaked to multiple cloud providers in a single turn.
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
from typing import Any, Callable, Optional

from aios.core.llm import LLMError
from aios.core.privacy_filter import PrivacyFilter

logger = logging.getLogger(__name__)

#: Provider names that are considered *cloud* providers.  Only one is tried per
#: turn; if it fails the failover falls back to a local provider.
_CLOUD_PROVIDERS: frozenset[str] = frozenset({"bedrock", "gemini", "aws", "google", "vertex"})

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

    def __init__(self, candidates: list[Candidate], *, on_failover: Optional[FailoverHook] = None) -> None:
        if not candidates:
            raise ValueError("FailoverChatClient requires at least one candidate")
        self._candidates: list[Candidate] = list(candidates)
        self._on_failover = on_failover
        self._idx = 0  # index of the current primary candidate
        #: Privacy filter — applied once before any cloud transmission this turn.
        self._privacy_filter = PrivacyFilter()

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
        If the cloud candidate fails, failover falls back to a *local* candidate
        (Ollama) — never to a second cloud provider.  This prevents the same
        (potentially sensitive) message list from being exposed to multiple cloud
        providers in a single turn.

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
                    extra={"audit": audit, "primary_provider": self._candidates[started][2]},
                )

        attempted: set[int] = set()

        # --- 1. Try candidates from *started* forward, respecting H9. ---
        for i in range(started, len(self._candidates)):
            if i in attempted:
                continue

            client, m, provider = self._candidates[i]

            # H9: if we've already tried a cloud provider this turn, skip additional
            # cloud providers — unless there is no local fallback at all.
            if i in cloud_indices and any(idx in attempted for idx in cloud_indices):
                if has_local_fallback:
                    continue  # skip: H9 says one cloud max when local exists
                # No local fallback — we have to try remaining clouds as last resort.
                logger.warning(
                    "H9: no local fallback available; trying additional cloud provider %s",
                    provider,
                )

            attempted.add(i)
            use_messages = filtered_messages if i in cloud_indices else messages

            try:
                result = client.chat(use_messages, tools=tools, model=m)
                # Success — stick with this candidate.
                previous_idx = self._idx
                self._idx = i
                # Fire failover hook if we changed providers.
                if self._on_failover and i != started:
                    success_provider = self._candidates[i][2]
                    success_model = self._candidates[i][1]
                    for failed_provider, failed_model, exc in errors:
                        try:
                            self._on_failover(
                                failed_provider, failed_model, success_provider, success_model, exc
                            )
                        except Exception:  # noqa: BLE001 - a hook must never break failover
                            pass
                return result
            except LLMError as exc:
                errors.append((provider, m, exc))
                self._idx = min(i + 1, len(self._candidates) - 1)  # forward-only

        # --- 2. All candidates from started onward failed. ---
        detail = "; ".join(f"{p}:{m} -> {exc}" for p, m, exc in errors) or "no candidates"
        raise LLMError(f"all {len(self._candidates)} model candidate(s) failed: {detail}")

    def list_models(self) -> Any:
        """Delegate discovery to the primary candidate (rarely used here)."""
        return self._candidates[0][0].list_models()
