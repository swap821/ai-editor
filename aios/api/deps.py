"""Shared FastAPI dependency providers for the API layer.

Extracted from ``aios/api/main.py`` (monolith split, 2026-07-06) so that route
modules under ``aios/api/routes/`` can depend on providers WITHOUT importing
``main`` (no import cycle) and WITHOUT redefining local proxy providers — the
proxy pattern silently breaks ``app.dependency_overrides`` because overrides
are keyed by function identity (the council-router seam documented in the
deep-audit report).

``main.py`` re-imports every name below, so the long-standing test idiom
``from aios.api.main import get_X`` keeps resolving to the SAME function
object and every existing dependency override remains valid.

Only STATELESS providers (fresh store constructors) and the self-contained
lazy cloud-client singletons live here. Providers entangled with ``main``'s
process state (approval store, session manager, executor/rate-limiter,
self-apply, edit snapshots, the memory compactor's singleton cluster) stay in
``main.py``.
"""
from __future__ import annotations

import threading
from typing import Any, Optional

from fastapi import Depends

from aios import config
from aios.agents.reflection_agent import ReflectionAgent
from aios.agents.swarm_patterns import SwarmPatternMemory
from aios.core.autonomy import AutonomyLedger
from aios.core.alignment import AlignmentInterpreter
from aios.core.bedrock import BedrockClient
from aios.core.cerebellum import Cerebellum
from aios.core.gemini import GeminiClient
from aios.core.llm import LLMClient, LLMError, OllamaClient
from aios.core.native_planner import NativePlanner
from aios.memory.alignment_evaluation import AlignmentEvaluationStore
from aios.memory.consolidation import MemoryConsolidator
from aios.memory.conversation import ConversationStateStore
from aios.memory.curriculum import CurriculumManager
from aios.memory.development import DevelopmentTracker
from aios.memory.facts import SemanticFacts
from aios.memory.mistake import MistakeMemory
from aios.memory.semantic import SemanticMemory
from aios.memory.skills import SkillMemory

#: Lazy cloud-client singletons — built on first use, reused across requests.
_bedrock_client: Optional[BedrockClient] = None
_gemini_client: Optional[GeminiClient] = None
_openai_client: Optional[Any] = None
_anthropic_client: Optional[Any] = None
_bedrock_lock = threading.Lock()
_gemini_lock = threading.Lock()
_openai_lock = threading.Lock()
_anthropic_lock = threading.Lock()


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

    Returns ``None`` unless Bedrock is opted in (region + model set) *and* boto3
    is importable — so the agent transparently stays on local inference when the
    cloud isn't set up. Overridden in tests with a fake.

    The client is built lazily and reused across requests; enablement is checked
    fresh each call (mirrors ``_router_policy``).
    """
    global _bedrock_client
    if not (config.BEDROCK_REGION and config.BEDROCK_MODEL):
        return None
    if _bedrock_client is not None:
        return _bedrock_client
    with _bedrock_lock:
        if _bedrock_client is not None:
            return _bedrock_client
        try:
            _bedrock_client = BedrockClient()
        except LLMError:
            return None
    return _bedrock_client


def get_gemini_client() -> Optional[GeminiClient]:
    """Provide the Google Gemini (Vertex AI) chat client, or ``None`` when unset.

    Returns ``None`` unless Gemini is opted in (a GCP project is set) *and* the
    ``google-genai`` SDK is importable — so the agent transparently stays on
    local/Bedrock inference when Gemini isn't configured. Auth is the laptop's
    ``gcloud`` ADC; this never touches a key on disk. Overridden in tests.

    The client is built lazily and reused across requests; enablement is checked
    fresh each call (mirrors ``_router_policy``).
    """
    global _gemini_client
    if not (config.GEMINI_PROJECT and config.GEMINI_MODEL):
        return None
    if _gemini_client is not None:
        return _gemini_client
    with _gemini_lock:
        if _gemini_client is not None:
            return _gemini_client
        try:
            _gemini_client = GeminiClient()
        except LLMError:
            return None
    return _gemini_client


def get_openai_client() -> Optional[Any]:
    """Provide the OpenAI-compatible chat client, or ``None`` when unconfigured."""
    global _openai_client
    if not config.OPENAI_ENABLED:
        return None
    if _openai_client is not None:
        return _openai_client
    with _openai_lock:
        if _openai_client is not None:
            return _openai_client
        from aios.core.openai_compat import OpenAICompatClient
        _openai_client = OpenAICompatClient()
    return _openai_client


def get_anthropic_client() -> Optional[Any]:
    """Provide the Anthropic direct chat client, or ``None`` when unconfigured."""
    global _anthropic_client
    if not config.ANTHROPIC_ENABLED:
        return None
    if _anthropic_client is not None:
        return _anthropic_client
    with _anthropic_lock:
        if _anthropic_client is not None:
            return _anthropic_client
        from aios.core.anthropic_direct import AnthropicDirectClient
        _anthropic_client = AnthropicDirectClient()
    return _anthropic_client


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


def get_swarm_pattern_memory() -> SwarmPatternMemory:
    """Provide the ant-colony swarm's decomposition-pattern memory."""
    return SwarmPatternMemory()


def get_semantic_facts() -> SemanticFacts:
    """Provide the human-approved personalization facts store (REAL only).

    Reads the ``semantic_facts`` table (human-gated writes); returns an empty
    list when no facts exist, so the conversational endpoint stays honest —
    personalization is dormant, never fabricated, when nothing is known. Cheap
    and stateless (opens a fresh connection per call). Overridden in tests.
    """
    return SemanticFacts()


def get_development_tracker(
    facts: SemanticFacts = Depends(get_semantic_facts),
) -> DevelopmentTracker:
    """Provide the evidence-backed developmental metrics store."""
    return DevelopmentTracker(facts=facts)


def get_autonomy() -> AutonomyLedger:
    """Provide the earned-autonomy ledger (opt-in; off => never grants autonomy)."""
    return AutonomyLedger()


def get_cerebellum() -> Cerebellum:
    """Provide the compiled-experience engine (sovereignty S1)."""
    cb = Cerebellum()
    cb.try_compile_all()
    return cb


def get_skill_memory(
    cerebellum: Cerebellum = Depends(get_cerebellum),
    facts: SemanticFacts = Depends(get_semantic_facts),
) -> SkillMemory:
    """Provide verification-backed procedural skill memory.

    Wired to the same request-scoped cerebellum instance so that a skill's
    promotion to 'verified' (or demotion back to 'candidate') during this
    request immediately compiles (or decompiles) the matching playbook —
    the sovereignty engine stays in sync with skill trust status. The facts
    store enables S2 cross-store ingestion on skill promotion.
    """
    return SkillMemory(cerebellum=cerebellum, facts=facts)


def get_mistake_memory(
    facts: SemanticFacts = Depends(get_semantic_facts),
) -> MistakeMemory:
    """Provide mistake memory with knowledge graph ingestion wiring."""
    return MistakeMemory(facts=facts)


def get_native_planner(
    skills: SkillMemory = Depends(get_skill_memory),
    patterns: SwarmPatternMemory = Depends(get_swarm_pattern_memory),
    facts: SemanticFacts = Depends(get_semantic_facts),
) -> NativePlanner:
    """Provide the sovereignty S3 native symbolic planner."""
    return NativePlanner(skills=skills, patterns=patterns, facts=facts)


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


__all__ = [
    "get_llm_client",
    "get_ollama_client",
    "get_bedrock_client",
    "get_gemini_client",
    "get_openai_client",
    "get_anthropic_client",
    "get_semantic_indexer",
    "get_reflection_agent",
    "get_swarm_pattern_memory",
    "get_semantic_facts",
    "get_development_tracker",
    "get_autonomy",
    "get_cerebellum",
    "get_skill_memory",
    "get_mistake_memory",
    "get_native_planner",
    "get_curriculum_manager",
    "get_memory_consolidator",
    "get_conversation_state_store",
    "get_alignment_evaluation_store",
    "get_alignment_interpreter",
]
