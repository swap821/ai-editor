# Council Deliberation Keepers — the two non-theater ideas, hardened

**Date:** 2026-07-01 · **Status:** spec (build-ready) · **Author:** Claude (review-gate)
**Provenance:** distilled from `github.com/0xNyk/council-of-high-intelligence` (an 18-persona
shell-script decision *skill* — no memory, no verification, no persistence; vote-gated). Its
deliberation *engine* is a topology mismatch for our runtime and its "2/3 majority → approve"
is authority laundering. Two ideas survive contact with our code. This specs only those two.

## What we are NOT taking (and why)

- **N-worker blind debate / cross-examination / dissent quota / novelty gate / "Hemlock rule."**
  Wrong topology. Our queens are role-specialists (`security`/`memory`/`testing`/`critique`),
  not interchangeable clones. Adding a debate layer is theater relocated from personas to
  phases, and costs minutes of 32B inference per mission for missions that resolve today in one
  near-deterministic pass.
- **Consensus as a gate.** Authority in our runtime comes from (a) human approval between
  `deliberate()` and `execute()`, and (b) synchronous post-hoc `TestingQueen.verify` under the
  strength taxonomy — never a vote. Neither keeper introduces voting. This is the load-bearing
  invariant.
- **The doc's King pseudocode.** It derives execution plans and mutates verification commands
  inside the King. Our `reason_king` is clamped strengthen-only + fail-closed. Do not regress it.

---

## Keeper 1 — Planner restate / ambiguity gate

**The gap.** `PlannerQueen.draft` (`aios/council/queens/planner.py`) turns a request into a
`MissionContract` with **no check that the goal is specified well enough to act on.** A vague
goal ("improve it", "fix that") drafts a contract and proceeds to Security/Memory review and a
human approval prompt — the human is asked to approve a mission whose *intent* was never pinned.

**The move.** Before returning `allow`/`allow_with_approval`, the Planner runs one ambiguity
check. If the goal is underspecified, it emits `verdict="defer"` with the specific ambiguity in
`reason` and the clarifying question(s) in `constraints`. That's it — the existing machinery does
the rest: `has_blocking_verdict` already treats `defer` as blocking, so `deliberate()` routes to
`_blocked_run` → `build_king_report` → status `needs_revision`, recommendation `revise`,
`human_summary = "Council blocked approval: planner: <ambiguity>"`. The human sees the
clarifying question instead of a blind approve. **This reuses the exact `defer` path the Planner
already uses for empty `allowed_files` (planner.py:110-114).**

### Design (deterministic-first, LLM-optional, strengthen-only)

Add `PlannerQueen._restate_gate(goal, contract) -> tuple[bool, str, list[str]]` returning
`(is_ambiguous, reason, clarifying_questions)`. Called in `draft()` **only on the request path**
(not when an existing `MissionContract` is passed in), **after** the contract is built, **before**
the final verdict is chosen — and it can ONLY turn `allow*` into `defer`, never the reverse.

**Default tier — deterministic heuristics (always on when the flag is set, no LLM):**
- goal length below a small threshold (e.g. < 12 non-whitespace chars) → ambiguous;
- goal is pronoun/deixis-only or matches a vague-verb-without-target set
  (`fix|improve|clean|refactor|make better|do that|handle this` with no noun/path/identifier) →
  ambiguous;
- (advisory, not blocking) no `verification_commands` **and** the goal names a change verb → add a
  `follow_up` note but do **not** defer on this alone.

**Opt-in tier — single LLM restate (mirrors the existing `COUNCIL_REASONING` double-gate):**
when `config.COUNCIL_RESTATE_GATE` is on **and** `self._llm is not None`, make **one** call:
"Restate this goal in one sentence. If it has more than one reasonable interpretation, or is
missing a concrete target, reply `AMBIGUOUS: <the competing interpretations / missing piece>`;
else reply `CLEAR`." Parse only that prefix. **Fail-closed:** any transport/parse error →
fall back to the deterministic verdict unchanged (never spuriously block, never wave through).
This is **one** call, not N workers, and never runs on the default path.

### Safety invariants (Keeper 1)

1. **One-directional.** The gate may only escalate `allow*` → `defer`. It can never turn a
   `deny`/`defer` into `allow`. (Same philosophy as narrow-only `reconcile_plan`.)
2. **No new default-path LLM call.** Deterministic heuristics are the default; the LLM restate is
   double-gated (flag + injected client), exactly like `PlannerQueen._reason`.
3. **No authority.** A `defer` routes to human clarification; it grants nothing.
4. **Idempotent / pure.** `_restate_gate` reads only the goal + contract; no I/O, no state.

### Tests first (TDD)

- `test_restate_gate_defers_on_vague_goal` — goal `"fix it"` → verdict `defer`, reason names
  vagueness, `constraints` non-empty (the clarifying question).
- `test_restate_gate_passes_specific_goal` — a goal naming a file/behavior → verdict unchanged
  (`allow_with_approval`), no defer.
- `test_restate_gate_is_one_directional` — a request that would already `defer` (empty
  `allowed_files`) stays `defer`; the gate never upgrades it.
- `test_restate_gate_llm_error_falls_back` — injected LLM raises → deterministic verdict returned,
  no exception escapes.
- `test_restate_gate_off_by_default` — with the flag unset and no LLM, behavior byte-identical to
  today for a specific goal.

---

## Keeper 2 — KingReport leads with what we don't know

**The gap.** `build_king_report` / `build_deliberation_report` (`aios/runtime/king_report.py`)
surface recommendation, risk, and a `human_summary`, but the report's *uncertainties* are
scattered across verdict `constraints`, `defer` reasons, and the `below_floor_warning`. The one
honest instinct worth taking from the source repo: **surface unknowns first.**

**The move.** A pure helper aggregates the uncertainties **already computed** (invent nothing) and
(a) prefixes `human_summary` with them — exactly as the `⚠ Weak verification…` prefix already does
at king_report.py:78-80 — and (b) stashes structured lists in the free-form `council_summary`
dict for the frontend/machine.

```python
def _open_questions(ledger, verification_result) -> tuple[list[str], list[str]]:
    """(unresolved_questions, follow_up) — sourced only from real signals, never invented."""
    unresolved, follow_up = [], []
    for v in ledger.council_verdicts:
        if v.verdict in {"deny", "defer"}:
            unresolved.append(f"{v.queen}: {v.reason}")
        unresolved.extend(v.constraints)            # constraints ARE open conditions
    if verification_result.get("below_floor_warning"):
        follow_up.append("Re-verify with a stronger, change-exercising command before trusting this result.")
    # de-dupe, preserve order
    return _dedup(unresolved), _dedup(follow_up)
```

Wire into `build_king_report` (after the strength block) and `build_deliberation_report`:
- `council_summary["unresolved_questions"] = unresolved`
- `council_summary["follow_up"] = follow_up`
- if `unresolved`: `human_summary = "Open: " + "; ".join(unresolved[:3]) + " — " + human_summary`

### Why this needs NO schema change

`KingReport` is `frozen`/`extra="forbid"` (contracts.py:26-29) — but `council_summary` is
`dict[str, Any]` and `human_summary` is a free string. Both keepers write only into those. **The
frozen v0.1 contract is untouched.** (If the operator later wants `unresolved_questions` as a
first-class top-level field for the frontend, that's a separate, additive schema slice — deferred.)

### Safety invariants (Keeper 2)

1. **Transparency only.** Never changes `recommendation`, `risk`, `approval_needed`, or
   `rollback_available`. It can only make the report *more honest*, never change the decision.
2. **No invention.** Every line traces to a real verdict/constraint/strength signal. Empty in →
   empty out → `human_summary` unchanged (degrades to today's behavior).
3. **Can be always-on** (pure additive transparency, zero authority impact). If the house style
   prefers a flag, gate behind `config.COUNCIL_REPORT_UNKNOWNS` — but the conservative default is
   on, since it cannot regress behavior.

### Tests first (TDD)

- `test_king_report_surfaces_defer_reason` — a `defer` verdict → its reason appears in
  `council_summary["unresolved_questions"]` and prefixes `human_summary` with `Open:`.
- `test_king_report_follow_up_on_weak_verification` — below-floor strength → a re-verify line in
  `follow_up`.
- `test_king_report_no_unknowns_is_unchanged` — all-`allow`, strong verification → lists empty,
  `human_summary` byte-identical to today.
- `test_deliberation_report_surfaces_constraints` — pre-execution report carries queen constraints
  as unresolved questions.

---

## Config (mirror the existing opt-in flags)

In `aios/config.py`, beside `COUNCIL_CRITIQUE` / `COUNCIL_REASONING` / `COUNCIL_KING_REASONING`:
- `COUNCIL_RESTATE_GATE` ← env `AIOS_COUNCIL_RESTATE_GATE` (default **off**; deterministic tier
  only activates with the flag, LLM tier needs flag **and** injected client).
- `COUNCIL_REPORT_UNKNOWNS` ← env `AIOS_COUNCIL_REPORT_UNKNOWNS` (default **on**; see 2.3).

## Files touched

- `aios/council/queens/planner.py` — `_restate_gate` + `draft()` wiring (Keeper 1).
- `aios/runtime/king_report.py` — `_open_questions` + wiring (Keeper 2).
- `aios/config.py` — two flags.
- `tests/test_council_orchestrator.py` / `tests/test_king_report.py` (or a new
  `tests/test_restate_gate.py`) — the TDD cases above.
- **Untouched:** `aios/runtime/contracts.py` (frozen), `aios/security/*` (frozen spine),
  `council_orchestrator.py` (the `defer`/`has_blocking_verdict` path already carries Keeper 1).

## Coordination note (two-agent protocol)

`planner.py` sits in **Codex's Lane C** (per `2026-07-01-fusion-roadmap-workorders.md`).
`king_report.py` is **unclaimed**. Options: (a) I take a short coordinated writer-lease for this
isolated slice while Codex is mid-C-lane on `main.py`/`events.py` (no file overlap with C2/C3), or
(b) queue both keepers behind Codex's current slice. Operator picks; do not double-write `planner.py`.

## Not in scope

Voting, personas, multi-worker debate, top-level schema fields, frontend rendering of the new
lists. Each is a separate decision, and none is required for the two keepers to add value.
