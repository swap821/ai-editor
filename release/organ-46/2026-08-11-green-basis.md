# Organ 46 — the basis for green

**Date:** 2026-08-11 · **Flipped at:** `3dc7323d` · **Counts:** 51→52 green, 3→2 yellow

This document exists so that anyone reading `status: "green"` in the ledger can
see exactly what that word is claiming, what it is not claiming, and who
produced the evidence.

## What green asserts

Two properties, both mechanically proven and both re-checked on every CI run.

**1. No path from a machine-authored lesson to an activated constitutional
change without a real, already-consumed human capability bound to that exact
change set.**

Proven by exhaustive AST enumeration rather than by example:
`tests/test_ratification_invariant.py` finds *every* write of
`status = ratified|activated` anywhere under `aios/` and requires each to sit
in a sanctioned, fully-qualified function behind the capability gate. Proven
non-vacuous twice — by planting an unguarded writer, and by planting a nested
impostor sharing a sanctioned name. Both were named by file, function and line.

The binding to the *exact* change set is `ratified_changes_digest`, recorded at
ratification and re-verified at activation, so a capability spent on one change
cannot activate another.

**2. A ratified amendment changes what the system enforces.**

Proven end to end through the real HTTP API, request by request, with nothing
hand-constructed:

```
edit BEFORE  -> 200 OK
ratify       -> 428 capability challenge -> 200
activate     -> 428 capability challenge -> 200
edit AFTER   -> 403 Forbidden
```

Same path, same file, opposite outcome, because an operator ratified an
amendment. Until this date, activation bumped a version counter and applied
nothing at all.

## What green does NOT assert

**The textual screening layer is not sound, and green does not claim it is.**
Four adversarial campaigns produced 31 confirmed findings against it. It is
advisory, evadable by paraphrase, and says so in its own API response
(`screen_limits` on every `check-simulations` reply). The organ's green rests on
the two properties above, not on the screen.

**The amendable surface is narrow.** v1 covers two fields (`scope_roots`,
`frozen_paths`) and one direction (protection-increasing only). Removing a
frozen path or widening scope is refused at ratification. `provider_policy_digest`
and `autonomy_policy_digest` are not amendable at all.

**Nobody outside this system has reviewed any of it.**

## Who produced the evidence, and the honest caveat

Four adversarial campaigns (70+ agents, 31 confirmed findings, each candidate
routed to an independent refuting agent). The fifth pass was **run by the model
itself** rather than as an independent campaign, because weekly usage limits
made another campaign impossible. That is a real reduction in independence and
it is recorded in C4 rather than glossed.

It matters more than usual here because of a pattern this work established:

**Five times in one day, a capability was added and the path was not wired.**
The screening layer, the store round-trip, the merge that dropped a security
fix, the API route, and finally the enforcer itself. Each was found only after
the previous one was declared done. The self-run pass predicted the fifth
before running — but only because the first four had taught it where to look.

A reader should weight the model's assurances about its own work accordingly.
The two properties green asserts are the ones with mechanical proofs precisely
because assurance was not enough.

## The self-run adversarial pass (2026-08-11)

Seven attacks, written down before running so the result could not be
reverse-fitted.

| # | Attack | Result |
|---|---|---|
| 1 | Enforcer reachability from production | **FINDING** — import-time singleton, no snapshot; fixed |
| 2 | Union bypass: can a snapshot drop a frozen prefix? | clean — 7 probes, spine stays frozen, none over-block |
| 3 | Digest collision between omitted and present defaults | clean |
| 4 | Privileged fields smuggled in at propose time | clean — all six refused with 422 |
| 5 | Rollback lineage | **FINDING** — silently discarded two later frozen paths; fixed |
| 6 | `propose_amendment(**extra)` passthrough | **FINDING** — ratification fields settable; closed |
| 7 | Fold edge cases, incl. removing the last scope root | clean — empty scope roots is fail-CLOSED |

Attack 4's first hand-run reported every field as "accepted". That was a 403
from a script with no privileged session — a defect in the harness, not the
code. It is recorded because a pass that only reports its successes is not an
adversarial pass.

## Blocker disposition

Every blocker was dispositioned, not deleted.

| Former blocker | Disposition |
|---|---|
| "no Ollama — live path needs a live model" | **False, measurably.** Organ 46's path references no LLM client, provider or model call. Pinned by `test_the_stale_ollama_blocker_is_measurably_false`. It survived because `organ_ledger.py`'s permitted-reason regex accepts the literal phrase, so the check was satisfied by the wording. |
| "marker screening is the wrong control" | **A finding, not an open task.** Moved into C4/C5 as a recorded limitation. The screen is correctly scoped as advisory and green does not rest on it. |
| the three human-red-team blockers | **Folded into C4 as a limitation**, per the operator's decision to narrow the claim rather than assert the review requirement was met. |

## How to re-check this

```
python -m pytest -q tests/test_amendment_reaches_enforcement.py
python -m pytest -q tests/test_ratification_invariant.py
python -m pytest -q tests/test_applicable_amendments.py
python -m pytest -q tests/test_amendments_bind_behaviour.py
python -m pytest -q tests/test_governance_red_team_corpus.py
python scripts/verify_organ_contracts.py
```

## If this ever stops being true

Demote it. The value of this ledger is that a green means something; an organ
that keeps its colour after its proof breaks is worth less than an honest
yellow. The prior campaigns' findings are all pinned as tests precisely so that
a regression fails loudly rather than quietly.
