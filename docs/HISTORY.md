# GAGOS: the honest history, from the first commit to 2026-10-21

*Written 2026-10-21 from the git history: 1,793 commits and 527 pull requests,
across 105 days with a commit. Every dated claim below names the PR that made it.
Where a claim was later found wrong, both the claim and its correction are here.
Nothing was removed to make the story look better. The current, verified state
is `HONEST_STATE.md`. This file records how the project got there.*

## Who built it

- **The operator** (`swap821`) owns the system and the machine, makes every decision recorded as an "operator decision", merges every PR, and holds every key.
- **Claude** (Claude Code) co-authored 974 commits: backend, governance, learning, evidence and docs.
- **Codex** co-authored 200 commits, mostly the frontend (the living mirror and the GAGOS 2030 renovation). It also reviews.
- **Kimi** co-authored 6.

## The five months at a glance

| Month | Commits | PRs | What was built | What turned out to be wrong |
|---|---|---|---|---|
| June | 694 | #1–#57 | A Python agent with memory, a security gateway, approvals, self-analysis, and the 3D "living being" frontend | Nothing was measured yet: claims ran ahead of checks |
| July | 648 | #73–#169 | The cerebellum (learned reflexes), the sovereignty proof, voice, the worker foundry, the 54-organ model | "54/54 organs green" (#155) |
| August | 129 | #170–#273 | A mechanical green contract, the operator's §VIII signature, three red-team campaigns, the golden cohort, security fixes | "54 green / 0 yellow" again (#256) |
| September | 185 | #274–#429 | The recount (5, not 54), organs re-earned on executing proofs, organ 55, fail-closed guards, the learning-loop audit and hardening | Several greens that were not; evidence orphaned by squash merges |
| October | 137 by 10-21 | #429–#538 | Production readiness (H1–H8), the payoff experiments, the first self-repair, key and identity recovery, the D12 lessons, the first live reflex | Learning was judged twice and did not help |

## June: from a chat app to a governed agent

- **2026-06-01, the first commit** (`c7ee68d0`). On the same day:
  - the Node.js backend was rewritten in Python 3.12;
  - it gained a four-layer memory with hybrid BM25/FAISS retrieval;
  - it gained a deterministic security gateway with a hash-chain audit log;
  - it gained a reflection agent on a local Ollama model.
- **06-02 to 06-04: the agent loop.**
  - planner, sandboxed executor and git rollback;
  - the React frontend, connected to the backend;
  - a chat that can act (the agentic tool loop);
  - lessons promoted from pending to verified;
  - a resumable in-chat approval for YELLOW actions;
  - `edit_file` with a diff preview;
  - a verifier that runs tests;
  - an opt-in AWS Bedrock provider;
  - the first scope-lock bypass fixes;
  - the Claude Code continuity system (`.aios/`).
- **06-07 to 06-08: the first PRs (#1–#11).**
  - The verifier and planner were wired into the live loop.
  - The self-analysis module (T0–T3) appeared: it reads its own code, diagnoses it, and proposes diffs, but never applies them.
- **06-22 to 06-23: the living being (#13–#53).** The 3D WebGL brain, its nerves and voice. Many PRs were the operator's direct visual calls.

*Honest note.* June built very fast, and the words "sovereign" and "verified"
were used before anything measured them. The rest of the history is largely the
work of making those words true, or withdrawing them.

## July: sovereignty, the organs, and an inflated green

- **07-03: the sovereignty phases.**
  - the cerebellum compiled-experience engine (#73);
  - a knowledge graph (#77);
  - the sovereignty proof and offline mode (#79), now `prove_sovereignty.py`.
- **07-04 to 07-07.**
  - local voice (faster-whisper and piper, #101);
  - the wonder organs, on by default (#99);
  - the learning-loop prover, which then passed 19/19 (#119, #125).
- **07-13 to 07-14.** The bounded worker foundry (#139) and the Slices 9–24 convergence (#141).
- **07-25: "54-Organ Production Baseline (54/54 Organs Green)" (#155).**

*Corrected later.* That 54/54 was not credible. On 2026-09-01 the ledger was
recounted and the true number was **5** (#281). The prover's 19/19 did not last
either: it later failed 7 of 8 nights on a 0.5b model, because it scored "the
model never reached the check" as a violation (fixed in #392).

## August: governance made real, and attacked

- **A green that executes.**
  - The twelve-condition gate stopped pattern-matching: C3–C9 now run the tests they certify (#171, #186, #187).
  - A proof that had called a cold start "restart resilience" was corrected (#182).
- **The operator's signature.**
  - §VIII got an approval channel (#191).
  - The signing tool can never hold a private key (#192).
  - Organs 1–5 went green on the operator's §VIII signature (#197).
- **Red team.** Three campaigns found 17, 7 and 4 bypasses of the constitutional screens, and all were closed (#201, #203, #206).
  - The lesson recorded: screens are not the security boundary. Organ 46 was re-anchored on a provable invariant (#204).
  - #205 corrected a false claim an agent had recorded about organ 46 (that a wording change was a ratifiable amendment).
- **Organ 44, the golden cohort.**
  - It had never run. It went 0/5 → 1/5 → 2.667/5 over many fixes (#214–#246).
  - Endurance had never run either. Its first real measure was 0.611, RED (#218).
- **Security audit (08-19).**
  - The sandbox could write the spine that judges it (#257).
  - The audit verifier trusted keys it stored itself (#258), with downgrade and erasure loopholes (#259).
  - All were fixed.
- **08-19: "54 green / 0 yellow" (#256).** Superseded within two weeks (below).

## September: the recount, and the learning loop held to the cage's standard

- **09-01: the recount.**
  - "The organ ledger's true green count is 5, not 54" (#281).
  - Waves 1–4 re-earned organs on proofs that execute, reaching 53 green / 1 yellow (#282–#287).
  - The same day, `complete()` was found sending prompts to the cloud without redaction, and fixed (#280).
- **Organ 55, the Refusal Reel** (#289): a benchmark that judges GAGOS by what it refuses.
  - Authority-surface holes were found and fixed: remote code fetch on approval alone (#295), a secret leak on the verify route (#296), loopback treated as identity (#299), approval without a fresh human act (#300).
  - #298 corrected a sovereignty claim that organ 55 measured as false.
  - A 43-model cohort found 0 breaches. All 14 failures were the benchmark blaming GAGOS for weak models (#340).
- **Fail-closed by default.** 13 fail-open guards were converted and the budget went 15 → 0 (#329).
  - "Green did not mean governable": the 54 became **13** (#331), then were re-earned to 44 at HEAD (#344).
- **Evidence and squash merges.** Master went red repeatedly because evidence cited commits that squash merges had orphaned (#345, #347, #354, #360, #365, #368). Guards now refuse it at the source.
- **Write steps compile.** They compile as checks, and a replay re-performs a write only on an exact human approval (#316–#324).
- **The learning-loop plan (09-25 onward).**
  - A threat model and red-team reel: every structural attack landed on the undefended tree (#369).
  - Containment: a replayed command needs a human's approval (#370), unverified memory is never recalled (#372), and learning stops under the emergency stop (#373).
  - Payoff run 1 was graded by a broken instrument and discarded (#371).
  - One owner per learning store (#376); the skill library became the only skill store (#412).
  - Signed provenance (#413), operator re-admission row by row (#420), bounded writes (#425).
  - A behavioural red team found that **5 of 6 strong models act on a poisoned verified lesson** (#405). That led to "recalled memory is data, never authority" (#421).
- **Frontend.** Codex shipped the living mirror (#350) and the GAGOS 2030 renovation (#363, #385).

## October: production readiness, and the payoff question

- **The learning guards proven** (10-04 to 10-11).
  - 521 mutations with 0 survivors (#443).
  - Organs 56–59 now govern the learning loop on the live path (#445).
  - Harmful memory is quarantined, revocation sticks, and the freeze is on the bus (#447).
- **H1–H8, production readiness** (10-11).
  - one scoreboard (#453);
  - keys in Windows Credential Manager (#455);
  - safe backups (#457);
  - sovereignty drills measured live (#458);
  - one law for cloud egress (#459);
  - a measured intelligence benchmark (#460).
- **10-12: the gaps measured.**
  - The one-gateway census found a `/plan` bypass and a chat 500 (#467).
  - The usefulness census found **0 of 23 lessons reached a live turn**.
  - Organ 32 was demoted to yellow (#489).
- **10-12: the first judged payoff, Phase 8: not met** (#480). Lessons did not beat a placebo (64 vs 64). There was no harm.
- **10-18 to 10-19: GAGOS can maintain itself.**
  - First self-repair: the vulture's dead imports (#495). Live on 10-19, mission `maint-3b41d3d6` reached VERIFIED_RESOLVED.
  - A reflex may replay only a command a human approved exactly (#510).
  - Health watch (#517).
  - A rebuild drill: recovered from GitHub plus a backup in 7.6 minutes (#518).
  - The spine signing key `2451e67b` was lost and rotated (#516).
- **10-19 to 10-20: identity and keys.**
  - The operator lost both secrets and recovered without losing the operator id or the 11 lessons scoped to it (#522, `docs/operations/OPERATOR_RECOVERY.md`).
  - Promotion and checkpoint now need a real key; there is no public default (#523).
- **10-19 to 10-21: D12, lessons written by a strong teacher.**
  - Kimi K3 taught two students on 156 practice targets.
  - Every one of 168 verified lessons was fact-checked: 106 true and specific, 9 false (5%).
  - The operator re-admitted the 106. **117 lessons now reach the operator's turns**.
  - The cloud judged run: **neither cloud member met, no harm** (`docs/learning/PAYOFF_D12_RESULT.md`).
  - The local judged run had not been run yet (it ran 10-25 to 10-28, below).
- **10-21.** A new certifi advisory (PYSEC-2026-4320) failed every PR's CI. Fixed by #527.
- **10-21 to 10-25: the first live reflex.**
  - The operator activated and signed three skills (#529).
  - A learned reflex served one of his real turns with no model call in its action. His own script checked it. The record is local, not in git.
  - Two defects the check exposed were fixed:
    - a sandbox outage had counted as a failed verification (#535);
    - the turn consulted two models before checking for a reflex (#537).
  - Five new dependency advisories turned master red; #536 fixed them.
- **10-28: the reflex re-proved with #537.** The operator re-ran the check. The whole turn made **no model call**: the reflex served it, the verify passed STRONG, and no approval was asked. Its skill was learned on a toy test, so this proves the mechanism, not organic learning.
- **10-28: the learning chain, end to end on real code.**
  - A new skill was learned from three live turns over a real repository test.
  - The operator activated it; the sweep compiled it into a reflex; and that reflex served a request with **no model call**.
  - It ran on a separate proof backend scoped to a fresh checkout of the repo.
  - Learning Ledger L3, L4 and L5 are now earned organically.
  - Two local trails were committed as frozen copies, so the ledger reads **8 of 8 green in a clean clone too**. Before this it was 1 of 8.
  - Found on the way: the activation tool could not name any newly learned skill (#543).
- **10-25 to 10-28: D12's local judged run: not met, no harm** (`docs/learning/PAYOFF_D12_RESULT.md`).
  - With lessons, the local student earned 91 of 249, against 103 without: 12 targets better, 18 worse, p = 0.21.
  - **The D12 family is not met.** Learning has now been judged by two pre-registered families, and neither found a benefit.
- **10-31 to 11-02: D13's judged run (local only): not met, no harm** (`docs/learning/PAYOFF_D13_RESULT.md`).
  - The student was shown only lessons about the code its task names. It earned 33 of 141 with them and 40 of 141 without: 5 targets better, 9 worse, Holm p = 0.48. Against a placebo: 4 better, 6 worse.
  - 38 of 85 targets were lost to 420 s timeouts on a 16 GB laptop, so the test was weaker than planned.
  - **Three pre-registered families have now judged learning, and none found a benefit.**

## Claims that were wrong, and their corrections

| Claimed | Found | Where |
|---|---|---|
| 54/54 organs green (07-25, again 08-19) | 5 credible (09-01). Re-earned to 53, cut to 13 as not governable (09-13), re-earned to 44 at HEAD; 50 / 59 today | #155, #256, #281, #331, #344 |
| Learning-loop prover 19/19 | Failed 7 of 8 nights: it counted "not reached" as a violation | #125, #392 |
| Restart resilience proven | It was a cold start | #182 |
| A claim about organ 46 (made by an agent) | False, and corrected | #205 |
| A sovereignty claim in the docs | Measured false by organ 55 | #298 |
| "The clean-box stranger test is blocked" | It was not, and it found 4 real install gaps | #314, #315 |
| The endurance nightly was a signal | It was red for about 60 runs, gated on a 0.5b model's obedience | #346 |
| The "universal" intelligence gateway | Measured, not enforced; organ 32 demoted | #467, #489 |
| The learning loop helps | Not shown: Phase 8 not met; D12 not met, cloud or local; D13 not met, with relevant lessons only | #480, `PAYOFF_D12_RESULT.md`, `PAYOFF_D13_RESULT.md` |
| The One Law holds | Writes could not compile until 09-07, and no skill is active on the operator's machine today | #316, `HONEST_STATE.md` |

## Mistakes by the agents, recorded so they are not repeated

- **Destroyed work.** Claude ran `git reset --hard` after an aborted checkout. It destroyed 15 files of Codex's uncommitted work, which could not be recovered. The rule now: an aborted checkout is a safety stop.
- **Bulk operations swallowed other work.** Twice, `git add -A <dir>` and sweeps by path absorbed work they should not have touched.
- **A machine-occupying run launched without asking.** On 2026-10-19 Claude started the 30-hour local practice run without asking. The operator wanted to restart the laptop first. The rule now: ask before any long run.
- **Wrong estimates.** The D12 cloud judged run was estimated at 3 hours and took about 8. A count in its first report was wrong (118 ties, not 107) and was fixed before merge.
- **Instruments trusted before they were checked.** Payoff run 1 (#371) and the "hollow run" class were both checked only after they had produced results. The rule now: inspect a real observation before trusting a result.

## Where this leaves things (2026-10-21)

The verified detail is `HONEST_STATE.md` ("State on 2026-10-21"). In one paragraph:

The cage is substantially built and attacked. The organ ledger stands at 50 green
and 9 yellow of 59 organs, with known attacks closed and the learning guards
mutation-tested. The animal is not yet shown to be useful. 117 fact-checked
lessons reach the operator's turns, but two judged experiments found no payoff on
the cloud student. The local student, which the pre-registration names as the
most likely to benefit, is next. No learned skill is active, so no reflex serves
a live turn. GAGOS has repaired itself once, live. It has been rebuilt from
scratch in 7.6 minutes, and the operator has recovered from a lost credential
without losing anything.
