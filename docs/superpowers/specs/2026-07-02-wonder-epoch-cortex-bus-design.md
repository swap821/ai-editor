# The Wonder Epoch — Durable Cortex Bus (Ratified Design)

**Status:** RATIFIED design — awaiting a separate "build W1" go (operator chose refine-not-build) · **Date:** 2026-07-02 · **Author:** Claude
**Parent:** fusion roadmap §4 (`2026-07-01-fusion-roadmap-workorders.md`), ADR §4.2–4.4
**Process:** brainstormed under `superpowers:brainstorming`; three open forks ratified by the operator 2026-07-02.

> **Why a gate, not a task.** Every foundation organ shipped default-off then earned its flip with evidence. The wonder organs (council reasoning/origination, earned autonomy, cloud burst) are categorically different: they let the organism *act with less supervision*. That crosses the project's whole thesis, so their enabling infrastructure gets a design sign-off BEFORE a line is written — not after.

---

## 1. The one problem this solves

The foundations woke (2026-07-02 AM) and the body learned to show them (PM). But the organism's **inner life between turns is still mute** — CRAG's corrective verdicts, reflection's lessons, consolidation, the self-model, and (future) council deliberation all run *inside the request/response of a single turn or not at all*. There is no place for a cold, re-derivable observer to do slow work off the hot path and have its results reach the body honestly.

The cortex bus is that place: a **durable, ordered, cross-process event tier** for signals that are *not* authority-bearing. It is the infrastructure the wonder organs need, built and proven BEFORE any of them is switched on.

## 2. The one law that must not break (ADR §4.1)

**Authority stays synchronous.** The verifier's return value is the authority. Skill promotion, autonomy crediting, and approval consumption already happen in-band on that return value — and they MUST NOT move onto the bus. The bus carries *observations* ("a turn completed", "recall was corrected", "a mistake was recorded"), never *decisions*. An event payload can inform the next turn; it can never grant a permission. If this line blurs, the supervision thesis is gone. **W3 makes this a standing, tested invariant.**

## 3. Ratified substrate (W1)

A durable **outbox**, not an in-memory queue. Rationale, ratified: workers are subprocesses (`spawner.py`), so an in-memory queue cannot cross the process boundary at all, and it loses every un-dispatched observation on a crash. The outbox is the only design that survives a crash AND crosses processes — the same append-then-anchor discipline the audit ledger already proves on this machine.

- **Durable, then dispatch.** Append the event to SQLite, commit, *then* notify subscribers. A crash between append and dispatch replays on restart — an observation is never silently lost.
- **250ms poll + wake-hint (ratified).** The dispatcher polls the outbox every 250ms and wakes early when a producer touches a hint file. Feels near-instant to a consumer, degrades to pure 250ms polling if a hint is missed. Cold-path observations (self-model rebuild, fact proposals) are non-interactive, so 250ms is comfortably below the perceptible floor.
- **Per-entity ordering (ratified).** Events order within a **signature = the entity the observation is about** (session_id for turn events, fact-subject for memory events); unrelated signatures interleave. No global total order (that would serialize the whole organism — one slow handler blocking every observer). This granularity is exactly what causality needs: `mistake-recorded → self-model-rebuilt-from-it` holds because both share the entity signature. **Data-model commitment:** handlers may rely on per-entity order; widening it later is a breaking change.
- **At-least-once, idempotent handlers.** Handlers dedupe on event id and tolerate replay. No handler may assume exactly-once.
- **Bounded + swept.** The outbox table is compacted like the memory tiers on a retention window (default: keep the last 10,000 dispatched observations or 7 days, whichever is smaller; `AIOS_CORTEX_BUS_RETENTION`-tunable). A full bus fails soft — drop-oldest observation and log it, never block a turn.
- **Default off** (`AIOS_CORTEX_BUS`). W1 wires **zero producers and zero consumers** — pure infrastructure, no behavior change possible.

## 4. Ratified slices (each independently shippable, gated, reversible)

- **W1 — the bus substrate.** `aios/runtime/cortex_bus.py`: append-then-dispatch, SQLite-backed, per-entity ordering, 250ms+hint dispatch, idempotent replay, retention sweep, fail-soft on full. Tests: durability across a simulated crash (append with no dispatch → replay on restart), ordering within a signature, interleave across signatures, replay-dedupe, fail-soft drop-oldest. Default off.
- **W2 — first observer: the self-model rebuild (ratified).** Move the self-model rebuild from per-turn synchronous (`main.py:_recall_self_model` path) to an async bus handler: a producer emits a "turn completed" observation; the handler rebuilds the self-model off the hot path. **Acceptance is a number** — turn latency before/after, reported in the handoff — plus "self-model reflects a turn within ~1s" (a few dispatch cycles at the 250ms cadence). Authority untouched (the self-model is advisory recalled context, never a decision). Chosen over the flashier memory-halo push because it is the *purer* proof of the bus's purpose (cold work off the hot path), it is hermetic (no frontend entanglement, no SSE-vs-bus question), and its payoff is measurable.
- **W3 — the conformance guard.** Extend `test_organism_conformance.py`: assert that an authority-bearing outcome (skill promotion) is STILL synchronous on the verifier's return value and is NEVER observed on the bus. A permanent guard for §2.
- **W4 — facts auto-extract off the hot path (optional, likely a no-op).** Today extraction runs in-band and is cheap + deterministic (fine as-is). IF profiling ever shows it matters, move it to a bus handler. Listed for completeness only.
- **Phase-4 organs (SEPARATE gate each, NOT here).** Only AFTER W1–W3 are green does enabling a wonder organ become a discussable task — council deliberation triggers, then (each its own operator decision) earned autonomy, cloud burst. None is in this doc's scope to enable; this doc only builds the floor they would stand on.

## 5. What this doc explicitly does NOT do

- It does not enable any wonder organ. `test_aliveness_defaults.py` stays green (all wonder flags off) throughout W1–W4.
- It does not move any authority onto the bus. W3 exists to prove that permanently.
- It does not touch the frozen security spine.

## 6. Sequencing & definition of done

- **Order:** W1 (infra, reversible, zero behavior change) → operator review → W2 (first observer, latency benchmark) → W3 (invariant guard). W4 only if profiled. Wonder organs are out of scope.
- **Per-slice gate:** TDD red→green, full backend gate exit 0 at the branch-coverage floor, `test_aliveness_defaults.py` green (wonder still caged), no frozen-spine edits, hash-pinned handoff for review.
- **Whole-epoch done (of THIS doc):** W1–W3 green and reviewed; the bus is durable, per-entity-ordered, cross-process-safe, and provably carries no authority-bearing event; a measured turn-latency improvement from W2 with the self-model fresh within ~1s; wonder organs left as separately-gated future decisions.

## 7. Status

Design ratified 2026-07-02. **Build is NOT authorized by this doc** — the operator chose to refine the design and stop. Building W1 begins only on a separate explicit "go", at which point the `superpowers:writing-plans` skill turns this into a step-by-step implementation plan.

**UPDATE 2026-07-02 (late): W1–W3 SHIPPED — this doc's whole-epoch definition of done is met.**
- W1 substrate `1a63752` · W2 first observer + structural authority gate `85e96e4` · W3 conformance guard `8864501` (each gate exit 0; final coverage 87.59% branch).
- The §2 law is now held at TWO layers: structurally (`CortexBus.append` refuses authority-family event types, fail-closed) and by the permanent W3 guard (real promotion turn with dispatch neutered → promotion lands synchronously while the bus sits undrained; five mutation red-proofs confirm the guard has teeth).
- W4 remains a profiled-only option. Wonder organs remain caged (`test_aliveness_defaults.py`); enabling any is a SEPARATE operator gate each, exactly as §4 requires.
