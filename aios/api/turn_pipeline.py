"""Turn-pipeline helpers for ``/api/generate`` — memory recall, CRAG,
confidence calibration, and reflection hooks.

Extracted from ``aios/api/main.py`` (structure audit, 2026-07-10): these ~20
functions preceded the 1,030-line ``generate()`` handler and accounted for a
large share of that file's size, unlike every other domain (council,
security, memory, voice, sovereignty, ...) which was already split into
``aios/api/routes/*.py``. Lives in ``aios/api/`` rather than ``aios/core/``
(the audit's suggested location) because several of these functions call the
client-provider factories in ``aios/api/deps.py`` (``get_gemini_client``,
``get_bedrock_client``, ``get_ollama_client``) directly -- moving them into
``aios/core/`` would make core/ depend on api/, a new layering inversion of
exactly the kind this extraction is meant to fix, not a smaller one.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from aios import config
from aios.agents.reflection_agent import ReflectionAgent, ReflectionError
from aios.api.deps import (
    get_bedrock_client,
    get_gemini_client,
    get_human_state_hypothesis_store,
    get_memory_authority,
    get_ollama_client,
)
from aios.core.websearch import web_search
from aios.logging_config import get_logger
from aios.memory.consolidation import MemoryConsolidator
from aios.memory.crag import (
    CragAction,
    evaluate_retrieval,
    external_retrieve,
    refine_context,
)
from aios.memory.development import DevelopmentTracker
from aios.memory.facts import SemanticFacts
from aios.memory.mistake import MistakeMemory
from aios.memory.retrieval import hybrid_search
from aios.domain.memory import HumanStateHypothesis, MemoryRecallContext
from aios.memory.self_model import render as render_self_model, synthesize_self_model
from aios.memory.semantic import SemanticMemory
from aios.memory.skills import SkillMemory
from aios.security.secret_scanner import scan_and_redact

logger = get_logger(__name__)


def _authority_owns(authority: Any | None, name: str, candidate: Any) -> bool:
    """Use authority reads only for the authority's canonical store."""
    owns_store = getattr(authority, "owns_store", None)
    if not callable(owns_store):
        # Lightweight authority fakes predate the ownership API; retain their
        # explicit authority behavior while real authorities fail closed below.
        return authority is not None
    try:
        return bool(owns_store(name, candidate))
    except Exception:  # noqa: BLE001 - advisory recall must remain available
        return False


def _operator_facts_block(
    facts: SemanticFacts,
    subject: str = "operator",
    *,
    authority: Any | None = None,
) -> Optional[str]:
    """Build a REAL-facts-only personalization block, or ``None`` when dormant.

    Reads human-approved active facts for *subject* (newest-first) and renders
    them as ``subject predicate object`` triples. Honesty law: when there are no
    facts the block is ``None`` (personalization stays dormant — never fabricated).
    Best-effort: any store error degrades to ``None`` rather than breaking chat.
    """
    try:
        rows = (
            authority.facts_for(subject)
            if _authority_owns(authority, "facts", facts)
            else facts.facts_for(subject)
        )
    except Exception as exc:  # noqa: BLE001 - personalization is an enhancement, never fatal
        logger.warning("Failed to load operator facts block", exc_info=exc)
        return None
    if not rows:
        return None
    triples = "\n".join(
        f"- {row['subject']} {row['predicate']} {row['object']}" for row in rows
    )
    return (
        "KNOWN FACTS ABOUT THE OPERATOR (human-approved; use to personalize, "
        "never invent beyond these):\n" + triples
    )


def _recall_self_model(
    development: DevelopmentTracker,
    mistakes: MistakeMemory,
    *,
    authority: Any | None = None,
) -> Optional[str]:
    """Synthesize the grounded, verified-only autobiographical self-model paragraph.

    Deterministic and fail-closed: with too little verified evidence the model is
    empty and nothing is injected (the organism never invents a self). Advisory —
    a failure degrades to ``None`` and never blocks the turn.
    """
    try:
        text = (
            authority.self_model()
            if _authority_owns(authority, "development", development)
            and _authority_owns(authority, "lessons", mistakes)
            else render_self_model(synthesize_self_model(development, mistakes))
        )
    except Exception as exc:  # noqa: BLE001 - the self-model is advisory recall
        logger.warning("Failed to synthesize self-model", exc_info=exc)
        return None
    return text or None


@dataclass
class FactRecallResult:
    """Rich result from fact recall: text for the prompt + inference metadata for SSE."""

    text: str
    inferences: list[dict] = field(default_factory=list)


def _recall_facts(
    facts: SemanticFacts,
    user_text: str,
    *,
    authority: Any | None = None,
) -> Optional[FactRecallResult]:
    """Recall relevant semantic facts (+ single-hop neighbors) for the forge.

    Returns a ``FactRecallResult`` with both the prompt-ready text AND the raw
    inference metadata so the generator can emit ``graph_inference`` /
    ``graph_horizon`` SSE events for the frontend.
    """
    user_text = (user_text or "").strip()
    if not user_text:
        return None
    authority_bound = _authority_owns(authority, "facts", facts)
    try:
        matched = (
            authority.facts_search(user_text)
            if authority_bound
            else facts.search(user_text)
        )
    except Exception as exc:  # noqa: BLE001 - recall is advisory
        logger.warning("Failed to search semantic facts", exc_info=exc)
        return None
    if not matched:
        return None

    # Collect subjects/objects to expand with single-hop neighbors.
    nodes: set[str] = set()
    for row in matched:
        nodes.add(str(row["subject"]))
        nodes.add(str(row["object"]))

    expanded: set[tuple[str, str, str]] = set()
    for row in matched:
        expanded.add((str(row["subject"]), str(row["predicate"]), str(row["object"])))
    for node in nodes:
        try:
            neighbor_rows = (
                authority.facts_neighbors(node)
                if authority_bound
                else facts.neighbors(node)
            )
            for row in neighbor_rows:
                expanded.add(
                    (str(row["subject"]), str(row["predicate"]), str(row["object"]))
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load neighbors for %s", node, exc_info=exc)

    if not expanded:
        return None
    triples = "\n".join(f"- {s} {p} {o}" for s, p, o in sorted(expanded))

    # S2: if any matched entity has deeper associations, include the
    # highest-confidence inference chain as structured context.
    inference_lines: list[str] = []
    inference_events: list[dict] = []
    for node in list(nodes)[:5]:
        try:
            edges = (
                authority.facts_traverse_weighted(node)
                if authority_bound
                else facts.traverse_weighted(node, max_depth=3, min_path_confidence=0.3)
            )
            if edges:
                from aios.core.inference import infer

                result = infer(user_text, edges, min_confidence=0.3)
                if result is not None and result.answer:
                    inference_lines.append(
                        f"  Inference ({result.combined_confidence:.0%} confidence): "
                        f"{result.answer}"
                    )
                    inference_events.append(
                        {
                            "query": result.query,
                            "chain": [
                                {
                                    "subject": s.subject,
                                    "predicate": s.predicate,
                                    "object": s.object,
                                    "depth": s.depth,
                                    "confidence": s.confidence,
                                }
                                for s in result.chain
                            ],
                            "combined_confidence": result.combined_confidence,
                            "answer": result.answer,
                            "reached_horizon": result.reached_horizon,
                            "entity": node,
                        }
                    )
        except Exception:
            logger.warning("traverse_weighted failed for %s", node, exc_info=True)

    if inference_lines:
        triples += "\n\nINFERRED ASSOCIATIONS (confidence-weighted, use cautiously):\n"
        triples += "\n".join(inference_lines[:3])

    text = (
        "RELEVANT APPROVED FACTS (use these; do not invent beyond this graph):\n"
        + triples
    )
    return FactRecallResult(text=text, inferences=inference_events)


def _latest_user(chat_messages: list[dict[str, Any]]) -> str:
    """Return the most recent user message text (already flattened to a string)."""
    for msg in reversed(chat_messages):
        if msg["role"] == "user":
            return msg["content"]
    return ""


_MEM_TRUSTED_HEADER = (
    "VERIFIED TRUSTED MEMORY (still prefer current tool evidence when available):\n"
)
_MEM_UNVERIFIED_HEADER = (
    "UNVERIFIED PRIOR CHAT MEMORY (may be stale or wrong; use only as a lead, "
    "never as evidence, and verify against tools/files before acting):\n"
)
_MEM_EXTERNAL_HEADER = (
    "EXTERNAL KNOWLEDGE (fetched on demand because local memory was insufficient; "
    "GENERATED/UNVERIFIED — treat as a lead only, verify against tools/files before "
    "acting):\n"
)


def _crag_cloud_source(query: str) -> list[str]:
    """CRAG external source A — the configured cloud model as a broader knowledge
    base. Returns ``[]`` when no cloud provider is configured. The cloud client
    secret-scrubs the message internally before transmission (PrivacyFilter)."""
    client = get_gemini_client() or get_bedrock_client()
    if client is None:
        return []
    prompt = (
        "Answer the question concisely and factually using only what you are "
        "confident about. If you do not know, say so rather than guessing.\n\n"
        f"Question: {query}"
    )
    try:
        response = client.chat([{"role": "user", "content": prompt}], tools=None)
    except Exception as exc:  # noqa: BLE001 - a cloud miss must not break recall
        logger.warning("CRAG cloud source failed", exc_info=exc)
        return []
    text = str((response or {}).get("content", "")).strip()
    return [text] if text else []


def _crag_web_source(query: str) -> list[str]:
    """CRAG external source B — a configurable web-search provider. Inert (``[]``)
    until AIOS_CRAG_SEARCH_ENDPOINT + AIOS_CRAG_SEARCH_API_KEY are set."""
    return web_search(
        query,
        endpoint=config.CRAG_SEARCH_ENDPOINT,
        api_key=config.CRAG_SEARCH_API_KEY,
    )


def _crag_document_source(query: str) -> list[str]:
    """Retrieve relevant chunks from user-uploaded knowledge documents."""
    from aios.memory.doc_ingest import DocumentIngestor

    ingestor = DocumentIngestor()
    return ingestor.search_chunks(query, limit=5)


def _crag_external_sources() -> list:
    """The enabled external corrective sources (each independently opt-in)."""
    sources: list = []
    if config.CRAG_DOCUMENTS:
        sources.append(_crag_document_source)
    if config.CRAG_CLOUD:
        sources.append(_crag_cloud_source)
    if config.CRAG_WEBSEARCH:
        sources.append(_crag_web_source)
    return sources


_CRAG_JUDGE_NUMBER = re.compile(r"\d*\.?\d+")


def _crag_llm_judge(query: str, passage: str) -> float:
    """A local-model relevance score in [0,1] for one (query, passage) pair.

    Used as the evaluator's optional caution-only clamp (it can only *lower* a hit's
    deterministic confidence — see ``evaluate_retrieval``). Raises on an unparseable
    reply or a model error so the evaluator ignores it and the deterministic score
    stands (never silently fabricates caution)."""
    response = get_ollama_client().chat(
        [
            {
                "role": "user",
                "content": (
                    "Rate how RELEVANT the passage is to answering the query, from "
                    "0.0 (irrelevant) to 1.0 (directly answers it). Reply with ONLY "
                    f"the number.\n\nQuery: {query}\nPassage: {passage}"
                ),
            }
        ],
        tools=None,
        model=config.LLM_MODEL,
    )
    text = str((response or {}).get("content", ""))
    match = _CRAG_JUDGE_NUMBER.search(text)
    if not match:
        raise ValueError(f"CRAG judge returned no score: {text!r}")
    return max(0.0, min(1.0, float(match.group(0))))


def _recall_memory(
    query: str, top_k: int = 3, *, authority: Any | None = None
) -> Optional[str]:
    """Best-effort hybrid recall of relevant semantic memories for *query*.

    Returns a prompt-ready knowledge block, or ``None`` when there is nothing
    relevant (or the memory subsystem is unavailable). ``hybrid_search``
    short-circuits to empty without loading the embedding model when the
    semantic index is empty, so this is a cheap no-op on a fresh system.

    When Corrective-RAG is enabled (``AIOS_CRAG``, default off) the retrieval is
    gated and refined before it reaches the prompt: a low-confidence (INCORRECT)
    recall is DROPPED rather than injected — the core anti-hallucination win — and
    the surviving hits are decompose-then-recomposed down to their golden strips.
    Trust labels are preserved (CRAG judges *relevance*; verified/unverified judges
    *trust*). CRAG fails soft to the unrefined block on any error.
    """
    try:
        memory_authority = authority or get_memory_authority()
        hits = memory_authority.recall(
            query,
            MemoryRecallContext(
                memory_types=("semantic",),
                limit=top_k,
                include_unverified=True,
            ),
            retrieval_fn=hybrid_search,
        )
    except Exception as exc:  # noqa: BLE001 - recall is an enhancement, never fatal
        logger.warning("Memory recall failed; continuing without context", exc_info=exc)
        return None
    if not hits:
        return None
    trusted = [
        hit
        for hit in hits
        if getattr(hit, "verification_status", "unverified") == "verified"
    ]
    unverified = [hit for hit in hits if hit not in trusted]

    if config.CRAG:
        try:
            verdict = evaluate_retrieval(
                query,
                hits,
                upper=config.CRAG_UPPER,
                lower=config.CRAG_LOWER,
                judge=_crag_llm_judge if config.CRAG_LLM_JUDGE else None,
            )
            # Slice 3: on a low-confidence local recall, gather refined external
            # knowledge (privacy-gated, default off, only when a source is enabled).
            external_body = ""
            if config.CRAG_EXTERNAL and verdict.action in (
                CragAction.INCORRECT,
                CragAction.AMBIGUOUS,
            ):
                try:
                    ext_docs = external_retrieve(query, _crag_external_sources())
                    external_body = refine_context(query, ext_docs) if ext_docs else ""
                except Exception as exc:  # noqa: BLE001 - external is additive
                    logger.warning("CRAG external retrieval failed", exc_info=exc)
                    external_body = ""

            if verdict.action is CragAction.INCORRECT:
                # Local retrieval is junk — never inject it. Use external if we got
                # any; otherwise no memory context (the anti-hallucination win).
                return (_MEM_EXTERNAL_HEADER + external_body) if external_body else None

            trusted_body = (
                refine_context(query, [h.text for h in trusted]) if trusted else ""
            )
            unverified_body = (
                refine_context(query, [h.text for h in unverified])
                if unverified
                else ""
            )
            crag_blocks: list[str] = []
            if trusted_body:
                crag_blocks.append(_MEM_TRUSTED_HEADER + trusted_body)
            if unverified_body:
                crag_blocks.append(_MEM_UNVERIFIED_HEADER + unverified_body)
            if external_body:  # AMBIGUOUS supplemented with external knowledge
                crag_blocks.append(_MEM_EXTERNAL_HEADER + external_body)
            if crag_blocks:
                return "\n\n".join(crag_blocks)
            # Refinement emptied everything → fall through to the legacy block so a
            # non-empty retrieval is never silently blanked.
        except Exception as exc:  # noqa: BLE001 - CRAG is additive; never break recall
            logger.warning("CRAG recall failed; using unrefined memory", exc_info=exc)

    blocks: list[str] = []
    if trusted:
        blocks.append(
            _MEM_TRUSTED_HEADER + "\n".join(f"- {hit.text}" for hit in trusted)
        )
    if unverified:
        blocks.append(
            _MEM_UNVERIFIED_HEADER + "\n".join(f"- {hit.text}" for hit in unverified)
        )
    return "\n\n".join(blocks)


def _record_episode(
    session_id: str, role: str, content: str, *, authority: Any | None = None
) -> None:
    """Persist one turn to L2 episodic memory. Best-effort; never fatal."""
    if not content or not content.strip():
        return
    try:
        memory_authority = authority or get_memory_authority()
        memory_authority.record_episodic(
            session_id, role, scan_and_redact(content).scrubbed
        )
    except Exception as exc:  # noqa: BLE001 - persistence must not break the chat
        logger.warning("Failed to record episodic memory", exc_info=exc)


def _record_human_state(
    session_id: str,
    turn_id: str,
    hypothesis: HumanStateHypothesis,
    *,
    store: Any | None = None,
) -> None:
    """Persist organ 30's per-turn human-state hypothesis. Best-effort;
    never fatal -- a store failure must never break the chat turn whose
    classification already happened and was already streamed to the UI."""
    try:
        target = store or get_human_state_hypothesis_store()
        target.save(session_id, turn_id, hypothesis)
    except Exception as exc:  # noqa: BLE001 - persistence must not break the chat
        logger.warning("Failed to record human state hypothesis", exc_info=exc)


def _recall_lessons(
    reflector: Optional[ReflectionAgent],
    session_id: str,
    query: str,
    limit: int = 5,
    *,
    authority: Any | None = None,
) -> list[dict[str, Any]]:
    """Best-effort recall of pending same-task and verified cross-task lessons.

    Carries lessons learned in earlier turns into the current one so the agent
    reasons with them. Recalled pending lessons remain advisory. Never fatal.
    """
    if isinstance(reflector, ReflectionAgent) and _authority_owns(
        authority, "lessons", reflector.mistakes
    ):
        try:
            return authority.recall_lessons(query, session_id, limit)
        except Exception as exc:  # noqa: BLE001 - lesson recall is advisory
            logger.warning("Failed to recall lessons through authority", exc_info=exc)
            return []
    if reflector is None:
        return []
    try:
        recall_relevant = getattr(reflector, "recall_relevant", None)
        if callable(recall_relevant):
            return recall_relevant(query, session_id, limit)
        return reflector.recall_pending(session_id, limit)
    except Exception as exc:  # noqa: BLE001 - lesson recall is an enhancement, never fatal
        logger.warning("Failed to recall lessons", exc_info=exc)
        return []


def _recall_pending_commands(
    reflector: Optional[ReflectionAgent], session_id: str
) -> list[tuple[int, str]]:
    """Best-effort ``(mistake_id, failed_command)`` for this session's pending
    lessons, used to seed the agent's fail->confirm tracker so a lesson recorded
    before an approval pause is promoted when its exact command later succeeds in
    the replayed continuation. Never fatal."""
    if reflector is None:
        return []
    try:
        pairs = getattr(reflector, "pending_command_pairs", None)
        return pairs(session_id) if callable(pairs) else []
    except Exception as exc:  # noqa: BLE001 - a tracking seed is an enhancement, never fatal
        logger.warning("Failed to recall pending lesson commands", exc_info=exc)
        return []


def _recall_skills(
    skills: SkillMemory,
    query: str,
    limit: int = 3,
    *,
    authority: Any | None = None,
) -> list[dict[str, Any]]:
    """Best-effort recall of reusable workflows backed by repeated verification."""
    try:
        return (
            authority.recall_skills(query, limit)
            if _authority_owns(authority, "skills", skills)
            else skills.relevant_verified(query, limit)
        )
    except Exception as exc:  # noqa: BLE001 - skill recall is an enhancement, never fatal
        logger.warning("Failed to recall verified skills", exc_info=exc)
        return []


def _verify_target_keys(command: str) -> list[str]:
    """Classification keys for one verification command.

    The same file is legitimately verified through different command spellings
    within one turn (the forced auto-verify vs the model's own pytest call), so a
    file key is the normalized ``.py`` token WITH its directory kept.
    Keeping the directory is load-bearing: two different files that share a
    basename (``a/test_w.py`` vs ``b/test_w.py``) must NOT collide, or a later
    sibling PASS would overwrite (mask) an earlier FAIL/weak target in the
    authoritative per-target maps and launder the turn's verdict + strength.

    Multi-file commands return one key per file. A failed ``pytest a.py b.py``
    therefore marks both targets unresolved; later single-file passes can clear
    each target independently, but a PASS on only ``a.py`` cannot mask ``b.py``.
    A suite-wide verify with no file token keys on the whole command — a
    whole-suite FAIL must be resolved by a whole-suite PASS of that same command.
    """
    keys: list[str] = []
    seen: set[str] = set()
    for raw in command.replace('"', " ").replace("'", " ").split():
        token = raw.replace("\\", "/").lower()
        if token.endswith(".py"):
            norm = token
            while norm.startswith("./"):
                norm = norm[2:]
            if norm and norm not in seen:
                seen.add(norm)
                keys.append(norm)
    return keys or [command.strip().lower() or "unattributed"]


def _verify_target_key(command: str) -> str:
    """Backward-compatible single-target helper for older tests/callers."""
    return _verify_target_keys(command)[0]


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
    indexer: Optional[SemanticMemory],
    user_text: str,
    answer: str,
    *,
    authority: Any | None = None,
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
        if authority is not None:
            authority.record_semantic_chat(clean, indexer=indexer)
        else:
            try:
                indexer.add(clean, memory_type="chat", verification_status="unverified")
            except TypeError:
                indexer.add(clean)
    except Exception as exc:  # noqa: BLE001 - indexing must not break the chat
        logger.warning(
            "Failed to index completed turn into semantic memory", exc_info=exc
        )


def _make_failure_hook(
    reflector: Optional[ReflectionAgent], session_id: str
) -> Optional[Any]:
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
        except Exception as exc:  # noqa: BLE001 - reflection must never break the chat
            logger.warning("Reflection agent failed to record lesson", exc_info=exc)
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
    *,
    authority: Any | None = None,
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
                if authority is not None and isinstance(
                    consolidator, MemoryConsolidator
                ):
                    authority.consolidate_lesson(mistake_id)
                else:
                    consolidator.consolidate_lesson(mistake_id)
        except Exception as exc:  # noqa: BLE001 - confirmation must never break the chat
            logger.warning("Failed to confirm/consolidate lesson", exc_info=exc)

    return confirm


def _calibrate_default_confidence(
    query: str,
    raw_confidence: Any,
    *,
    reflector: Optional[ReflectionAgent],
    development: DevelopmentTracker,
    skills: SkillMemory,
    authority: Any | None = None,
) -> tuple[float, dict[str, Any]]:
    """Apply planner-style verified-memory calibration to the default chat gate."""
    started = time.perf_counter()
    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    if not (0.0 <= confidence <= 1.0):
        confidence = 0.0

    lessons: list[dict[str, Any]] = []
    outcome = None
    verified_skills: list[dict[str, Any]] = []
    if reflector is not None:
        try:
            lessons = (
                authority.recall_verified_lessons(query, 5)
                if _authority_owns(authority, "lessons", reflector.mistakes)
                else reflector.mistakes.relevant_verified(query, limit=5)
            )
        except Exception:  # noqa: BLE001 - default chat remains available if memory is down
            pass
    try:
        outcome = (
            authority.development_success_rate(query)
            if _authority_owns(authority, "development", development)
            else development.relevant_success_rate(query)
        )
    except Exception:  # noqa: BLE001 - default chat remains available if metrics are down
        pass
    try:
        verified_skills = (
            authority.recall_skills(query, 3)
            if _authority_owns(authority, "skills", skills)
            else skills.relevant_verified(query, limit=3)
        )
    except Exception:  # noqa: BLE001 - default chat remains available if memory is down
        pass

    lesson_adjustment = max(
        -0.4,
        sum(
            float(item["confidence_delta"]) * float(item["relevance"])
            for item in lessons
        ),
    )
    history_adjustment = 0.0
    if outcome is not None:
        history_adjustment = max(
            -0.15,
            min(0.15, (outcome.success_rate - 0.5) * 0.3 * outcome.relevance),
        )
    skill_adjustment = min(
        config.SKILL_CONFIDENCE_BONUS_MAX,
        sum(
            float(item["strength"]) * float(item["relevance"])
            for item in verified_skills
        ),
    )
    final = round(
        max(
            0.0,
            min(
                1.0,
                confidence + lesson_adjustment + history_adjustment + skill_adjustment,
            ),
        ),
        6,
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    evidence = {
        "raw_confidence": confidence,
        "lesson_adjustment": round(lesson_adjustment, 6),
        "history_adjustment": round(history_adjustment, 6),
        "skill_adjustment": round(skill_adjustment, 6),
        "final_confidence": final,
        "lesson_ids": [int(item["mistake_id"]) for item in lessons],
        "outcome_attempts": outcome.attempts if outcome is not None else 0,
        "outcome_success_rate": outcome.success_rate if outcome is not None else None,
        "skill_ids": [int(item["skill_id"]) for item in verified_skills],
        "latency_ms": latency_ms,
    }
    return final, evidence
