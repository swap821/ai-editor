# One gateway, measured

*2026-10-12, updated 2026-10-28. The production scoreboard's `one_gateway`
gate: "every model call through the one gateway".*

## What was true before

Organ 32's gateway (`aios/application/intelligence/gateway.py`) is where a model
call is meant to pass. Passing it means four checks:
- the emergency stop;
- identity and constitution binding;
- a recorded representative context;
- output redaction.

There were two kinds of evidence that every call passed it:

- **Construction was enforced.**
  `tests/architecture/test_intelligence_boundary.py` keeps provider classes out
  of application code.
- **Calls were claimed in prose.** Organ 32's ledger row listed each path that
  had been migrated. Nothing counted the calls themselves.

## What measures it now

| Piece | What it does |
|---|---|
| `aios/core/model_calls.py` | Every provider adapter (Ollama, Bedrock, Gemini, OpenAI-compatible, Vertex, Anthropic) calls `observe()` once per request, as it leaves. Each gateway entrance runs the caller's model call inside a scope. The record says which entrance it came through (`null` means none) and which code asked. It holds no prompt, no output and no key. It is written to `<data>/model_calls/<date>.jsonl` and kept for 30 days. |
| Gateway entrances | The five entrances are `route`, `stream`, `stream_structured`, `stream_compatibility` and `complete_compatibility`. Streams hold the scope only while they advance, so a consumer's own calls between chunks are never credited to the gateway. |
| `tools/model_call_inventory.py` | Drives the **real app** with its **real adapters** in a child process on a throwaway data directory. Ollama is a fake HTTP server, so no model is involved. Bedrock is a recording transport. It reports every call's entrance. |
| `tools/production_readiness.py` → `one_gateway` | Reads this machine's ledger for the last 7 days. It PASSes only if every production call came through an entrance. |

**Two integrity checks keep the inventory honest:**
- Every request the fake server and the transport **received** must have a
  ledger record. A call the ledger missed would otherwise read as no call.
- A surface that made no model call is **not reached**, never clean.

## 2026-10-28: real use found a call the inventory missed

**The operator's own ledger held ungated production calls.** On 2026-10-28 it
held 163 calls (`data/model_calls/`, written on 2026-10-12 and 2026-10-21), and
25 passed no entrance.

- **12 have no repository frame at all.**
  - They were made on 2026-10-12 by scripts outside the repository, writing to
    the live data directory.
  - Their models and times match that day's clerk-model trials. They are not
    production, but the scoreboard judges them, because their site is not
    under `tools/` or `tests/`.
- **13 were production, every one from `aios/core/router_wiring.py:picker`.**
  They were made on `/api/generate` turns on 2026-10-21.

**What the picker is.**
- When routing policy allows two or more candidates, a small local model is
  asked to prefer one. The operator's machine allows that for reasoning and
  coding (`AIOS_ROUTER_CLOUD_TASKS`).
- Its prompt holds the task type and the allow-list, no user text. So nothing
  private left the machine.
- But the call skipped the emergency-stop check and output redaction. "Every
  model call through the one gateway" was false in daily use.

**Why the inventory missed it.** Its auto-routed turn ran with cloud off, so
every turn had one candidate and no pick. It listed the picker as not
reached, which was true of the inventory and not of the machine.

**Fixed:**
- **The picker runs only through a gate.**
  - `/api/generate` and `/api/v1/chat` build the gate on the local-only
    compatibility entrance.
  - Without a gate there is no pick, and routing stays deterministic.
  - An engaged stop refuses the pick before any model call.
- **Only the chosen allow-list position leaves the gated call.** Redaction
  rewrites the real id `qwen3-coder-480b-a35b-v1:0` as high-entropy, so a
  redacted reply would have silently lost that pick.
- **Tests:** `tests/test_route_picker_gateway.py`.
- **The inventory gained the surface `generate_routed`.** It runs with cloud
  allowed for coding, as on the operator's machine.
  - **Positive control:** on master `777da7ff`'s code it reports
    `UNGATED x1: aios/core/router_wiring.py:picker`.
  - On the fix, all of the surface's 4 calls are gated, the pick among them
    (`router_wiring.py:_pick_position`, through `complete_compatibility`).

**The inventory, 2026-10-28** (`release/one-gateway/inventory-2026-10-28.json`):
- 12 surfaces, 66 model calls, all 66 gated.
- The ledger is complete: 64 Ollama and 2 Bedrock requests received, every one
  recorded.
- 15 of 27 static sites observed. The 12 not observed are the table below,
  less the picker.

## The inventory, 2026-10-12

Evidence: `release/one-gateway/inventory-2026-10-12.json`.

**11 surfaces were driven, making 62 model calls. All 62 are gated.** The
ledger is complete: 61 Ollama and 1 Bedrock requests received, and every one
recorded.

| Surface | Calls | Entrance(s) |
|---|---|---|
| `/api/generate` local (alignment, planner, agent) | 3 | route, stream_structured |
| `/api/generate` cloud (Bedrock agent) | 3 | route, stream_structured |
| `/api/generate` second turn, same session | 6 | as above |
| `/api/v1/chat` authenticated, conversation | 1 | stream |
| `/api/v1/chat` authenticated, "what is …" | 1 | stream |
| `/api/v1/chat` API token, no session | 1 | stream_compatibility |
| `/api/v1/reflect` | 2 | route |
| `/api/v1/plan` | 1 | route *(was ungated, see below)* |
| `/api/v1/hiring/call` | 1 | route |
| Clerk refresh, approve, health-check, qualify | 42 | complete_compatibility |
| Council origination (Queen deliberation) | 1 | route |

### What it found

1. **`POST /api/v1/plan` called the model with no entrance.**
   - The route handed the raw LLM client to the Planner. Its call passed no
     emergency-stop check, no redaction and no context record. The forge's
     own planner and `/api/v1/reflect` did pass the gateway.
   - Fixed:
     - an authenticated principal takes the governed advisory entrance;
     - anyone else takes the local-only compatibility entrance (as does a
       principal with no constitution binding: stricter, never a 500).
   - Test: `tests/test_plan_route_gateway.py`.
2. **`/api/v1/chat` returned a 500 for ordinary questions.**
   - A transcript starting "what is", "explain", "list", "show", "describe"
     or "summarize" is classified ADVISORY.
   - The chat route registered a stream only for conversation mode, so those
     directives raised.
   - Fixed: the route is talk only, so every mode streams as conversation.
   - Test: `tests/test_chat.py::test_a_read_only_question_is_answered_not_a_500`.

### What it did not reach (not measured, NOT clean)

The inventory scans `aios/` for candidate model-call sites. A site counts as
observed if it appears anywhere on a recorded call's stack. **14 of 27 were
observed.** The 13 below were not, so nothing here says they are gated:

| Site | Why it was not reached |
|---|---|
| `turn_pipeline._crag_llm_judge`, `_crag_cloud_source` | CRAG judges recalled memory. With a fresh store and offline embeddings, recall had nothing to judge. |
| `local_workforce/service._execute_advisory_job`, `domain/local_workforce/runtime.execute_job` | The clerk's real jobs need an admitted model. The fake model fails qualification, as it should. |
| `runtime/intelligence_gateway.*` (3), `council_orchestrator.execute` | Worker reasoning (`AIOS_WORKER_REASONING`, off by default) and execution after King approval. |
| `maintenance/service.run_approved_repair` | Needs an approved repair mission. |
| `self_analysis_agent.propose_fix` | Self-analysis proposals. |
| `models/model_router.complete`, `router_wiring.picker` | Not reached by any driven route. *The picker WAS reached on the operator's machine, ungated: see 2026-10-28 above.* |
| `governance/runtime_proof._probe_mission` | A proof fixture, not a production caller. |

On a live machine, the scoreboard gate covers whatever real use reaches.

## What this does not do

- **It does not refuse an ungated call.** It measures. Refusing (fail closed
  in the adapters) is a later decision, for the operator, once real use
  shows zero.
- **Embeddings are not counted.** They run in-process (sentence-transformers)
  and send nothing out.
- **Measurement tools are reported, not judged.** Their own direct calls (the
  benchmark, the payoff harness) carry a `tools/` site. A production path
  that a tool drives is still judged, by its production frame.
