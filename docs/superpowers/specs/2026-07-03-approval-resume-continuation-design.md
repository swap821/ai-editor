# Approval-Resume Continuation — Design Gate (PROPOSED)

**Status:** PROPOSED — awaiting operator ratification. **Build is NOT authorized by this doc.**
**Date:** 2026-07-03 · **Author:** Claude · **Evidence:** the witnessed demo (dev-events 341–351) + the prove-it path.

## 1. The one problem this solves

When a turn pauses on a YELLOW action and the operator approves, the resume
turn rebuilds the model's context from ONLY the client-resent messages
(`main.py:3297 _to_chat_messages(req.messages)`); the model's own in-turn
plan — its assistant messages and the tool_call trace that led to the pause —
is discarded. The model re-derives the remaining work from the raw directive
text every time.

Witnessed cost (2026-07-03, gemini-2.5-flash): one two-file directive took
**nine approval pauses**, produced **duplicate artifact pairs** with drifted
names (`reverse_string.py` AND `string_reverser.py`, each with its test), and
burned operator patience clicking approvals for work the model had already
planned differently one resume earlier. `_pre_apply_grants` anchors the
APPLIED writes into the resume convo (shipped, correct), but nothing anchors
the model's *intent* for the un-applied remainder — so names drift and steps
duplicate.

## 2. The law that must not move

Supervision semantics are untouched in every option below: one server-issued
single-use token per YELLOW action, consumed via redeem; RED refused always;
grants session-scoped and cleared at done; the structural authority gate and
the W3 conformance guard stay green verbatim. This design changes only the
FIDELITY OF THE MODEL'S CONTEXT on resume — never what is permitted.

## 3. Options

### A. Turn-state continuation (RECOMMENDED)
When a turn pauses on `human_required`, persist the in-turn conversation tail
(the model's assistant messages + tool results accumulated after the client
messages) as transient turn state: keyed by session_id, TTL = the approval
token TTL, stored beside the session (NOT the cortex bus — this is hot-path
turn context, not an observation; and NOT authority — replaying it grants
nothing). On resume (approvalTokens present), after `_pre_apply_grants`
anchors the on-disk truth, append the stored tail so the model continues
mid-plan: it sees its own prior reasoning, its own tool_call for the approved
write and the grant's applied result, and proceeds to the NEXT step of the
SAME plan.
- **Drift:** eliminated at the source — names were minted once, in turn 1.
- **Pauses:** exactly one per YELLOW action actually needed by the plan.
- **Fail-soft:** state missing/expired/corrupt → today's behavior (fresh
  re-plan). Nothing new can break a turn.
- **Cost:** a small transient store + wiring in the pause and resume paths;
  the deepest-touch option (the generate handler's turn assembly).

### B. Plan-pin note (cheap, partial)
Persist only the paused step's tool_call args; on resume inject one system
note: "Already applied: <files>. Continue your original plan; do not rename
artifacts; next approved step: <action>." No convo replay.
- Kills most duplicate-artifact drift; does NOT stop the model re-planning
  the remainder differently. ~20% of A's cost, ~60% of its value. Can ship
  first and be subsumed by A later.

### C. Batch plan-then-approve (NOT recommended now)
Dry-run the model to collect ALL writes, present one human_required carrying
every creation, one approval lands all. One click total — but the agent loop
semantics change deeply (the model can no longer react to intermediate
results), the diff the human approves grows large, and partial-approval UX
becomes its own project. Park it.

## 4. Acceptance (whichever option is ratified)
- A live two-file directive (the PROVE_IT.md witnessed run) completes with
  ≤ one pause per YELLOW write, ZERO drifted/duplicate artifacts, outcome
  `verified_success`, one skill minted whose recipe carries both writes.
- `prove_it.py --live` (real local model) becomes reliably 7/7 across 3 runs.
- W3 conformance guard, approval round-trip suite, and the full gate stay
  green; no new authority path (adversarial review confirms the stored tail
  cannot smuggle grants, tokens, or zone changes — it is model context only,
  fed through the same gated tool loop).

## 5. Sequencing
Operator ratifies an option (A / B-then-A / C) → writing-plans skill turns it
into slices → Sonnet fleet builds under the supervision pattern (adversarial
verify mandatory) → Fable reviews, commits, operator lands. Same discipline
as the cortex bus. Nothing starts until the fork is chosen.
