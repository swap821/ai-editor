# Handoff → Codex — Council deliberation keepers (2 isolated slices)

**From:** Claude (review-gate) · **Date:** 2026-07-01 · **Type:** additive, opt-in, fail-closed
**Spec (authoritative):** `docs/superpowers/specs/2026-07-01-council-deliberation-keepers.md`

## What this is
Two — and only two — ideas distilled from `0xNyk/council-of-high-intelligence` after fetching
the source (18-persona shell skill; no memory/verification/persistence; vote-gated). Its
deliberation engine is a topology mismatch and its "2/3 majority → approve" is authority
laundering. **Do not port the engine. Do not add voting.** Build only the two keepers below.

## Slice 1 — Planner restate gate  (`aios/council/queens/planner.py`)
- Add `PlannerQueen._restate_gate(goal, contract) -> (is_ambiguous, reason, questions)`.
- Call in `draft()` on the **request path only**, after the contract is built, before the final
  verdict — it may ONLY escalate `allow*` → `defer`, never the reverse.
- Deterministic heuristics are the default (short/pronoun-only/vague-verb-without-target goals).
- LLM restate tier is **one** call, double-gated behind `config.COUNCIL_RESTATE_GATE` **and**
  `self._llm is not None`; fail-closed to the deterministic verdict on any error (mirror `_reason`).
- A `defer` needs no orchestrator change: `has_blocking_verdict` → `_blocked_run` already carries it.

## Slice 2 — KingReport leads with unknowns  (`aios/runtime/king_report.py`)
- Add pure `_open_questions(ledger, verification_result) -> (unresolved, follow_up)` — sourced
  ONLY from real signals (defer reasons, verdict constraints, `below_floor_warning`). Invent nothing.
- Wire into `build_king_report` (after the strength block) and `build_deliberation_report`:
  stash both lists in `council_summary`, and prefix `human_summary` with `Open: …` when non-empty
  (same pattern as the existing `⚠ Weak verification…` prefix).
- **No `contracts.py` edit** — write only into the free-form `council_summary` dict + `human_summary`.

## Config (`aios/config.py`, beside the existing COUNCIL_* flags)
- `COUNCIL_RESTATE_GATE` ← `AIOS_COUNCIL_RESTATE_GATE` (default **off**).
- `COUNCIL_REPORT_UNKNOWNS` ← `AIOS_COUNCIL_REPORT_UNKNOWNS` (default **on**; pure transparency).

## Hard invariants (review will check these)
1. No voting, no personas, no multi-worker debate anywhere.
2. Slice 1 is one-directional (allow→defer only); never upgrades a deny/defer.
3. Slice 2 never changes recommendation/risk/approval_needed/rollback — transparency only.
4. Frozen untouched: `aios/runtime/contracts.py`, `aios/security/*`.
5. No new LLM call on the default path; empty-in → behavior byte-identical to today.
6. TDD: write the tests in the spec (§Tests first for each keeper) before implementation;
   keep coverage ≥ 85%.

## Sequencing (two-agent protocol)
`planner.py` is in your Lane C. `king_report.py` is unclaimed. Land these **after** your current
`main.py`/`events.py` C-lane slice so there's no in-file overlap — no rush. Slice 2 can go first
(unclaimed) if convenient.

## Review-gate (Claude, after Codex lands)
- Verify one-directionality of the gate (adversarial: a malicious/ambiguous goal cannot become
  `allow`); verify Slice 2 changes no decision field; confirm frozen files untouched; confirm the
  off/empty paths are byte-identical to today; run the suite + coverage floor.
