# Intelligence Call Inventory

## Goal
Inventory every active local and cloud model call and establish one future canonical path.

## Target Architecture

The single canonical path for all intelligence queries moving forward is:

```text
Caller
→ ModelCallRequest
→ PrivacyBroker
→ IntelligencePolicy
→ Local Workforce Admission or Frontier Hiring
→ Provider Adapter
→ ModelCallRecord
→ Cortex Observation
```

Currently, this architecture is partially implemented in `aios/application/models/model_router.py` (`ModelRouter`), which handles privacy policy evaluation, provider selection, fallback, and `ModelCallRecord` emission for completion queries.

## Call Path Inventory

### 1. `aios/agents/tool_agent.py`
- **Call:** `self.llm.chat(convo, tools=specs, model=self.model)`
- **Role:** Autonomous execution / Tool loop.
- **Classification:** **COMPATIBILITY**
- **Notes:** Consumes an injected client. Currently instantiated directly via `BedrockClient()` / `GeminiClient()` in `generate_pipeline.py`. Must migrate to receive a client governed by `ModelRouter` and `PrivacyBroker`.

### 2. `aios/application/turns/generate_pipeline.py`
- **Call:** `BedrockClient()` / `GeminiClient()` instantiation and usage for `cloud_client`.
- **Role:** Turn generation pipeline cloud-bursting.
- **Classification:** **UNVERIFIED / DEAD**
- **Notes:** Directly bypasses all policy, privacy broker, and routing architecture by instantiating clients from raw config. Must be eliminated and migrated to canonical hiring broker.

### 3. `aios/api/main.py`
- **Call:** `chat_client.chat(messages, tools=None, model=model)`
- **Role:** Direct API `/api/v1/chat` endpoint.
- **Classification:** **COMPATIBILITY**
- **Notes:** Uses `_select_chat_client` which does some privacy filtering but does not use the full unified canonical record emission and hiring broker path.

### 4. `aios/api/turn_pipeline.py`
- **Call:** `client.chat(...)` and `get_ollama_client().chat(...)`
- **Role:** Chat generation and title generation.
- **Classification:** **COMPATIBILITY**
- **Notes:** Uses `_select_chat_client` or hardcoded local client. Needs migration to the unified ModelRouter architecture.

### 5. `aios/core/failover.py` & `aios/core/router_wiring.py`
- **Call:** `client.chat(...)` and `ollama.chat(...)`
- **Role:** Meta-model routing picker and failover adapters.
- **Classification:** **CANONICAL (Provider Adapters)**
- **Notes:** These are the low-level provider adapters and routing primitives. They are valid within the boundary of the `ModelRouter` but should not be called directly by application code.

### 6. `aios/agents/reflection_agent.py`, `self_analysis_agent.py`, `aios/core/alignment.py`, `aios/core/planner.py`, `aios/council/reasoning.py`
- **Call:** `llm.complete(...)`
- **Role:** Specialized reasoning and generation tasks.
- **Classification:** **COMPATIBILITY**
- **Notes:** Uses injected completion clients. Need to be wired to consume the `ModelRouter.complete()` interface or a wrapped interface that enforces the boundary.

### 7. `aios/runtime/intelligence_gateway.py`
- **Call:** `client.complete(...)`
- **Role:** Reasoning gateway for Council Runtime workers.
- **Classification:** **COMPATIBILITY**
- **Notes:** This is a partial implementation of governed intelligence that predates `ModelRouter`. It applies `BudgetGuard` and `SecretPolicy` but should be unified with the `ModelRouter` / `PrivacyBroker` path.

## Approved Provider-Adapter Allowlist

Moving forward, only the following low-level provider adapters are approved. They must only be instantiated and invoked by the canonical `ModelRouter` (or its immediate routing sub-components), never directly by application layers.

1. `OllamaClient` (`aios.core.llm`)
2. `BedrockClient` (`aios.core.bedrock`)
3. `GeminiClient` (`aios.core.gemini`)
4. `OpenAICompatClient` (`aios.core.openai_compat`)
5. `AnthropicDirectClient` (`aios.core.anthropic_direct`)

## Migration Order

To safely converge all intelligence calls to the canonical boundary:

1. **Phase 1: Eradicate Unverified Cloud Bursting.** Refactor `generate_pipeline.py` to remove direct instantiation of `BedrockClient` and `GeminiClient`. Use the canonical `ModelRouter` or `_select_chat_client` temporarily.
2. **Phase 2: Unify Completion Calls.** Migrate `IntelligenceGateway`, `ReflectionAgent`, `Planner`, and `SelfAnalysisAgent` to use `ModelRouter.complete()` directly, passing appropriate `ModelCallRequest` objects with privacy requirements.
3. **Phase 3: Extend ModelRouter for Chat.** Add `chat()` capabilities to `ModelRouter` alongside `complete()`, implementing the same `ModelCallRecord` and `PrivacyBroker` emission for interactive tool-use models.
4. **Phase 4: Migrate ToolAgent and TurnPipeline.** Switch `ToolAgent` and the main `/api/v1/chat` pipeline to use `ModelRouter.chat()`.
5. **Phase 5: Enforce the Boundary.** Enable strict architectural tests that fail if any application code imports or invokes a provider adapter directly.
