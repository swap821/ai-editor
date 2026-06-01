"""FastAPI orchestration layer for the AI OS.

Exposes the subsystems built so far behind versioned HTTP endpoints. This is
Phase 3a — the four endpoints backed by completed subsystems are live:

    POST /api/v1/memory/search     hybrid BM25+FAISS+decay retrieval
    POST /api/v1/security/classify deterministic, fail-closed zone classifier
    GET  /api/v1/audit/verify      tamper-evident hash-chain verification
    POST /api/v1/reflect           structured failure post-mortem -> Mistake DB

The remaining blueprint endpoints (``/plan``, ``/execute``, ``/approval/req``,
``/rollback``) are reserved for Phase 3b, once the planner, sandboxed executor,
and rollback engine land.

The LLM client is supplied via dependency injection (:func:`get_llm_client`) so
tests can override it with a fake and avoid any network/model dependency.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

import aios
from aios.agents.reflection_agent import ReflectionAgent, ReflectionError
from aios.core.llm import LLMClient, OllamaClient
from aios.memory.db import init_memory_db
from aios.memory.retrieval import hybrid_search
from aios.security.audit_logger import init_audit_db, verify_chain
from aios.security.gateway import classify


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure both databases exist before the app serves traffic."""
    init_memory_db()
    init_audit_db()
    yield


app = FastAPI(
    title="AI OS - Jarvis",
    version=aios.__version__,
    summary="Local-first, memory-driven, security-gated, human-supervised AI OS.",
    lifespan=lifespan,
)


def get_llm_client() -> LLMClient:
    """Provide the default local LLM client. Overridden in tests."""
    return OllamaClient()


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class MemorySearchRequest(BaseModel):
    """Body for ``/memory/search``."""

    query: str = Field(..., description="Natural-language search query.")
    top_k: int = Field(3, ge=1, le=50, description="Number of results to return.")


class ClassifyRequest(BaseModel):
    """Body for ``/security/classify``."""

    command: str = Field(..., description="Action payload to classify.")


class ReflectRequest(BaseModel):
    """Body for ``/reflect``."""

    command: str = Field(..., description="The action/command that failed.")
    error_output: str = Field(..., description="Captured error text.")
    task_id: Optional[str] = Field(None, description="Stable id for recurrence detection.")


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok", "version": aios.__version__}


@app.post("/api/v1/memory/search")
def memory_search(req: MemorySearchRequest) -> dict:
    """Hybrid BM25 + FAISS + temporal-decay retrieval over semantic memory."""
    results = hybrid_search(req.query, top_k=req.top_k)
    return {"query": req.query, "results": [asdict(r) for r in results]}


@app.post("/api/v1/security/classify")
def security_classify(req: ClassifyRequest) -> dict:
    """Deterministic, fail-closed security-zone classification."""
    result = classify(req.command)
    return {
        "zone": result.zone.value,
        "confidence": result.confidence,
        "reason": result.reason,
    }


@app.get("/api/v1/audit/verify")
def audit_verify(from_entry: int = 1, to_entry: Optional[int] = None) -> dict:
    """Verify the tamper-evident audit hash chain over an optional id range."""
    status = verify_chain(from_id=from_entry, to_id=to_entry)
    return asdict(status)


@app.post("/api/v1/reflect")
def reflect(req: ReflectRequest, llm: LLMClient = Depends(get_llm_client)) -> dict:
    """Run the reflection agent on a failure and store a structured lesson."""
    agent = ReflectionAgent(llm)
    try:
        reflection = agent.reflect(req.command, req.error_output, task_id=req.task_id)
    except ReflectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return asdict(reflection)
