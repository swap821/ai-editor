"""Model-discovery routes for the chat model picker (local + cloud + auto).

Extracted from ``aios/api/main.py`` (monolith split, 2026-07-06) into an
APIRouter module. Dependency providers come from ``aios.api.deps`` — the SAME
function objects ``main`` re-exports, so ``app.dependency_overrides`` keyed on
either import path keep working.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends

from aios.api.deps import get_bedrock_client, get_gemini_client, get_ollama_client
from aios.core.bedrock import BedrockClient
from aios.core.gemini import GeminiClient
from aios.core.llm import OllamaClient
from aios.core.model_selector import (
    TASKS,
    describe_choice,
    select_model,
    supports_tool_protocol,
)

router = APIRouter()


@router.get("/api/v1/models/local")
def models_local(client: OllamaClient = Depends(get_ollama_client)) -> dict[str, Any]:
    """List installed models policy-compatible with this conversational UI."""
    info = client.list_models()
    models = info.get("models") or []
    chat_models = [
        model
        for model in models
        if isinstance(model, str) and supports_tool_protocol(model)
    ]
    return {**info, "models": chat_models}


@router.get("/api/v1/models/bedrock")
def models_bedrock(
    bedrock: Optional[BedrockClient] = Depends(get_bedrock_client),
) -> dict[str, Any]:
    """List invocable AWS Bedrock text models for the picker.

    ``{"available": bool, "models": [{"id","name"}]}`` — empty when Bedrock isn't
    configured or the credentials lack control-plane (discovery) access, in which
    case the UI falls back to a curated cloud list.
    """
    if bedrock is None:
        return {"configured": False, "available": False, "models": []}
    models = bedrock.list_models()
    return {"configured": True, "available": bool(models), "models": models}


@router.get("/api/v1/models/gemini")
def models_gemini(
    gemini: Optional[GeminiClient] = Depends(get_gemini_client),
) -> dict[str, Any]:
    """List invocable Google Gemini models for the picker.

    ``{"configured": bool, "available": bool, "models": [{"id","name"}]}`` — empty
    when Gemini isn't configured (no GCP project). When configured, ``list_models``
    already falls back to the curated Gemini set if live Vertex discovery is
    unavailable, so the picker always has the well-known models to offer.
    """
    if gemini is None:
        return {"configured": False, "available": False, "models": []}
    models = gemini.list_models()
    return {"configured": True, "available": bool(models), "models": models}


@router.get("/api/v1/models/auto")
def models_auto(
    task: str = "coding",
    client: OllamaClient = Depends(get_ollama_client),
) -> dict[str, Any]:
    """What the agent would auto-select, per task (drives the 'Auto' picker entry).

    Choosing the best local model is the agent's job, not the user's. Returns the
    pick for *task* plus a ``by_task`` map (coding/reasoning/general/fast) over the
    LIVE installed set, so the UI can show "Auto · <model>" and surface how the
    agent routes by purpose. Selection applies the live loop's tool-capability
    requirement, so discovery never advertises a different Auto route than runtime.
    """
    models = client.list_models().get("models") or []
    by_task = {t: select_model(models, task=t, require_tools=True) for t in TASKS}
    chosen = select_model(models, task=task, require_tools=True)
    if not chosen:
        return {"available": False, "model": None, "task": task,
                "reason": "no local chat model installed", "by_task": by_task}
    return {"available": True, "model": chosen, "task": task,
            "reason": describe_choice(chosen), "by_task": by_task}
