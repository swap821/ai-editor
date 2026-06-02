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

import json
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Iterator, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import aios
from aios import config
from aios.agents.reflection_agent import ReflectionAgent, ReflectionError
from aios.agents.rollback_engine import RollbackEngine, RollbackError
from aios.agents.tool_agent import ToolAgent
from aios.core.executor import Executor
from aios.core.llm import LLMClient, OllamaClient
from aios.core.planner import Planner, PlannerError
from aios.memory.db import init_memory_db
from aios.memory.episodic import EpisodicMemory
from aios.memory.retrieval import hybrid_search
from aios.memory.semantic import SemanticMemory
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

# Browser clients (the Vite front-end) run on a different origin, so the API
# must opt them in explicitly. Origins come from config (env-overridable).
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.API_CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


def get_executor() -> Executor:
    """Provide the default sandboxed executor. Overridden in tests."""
    return Executor()


def get_rollback_engine() -> RollbackEngine:
    """Provide the default sandbox rollback engine. Overridden in tests."""
    return RollbackEngine()


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


class GenerateRequest(BaseModel):
    """Body for ``/api/generate`` — the conversational chat endpoint.

    ``messages`` is the front-end's running history in the shape
    ``[{"role": "user"|"assistant", "content": [{"text": "..."}]}]``.
    ``model_id`` is the UI's selected model id (e.g. ``ollama.llama3.2:3b``);
    the ``ollama.`` prefix is stripped, and any non-local id falls back to the
    configured default local model.
    """

    messages: list[dict] = Field(default_factory=list)
    model_id: Optional[str] = Field(None, alias="modelId")
    session_id: str = Field("ui-session", alias="sessionId")

    model_config = {"populate_by_name": True}


class TerminalRequest(BaseModel):
    """Body for ``/api/terminal`` — a single shell command from the UI terminal."""

    command: str = Field(..., description="Command typed into the UI terminal.")
    session_id: Optional[str] = Field(None, alias="sessionId")

    model_config = {"populate_by_name": True}


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


# --------------------------------------------------------------------------- #
# Front-end bridge: model discovery, conversational chat, UI terminal
# These three endpoints back the React UI's main surfaces. The ``/api/v1/*``
# routes above expose individual subsystems; these compose them for the UI.
# --------------------------------------------------------------------------- #
@app.get("/api/v1/models/local")
def models_local(client: OllamaClient = Depends(get_ollama_client)) -> dict:
    """List models installed in the local Ollama engine (for the model picker)."""
    return client.list_models()


def _resolve_local_model(model_id: Optional[str]) -> str:
    """Map a UI model id to a local Ollama tag (``ollama.x`` -> ``x``).

    Non-local ids (or none) fall back to the configured default local model, so
    the local-first backend always has something to run.
    """
    if model_id and model_id.startswith("ollama."):
        return model_id[len("ollama.") :]
    return config.LLM_MODEL


def _to_chat_messages(messages: list[dict]) -> list[dict]:
    """Flatten the UI history (``content`` arrays) into Ollama chat messages."""
    out: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = " ".join(
                c.get("text", "") for c in content if isinstance(c, dict)
            ).strip()
        else:
            text = ""
        if text:
            out.append({"role": role, "content": text})
    return out


def _sse(event: str, data: dict) -> str:
    """Format one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


#: Agent event type -> SSE event name the front-end's stream reader understands.
_STEP_EVENTS = {"tool_call", "tool_result", "tool_blocked"}

#: Episodic (L2) memory facade — the durable, chronological record of every turn.
_EPISODIC = EpisodicMemory()


def _latest_user(chat_messages: list[dict]) -> str:
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
    lines = "\n".join(f"- {hit.text}" for hit in hits)
    return (
        "RELEVANT PROJECT MEMORY (recalled from past sessions; use if helpful):\n"
        f"{lines}"
    )


def _record_episode(session_id: str, role: str, content: str) -> None:
    """Persist one turn to L2 episodic memory. Best-effort; never fatal."""
    if not content or not content.strip():
        return
    try:
        _EPISODIC.record(session_id, role, content)
    except Exception:  # noqa: BLE001 - persistence must not break the chat
        pass


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
        indexer.add(f"User: {user_text}\nAssistant: {answer}")
    except Exception:  # noqa: BLE001 - indexing must not break the chat
        pass


def _make_failure_hook(reflector: Optional[ReflectionAgent], session_id: str):
    """Build the agent's on-failure hook from a reflection agent (or ``None``).

    The hook records a structured lesson in the Mistake pool and returns a small
    summary for the UI; any failure to reflect is swallowed so a learning step
    never breaks the chat.
    """
    if reflector is None:
        return None

    def hook(command: str, error_output: str) -> Optional[dict]:
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


@app.post("/api/generate")
def generate(
    req: GenerateRequest,
    client: OllamaClient = Depends(get_ollama_client),
    executor: Executor = Depends(get_executor),
    indexer: Optional[SemanticMemory] = Depends(get_semantic_indexer),
    reflector: Optional[ReflectionAgent] = Depends(get_reflection_agent),
) -> StreamingResponse:
    """Run the agentic tool loop with memory, streaming it to the UI as SSE.

    Pipeline per turn (blueprint stages 4 -> ... -> consolidation):
      1. Recall relevant semantic memories and inject them into the agent's
         context (surfaced as a ``query_knowledge`` step when anything is found).
      2. Persist the user turn to L2 episodic memory.
      3. Run the agentic tool loop (``read_file``/``read_directory``/
         ``execute_terminal``, all gated + audited), forwarding tool activity as
         ``step`` frames, the answer as ``text_chunk`` frames, any code as a
         ``code`` frame, and finishing with ``done`` (or ``error``).
      4. Persist the assistant's final answer to L2 episodic memory and embed the
         completed turn into L3 semantic memory (self-reinforcing recall).
    """
    chat_messages = _to_chat_messages(req.messages)
    model = _resolve_local_model(req.model_id)
    session_id = req.session_id
    user_text = _latest_user(chat_messages)

    def event_stream() -> Iterator[str]:
        if not user_text:
            yield _sse("error", {"text": "No user message provided."})
            return

        # 1. Recall (best-effort) + 2. persist the user turn.
        memory_context = _recall_memory(user_text)
        if memory_context:
            yield _sse(
                "step",
                {
                    "type": "tool_result",
                    "tool": "query_knowledge",
                    "output": memory_context[:400],
                    "id": "memory-recall",
                },
            )
        _record_episode(session_id, "user", user_text)

        # 3. Agentic loop with the recalled context + reflection hook.
        agent = ToolAgent(
            client,
            executor,
            model=model,
            session_id=session_id,
            memory_context=memory_context,
            on_failure=_make_failure_hook(reflector, session_id),
        )
        answer_parts: list[str] = []
        for ev in agent.run(chat_messages):
            kind = ev["type"]
            if kind in _STEP_EVENTS:
                yield _sse("step", ev)
            elif kind == "text":
                answer_parts.append(ev["text"])
                yield _sse("text_chunk", {"text": ev["text"]})
            elif kind == "code":
                yield _sse("code", {"code": ev["code"], "language": ev["language"]})
            elif kind == "error":
                yield _sse("error", {"text": ev["text"]})
            elif kind == "done":
                # 4. Persist the answer (L2) and consolidate the turn into L3.
                answer = "".join(answer_parts)
                _record_episode(session_id, "assistant", answer)
                _index_turn(indexer, user_text, answer)
                yield _sse("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/terminal")
def terminal(
    req: TerminalRequest, executor: Executor = Depends(get_executor)
) -> dict:
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
        return {
            "output": f"[APPROVAL REQUIRED] {result.reason}",
            "isError": False,
            "requiresApproval": True,
        }
    # BLOCKED / TIMEOUT / ERROR
    return {"output": f"[{result.status}] {result.reason}", "isError": True}
