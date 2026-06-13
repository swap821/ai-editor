# MULTI_LLM_PLAN.md — a multi-provider LLM library with task-aware, evidence-calibrated routing

**Authored 2026-06-13 (draft for operator approval — design-first, no code until you say go).**
Operator's intent (his words): the AWS Bedrock key and the laptop's Google `gcloud` auth should
make the AI-OS a **multi-LLM library** — many providers/models, and the mind **picks the right
model for the task**. This is the most direct answer to the #1 limiter the analysis named — the
**7B local-model ceiling** (`FUTURE_FRONTIER.md` S1 + "capability-aware, evidence-calibrated routing").

---

## 1. Where we already are (grounded — do NOT rebuild)

- **A task-aware, tool-aware router already exists** — `aios/core/model_selector.py`: `infer_task()`
  classifies each message as **coding / reasoning / general / fast**; `select_model()` deterministically
  picks the best model and drops ones that can't tool-call (`require_tools`). **But it is LOCAL-ONLY** —
  it ranks *Ollama tags*. It does not route across providers.
- **Two providers wired, same `chat(messages, *, tools, model)` contract:** `OllamaClient` (`aios/core/llm.py`,
  local, urllib) and `BedrockClient` (`aios/core/bedrock.py`, Converse API — uniform tool-use across
  Claude/Nova/Llama, lazy `boto3`, model discovery via `list_models`). The agent loop, memory, security,
  and verifier are **provider-agnostic** already.
- **Routing today** (`aios/api/main.py`): `modelId='auto'` → local `select_model`; `ollama.x` → local;
  any other id → Bedrock-or-503. The classic UI has a rich Bedrock catalog + Ollama picker + the "Auto" badge.
- **Config:** `BEDROCK_ENABLED` = region AND model both set (`config.py`); `AWS_BEARER_TOKEN_BEDROCK` (the `ABSK` key).
- **Gemini / Vertex is NOT integrated at all.** (The classic "Google" entries are Ollama Gemma, not Gemini.)

**So the foundation is ~half-built.** The gap is exactly your intent: **cross-provider, task-aware auto-routing**,
plus **Google Gemini**, plus **securing the credentials**.

---

## 2. The architecture (the delta)

A small **provider registry** + a **router** above the existing seam — the agent loop never changes.

```
infer_task(message) ──►  ROUTER  ──►  picks (provider, model)  ──►  ChatClient.chat(...)  ──►  the CAGE verifies
  (exists)                 │            governed by a POLICY                (Ollama / Bedrock / Gemini)
                           │            + evidence calibration
        PROVIDER REGISTRY ─┘   local(Ollama) · cloud(Bedrock) · cloud(Gemini/Vertex) · [future: more]
```

1. **Provider registry** — each provider is a `ChatClient` (the contract already exists) with: `id_prefix`
   (`ollama.` / `bedrock.` / `gemini.`), `is_available()`, `list_models()`, and a `privacy` tag (`local` | `cloud`)
   + a coarse `cost` tag. Ollama + Bedrock already fit; add **`GeminiClient`** (Vertex AI / `google-genai`,
   auth via the laptop's `gcloud` Application Default Credentials — no key in the repo; tool-use via Gemini
   function-calling, mapped to the same message shape like `bedrock._to_converse` does).
2. **The router** — generalize `model_selector` to a cross-provider pick:
   `route(task, installed_local, available_cloud, policy, metrics) -> (provider, model)`. Keep the existing
   local tier logic; add a provider-selection layer driven by the **policy** below. `auto` now considers ALL
   providers; explicit ids (`gemini.…`, `bedrock.…`, `ollama.…`) still force a provider.
3. **The policy (operator-owned, the heart of it):** task → candidate providers/models, gated by:
   - **PRIVACY** — which tasks may leave the machine. Default **local-first**; cloud is an *opt-in escalation*
     per task class. (e.g. generic reasoning/scaffolding → cloud ok; anything touching private/sensitive
     code → local-only.) You set the boundary; every cloud call is audit-logged so it's visible.
   - **COST** — prefer **free local**; escalate to paid cloud only when warranted (a hard task the local
     model keeps failing). A per-call cost/latency budget.
   - **CAPABILITY** — hard tasks (deep reasoning, big context) → a frontier cloud model; quick/cheap → local.
4. **Evidence calibration (the soul, applied to routing):** over time, blend the heuristic with the
   **measured per-(model, task) verified-success rate** from `development.py` / the audit chain — so the router
   learns which model actually performs on *your* workload. Deterministic, no LLM in the routing path. (This is
   FUTURE_FRONTIER's "capability-aware, evidence-calibrated routing"; cold-start falls back to the heuristic.)

---

## 3. Why this keeps the soul (not a compromise)

- **"Trust the evidence, not the model" is provider-agnostic.** A frontier model is still just a *proposer*; the
  cage (gateway → scope-lock → approval → verifier) decides regardless of who proposed. RED stays hard-blocked.
- **Every call is audited** — the audit chain logs *which provider + model* produced each action, so cloud usage
  is fully visible/inspectable. The router's pick is itself recordable evidence.
- **Local-first stays the DEFAULT** — privacy, offline, and free by default; cloud is a per-task, policy-gated,
  audited escalation. The voyaging-mind UI can show which brain is active per turn.

## 4. The honest trade-offs (decide consciously)

- **Privacy / data-egress** — routing to Gemini/Bedrock sends your prompt + code to Google/AWS. Mitigated by the
  policy (you choose what may leave) + the audit trail, but it IS a real choice. **The privacy boundary is the one
  thing only you can set.**
- **Cost + rate limits** — cloud frontier costs money + throttles; the cost gate + evidence-calibration keep it
  to "escalate only when worth it."
- **Credential hygiene** — Bedrock key belongs in the **backend env** (it's backend-only; today it's mis-placed in
  `frontend/.env`, PLAN H1). Gemini uses `gcloud` ADC (no key on disk in the repo). Neither ever in git.

---

## 5. Phased build plan (each: restate + wait for OK; tests-first; ~90% honest)

- **P0 — Secure the credentials (hours).** Move/rotate the Bedrock `ABSK` token out of `frontend/.env` into the
  backend env (`AWS_BEARER_TOKEN_BEDROCK`); confirm `gcloud` ADC is present for Gemini. Document. *(= PLAN H1, now reframed as "provider #1 hygiene".)*
- **P1 — Add the Gemini provider (~3-4 days).** `GeminiClient` (Vertex/`google-genai`, ADC auth, function-calling →
  the agent message shape), `gemini.*` model ids, config flags (`AIOS_GEMINI_ENABLED`/project/location), `main.py`
  routing branch, `list_models`, and the classic selector lists Gemini models. **Explicit-pick first** (like Bedrock) —
  prove a Gemini turn end-to-end through the cage before auto-routing to it.
- **P2 — Cross-provider auto-router + policy (~3-4 days).** Generalize `model_selector` to the provider-aware
  `route(...)`; add the operator **policy** (task → provider, privacy gate, cost gate) as config + a small policy
  module; `auto` now spans providers. Tests pin: privacy gate never sends a local-only task to cloud; RED still blocked.
- **P3 — Evidence calibration + UI (~3-4 days).** Blend measured per-(model,task) success from dev-metrics into the
  route; surface the router's choice + provider + a privacy indicator in the UI (the model picker already shows
  provider groups — extend it; the superbrain topbar can show the active brain).

**Recommended order:** P0 (cheap + the security win) → P1 (Gemini, the immediate frontier access) → P2 (the auto-router
that realizes "the mind picks the model") → P3 (calibration + UI). P0+P1 alone already give you a usable multi-LLM
library with explicit per-task model choice; P2 makes it automatic.

---

## 6. Open decisions for the operator
1. **The privacy boundary** — what task classes may go to the cloud vs local-only? (I'll encode it as the default policy.)
2. **Start point** — P0 (secure creds) first, or jump to P1 (Gemini) since the key already works on loopback?
3. **Gemini access path** — Vertex AI (via your GCP project + ADC) vs the `google-genai` Gemini API (an API key). ADC/Vertex
   is cleaner (no key on disk); confirm your `gcloud` is logged into a project with Vertex/Gemini enabled.

_Grounded in `model_selector.py` (task-aware, local-only today), `bedrock.py`, `llm.py`, `config.py`, `main.py`.
Dovetails `PLAN.md` S1 + `FUTURE_FRONTIER.md`. No code until you approve a phase._
