# GAGOS Architecture

*Synthesized from a full-repo subsystem mapping pass + an independent adversarial dead-code
verification pass. Backend paths are relative to `aios/`, frontend paths relative to
`frontend/src/`, unless a full path is given.*

---

## 1. Architecture Tree

### Backend — `aios/`

```
aios/
├── __main__.py                  entry point: uvicorn.run("aios.api.main:app", ...)
├── config.py                    all env-driven feature flags (opt-in subsystem switches, model/router config)
├── logging_config.py            structlog setup + request-scoped session/request-id binding
├── boot_attestation.py          startup integrity attestation, run once from lifespan()
├── audit_anchor.py              external anchor publish/verify for the tamper-evident audit chain
├── probe_common.py              shared helpers for the standalone evidence/probe tooling (see §4 gaps)
│
├── api/                         ── HTTP surface (FastAPI) ──
│   ├── main.py                  core app: 49 endpoints, lifespan, middleware, generate()/chat()/terminal()
│   └── routes/
│       ├── council.py           Council mission origination/list/approve/reject/rollback (7 endpoints)
│       ├── sovereignty.py        Queen services, pheromones, live surface, rollback registry, audit anchor, policy engine (24 endpoints)
│       └── voice.py              local STT (faster-whisper) / TTS (piper) endpoints (3 endpoints)
│
├── agents/                      ── the agentic tool-loop layer ──
│   ├── tool_agent.py             ToolAgent: the agentic tool-calling loop engine itself
│   ├── tool_handlers.py          individual tool implementations dispatched inside the loop
│   ├── tool_loop_helpers.py      shared loop utilities (event shaping, bookkeeping)
│   ├── swarm.py                  run_swarm(): multi-agent/multi-caste concurrent run
│   ├── swarm_patterns.py         SwarmPatternMemory: reusable swarm-strategy memory
│   ├── role_pass.py              run_role_pass(): single-role scoped agent pass
│   ├── reflection_agent.py       ReflectionAgent: turns a failure into a structured lesson
│   ├── rollback_engine.py        RollbackEngine: sandbox working-tree snapshot/restore
│   └── self_analysis_agent.py    the T0–T4 self-analysis pipeline (repo self-critique → proposals)
│
├── core/                        ── model routing, execution, security-adjacent policy, verification ──
│   ├── llm.py                    LLMClient / LLMError / OllamaClient (local model transport)
│   ├── bedrock.py / gemini.py / openai_compat.py / anthropic_direct.py   cloud LLM client adapters (lazy, lock-guarded singletons)
│   ├── model_selector.py         infer_task / select_model / supports_tool_protocol — task→model selection
│   ├── router.py / router_wiring.py   the multi-LLM router + its provider-selection wiring (`_select_chat_client`, `_active_route`, etc.)
│   ├── catalog.py                model/provider catalog
│   ├── planner.py / native_planner.py   Planner (confidence-gated task decomposition) and NativePlanner
│   ├── executor.py               Executor: scope-constrained, rate-limited sandboxed command execution
│   ├── confidence_filter.py      gate(): confidence-gated decision to proceed/pause
│   ├── cerebellum.py              Cerebellum: procedural "playbook" pre-check (learned reflexes)
│   ├── alignment.py               AlignmentInterpreter, user-correction application/validation
│   ├── approvals.py               ApprovalStore: human-decision tokens for YELLOW-zone actions
│   ├── verifier.py                Verifier: post-execution result verification
│   ├── verification_strength.py   VerificationStrength / meets_promotion_floor / strength_from_text — anti-laundering strength taxonomy
│   ├── self_apply.py              SelfApplyEngine: gated/verified/auto-rollback self-modification (T3)
│   ├── session_manager.py         SessionManager: server-side session state
│   ├── events.py                  event_for_sse(): internal-event → SSE-frame mapping
│   ├── telemetry.py                turn/zone/route telemetry recording
│   ├── metrics.py                  Prometheus MetricsCollector + MetricsMiddleware
│   ├── prompt_writer.py            PromptWriter: system-prompt assembly (operator-facts + recall sections)
│   ├── inference.py                infer(): shared low-level completion helper
│   ├── websearch.py                web_search(): external web lookup (used by CRAG's web source)
│   ├── voice.py                    STTService / TTSService / VoiceError
│   └── self_consistency.py         DEAD — see §3
│
├── memory/                      ── the memory stack (L1 working → L2 episodic → L3 semantic + graph) ──
│   ├── db.py                       shared sqlite connection / init_memory_db
│   ├── working.py                  WorkingMemory (in-turn scratch state)
│   ├── episodic.py                 EpisodicMemory (per-turn transcript log, secret-scrubbed)
│   ├── semantic.py                 SemanticMemory (indexed Q→A turns)
│   ├── embeddings.py                VectorIndex (FAISS-backed embedding index)
│   ├── retrieval.py                 hybrid_search(): BM25 + FAISS + decay recall
│   ├── relevance.py                 signature()/task_signature: recall relevance scoring
│   ├── crag.py                      Corrective-RAG: evaluate_retrieval / refine_context / external_retrieve (opt-in)
│   ├── facts.py                     SemanticFacts: durable fact store
│   ├── fact_extraction.py           extract_candidates(): auto-extraction of fact proposals from chat
│   ├── skills.py                    SkillMemory (candidate → verified procedural skills)
│   ├── mistake.py                   MistakeMemory (recorded failures → lessons)
│   ├── curriculum.py / curriculum_miner.py   safe curriculum task definitions + auto-mined proposals
│   ├── development.py               DevelopmentTracker: behavior-change/verification-coverage metrics
│   ├── consolidation.py             MemoryConsolidator: idempotent lesson/fact indexing sweep
│   ├── compaction.py                MemoryCompactor: audited memory-forgetting sweep
│   ├── conversation.py              ConversationStateStore: recent-dialogue + alignment-frame restore
│   ├── alignment_evaluation.py      AlignmentEvaluationStore: diagnostic human-alignment evidence
│   ├── self_model.py                synthesize_self_model()/render(): grounded, verified-only self-model text
│   ├── operator_model.py            render_operator_model(): structured operator-knowledge snapshot
│   ├── doc_ingest.py                DocumentIngestor: RAG document ingestion
│   └── pheromones.py                PheromoneStore/PheromoneType: stigmergic trail deposits/decay
│
├── runtime/                     ── process/subprocess orchestration, cross-cutting live state ──
│   ├── contracts.py                 KingReport / RunLedger dataclasses (Council mission artifacts)
│   ├── cortex_bus.py                CortexBus: the append-only cross-process observation bus (opt-in)
│   ├── cortex_bus_dispatcher.py      CortexBusDispatcher: polling dispatcher (poll_interval=0.25)
│   ├── self_model_handler.py         SelfModelHandler: consumes bus events into the self-model
│   ├── king_report.py / run_ledger.py   persistence stores for Council mission artifacts
│   ├── snapshots.py                  SnapshotManager: working-tree snapshot/restore primitive
│   ├── turn_state.py                 module-level in-flight turn / approval-resume state
│   ├── live_surface.py               LiveSurface: ephemeral coordination-signal surface
│   ├── rollback_registry.py          RollbackRegistry: snapshot-point registration/pruning
│   ├── spawner.py                    WorkerSpawner: launches Council worker subprocesses
│   ├── backends.py                   ControlledSubprocessBackend (string-dispatches `aios.runtime.worker_entry`)
│   ├── worker_entry.py               subprocess entry point for a spawned Council worker
│   └── worktree_backend.py           DEAD — see §3
│
├── security/                    ── the security gateway ──
│   ├── gateway.py                   classify()/Zone/RateLimiter: deterministic fail-closed RED/YELLOW/GREEN zone classification
│   ├── audit_logger.py               log_action()/verify_chain(): tamper-evident hash-chained audit trail
│   ├── secret_scanner.py             scan_and_redact(): secret scrubbing before persistence
│   └── injection_shield.py           VectorInjectionShield: opt-in embedding-space prompt-injection guard
│
├── council/                     ── the King/Queen/Worker supervised-autonomy layer ──
│   ├── __init__.py                   CouncilMissionRequest, CouncilOrchestrator (top-level orchestration)
│   ├── council_state.py              CouncilState: Phase-3A SQLite-backed mission state
│   ├── reasoning.py / king_reasoning.py   PlannerQueen/King LLM planning + reasoning (opt-in, `AIOS_COUNCIL_REASONING`)
│   ├── queen_verdict.py              has_blocking_verdict(): Queen-vote gate for mission approval
│   └── queen_service.py              QueenService ABC + QUEEN_SERVICES registry (see §4 — registry always empty)
│
└── policy/
    └── engine.py                     PolicyEngine: additive-only policy propose/vote/enact/suspend/chain
```

### Frontend — `frontend/src/`

```
frontend/src/
├── main.jsx                          entry point; lazy-mounts SuperbrainApp; imports monacoConfig/troikaConfig once
│
├── workbench/
│   ├── GagosChrome.jsx                the live 2D DOM chat/chrome shell — sends turns, publishes most cognitionBus events
│   └── voiceSpeak.ts                  TTS speak-aloud loop; publishes 'voice-speaking' for spoken playback
│
├── utils/
│   ├── index.js                      DEAD orphaned barrel — see §3
│   └── sanitizeHtml.js               real module — imported directly by GagosChrome.jsx, not via the barrel
│
└── superbrain/                       ── the 3D "being" + its supporting chrome ──
    ├── SuperbrainApp.jsx              app root: wires BootSequence + WorkspaceCanvas (3D) + GagosChrome (2D)
    ├── superbrain.css                 global stylesheet for the 2D chrome layer
    │
    ├── components/
    │   ├── QualityTierProvider.tsx    metabolic governor: persisted baseTier + live "generating" dim, read by every quality-sensitive consumer
    │   │
    │   ├── canvas/                    ── the R3F/WebGL scene tree ──
    │   │   ├── WorkspaceCanvas.tsx         mounts <Canvas> + QualityTierProvider + TierGovernor + SuperbrainScene; bridges GPU-loss/lifecycle events onto the bus
    │   │   ├── SuperbrainScene.tsx         scene root: lifecycle/posture/camera/uniform state machine; subscribes to cognitionBus; composes all children
    │   │   ├── BrainPointField.tsx         the fused brain+spine point-cloud (primary "points" being); reacts to phaseWeather + 'hesitation'
    │   │   ├── NodeLattice.tsx             interior supercomputer node-lattice; fetches on 'telemetry', flares hubs on other events
    │   │   ├── CommandNerve3D.tsx          the command bar rendered as a live 3D nerve-tube (dock → conus)
    │   │   ├── MaterializationLayer.tsx    orchestrates materialized work-surfaces; ingests completion-reflex + code-emission bus events
    │   │   ├── MaterializedTab.tsx         one materialized work-surface (code/input-echo/approval prompt), seated on a spine vertebra
    │   │   ├── AnatomicalConductorOverlay.tsx   vertebra-role signal beads
    │   │   ├── AttentionConductionPulse.tsx     traveling pulse when attention transfers between tabs
    │   │   ├── CompletionMemoryBead.tsx     completed-reflex/task memory-bead VFX
    │   │   ├── ReabsorptionParticles.tsx    particle stream from a retracting tab back into the brain
    │   │   ├── CorticalSignals.tsx          animated "thought-wave" shader across the cortex surface
    │   │   ├── BodySpeech.tsx               streaming reply as luminous troika <Text>, polling replyVoiceBus every frame
    │   │   ├── MemoryGalaxy.tsx             every real pheromone trail as a persistent background star; re-syncs on 'telemetry'
    │   │   ├── MemoryHalo.tsx               pending fact-proposal motes orbiting the cortex (supervised approve/reject)
    │   │   ├── RegionPins.tsx (+.test)      anatomical callout pins — gated off via hardcoded `SHOW_REGION_PINS=false` (see §4)
    │   │   ├── CosmicBackground.tsx         deep-space starfield/background shader; freezes on 'approval-required'
    │   │   ├── KnowledgeHorizon.tsx         photographic deep-space sky dome, mounted only when `sky==='layered'`
    │   │   ├── NeuralAura.tsx               membrane/nucleus glow shells (mesh-mode brain)
    │   │   ├── OrganSurface.tsx             alternate hand-painted "organ" flesh-texture brain surface
    │   │   ├── AccretionCore.tsx            mesh-mode accretion-disc VFX, pulses on 'knowledge-acquired'
    │   │   ├── CognitiveGrasp.tsx           mesh-mode recall-stream glints; publishes 'burst' on trail resolution
    │   │   ├── NervousSystem.tsx            mesh-mode nerve-tree/spine geometry; driven by 'voice-speaking'
    │   │   ├── PostFX.tsx                   post-processing chain (Bloom → ChromaticAberration → AgX tonemap → Vignette → Noise)
    │   │   ├── TierGovernor.tsx             in-Canvas PerformanceMonitor DPR relief valve (never changes geometry/palette)
    │   │   ├── WebGLErrorBoundary.tsx       React error boundary wrapping the Canvas
    │   │   ├── FallbackScene.tsx (+.css)    non-WebGL 2D fallback
    │   │   ├── CorticalNerve.tsx            DEAD — see §3
    │   │   ├── HorizonGlow.tsx              DEAD — see §3
    │   │   └── IdentityReadout.tsx          DEAD — see §3
    │   │
    │   └── ui/
    │       ├── ApprovalPanel.tsx           the DOM decision surface (diff/command summary + Authorize/Reject)
    │       ├── BootSequence.tsx (+.module.css)   fullscreen kernel-boot overlay; publishes 'synthesis'/"GAGOS ONLINE" once
    │       ├── SwarmHUD.tsx                minimal read-only ant-colony swarm-turn overlay (mounted in GagosChrome.jsx)
    │       ├── SuperbrainHUD.tsx           DEAD (unmounted legacy 2D HUD) — see §3
    │       └── CyberCursor.tsx (+.module.css)   DEAD — see §3
    │
    └── lib/                            ── ~90 modules, pure logic + bus/adapter plumbing ──
        ├── cognitionBus.ts             the event bus itself: subscribeCognition/publishCognition (§2)
        ├── aiosAdapter.ts              backend I/O binding: SSE parsing → cognitionBus translation (~35 publish sites)
        ├── organismPhaseBus.ts / conversationPhaseBus.ts    lifecycle-phase handoff (React → useFrame scene root)
        ├── replyVoiceBus.ts            reduces 'voice-speaking' → {phase, text} for BodySpeech
        ├── funnelAnchorBus.ts / stemAnchorBus.ts   3D→DOM screen-space anchor projections for the command dock
        ├── surfaceDialBus.ts           live operator tuning dial for surface materials
        ├── spineFusionBus.ts           publishes the spine→brain-cloud weld transform
        ├── swarmHUDStore.ts            reactive view of ant-colony swarm SSE frames
        ├── sessionId.ts / activeBrain.ts   server session id; active-brain readout formatting
        ├── metricsStore.ts / outcomeImprint.ts / phaseWeather.ts / turnMetabolism.ts / completionReflex.ts   bus-reducing derived-state singletons ("reduce once, poll every frame")
        ├── lifecycleStateMachine.ts / organismLifecycle.ts / livingOrchestrator.ts / bodyPosture.ts / beingMode.ts   posture/lifecycle derivation
        ├── spineAnatomy.ts / spinePointField.ts / anatomicalConductor.ts / anatomicalRootSystem.ts / spinalRootActuator.ts / vertebraConductorRoots.ts / attentionConduction.ts   anatomy/geometry
        ├── livingWorkspaceLayout.ts / materializedSurface{Anchors,Pose,Skin,TextPreview}.ts / organMaterialState.ts / surfaceShapeGrammar.ts   materialized-tab layout/skin
        ├── brainMaterial.ts / brainScene.ts / pointFieldSampler.ts / pointFieldMaterial.ts / pointFieldLifecycle.ts / seededRandom.ts   rendering plumbing
        ├── intentRouting.ts            regex work-intent classifier (frontend-side pre-routing)
        ├── tabStore.ts                 materialized-tab CRUD store
        ├── gagosDial.ts                DEAD — see §3
        └── soundEngine.ts              LIKELY DEAD — see §3 (only consumer is the dead SuperbrainHUD)
```

---

## 2. How It Works End to End

This traces a chat message from the DOM chrome (`GagosChrome.jsx`) through the backend and
back out to the 3D scene. GAGOS has **two** backend entry points for a chat turn, and the
frontend chooses between them:

- **`POST /api/v1/chat`** (`main.py:4030`, handler `chat()`) — the lean, no-tool-loop
  conversational path ("the GAGOS voice mind"). This is what `GagosChrome.jsx:719` hits via
  `sendVoiceTurn()` (`aiosAdapter.ts:666-724`) for ordinary conversation.
- **`POST /api/generate`** (`main.py:2994`, handler `generate()`) — the full memory-augmented,
  tool-calling agent loop. The frontend's own intent classifier (`lib/intentRouting.ts`) and the
  backend's `POST /api/v1/intent/preview` → `_classify_intent()` (`main.py:1241`) resolve a
  message to a command/code/swarm/browse intent; when the resolved intent needs tool use,
  file edits, command execution, or a multi-agent swarm, the request goes here instead.

The steps below follow the `/api/generate` path since it exercises the full pipeline the
question asks about (routing → tool-loop → security → verification → memory/telemetry →
cognition-bus fan-out → 3D render). The `/api/v1/chat` path shares the same edge middleware,
routing, recall, and cognition-bus fan-out, but skips the tool loop, security-zone
classification, and verification steps.

### Step 1 — Edge middleware (every request, both endpoints)

1. `bind_request_context()` (`main.py:348`) stamps an `x-request-id` and binds structlog
   context (request id, method, path, a hashed session id pulled from the cookie or body).
2. `require_api_token()` (`main.py:449`) is the auth gate: it protects `/api/*` and docs paths,
   enforces Bearer-token comparison via `secrets.compare_digest`, falls back to loopback-only
   access when no token is configured, and blocks the docs UI entirely when off-loopback with
   `ENABLE_DOCS` false. `_real_client_ip()` (`main.py:410`) resolves the true client IP,
   honoring `X-Forwarded-For` only when `TRUST_PROXY_HEADERS` is set and the peer is a
   `TRUSTED_PROXIES` entry.
3. `endpoint_rate_limit()` (`main.py:558`) calls `_check_endpoint_rate_limit()`
   (`main.py:529`) — a per-path/per-IP sliding-window limiter covering approval, execute,
   terminal, council, voice, policy, pheromone/surface, and rollback endpoints.

### Step 2 — Endpoint entry, input safety, routing

4. `generate()` (`main.py:2994`) validates input length and prompt-injection via
   `_check_prompt_injection()` (`main.py:3989`, which reuses `aios.security.gateway.classify()`
   and blocks only RED verdicts whose reason names prompt injection), infers the task via
   `aios.core.model_selector.infer_task`, and selects the chat client/model through
   `aios.core.router_wiring` (`_select_chat_client`, `_active_route`, `_provider_name`, etc.) —
   this is the multi-LLM router (local Ollama vs. Bedrock/Gemini/OpenAI-compat/Anthropic-direct,
   privacy-gated local-first by default).
5. Any previously issued approval token is redeemed here — the code explicitly **rejects raw
   approved payloads**, requiring a token, and resolves an in-flight approval-resume tail via
   `aios.runtime.turn_state`.

### Step 3 — Memory recall (pre-loop context assembly)

Inside the `event_stream()` generator, each recall step is surfaced to the frontend as an SSE
`step` frame (via `_sse()`/`_sse_writer()`, `main.py:2355/2376` — which escape embedded newlines
in the payload to prevent SSE-frame injection from LLM output):

6. Alignment interpretation (`aios.core.alignment.AlignmentInterpreter`,
   `apply_user_corrections`) plus an ask-pause if the interpreter is unsure of intent.
7. `Cerebellum` playbook pre-check (`aios.core.cerebellum.Cerebellum`) — a learned-reflex
   shortcut for previously-mastered procedural patterns.
8. Confidence gate (`aios.core.confidence_filter.gate`) — decides whether to proceed or pause
   for clarification based on calibrated confidence (`_calibrate_default_confidence()`,
   `main.py:2914`).
9. Sequential recall, each function pulling from a different memory tier:
   - `_recall_memory()` (`main.py:2667`) — hybrid BM25 + FAISS + decay search
     (`aios.memory.retrieval.hybrid_search`), gated through the full **Corrective-RAG (CRAG)**
     pipeline when `config.CRAG` is enabled: `evaluate_retrieval`/`refine_context`/
     `external_retrieve` (`aios.memory.crag`) with cloud/web/document sources and an optional
     LLM relevance judge (`_crag_cloud_source`, `_crag_web_source`, `_crag_document_source`,
     `_crag_llm_judge`, `main.py:2585-2666`).
   - `_recall_lessons()` (`main.py:2760`) and `_recall_skills()` (`main.py:2780`) — best-effort
     mistake/skill memory recall (`aios.memory.mistake`, `aios.memory.skills`).
   - `_recall_facts()` (`main.py:2480`) — semantic facts (`aios.memory.facts.SemanticFacts`)
     plus single-hop graph expansion and confidence-weighted inference chains.
   - `_recall_self_model()` (`main.py:2455`) — the grounded, verified-only self-model paragraph
     (`aios.memory.self_model.synthesize_self_model`).

### Step 4 — The agent tool-loop

10. `make_agent()` (`main.py:3406`) builds a `ToolAgent` (`aios/agents/tool_agent.py`) wired
    with two hooks: `_make_failure_hook()` (`main.py:2863`, records a mistake on tool failure)
    and `_make_confirm_hook()` (`main.py:2891`, promotes a pending lesson to verified on
    confirmed success). `make_cloud_agent()` (`main.py:3462`) builds the cloud-burst variant
    used for swarm work.
11. Depending on the request, the turn dispatches to `run_swarm()`
    (`aios/agents/swarm.py`, multi-caste concurrent run using `SwarmPatternMemory` from
    `aios/agents/swarm_patterns.py`), `run_role_pass()` (`aios/agents/role_pass.py`, a single
    scoped role), or a plain `make_agent().run()`.
12. Inside `ToolAgent`, each turn of the loop asks the selected LLM for the next action; tool
    calls are dispatched to `aios/agents/tool_handlers.py`, with `aios/agents/tool_loop_helpers.py`
    providing shared loop bookkeeping. Every tool call/result is wrapped by `_safe_iter()`
    (`main.py:3656`), which turns a mid-stream exception into an `error`+`done` SSE pair instead
    of silently killing the stream.

### Step 5 — Security gateway and sandboxed execution

13. Every command/edit the agent wants to perform is classified by
    `aios.security.gateway.classify()` — a **deterministic, fail-closed** RED/YELLOW/GREEN zone
    classifier (also exposed directly at `POST /api/v1/security/classify`, `main.py:2021`).
14. GREEN actions run immediately through `aios.core.executor.Executor` (a scope-constrained,
    rate-limited sandbox executor, provided via `get_executor()`, `main.py:705`).
15. YELLOW actions pause the loop: the main event-dispatch loop (`main.py:3665-3937`) emits a
    `human_required` SSE frame, issues an approval token for the pending edit/create/command via
    `aios.core.approvals.ApprovalStore`, records a `paused` outcome plus telemetry. The operator
    resolves it via `POST /api/v1/approval/req` (`main.py:2110`), which redeems the token and (if
    approved) lets `Executor` proceed.
16. RED actions are refused outright by `classify()` and never reach `Executor`, regardless of
    any approval token (see the hard invariant in §4).

### Step 6 — Verification

17. Each `tool_call`/`tool_result` event is provenance-gated for verify-evidence extraction, and
    the loop emits `verify_result` SSE frames as `aios.core.verifier.Verifier` checks outcomes.
18. `_verify_target_keys()`/`_verify_target_key()` (`main.py:2789/2820`) key verification
    evidence **per target file**, specifically so a passing sibling file can't mask an
    unresolved FAIL on a different file in the same turn.
19. `aios.core.verification_strength` (`VerificationStrength`, `strength_from_text`,
    `meets_promotion_floor`) computes how strong a piece of verification evidence is — this
    strength value gates every downstream memory-write in the next step.

### Step 7 — Outcome recording, memory writes, telemetry, audit

20. `record_outcome()` (`main.py:3506`) writes development/skill/curriculum/pheromone-reuse
    evidence — but only evidence at or above the **weakest authoritative verification strength**
    seen for that outcome (`meets_promotion_floor`), an explicit anti-laundering design so a
    weak/echo "green" can't mint a verified skill or lesson.
21. `_record_episode()` (`main.py:2750`) persists the turn to L2 episodic memory
    (`aios.memory.episodic.EpisodicMemory`), after secret-scrubbing via
    `aios.security.secret_scanner.scan_and_redact`.
22. `_index_turn()` (`main.py:2840`) embeds the completed Q→A turn into L3 semantic memory
    (`aios.memory.embeddings.VectorIndex`).
23. Every gated action (classify → execute → approve → verify) is appended to the tamper-evident
    audit hash chain via `aios.security.audit_logger.log_action()`, independently checkable at
    `GET /api/v1/audit/verify` (`main.py:2032`, `verify_chain()`).

### Step 8 — Turn completion and the Cortex Bus

24. On the `done` event, the loop persists the final answer, computes per-target
    verified_success/failure/unverified status, emits `skill.mastered` frames for any newly
    verified skill, clears the approval/turn-state, and emits the terminal `done` SSE frame.
25. `_append_turn_completed()` (`main.py:277`) then best-effort-appends a `turn.completed`
    observation onto the **Cortex Bus** (`aios.runtime.cortex_bus.CortexBus`) — but only if the
    bus was started at boot, which `lifespan()` (`main.py:183-263`) does conditionally
    (opt-in; see §4). When on, `CortexBusDispatcher` (`aios.runtime.cortex_bus_dispatcher`,
    poll_interval 0.25s, `_build_cortex_dispatcher()` at `main.py:267`) and
    `aios.runtime.self_model_handler.SelfModelHandler` consume it.
26. The whole generator is returned as `StreamingResponse(event_stream(), media_type=
    "text/event-stream")` — this is the SSE stream the frontend reads.

### Step 9 — Frontend: SSE → cognition bus fan-out

27. `lib/aiosAdapter.ts` parses the SSE stream (`readSse`) and translates every frame kind into
    a typed `CognitionEventType` (`lib/cognitionBus.ts:13-56` — 15 values: `knowledge-acquired`,
    `directive`, `burst`, `agent-dispatch`, `synthesis`, `approval-required`,
    `approval-resolved`, `telemetry`, `route`, `voice-speaking`, `verify`, `hesitation`,
    `reflex-recall`, `graph-recall`, `template-plan`), calling `publishCognition()` at roughly 35
    call sites (`aiosAdapter.ts:117-1252`) — e.g. `tool_call` → `agent-dispatch`, a verifier
    verdict → `knowledge-acquired`/`verify`, `human_required` → `approval-required`, a route
    frame → `route`, an audit-chain failure → `synthesis`.
28. `cognitionBus.ts:79-97` is a ~20-line synchronous pub/sub singleton: a `Set<Listener>`,
    `publishCognition()` iterates listeners in publish order, each wrapped in its own `try/catch`
    so one faulty subscriber can't sever the rest. There is no queueing, batching, or priority —
    pure fan-out, one event to every live subscriber.

### Step 10 — Fan-out consumers and 3D rendering

29. **3D scene subscribers**, each reacting to its own narrow slice of event types:
    `SuperbrainScene.tsx:1673` (thought-waves/camera pushes/approval holds),
    `BrainPointField.tsx:190` (`hesitation`), `CosmicBackground.tsx:135` (freezes on
    `approval-required`), `NodeLattice.tsx:695,867` (fetches on `telemetry`, flares hubs on other
    events), `MemoryGalaxy.tsx:165` (re-syncs on `telemetry`),
    `MaterializationLayer.tsx:107,115` (ingests completion-reflex + creates a
    `MaterializedTab.tsx` on code-emission events), mesh-mode-only subscribers
    (`AccretionCore.tsx:189`, `NervousSystem.tsx:401`, `CognitiveGrasp.tsx:398`).
30. **Derived-state singletons** ("reduce once, poll every frame" pattern): `lib/metricsStore.ts:125`,
    `lib/outcomeImprint.ts:161`, `lib/phaseWeather.ts:139`, `lib/replyVoiceBus.ts:34`,
    `lib/turnMetabolism.ts:216` each subscribe once and reduce the event stream into a small
    piece of state that other components read every `useFrame` tick rather than subscribing
    directly. `BodySpeech.tsx` is the clearest example: it polls `replyVoiceBus` every frame to
    render the being's streaming reply as luminous troika `<Text>` near the cortex.
31. `components/QualityTierProvider.tsx:125` also subscribes: `directive` sets a "generating"
    flag that dims one render-quality tier for the duration of the turn; `synthesis`/
    `approval-required` clear it.
32. **DOM chat itself** (`workbench/GagosChrome.jsx`) is not just a consumer — it's the other
    major publisher, emitting `voice-speaking` at every phase of a turn (`question`, `reply` per
    streamed chunk, `reply-complete`, `error`, `stopped`) and `directive` events
    (`GagosChrome.jsx:572-900`), while separately reading back `route`/`verify` events at
    `GagosChrome.jsx:369,391`. `workbench/voiceSpeak.ts` publishes its own `voice-speaking`
    events (`speaking`/`speaking-complete`) for the TTS speak-aloud loop.
33. Finally, `SuperbrainScene.tsx` composes every canvas child (`BrainPointField`, `NodeLattice`,
    `MaterializationLayer`, `CorticalSignals`, `PostFX`, etc.) inside `WorkspaceCanvas.tsx`'s
    `<Canvas>`, applying all the derived state each `useFrame` tick to produce the actual WebGL
    render the operator sees — the single point where routing, the tool-loop, security,
    verification, and memory all converge back into one continuously-animated 3D being.

---

## 3. Confirmed Dead / Unused Code

Everything in this section was independently re-derived from scratch (fresh greps, a
from-scratch AST-based import-graph script, `git blame`, manual chain-tracing) — not merely
copied from an earlier hunt's narration — and reproduced with **zero refutations**. Nothing
below should be treated as a judgment call; all are safe deletion candidates pending a final
sanity pass, but see the caveats inline for the two flagged as "likely" rather than outright
dead.

### Backend

- **`aios/core/self_consistency.py`** (entire module: `run_self_consistency`,
  `ConsistencyResult`, `_best_passing_index`, `_best_failing_index`) — only referenced by
  `tests/test_self_consistency.py`; zero in-repo importers by independent AST analysis;
  `aios/core/verifier.py` never imports it back (only a `TYPE_CHECKING`-only forward reference
  exists inside `self_consistency.py` itself). **Corroborating evidence**: `aios/config.py:414-415`
  defines `SELF_CONSISTENCY`/`SELF_CONSISTENCY_N` flags (`AIOS_SELF_CONSISTENCY` env vars) that
  are never read or branched on anywhere in the codebase — an authored-but-never-wired config
  flag pointing at authored-but-never-wired code.

- **`aios/runtime/worktree_backend.py`** (entire module: `WorktreeBackend`, `WorktreeLane`,
  `InvalidLaneIdError`, `LaneExistsError`, `LaneNotFoundError`) — only referenced by
  `tests/test_worktree_backend.py`; zero in-repo importers. `WORKTREE_BACKEND`/`WORKTREE_ROOT`
  config flags in `aios/config.py` are defined but never read outside `config.py` itself.
  `aios/runtime/spawner.py:70` hardcodes `ControlledSubprocessBackend` unconditionally, with no
  branch that could ever construct a `WorktreeBackend`. (One incidental grep hit in
  `docs/superpowers/specs/2026-06-27-sovereign-ai-os-roadmap.md` is a mention of a *different*,
  future-planned `GitWorktreeBackend` — a coincidental substring match, not a real reference.)
  Introduced in the same commit as `self_consistency.py` (`91639dc`, "sovereign roadmap phases
  3B-8"), consistent with a pair of authored-but-never-wired features.

- **`aios/council/queen_service.py::SecurityQueenService`** — the `QueenService` ABC /
  `QUEEN_SERVICES` registry / `register_service()` / `unregister_service()` machinery is
  genuinely live and reachable (via `aios/api/routes/sovereignty.py`'s
  `/api/v1/council/services*` endpoints), but no production code path ever calls
  `register_service(SecurityQueenService())` — the only hits for
  `register_service`/`SecurityQueenService`/`QUEEN_SERVICES` outside tests are the definition
  site and `aios/council/__init__.py`'s re-export. `aios.api.main.lifespan()` (the only startup
  hook) starts the Cortex Bus/dispatcher/self-model-handler but never touches `QUEEN_SERVICES`.
  **Net effect**: `QUEEN_SERVICES` stays permanently `{}` at runtime, so the wired
  `/api/v1/council/services/{name}/start|stop` endpoints operate on an always-empty registry.

### Frontend

- **`components/canvas/CorticalNerve.tsx`** — orphaned; `MaterializationLayer.tsx:454` contains
  the literal comment documenting its removal.
- **`components/canvas/HorizonGlow.tsx`** — orphaned (no render site anywhere).
- **`components/canvas/IdentityReadout.tsx`** — orphaned; removed alongside `BrainstemIntake` in
  commit `231dcd5`.
- **`components/ui/CyberCursor.tsx`** + **`CyberCursor.module.css`** — orphaned custom
  cursor component, no mount site.
- **`components/ui/SuperbrainHUD.tsx`** — the component/default export is unreachable (no JSX
  render site, no default-export import anywhere); `WorkspaceCanvas.tsx:104` has a corroborating
  comment ("removed 2D HUD, so there are no setters here"). Its `CognitiveMode` **type** is
  still legitimately re-exported and used elsewhere via type-only imports (in `NeuralAura.tsx`,
  `WorkspaceCanvas.tsx`, `SuperbrainScene.tsx`) — only the component itself is dead, not the
  whole file's exports.
- **`lib/gagosDial.ts`** — orphaned dev-console tuning module, no live import.
- **`lib/soundEngine.ts`** — *likely* dead rather than confirmed-orphaned: it is unit-tested and
  its logic is intact, but its only application-level consumer is the already-dead
  `SuperbrainHUD.tsx`, so it never actually runs in the live app.
- **`frontend/src/utils/index.js`** — orphaned barrel export; the one real consumer
  (`GagosChrome.jsx`) imports `sanitizeHtml` directly from `../utils/sanitizeHtml`, not through
  this barrel.

---

## 4. Known Architectural Notes

### Opt-in vs. default-on subsystems

| Subsystem | Status | Gate |
|---|---|---|
| Cortex Bus + `CortexBusDispatcher` + `SelfModelHandler` | **opt-in**, default OFF | started conditionally inside `lifespan()` (`main.py:183-263`) |
| Vector injection shield (`aios.security.injection_shield.VectorInjectionShield`) | **opt-in** | conditionally installed in `lifespan()` (`main.py:206`) |
| Corrective-RAG (`aios.memory.crag`) | **opt-in** | `config.CRAG` |
| Council reasoning (LLM planning/reasoning inside missions) | **opt-in** | `AIOS_COUNCIL_REASONING` |
| Worker reasoning (think→act→verify→repair loop) | **opt-in** | `AIOS_WORKER_REASONING` |
| Council mission origination (chat/dashboard → deliberate → King approve) | **opt-in** | `AIOS_COUNCIL_ORIGINATION` |
| CritiqueQueen | **opt-in** | `config.COUNCIL_CRITIQUE` |
| Self-consistency verification pass | authored, **never wired** (dead — see §3) | `AIOS_SELF_CONSISTENCY` / `AIOS_SELF_CONSISTENCY_N` (read nowhere) |
| Worktree-isolated lane backend | authored, **never wired** (dead — see §3) | `WORKTREE_BACKEND` / `WORKTREE_ROOT` (read nowhere outside `config.py`) |
| Frontend mesh-mode being (`AccretionCore`, `CognitiveGrasp`, `NervousSystem`, `NeuralAura`, `OrganSurface`) | **opt-in escape hatch**, not the default runtime path | `?being=mesh` URL param (per `lib/beingMode.ts`'s own comment: "retained only as an internal escape hatch") |
| `RegionPins.tsx` | wired but **disabled** | `SuperbrainScene.tsx:72` hardcodes `const SHOW_REGION_PINS = false` with no env/URL override |
| Sound engine (`lib/soundEngine.ts`) | nominally "sovereign/opt-in" by design, but **effectively inert** | its only consumer is the dead `SuperbrainHUD.tsx` (see §3) |

### Hard security invariants (must never be weakened)

- **RED-zone hard block.** `aios.security.gateway.classify()` is a deterministic, fail-closed
  RED/YELLOW/GREEN classifier. RED actions are refused outright and never reach `Executor` —
  this holds even after a human approval, because approval tokens are only ever issued/redeemed
  for YELLOW-classified actions in the first place. This is stricter than a typed-token
  "approve anything" model by design; do not introduce a path that lets an approval token
  override a RED verdict.
- **Fail-closed auth off-loopback.** `require_api_token()` (`main.py:449`) requires a
  Bearer token (compared via `secrets.compare_digest`, not `==`) for any non-loopback client;
  loopback-only access is the sole exception, and even the OpenAPI docs are blocked off-loopback
  when `ENABLE_DOCS` is false.
- **Fail-closed CORS.** `_validate_cors_origins()` (`main.py:306`) explicitly rejects `"*"` and
  host-less origin entries.
- **Approval-token redemption only, never raw payload trust.** `generate()` explicitly rejects
  raw "approved" payloads submitted without a valid token — the token, not client-asserted state,
  is the sole proof of human authorization.
- **Verification anti-laundering.** `record_outcome()` (`main.py:3506`) gates every
  development/skill/curriculum/pheromone-reuse memory write behind the **weakest** authoritative
  verification strength seen for that outcome (`aios.core.verification_strength.
  meets_promotion_floor`), and `_verify_target_keys()`/`_verify_target_key()` key evidence
  **per target file** so a passing sibling file can never mask an unresolved failure elsewhere
  in the same turn. Do not let a single "verified" tag apply across multiple targets.
- **Secret scrubbing before persistence.** `_record_episode()` runs
  `aios.security.secret_scanner.scan_and_redact()` before anything is written to episodic
  memory.
- **Tamper-evident audit chain.** Every gated action is hash-chained via
  `aios.security.audit_logger.log_action()`, independently checkable via `verify_chain()`
  (`GET /api/v1/audit/verify`) and externally anchorable (`aios.audit_anchor`,
  `GET/POST /api/v1/audit/anchor*`).
- **SSE-frame-injection resistance.** `_sse()` (`main.py:2355`) escapes embedded newlines in
  streamed payloads specifically so LLM-generated output can't forge a fake SSE frame boundary
  in the stream sent to the frontend.
- **Container-only self-apply.** `get_self_apply_engine()`'s nested `project_root_runner()`
  (`main.py:734`) refuses to run on the bare host and only runs `pytest tests/` from the
  project root inside the sandboxed executor — self-modification cannot escape the container.

### Genuine gaps and inconsistencies

- **A fully-wired HUD that never runs.** `components/ui/SuperbrainHUD.tsx` subscribes to
  essentially the entire `cognitionBus` event surface (terminal feed, directive input, sound
  toggle, sky/surface topbar) and even publishes its own `directive` events from its submit
  handler — but the component is never mounted anywhere in the live app (§3). It's a complete,
  working HUD that is fully isolated from the runtime it was built to observe: all of its bus
  wiring is dead weight until (if ever) it's re-mounted. Anyone extending `cognitionBus.ts`
  should be aware this file exists and *looks* like a live consumer to search when they grep for
  usages, but currently is not one.
- **An always-empty service registry.** The `/api/v1/council/services/{name}/start|stop`
  endpoints in `routes/sovereignty.py` are fully wired against `aios.council.queen_service.
  QUEEN_SERVICES`, but since nothing ever calls `register_service()` at startup, the dict is
  permanently empty — these endpoints are live code operating on nothing (§3).
- **Repeated "authored config flag, never wired" pattern.** Both `SELF_CONSISTENCY*` and
  `WORKTREE_BACKEND`/`WORKTREE_ROOT` follow the identical shape: a config flag pair defined in
  `aios/config.py`, exported, and never read anywhere else. This is a recognizable house pattern
  worth watching for during future feature work — a config flag existing is not evidence a
  feature is wired.
- **`aios/probe_common.py` sits oddly inside the package boundary.** It has zero importers from
  within `aios/` itself (unreachable from the FastAPI app or the `aios.__main__` entry point),
  yet it's a real, actively-maintained shared helper for the standalone evidence/probe tooling
  layer (`tools/daily_use_probe.py`, `tools/endurance_tester.py`,
  `tools/experience_accumulator.py`, `tools/golden_mission_runner.py`,
  `curriculum_evidence_driver.py`). It is **not dead** — do not delete it — but its location
  inside the `aios/` package rather than alongside the `tools/` scripts that consume it is an
  architectural inconsistency worth a deliberate call (move it, or accept `aios/` as also hosting
  shared tooling code).
- **Subprocess dispatch is invisible to static import analysis.** Council workers are launched
  via a runtime string, not a static import: `aios/council/__init__.py`'s
  `CouncilOrchestrator` → `aios/runtime/spawner.py`'s `WorkerSpawner` →
  `aios/runtime/backends.py`'s `ControlledSubprocessBackend`, which launches the module string
  `"aios.runtime.worker_entry"` via `asyncio.create_subprocess_exec`. `worker_entry.py` then
  statically imports `worker_api.py` and `intelligence_gateway.py` (which imports
  `budget_guard.py`). Because the launch is a string, not an `import`, a naive AST-based
  reachability scan flags `worker_entry.py` (and everything only reachable through it) as an
  orphan — it isn't. Any future dead-code hunt needs to special-case this subprocess boundary or
  it will produce a false positive on the entire worker call chain.
- **A dead branch inside a live, actively-used file.** `SuperbrainScene.tsx:1690-1694` gates its
  reply-glow bump behind `event.source === 'reply'`, but no publisher anywhere in the codebase
  ever sets `source: 'reply'` on a `voice-speaking` event — real publishers use `source: 'gagos'`
  (`GagosChrome.jsx`) or `source: 'voice-tts'` (`voiceSpeak.ts`). This branch is unreachable
  today; it's not a file-level orphan (the file is very much alive) but is worth fixing or
  removing so the reply-glow behavior matches what the code appears to say it does.

---

## Needs Human Review

These items surfaced during the verification pass but were explicitly **not** classified as
dead — they require a human (not an automated pass) to decide whether any action is warranted:

- **`aios/probe_common.py`** — confirmed to have zero importers from inside `aios/` itself, but
  real, currently-maintained callers exist in `tools/` scripts and `curriculum_evidence_driver.py`
  outside the package. Correctly *not* a deletion candidate; the open question is purely about
  where this shared code should live, not whether it's used. (See the gap entry above.)
- **Subsystem file-count bookkeeping.** The original dead-code hunts' summary paragraphs quoted
  file counts per subsystem (e.g. "`aios/core/` — 29 of 31 files", "`aios/memory/` — 22 files",
  "`aios/council/` — 12 files") that don't cleanly reconcile with a fresh `find` over the
  directories today (e.g. `core/` currently has 34 `.py` files including `__init__.py`,
  `memory/` has 24, `council/` has 13 including `reasoning.py` plus two `__init__.py` files).
  This reads as an arithmetic/prose slip in the summary narration rather than a sign of a missed
  dead file — an independently-rebuilt reachability graph, built without trusting the original
  counts, landed on the exact same two backend dead files and no others. Flagged here only so a
  future pass doesn't waste time trying to reconcile stale counts against disk.
