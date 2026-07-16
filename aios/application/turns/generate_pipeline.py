"""Application-owned agentic generation turn pipeline.

The HTTP route validates the request, prepares server-owned approval state, and
injects the runtime snapshot. This handler owns the generation lifecycle and
legacy SSE-compatible tool/verification stream so orchestration is dispatched
through TurnCoordinator rather than remaining as a route-local nested function.
"""

from __future__ import annotations

import json
import time
from importlib import import_module
from typing import Any, Iterator, Optional

from fastapi import HTTPException

from aios.application.turns.turn_context import TurnContext
from aios.application.turns.turn_coordinator import RuntimeDeps

_LIVE_NAMES = (
    "CanonicalEvent",
    "CanonicalEventType",
    "CapabilityError",
    "EventPhase",
    "MistakeMemory",
    "Planner",
    "PlannerError",
    "PolicyBrokerError",
    "ToolAgent",
    "TrustLevel",
    "VerificationStrength",
    "Zone",
    "_AUTO_IDS",
    "_STEP_EVENTS",
    "_active_route",
    "_generate_action_envelope",
    "_generate_capability_binding",
    "_calibrate_default_confidence",
    "_cortex_bus",
    "_index_turn",
    "_latest_user",
    "_make_confirm_hook",
    "_make_failure_hook",
    "_recall_facts",
    "_recall_lessons",
    "_recall_memory",
    "_recall_pending_commands",
    "_recall_self_model",
    "_recall_skills",
    "_record_episode",
    "_route_metrics",
    "_self_model_handler",
    "_sse_writer",
    "_select_chat_client",
    "_to_chat_messages",
    "_validate_generate_action_payload",
    "_verify_target_keys",
    "_workflow_step",
    "apply_user_corrections",
    "confidence_gate",
    "config",
    "extract_candidates",
    "infer_task",
    "log_action",
    "logger",
    "meets_promotion_floor",
    "plan_to_prompt_block",
    "router",
    "serialize_plan",
    "strength_from_text",
    "task_signature",
    "telemetry",
    "turn_state",
)


def _refresh_main_bindings() -> None:
    """Refresh mutable API seams so test/runtime overrides remain authoritative."""
    api_main = import_module("aios.api.main")
    namespace = globals()
    for name in _LIVE_NAMES:
        namespace[name] = getattr(api_main, name)


def prepare_generate_state(context: TurnContext, runtime: RuntimeDeps) -> None:
    """Prepare server-owned generation state before the response is created.

    This runs synchronously inside ``TurnCoordinator.coordinate`` so malformed
    approval tokens still produce the route's original HTTP error status rather
    than becoming a late stream failure.
    """
    _refresh_main_bindings()
    extra = runtime.extra
    req = extra["request_model"]
    request = extra["http_request"]
    principal = extra["principal"]
    client = runtime.chat_client
    user_text = context.directive
    chat_messages = _to_chat_messages(req.messages)
    session_id = context.session_id
    task = infer_task(user_text)
    chat_client, model = _select_chat_client(
        req.model_id,
        client,
        runtime.bedrock,
        gemini=runtime.gemini,
        openai=runtime.openai_client,
        anthropic=runtime.anthropic_client,
        task=task,
        metrics=_route_metrics(runtime.development, req.model_id),
        calibration_weight=config.ROUTER_CALIBRATION_WEIGHT,
        data_classification=context.data_classification,
    )
    _, model = _active_route(
        chat_client,
        runtime.bedrock,
        runtime.gemini,
        model,
        openai=runtime.openai_client,
        anthropic=runtime.anthropic_client,
    )

    def route_meta() -> dict[str, Any]:
        provider, served_model = _active_route(
            chat_client,
            runtime.bedrock,
            runtime.gemini,
            model,
            openai=runtime.openai_client,
            anthropic=runtime.anthropic_client,
        )
        return {
            "provider": provider,
            "model": served_model,
            "privacy": "local" if provider == router.PROVIDER_OLLAMA else "cloud",
            "task": task,
            "auto": req.model_id in _AUTO_IDS,
            "turn_id": context.turn_id,
            "mode": context.mode.value,
        }

    runtime.compactor.touch_working_session(session_id)
    if req.approved_commands or req.approved_edits or req.approved_creations:
        raise HTTPException(
            status_code=400,
            detail="raw approved payloads are not accepted; use server-issued approvalTokens",
        )
    capabilities = extra["capabilities"]
    broker = extra["broker"]
    approved_commands: list[str] = []
    approved_edits: list[dict[str, Any]] = []
    approved_creations: list[dict[str, Any]] = []
    try:
        if not req.approval_tokens:
            capabilities.clear_grants(session_id, route="/api/generate")
        for token in req.approval_tokens:
            capability = capabilities.inspect(token)
            payload = _validate_generate_action_payload(
                capability.binding.action_type,
                capability.action_payload,
            )
            expected = _generate_capability_binding(
                principal,
                capability.binding.action_type,
                payload,
            )
            decision = broker.submit(
                _generate_action_envelope(
                    principal,
                    request,
                    capability.binding.action_type,
                    payload,
                ),
                capability_token=token,
                capability_binding=expected,
            )
            if not decision.allowed:
                raise PolicyBrokerError("generate capability was not authorised")
            if capability.binding.action_type == "command":
                runtime.executor.reset_sensitive_actions(session_id)
        for capability in capabilities.grants(session_id, route="/api/generate"):
            exact_payload = _validate_generate_action_payload(
                capability.binding.action_type,
                capability.action_payload,
            )
            if capability.binding.action_type == "command":
                approved_commands.append(str(exact_payload["command"]))
            elif capability.binding.action_type == "edit":
                approved_edits.append(exact_payload)
            elif capability.binding.action_type == "create":
                approved_creations.append(exact_payload)
    except (CapabilityError, PolicyBrokerError, KeyError) as exc:
        raise HTTPException(
            status_code=400, detail=f"invalid approval token: {exc}"
        ) from exc

    resume_tail = (
        turn_state.take(session_id)
        if req.approval_tokens
        else (turn_state.clear(session_id) or None)
    )

    def issue_generate_capability(action_type: str, payload: dict[str, Any]) -> str:
        binding = _generate_capability_binding(principal, action_type, payload)
        decision = broker.submit(
            _generate_action_envelope(principal, request, action_type, payload),
            capability_binding=binding,
            issue_capability=True,
        )
        if not decision.approval_token:
            raise PolicyBrokerError("generate capability issuance returned no token")
        return decision.approval_token

    runtime.extra["generate_state"] = {
        "_issue_generate_capability": issue_generate_capability,
        "_route_meta": route_meta,
        "alignment_evaluation": runtime.alignment_evaluation,
        "alignment_interpreter": runtime.alignment_interpreter,
        "anthropic_client": runtime.anthropic_client,
        "approved_commands": approved_commands,
        "approved_creations": approved_creations,
        "approved_edits": approved_edits,
        "autonomy": runtime.autonomy,
        "bedrock": runtime.bedrock,
        "capabilities": capabilities,
        "cerebellum": runtime.cerebellum,
        "chat_client": chat_client,
        "chat_messages": chat_messages,
        "consolidator": runtime.consolidator,
        "conversation_state": runtime.conversation_state,
        "curriculum": runtime.curriculum,
        "development": runtime.development,
        "executor": runtime.executor,
        "facts": runtime.facts,
        "gemini": runtime.gemini,
        "indexer": runtime.indexer,
        "mistakes": runtime.mistakes,
        "model": model,
        "native_planner": runtime.native_planner,
        "openai_client": runtime.openai_client,
        "planner_llm": runtime.planner_llm,
        "reflector": runtime.reflector,
        "req": req,
        "resume_tail": resume_tail,
        "session_id": session_id,
        "skills": runtime.skills,
        "snapshot": runtime.snapshot,
        "swarm_patterns": runtime.swarm_patterns,
        "task": task,
        "user_text": user_text,
        "compactor": runtime.compactor,
    }


def stream_generate(context: TurnContext, runtime: RuntimeDeps) -> Iterator[str]:
    """Run one agentic generation turn from an injected immutable runtime snapshot."""
    _refresh_main_bindings()
    state = runtime.extra.get("generate_state")
    if not isinstance(state, dict):
        raise RuntimeError("generate handler runtime snapshot is missing")

    ctx = context
    _issue_generate_capability = state["_issue_generate_capability"]
    _route_meta = state["_route_meta"]
    alignment_evaluation = state["alignment_evaluation"]
    alignment_interpreter = state["alignment_interpreter"]
    anthropic_client = state["anthropic_client"]
    approved_commands = state["approved_commands"]
    approved_creations = state["approved_creations"]
    approved_edits = state["approved_edits"]
    autonomy = state["autonomy"]
    bedrock = state["bedrock"]
    capabilities = state["capabilities"]
    cerebellum = state["cerebellum"]
    chat_client = state["chat_client"]
    chat_messages = state["chat_messages"]
    consolidator = state["consolidator"]
    conversation_state = state["conversation_state"]
    curriculum = state["curriculum"]
    development = state["development"]
    executor = state["executor"]
    facts = state["facts"]
    gemini = state["gemini"]
    indexer = state["indexer"]
    mistakes = state["mistakes"]
    model = state["model"]
    native_planner = state["native_planner"]
    openai_client = state["openai_client"]
    planner_llm = state["planner_llm"]
    reflector = state["reflector"]
    req = state["req"]
    resume_tail = state["resume_tail"]
    session_id = state["session_id"]
    skills = state["skills"]
    snapshot = state["snapshot"]
    swarm_patterns = state["swarm_patterns"]
    task = state["task"]
    user_text = state["user_text"]
    compactor = state["compactor"]
    sse = _sse_writer(ctx.turn_id)
    yield sse("turn.started", {"mode": ctx.mode.value})
    if not user_text:
        yield sse("error", {"text": "No user message provided."})
        return

    # Telemetry (Phase 1 lap-counter, roadmap SS1): observation-only, never
    # gates or blocks a turn (record_run fails open). `_dispatch_path` starts
    # at the worst-case honest default and is only ever UPGRADED to a more
    # specific value once a real event proves it (playbook/native-plan
    # replay) -- so a turn that never emits one of those events is
    # correctly counted as `llm` (or `refused_offline` under the offline
    # guard). `_max_zone` is a coarse approximation (see scoping notes):
    # it starts GREEN and is only ever raised, never lowered, toward the
    # worst zone actually observed this turn.
    _turn_started = time.perf_counter()
    _dispatch_path = (
        telemetry.DISPATCH_REFUSED_OFFLINE
        if config.OFFLINE_MODE
        else telemetry.DISPATCH_LLM
    )
    _max_zone = Zone.GREEN.value
    _ZONE_RANK = {Zone.GREEN.value: 0, Zone.YELLOW.value: 1, Zone.RED.value: 2}

    def _bump_zone(new_zone: str) -> None:
        nonlocal _max_zone
        if _ZONE_RANK.get(new_zone, 0) > _ZONE_RANK.get(_max_zone, 0):
            _max_zone = new_zone

    def _record_telemetry(verified_outcome: str) -> None:
        provider, served_model = _active_route(
            chat_client,
            bedrock,
            gemini,
            model,
            openai=openai_client,
            anthropic=anthropic_client,
        )
        telemetry.record_run(
            session_id=session_id,
            task_signature=task_signature(user_text),
            dispatch_path=_dispatch_path,
            provider=provider,
            model=served_model,
            verified_outcome=verified_outcome,
            latency_ms=round((time.perf_counter() - _turn_started) * 1000),
            max_zone=_max_zone,
        )

    # The ACTIVE BRAIN for this turn: which provider/model served it + a privacy
    # indicator, so the UI can show the voyaging mind's current brain. Emitted
    # LAZILY — only once a model has actually served (the first text/tool_call/
    # code), and again whenever a mid-loop failover switches the serving model —
    # so the badge names the model that did the work, never a ranked-but-
    # uninvocable primary that silently failed over. A `FailoverChatClient` only
    # knows which candidate served AFTER its first `chat()` returns; announcing
    # before that would advertise the cascade head, which may not be invocable.
    # Purely informational; the cage decides regardless.
    announced_route: Optional[tuple[str, str]] = None

    def _route_frame() -> Optional[str]:
        nonlocal announced_route
        p, m = _active_route(
            chat_client,
            bedrock,
            gemini,
            model,
            openai=openai_client,
            anthropic=anthropic_client,
        )
        if (p, m) == announced_route:
            return None  # unchanged since the last announcement — don't repeat
        announced_route = (p, m)
        return sse(
            "route",
            {
                "provider": p,
                "model": m,
                "privacy": "local" if p == router.PROVIDER_OLLAMA else "cloud",
                "task": task,
                "auto": req.model_id in _AUTO_IDS,
                "turn_id": ctx.turn_id,
                "mode": ctx.mode.value,
            },
        )

    # 1. Understand + apply the deterministic communication policy + recall.
    #    The alignment frame is advisory. Its communication policy may pause
    #    a context-free request to ask a question, but it has no execution or
    #    approval authority and is never treated as evidence. When the
    #    interpreter is disabled (AIOS_INTERPRET_ALIGNMENT=false) the turn
    #    skips interpretation entirely: no frame, observation, or ask-pause.
    context_parts: list[str] = []
    alignment = None
    # Hoisted above the (conditional) alignment block: the plan stage below
    # must be able to read it even when AIOS_INTERPRET_ALIGNMENT is off.
    _cerebellum_matched = False
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
            except (TypeError, ValueError) as exc:
                # Corrupt optional continuity state must never break chat or
                # silently gain authority.
                logger.warning("Failed to apply active user correction", exc_info=exc)
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
        except Exception as exc:  # noqa: BLE001 - evaluation must never break the chat
            logger.warning("Failed to record alignment evaluation", exc_info=exc)
        try:
            if active_correction is not None and alignment.correction.active:
                conversation_state.refresh_active_correction(
                    session_id,
                    base_frame=base_alignment_payload,
                    corrected_frame=alignment_payload,
                )
            else:
                conversation_state.save(session_id, alignment_payload)
        except Exception as exc:  # noqa: BLE001 - continuity must never break the chat
            logger.warning("Failed to persist alignment frame", exc_info=exc)
        yield sse("alignment", alignment_payload)
        if alignment.communication.ambiguity_action == "ask":
            question = alignment.communication.clarifying_question
            _record_episode(
                session_id, "user", user_text, authority=runtime.memory_authority
            )
            _record_episode(
                session_id, "assistant", question, authority=runtime.memory_authority
            )
            capabilities.clear_grants(session_id, route="/api/generate")
            yield sse("text_chunk", {"text": question})
            # An advisory early exit is still a real turn -- count it
            # (aborted), or every clarification-asked turn silently
            # vanishes from telemetry.
            _record_telemetry(telemetry.OUTCOME_ABORTED)
            yield sse("done", {})
            return

    # ── Sovereignty S1: cerebellum pre-check ──────────────────
    # If a compiled playbook matches the user message, skip the
    # confidence gate — the actual replay happens inside
    # ToolAgent.run() (below), which dispatches every step through
    # self._dispatch (the FULL security pipeline: classify(),
    # scope_lock, audit_logger, verifier). This pre-check only
    # matches and announces; it never dispatches a tool call
    # itself, so there is no parallel security path. Deliberately
    # OUTSIDE the alignment block: ToolAgent replays a matched
    # playbook regardless of AIOS_INTERPRET_ALIGNMENT, so the match
    # announcement — and the plan stage's reflex-skip below — must
    # not depend on the interpreter being enabled.
    if user_text:
        try:
            _cb_match = cerebellum.match(user_text)
        except Exception as exc:  # noqa: BLE001 - cerebellum is advisory, never fatal
            logger.warning("Cerebellum match failed", exc_info=exc)
            _cb_match = None
        if _cb_match is not None:
            _cerebellum_matched = True
            yield sse(
                "cerebellum_match",
                {
                    "goal": _cb_match.goal_pattern,
                    "playbook_id": _cb_match.id,
                    "step_count": len(_cb_match.steps),
                },
            )

    if alignment is not None and not _cerebellum_matched:
        confidence, confidence_calibration = _calibrate_default_confidence(
            " ".join(
                part for part in (user_text, alignment.goal, alignment.intent) if part
            ),
            alignment.confidence,
            reflector=reflector,
            development=development,
            skills=skills,
            authority=runtime.memory_authority,
        )
        confidence_result = confidence_gate(confidence)
        if not confidence_result.passed:
            question = (
                "I am not confident enough in my understanding to proceed. "
                "What should I clarify before continuing?"
            )
            if alignment.unknowns:
                question = (
                    "I am not confident enough in my understanding to proceed. "
                    f"Please clarify: {alignment.unknowns[0]}"
                )
            payload = {
                "confidence": confidence,
                "threshold": config.CONFIDENCE_THRESHOLD,
                "reason": confidence_result.reason,
                "goal": alignment.goal,
                "intent": alignment.intent,
                "question": question,
                "calibration": confidence_calibration,
            }
            _record_episode(
                session_id, "user", user_text, authority=runtime.memory_authority
            )
            _record_episode(
                session_id, "assistant", question, authority=runtime.memory_authority
            )
            capabilities.clear_grants(session_id, route="/api/generate")
            yield sse("confidence.gated", payload)
            yield sse("text_chunk", {"text": question})
            # A confidence-gated turn is still a real turn -- count it.
            _record_telemetry(telemetry.OUTCOME_ABORTED)
            yield sse("done", {})
            return

    # ── Mandatory plan stage (Product-Phase-1 close-out; AIOS_PLAN_STAGE) ──
    # The SAME deterministic Planner behind POST /api/v1/plan, run
    # unconditionally on every non-reflex FIRST turn: native-first
    # (verified experience templates), LLM fallback. The plan is ADVISORY
    # context — it has no execution or approval authority; escalated
    # steps still pause at the gateway's per-action approval surface when
    # they actually execute, and telemetry's dispatch_path is NOT
    # upgraded here (the plan advises the turn; it does not serve it —
    # see the invariant where _dispatch_path is initialized). Fail-open
    # by design: any planner failure (including offline-mode native
    # misses) logs, emits nothing, and the turn proceeds — the confidence
    # gate and approval surface remain the safety layer. Skipped on
    # reflex turns (a matched playbook exists precisely to avoid this
    # consultation) and on approval-resume turns (the goal was already
    # planned when the turn first ran; re-planning mid-approved-action
    # would inject a second, possibly different plan).
    if (
        config.PLAN_STAGE_ENABLED
        and user_text
        and not _cerebellum_matched
        and not req.approval_tokens
    ):
        # Announce BEFORE the (blocking) planner consultation so the
        # stream is never silent for a full LLM completion — time-to-
        # first-byte stays bounded and the UI can show the phase.
        yield sse(
            "step",
            {
                "type": "tool_result",
                "tool": "plan",
                "output": "Plan stage: decomposing the goal into confidence-gated steps…",
                "id": "plan-stage",
            },
        )
        try:
            _stage_planner = Planner(
                planner_llm,
                native=native_planner,
                mistakes=mistakes,
                development=development,
                skills=skills,
                memory_authority=runtime.memory_authority,
            )
            _stage_plan = _stage_planner.plan(user_text)
        except PlannerError as exc:
            logger.warning("Plan stage failed open: %s", exc)
        except Exception as exc:  # noqa: BLE001 - planning is advisory, never fatal
            logger.warning("Plan stage failed open", exc_info=exc)
        else:
            yield sse("plan", serialize_plan(_stage_plan))
            context_parts.append(plan_to_prompt_block(_stage_plan))

    semantic = _recall_memory(user_text, authority=runtime.memory_authority)
    if semantic:
        context_parts.append(semantic)
        yield sse(
            "step",
            {
                "type": "tool_result",
                "tool": "query_knowledge",
                "output": semantic[:400],
                "id": "memory-recall",
            },
        )

    lessons = _recall_lessons(
        reflector,
        session_id,
        user_text,
        authority=runtime.memory_authority,
    )
    if lessons:
        block = (
            "RELEVANT LESSONS (verified cross-task or pending from this task):\n"
            + "\n".join(
                f"- [{le.get('verification_status', 'pending')}; {le['error_type']}] "
                f"{le['lesson_text']}"
                for le in lessons
            )
        )
        context_parts.append(block)
        yield sse(
            "step",
            {
                "type": "tool_result",
                "tool": "reflect",
                "output": f"Recalled {len(lessons)} past lesson(s); filtered for relevance.",
                "id": "lesson-recall",
            },
        )

    recalled_skills = _recall_skills(
        skills,
        user_text,
        authority=runtime.memory_authority,
    )
    if recalled_skills:
        skill_block = "VERIFIED REUSABLE WORKFLOWS:\n" + "\n".join(
            f"- For {skill['goal_pattern']}: {' -> '.join(skill['steps'])} "
            f"(verified success rate {skill['success_rate']:.0%})"
            for skill in recalled_skills
        )
        context_parts.append(skill_block)
        yield sse(
            "step",
            {
                "type": "tool_result",
                "tool": "query_skills",
                "output": f"Recalled {len(recalled_skills)} verified workflow(s).",
                "id": "skill-recall",
            },
        )

    facts_result = _recall_facts(
        facts,
        user_text,
        authority=runtime.memory_authority,
    )
    if facts_result:
        context_parts.append(facts_result.text)
        yield sse(
            "step",
            {
                "type": "tool_result",
                "tool": "query_facts",
                "output": facts_result.text[:400],
                "id": "fact-recall",
            },
        )
        for inf in facts_result.inferences:
            yield sse("graph_inference", inf)
            if inf.get("reached_horizon"):
                yield sse(
                    "graph_horizon",
                    {
                        "entity": inf.get("entity", "?"),
                        "confidence": inf.get("combined_confidence", 0),
                    },
                )

    # Narrative self (opt-in): a grounded, verified-only autobiographical
    # self-model joins the recalled context — the organism reasoning with an
    # honest sense of what it's actually reliable at. Fail-closed: empty when
    # there's too little verified evidence.
    if config.NARRATIVE_SELF_ENABLED:
        # W2: when the cortex bus is on, the self-model was synthesized OFF
        # the hot path by SelfModelHandler (turn.completed observer) — read
        # its cache. Fall back to inline synthesis when the bus is off
        # (default: identical to pre-W2 behavior) or before the first
        # observation has been processed.
        cached_self_model = (
            _self_model_handler.recall()
            if config.CORTEX_BUS and _self_model_handler is not None
            else None
        )
        self_model_block = (
            cached_self_model
            if cached_self_model is not None
            else _recall_self_model(
                development,
                mistakes,
                authority=runtime.memory_authority,
            )
        )
        if self_model_block:
            context_parts.append(self_model_block)
            yield sse(
                "step",
                {
                    "type": "tool_result",
                    "tool": "self_model",
                    "output": self_model_block[:400],
                    "id": "self-model-recall",
                },
            )

    memory_context = "\n\n".join(context_parts) or None

    # Seed for the fail->confirm tracker (see _recall_pending_commands): this
    # session's still-pending lessons + their failed commands, so a lesson
    # recorded before an approval pause is promoted when its exact command
    # finally succeeds in the replayed continuation of the turn.
    recalled_pending = _recall_pending_commands(reflector, session_id)

    # 2. Persist the user turn.
    _record_episode(
        session_id, "user", user_text, authority=runtime.memory_authority
    )

    # 3. Agentic loop with recalled context + lessons + reflection + confirmation.
    #    `chat_client` is local Ollama or cloud Bedrock per the selected model.
    #    The factory exists so the role-pass castes can stamp out per-role
    #    views (system prompt + tool subset) over the SAME gated wiring.
    # C4: streaming function for real-time cloud token delivery.
    _stream_fn = getattr(chat_client, "stream_chat_with_tools", None)

    def make_agent(**overrides: Any) -> ToolAgent:
        return ToolAgent(
            chat_client,
            executor,
            model=model,
            session_id=session_id,
            memory_context=memory_context,
            on_failure=_make_failure_hook(reflector, session_id),
            confirm_lesson=_make_confirm_hook(
                reflector, consolidator, authority=runtime.memory_authority
            ),
            # Confirm-across-approval-boundary: seed the fail->confirm tracker
            # so a lesson recorded before an approval pause is still promoted
            # when its exact command later succeeds in the replayed turn.
            recalled_pending=recalled_pending,
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
            # Earned-autonomy bridge: opt-in, off by default. When enabled and
            # a write class has earned it, the turn applies it without pausing
            # (still gated, audited, and revoked instantly on a verified fail).
            autonomy=autonomy,
            # Approval-resume continuation (ratified option A, S3): the prior
            # pause's convo tail for this session, or None. Model context
            # only -- carries no authority of its own.
            resume_tail=resume_tail,
            # Sovereignty S1: compiled-experience engine. Matches verified
            # skill arcs and replays them through _dispatch without an LLM.
            cerebellum=cerebellum,
            # Sovereignty S3: native symbolic planner. Plans known task
            # shapes from verified experience without an LLM call.
            native_planner=native_planner,
            memory_authority=runtime.memory_authority,
            # C4: stream tokens in real-time when the cloud client supports it.
            stream_fn=_stream_fn if callable(_stream_fn) else None,
            **overrides,
        )

    # Cloud-burst factory: when the ant-colony's CLOUD_BROKER labels a subtask
    # as cloud-eligible, it runs through a dedicated cloud chat client. The
    # provider is surfaced in `cloud_route` SSE frames so the UI can mark the
    # leg as having left the local machine.
    cloud_client: Optional[Any] = None
    cloud_provider: Optional[str] = None
    cloud_model: Optional[str] = None
    if req.swarm and config.SWARM_CLOUD_BURST_ENABLED:
        if config.BEDROCK_ENABLED:
            cloud_client = BedrockClient()
            cloud_provider = "bedrock"
            cloud_model = config.BEDROCK_MODEL
        elif config.GEMINI_ENABLED:
            cloud_client = GeminiClient()
            cloud_provider = "gemini"
            cloud_model = config.GEMINI_MODEL

    def make_cloud_agent(**overrides: Any) -> ToolAgent:
        if cloud_client is None:
            raise RuntimeError(
                "Cloud burst requested but no cloud provider is configured"
            )
        return ToolAgent(
            cloud_client,
            executor,
            model=cloud_model,
            session_id=session_id,
            memory_context=memory_context,
            on_failure=_make_failure_hook(reflector, session_id),
            confirm_lesson=_make_confirm_hook(
                reflector, consolidator, authority=runtime.memory_authority
            ),
            # Confirm-across-approval-boundary: seed the fail->confirm tracker
            # so a lesson recorded before an approval pause is still promoted
            # when its exact command later succeeds in the replayed turn.
            recalled_pending=recalled_pending,
            approved_commands=approved_commands,
            approved_edits=approved_edits,
            approved_creations=approved_creations,
            snapshot=snapshot,
            planner_llm=planner_llm,
            self_analysis_llm=planner_llm,
            memory_authority=runtime.memory_authority,
            autonomy=autonomy,
            resume_tail=resume_tail,
            **overrides,
        )

    answer_parts: list[str] = []
    workflow_steps: list[str] = []
    blocked_actions = 0
    verification_evidence: list[str] = []
    verify_verdicts: dict[str, str] = {}
    #: Per-target verification strength (parallel to the verdict dicts), so the
    #: turn's calibration strength is the WEAKEST authoritative PASS — a strong
    #: verify on one target can never launder a weak one, and a model's advisory
    #: verify can never raise the authoritative strength (see ``record_outcome``).
    verify_strengths: dict[str, VerificationStrength] = {}
    #: Verdicts from the FORCED auto-verify only (id ``autoverify-*``). This is
    #: the authoritative evidence for the turn's outcome; the model's own
    #: ``verify`` tool calls are advisory and must not override it.
    auto_verdicts: dict[str, str] = {}
    auto_strengths: dict[str, VerificationStrength] = {}
    communication_notice = (
        alignment.communication_notice() if alignment is not None else ""
    )
    if communication_notice:
        answer_parts.append(communication_notice)
        yield sse("text_chunk", {"text": communication_notice})

    mastered_levels: list[tuple[str, int]] = []

    def record_outcome(outcome: str) -> None:
        """Best-effort development, skill, and curriculum evidence write."""
        # The strength of this turn's authoritative verification gates ALL
        # calibration (roadmap Phase 1): a below-floor (weak) green must not
        # calibrate the router/planner, promote a swarm pattern, or advance
        # curriculum mastery. Strength is the WEAKEST authoritative target
        # strength (auto-verify if any ran, else the model's own verify) — not
        # the last PASS across all evidence. This defeats laundering: a model
        # cannot append a STRONG advisory verify to raise a turn whose forced
        # auto-verify was weak, and one strong target cannot mask a weak one.
        authoritative_strengths = auto_strengths or verify_strengths
        turn_strength = (
            min(authoritative_strengths.values())
            if authoritative_strengths
            else VerificationStrength.NONE
        )
        # A weak verified_success is recorded as 'unverified' so it is excluded
        # from router/planner calibration (reuses the existing exclusion).
        dev_outcome = (
            "unverified"
            if outcome == "verified_success"
            and not meets_promotion_floor(turn_strength)
            else outcome
        )
        try:
            record_development = (
                runtime.memory_authority.record_development
                if runtime.memory_authority is not None
                and runtime.memory_authority.owns_store("development", development)
                else development.record
            )
            record_development(
                user_text,
                dev_outcome,
                tool_calls=len(workflow_steps),
                human_interventions=len(req.approval_tokens),
                blocked_actions=blocked_actions,
                metadata=_route_meta(),
            )
        except Exception as exc:  # noqa: BLE001 - metrics must never break chat
            logger.warning("Development metrics recording failed", exc_info=exc)
        if config.FACTS_AUTO_EXTRACT:
            try:
                proposed_count = 0
                for fact_subject, fact_predicate, fact_object in extract_candidates(
                    user_text,
                    max_candidates=config.FACTS_AUTO_EXTRACT_MAX_PER_TURN,
                ):
                    strengthen_or_propose = (
                        runtime.memory_authority.facts_strengthen_or_propose
                        if runtime.memory_authority is not None
                        and runtime.memory_authority.owns_store("facts", facts)
                        else facts.strengthen_or_propose
                    )
                    r = strengthen_or_propose(fact_subject, fact_predicate, fact_object)
                    if r.proposed or r.reason == "strengthened":
                        proposed_count += 1
                if proposed_count and _cortex_bus:
                    canonical = CanonicalEvent(
                        event_type=CanonicalEventType.FACTS_PROPOSED.value,
                        phase=EventPhase.WONDER.value,
                        status="success",
                        trust=TrustLevel.VERIFIED.value,
                        source="generate",
                        session_id=session_id,
                        turn_id=ctx.turn_id,
                        payload={"count": proposed_count},
                    )
                    _cortex_bus.append(
                        canonical.event_type,
                        session_id,
                        canonical.to_dict(),
                    )
            except Exception as exc:  # noqa: BLE001 - proposal formation is best-effort
                logger.warning("Failed to propose auto-extracted facts", exc_info=exc)
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
        direct_id: Optional[int] = None
        if workflow_steps:
            try:
                # Gate promotion on verification strength (roadmap Phase 1): the
                # strength token is stamped into the [VERIFY ...] evidence by the
                # Verifier (command-aware), so a weak green cannot mint a
                # verified skill. On a fail, success=False makes strength moot.
                record_attempt = (
                    runtime.memory_authority.record_skill_attempt
                    if runtime.memory_authority is not None
                    and runtime.memory_authority.owns_store("skills", skills)
                    else skills.record_attempt
                )
                direct_id = record_attempt(
                    user_text,
                    workflow_steps,
                    success=passed,
                    strength=turn_strength,
                )
            except Exception as exc:  # noqa: BLE001 - skill learning is best-effort
                logger.warning("Failed to record skill attempt", exc_info=exc)
        # Reuse pheromone: trails that were recalled into this turn's
        # context share its verifier verdict — minus the trail the agent
        # re-walked directly, which record_attempt already credited.
        # Exclude ONLY the trail the agent re-walked directly (already credited
        # by record_attempt) so it isn't double-credited. When direct_id is
        # None (no direct walk, or record_attempt failed) there is nothing to
        # exclude, so every recalled trail correctly earns reuse credit. The
        # explicit None check documents that intent (the old `!= direct_id` was
        # an always-true int-vs-None compare — same behavior, but a smell).
        reused_ids = [
            int(s["skill_id"])
            for s in recalled_skills
            if direct_id is None or int(s["skill_id"]) != direct_id
        ]
        if reused_ids:
            try:
                record_reuse = (
                    runtime.memory_authority.record_skill_reuse
                    if runtime.memory_authority is not None
                    and runtime.memory_authority.owns_store("skills", skills)
                    else skills.record_reuse
                )
                record_reuse(reused_ids, success=passed)
            except Exception as exc:  # noqa: BLE001 - reuse credit is best-effort
                logger.warning("Failed to record skill reuse credit", exc_info=exc)
        if swarm_plan:
            try:
                swarm_patterns.record_attempt(
                    user_text, swarm_plan, success=passed, strength=turn_strength
                )
            except Exception as exc:  # noqa: BLE001 - pattern learning is best-effort
                logger.warning("Failed to record swarm pattern attempt", exc_info=exc)
        try:
            curriculum.record_matching(
                user_text,
                passed=passed,
                evidence=evidence,
                strength=turn_strength,
                on_mastered=lambda skill, level: mastered_levels.append((skill, level)),
            )
        except Exception as exc:  # noqa: BLE001 - unmatched/invalid curriculum is harmless
            logger.warning("Failed to record curriculum match", exc_info=exc)

    if req.swarm or req.role_pass:
        requested_strategy = "swarm" if req.swarm else "role_pass"
        _record_telemetry(telemetry.OUTCOME_ABORTED)
        yield sse(
            "error",
            {
                "code": "strategy_unavailable",
                "text": (
                    f"experimental strategy is not production-selected: "
                    f"{requested_strategy}; route it through WorkerFoundry before enabling"
                ),
            },
        )
        yield sse("done", {})
        return
    try:
        event_source = make_agent().run(chat_messages)
    except Exception as exc:  # noqa: BLE001 - agent construction must not kill SSE
        logger.error("Tool-loop construction failed", exc_info=exc)
        yield sse("error", {"text": f"Internal error: {exc}"})
        # A turn killed by construction failure is still a real turn -- count it.
        _record_telemetry(telemetry.OUTCOME_ABORTED)
        yield sse("done", {})
        return

    def _safe_iter(source):
        """Wrap a generator so exceptions during iteration are logged, not silent."""
        try:
            yield from source
        except Exception as exc:  # noqa: BLE001
            logger.error("Tool-loop iteration failed", exc_info=exc)
            yield {"type": "error", "text": f"Internal error: {exc}"}
            yield {"type": "done"}

    swarm_plan: Optional[list[str]] = None
    for ev in _safe_iter(event_source):
        kind = ev["type"]
        if kind in ("tool_call", "text", "code", "done", "human_required"):
            # A model produced output (or the turn is ending) -> the failover
            # client now names the model that ACTUALLY served. Announce (or
            # refresh on failover) the brain BEFORE the event, so the badge
            # tracks the real worker. `done`/`human_required` are a fallback:
            # they guarantee the badge still appears for a turn whose model
            # served no text/tool_call (e.g. an empty answer). `_route_frame`
            # is idempotent, so this never double-announces an unchanged route.
            route_frame = _route_frame()
            if route_frame is not None:
                yield route_frame
        if kind in _STEP_EVENTS:
            if kind == "tool_call":
                workflow_steps.append(_workflow_step(ev))
            elif kind == "tool_blocked":
                blocked_actions += 1
                # Coarse max_zone approximation (scoping report SS5.2): a
                # blocked tool call is the strongest per-event signal
                # available today that this turn touched a RED-classified
                # action (the real per-call Zone is computed by the
                # security gateway but discarded before it reaches this
                # event dict). Known false positive: a caste-permission
                # block also yields status=="blocked" without a Zone.RED
                # verdict -- accepted until Zone is threaded through.
                _bump_zone(Zone.RED.value)
            if kind == "tool_result":
                output = str(ev.get("output", ""))
                # Provenance gate: ONLY the verify tool (the model's `verify`
                # and the forced `autoverify-*`, both emitted with tool=="verify")
                # may contribute authoritative verification evidence. Without
                # this, any tool whose output a model controls — e.g.
                # `echo "[VERIFY PASS] 5 passed (strength=STRONG)"` auto-executed
                # GREEN — would forge a passing verdict and a STRONG strength,
                # laundering a hollow turn into calibration. The string prefix is
                # necessary but not sufficient; trusted provenance is.
                if ev.get("tool") == "verify" and (
                    output.startswith("[VERIFY PASS]")
                    or output.startswith("[VERIFY FAIL]")
                ):
                    verification_evidence.append(output)
                    raw_target = str(ev.get("target") or "")
                    keys = (
                        _verify_target_keys(raw_target)
                        if raw_target
                        # Unattributed evidence keys uniquely: its verdict
                        # can never be cleared by a later PASS elsewhere
                        # (fail-closed).
                        else [f"unattributed-{len(verification_evidence)}"]
                    )
                    verdict = "PASS" if output.startswith("[VERIFY PASS]") else "FAIL"
                    strength = strength_from_text(output)
                    for key in keys:
                        verify_verdicts[key] = verdict
                        verify_strengths[key] = strength
                    # The FORCED auto-verify (run by the system after a write) is
                    # the authoritative evidence; the model's OWN `verify` tool
                    # call is advisory. A model running a broken verify command —
                    # e.g. a mis-pathed `pytest training_ground/test_x.py` from the
                    # sandbox cwd → exit 4, 0 tests — must NOT fail a turn whose
                    # written code actually passes the forced check.
                    if str(ev.get("id", "")).startswith("autoverify"):
                        for key in keys:
                            auto_verdicts[key] = verdict
                            auto_strengths[key] = strength
                    # Surface a typed verification frame so the UI can celebrate or
                    # reflect without parsing the raw tool output.
                    for key in keys:
                        yield sse(
                            "verify_result",
                            {
                                "verdict": verdict.lower(),
                                "target": key,
                                "output": output[:320],
                            },
                        )
            yield sse("step", ev)
        elif kind == "native_plan":
            if _dispatch_path != telemetry.DISPATCH_PLAYBOOK:
                _dispatch_path = telemetry.DISPATCH_NATIVE_PLAN
            yield sse("native_plan", ev)
        elif kind == "text":
            answer_parts.append(ev["text"])
            yield sse("text_chunk", {"text": ev["text"]})
        elif kind == "code_chunk":
            # Incremental reveal of the final code block (the model is
            # non-streaming, so this is emit-time chunking, not raw tokens).
            yield sse("code_chunk", {"code": ev["code"], "language": ev["language"]})
        elif kind == "code":
            yield sse("code", {"code": ev["code"], "language": ev["language"]})
        elif kind == "error":
            yield sse("error", {"text": ev["text"]})
        elif kind == "earned_autonomy":
            # The earned-autonomy bridge auto-applied a write with NO human
            # pause — the write class earned it by verified-success evidence.
            # Surface it so the brain can show itself acting on its own
            # earned trust (still gated, audited, and revocable).
            yield sse("earned_autonomy", ev)
        elif kind.startswith("cerebellum_"):
            # Sovereignty S1: the cerebellum replayed a compiled playbook.
            # Forward all cerebellum events to the SSE stream so the
            # organism body renders the reflex phase (orange, low
            # metabolism, no brain churn).
            if kind == "cerebellum_step_done":
                workflow_steps.append(f"{ev.get('tool', '?')}: cerebellum replay")
            elif kind == "cerebellum_done":
                _dispatch_path = telemetry.DISPATCH_PLAYBOOK
            yield sse(kind, ev)
        elif kind == "swarm_plan":
            # Plan event from the ant-colony; used internally for pattern
            # recording and also surfaced to the UI so the HUD can render it.
            swarm_plan = ev.get("plan")
            yield sse(kind, ev)
        elif kind in ("caste_start", "caste_end", "cloud_route"):
            # Observational swarm lifecycle frames for the 3D HUD.
            if kind == "cloud_route" and cloud_provider:
                try:
                    log_action(
                        "cloud-route",
                        json.dumps({"provider": cloud_provider, "model": cloud_model}),
                        Zone.GREEN,
                    )
                except Exception as exc:  # noqa: BLE001 - audit must never break the stream
                    logger.warning(
                        "Failed to record cloud-route audit entry", exc_info=exc
                    )
            yield sse(kind, ev)
        elif kind == "human_required":
            # The agent paused on a YELLOW command. Ask the UI for approval;
            # the turn ends here (no answer recorded) and is replayed once the
            # human authorises the command. Surface the *command* in plain
            # language — never the raw classifier reason, which embeds the
            # matched regex pattern (e.g. "\\bpip\\s+install\\b") and belongs
            # in the audit log, not in a human approval prompt. Shape matches
            # the frontend's pendingAction handler ({commands, explanation}).
            _bump_zone(Zone.YELLOW.value)
            cmd = ev["command"]
            edit = ev.get("edit")
            creation = ev.get("creation")
            # Approval-resume continuation (ratified option A, S2): pop the
            # convo tail off the event BEFORE any payload is built below --
            # it must never reach `payload`/the SSE wire. Stashed under this
            # session id so a later resume (token redeemed above) can pop it
            # back out and splice it into the next ToolAgent.run's convo.
            # The token itself lives only in `payload` (issued just below),
            # never in the tail -- the tail carries no authority.
            _convo_tail = ev.pop("_convo_tail", None)
            if _convo_tail:
                turn_state.stash(session_id, _convo_tail)
            try:
                if edit is not None:
                    token = _issue_generate_capability("edit", edit)
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
                    token = _issue_generate_capability("create", creation)
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
                    command_payload = {"command": cmd}
                    token = _issue_generate_capability("command", command_payload)
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
            except (CapabilityError, PolicyBrokerError) as exc:
                logger.warning(
                    "Approval payload refused before token issue", exc_info=exc
                )
                capabilities.clear_grants(session_id, route="/api/generate")
                yield sse("error", {"text": f"Approval request refused: {exc}"})
                return
            try:
                record_development = (
                    runtime.memory_authority.record_development
                    if runtime.memory_authority is not None
                    and runtime.memory_authority.owns_store("development", development)
                    else development.record
                )
                record_development(
                    user_text,
                    "paused",
                    tool_calls=len(workflow_steps),
                    human_interventions=len(req.approval_tokens),
                    blocked_actions=blocked_actions,
                    metadata=_route_meta(),
                )
            except Exception as exc:  # noqa: BLE001 - metrics must never break approval
                logger.warning(
                    "Development metrics recording failed for paused turn", exc_info=exc
                )
            # A turn that pauses for approval and is never resumed must still
            # be counted -- otherwise every YELLOW-gated turn (a large share
            # of real traffic) silently vanishes from telemetry entirely.
            _record_telemetry(telemetry.OUTCOME_ABORTED)
            yield sse("human_required", payload)
        elif kind == "done":
            # 4. Persist the answer (L2) and consolidate the turn into L3.
            answer = "".join(answer_parts)
            _record_episode(
                session_id, "assistant", answer, authority=runtime.memory_authority
            )
            _index_turn(
                indexer,
                user_text,
                answer,
                authority=runtime.memory_authority,
            )
            # The turn's outcome is the PER-TARGET final verdict: for every
            # target that was verified this turn, its LAST verdict must be
            # PASS. A turn that fails, self-corrects, and re-verifies the
            # same target green IS a verified success — the loop's whole
            # design is verify -> reflect -> fix (operator decision
            # 2026-06-11, refined the same day from global last-evidence-
            # wins) — but a final PASS on one target can no longer mask an
            # unresolved FAIL on another.
            if not verification_evidence:
                record_outcome("unverified")
                _record_telemetry(telemetry.OUTCOME_UNVERIFIED)
            else:
                # The FORCED auto-verify is authoritative; fall back to the
                # model's own verify only when nothing was auto-verified.
                authoritative = auto_verdicts or verify_verdicts
                if any(v == "FAIL" for v in authoritative.values()):
                    record_outcome("verified_failure")
                    _record_telemetry(telemetry.OUTCOME_FAIL)
                else:
                    record_outcome("verified_success")
                    _record_telemetry(telemetry.OUTCOME_PASS)
            # B5 growth: announce curriculum mastery so the body's lattice
            # can harden. Additive frame; fires only on the transition and
            # only under the STRONG promotion floor (gated inside
            # record_matching), so a weak green can never make the body
            # celebrate growth that did not happen.
            for mastered_skill, mastered_level in mastered_levels:
                yield sse(
                    "skill.mastered",
                    {
                        "skill": mastered_skill,
                        "level": mastered_level,
                        "source": "curriculum",
                    },
                )
            capabilities.clear_grants(session_id, route="/api/generate")
            turn_state.clear(session_id)
            yield sse("done", {})
