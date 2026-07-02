# The Wonder Epoch — Design Gate for the Durable Cortex Bus

**Status:** DESIGN — awaiting operator sign-off (do NOT build yet) · **Date:** 2026-07-02 · **Author:** Claude
**Parent:** fusion roadmap §4 (`2026-07-01-fusion-roadmap-workorders.md`), ADR §4.2–4.4
**Gate:** This is the door to the wonder phase. It opens only on the operator's explicit go.

> **Why a gate, not a task.** Every foundation organ so far shipped default-off then earned its flip with evidence. The wonder organs (council reasoning/origination, earned autonomy, cloud burst) are categorically different: they let the organism *act with less supervision*. That crosses the project's whole thesis, so their enabling infrastructure gets a design sign-off BEFORE a line is written — not after.

---

## 1. The one problem this solves

The foundations woke (morning) and the body learned to show them (afternoon). But the organism's **inner life between turns is still mute** — CRAG's corrective verdicts, reflection's lessons, consolidation, the self-model, and (future) council deliberation all run *inside the request/response of a single turn or not at all*. There is no place for a cold, re-derivable observer to do slow work off the hot path and have its results reach the body honestly.

The cortex bus is that place: a **durable, ordered, cross-process event tier** for signals that are *not* authority-bearing. It is the infrastructure the wonder organs need, built and proven BEFORE any of them is switched on.

## 2. The one law that must not break (ADR §4.1)

**Authority stays synchronous.** The verifier's return value is the authority. Skill promotion, autonomy crediting, and approval consumption already happen in-band on that return value — and they MUST NOT move onto the bus. The bus carries *observations* ("a turn completed", "recall was corrected", "a mistake was recorded"), never *decisions*. An event payload can inform the next turn; it can never grant a permission. If this line blurs, the supervision thesis is gone. Every task below is measured against it.

## 3. Shape (proposed, for critique)

- **Durable, then dispatch.** Append the event to SQLite, commit, *then* notify subscribers. A crash between append and dispatch replays on restart — an observation is never silently lost. (Mirror of the audit ledger's append-then-anchor discipline.)
- **Per-signature ordering.** Events sharing a signature (e.g. same session, same fact subject) dispatch in append order; unrelated signatures may interleave. No global total order — that would serialize the whole organism.
- **Cross-process safe.** Workers are subprocesses (`spawner.py`); the bus is a SQLite table with a polling/notify cursor, not an in-memory queue. Any process appends; the dispatcher drains.
- **At-least-once, idempotent handlers.** Handlers must tolerate replay (dedupe on event id). No handler may assume exactly-once.
- **Bounded + swept.** The bus table is compacted like the memory tiers (a retention window); a full bus fails soft (drop-oldest observation, log it — never block a turn).

## 4. Proposed slices (each independently shippable, gated, reversible)

- **W1 — the bus substrate.** `aios/runtime/cortex_bus.py`: append-then-dispatch, SQLite-backed, per-signature ordering, idempotent replay, retention sweep. Pure infrastructure, ZERO producers/consumers wired. Tests: durability across a simulated crash, ordering within a signature, replay-dedupe, fail-soft on a full bus. Default off (`AIOS_CORTEX_BUS`).
- **W2 — first observer (read-only).** Move ONE existing cold signal onto it as proof: the self-model rebuild (today it's a per-turn synchronous recall). Producer emits "turn completed"; an async handler rebuilds the self-model off the hot path. Measured: turn latency drops, self-model still current within N seconds. Authority untouched (self-model is advisory context).
- **W3 — the conformance extension.** Extend `test_organism_conformance.py`: assert that an authority-bearing outcome (skill promotion) is STILL synchronous and never observed on the bus — a standing guard for §2.
- **W4 — facts auto-extract off the hot path (optional).** Today extraction runs in-band (cheap, deterministic — fine). IF profiling shows it matters, move it to a bus handler. Listed for completeness; likely a no-op.
- **Phase-4 organs (SEPARATE gate each).** Only AFTER W1–W3 are green does turning on a wonder organ become a discussable task — council deliberation triggers, then (each its own decision) earned autonomy, cloud burst. None is in this doc's scope to enable; this doc only builds the floor they'd stand on.

## 5. What this doc explicitly does NOT do

- It does not enable any wonder organ. `test_aliveness_defaults.py` stays green (all wonder flags off) throughout W1–W4.
- It does not move any authority onto the bus. W3 exists to prove that permanently.
- It does not touch the frozen security spine.

## 6. The operator's decision

Three ways forward — your call:

1. **Build W1 now** (pure infra, fully reversible, no behavior change) and review before W2.
2. **Refine this design first** — critique the shape in §3 (durability model, ordering, retention) before any code.
3. **Hold** — the foundations + body + honest coverage are a complete, shippable chapter; the wonder epoch waits for a deliberate later start.

Recommendation: **(1)** — W1 is the lowest-risk, highest-leverage step (it unblocks every cold observer and the B4 memory-halo's push upgrade), and it cannot change organism behavior because nothing produces or consumes yet. But this is a thesis-level direction, so the design is on the table first, per the project's own discipline.
