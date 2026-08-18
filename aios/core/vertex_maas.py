"""Vertex AI Model-as-a-Service provider (DeepSeek, gpt-oss, and friends).

Vertex hosts far more than Gemini. Verified by INVOKING each id on 2026-08-18,
because a publisher listing shows the catalogue rather than what a project may
call -- reading the listing instead of probing it cost a whole golden cohort
earlier the same day:

    deepseek-ai/deepseek-r1-0528-maas   us-central1   200 OK  (tool calls work)
    openai/gpt-oss-120b-maas            us-central1   429     throttled, reachable
    meta/llama-4-maverick-...-maas      every region  404     listed, not callable
    nvidia/nemotron-v3                  every region  404     listed, not callable
    anthropic/claude-opus-4-5           global        429     zero quota allocated

So this exists because DeepSeek R1 answers today and supports the tool-calling
contract the agent loop needs. Anthropic's models resolve on Vertex but the
project has no quota, and a quota request was refused, so that route is closed.

Why not just point ``OpenAICompatClient`` at the URL: Vertex authenticates with a
short-lived ADC bearer token, not a static key. ``OpenAICompatClient`` holds
``api_key`` for the life of the process, so a run longer than the token lifetime
would start failing mid-way -- exactly the kind of "works in the smoke test, dies
in the 30-minute measurement" defect this repo keeps paying for. ``_headers`` is
overridden to mint a fresh token per request instead.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from aios import config
from aios.core.llm import LLMError
from aios.core.openai_compat import OpenAICompatClient

#: DeepSeek R1 emits its chain of thought inside <think>...</think> in the
#: assistant content. That text is reasoning, not an answer: it is not a tool
#: call, it should not reach the operator's narrative pane, and it should not be
#: replayed to the model as if it were a prior statement. Stripped here rather
#: than in the shared parser because it is one provider's quirk.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
#: An unterminated block -- the model was still reasoning when the budget ran out.
_THINK_OPEN = re.compile(r"<think>.*\Z", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Remove <think> blocks, closed or truncated, from assistant content."""
    if not text or "<think" not in text.lower():
        return text
    cleaned = _THINK_BLOCK.sub("", text)
    cleaned = _THINK_OPEN.sub("", cleaned)
    return cleaned.strip()


def maas_base_url(project: str, location: str) -> str:
    """The OpenAI-compatible endpoint for Vertex MaaS models.

    ``global`` has no region prefix on the host; every other location does. The
    same asymmetry bit the Gemini path (see aios/core/gemini.py CURATED_MODELS),
    so it is written once here rather than assembled at each call site.
    """
    host = (
        "aiplatform.googleapis.com"
        if location == "global"
        else f"{location}-aiplatform.googleapis.com"
    )
    return (
        f"https://{host}/v1beta1/projects/{project}"
        f"/locations/{location}/endpoints/openapi"
    )


class VertexMaaSClient(OpenAICompatClient):
    """:class:`~aios.agents.tool_agent.ChatClient` backed by a Vertex MaaS model."""

    def __init__(
        self,
        *,
        model: str = config.VERTEX_MAAS_MODEL,
        project: str = config.VERTEX_MAAS_PROJECT,
        location: str = config.VERTEX_MAAS_LOCATION,
        max_tokens: int = config.VERTEX_MAAS_MAX_TOKENS,
        credentials: Optional[Any] = None,
        request_factory: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        if not project:
            raise LLMError(
                "Vertex MaaS needs a GCP project: set AIOS_VERTEX_MAAS_PROJECT "
                "(or AIOS_GEMINI_PROJECT, which it defaults to)."
            )
        self.project = project
        self.location = location
        self._credentials = credentials
        self._request_factory = request_factory
        super().__init__(
            api_key="",  # never used; _headers mints a fresh token instead
            base_url=maas_base_url(project, location),
            model=model,
            max_tokens=max_tokens,
            **kwargs,
        )

    def _auth_request(self) -> Any:
        """The transport handed to ``credentials.refresh()``.

        Injectable for the same reason ``credentials`` is: google-auth lives in
        requirements-OPTIONAL.txt, so a caller that supplies its own credentials
        must not be forced to have it installed.
        """
        if self._request_factory is not None:
            return self._request_factory()
        import google.auth.transport.requests

        return google.auth.transport.requests.Request()

    def _fresh_token(self) -> str:
        """Mint/refresh an ADC access token. Never cached beyond its own refresh.

        google is imported WHERE IT IS NEEDED, not at the top of this block.
        Importing it eagerly defeated the `credentials` parameter entirely: the
        one caller who had already done the auth work still crashed with
        ModuleNotFoundError before reaching the branch that would have used it.
        """
        try:
            creds = self._credentials
            if creds is None:
                import google.auth

                creds, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                self._credentials = creds
            if not getattr(creds, "valid", False):
                creds.refresh(self._auth_request())
            token = getattr(creds, "token", "")
            if not token:
                raise LLMError("Vertex ADC returned no access token.")
            return str(token)
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 - surfaced as a provider error
            raise LLMError(
                "Vertex MaaS could not obtain Application Default Credentials: "
                f"{exc}. Run `gcloud auth application-default login`."
            ) from exc

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._fresh_token()}",
            # Required for ADC: without it Vertex answers 403 "requires a quota
            # project", which reads like a permissions problem and is not one.
            "x-goog-user-project": self.project,
        }

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        result = super().chat(messages, tools=tools, model=model)
        result["content"] = strip_reasoning(str(result.get("content") or ""))
        return result

    def complete(self, prompt: str, *, system: Optional[str] = None) -> str:
        return strip_reasoning(super().complete(prompt, system=system))
