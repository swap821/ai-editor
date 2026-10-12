# Honest State of Sovereignty

**Last updated:** 2026-10-12 (verified on `6b64b9ca`; earlier sections keep the
commit they were measured on)
**Proof script:** `prove_sovereignty.py` (18 assertions, 6 phases, all pass on `6b64b9ca`)

## State on 2026-10-12 (verified that day; nothing below was carried forward unchecked)

**The headline did not move this period. What changed is what is protected from being faked.**

- **Organ ledger: 50 green / 9 yellow / 59.**
  - Organ 32, the Universal Intelligence Gateway, was demoted today. It had no
    blockers, while its own claim was unmeasured on 13 of 27 model-call sites,
    3 of them in its own entrypoint `aios/runtime/intelligence_gateway.py`.
  - And "universal" is measured, not enforced: an ungated call is recorded,
    not refused (`docs/ONE_GATEWAY.md`).
- **The proof script proves the mechanism, not the operator's machine.**
  - `prove_sovereignty.py` passes 18/18 on a store it seeds itself.
  - On the operator's live store, 0 of 80 institutional skills are active (73
    candidate, 7 deprecated). So **no learned reflex can serve a live turn
    today.**
  - Learning Ledger L4 and L5 stay unmet until the operator activates a skill
    (`tools/activate_skills.py`, his act) and approves its step once (Phase 0b).
- **Write steps now compile.** This supersedes the 2026-09-01 and 2026-09-06
  statements below that they could not.
  - `create_file` and `edit_file` are in `_COMPILABLE_TOOLS`
    (`aios/core/cerebellum.py`), compiled as checks.
  - A replay performs a write only when a human approved the exact bytes
    (`aios/core/replay_writes.py`).
  - Those older statements are left as dated evidence.
- **Learning usefulness was judged and not shown.**
  - The pre-registered Phase 8 family (`docs/learning/PAYOFF_PHASE8_RESULT.md`)
    gave H1 not met: cloud 17 vs 11 targets, Holm p = 1.0; ON earned exactly
    what PLACEBO did (64 vs 64); the 7B was at the floor.
  - No harm (H2), and hardening kept utility (H3).
  - The next experiment, D12, is a new pre-registered family, so it cannot
    become a quiet re-grade of Phase 8.
- **Approval authority (M7)** was not re-measured on this date. The 2026-09-06
  correction below stands as last measured.
- **Per-task scope binding is defined but unused.**
  - `scope_context` (`aios/security/scope_lock.py`) has no production caller.
  - Every task runs under the global `SCOPE_ROOTS`.
- **Cloud.**
  - The production cloud key is held in Windows Credential Manager.
  - The shipped default `AIOS_BEDROCK_MODEL` (`amazon.nova-lite-v1:0`) cannot
    be called on demand in `ap-south-1`. The operator's `.env` overrides it.
  - Gemini and Vertex authenticate through `gcloud` ADC, not the keystore, so
    they are not 24/7-capable under the production keystore.
- **The clerk.**
  - Three local models qualify 22/22, and on the clerk benchmark
    (`docs/clerk/CLERK_BENCHMARK_RESULT.md`) they score 45 to 47 of 54.
  - The clerk's "frontier escalation" returns `rejected` and runs nothing.
  - A cloud clerk exists only as a §VIII proposal (#486, not applied), not
    under the name `reasoning`.
- **The endurance nightly fires every night, and it failed on each night from
  2026-10-07 to 2026-10-11** (the last five recorded). The tester aborts on 5 consecutive errors, so it records no
  usable evidence either way. The learning-loop prover in the same workflow
  passes.

## What "sovereign" means here

"Sovereign" is a testable property, not a marketing claim. This system is
sovereign to the extent that it can operate meaningfully without external
LLM calls, using only its own verified experience.

## What works offline

| Capability | Organ | Evidence |
|------------|-------|----------|
| Replay of practiced **read/verify** tasks | S1 Cerebellum | Compiled playbooks execute through the security gateway without an LLM. **Write steps do not compile:** `_COMPILABLE_TOOLS` (`aios/core/cerebellum.py:41`) admits only `read_file`, `read_directory`, `execute_terminal`, `verify` — `create_file`/`edit_file` need content that step summaries do not store. *(Superseded 2026-10-12: writes compile as checks; see "State on 2026-10-12". Note also that no skill is active on the operator's machine, so nothing replays there today.)* |
| Multi-hop inference | S2 Knowledge Graph | Confidence-weighted graph traversal composes answers from verified facts |
| Planning of known task shapes | S3 Native Planner | Verified skills and swarm patterns produce deterministic plans |
| Verification | Verifier | pytest runs via subprocess -- no LLM needed |

## What does NOT work offline

| Capability | Why | Honest degradation |
|------------|-----|-------------------|
| Novel tasks | No compiled playbook or verified pattern matches | Honest refusal: "I can't handle it natively yet" |
| **Replay of write workflows** | `create_file`/`edit_file` steps cannot compile into a playbook at all *(superseded 2026-10-12: they compile as checks, and a write replays only with a human approval of the exact bytes; see "State on 2026-10-12")* | Falls through to the LLM path. This is the workflow class the system most often performs, so the reflex layer does not yet cover its main job. |
| Reflection on failure | LLM needed to extract structured lessons | Silently skipped (logged at INFO) |
| LLM-based planning | LLM needed for novel task decomposition | PlannerError with explanatory message |
| Chat (novel conversation) | LLM needed for general reasoning | Honest refusal before LLM loop |

## What "verified" means

A skill is verified after 3+ STRONG successes at >= 80% success rate.
A swarm pattern is verified after 2+ successes at >= 60% rate.
A fact is committed only after contradiction detection.
Verification strength follows the taxonomy in `aios/core/verification_strength.py`.

## What sovereignty is NOT

- It is NOT a foundation model. The system does not generate text, reason about
  novel concepts, or produce creative output without an LLM.
- It is NOT autonomous. Every YELLOW action stops for an approval, and the
  cerebellum replays through the same gate as LLM-proposed actions.

  **Measured correction, 2026-09-06.** This bullet used to read "the operator
  has final authority on all YELLOW actions". Organ 55's mission M7 measures
  that claim and it FAILS: the approval token is returned to the principal that
  requested the action, so one principal can request and approve the same
  action with no human anywhere in the loop. The gate is real -- nothing runs
  without an approval -- but the system cannot presently prove the approval came
  from the operator rather than from the requester. The audit rows are
  identical. "Final authority" was a stronger claim than the evidence supports,
  and this document is the wrong place to make one.

  **Partly closed the same day.** Approving an action that fetches and executes
  remote code now requires an authentication event NEWER than the request, so
  the requester cannot authorise its own supply-chain fetch -- M7 measured that
  holding against a live server. The requirement is deliberately scoped there:
  YELLOW covers `mkdir`, `touch` and `pytest`, and a re-authentication per
  `mkdir` would be unusable, so an agent inside a privileged window can STILL
  self-approve ordinary work. The bullet above therefore stands as written for
  the ordinary case. This note is added rather than rewriting the correction,
  because dated evidence is not edited here -- it is superseded in place.
- It is NOT omniscient. The knowledge graph contains only verified facts. Its
  horizon is visible and honest.
- It is NOT permanent. A compiled playbook decompiles after 2 consecutive
  failures. A demoted skill invalidates its playbook. Sovereignty is earned
  and can be lost.

## Decided, not yet built

*(Superseded 2026-10-12. Option A was built after this was written. Stage 1 made
a compiled write step confirmable against a content digest, and stage 2 slice 1
(#319, 2026-09-07, `aios/core/replay_writes.py`) records exact, revocable write
decisions. The "blocker" named below no longer exists. The section is kept as
the 2026-09-06 record.)*

**The learning loop, Option A** (operator decision, 2026-09-06). Stage 1 is a
content-identical, idempotent `create_file`: replay checks the target digest and
abstains if it differs. The blocker is `_COMPILABLE_TOOLS` in
`aios/core/cerebellum.py`, which excludes writes, so a compiled playbook can
today replay only reads and commands.

Recorded here rather than built because it is roughly a three-week effort. The
alternative considered and rejected was Option B: narrow the public claim to
match what the loop actually does. The claim stays; the work is owed.

## How to prove it

```
python prove_sovereignty.py
```

18 assertions. Zero spin. If any fails, the word "sovereign" is revoked
until the underlying defect is fixed.

## The One Law

> A task the system has verifiably completed three times before executes
> entirely without an LLM call, through the full security gateway, with
> human approval on YELLOW steps, verified by the same evidence-based
> verifier that judged the original successes.

*(Superseded in part on 2026-10-12. Write steps now compile, as checks. A write
replays only with a human approval of the exact bytes. Separately, no skill is
active on the operator's machine, so the One Law currently holds for no live
task at all. See "State on 2026-10-12". The paragraph below is the 2026-09-01
measurement.)*

**Where the One Law holds today, and where it does not.** It holds for tasks
built from read, directory-read, terminal and verify steps. It does **not**
hold for any task that writes a file, because such a step cannot be compiled
into a playbook in the first place (`aios/core/cerebellum.py:41`). The Law is
therefore satisfied for a class the system rarely runs and unsatisfied for the
class it usually runs. Stated here rather than left to be discovered, because
the gap is the difference between the claim and the product.
