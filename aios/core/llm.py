"""Local LLM client abstraction (Ollama-backed, standard-library only).

Defines the minimal :class:`LLMClient` protocol the reflection agent and planner
depend on, plus :class:`OllamaClient`, which talks to a local Ollama server's
HTTP API using only ``urllib`` — no extra dependencies. Because the agents
depend on the *protocol*, tests inject a fake client and need neither a network
connection nor a model.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional, Protocol, runtime_checkable

from aios import config


class LLMError(RuntimeError):
    """Raised when a local LLM request fails."""


@runtime_checkable
class LLMClient(Protocol):
    """Anything that can turn a prompt into a completion string."""

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        """Return the model's text completion for *prompt* (optional *system*)."""
        ...


class OllamaClient:
    """:class:`LLMClient` backed by a local Ollama server via its HTTP API."""

    def __init__(
        self,
        model: str = config.LLM_MODEL,
        *,
        host: str = config.OLLAMA_HOST,
        timeout_s: int = config.LLM_REQUEST_TIMEOUT_S,
        temperature: float = config.LLM_TEMPERATURE,
        num_ctx: int = config.LLM_NUM_CTX,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout_s = timeout_s
        self.temperature = temperature
        self.num_ctx = num_ctx

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        """Generate a single non-streaming completion from the local model.

        Raises:
            LLMError: On any transport or decoding failure.
        """
        payload: dict[str, object] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
        }
        if system:
            payload["system"] = system

        request = urllib.request.Request(
            f"{self.host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Surface Ollama's own error body (e.g. out-of-memory, unknown model).
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace").strip()
            except Exception:  # noqa: BLE001 - best-effort detail extraction
                detail = ""
            raise LLMError(
                f"Ollama returned HTTP {exc.code} for model '{self.model}': "
                f"{detail or exc.reason}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LLMError(f"Ollama request to {self.host} failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LLMError(f"Ollama returned a non-JSON response: {exc}") from exc

        return str(body.get("response", ""))

    def is_available(self) -> bool:
        """Return True if the Ollama server answers a tags probe within 4s."""
        try:
            request = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(request, timeout=4) as response:
                return response.status == 200
        except Exception:  # noqa: BLE001 - availability check must never raise
            return False
