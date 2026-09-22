# The Learning Ledger

*Status as of 2026-09-22: **8 green / 8 faculties**, computed by
`scripts/verify_learning_conditions.py` and enforced by the `learning-ledger`
job in CI. This document describes the apparatus; the ledger itself is
`.aios/state/LEARNING_LEDGER.json` and it is the authority. Where they
disagree, the ledger is right and this file is stale.*

## Why it exists

GAGOS had two halves with very different standards of proof. The cage — 55
organs, twelve conditions each, machine-verified, mutation-probed, operator
attested — could say precisely what it had proven and what it had not. The
animal could not. Learning features were tested, documented and shipped, and
the honest answer to "does the loop actually learn?" was a shrug backed by
anecdotes.

This is the same apparatus pointed at the animal. Eight faculties, twelve
conditions, verdicts **computed and never declared** — the JSON has no field
anyone can write `PASS` into.

## The eight faculties

| | faculty | the claim |
|---|---|---|
| L1 | Reflection | a real failure becomes a lesson |
| L2 | Lesson transfer | the lesson is recalled and confirmed by a later success |
| L3 | Skill acquisition | repeated STRONG successes verify an arc |
| L4 | Reflex compilation | a verified arc becomes a playbook |
| L5 | Reflex replay | a turn is served with **zero** LLM calls |
| L6 | Curriculum progression | levels are proposed, trained, and mastered |
| L7 | Organic acquisition | the loop can be fed from real code, contained |
| L8 | Measurement integrity | the instrument refuses to score what it did not measure |

## The twelve conditions

Mirrored from the organ ledger's C1..C12 **in meaning**, not in wording.

| | condition |
|---|---|
| LC1 | a production entrypoint exists |
| LC2 | it is reachable from the live turn path |
| LC3 | its state is durable |
| LC4 | its transitions are journalled append-only (or declared N/A with a reason) |
| LC5 | it fails closed, tested |
| LC6 | focused tests exist and RUN (a suite that collects nothing is not coverage) |
| LC7 | integration tests exist and RUN |
| LC8 | a mutation probe shows that breaking it would be noticed |
| LC9 | no residual blockers — and a blocker is stated, never hidden |
| LC10 | **organic** live evidence: it works on real code, not on a toy world |
| LC11 | that evidence names the commit that produced it |
| LC12 | that commit is an ancestor of HEAD |

LC10 is the one that mattered. Every faculty could pass LC1–LC9 against goals
the benchmark seeded for itself, which proves the mechanism and not the claim.

## What "organic" means here

Real models, doing real work, on this repository's own source — not
`training_ground/`, not `lab/`. The evidence comes from
`tools/organic_chain_run.py`, which drives the whole chain inside the
self-corpus: a throwaway git worktree pinned to a commit, `AIOS_SCOPE_ROOTS`
**replaced** (so `training_ground` and `lab` drop out too), a green baseline
required before anything runs, and the live tree fingerprinted before and after.

A run whose live tree moved is refused — including when the thing that moved it
was a commit by the person running it. That refusal is correct: the guard
cannot distinguish "the training escaped" from "someone else is typing", and it
must not guess.

## Things this apparatus refuses to do

These are not aspirations; each one has a test.

- **No condition is loosened to produce a green.** `aios/security/*` and
  `probe_common.ALLOWED_FILE_RE` are byte-identical to master.
- **A hollow run is not a verdict.** A suite that did not run cannot produce a
  PASS *or* a FAIL — `SuiteResult.hollow` refuses to score, because a dead
  instrument fabricating failures is the same defect as one fabricating passes.
- **A lucky pass is a fail.** L4/L5 may only cite a playbook whose skill *that
  run* earned; citing "the newest compiled playbook" once lit up on a leftover
  synthetic seed.
- **A failure is reported, never seeded.** If the model happens to succeed
  first time, L1 and L2 report NOT PROVEN rather than inventing a stumble.
- **The system does not expand its own training.** The curriculum miner
  proposes (`.aios/audit/curriculum-proposals.jsonl`, `accepted=false`);
  accepting is a human act, and a training harness doing it on the miner's
  behalf would be the same act wearing a different hat.

## Running it

```
python scripts/verify_learning_conditions.py      # the gate; exits non-zero on any red
python scripts/learning_scoreboard.py             # the numbers
python scripts/learning_scoreboard.py --check     # alarm: did a proven count go DOWN?
python tools/organic_chain_run.py --targets 1     # earn fresh organic evidence
```

The scoreboard needs a machine that has actually run the system: it reads
`data/aios_memory.db`, which is gitignored. On a store-less machine `--check`
prints `NOT CHECKED` rather than a clean bill of health, and it is deliberately
absent from CI for that reason — a green that means nothing is worse than no
check at all.
