# Organ 46 — decision memo: should it go green?

**Author:** the model. **Decider:** the operator. **Status:** organ 46 is yellow
and stays yellow until you say otherwise.

This memo exists because the alternative was worse. I told you changing organ
46's C4 wording was a constitutional amendment you would ratify under Law XIII.
That was false — verified below — and I had already committed it to this repo's
ledger, to `ac8736c6`'s message, and to PR #204. Drafting that amendment would
have used a real security control to lend borrowed legitimacy to a ledger edit
I authored and am arguing in favour of.

So: no amendment. A memo, and your decision.

---

## 1. The correction, stated plainly

`ConstitutionSnapshotV1` contains exactly twelve fields:

```
constitution_id, version, foundation_laws, policy_references, scope_roots,
frozen_paths, provider_policy_digest, autonomy_policy_digest, created_at,
ratified_by_operator_id, previous_snapshot_digest, snapshot_digest
```

It contains **no C1–C12 and no red-team clause**. The twelve-condition contract
lives in `scripts/verify_organ_twelve_conditions.py`. Organ 46's C4 verdict is a
string in `.aios/state/ORGAN_GREEN_LEDGER.json`, authored by me in an earlier
session.

Pinned by `tests/test_ratification_invariant.py::
test_the_twelve_condition_contract_is_not_constitutional_content`, so the next
confident sentence about which mechanism governs what will fail a test rather
than reach a commit message.

**The mechanism is an operator decision on the ledger.** Which is why this is a
memo.

## 2. What changed today

Three PRs (#201, #203, #204) and two adversarial campaigns (49 agents, 24
confirmed bypasses).

The load-bearing discovery was not any bypass. It was that
**`check-simulations` gates nothing** — it returns a report;
`ratify_amendment_route` decides and never consults it. The realised impact of
all 24 confirmed bypasses was therefore exactly one thing: a false passing badge
shown to a human.

That reframes what organ 46 could honestly claim:

| | before | after |
|---|---|---|
| green rests on | the screening layer being sound | the ratification invariant |
| provable? | no — paraphrase is unbounded | yes — exhaustive AST enumeration |
| screen's status | presented as *the check* | advisory triage, says so in its own API response |
| "who ratifies" | prose in `proposed_diff` | `approval_model`, a frozen one-member type |

## 3. The case FOR green

**The invariant is proven, not asserted.** `test_ratification_invariant.py`
enumerates over the AST every write of `status` = ratified/activated anywhere
under `aios/` and requires each to sit behind the capability gate. Not a
happy-path test — a test about code that does not exist yet. Non-vacuity
demonstrated by planting an unguarded writer and confirming it is named by file,
function and line.

**Two campaigns attacked and never reached the boundary.** 49 agents, 24
confirmed findings, zero touching `ratify_amendment`. One finding claimed to,
and the campaign's own synthesis flagged the claim as inconsistent; verified
that `api/routes/governance.py:283` requires
`isinstance(proof, ConsumedCapabilityProof)` and 403s otherwise.

**The organ now states its own limits in the response body**, not in a docstring
nobody reads. A reviewer is told the screen is evadable, at the moment they read
its verdict.

**The semantic attack class is structurally dead.** Timeout ratification,
objection windows, delegate approvers, risk tiering — bypasses as prose, and as
data they do not typecheck. There is no paraphrase of an invalid enum member.

**Every finding from both campaigns is pinned** — 470 corpus cases, including a
330-character generalisation sweep that caught my own first remediation being
incomplete.

## 4. The case AGAINST green — read this one twice

**I am arguing my own grade.** I wrote the code, the tests, the campaigns'
prompts, the caveat now inconvenient to me, and this memo. Every argument above
is mine. That is not a disclaimer; it is the strongest single reason to discount
what you just read.

**I was wrong about the governing mechanism today, with total confidence, in a
commit.** Not about a subtle race — about which control governs a rule, in the
organ whose subject is which controls govern what. If I got that wrong, the
prior on the rest of my reasoning here should move.

**The C4 caveat is still true.** Agent campaigns are not a human red team. My
argument is not that it has become false; it is that green would now assert
something the caveat does not disclaim. That is a *reframing*, and reframing is
what motivated reasoning looks like from the inside.

**The green would be narrower than the organ's name implies.** "Constitutional
Learning Organ" green would mean "the ratification invariant holds", not "this
organ safely governs what GAGOS may learn." Anyone reading the ledger without
the memo would infer the second.

**The trend is against.** Campaign two found *more severe* defects in the fix
than campaign one found in the original. Two data points, both pointing the same
way. A third campaign against today's typed-data work has not run, and today's
work is hours old — the same objection I raised against going green yesterday,
and it has not stopped being true because I am now the one inconvenienced by it.

**Nothing forces this.** Yellow costs nothing except a colour in a table. There
is no deadline, no dependency, no blocked work.

## 5. What green would and would not mean

**Would:** no path exists from a machine-authored lesson to an activated
constitutional change without a real, already-consumed human capability, proven
exhaustively and re-proven on every CI run.

**Would not:** that the screening layer is sound. It is not, cannot be, and the
organ says so in its own API response and evidence.

## 6. The options

**A. Stay yellow.** Costs nothing. The evidence keeps accumulating and this memo
does not expire. My recommendation is that this is defensible indefinitely.

**B. Run a third campaign against the typed-data work first,** then revisit. The
strongest option on evidence: it attacks something never attacked, and today's
architecture is exactly the sort of thing that looks sound to its author. If
your instinct is that green is close, this is how to find out cheaply.

**C. Go green on the narrowed claim now,** with C4 rewritten to describe what
the organ's integrity evidence actually is and the human-red-team line kept as a
recorded limitation rather than a blocker. Defensible on the evidence. Requires
believing my reframing, from someone who was confidently wrong today.

**D. Decide green is the wrong target for this organ.** Its subject is
undecidable — whether a proposal reduces human authority is not determinable
from text. An organ whose honest state is permanently qualified may deserve a
different label than the other 53.

## 7. My recommendation

**B, then C.** Not A — the invariant work is real and I do not think it should
sit unrecognised forever. Not C today — I was wrong about a governing mechanism
this morning, campaign two found worse in the fix than campaign one found in the
original, and the typed-data work is hours old.

One campaign against the new architecture is a few hours and settles it. If it
comes back thin, C becomes a straightforward call and you will be deciding on
three data points instead of my say-so.

If you overrule this and take C now, the ledger diff is ready and I will state
plainly in it that green was taken on the model's reframing against the model's
own recommendation. That is a defensible record. What I will not do is write it
as though the question were closed.
