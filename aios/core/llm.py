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
from typing import Iterator, Optional, Protocol, runtime_checkable, Any

from aios import config


class LLMError(RuntimeError):
    """Raised when a local LLM request fails."""


@runtime_checkable
class LLMClient(Protocol):
    """Anything that can turn a prompt into a completion string."""

    def complete(self, prompt: str, *, system: Optional[str] = None, json_mode: bool = False) -> str:
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

    def complete(
        self, prompt: str, *, system: Optional[str] = None, json_mode: bool = False
    ) -> str:
        """Generate a single non-streaming completion from the local model.

        When *json_mode* is set, Ollama's ``format: "json"`` grammar constraint is
        requested so small local models (e.g. ``llama3.2:3b``) emit a single valid
        JSON object instead of trailing off into prose — the difference between an
        unparseable reflection and a reliable one.

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
        if json_mode:
            payload["format"] = "json"

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

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        """Single non-streaming chat turn via Ollama ``/api/chat``.

        Used by the agentic tool loop: when *tools* are supplied and the model
        supports function calling, the returned message may carry a
        ``tool_calls`` list instead of (or alongside) ``content``.

        Args:
            messages: Ollama chat messages (``role`` + ``content`` [+ ``tool_calls``]).
            tools: Optional OpenAI-style function tool specs.
            model: Per-call model override.

        Returns:
            The assistant ``message`` dict (``role``/``content``/``tool_calls``).

        Raises:
            LLMError: On any transport or decoding failure.
        """
        payload: dict[str, object] = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
        }
        if tools:
            payload["tools"] = tools

        request = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace").strip()
            except Exception:  # noqa: BLE001 - best-effort detail extraction
                detail = ""
            raise LLMError(
                f"Ollama returned HTTP {exc.code} for model "
                f"'{model or self.model}': {detail or exc.reason}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LLMError(f"Ollama chat to {self.host} failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LLMError(f"Ollama returned a non-JSON response: {exc}") from exc

        message = body.get("message")
        if not isinstance(message, dict):
            return {"role": "assistant", "content": ""}
        return message

    def stream_complete(
        self, prompt: str, *, system: Optional[str] = None, model: Optional[str] = None
    ) -> Iterator[str]:
        """Yield completion text chunks as the local model produces them.

        Talks to Ollama's streaming ``/api/generate`` (newline-delimited JSON),
        yielding each ``response`` fragment so callers can forward tokens to a
        client in real time. *model* overrides the instance default for a single
        call (used when the UI selects a specific local model).

        Raises:
            LLMError: On any transport or decoding failure.
        """
        payload: dict[str, object] = {
            "model": model or self.model,
            "prompt": prompt,
            "stream": True,
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
                for raw_line in response:
                    line = raw_line.decode("utf-8", "replace").strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    piece = chunk.get("response")
                    if piece:
                        yield str(piece)
                    if chunk.get("done"):
                        break
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace").strip()
            except Exception:  # noqa: BLE001 - best-effort detail extraction
                detail = ""
            raise LLMError(
                f"Ollama returned HTTP {exc.code} for model "
                f"'{model or self.model}': {detail or exc.reason}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LLMError(f"Ollama stream to {self.host} failed: {exc}") from exc

    def list_models(self) -> dict[str, Any]:
        """Return installed local models as ``{"available": bool, "models": [str]}``.

        ``available`` reports whether the Ollama server answered at all, so the
        UI can distinguish "engine down" from "engine up but nothing pulled".
        Never raises — failures collapse to ``{"available": False, "models": []}``.
        """
        try:
            request = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(request, timeout=4) as response:
                body = json.loads(response.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - discovery must never raise
            return {"available": False, "models": []}
        names = [str(m.get("name", "")) for m in body.get("models", []) if m.get("name")]
        return {"available": True, "models": names}

    def list_detailed_models(self) -> list[dict[str, Any]]:
        """Return installed local models with all available Ollama metadata."""
        try:
            request = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(request, timeout=4) as response:
                body = json.loads(response.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return []
        return [m for m in body.get("models", []) if isinstance(m, dict) and "name" in m]

    def is_available(self) -> bool:
        """Return True if the Ollama server answers a tags probe within 4s."""
        try:
            request = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(request, timeout=4) as response:
                return response.status == 200
        except Exception:  # noqa: BLE001 - availability check must never raise
            return False
