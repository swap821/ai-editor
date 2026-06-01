"""FastAPI orchestration layer for the AI OS.

Exposes the subsystems behind versioned HTTP endpoints. Phase 3a + 3b are live:

    POST /api/v1/memory/search     hybrid BM25+FAISS+decay retrieval
    POST /api/v1/security/classify deterministic, fail-closed zone classifier
    GET  /api/v1/audit/verify      tamper-evident hash-chain verification
    POST /api/v1/reflect           structured failure post-mortem -> Mistake DB
    POST /api/v1/plan              chain-of-thought planner + confidence gate
    POST /api/v1/execute           gateway-guarded, scope-locked execution
    POST /api/v1/approval/req      human approval of an escalated action
    POST /api/v1/rollback          restore the sandbox to a prior snapshot

Collaborators (LLM client, executor, rollback engine) are supplied via
dependency injection so tests can override them with fakes/sandboxes and avoid
any network, model, or host side effects.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

import aios
from aios.agents.reflection_agent import ReflectionAgent, ReflectionError
from aios.agents.rollback_engine import RollbackEngine, RollbackError
from aios.core.executor import Executor
from aios.core.llm import LLMClient, OllamaClient
from aios.core.planner import Planner, PlannerError
from aios.memory.db import init_memory_db
from aios.memory.retrieval import hybrid_search
from aios.security.audit_logger import init_audit_db, log_action, verify_chain
from aios.security.gateway import Zone, classify


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


def get_executor() -> Executor:
    """Provide the default sandboxed executor. Overridden in tests."""
    return Executor()


def get_rollback_engine() -> RollbackEngine:
    """Provide the default sandbox rollback engine. Overridden in tests."""
    return RollbackEngine()


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


class PlanRequest(BaseModel):
    """Body for ``/plan``."""

    goal: str = Field(..., description="High-level goal to decompose into steps.")


class ExecuteRequest(BaseModel):
    """Body for ``/execute``."""

    command: str = Field(..., description="Command to classify, gate, and run.")
    session_id: Optional[str] = Field(None, description="Session id for rate limiting.")


class ApprovalRequest(BaseModel):
    """Body for ``/approval/req`` — a human's decision on an escalated action."""

    command: str = Field(..., description="The escalated command being decided on.")
    approve: bool = Field(..., description="True to authorise execution, False to reject.")


class RollbackRequest(BaseModel):
    """Body for ``/rollback``."""

    snapshot_id: Optional[str] = Field(
        None, description="Target snapshot SHA; defaults to the previous snapshot."
    )


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


def _serialize_plan(plan) -> dict:
    """Flatten a Plan (with TaskStep dataclasses) into JSON-safe primitives."""
    return {
        "goal": plan.goal,
        "requires_human": plan.requires_human,
        "steps": [asdict(s) for s in plan.steps],
        "approved": [asdict(s) for s in plan.approved],
        "escalate": [
            {"step": asdict(e["step"]), "reason": e["reason"], "action": e["action"]}
            for e in plan.escalate
        ],
    }


@app.post("/api/v1/plan")
def plan(req: PlanRequest, llm: LLMClient = Depends(get_llm_client)) -> dict:
    """Decompose a goal into a confidence-gated task tree."""
    planner = Planner(llm)
    try:
        result = planner.plan(req.goal)
    except PlannerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _serialize_plan(result)


@app.post("/api/v1/execute")
def execute(req: ExecuteRequest, executor: Executor = Depends(get_executor)) -> dict:
    """Classify, gate, audit, and (if GREEN) run a command in the sandbox."""
    result = executor.execute(req.command, session_id=req.session_id)
    return asdict(result)


@app.post("/api/v1/approval/req")
def approval_req(req: ApprovalRequest, executor: Executor = Depends(get_executor)) -> dict:
    """Resolve a human decision on an escalated (YELLOW) action.

    Approve -> run the command in the sandbox (RED is still refused). Reject ->
    audit the rejection and return without running.
    """
    if not req.approve:
        log_action("human-approval", f"REJECTED: {req.command}", Zone.YELLOW)
        return {"decision": "rejected", "command": req.command, "executed": False}

    result = executor.execute_approved(req.command)
    return {
        "decision": "approved",
        "command": req.command,
        "executed": result.status == "OK",
        "result": asdict(result),
    }


@app.post("/api/v1/rollback")
def rollback(
    req: RollbackRequest, engine: RollbackEngine = Depends(get_rollback_engine)
) -> dict:
    """Restore the sandbox working tree to a prior snapshot."""
    try:
        result = engine.rollback(req.snapshot_id)
    except RollbackError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return asdict(result)
