# JARVIS VOICE MIND — plan + architecture (docs-before-code)

> **Initiative (2026-06-14, operator):** build a true-"Jarvis" VOICE conversation loop — the operator
> SPEAKS, the system transcribes, runs it through the existing multi-LLM router with a **Hinglish**
> (English/Hindi mixed) + **personalization** system prompt, responds, and SPEAKS back (TTS), with the
> response also driving the glowing 3D brain (the "goosebumps in a dark room" core, now unfrozen but
> CHERISHED — enhance, never replace).
>
> **Locked decisions:** (1) first front = **the mind (backend)**; (2) talk-back = **voice now (true
> Jarvis)**; (3) language + all-coding knowledge = **leverage the frontier LLMs + RAG + memory** (NOT
> training a model — the LLMs already know English/Hindi/Hinglish + every coding language).

## The honest reframe (why this is weeks, not months)
The frontier models the router already serves (Gemini, Bedrock/Claude, local qwen2.5-coder/llama3.1)
ALREADY know the languages and all coding. We do NOT "feed grammar lessons" or "raise a brain from
zero." The "5-year-old brain that explores + grasps" is the EXISTING curriculum + skills + stigmergy +
memory loop (brain-growth already evidenced). So the real build is the layers ON TOP:
1. **Hinglish soul** — a conversational system prompt + few-shot in the operator's mixed voice.
2. **Understand-me-deeply** — personalization from `SemanticFacts` (a living model of the operator).
3. **Voice I/O** — STT (speak to it) + TTS (it speaks back) = the Jarvis loop.
4. **Prompt-writer skill** — a meta-prompting capability (later slice).
5. **RAG knowledge grounding** — doc-anchored coding answers (later slice).

## Architecture map (the real seams — from the backend exploration)
- **Conversational turn:** reuse the chat client + router via `_select_chat_client()` (`aios/api/main.py`
  ~1253) and the SSE helper `_sse()` (~1363). The existing `POST /api/generate` (~1556) runs the full
  agentic TOOL/coding loop — too heavy for chat — so add a LEAN conversational endpoint beside it.
- **System prompt + context injection:** `aios/agents/tool_agent.py` SYSTEM_PROMPT (~148) +
  memory-context concat (~649). The Hinglish/personalization prompt is injected the same way.
- **Personalization facts:** `aios/memory/facts.py` `SemanticFacts.add_fact()` (~50) /
  `.facts_for(subject="operator")` (~145); fact endpoint `POST /api/v1/memory/facts` (~673).
- **Conversation state:** `aios/memory/conversation.py` `ConversationStateStore.save/get` (~40/59).
- **Router privacy gate:** `aios/core/router.py` `Policy.cloud_tasks` (~139) — local-first by default;
  respect it (voice chat stays local unless the operator opens cloud).
- **Frontend dispatch + stream:** `frontend/src/superbrain/lib/aiosAdapter.ts` `sendDirective()` (~359)
  + `streamTurn()` (~225) parse SSE → `cognitionBus`. Voice transcript is injected here; TTS is
  triggered on streamed text.
- **Brain reaction:** `cognitionBus` publish/subscribe (`cognitionBus.ts` ~56/63); `soundEngine.ts`
  already rides the bus. A new `voice-speaking` event makes the 3D brain pulse while TTS plays.
- **Today there is NO STT/TTS** — only synthesized `soundEngine`. Voice I/O is net-new.

## Slice plan (ordered, each shippable + verifiable)
- **Slice 1 — Hinglish chat backend. DONE (2026-06-14, commit `13490c1`, branch `feat/jarvis-voice`).**
  `POST /api/v1/chat {transcript, sessionId, modelId?}` in `aios/api/main.py`: `CHAT_SYSTEM_PROMPT`
  (Hinglish persona, conversation-not-forge), `_operator_facts_block()` (real `SemanticFacts` only,
  dormant when none), routes via `_select_chat_client` (local-first gate intact, cloud never forced),
  one chat-client call `tools=None` (no ToolAgent loop), streams SSE `route -> text_chunk -> done`,
  persists the turn. `tests/test_chat.py` (6 tests). Gate: import OK, **pytest 551 passed / 1 skipped**,
  both review lenses clean. Curl-testable now. (Non-blocking future polish noted by review:
  `_select_chat_client` hardcodes `require_tools=True` on the `auto` branch — fail-soft, irrelevant to
  this no-tools endpoint, optional later.)
- **Slice 2 — Voice I/O frontend (the goosebumps loop).** Mic capture → STT → Slice-1 endpoint →
  stream → TTS speak-back → the brain pulses while speaking (a `voice-speaking` bus event). A
  push-to-talk control in the HUD.
- **Slice 3 — Personalization deepening.** Auto-distill durable facts about the operator from
  conversations (with approval) → richer "model of you" each turn.
- **Slice 4 — Prompt-writer skill + RAG grounding.** Meta-prompting module + doc retrieval.

## STT / TTS engine recommendation
- **MVP: browser-native** — Web Speech `SpeechRecognition` (hi-IN/en-IN locales) for STT +
  `SpeechSynthesis` for TTS. Zero install, works in Chrome now, fastest path to the goosebumps loop.
  Trade: Chrome's STT uses Google's cloud (a privacy note, fine for an MVP).
- **Hardening (later): local** — `faster-whisper` (STT) + `piper` (TTS) for private, offline,
  better-voice Jarvis. Heavier (RAM + install); layer in once the loop is proven. Keeps local-first.

## Laws that still hold
Leverage LLMs (no training). Respect the router privacy gate (local-first). Honesty: personalization
uses REAL facts, never fabricated. The glowing brain is the cherished core — enhance toward Jarvis,
keep reversibility (branch/tags/before-after/operator's eye). Keep THIS doc + Tier-1 docs + RESUME
current as each slice lands ([[doc-currency-convention]]).
