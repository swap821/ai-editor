# The Learning Ledger

*Status as of 2026-09-28, Phase 2 slice 2.4c-B: **5 green / 8 faculties**
expected (L3, L4 and L5 yellow, each with a named blocker), computed by
`scripts/verify_learning_conditions.py` and enforced by the `learning-ledger`
job in CI. The switch to the skill library made the cited evidence for L3 and
L4 describe a path that no longer runs; see "Slice 2.4c-B" below.*

*Earlier status, 2026-09-24: 6 green / 8 (L2 and L4 yellow), then 7 / 8 after
#404 re-earned them. This document describes the apparatus; the ledger
itself is `.aios/state/LEARNING_LEDGER.json` and it is the authority. Where
they disagree, the ledger is right and this file is stale.*

*History, kept rather than rewritten: it reached 8/8 on 2026-09-22 in #359.
Squash-merging #359 discarded every commit the evidence cited and master fell
to 0/8; #360 re-earned the evidence at a commit already on master, and L2 and
L4 did not re-fire in three runs there. They are yellow with the reason stated
in the ledger — see "Why L2 and L4 are yellow" below — rather than re-pointed
at a run that did not produce them.*

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
| L3 | Skill acquisition | repeated STRONG successes make a library arc review-ready |
| L4 | Reflex compilation | an operator-activated skill becomes a playbook |
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

## Slice 2.4c-B: L3 and L4 yellow again (2026-09-28)

The institutional skill library became the only skill store
(`docs/learning/PHASE2_DESIGN.md`, slice 2.4c-B). Two faculty claims changed
with it, as stated before the switch was built:

- **L3** now means *review-ready*, not *verified*. Its owner is
  `InstitutionalSkillAdapter`. Nothing promotes itself: evidence makes an arc
  review-ready, and only the operator activates it. The cited organic evidence
  (skill 66, verified by the legacy store by itself) is of a path that no
  longer runs.
- **L4** compiles only from a skill the operator activated. The cited organic
  compile (playbook 16) came from a self-promoted skill, which can no longer
  happen.

Both are yellow with that blocker in the ledger. Re-earning them needs an
organic run that makes a library arc review-ready (L3), then the operator's
activation of such a skill and a run that compiles it (L4). L5 also needs L4's
activation first. The instrument itself did not notice: LC11/LC12 check only
that the evidence commit is recorded and on master, so a changed owner keeps a
stale green unless the blocker is written. That gap is recorded here rather
than hidden by it.

## L2 and L4 re-earned (2026-09-28); L5 stays yellow by design

> **Superseded for L4 by slice 2.4c-B (same day).** The compile below was of a
> self-promoted skill; see the section above. The run is true history and is
> kept as written.

Organic run `20260927T221713-b131ac59` at `701dda46` (master) used a ladder: the
local `qwen2.5-coder:7b` first, then Bedrock `deepseek.v3.2` and
`mistral.devstral-2-123b`. The artifact is
`docs/learning/organic_chain_20260927T221713-b131ac59.json`.

- **L2 (green).** The 7B's real failures were reflected locally, as production
  reflects, into lesson 107. A stronger tier then passed the *identical*
  failed command, and the lesson was promoted. **Scope:** the confirming model
  never saw the lesson. L2 is confirmation by the identical command, as this
  ledger defines it. Whether a lesson's *content* helps is the payoff
  benchmark's question, and its cloud baseline found no measurable benefit.
- **L4 (green).** A new verify-only arc, skill 90, earned three STRONG turns,
  and `try_compile_all` compiled playbook 16. It is a fresh compile, not the
  idempotent re-run that kept L4 yellow.
- **L5 (still yellow).** Playbook 16 matched, but its approval-needing `pytest`
  step was refused during replay, and the model was consulted. That is Phase
  0b's containment working: a reflex learned with no human approval cannot
  serve a turn alone. Earning L5 needs a step that a human approved (Phase 5),
  not a loosened gate.

## Why L2 and L4 are yellow

> **Superseded 2026-09-28.** L2 and L4 were re-earned; see the section above.
> This section is kept as dated evidence.

Both lost their organic evidence when #359 was squash-merged, and neither
re-fired in three runs of `tools/organic_chain_run.py` at `00dbf6f3`.

- **L2 (lesson transfer)** needs a lesson recorded from a real failure to be
  confirmed by the *identical* command later succeeding. The local model
  (`qwen2.5-coder:7b`) failed 12 of 14 real attempts and never recovered on the
  same command. That is its success rate on this corpus, not a broken link —
  conformance mission M2 still proves the mechanism. Re-earning it organically
  needs either more attempts per target or a stronger model tier in the ladder,
  which requires the operator's cloud credentials.
- **L4 (reflex compilation)** needs a *new* arc to reach three STRONG runs.
  `try_compile_all` is idempotent, so while the one organic playbook exists a
  re-run compiles nothing new and there is no fresh compile to witness.

A seeded failure would satisfy L2 and prove nothing; re-pointing a sha at a run
that compiled nothing would satisfy L4 and prove nothing. Both are refused.

## The ledger is not the judged number

The ledger proves the parts are real and honestly measured. It does **not**
claim any of it helps: no condition in LC1..LC12 asks whether learning improved
an outcome. That question belongs to the payoff benchmark
(`tools/learning_payoff.py`), the animal's equivalent of organ 55.

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
