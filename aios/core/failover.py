"""Failover chat client — the multi-LLM library's resilience layer.

A multi-LLM library exists so one model's failure never blocks the work: with many
models available across local + cloud, the turn should ride the next one rather
than wait. This wraps the router's **ranked candidate list** and tries them in
order — if the active candidate's ``chat()`` raises :class:`LLMError` (a provider
outage, throttle, credential lapse, bad-model id…), it falls over to the next
automatically.

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

from typing import Any, Callable, Optional

from aios.core.llm import LLMError

#: A candidate is ``(chat_client, model_id, provider_name)``, best-first.
Candidate = tuple[Any, str, str]
#: Optional callback ``(failed_provider, failed_model, next_provider, next_model, error)``.
FailoverHook = Callable[[str, str, str, str, Exception], None]


class FailoverChatClient:
    """Try a ranked list of ``(client, model, provider)`` candidates, in order."""

    def __init__(self, candidates: list[Candidate], *, on_failover: Optional[FailoverHook] = None) -> None:
        if not candidates:
            raise ValueError("FailoverChatClient requires at least one candidate")
        self._candidates: list[Candidate] = list(candidates)
        self._on_failover = on_failover
        self._idx = 0  # index of the current primary candidate

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

        The optional ``on_failover`` hook is fired only after a later candidate
        *successfully* serves the turn, and it reports that successful candidate as
        the destination (never a candidate that itself immediately failed).
        """
        errors: list[tuple[str, str, Exception]] = []
        started = self._idx
        for i in range(started, len(self._candidates)):
            client, m, provider = self._candidates[i]
            try:
                result = client.chat(messages, tools=tools, model=m)
                self._idx = i  # stick with the one that worked
                if self._on_failover and i > started:
                    # Report every failed hop against the candidate that finally won.
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
            except LLMError as exc:  # provider outage/throttle/bad-id -> next model
                errors.append((provider, m, exc))
                self._idx = min(i + 1, len(self._candidates) - 1)  # forward-only
        detail = "; ".join(f"{p}:{m} -> {exc}" for p, m, exc in errors) or "no candidates"
        raise LLMError(f"all {len(self._candidates)} model candidate(s) failed: {detail}")

    def list_models(self) -> Any:
        """Delegate discovery to the primary candidate (rarely used here)."""
        return self._candidates[0][0].list_models()
