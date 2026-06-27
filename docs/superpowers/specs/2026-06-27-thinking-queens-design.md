# Phase 3 — Thinking Queens (real Queen reasoning)

Date: 2026-06-27
Status: Approved (operator), ready for implementation plan
Branch target: `council-runtime-v01` (then fast-forward to `master` on green, per session convention)

## Goal

Make the Council **deliberate with real reasoning** instead of returning canned
verdicts. Today `PlannerQueen` copies request → contract with a hardcoded
`confidence=0.82`, `MemoryQueen` echoes hints and can never block, `TestingQueen`
is half-real (can drive the real `Verifier`), and only `SecurityQueen` truly
analyzes. This slice makes Planner and Memory reason for real, and makes the
deliberation durable + replayable (roadmap Phase 3A).

## Non-goals (YAGNI / explicitly excluded)

- The **real worker** (replacing the hardcoded heartbeat) — separate slice.
- Phase 3B Queen-as-service registry / long-lived services.
- Phase 4 pheromone decay/strengthening (Memory uses existing memory stores only).
- Any change to the FROZEN security spine (`aios/security/*`).

## The load-bearing invariant — reasoning advises, it never holds authority

An LLM in a Queen may make the mission **more cautious or more detailed**; it can
**never escalate privilege**. Enforced mechanically, fail-closed:

- **PlannerQueen can only NARROW, never widen.** After the LLM proposes a plan,
  the result is reconciled against the *request's* bounds:
  - `allowed_files` → intersected with the request set (LLM may drop, never add).
  - `forbidden_files` → union (LLM may add, never remove).
  - `risk_level` → may only be raised (GREEN→YELLOW→RED), never lowered.
  - `requires_approval` → may only be set true, never cleared.
  - `verification_commands` → may add; existing ones are preserved.
  - Anything outside these rules in the LLM output is **discarded**, not trusted.
  The reconciled contract is then handed to the real `SecurityQueen` exactly as
  today (this slice does not change Security).
- **MemoryQueen** gains the power to **DEFER** (or **DENY** on a strong match)
  when retrieval surfaces a prior *verified failure* of the same mission shape.
  It still cannot `allow`-grant anything it could not before.

If any reasoning step errors or times out, the Queen **falls back to today's
deterministic behavior** (fail-closed = no worse than current). Reasoning never
blocks a mission *open*; on doubt it defers.

## Components

### `ReasoningClient` (new, small protocol)
`aios/council/reasoning.py`
- Protocol: `reason(prompt: str, *, allow_cloud: bool = False, max_tokens: int = ...) -> str`.
- Default impl `LLMReasoningClient` wraps the existing router-backed `LLMClient`
  (`aios/core` / `get_llm_client`) → local-first routing + the existing privacy
  gate apply unchanged. `allow_cloud=False` by default.
- Tests inject a `FakeReasoningClient` returning canned JSON → fully
  deterministic; **no network in any test path**.

### `PlannerQueen` (modify `aios/council/queens/planner.py`)
- Constructor gains `reasoning: ReasoningClient | None = None` (DI, like
  `TestingQueen(verifier=...)`).
- When `reasoning` is present AND `config.COUNCIL_REASONING` is on: build a
  bounded prompt (goal + request bounds), ask for a structured plan
  (steps, files-to-touch ⊆ allowed_files, suggested verification_commands,
  risk read, confidence 0..1). Parse defensively (bad/partial JSON → fallback).
- Reconcile via the narrow-only filter (above), write the plan to
  `metadata["council_plan"]`, merge `verification_commands`, and set the verdict
  `confidence` from the model (clamped 0..1) instead of `0.82`.
- `reasoning is None` or flag off → **byte-for-byte today's behavior**.

### `MemoryQueen` (modify `aios/council/queens/memory.py`)
- Constructor gains `retriever: CouncilMemoryRetriever | None = None`.
- `CouncilMemoryRetriever` (new, in `aios/council/reasoning.py` or a sibling)
  is a thin read-only adapter over the existing memory engine: semantic/episodic
  lookup for relevant prior context + `mistakes` lookup for known failures,
  keyed on the goal. Returns `(hints: list[str], known_failure: bool, detail)`.
- With a retriever + flag on: inject hints into `pheromone_context`/constraints
  (as today) AND **DEFER** when a relevant prior failure is found (DENY only on a
  high-confidence exact-shape failure match). No retriever / flag off → today's
  metadata-echo behavior.

### `council_state.py` (new — roadmap Phase 3A)
`aios/council/council_state.py`
- SQLite store (path from `config`, e.g. `COUNCIL_RUNTIME_DIR/council_state.db`).
- Tables exactly per spec: `queen_verdicts` (id, mission_id, queen_name, verdict,
  risk, reason, constraints_json, confidence, created_at) and `council_events`
  (id, mission_id, queen_name, event_type, payload_json, risk, snapshot_id,
  created_at).
- API: `record_verdict(mission_id, QueenVerdict)`, `record_event(...)`,
  `verdicts_for(mission_id)`, `events_for(mission_id)` (replay surface).
- Created lazily; WAL; safe to call when the dir doesn't exist yet.

### Orchestrator wiring (`aios/council/council_orchestrator.py`)
- Accept optional `council_state: CouncilState | None`. After each Queen verdict
  and at each lifecycle point (draft, security, memory, worker spawn, testing,
  report), call `record_verdict` / `record_event` (with `snapshot_id`).
- Persistence is **best-effort and non-fatal**: a store error logs + continues
  (the JSON artifacts remain the source of truth this slice; durability is
  additive). No behavior change when `council_state is None`.

### Config (`aios/config.py`)
- `COUNCIL_REASONING: bool` (env `AIOS_COUNCIL_REASONING`, **default False**).
- `COUNCIL_STATE_DB` path (default under `COUNCIL_RUNTIME_DIR`).
- Reasoning client + retriever + state are wired in the API/composition layer via
  `Depends(...)`, so production turns them on by flag and tests inject fakes.

## Data flow (one deliberation, flag ON)

1. `PlannerQueen.draft(request)` → LLM proposes plan → narrow-only reconcile →
   contract + planner verdict (model confidence). `record_verdict`.
2. `SecurityQueen.review(contract)` (unchanged, real). `record_verdict`.
3. `MemoryQueen.review(contract)` → retrieve trails/mistakes → hints +
   defer/deny on known failure. `record_verdict`.
4. If blocking verdict → blocked run (as today). Else spawn worker (unchanged
   this slice), `TestingQueen.verify`, build King report. `record_event` at each.
5. All verdicts/events durable in `council_state.db` → replayable.

## Error handling

- LLM/retrieval/JSON errors → per-Queen deterministic fallback (fail-closed).
- SQLite errors → logged, non-fatal (JSON artifacts unaffected).
- LLM output that violates the narrow-only rules → offending fields discarded,
  not applied; never raises into a privilege grant.

## Testing

- `FakeReasoningClient` + `FakeCouncilMemoryRetriever`: deterministic unit tests.
- **Adversarial**: a reasoning client that tries to add an out-of-scope
  `allowed_file`, lower risk to GREEN, and clear `requires_approval` → asserted
  to be fully clamped (the core security test for this slice).
- MemoryQueen DEFER/DENY on a seeded known-failure; allow when none.
- `council_state` round-trip + replay (`verdicts_for`/`events_for`).
- Flag-off / client-None paths assert byte-for-byte current behavior (regression
  guard).
- Full backend suite + 85% coverage floor stays green; frozen spine untouched.

## Rollout

- Ships **off by default** (`AIOS_COUNCIL_REASONING=false`) → zero behavior change
  in CI/production until the operator flips it. Mirrors the project's gated,
  opt-in pattern for new agent capabilities (`AIOS_EARNED_AUTONOMY`,
  `AIOS_SWARM_*`).
