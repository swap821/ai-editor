# The narrative self — a grounded autobiographical self-model

Date: 2026-06-28
Status: Approved (operator)
Branch target: `council-runtime-v01` → fast-forward `master` on green
Lineage: the highest-leverage cognition step after Phase 1 (graded verification) +
Phase 2/2b (execution boundary); the convergent #1 of both outside reviews.

## Goal

Give the organism an honest relationship with *itself*. Synthesize a short,
first-person autobiographical self-model from the already-graded telemetry —
*"Across verified work I'm reliable at coding tasks; I more often miss on
reasoning; recurring lesson: …"* — and inject it into the agent's recalled
context. A self-trait may be claimed **only** from above-floor (STRONG) verified
evidence; cold-start is silent (no invented personality).

## Principles

- **Deterministic, not LLM-narrated.** The point is honesty with its own evidence.
  v1 derives traits from graded rates and renders a templated paragraph — grounded,
  testable, no embellishment, no extra LLM call. LLM-narrated voice is a future polish.
- **Fail-closed / grounded-only.** A trait requires ≥ `min_attempts` *verified*
  attempts; below that, no trait. Every source reads only verified evidence, so the
  strength gate is satisfied by construction (Phase 1 already downgrades weak greens
  to `unverified`, which these queries exclude).
- **Read-only.** Synthesized fresh per turn from existing tables; no new persistence.
- **Opt-in.** `AIOS_NARRATIVE_SELF` (default off) — the same fail-closed rollout as
  the other cognition features.

## Components

### 1. `aios/memory/self_model.py` (pure synthesizer + renderer)
- `@dataclass Trait { kind: "strength"|"soft_spot"|"caution", subject: str, detail: str, attempts: int, rate: float|None }`
- `@dataclass SelfModel { strengths: list[Trait], soft_spots: list[Trait], cautions: list[Trait] }` with `is_empty`.
- `synthesize_self_model(development, mistakes, *, min_attempts=4, strong_rate=0.8, weak_rate=0.5, max_traits=3) -> SelfModel`:
  - **strengths/soft_spots** from `development.task_profile()` — per task category
    (across models), verified attempts + verified-success rate. A category with
    `attempts >= min_attempts` and `rate >= strong_rate` → strength; `rate <= weak_rate`
    → soft_spot. Ranked by attempts; capped at `max_traits` each.
  - **cautions** from `mistakes.recurring(limit=max_traits)` — verified lessons with
    `occurrence_count > 1`, most-recurring first.
  - Empty when there is no qualifying evidence.
- `render(model) -> str`: a compact first-person paragraph, or `""` when empty.
  Example: `"Self-model (from verified work): reliable at coding (9/10). Weaker at
  reasoning (2/6). Recurring lesson: re-run the failing test before claiming done."`

### 2. Two tiny read-only store helpers
- `DevelopmentTracker.task_profile(*, min_attempts=1, limit=5000) -> dict[str, tuple[int, float]]`:
  per-task `(verified_attempts, verified_success_rate)` from
  `outcome IN ('verified_success','verified_failure')`, keyed on `metadata.task`.
  Mirrors `model_task_success_rates` but keyed on task only. (The self-model applies
  its own `min_attempts`; the store-level floor stays 1 so the synthesizer owns the policy.)
- `MistakeMemory.recurring(*, limit=5) -> list[dict]`: verified lessons with
  `occurrence_count > 1`, ordered by `occurrence_count` desc.

### 3. Wiring (`aios/api/main.py`)
- A `_recall_self_model(development, mistakes)` helper (mirrors `_recall_facts`):
  returns the rendered paragraph or `None`. Best-effort (never breaks chat).
- In the recall block, when `config.NARRATIVE_SELF_ENABLED`: append the paragraph to
  `context_parts` (so it flows into `ToolAgent(memory_context=...)`), and emit a
  `tool_result`/`self_model` recall step (like fact recall) for observability.
- `config.NARRATIVE_SELF_ENABLED = _env_bool("AIOS_NARRATIVE_SELF", False)` (+ `__all__`).

## Error handling / fail-closed
- No / insufficient / unverified evidence → empty model → empty paragraph → nothing
  injected. Never an invented trait.
- Any synthesis exception is caught at the call site (best-effort recall), logged,
  and the turn proceeds without a self-model.
- Flag off → the path is never taken.

## Testing (the crisp guard the open-endedness needs)
- A task category with `rate >= strong_rate` over `>= min_attempts` verified attempts
  → a **strength**; `rate <= weak_rate` → a **soft_spot**.
- `< min_attempts` verified attempts, or **unverified-only** events → **NO trait**
  (the headline strength-gate test).
- A recurring *verified* lesson → a **caution**; a non-recurring or unverified lesson
  → none.
- `render()` is deterministic + first-person; an empty model → `""`.
- `task_profile()` counts only verified events; `recurring()` only verified,
  occurrence>1.
- Wiring: flag on + evidence → the paragraph is in `context_parts`; flag off →
  nothing injected.
- Full backend suite + 85% floor; frozen security spine untouched.

## Scope (YAGNI)
Deterministic synthesis only; traits from the existing router task categories (no new
taxonomy); read-only (no new tables). Deferred: LLM-narrated voice, finer-grained task
taxonomy, per-model self-traits, persistence/decay of the self-model.

## Rollout
Opt-in, no migration. With the flag on, a grounded self-model paragraph joins the
recalled context when (and only when) there is qualifying verified evidence.
