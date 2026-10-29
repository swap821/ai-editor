# Honest State of Sovereignty

**Last updated:** 2026-10-29 ("State on 2026-10-29" below; earlier sections keep
the commit they were measured on). The whole story, from the first commit, is
`docs/HISTORY.md`.
**Proof script:** `prove_sovereignty.py` (18 assertions, 6 phases, all pass on `6b64b9ca`)

## Later on 2026-10-29: the daily backend made dependable (branch `feat/daily-boring`, off master `062a328a`)

The operator's ask: "make the daily animal boring". Four things are built here; the fifth needs his own runs.

- **One way to start his daily backend** (`tools/daily_backend.py`, `docs/operations/DAILY_BACKEND.md`).
  - **Before:** its settings lived in an agent's scratch script. A backend started any other way failed silently: a different scope identity, so no earned reflex matched; or no learning key; or his user-wide cloud opt-in.
  - **Now:** `up` starts it with every setting he chose, each dated in the tool, and then runs `check`.
- **`check`: would each reflex serve here, now?** (`Cerebellum.readiness`, `tests/test_reflex_readiness.py`)
  - It is read-only and calls no model. It asks what a match and the replay preflight ask, using their own helpers.
  - It names each reason a reflex would not serve: another scope, replay of approved commands off, no approval in this workspace, an inactive skill, a RED command, or a stale file.
  - **Stale matters most.** A file the skill touches changed, for example after a refresh of `work/ai-editor`. The first matching turn withdraws that reflex, and only his re-activation brings it back. `check` says so before any turn does, and changes nothing. The test shows `match` then doing exactly what it warned of.
- **The cloud-first noise is fixed at its root** (`tests/test_bedrock_needs_credentials.py`).
  - Bedrock is offered only when a request could be signed. With `coding` opted into the cloud and no AWS key loaded, `auto` goes straight to the local model.
  - The positive control: with a key, it routes to Bedrock as before.
  - The daily tool also always sets `AIOS_ROUTER_CLOUD_TASKS` (empty unless chosen at launch), so his user-wide `reasoning,coding` no longer decides. Removing the user-wide value is his choice.
- **Chat needs no task scope, and the reason is now a test.** `/api/v1/chat` is a real entry surface: the HUD's voice channel.
  - A chat turn builds no tool agent and executes nothing, so a scope has nothing to narrow there.
  - The test fails if that ever changes. Its spies were checked against an `/api/generate` turn, where they do fire.
- **A review the same day found four more problems.** Each was checked on this machine before anything was changed.
  - **A `.venv` inside the repository counted as production code. It was a bug from #552, and it is now fixed.**
    - The README's install puts the virtualenv inside the repository. The gateway then judged pytest's own installed frames as repository code outside `tests/`, refused test-made calls, and the README's layout ran red: 28 tests, 42 across the gate.
    - It failed closed, so nothing got through.
    - CI and the agent's worktrees run a virtualenv outside the tree, so both stayed green, and every full-suite run the agent reported was green for that reason.
    - Now installed code is never repository code (`aios/core/model_calls.py::_relative`). Two tests fail without the change.
    - **The full suite then ran in his own checkout, with `.venv` inside.** Every test passed except 6, and those 6 fail the same way on unchanged master there. His `.env` values (`AIOS_LLM_MODEL`, `AIOS_BEDROCK_MODEL`) reach the tests: `tests/test_local_clerk_default.py` and five in `tests/test_route_wiring.py`. That leak is separate, and still open.
  - **His user-wide `AIOS_ROUTER_CLOUD_TASKS` also breaks the test suite.** `tests/test_aliveness_defaults.py` asserts that cloud routing is off by default, and it fails in any shell that inherits the value.
  - **The audit chain cannot verify on his machine, because its key could never be stored.**
    - `AIOS_AUDIT_PRIVATE_KEY` had no place in the keystore, so every start signed with a throwaway key: key_id 81 today.
    - The frozen logger anchors trust on that key's public half, so no anchor existed.
    - Now the keystore, the daily backend and the production container all carry it.
    - Still his: generating and storing the key, and deciding on the epoch boundary for the old entries (`docs/security/PROPOSAL_AUDIT_EPOCH_BOUNDARY.md`).
    - The claim that three of the four release-signing keys are lost or exposed is not yet checked.
  - **The first self-repair never reached master.** The 2026-10-19 repair stayed in the worktree `C:\gm`. #557 carries GAGOS's byte-identical diff, with its mission, promotion and verification ids.
  - **The mutation probe could score a kill that the mutation did not cause.**
    - A test leaves `training_ground/.git` pointing into a pytest folder that is then deleted. Every later session in that checkout fails, so every later mutation looked killed.
    - This happened here too, after the agent's own run.
    - **Fixed on branch `fix/probe-closing-control`, 2026-10-30.**
      - Sessions remove their own pointer and heal a dangling one.
      - The probe has a closing control: each test set that backed a kill runs once more on the unmutated code, and a failing one makes those kills NO VERDICT.
      - Fixed on the way: a nested pytest session deleted its parent's scratch, and `tests/test_bandit_gate.py` rewrote a tracked file's line endings. Both now leave the tree as they found it.
      - The full suite passes.
  - **Found while checking that: tests write into the operator's own rollback history.**
    - In his main checkout, `training_ground/.git` is a real git repository: his daily backend's rollback history.
    - A full test run there commits `[SNAPSHOT]` entries into it, and some tests create and delete files in `training_ground/`. One run added 5 commits.
    - Not fixed yet. It needs a decision on where the default rollback engine works under test.
- **Not done yet: reflexes on more real modules, and serving after a restart.** These need his approvals, his activation and his credential.
  - The script and both targets are ready: `tests/test_failover.py` (21 tests) and `tests/test_privacy_filter.py`. Each passed in the real sandbox under the bound scope.

## State on 2026-10-29 (measured on branch `feat/gateway-universal`, off master `692c5c78`)

- **A forge turn can be confined to one project** (`docs/operations/WORK_SCOPE.md`, "Per-task binding").
  - **What it is:** the frozen scope lock's narrow-only binding is now wired into `/api/generate`. The client declares it per turn (`scopeRoot`) or the launch environment does (`AIOS_TASK_SCOPE`), never the model.
  - **Refused, never ignored:** a scope the lock would not honour is a 400.
  - **Proof:** the same model command pauses for approval in one bound scope and is a scope violation in another. That proves the binding reaches the checks inside the streamed turn.
  - **What it narrows:** creating, editing and running commands. Reads stay project-wide.
  - **What it changes:** approvals and reflexes earned in a bound turn apply only to turns bound the same way. The model is told its scope and where its commands run.

- **The one gateway is enforced, not only measured** (`docs/ONE_GATEWAY.md`, "2026-10-29"). The operator asked for it to be proven.
  - **Why enforcement:** a drive only shows the paths it reached, and real use had already found one it missed. Now an ungated production call is refused before the adapter sends it.
  - **The proof, in three tested steps:**
    1. Only the provider adapters can reach a model.
    2. Each adapter records a call before sending it.
    3. A call with no entrance is refused.
  - **`AIOS_GATEWAY_ENFORCE`:** on by default. A `tools/` or `scripts/` program's own process is exempt unless the switch is set to `1`, and its calls are still recorded and judged. `0` turns refusing off.
  - **Driven with refusing on:** 15 surfaces made 74 model calls, all gated and none refused, and the ledger is complete. 21 of 29 candidate sites were observed. Of the rest, 2 are not model calls and 2 have no production caller, and the 4 not driven are gated by how they are built.
  - **Found and fixed:**
    - Memory recall could call the model directly when a route passed it no gated judge. `/api/v1/chat` passed none, but no turn could reach that, so it was latent.
    - Unbound Council worker reasoning called the model directly. The Council route always binds, so no reachable route is known.
  - **The switch is behind the freeze.** The operator authorized the move ("Honestly fix this", then "I'll allow it" after the safety classifier stopped the record). `AIOS_GATEWAY_ENFORCE` and both exemption lists now live in `aios/security/limits.py` (`release/section-viii/2026-10-29-gateway-enforcement-behind-the-freeze.md`). A typo never turns refusing off.
  - **Organ 32 is green: 51 green / 8 yellow** (was 50 / 9).
    - **The adversarial re-read closed three ways the proof could be broken.** None was a live hole.
      - Passing a call off as a measurement tool's: a call is now production if any frame on its stack is.
      - Faking an entrance: only the gateway may open one.
      - Reaching a provider SDK past the adapters.
    - **It also fixed one real bug:** pseudo-files such as `<frozen runpy>` counted as repo frames.
    - **CI caught a real case:** the live clerk tests ran organ 37's qualifier with a raw client, and the calls were refused. The tests now use the production composition.
    - **Its live evidence now includes a refused call.** `aios/core/model_calls.py` and `aios/security/limits.py` joined its entrypoints.
    - **The 12-condition verifier passes it:** 144 test files, 2824 passed, 0 failed. The verifier's other 5 local failures are environmental: no vitest and no live Ollama locally, both of which CI supplies.
    - **One reviewer, the agent, did the re-read.** The verifier and CI executed the tests.
- **D13's judged run was killed by Windows Update** on 2026-10-29 at 00:08, at target 8 of 85. Windows rebooted on its own to install KB5127936.
  - The harness writes its trail only at the end, so nothing can be judged. It restarts from scratch, on the same pinned code and store.
  - No interim result was tallied, so the restart is clean.
- **D13 was relaunched, then stopped at the operator's word, the same day.**
  - Relaunched at 11:44 UTC: the same code `e6e8d668`, the store re-copied with its hashes checked, the same arguments.
  - Stopped at about 12:50 UTC, at target 2 of 85, with no trail written, so nothing is judged. He asked for the daily system to be made dependable first.
  - **Memory was the hazard.** About 0.2 GB was free while the 9B model ran. Two of the first target's arms timed out, so the target was dropped as not comparable. The killed first attempt had 9 model errors in 66 attempts.
  - Kept as `C:\d13out\stopped-by-operator-20261029`. D13 stays pre-registered and unrun.

## State on 2026-10-28 (measured 2026-10-21 to 10-28; master `de88e7dd` unless a line says otherwise)

**Learning has now been judged twice, and neither time did it help. But the whole
chain now works on real code: a skill learned from a real test of this repository
became a reflex that served a request with no model call at all.**

- **D12 is judged: not met, and no harm** (`docs/learning/PAYOFF_D12_RESULT.md`, `payoff_d12_judged_result.json`).
  - The local student (`qwen3.5:9b`) ran the same 150 targets on the cloud run's code, from the store as it was before skills were activated.
  - With lessons it earned 91 of 249, against 103 without. By target: 12 better, 18 worse, p = 0.21. That is not significant, and not harm by the registered rule.
  - Real lessons against a placebo of the same size: 9 vs 12.
  - So no member of the four-member family is met, and the usefulness gate stays FAIL.
  - Diagnostic: recall does vary by task, but it is rarely about the task. Only 27 of 150 targets were shown a lesson from their own module.
- **D13 is pre-registered, not run** (`docs/learning/PAYOFF_PREREGISTRATION.md` D13; the operator chose it on 2026-10-28).
  - Lesson recall changes in the product: a task that names code is shown only lessons about that code, or none. Plain conversation keeps the old rule.
  - Measured offline, with no model: on D12's 150 targets the most-shown lesson drops from 109 targets to 9, and 51 targets see any lesson at all.
  - The run: 85 never-practised targets that a lesson about their code exists for, on D12's store snapshot, code and student. Only the recall rule differs. It takes about 1.5 days of the laptop.
  - Stated before it runs: it can only see a large effect (about 22 targets better against 8 worse), and D12's same-module targets leaned the other way (9 vs 15).
- **Skills.** On 2026-10-21 the operator activated three skills (41, 49, 79) and signed them (#529). The census admits 3 of 3.
- **The learning chain again, on the operator's daily system** (2026-10-29, `docs/learning/organic_reflex_proof_2026-10-29_daily/`). This makes a track record, not a first. It differs from 10-28 in one way: it ran on his daily backend, with his own store, rather than on a proof backend with a copied store.
  - **The setup.** His daily backend ran master `cd5faf54` and was started after its checkout moved there.
    - Every forge turn was bound to his work checkout `work/ai-editor` by `AIOS_TASK_SCOPE` (#554). The requests named no scope, so they were bound exactly as his own turns are.
    - The sandbox image was `aios-verify`. Replay of approved commands was on.
  - **L3, learned:** three live turns ran `pytest ai-editor/tests/test_gateway_enforcement.py -q`, 13 real tests of the enforcement shipped in #552. The local `qwen2.5-coder:7b` answered. Each turn was a STRONG pass, and he approved the exact command each time. The library made the new arc review-ready.
  - **L4, compiled:** he activated it, and the activation is signed. The next request's sweep compiled it into playbook 17 of his daily store (journal event 33).
  - **L5, served:** in that same request the reflex served the turn. The verify passed STRONG; no approval was asked and no interpreter or planner ran. **Zero model calls:** his model-call ledger stayed at 195 lines.
  - **So a reflex learned on his real code now serves his daily turns,** under the scope those turns run in.
  - **Recorded, and explained.** On the first leg of each Stage A turn, the tool agent's failover tried Bedrock before the local model, five attempts in all.
    - Each attempt failed with "Unable to locate credentials" before sending, because this backend loads no AWS key. The local model answered.
    - **The cause is the operator's own setting.** The backend inherited `AIOS_ROUTER_CLOUD_TASKS=reasoning,coding` from his user-wide Windows environment. That makes an `auto` coding turn cloud-eligible, and the router ranks the Bedrock models above the local one.
    - With AWS keys loaded, those calls would go to the cloud, after the privacy filter. Setting it to `""` in the launch environment keeps `auto` local-only. That is his choice.
- **The learning chain, end to end on real code** (2026-10-28, `docs/learning/organic_reflex_proof_2026-10-28/`).
  - **L3, learned:** three live turns, answered by the local model through the real API, ran `pytest ai-editor-selfcorpus/tests/test_relevance.py -q`. That is 4 real tests of `aios/memory/relevance.py`, each run a STRONG pass under the operator's exact approval. The library made the new arc review-ready, and nothing promoted itself.
  - **L4, compiled:** the operator activated it, and the activation is signed. The next request's sweep compiled it into playbook 17. This is the first compile ever observed from an operator-activated skill (journal event 33).
  - **L5, served:** in that same request the reflex served the turn. The verify passed STRONG; no approval was asked and no interpreter or planner ran. **Zero model calls:** the proof store's model-call ledger did not grow, and Ollama's own log shows no inference.
  - **The setup, in full.** A separate proof backend: the operator's code at `de88e7dd` and his keys, plus four differences. Its data is a copy of his store, its scope is a fresh checkout of this repo (the self-corpus), and its sandbox image is the app image, which has the repo's dependencies, with the same lockdown flags. Replay of approved commands is on. His approvals there are keyed to that workspace, so they authorise nothing in his daily one. The task was chosen to earn the faculties, as organic runs choose their targets.
  - **Two defects found on the way:**
    - The activation tool could not name any skill learned after the migration: legacy ids only. So no newly learned skill could ever have become a reflex. Fixed in #543.
    - The operator's live setup cannot verify this repo's own tests. Its scope is `training_ground/` and `lab/` only, and its sandbox image has only pytest. That is why every earlier live reflex was a toy. Both are his settings, and neither was changed.
- **A learned reflex served a live turn with no model call at all** (2026-10-28, `docs/learning/reflex_live_proof_20261028.json`).
  - The operator ran the check himself, on his backend running master `de88e7dd` (which has #537), started after the checkout moved to it.
  - Playbook 5 replayed a verify command he had approved exactly. It passed STRONG. No approval was asked, and no interpreter or planner ran.
  - **Zero model calls in the whole turn.** The model-call ledger stayed at 163 lines, and Ollama's own request log shows no inference request in that window.
  - On 2026-10-21 the same reflex served a turn that still made two model calls, the route picker and the interpreter (`reflex_live_proof_20261021.json`). #537 removed both.
  - **The limit, stated plainly:** playbook 5's skill (41) was learned by the July learning-loop prover on a toy test (`assert 1 + 1 == 2`). So this run proved the mechanism, not learning; the real-code chain above closed that gap the same day.
  - The committed records have the operator's principal id redacted, and each carries the sha256 of its original.
- **An outage is no longer a verdict** (#535). When the sandbox cannot start a command:
  - no verify verdict is given;
  - no skill is marked against;
  - no reflex is retired;
  - no command approval is withdrawn.
- **Learning Ledger: L3, L4 and L5 earned organically** (`.aios/state/LEARNING_LEDGER.json`).
  - Their blockers are discharged with the real-code evidence above. The two toy live runs stay recorded as live, NOT organic.
  - **8 green / 8, in a clean clone too** (measured 2026-10-28). Before this work it was 5 / 8 on the laptop and 1 / 8 in a clean clone.
    - Five faculties had cited two trails that exist only on the laptop: `.aios/audit/` is gitignored. Those are now committed as frozen, byte-identical copies in `docs/learning/trails/`, and the ledger points there.
    - Before committing, both were read for secrets: every scanner hit was a false positive (a commit hash, a test name, a model id). Each faculty's cited run was also checked to support its claim.
    - The CI job reports these verdicts but does not require green.
- **The operator's backend can now verify this repository's own tests** (`docs/operations/WORK_SCOPE.md`; the operator chose the design on 2026-10-28).
  - It does so in a separate checkout, `work/ai-editor` on branch `gagos/work`, never the live one.
  - It uses a pinned verify image (`Dockerfile.verify`) and a 120 s command budget; the default budget stays 30 s.
  - Measured through the backend's own executor: tests in `work/ai-editor` pass, and they import that checkout's code. The live checkout's tests stay RED even when approved.
  - Earlier skills and approvals no longer match, because the scope identity changed. Per-task scope binding is still unused: `work/` is a global root. *(Superseded 2026-10-29: a turn can be bound; see "State on 2026-10-29".)*
- **The gateway was not universal in daily use, and the inventory had not seen it** (`docs/ONE_GATEWAY.md`, "2026-10-28").
  - The operator's model-call ledger held 163 calls. 13 production calls passed no gateway entrance, every one from the route picker (`aios/core/router_wiring.py`). That is the small local model that prefers a route when policy allows two or more.
  - Its prompt carries no user text, so nothing private left. But it skipped the emergency stop and redaction.
  - The inventory never reached it, because its turns ran with cloud off. A new surface with the operator's routing policy reproduces it on master's code: `UNGATED x1`.
  - The picker now runs only through the local-only compatibility entrance, and without a gate there is no pick. The inventory now shows 66 of 66 calls gated across 12 surfaces, with 15 of 27 sites observed.
  - Still open (organ 32 stays yellow): 12 sites are never driven, and an ungated call is recorded, not refused.
  - 12 more ledger calls came from scripts outside the repository on 2026-10-12, not production.
- **Organ ledger: 50 green / 9 yellow / 59**, unchanged. Every organ's evidence was re-gathered and passed at `b5ddaed7` (#538). Master CI is green on every job.

## State on 2026-10-21 (measured 2026-10-19 to 10-21 on master `501c2536`, unless a line says otherwise)

**The cage held and grew. The animal now has true lessons, but they have not
yet been shown to help.**

- **Organ ledger: 50 green / 9 yellow / 59**, unchanged since 2026-10-12.
  - Yellow: 20, 32, 40, 44, 46, 48, 49, 51, 55.
- **Learning Ledger: 5 green / 8.** L3, L4 and L5 wait on one act of the operator: activating a skill. **0 skills are active**, so no learned reflex serves a live turn, and the One Law holds for no live task.
- **Lessons.** 117 lessons now pass the production recall gate for the operator (census on a copy of the live store, 2026-10-21: 117 of 140). They are the 11 from Phase 8 plus 106 from D12:
  - written by a strong teacher (Kimi K3);
  - fact-checked one by one (168 checked, 9 false);
  - re-admitted by the operator.

  See `docs/learning/D12_PRACTICE_AND_FACTCHECK_RESULT.md`.
- **Usefulness is still not shown.**
  - Phase 8: not met.
  - D12, cloud student: **neither member met**, with no harm. ON and OFF earned exactly the same, 114 of 423 each (`docs/learning/PAYOFF_D12_RESULT.md`).
  - D12, local student: not run yet. The pre-registration names it as the member most likely to show a benefit. It needs about 2–3 days of the laptop.
- **A defect the fact-check found.** The frozen secret scanner redacts ordinary identifiers that look high-entropy, so 9 lessons taught the redaction instead of the code. Fixing it is a §VIII proposal for the operator (`aios/security/` is frozen).
- **Self-repair works once, live.** Mission `maint-3b41d3d6` removed dead imports and reached VERIFIED_RESOLVED on 2026-10-19 (`docs/operations/FIRST_SELF_REPAIR.md`). One repair is not a track record.
- **Recovery is real.**
  - The operator lost both secrets and recovered with the same operator id, losing nothing (#522, `docs/operations/OPERATOR_RECOVERY.md`).
  - A rebuild from GitHub plus a backup took 7.6 minutes (#518).
  - The spine signing key was lost and rotated (#516).
- **Keys.** Promotion and checkpoint now need a real key from the keystore; the public default is gone (#523).
- **Cloud.** The Bedrock API key that served earlier runs has been refused inference since 2026-10-18 ("Operation not allowed", all models, both regions). D12 ran through the operator's IAM key in us-east-1 instead, recorded as an amendment before it ran.
- **CI.** A new advisory against certifi (PYSEC-2026-4320) failed every PR on 2026-10-21. Fixed by #527.
- **Not re-measured this period:**
  - approval authority (M7);
  - the clerk (last measured 2026-10-11: no admitted model has run a real job);
  - `prove_sovereignty.py`.

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
