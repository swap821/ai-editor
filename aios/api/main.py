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
    GET  /api/v1/alignment/evaluation diagnostic human-alignment evidence
    POST /api/v1/alignment/feedback explicit human label for a visible frame

Collaborators (LLM client, executor, rollback engine) are supplied via
dependency injection so tests can override them with fakes/sandboxes and avoid
any network, model, or host side effects.
"""
from __future__ import annotations

import json
import secrets
import sys
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Callable, Iterator, Optional, Any, cast

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import aios
from aios import config
from aios.agents.reflection_agent import ReflectionAgent, ReflectionError
from aios.agents.rollback_engine import RollbackEngine, RollbackError
from aios.agents.tool_agent import ToolAgent
from aios.core.executor import (
    Executor,
    _bounded_run,
    approved_runner_from_config,
    validate_approved_execution_backend,
)
from aios.core.bedrock import BedrockClient
from aios.core.llm import LLMClient, LLMError, OllamaClient
from aios.core.model_selector import (
    TASKS,
    describe_choice,
    infer_task,
    select_model,
    supports_tool_protocol,
)
from aios.core.approvals import ApprovalError, ApprovalStore
from aios.core.alignment import (
    AlignmentInterpreter,
    apply_user_corrections,
    frame_from_state,
    validate_user_corrections,
)
from aios.core.planner import Planner, PlannerError
from aios.core.self_apply import DEFAULT_VERIFY_COMMAND, SelfApplyEngine
from aios.core.verifier import Verifier
from aios.memory.db import get_connection, init_memory_db
from aios.memory.alignment_evaluation import AlignmentEvaluationStore
from aios.memory.consolidation import MemoryConsolidator
from aios.memory.conversation import ConversationStateStore
from aios.memory.curriculum import CurriculumManager
from aios.memory.development import DevelopmentTracker
from aios.memory.episodic import EpisodicMemory
from aios.memory.retrieval import hybrid_search
from aios.memory.semantic import SemanticMemory
from aios.memory.skills import SkillMemory
from aios.security.audit_logger import init_audit_db, log_action, verify_chain
from aios.security.gateway import RateLimiter, Zone, classify
from aios.security.secret_scanner import scan_and_redact

_APPROVALS = ApprovalStore(db_path=config.APPROVAL_DB_PATH)
_RATE_LIMITER = RateLimiter(db_path=config.APPROVAL_DB_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure both databases exist before the app serves traffic."""
    if config.API_HOST not in {"127.0.0.1", "localhost", "::1"}:
        if not config.API_TOKEN:
            raise RuntimeError("AIOS_API_TOKEN is required when AIOS_API_HOST is non-loopback")
        if len(config.API_TOKEN) < 32:
            raise RuntimeError("AIOS_API_TOKEN must be at least 32 characters for non-loopback use")
    validate_approved_execution_backend()
    init_memory_db()
    init_audit_db()
    # Opt-in second injection layer: install the vector blocklist when enabled.
    # Best-effort — a model/load failure must never block startup, since the
    # regex layer remains the active defence.
    if config.INJECTION_VECTOR_SHIELD:
        try:
            from aios.security.injection_shield import VectorInjectionShield
            from aios.security.gateway import set_injection_shield

            set_injection_shield(VectorInjectionShield())
        except Exception:  # noqa: BLE001 - enhancement; never block startup
            pass
    yield


app = FastAPI(
    title="AI OS - Jarvis",
    version=aios.__version__,
    summary="Local-first, memory-driven, security-gated, human-supervised AI OS.",
    lifespan=lifespan,
)

# Browser clients (the Vite front-end) run on a different origin, so the API
# must opt them in explicitly. Origins come from config (env-overridable).
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.API_CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def require_api_token(request: Request, call_next):
    """Protect API and schema surfaces; keep unauthenticated use loopback-only."""
    protected = request.url.path.startswith("/api/") or request.url.path in {
        "/docs",
        "/redoc",
        "/openapi.json",
    }
    if protected and request.method != "OPTIONS":
        if config.API_TOKEN:
            auth = request.headers.get("authorization", "")
            expected = f"Bearer {config.API_TOKEN}"
            if not secrets.compare_digest(auth, expected):
                return JSONResponse(status_code=401, content={"detail": "invalid or missing API token"})
        else:
            client_host = request.client.host if request.client else ""
            if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "unauthenticated API access is loopback-only"},
                )
    return await call_next(request)


def get_llm_client() -> LLMClient:
    """Provide the default local LLM client. Overridden in tests."""
    return OllamaClient()


def get_ollama_client() -> OllamaClient:
    """Provide a concrete Ollama client for streaming + model discovery.

    Distinct from :func:`get_llm_client` (which yields the minimal protocol) so
    the chat/discovery endpoints can use streaming and ``/api/tags`` while
    remaining overridable in tests.
    """
    return OllamaClient()


def get_bedrock_client() -> Optional[BedrockClient]:
    """Provide the AWS Bedrock cloud chat client, or ``None`` when unconfigured.

    Returns ``None`` unless :data:`aios.config.BEDROCK_ENABLED` (region + model
    set) *and* boto3 is importable — so the agent transparently stays on local
    inference when the cloud isn't set up. Overridden in tests with a fake.
    """
    if not config.BEDROCK_ENABLED:
        return None
    try:
        return BedrockClient()
    except LLMError:
        return None


def get_executor() -> Executor:
    """Provide the default scope-constrained executor. Overridden in tests."""
    return Executor(
        approved_runner=approved_runner_from_config(),
        rate_limiter=_RATE_LIMITER,
    )

def get_approval_store() -> ApprovalStore:
    """Provide the durable local multi-worker approval capability store."""
    return _APPROVALS


def get_rollback_engine() -> RollbackEngine:
    """Provide the default sandbox rollback engine. Overridden in tests."""
    return RollbackEngine()


def get_self_apply_engine(
    executor: Executor = Depends(get_executor),
) -> SelfApplyEngine:
    """Provide the Self-Analysis T3 apply engine (verifies via the gated Executor).

    The engine is the ONLY way an approved proposal reaches the real ``aios/`` source
    — there is deliberately no agent tool that applies. Overridden in tests with a
    fake verifier + temp project root so no real shell/suite runs.
    """
    isolated_runner = approved_runner_from_config()

    def project_root_runner(
        command: str, *, cwd: str, env: dict[str, str], timeout_s: int
    ) -> tuple[str, str, int]:
        """Run self-apply verification from the project root, after gateway approval.

        ``SelfApplyEngine`` verifies changes to ``aios/`` with ``pytest tests/``.
        The ordinary agent executor intentionally runs in ``training_ground/``;
        using that cwd would look for ``training_ground/tests`` and roll back good
        proposals. The command still passes through the same Executor gateway and
        audit path before this runner is invoked.
        """
        if command != DEFAULT_VERIFY_COMMAND:
            raise ValueError("self-apply verifier accepts only the fixed project test command")
        if isolated_runner is not None:
            return isolated_runner(
                command,
                cwd=str(config.PROJECT_ROOT),
                env=env,
                timeout_s=timeout_s,
            )
        completed = _bounded_run(
            [sys.executable, "-m", "pytest", "tests/", "-q"],
            cwd=str(config.PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return completed.stdout or "", completed.stderr or "", completed.returncode

    verify_executor = Executor(
        runner=project_root_runner,
        timeout_s=120,
        actor="self-apply-verifier",
    )
    return SelfApplyEngine(verifier=Verifier(verify_executor))


def get_edit_snapshot() -> Callable[..., object]:
    """Provide the pre-edit snapshot hook for the agent's ``edit_file`` tool.

    Returns a callable that lazily constructs a sandbox :class:`RollbackEngine`
    and snapshots it — only when an approved edit is actually applied, so read /
    command turns pay nothing. Fail-closed: a snapshot failure propagates so the
    agent refuses the edit (no unprotected write). Overridden in tests with a recorder.
    """
    def snapshot(message: str = "pre-edit snapshot") -> None:
        # Let failures propagate: the agent treats a snapshot error as fail-closed
        # and refuses the edit, so a write is never applied without a captured
        # pre-edit state to roll back to.
        RollbackEngine().create_snapshot(message)

    return snapshot


def get_semantic_indexer() -> Optional[SemanticMemory]:
    """Provide the L3 semantic writer used to index completed chat turns.

    Returns ``None`` when :data:`aios.config.INDEX_CHAT` is disabled (so no
    embedding model is loaded). Overridden in tests with a fake recorder so the
    suite never loads the real embedder or mutates the on-disk vector index.
    """
    return SemanticMemory() if config.INDEX_CHAT else None


def get_reflection_agent(
    llm: LLMClient = Depends(get_llm_client),
) -> Optional[ReflectionAgent]:
    """Provide the reflection agent that turns a command failure into a lesson.

    Returns ``None`` when :data:`aios.config.REFLECT_ON_FAILURE` is disabled.
    Reuses the injected LLM client so it is fully overridable in tests.
    """
    return ReflectionAgent(llm) if config.REFLECT_ON_FAILURE else None


def get_development_tracker() -> DevelopmentTracker:
    """Provide the evidence-backed developmental metrics store."""
    return DevelopmentTracker()


def get_skill_memory() -> SkillMemory:
    """Provide verification-backed procedural skill memory."""
    return SkillMemory()


def get_curriculum_manager() -> CurriculumManager:
    """Provide the non-autonomous curriculum evidence store."""
    return CurriculumManager()


def get_memory_consolidator() -> MemoryConsolidator:
    """Provide the evidence-gated trusted-memory promotion service."""
    return MemoryConsolidator()


def get_conversation_state_store() -> ConversationStateStore:
    """Provide durable, unverified shared-understanding state."""
    return ConversationStateStore()


def get_alignment_evaluation_store() -> AlignmentEvaluationStore:
    """Provide diagnostic human-alignment evidence; it never changes policy."""
    return AlignmentEvaluationStore()


def get_alignment_interpreter(
    llm: LLMClient = Depends(get_llm_client),
) -> Optional[AlignmentInterpreter]:
    """Provide the advisory per-turn alignment interpreter.

    Returns ``None`` when :data:`aios.config.INTERPRET_ALIGNMENT` is disabled,
    so a generated turn costs no extra local completion. Reuses the injected
    LLM client so tests override it with fakes.
    """
    return AlignmentInterpreter(llm) if config.INTERPRET_ALIGNMENT else None


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
    session_id: Optional[str] = Field(
        None,
        alias="sessionId",
        description="Required for a YELLOW command's server-issued approval capability.",
    )

    model_config = {"populate_by_name": True}


class ApprovalRequest(BaseModel):
    """Body for ``/approval/req`` — a human's decision on an escalated action."""

    approval_token: str = Field(..., alias="approvalToken")
    session_id: str = Field(..., alias="sessionId")
    approve: bool = Field(..., description="True to authorise execution, False to reject.")

    model_config = {"populate_by_name": True}


class RollbackRequest(BaseModel):
    """Body for ``/rollback``."""

    snapshot_id: Optional[str] = Field(
        None, description="Target snapshot SHA; defaults to the previous snapshot."
    )


class ApplyProposalRequest(BaseModel):
    """Body for the Self-Analysis T3 apply endpoint — the HUMAN approver's id."""

    approved_by: str = Field("", alias="approvedBy")

    model_config = {"populate_by_name": True}


class GenerateRequest(BaseModel):
    """Body for ``/api/generate`` — the conversational chat endpoint.

    ``messages`` is the front-end's running history in the shape
    ``[{"role": "user"|"assistant", "content": [{"text": "..."}]}]``.
    ``model_id`` is the UI's selected model id (e.g. ``ollama.llama3.2:3b``);
    the ``ollama.`` prefix is stripped, while an explicit non-local id requires
    configured Bedrock and never silently changes providers.
    """

    messages: list[dict[str, Any]] = Field(default_factory=lambda: cast(list[dict[str, Any]], []))
    model_id: Optional[str] = Field(None, alias="modelId")
    session_id: str = Field("ui-session", alias="sessionId")
    approval_tokens: list[str] = Field(default_factory=list, alias="approvalTokens")
    #: Commands the human has authorised for this turn. When the agent pauses on
    #: a YELLOW command, the frontend re-sends the turn with that command added
    #: here so it actually runs (resumable in-chat approval — blueprint Q5).
    approved_commands: list[str] = Field(default_factory=list, alias="approvedCommands")
    #: File edits the human has authorised this turn (the edit analog of
    #: ``approvedCommands``), each ``{filepath, old_string, new_string}``.
    approved_edits: list[dict[str, Any]] = Field(default_factory=list, alias="approvedEdits")
    #: New files the human has authorised this turn (the create analog of
    #: ``approvedEdits``), each ``{filepath, content}``.
    approved_creations: list[dict[str, Any]] = Field(default_factory=list, alias="approvedCreations")

    model_config = {"populate_by_name": True}


class TerminalRequest(BaseModel):
    """Body for ``/api/terminal`` — a single shell command from the UI terminal."""

    command: str = Field(..., description="Command typed into the UI terminal.")
    session_id: Optional[str] = Field(None, alias="sessionId")

    model_config = {"populate_by_name": True}


class FactPromotionRequest(BaseModel):
    """Body for human-approved contradiction-aware fact promotion."""

    subject: str
    predicate: str
    object: str
    approved_by: str = Field(..., alias="approvedBy")

    model_config = {"populate_by_name": True}


class CurriculumTaskRequest(BaseModel):
    """Body for defining a safe curriculum task; definitions never auto-run."""

    skill_name: str = Field(..., alias="skillName")
    level: int = Field(..., ge=1)
    prompt: str
    held_out: bool = Field(False, alias="heldOut")

    model_config = {"populate_by_name": True}


class ConversationSessionRequest(BaseModel):
    """Request restoration of one durable conversation session."""

    session_id: str = Field(..., min_length=1, alias="sessionId")
    limit: int = Field(50, ge=1, le=100)

    model_config = {"populate_by_name": True}


class ConversationCorrectionRequest(BaseModel):
    """User-authored corrections to the current advisory interpretation."""

    session_id: str = Field(..., min_length=1, alias="sessionId")
    corrections: dict[str, Any]

    model_config = {"populate_by_name": True}


class AlignmentFeedbackRequest(BaseModel):
    """Explicit human evaluation of the latest visible understanding frame."""

    session_id: str = Field(..., min_length=1, alias="sessionId")
    observation_id: Optional[int] = Field(None, ge=1, alias="observationId")
    outcome: str
    issues: list[str] = Field(default_factory=list)
    notes: str = Field("", max_length=2000)

    model_config = {"populate_by_name": True}


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict[str, Any]:
    """Liveness probe."""
    return {"status": "ok", "version": aios.__version__}


@app.post("/api/v1/memory/search")
def memory_search(req: MemorySearchRequest) -> dict[str, Any]:
    """Hybrid BM25 + FAISS + temporal-decay retrieval over semantic memory."""
    results = hybrid_search(req.query, top_k=req.top_k)
    return {"query": req.query, "results": [asdict(r) for r in results]}


@app.post("/api/v1/memory/consolidate")
def memory_consolidate(
    consolidator: MemoryConsolidator = Depends(get_memory_consolidator),
) -> dict[str, Any]:
    """Idempotently index current verified lessons and active approved facts."""
    return consolidator.run()


@app.post("/api/v1/conversation/session")
def restore_conversation_session(
    req: ConversationSessionRequest,
    state: ConversationStateStore = Depends(get_conversation_state_store),
) -> dict[str, Any]:
    """Restore recent dialogue and the latest unverified alignment frame."""
    rows = _EPISODIC.recent(req.session_id, req.limit)
    messages = [
        {"role": str(row["role"]), "content": [{"text": str(row["content"])}]}
        for row in rows
        if row["role"] in {"user", "assistant"}
    ]
    return {
        "alignment": state.get(req.session_id),
        "activeCorrection": state.active_correction(req.session_id),
        "correctionHistory": state.correction_history(req.session_id),
        "messages": messages,
    }


@app.post("/api/v1/conversation/correction")
def correct_conversation_alignment(
    req: ConversationCorrectionRequest,
    state: ConversationStateStore = Depends(get_conversation_state_store),
    evaluation: AlignmentEvaluationStore = Depends(get_alignment_evaluation_store),
) -> dict[str, Any]:
    """Apply user-authored interpretation overrides; never grant authority."""
    current_payload = state.get(req.session_id)
    if current_payload is None:
        raise HTTPException(status_code=404, detail="no alignment frame exists for session")
    try:
        incoming = validate_user_corrections(req.corrections)
        active = state.active_correction(req.session_id)
        merged = dict(active["corrections"]) if active is not None else {}
        merged.update(incoming)
        current = frame_from_state(current_payload)
        corrected = apply_user_corrections(current, merged, revision=1)
        corrected_payload = corrected.as_dict()
        evaluation_payload = current_payload.get("evaluation")
        if isinstance(evaluation_payload, dict):
            corrected_payload["evaluation"] = evaluation_payload
        revision, persisted = state.record_correction(
            req.session_id,
            before_frame=current_payload,
            after_frame=corrected_payload,
            corrections=merged,
            corrected_fields=sorted(merged),
            expected_revision=(int(active["revision"]) if active is not None else None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        observation_id = (
            evaluation_payload.get("observation_id")
            if isinstance(evaluation_payload, dict)
            else None
        )
        evaluation.mark_latest_corrected(
            req.session_id,
            sorted(merged),
            observation_id=int(observation_id) if observation_id else None,
        )
    except Exception:  # noqa: BLE001 - diagnostic evidence must never break correction
        pass
    return {
        "alignment": persisted,
        "activeCorrection": {
            "revision": revision,
            "corrections": merged,
            "fields": sorted(merged),
        },
        "correctionHistory": state.correction_history(req.session_id),
    }


@app.get("/api/v1/alignment/evaluation")
def alignment_evaluation_summary(
    evaluation: AlignmentEvaluationStore = Depends(get_alignment_evaluation_store),
) -> dict[str, Any]:
    """Return diagnostic alignment evidence without changing policy."""
    return evaluation.summary()


@app.post("/api/v1/alignment/feedback")
def record_alignment_feedback(
    req: AlignmentFeedbackRequest,
    evaluation: AlignmentEvaluationStore = Depends(get_alignment_evaluation_store),
) -> dict[str, Any]:
    """Record explicit operator feedback on the latest session observation."""
    try:
        observation_id = evaluation.record_feedback(
            req.session_id,
            outcome=req.outcome,
            issues=req.issues,
            notes=req.notes,
            observation_id=req.observation_id,
        )
    except ValueError as exc:
        status = 404 if "no alignment observation" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {
        "observationId": observation_id,
        "automaticPolicyUpdates": False,
    }


@app.post("/api/v1/conversation/correction/clear")
def clear_conversation_alignment_correction(
    req: ConversationSessionRequest,
    state: ConversationStateStore = Depends(get_conversation_state_store),
) -> dict[str, Any]:
    """Clear active user corrections and restore the superseded base frame."""
    try:
        restored = state.clear_correction(req.session_id)
        alignment = frame_from_state(restored).as_dict()
        evaluation_payload = restored.get("evaluation")
        if isinstance(evaluation_payload, dict):
            alignment["evaluation"] = evaluation_payload
        state.save(req.session_id, alignment)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "alignment": alignment,
        "activeCorrection": None,
        "correctionHistory": state.correction_history(req.session_id),
    }


@app.post("/api/v1/memory/facts")
def promote_fact(
    req: FactPromotionRequest,
    consolidator: MemoryConsolidator = Depends(get_memory_consolidator),
) -> dict[str, Any]:
    """Promote one human-approved fact, refusing unresolved contradictions."""
    result = consolidator.promote_fact(
        req.subject, req.predicate, req.object, approved_by=req.approved_by
    )
    if result.reason == "contradiction":
        raise HTTPException(
            status_code=409,
            detail={
                "reason": result.reason,
                "conflictId": result.conflict_id,
                "conflictObject": result.conflict_object,
            },
        )
    if not result.committed:
        raise HTTPException(status_code=422, detail=result.reason)
    return asdict(result)


@app.post("/api/v1/memory/facts/reconcile")
def reconcile_fact(
    req: FactPromotionRequest,
    consolidator: MemoryConsolidator = Depends(get_memory_consolidator),
) -> dict[str, Any]:
    """Human-approved replacement of a contradictory fact and its vector."""
    result = consolidator.reconcile_fact(
        req.subject, req.predicate, req.object, approved_by=req.approved_by
    )
    if not result.committed:
        raise HTTPException(status_code=422, detail=result.reason)
    return asdict(result)


@app.get("/api/v1/development/metrics")
def development_metrics(
    tracker: DevelopmentTracker = Depends(get_development_tracker),
) -> dict[str, Any]:
    """Return measured behavior-change and verification coverage metrics."""
    return tracker.summary()


@app.get("/api/v1/development/skills")
def development_skills(
    status: Optional[str] = None,
    skills: SkillMemory = Depends(get_skill_memory),
) -> dict[str, Any]:
    """List candidate and verified procedural skills."""
    return {"skills": skills.list(status=status)}


@app.get("/api/v1/development/curriculum")
def development_curriculum(
    skill_name: Optional[str] = None,
    curriculum: CurriculumManager = Depends(get_curriculum_manager),
) -> dict[str, Any]:
    """List safe curriculum definitions and evidence state."""
    return {"tasks": curriculum.list(skill_name)}


@app.post("/api/v1/development/curriculum")
def add_curriculum_task(
    req: CurriculumTaskRequest,
    curriculum: CurriculumManager = Depends(get_curriculum_manager),
) -> dict[str, Any]:
    """Define a curriculum task without executing it."""
    try:
        task_id = curriculum.add_task(
            req.skill_name, req.level, req.prompt, held_out=req.held_out
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": task_id, "executed": False}


@app.post("/api/v1/security/classify")
def security_classify(req: ClassifyRequest) -> dict[str, Any]:
    """Deterministic, fail-closed security-zone classification."""
    result = classify(req.command)
    return {
        "zone": result.zone.value,
        "confidence": result.confidence,
        "reason": result.reason,
    }


@app.get("/api/v1/audit/verify")
def audit_verify(from_entry: int = 1, to_entry: Optional[int] = None) -> dict[str, Any]:
    """Verify the tamper-evident audit hash chain over an optional id range."""
    status = verify_chain(from_id=from_entry, to_id=to_entry)
    return asdict(status)


@app.post("/api/v1/reflect")
def reflect(req: ReflectRequest, llm: LLMClient = Depends(get_llm_client)) -> dict[str, Any]:
    """Run the reflection agent on a failure and store a structured lesson."""
    agent = ReflectionAgent(llm)
    try:
        reflection = agent.reflect(req.command, req.error_output, task_id=req.task_id)
    except ReflectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return asdict(reflection)


def _serialize_plan(plan: Any) -> dict[str, Any]:
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
        "calibrations": [asdict(c) for c in plan.calibrations],
    }


@app.post("/api/v1/plan")
def plan(req: PlanRequest, llm: LLMClient = Depends(get_llm_client)) -> dict[str, Any]:
    """Decompose a goal into a confidence-gated task tree."""
    planner = Planner(llm)
    try:
        result = planner.plan(req.goal)
    except PlannerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _serialize_plan(result)


@app.post("/api/v1/execute")
def execute(
    req: ExecuteRequest,
    executor: Executor = Depends(get_executor),
    approvals: ApprovalStore = Depends(get_approval_store),
) -> dict[str, Any]:
    """Classify, gate, audit, and (if GREEN) run a command in the sandbox."""
    result = executor.execute(req.command, session_id=req.session_id)
    response = asdict(result)
    if result.status == "REQUIRE_APPROVAL":
        if not req.session_id:
            raise HTTPException(
                status_code=400,
                detail="sessionId is required to approve a YELLOW command",
            )
        response["approvalToken"] = approvals.issue(
            "command", {"command": req.command}, req.session_id
        )
        response["sessionId"] = req.session_id
    return response


@app.post("/api/v1/approval/req")
def approval_req(
    req: ApprovalRequest,
    executor: Executor = Depends(get_executor),
    approvals: ApprovalStore = Depends(get_approval_store),
) -> dict[str, Any]:
    """Resolve a human decision on an escalated (YELLOW) action.

    Approve -> run the command in the sandbox (RED is still refused). Reject ->
    audit the rejection and return without running.
    """
    try:
        action = approvals.consume(req.approval_token, req.session_id)
    except ApprovalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    command = str(action.payload.get("command", ""))
    if not req.approve:
        if action.action_type == "command":
            executor.reset_sensitive_actions(req.session_id)
        target = command or str(action.payload.get("filepath", action.action_type))
        log_action("human-approval", f"REJECTED {action.action_type}: {target}", Zone.YELLOW)
        return {
            "decision": "rejected",
            "actionType": action.action_type,
            "command": command,
            "executed": False,
        }
    if action.action_type != "command":
        raise HTTPException(status_code=400, detail="approval token is not for a command")
    executor.reset_sensitive_actions(req.session_id)

    result = executor.execute_approved(command)
    return {
        "decision": "approved",
        "command": command,
        "executed": result.status == "OK",
        "result": asdict(result),
    }


@app.post("/api/v1/rollback")
def rollback(
    req: RollbackRequest, engine: RollbackEngine = Depends(get_rollback_engine)
) -> dict[str, Any]:
    """Restore the sandbox working tree to a prior snapshot."""
    try:
        result = engine.rollback(req.snapshot_id)
    except RollbackError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return asdict(result)


# --------------------------------------------------------------------------- #
# Self-Analysis T3 — human-gated review + apply of fix proposals
# The agent has NO tool to apply (see tool_agent); these human-called endpoints
# are the ONLY path from a 'proposed' row to a real write in aios/.
# --------------------------------------------------------------------------- #
@app.get("/api/v1/self-analysis/proposals")
def list_proposals(status: Optional[str] = "proposed") -> dict[str, Any]:
    """List Self-Analysis findings (default the ``proposed`` ones) for the review UI."""
    init_memory_db()
    sql = (
        "SELECT id, target_path, finding_type, evidence, proposed_zone, "
        "proposed_diff, proposed_by, approved_by, status FROM self_analysis_report"
    )
    params: list[Any] = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY id DESC LIMIT 200"
    with get_connection() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    return {"proposals": rows}


@app.post("/api/v1/self-analysis/proposals/{proposal_id}/apply")
def apply_proposal(
    proposal_id: int,
    req: ApplyProposalRequest,
    engine: SelfApplyEngine = Depends(get_self_apply_engine),
) -> dict[str, Any]:
    """Apply an approved proposal to ``aios/`` — gated, verified, auto-rollback (T3)."""
    result = engine.apply(proposal_id, approved_by=req.approved_by)
    return asdict(result)


@app.post("/api/v1/self-analysis/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int) -> dict[str, Any]:
    """Reject a ``proposed`` finding (status -> ``rejected``); never applies anything."""
    init_memory_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT status FROM self_analysis_report WHERE id = ?", (proposal_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"no proposal with id {proposal_id}")
        if row["status"] != "proposed":
            raise HTTPException(
                status_code=409,
                detail=f"proposal {proposal_id} is '{row['status']}', not 'proposed'",
            )
        conn.execute(
            "UPDATE self_analysis_report SET status = 'rejected' WHERE id = ?", (proposal_id,)
        )
    return {"id": proposal_id, "status": "rejected"}


# --------------------------------------------------------------------------- #
# Front-end bridge: model discovery, conversational chat, UI terminal
# These three endpoints back the React UI's main surfaces. The ``/api/v1/*``
# routes above expose individual subsystems; these compose them for the UI.
# --------------------------------------------------------------------------- #
@app.get("/api/v1/models/local")
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


@app.get("/api/v1/models/bedrock")
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


@app.get("/api/v1/models/auto")
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


def _resolve_local_model(model_id: Optional[str]) -> str:
    """Map a UI model id to a local Ollama tag (``ollama.x`` -> ``x``).

    Non-local ids (or none) fall back to the configured default local model, so
    the local-first backend always has something to run.
    """
    if model_id and model_id.startswith("ollama."):
        return model_id[len("ollama.") :]
    return config.LLM_MODEL


#: UI model ids meaning "let the agent choose the best installed local model".
_AUTO_IDS = frozenset({"auto", "auto.best", "ollama.auto"})


def _auto_local_model(ollama: Any, task: str = "coding") -> Optional[str]:
    """Best installed TOOL-CAPABLE local model for *task*, or ``None``.

    ``require_tools=True``: the agentic loop must never route to a model that
    can't function-call (reasoning-only/base families), even when the request
    reads like reasoning. Fail-soft: discovery/selection failing must never break
    a turn, so the caller falls back to the configured default.
    """
    try:
        info = ollama.list_models()
        return select_model(info.get("models") or [], task=task, require_tools=True)
    except Exception:  # noqa: BLE001 - discovery/selection must never raise
        return None


def _select_chat_client(
    model_id: Optional[str],
    ollama: Any,
    bedrock: Optional[Any],
    *,
    task: str = "coding",
) -> tuple[Any, str]:
    """Pick the ``(chat_client, model)`` for the requested UI model id.

    ``auto`` lets the AGENT choose the best installed local model for *task* (the
    user never has to). ``ollama.x`` always runs locally on ``x``. An explicit
    non-local id routes to Bedrock and fails clearly when Bedrock is unavailable;
    it never silently changes providers. No id means the configured local default.
    """
    if model_id in _AUTO_IDS:
        # Agent-chosen model for the agentic loop. Fail-soft: if Ollama is
        # unreachable or has no usable model, fall through to cloud/default below.
        chosen = _auto_local_model(ollama, task)
        if chosen:
            return ollama, chosen
        if bedrock is not None:
            return bedrock, config.BEDROCK_MODEL
        return ollama, config.LLM_MODEL
    if model_id and model_id.startswith("ollama."):
        local_model = _resolve_local_model(model_id)
        if not supports_tool_protocol(local_model):
            raise HTTPException(
                status_code=422,
                detail=f"local model '{local_model}' cannot accept the agent tool protocol",
            )
        return ollama, local_model
    if model_id and bedrock is not None:
        # Pass the selected Bedrock model id straight through (so each dropdown
        # choice runs that actual model).
        return bedrock, model_id
    if model_id:
        raise HTTPException(
            status_code=503,
            detail="cloud model selected but AWS Bedrock is not configured",
        )
    return ollama, config.LLM_MODEL


def _to_chat_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten the UI history (``content`` arrays) into Ollama chat messages."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            content_list: list[Any] = cast(list[Any], content)
            text_parts: list[str] = [
                cast(dict[str, Any], c).get("text", "")
                for c in content_list
                if isinstance(c, dict)
            ]
            text = " ".join(text_parts).strip()
        else:
            text = ""
        if text:
            out.append({"role": role, "content": text})
    return out


def _sse(event: str, data: dict[str, Any]) -> str:
    """Format one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


#: Agent event type -> SSE event name the front-end's stream reader understands.
_STEP_EVENTS = {"tool_call", "tool_result", "tool_blocked"}

#: Episodic (L2) memory facade — the durable, chronological record of every turn.
_EPISODIC = EpisodicMemory()


def _latest_user(chat_messages: list[dict[str, Any]]) -> str:
    """Return the most recent user message text (already flattened to a string)."""
    for msg in reversed(chat_messages):
        if msg["role"] == "user":
            return msg["content"]
    return ""


def _recall_memory(query: str, top_k: int = 3) -> Optional[str]:
    """Best-effort hybrid recall of relevant semantic memories for *query*.

    Returns a prompt-ready knowledge block, or ``None`` when there is nothing
    relevant (or the memory subsystem is unavailable). ``hybrid_search``
    short-circuits to empty without loading the embedding model when the
    semantic index is empty, so this is a cheap no-op on a fresh system.
    """
    try:
        hits = hybrid_search(query, top_k=top_k)
    except Exception:  # noqa: BLE001 - recall is an enhancement, never fatal
        return None
    if not hits:
        return None
    trusted = [
        hit for hit in hits if getattr(hit, "verification_status", "unverified") == "verified"
    ]
    unverified = [hit for hit in hits if hit not in trusted]
    blocks: list[str] = []
    if trusted:
        blocks.append(
            "VERIFIED TRUSTED MEMORY (still prefer current tool evidence when available):\n"
            + "\n".join(f"- {hit.text}" for hit in trusted)
        )
    if unverified:
        blocks.append(
            "UNVERIFIED PRIOR CHAT MEMORY (may be stale or wrong; use only as a lead, "
            "never as evidence, and verify against tools/files before acting):\n"
            + "\n".join(f"- {hit.text}" for hit in unverified)
        )
    return "\n\n".join(blocks)


def _record_episode(session_id: str, role: str, content: str) -> None:
    """Persist one turn to L2 episodic memory. Best-effort; never fatal."""
    if not content or not content.strip():
        return
    try:
        _EPISODIC.record(session_id, role, scan_and_redact(content).scrubbed)
    except Exception:  # noqa: BLE001 - persistence must not break the chat
        pass


def _recall_lessons(
    reflector: Optional[ReflectionAgent], session_id: str, query: str, limit: int = 5
) -> list[dict[str, Any]]:
    """Best-effort recall of pending same-task and verified cross-task lessons.

    Carries lessons learned in earlier turns into the current one so the agent
    reasons with them. Recalled pending lessons remain advisory. Never fatal.
    """
    if reflector is None:
        return []
    try:
        recall_relevant = getattr(reflector, "recall_relevant", None)
        if callable(recall_relevant):
            return recall_relevant(query, session_id, limit)
        return reflector.recall_pending(session_id, limit)
    except Exception:  # noqa: BLE001 - lesson recall is an enhancement, never fatal
        return []


def _recall_skills(skills: SkillMemory, query: str, limit: int = 3) -> list[dict[str, Any]]:
    """Best-effort recall of reusable workflows backed by repeated verification."""
    try:
        return skills.relevant_verified(query, limit)
    except Exception:  # noqa: BLE001 - skill recall is an enhancement, never fatal
        return []


def _workflow_step(event: dict[str, Any]) -> str:
    """Create a compact, redacted procedural step from one tool-call event."""
    name = str(event.get("tool", ""))
    raw_input = event.get("input")
    if not isinstance(raw_input, dict):
        return name
    useful = []
    for key in ("command", "filepath", "path", "goal"):
        value = raw_input.get(key)
        if value is not None and str(value).strip():
            useful.append(f"{key}={str(value).strip()[:160]}")
    detail = ", ".join(useful)
    return scan_and_redact(f"{name}: {detail}" if detail else name).scrubbed


def _index_turn(
    indexer: Optional[SemanticMemory], user_text: str, answer: str
) -> None:
    """Embed a completed Q->A turn into L3 semantic memory so future recall finds it.

    Best-effort and gated by the injected *indexer* (``None`` disables it). This
    is what makes recall self-reinforcing: today's answer becomes tomorrow's
    recalled context. Skipped for empty answers.
    """
    answer = (answer or "").strip()
    if indexer is None or not answer:
        return
    try:
        payload = f"UNVERIFIED_CHAT\nUser: {user_text}\nAssistant: {answer}"
        clean = scan_and_redact(payload).scrubbed
        try:
            indexer.add(clean, memory_type="chat", verification_status="unverified")
        except TypeError:
            indexer.add(clean)
    except Exception:  # noqa: BLE001 - indexing must not break the chat
        pass


def _make_failure_hook(reflector: Optional[ReflectionAgent], session_id: str) -> Optional[Any]:
    """Build the agent's on-failure hook from a reflection agent (or ``None``).

    The hook records a structured lesson in the Mistake pool and returns a small
    summary for the UI; any failure to reflect is swallowed so a learning step
    never breaks the chat.
    """
    if reflector is None:
        return None

    def hook(command: str, error_output: str) -> Optional[dict[str, Any]]:
        try:
            reflection = reflector.reflect(command, error_output, task_id=session_id)
        except ReflectionError:
            return None
        except Exception:  # noqa: BLE001 - reflection must never break the chat
            return None
        return {
            "error_type": reflection.error_type,
            "lesson_text": reflection.lesson_text,
            "recurrence": reflection.recurrence,
            "mistake_id": reflection.mistake_id,
        }

    return hook


def _make_confirm_hook(
    reflector: Optional[ReflectionAgent],
    consolidator: Optional[MemoryConsolidator] = None,
):
    """Build the agent's lesson-confirmation hook (promotes pending->verified).

    Guarded so promotion can never break the chat; ``None`` when reflection is
    disabled, in which case the agent simply never confirms.
    """
    if reflector is None:
        return None

    def confirm(mistake_id: int) -> None:
        try:
            reflector.confirm_lesson(mistake_id)
            if consolidator is not None:
                consolidator.consolidate_lesson(mistake_id)
        except Exception:  # noqa: BLE001 - confirmation must never break the chat
            pass

    return confirm


@app.post("/api/generate")
def generate(
    req: GenerateRequest,
    client: OllamaClient = Depends(get_ollama_client),
    bedrock: Optional[BedrockClient] = Depends(get_bedrock_client),
    executor: Executor = Depends(get_executor),
    indexer: Optional[SemanticMemory] = Depends(get_semantic_indexer),
    reflector: Optional[ReflectionAgent] = Depends(get_reflection_agent),
    snapshot: Callable[..., object] = Depends(get_edit_snapshot),
    planner_llm: LLMClient = Depends(get_llm_client),
    approvals: ApprovalStore = Depends(get_approval_store),
    development: DevelopmentTracker = Depends(get_development_tracker),
    skills: SkillMemory = Depends(get_skill_memory),
    curriculum: CurriculumManager = Depends(get_curriculum_manager),
    consolidator: MemoryConsolidator = Depends(get_memory_consolidator),
    conversation_state: ConversationStateStore = Depends(get_conversation_state_store),
    alignment_evaluation: AlignmentEvaluationStore = Depends(get_alignment_evaluation_store),
    alignment_interpreter: Optional[AlignmentInterpreter] = Depends(get_alignment_interpreter),
) -> StreamingResponse:
    """Run the agentic tool loop with memory, streaming it to the UI as SSE.

    Pipeline per turn (blueprint stages 4 -> ... -> consolidation):
      1. Recall relevant semantic memories and inject them into the agent's
         context (surfaced as a ``query_knowledge`` step when anything is found).
      2. Persist the user turn to L2 episodic memory.
      3. Run the agentic tool loop (``read_file``/``read_directory``/
         ``execute_terminal``, all gated + audited), forwarding tool activity as
         ``step`` frames, the validated advisory interpretation as an
         ``alignment`` frame, the answer as ``text_chunk`` frames, any code as
         a ``code`` frame, and finishing with ``done`` (or ``error``).
      4. Persist the assistant's final answer to L2 episodic memory and embed the
         completed turn into L3 semantic memory (self-reinforcing recall).
    """
    chat_messages = _to_chat_messages(req.messages)
    user_text = _latest_user(chat_messages)
    # The agent routes by PURPOSE: infer the task from the user's message so 'auto'
    # picks a coder for code, a reasoner for analysis, etc. (require_tools still
    # keeps the loop on a tool-capable model regardless of the inferred task).
    task = infer_task(user_text)
    chat_client, model = _select_chat_client(req.model_id, client, bedrock, task=task)
    session_id = req.session_id
    if req.approved_commands or req.approved_edits or req.approved_creations:
        raise HTTPException(
            status_code=400,
            detail="raw approved payloads are not accepted; use server-issued approvalTokens",
        )
    approved_commands: list[str] = []
    approved_edits: list[dict[str, Any]] = []
    approved_creations: list[dict[str, Any]] = []
    try:
        if not req.approval_tokens:
            approvals.clear_session(session_id)
        for token in req.approval_tokens:
            action = approvals.redeem(token, session_id)
            if action.action_type == "command":
                executor.reset_sensitive_actions(session_id)
        for action in approvals.grants(session_id):
            if action.action_type == "command":
                approved_commands.append(str(action.payload["command"]))
            elif action.action_type == "edit":
                approved_edits.append(action.payload)
            elif action.action_type == "create":
                approved_creations.append(action.payload)
    except (ApprovalError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid approval token: {exc}") from exc

    def event_stream() -> Iterator[str]:
        if not user_text:
            yield _sse("error", {"text": "No user message provided."})
            return

        # 1. Understand + apply the deterministic communication policy + recall.
        #    The alignment frame is advisory. Its communication policy may pause
        #    a context-free request to ask a question, but it has no execution or
        #    approval authority and is never treated as evidence. When the
        #    interpreter is disabled (AIOS_INTERPRET_ALIGNMENT=false) the turn
        #    skips interpretation entirely: no frame, observation, or ask-pause.
        context_parts: list[str] = []
        alignment = None
        if alignment_interpreter is not None:
            base_alignment = alignment_interpreter.understand(chat_messages)
            alignment = base_alignment
            active_correction = conversation_state.active_correction(session_id)
            if active_correction is not None:
                try:
                    alignment = apply_user_corrections(
                        alignment,
                        active_correction["corrections"],
                        revision=int(active_correction["revision"]),
                    )
                except (TypeError, ValueError):
                    # Corrupt optional continuity state must never break chat or
                    # silently gain authority.
                    pass
            context_parts.append(alignment.to_prompt_block())
            alignment_payload = alignment.as_dict()
            base_alignment_payload = base_alignment.as_dict()
            try:
                observation_id = (
                    alignment_evaluation.latest_observation_id(session_id)
                    if req.approval_tokens
                    else alignment_evaluation.record(session_id, alignment_payload)
                )
                if observation_id is not None:
                    alignment_payload["evaluation"] = {
                        "observation_id": observation_id,
                        "automatic_policy_updates": False,
                    }
                    base_alignment_payload["evaluation"] = alignment_payload["evaluation"]
            except Exception:  # noqa: BLE001 - evaluation must never break the chat
                pass
            try:
                if active_correction is not None and alignment.correction.active:
                    conversation_state.refresh_active_correction(
                        session_id,
                        base_frame=base_alignment_payload,
                        corrected_frame=alignment_payload,
                    )
                else:
                    conversation_state.save(session_id, alignment_payload)
            except Exception:  # noqa: BLE001 - continuity must never break the chat
                pass
            yield _sse("alignment", alignment_payload)
            if alignment.communication.ambiguity_action == "ask":
                question = alignment.communication.clarifying_question
                _record_episode(session_id, "user", user_text)
                _record_episode(session_id, "assistant", question)
                approvals.clear_session(session_id)
                yield _sse("text_chunk", {"text": question})
                yield _sse("done", {})
                return

        semantic = _recall_memory(user_text)
        if semantic:
            context_parts.append(semantic)
            yield _sse(
                "step",
                {
                    "type": "tool_result",
                    "tool": "query_knowledge",
                    "output": semantic[:400],
                    "id": "memory-recall",
                },
            )

        lessons = _recall_lessons(reflector, session_id, user_text)
        if lessons:
            block = "RELEVANT LESSONS (verified cross-task or pending from this task):\n" + "\n".join(
                f"- [{le.get('verification_status', 'pending')}; {le['error_type']}] "
                f"{le['lesson_text']}"
                for le in lessons
            )
            context_parts.append(block)
            yield _sse(
                "step",
                {
                    "type": "tool_result",
                    "tool": "reflect",
                    "output": f"Recalled {len(lessons)} past lesson(s); filtered for relevance.",
                    "id": "lesson-recall",
                },
            )

        recalled_skills = _recall_skills(skills, user_text)
        if recalled_skills:
            skill_block = "VERIFIED REUSABLE WORKFLOWS:\n" + "\n".join(
                f"- For {skill['goal_pattern']}: {' -> '.join(skill['steps'])} "
                f"(verified success rate {skill['success_rate']:.0%})"
                for skill in recalled_skills
            )
            context_parts.append(skill_block)
            yield _sse(
                "step",
                {
                    "type": "tool_result",
                    "tool": "query_skills",
                    "output": f"Recalled {len(recalled_skills)} verified workflow(s).",
                    "id": "skill-recall",
                },
            )

        memory_context = "\n\n".join(context_parts) or None

        # 2. Persist the user turn.
        _record_episode(session_id, "user", user_text)

        # 3. Agentic loop with recalled context + lessons + reflection + confirmation.
        #    `chat_client` is local Ollama or cloud Bedrock per the selected model.
        agent = ToolAgent(
            chat_client,
            executor,
            model=model,
            session_id=session_id,
            memory_context=memory_context,
            on_failure=_make_failure_hook(reflector, session_id),
            confirm_lesson=_make_confirm_hook(reflector, consolidator),
            approved_commands=approved_commands,
            approved_edits=approved_edits,
            approved_creations=approved_creations,
            snapshot=snapshot,
            # The Planner needs a COMPLETION client (.complete()); pass the local
            # get_llm_client one — never `chat_client`, which may be cloud Bedrock —
            # so planning always uses the local completion model.
            planner_llm=planner_llm,
            # Self-Analysis T2 (propose_fixes) drafts diffs with the SAME completion
            # client (not chat_client). It only writes proposals to the report —
            # never edits or applies source.
            self_analysis_llm=planner_llm,
        )
        answer_parts: list[str] = []
        workflow_steps: list[str] = []
        blocked_actions = 0
        verification_evidence: list[str] = []
        communication_notice = (
            alignment.communication_notice() if alignment is not None else ""
        )
        if communication_notice:
            answer_parts.append(communication_notice)
            yield _sse("text_chunk", {"text": communication_notice})

        def record_outcome(outcome: str) -> None:
            """Best-effort development, skill, and curriculum evidence write."""
            try:
                development.record(
                    user_text,
                    outcome,
                    tool_calls=len(workflow_steps),
                    human_interventions=len(req.approval_tokens),
                    blocked_actions=blocked_actions,
                    metadata={"model": model, "task": task},
                )
            except Exception:  # noqa: BLE001 - metrics must never break chat
                pass
            if outcome not in {"verified_success", "verified_failure"}:
                return
            passed = outcome == "verified_success"
            if passed:
                evidence = next(
                    (
                        item
                        for item in reversed(verification_evidence)
                        if item.startswith("[VERIFY PASS]")
                    ),
                    "",
                )
            else:
                evidence = next(
                    (
                        item
                        for item in reversed(verification_evidence)
                        if item.startswith("[VERIFY FAIL]")
                    ),
                    "",
                )
            if workflow_steps:
                try:
                    skills.record_attempt(user_text, workflow_steps, success=passed)
                except Exception:  # noqa: BLE001 - skill learning is best-effort
                    pass
            try:
                curriculum.record_matching(user_text, passed=passed, evidence=evidence)
            except Exception:  # noqa: BLE001 - unmatched/invalid curriculum is harmless
                pass

        for ev in agent.run(chat_messages):
            kind = ev["type"]
            if kind in _STEP_EVENTS:
                if kind == "tool_call":
                    workflow_steps.append(_workflow_step(ev))
                elif kind == "tool_blocked":
                    blocked_actions += 1
                if kind == "tool_result":
                    output = str(ev.get("output", ""))
                    if output.startswith("[VERIFY PASS]") or output.startswith("[VERIFY FAIL]"):
                        verification_evidence.append(output)
                yield _sse("step", ev)
            elif kind == "text":
                answer_parts.append(ev["text"])
                yield _sse("text_chunk", {"text": ev["text"]})
            elif kind == "code":
                yield _sse("code", {"code": ev["code"], "language": ev["language"]})
            elif kind == "error":
                yield _sse("error", {"text": ev["text"]})
            elif kind == "human_required":
                # The agent paused on a YELLOW command. Ask the UI for approval;
                # the turn ends here (no answer recorded) and is replayed once the
                # human authorises the command. Surface the *command* in plain
                # language — never the raw classifier reason, which embeds the
                # matched regex pattern (e.g. "\\bpip\\s+install\\b") and belongs
                # in the audit log, not in a human approval prompt. Shape matches
                # the frontend's pendingAction handler ({commands, explanation}).
                cmd = ev["command"]
                edit = ev.get("edit")
                creation = ev.get("creation")
                if edit is not None:
                    token = approvals.issue("edit", edit, session_id)
                    # An edit_file approval: surface the unified diff + the edit
                    # triple so the UI shows the diff and re-sends it as an
                    # approved edit on resume (a snapshot is taken before writing).
                    payload = {
                        "input": {
                            "edits": [edit],
                            "approvalToken": token,
                            "diff": ev.get("diff", ""),
                            "explanation": (
                                "The agent wants to edit a file. Review the diff "
                                "and approve to apply it. A snapshot is taken first, "
                                "then an available sibling test runs automatically."
                            ),
                        },
                        "text": f"Approval required to apply an edit to {ev.get('filepath', '')}",
                        "requiresApproval": True,
                    }
                elif creation is not None:
                    token = approvals.issue("create", creation, session_id)
                    # A create_file approval: surface the all-additions diff + the
                    # {filepath, content} pair so the UI shows the new file and
                    # re-sends it as an approved creation on resume (a snapshot is
                    # taken before writing, so the new file stays revertible).
                    payload = {
                        "input": {
                            "creations": [creation],
                            "approvalToken": token,
                            "diff": ev.get("diff", ""),
                            "explanation": (
                                "The agent wants to create a new file. Review the "
                                "contents and approve to write it. A snapshot is "
                                "taken first, then an available sibling test runs "
                                "automatically."
                            ),
                        },
                        "text": f"Approval required to create {ev.get('filepath', '')}",
                        "requiresApproval": True,
                    }
                else:
                    token = approvals.issue("command", {"command": cmd}, session_id)
                    payload = {
                        "input": {
                            "commands": [cmd],
                            "approvalToken": token,
                            "explanation": (
                                "The agent wants to run a caution-level command "
                                "(e.g. a package install, git write, or file "
                                "change). Review it and approve to let it run."
                            ),
                        },
                        "text": f"Approval required to run: {cmd}",
                        "requiresApproval": True,
                    }
                try:
                    development.record(
                        user_text,
                        "paused",
                        tool_calls=len(workflow_steps),
                        human_interventions=len(req.approval_tokens),
                        blocked_actions=blocked_actions,
                        metadata={"model": model, "task": task},
                    )
                except Exception:  # noqa: BLE001 - metrics must never break approval
                    pass
                yield _sse("human_required", payload)
            elif kind == "done":
                # 4. Persist the answer (L2) and consolidate the turn into L3.
                answer = "".join(answer_parts)
                _record_episode(session_id, "assistant", answer)
                _index_turn(indexer, user_text, answer)
                # The turn's outcome is its FINAL verification verdict ("last
                # evidence wins"): the loop's whole design is verify -> reflect
                # -> fix, so a turn that fails, self-corrects, and ends green IS
                # a verified success — under fail-dominant classification the
                # agent could never bank a success on any task that needed its
                # own verifier feedback (operator decision 2026-06-11).
                # Follow-up: make this per-target once evidence carries the
                # verified file/command, so a final PASS on one target cannot
                # mask an earlier unresolved FAIL on another.
                if not verification_evidence:
                    record_outcome("unverified")
                elif verification_evidence[-1].startswith("[VERIFY PASS]"):
                    record_outcome("verified_success")
                else:
                    record_outcome("verified_failure")
                approvals.clear_session(session_id)
                yield _sse("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/terminal")
def terminal(
    req: TerminalRequest,
    executor: Executor = Depends(get_executor),
    approvals: ApprovalStore = Depends(get_approval_store),
) -> dict[str, Any]:
    """Run a UI-terminal command through the security gateway + sandbox.

    Returns the front-end terminal's ``{output, isError}`` shape. The command is
    classified and gated exactly like an agent action: RED is blocked, YELLOW is
    reported as needing approval, and only GREEN runs in the scope-locked
    sandbox. Every outcome is audited by the executor.
    """
    result = executor.execute(req.command, session_id=req.session_id)

    if result.status == "OK":
        output = (result.stdout or "") + (result.stderr or "")
        return {
            "output": output.strip() or "(no output)",
            "isError": bool(result.exit_code),
        }
    if result.status == "REQUIRE_APPROVAL":
        if not req.session_id:
            raise HTTPException(
                status_code=400,
                detail="sessionId is required to approve a YELLOW command",
            )
        token = approvals.issue("command", {"command": req.command}, req.session_id)
        return {
            "output": f"[APPROVAL REQUIRED] {result.reason}",
            "isError": False,
            "requiresApproval": True,
            "approvalToken": token,
            "command": req.command,
        }
    # BLOCKED / TIMEOUT / ERROR
    return {"output": f"[{result.status}] {result.reason}", "isError": True}
