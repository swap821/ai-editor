# Honest State of Sovereignty

**Last updated:** 2026-11-12 ("2026-11-12, GAGOS's daily envelope, signed by the operator" below;
earlier sections keep the commit they were measured on). The whole story, from the first commit, is
`docs/HISTORY.md`.
**Proof script:** `prove_sovereignty.py` (18 assertions, 6 phases, all pass on `6b64b9ca`)

## 2026-11-12, GAGOS's daily envelope, signed by the operator (branch `feat/daily-envelope`)

- **His decision.** On 11-11 he chose that GAGOS's missions are approved once a day, as an envelope. On 11-12 he chose how: "Envelope via organs 9+10". This is move A's first PR (the aliveness map, https://claude.ai/artifact/DemaQfKyGyyaMUTUJCux8L).
- **What stood in the way, measured.**
  - Only a privileged operator can create a council mission (`POST /api/v1/council/missions`).
  - `MissionAuthority.approve` consumes one human-bound capability per mission.
  - So GAGOS could neither originate nor be approved without him, one mission at a time.
- **The envelope** (`aios/domain/capabilities/envelope.py` terms, `aios/application/capabilities/envelope.py` authority, `aios/infrastructure/capabilities/envelope_store.py` store, beside the exact capabilities). It is a capability of its own kind; the one-action capability is not loosened:
  - **Signing.** Only an operator with a recent strong re-authentication and a recorded authentication event can sign. The terms: folders, kinds (`tests` or `code`), 1 to 20 missions, 1 to 24 hours, delivery by PR only.
  - **Admission.** A GAGOS mission takes one slot, atomically. Eight missions racing for the last slot: one wins. Its record names the envelope and the slot ("slot k of N").
  - **Never inside.**
    - Paths: `aios/security/`, `.git/`, `.github/`, `.aios/`, `data/`, any `.env` file, absolute paths, `..`, wildcards. They are refused even inside a wide folder (`aios/` does not reach `aios/SECURITY/x.py`).
    - The signer cannot originate inside his own envelope (INVARIANT III).
  - **Ended** by expiry, by his revocation, or by a newer signature. Any engagement of the emergency stop also ends it, even after the stop is cleared: the stop's generation is recorded at signing. A missing or "ungoverned" stop refuses outright.
- **His doors.** `GET`, `POST /api/gagos/envelope` and `POST /api/gagos/envelope/revoke`, all privileged-operator. They are classified in the policy kernel: signing and ending are YELLOW, like approving a repair; reading is GREEN. His operator id is never echoed.
- **Not yet.** Nothing admits into it yet. GAGOS's origination through the council (A2) and the mission run with PR-only promotion (A3) come next. Until he signs an envelope and A2 lands, the hour stops at the clerk's briefing, as today.
- **Organs.** The kernel and the action types are entrypoints of organs 7, 25, 27, 45 and 46, so their evidence is re-gathered at this branch's tip.
- **Codex's adversarial review** (gpt-6.1-sol, read-only) found four real holes. All are fixed and each is pinned by a test that reproduces it:
  - **High.** Windows aliases passed the frozen-path check: `aios/security./x.py` (Windows drops the trailing dot) and `aios/security::$INDEX_ALLOCATION/x.py`. Colons, `<>"|`, 8.3 short names (`~1`), and segments ending in a dot or a space are now refused.
  - **Medium.** A stop engaging between the stop check and reading its generation was recorded as the envelope's own generation, so the envelope survived the clearing. One snapshot now decides both.
  - **Medium.** A stop engaging while a slot was taken still returned the slot. The slot is now void, and `held_slot` refuses it.
  - **Medium.** The clock was read before the writer lock, so a slow lock admitted an envelope that had just expired. The clock is now read inside the lock.
- **Still to hold at the writing layer (A3):** canonical filesystem containment, including reparse points, when a mission's files are actually written.
- **Tests:** 64 new, red-team and race cases included.

## 2026-11-12, the clerk's first live intake; it reads goals as written (branch `fix/clerk-reads-goal-as-written`)

- **Phase 1 ran live** in the 12:50 UTC hour (master `ca928970`), on the two blueprint goals:
  - **qwen3.5:9b triaged** both as medium / frontend / no escalation, which is right for both.
  - **qwen2.5:3b briefed** both, and the writers took both goals.
  - Each job is in the clerk's provenance store and the outcome in the ledger's `goal_intake`.
- **What the briefings showed.** The clerk had read the goals through the **cloud** egress scrubbers:
  - the secret policy's entropy pass took the blueprint document's path for a secret (`<REDACTED:HIGH_ENTROPY:…>`);
  - the privacy filter removed every file path (`frontend[PATH REDACTED]`);
  - the briefings carried the debris: "recoverableTabs has at most 636f2506034a entries", and files listed as `frontend[PATH REDACTED]`.
- **3b's briefings also invented constraints** that the requests did not hold (for example "restored correctly in both passing and failing tests"). Its qualification case checks faithfulness on one request, and this is the first live evidence against it. The writer reads the briefing as advisory beside his words, which decide.
- **The fix.** The clerk is local, and the README's step 3 comes before its step 4 (privacy), so the cloud scrubbers are not its gate.
  - `goal_intake.clerk_redact`: a goal holding a credential the secret policy **names** (a key, a token, a private key) is read scrubbed, so no credential reaches the clerk or its provenance store.
  - Any other goal is read as written; the entropy guess and the path filter are not applied.
  - What a cloud writer reads of the briefing is still scrubbed (`egress_redact` in `task_jobs`).
- **UX-05's delivery, twice.** In both hours the change passed the sandbox (350 tests) and Opus accepted it, then delivery failed: "the tests related to the frontend targets did not pass". The check runs with and without the change, so the failure was the change's doing in the hour. Yet every reproduction passes with the delivery's own `frontend_smoke`: on master, on the hour's exact delivery tree (`#638`'s head), and in GAGOS's own worktree unchanged. The output that would say why was thrown away (a local `steps` list). Delivery now keeps the failing step's own last lines with the reason, in the local log and ledger only: a named credential is scrubbed; the failing test's path is kept.
- **Tests:** 2 new, on the live goal's own text: the cloud scrubbers alter it, and the clerk reads it unchanged. A credential still never reaches the clerk, and the hour's test now also requires the file paths to arrive. With the old redaction the hour's test fails.

## 2026-11-12, never two backends; the clerk is qualified and granted (branch `fix/watchdog-no-second-backend`)

- **The memory the laptop lost, measured.**
  - Five `python -m aios` backends were running, each about 1.85 GB committed, and only one served :8000.
  - The cause: every 15 minutes the watchdog (`gagos_backend_job.py` → `daily_backend.py up`) asked `/health` with a 3-second timeout. On a full laptop a paged-out backend answers more slowly than that, so `up` started another beside it and never stopped the old one; Windows let the new one bind the busy port.
  - With the operator's OK, the four extra backends were stopped: committed memory went from 32.1 to 24.7 GB.
- **The fix (`up`).**
  - A backend this tool started (pid plus creation time, now recorded) that still runs is waited for, up to 120 s.
  - If it stays silent, it is stopped, its whole tree and the executor's, before anything new starts.
  - A record that cannot prove the pid is ours (no creation time, or the pid now another program's after a reboot) is never killed.
  - Tests: 4 new. Two fail when the guard is disabled.
- **The laptop's memory, for the record.**
  - It had not truly restarted since 11-11 00:44: Fast Startup is on, so "Shut down" does not reboot. The operator then did a real restart.
  - At his choice, `C:\Users\kumar\.wslconfig` now caps Docker's Linux VM at 4 GB; it had been 3.6 GB and growing.
  - Dell SupportAssist and TechHub plus NVIDIA Share restart themselves when stopped. Disabling them is his call.
  - About 1 GB of non-paged kernel pool is this machine's baseline, measured right after boot.
- **The clerk, qualified on master's code** (`ccc6ae19`, 25 tests, triage and briefing included):
  - **qwen3.5:9b** passed all 25.
  - **qwen2.5:3b** passed every safety gate and failed only `triage_escalates` (it did not escalate the expired-token security case). Per-job admission (#628) admits it for the 10 jobs its tests back, `prepare_briefing` included and triage not.
  - 9b was loaded first with a two-token generate. A load Ollama refuses changes nothing, whereas a failed health check inside `qualify` would have rejected 9b and its live job.
- **The operator granted, by his rule (the lightest qualified model per job):** qwen3.5:9b triage (plus its summarise_disagreement); qwen2.5:3b prepare_briefing. The two blueprint goals are queued again (`gt-fa6fc5025e` UX-05, `gt-e2de45c6f5` PERF-04): the clerk's first live intake.
- **Codex's gpt-6-luna is back.** It answered through the workshop's own call path; its limit had lifted. GAGOS's next batch probes it and it rejoins.
- **Findings on the two goals.**
  - **UX-05:** passed the sandbox and review, then failed delivery. The same `vitest related` run passes now, 350 tests; it had run at 0.5 GB free.
  - **PERF-04:** the work-surface store refuses to close results past `RECOVERABLE_RESULT_LIMIT` by design (`recoveryIssue` 'capacity'), so the old test's expectation was wrong. Closed workspace panels (one per distinct `file:<path>`) are kept forever; whether they should be is a product decision.

## 2026-11-12, a writer that makes no edit is heard (branch `fix/task-no-edit-refusal`)

- **What happened.** The blueprint goal PERF-04 (a 100-cycle bound test for the work-surface store) was refused twice, in the 08:50 and 09:50 UTC hours, as "expected exactly one fenced code block, got 0". In the same hours Sonnet delivered other changes, so the writer was not failing.
- **The cause.** The task writer is told: "If the task cannot be done in this file alone, reply with no edit at all." My goal showed it `tabStore.test.ts` but not `tabStore.ts`, whose API the test needs, so it made no edit. The workshop read that as a broken whole file, and the writer's words were not kept anywhere.
- **The fix.**
  - An answer with no edit and no fenced file is refused as "the writer made no edit: '<its words>'", scrubbed and at most 240 characters, for tasks over one file and over several.
  - The goal is added again (`gt-7d07ed1f18`) with the store shown so the writer can read its API, and told not to change it.
- **Tests:** 5 in `tests/test_gagos_task_no_edit.py`. The single-file case fails when the check is removed. One older test now pins its prose case to the new message; its unchanged-file case keeps "every file unchanged". GAGOS's workshop tests and the guards pass.

## 2026-11-12, a waiting goal can be asked again (branch `fix/goal-intake-attempt-ids`)

- **What happened.** In the 07:50 UTC hour, GAGOS asked the clerk again about the goal still waiting from 06:50 (`gt-c295ef7b4f`). The ask failed: "the clerk could not be asked: IntegrityError: UNIQUE constraint failed: local_job_requests.job_id".
- **The cause, my own (#627).** Each clerk job's id was fixed per goal (`goal-<id>-triage`). The clerk's provenance store keys every job by its id, so a goal could be asked only once. Every goal waiting for the clerk would have failed like this each hour.
- **The fix.** Each intake is its own attempt, stamped in UTC: `goal-<id>-<stamp>-triage`. Each step's job id is in the outcome, so the ledger points at the clerk's own record.
- **Evidence.** A new test asks a waiting goal twice through the real service and provenance store: both attempts are on record. With the old fixed id it fails with the hour's exact error. The goal-intake tests pass, 26.

## 2026-11-12, masking holds wherever the file lands in the prompt (branch `fix/mask-in-prompt-context`)

- **What happened.** In the 06:50 UTC hour, the first with real goals, the clerk took in both blueprint goals. Both waited, because no model is granted triage yet. The writers then refused `gt-838f049241` (UX-05) unsent: "the secret policy would scrub this file, so it is not sent".
- **The cause, measured.**
  - The frozen secret scanner's sliding window starts at every fifth character of the whole payload, so whether a span is scrubbed depends on where it lands.
  - The ordinary line `if (turnTokenRef.current !== token || !ownsWorkSurface(writingTab.id, token)) return;` is scrubbed at offsets 2 and 7, and at no other offset from 0 to 9.
  - GAGOS masked each file alone, at offset 0, then checked the assembled prompt, where the line sat at 2 mod 5.
- **The fix, in the workshop; the frozen scanner is untouched.**
  - `mask_redact` asks the scrubbers at all five alignments and takes each line as the first alignment that changes it.
  - Every `mask_lines` call uses it (7), for writers and reviewers alike.
  - The egress gate (`would_be_altered`) is unchanged and still refuses anything the scrubbers would alter.
- **Evidence.** The exact prompt the hour refused, rebuilt with his direction notes:
  - the old masking gives the same refusal;
  - the new masking passes the gate unchanged.

  14 tests (`tests/test_gagos_mask_alignment.py`) cover the scanner's offset dependence, the old oracle missing it, the masked file surviving at offsets 0 to 9, and exact restoration. All GAGOS workshop tests plus the consistency and source guards pass: 484.
- **After merge:** the UX-05 goal is added again (a refused task stays refused).

## 2026-11-12, the clerk is admitted per job (branch `feat/clerk-per-job-admission`)

- **What happened.** The operator approved qwen2.5:3b, and its qualification rejected it ("Failed qualification suite"). Two findings:
  - The run came from his main checkout, still at `bd8a75c9`, before #627, so triage and briefing were not tested at all (22 tests).
  - The suite is all-or-nothing. 3b passed 21 of 22, including every safety test, and failed only `skill_selection_applies` (it said a skill did not apply when it did: the cautious direction, which escalates). That one miss rejected it for every job.
- **The operator's decision:** re-qualify on master's code, and per-job admission for his review.
- **The rule now** (`qualification_evidence.gates_passed`, `jobs_backed`, `admits_job`):
  - Gates, meaning every test that backs no job (injection, secrets, tool refusal, limits, timeouts, reliability, ...), stay all-or-nothing. A test added later without a job is a gate by default.
  - A model that passes every gate is admitted only for the jobs whose own tests all passed. Admission grants nothing: the operator grants jobs, and only backed ones.
  - The dispatcher judges the job at hand (`job_profile`). A model is escalated for a job it failed, and for every job when a gate failed.
- **A hole closed on the way.** The grant check read only a job's own tests, so a model that failed a safety gate could still be granted triage. The runtime never used such a grant (it needs admission), but the check now requires the gates too.
- **Test fakes made honest.** MagicMock registries handed the dispatcher a MagicMock whose `.passed` was merely truthy. They now hand it a real result built from `qualifier.suite_test_ids()` (`tests/clerk_qualification_fixture.py`), guarded by a real run recording exactly those ids.
- **Tests:** 19 in `tests/test_local_clerk_per_job_admission.py`, through the real API, service and SQLite registry: a model that fails only skill selection is admitted for the rest and can be granted triage but never skill selection; a model that leaks the secret fixture is rejected and can be granted nothing. Two shown to fail when their rule was removed.
- **Not yet done:** re-qualifying 3b and 9b on master's code. Free memory was 0.5 GB, and the clean-up of three stale backend processes (about 1.85 GB committed each) waits for the operator.

## 2026-11-12, GAGOS's goals go through the clerk (branch `feat/clerk-qualification-briefing`, PR #627)

- **What runs now.** Each hour, before the writers, up to three of the operator's open goals go to the local clerk's own governed service (`LocalWorkforceService.run_advisory_job`): triage, then a briefing. Each job is in the clerk's provenance store, recorded by that service. The outcome is in the workshop ledger's new `goal_intake` table, and the report says where the clerk is with each goal.
- **One builder, two callers.** The prompts, the declared output and the reading of the answer live in `aios/domain/local_workforce/goal_jobs.py`, as `skill_selection.py` does for the reuse job. Organ 37's triage and briefing cases are built from it, so a model granted a job was measured on exactly that job.
- **The clerk blocks nothing.** It is advisory. A briefed goal's writer reads the clerk's constraints and "done when" beside the operator's words, labelled as the clerk's, with his task deciding. A goal the clerk cannot brief is worked on as before.
- **What the clerk produces for the next phases.** A briefed goal also becomes the Queen Council's own `CouncilMissionRequest`: his files only, never the clerk's; goal, constraints and "done when" from the briefing; `created_by` `gagos_clerk`. It is stored for phase 2 (the council plans it). **Nothing reads it yet.**
- **Measured, not yet live.** No model is granted TRIAGE or PREPARE_BRIEFING. Until the operator approves qwen2.5:3b, the qualification runs and he grants the jobs, every goal waits with "No admitted healthy local model for profile", and that refusal is on the clerk's record.
- **Not asked, and why.** `check_context_completeness`'s qualification case hands the model its answer ("Return exactly complete=false and missing=[...]"), so a grant would not show judgment. It needs the treatment skill selection and triage got (paired cases from one builder) before GAGOS asks it. That is open.
- **Tests:** 25 new in `tests/test_goal_intake.py`, including the real clerk service with its provenance store in both directions (granted → briefed and recorded; nothing granted → waiting, refusal recorded), his words scrubbed before the clerk reads them, and the writer prompt with and without a briefing. Two were shown to fail when their behaviour was broken (a writer without the briefing; the council's scope taken from the clerk).

## 2026-11-11, the clerk can be qualified to triage and to brief (master `a79a4030`+, branch `feat/clerk-qualification-briefing`)

- **Why.** The operator was disappointed that GAGOS's work runs beside its organs rather than through them. The honest map (doc "GAGOS as one system: the honest map and the plan") found that only the workshop runs: steps 2, 3, 6, 13 and 14 of the README's mission flow never ran for real work. The plan starts at phase 1, goals through the clerk.
- **What the registry showed.** The clerk is qualified for one job only, `summarise_disagreement` on qwen3.5:9b. Organ 37's suite had **no test** for TRIAGE, PREPARE_BRIEFING, FORMAT_REPORT or PARAMETERISE_SKILL, so no model could ever be granted the README's step 3 ("the local clerk classifies the task and prepares a briefing").
- **What changes, in the owning organ:**
  - `triage_escalates` and `triage_routine` come as a pair, like skill selection, so a constant answer fails one. Both must pass for TRIAGE.
  - `briefing` checks exact fields; the files exactly as the request names them, in order, none invented; the "not the backend" constraint kept; `done_when` naming the deciding test; and a key given beside the request never repeated (`forbidden_values`). It backs PREPARE_BRIEFING.
  - `TEST_ID_TO_JOB_PROFILE` maps all three. FORMAT_REPORT and PARAMETERISE_SKILL still have no test.
- **The operator's decisions the same day:** a daily approval envelope; for GAGOS's code going to his plan brains, only keys and paths hidden; qualify both qwen2.5:3b and qwen3.5:9b; D15 runs to its stopping rule, then folds into the skill system. Approving qwen2.5:3b and granting roles are his acts. Qualifying waits for his go, because of memory.
- **Tests:** 9 new, and both fake clients answer the new cases. The clerk's test files: 106 passed. Organs 33, 35, 36, 37 and 53 re-gathered at the branch tip.

## 2026-11-11, GAGOS's PR body outgrew GitHub's limit (master `23b1c4bd`, branch `fix/gagos-pr-body-limit`)

- **What happened.** From 08:53 UTC every hour's delivery waited. GitHub refused the PR for `gagos/daily-2026-11-11-3` with `422: body is too long (maximum is 65536 characters)`. The PR body was the day's whole report, every proposal refused and rejected ones included, and the day's volume (#616's larger batches) passed the limit. Ten accepted changes were waiting, among them GAGOS's first work in the superbrain.
- **The fix.** `pr_body` uses the whole report while it fits under `PR_BODY_LIMIT` (60,000). Otherwise it lists this PR's own proposals in full and counts the day's others by status, pointing to the full report `reports/<day>.md` in GAGOS's data on the laptop. If even that is too long, it is cut at the limit, saying so, and keeps the footer. The misses stay counted; they are just not all listed in the PR.
- **Tests:** 4 new. The workshop set passes; Bandit is clean.

## 2026-11-11, a task's writer answers with edits (master `a79a4030`, branch `feat/gagos-task-edits`)

- **Why.** The operator wants GAGOS itself to complete the living-being blueprint. 15 frontend files are over the 40,000-character whole-file bound, and they are the body's core: `MaterializedTab` 114,541, the LEGACY scene, the HUD, `livingMirror.css`, `GagosChrome`. A writer returning whole files could not touch them.
- **What changes:**
  - A task's writer now answers with exact SEARCH/REPLACE edits, applied in order to the text it was shown.
  - Each SEARCH must match exactly one place.
  - The original's line endings are kept.
  - An answer without edits is still read as a whole file, as before.
  - A task file may be up to 160,000 characters, and a task's files 240,000 together: what one prompt carries, since only edits come back.
- **What doesn't change.** Lint findings and first tests keep whole-file answers, so D15's pre-registered conditions are untouched.
- **One line, found by the crew's live test.** On this laptop `claude` is `claude.CMD`, and `cmd.exe` cuts a `--system-prompt` argument at its first line break. The first edit format had six line breaks, so Claude writers would have received it cut off after its first line. It is now one line, and a guard test keeps every writer's instruction on one line. The existing instructions all were.
- **Tests:** 16 new; 3 bound tests rewritten to the new contract. The workshop set: 400 passed, 8 skipped. Bandit is clean.

## 2026-11-11, GAGOS works on the superbrain through the port (master `4862ca54`, branch `feat/gagos-through-the-port`)

- **Found while planning the body's 10/10.** `frontend/src/superbrain` is lab-first: authored in the git-ignored lab `GAG demo/gag-orchestrator/src`, which exists only in the operator's main checkout, and ported with digests in `frontend/superbrain-source.json`. It holds 139 production files and 29,415 lines (61% of the frontend), including 6 of the 9 files over 800 lines and the dead `SuperbrainHUD`. GAGOS works from a clean checkout and left every ported file alone, so most of the body's debt was out of its reach.
- **The operator's word:** "GAGOS through the port (Recommended)".
- **What changes:**
  - `editable_frontend_files` now includes the ported files;
  - a delivery that changes one also writes `superbrain-source.json` in the same commit, with the digest a port would record (CRLF read as LF);
  - an entry is updated, a new file of a kind the port carries joins, a removed one leaves;
  - order and line endings are kept, so a change is a one-line manifest diff.
- **A new guard,** `tests/test_port_manifest.py`, checks that every recorded file exists with exactly its recorded digest. It failed on master before #620: #533 and #534 both changed `SuperbrainScene.LEGACY.tsx`, and the merged file matched neither recorded digest. CI never ran the port check. #620's manifest, computed from the merged files, mended it, and on master `4862ca54` the guard passes. Register row `port-manifest`: 47 of 47.
- **For the labs:** AGENTS.md and `frontend/README.md` say so. A lab older than master is stale, so before the next lab-first change it is moved aside and restored with `npm run port:restore`. Palette and textures stay sacred, and look-and-feel work on the being stays the operator's and Codex's in the lab.
- **Tests:** 7 new, plus 1 delivery test. The workshop and sandbox set: 397 passed, 8 skipped. The 307 tests that read AGENTS.md or the README pass. Bandit is clean, and no organ's entrypoints are touched.

## 2026-11-11, Codex's last three weeks of body work land (master `5201dbc8`, branch `feat/land-codex-body-work`)

- **Found while planning the body's 10/10.** Codex's goal for the body (09-24 to 11-08, about 235 hours, paused at its usage limit, not complete) is in its own goal store. Its measure is the frozen 29-criterion acceptance ledger in `docs/frontend/` (3 of 100 accepted; 52.5 of 100 implemented by Codex's 10-09 audit). Its work from 10-22 to 11-07 was never committed: 78 source files, 20 new modules, some of them approved by the operator.
- **A mistake of mine.** My worktree cleanup on 11-10 archived that tree and then removed it. It was restored byte for byte today, and the work is also on the local branch `archive/codex-living-being-run-20261107`.
- **The operator's word:** "Claude lands it now".
- **How it was ported.** A cherry-pick of only what changed after Codex's last commit `3204cbdc`; most of that commit had reached master through #496 and #531 to #534. The first attempt merged from the 10-13 branch point instead: 40 conflicts, a stray constant, and a 150-line block doubled without a conflict marker. It was discarded.
- **What the port needed.** 13 conflicts, five of them source, each read against its base. Records keep both sides' entries. The port manifest's hashes come from the merged files.
- **What was checked.** An audit of all 70 changed files: no doubled lines; no addition from either side lost, except old signatures replaced on purpose; no deletion undone.
- **Two fixes beyond the port.** The thumbnail targets wrote `0` where browsers read back `0px`, so their "unchanged" check never matched and the transform was rewritten every frame. And the IME test now waits 5 s for the lazy terminal.
- **Results:**
  - `tsc` is clean and the build passes;
  - ESLint shows 0 errors and 106 of 124 warnings on master after #617 (the 5 it adds are in Codex's new code);
  - Vitest: **2,087 tests in 269 files pass** (master about 1,931).
  - No organ's entrypoints or tests changed.
- **Not acceptance.** Physical phones, assistive technology, the live backend journey and the ledger itself remain open. Codex's `RESUME.md` carries a dated note telling it this landed.

## 2026-11-11, the body's 10/10 begins: GAGOS gets a type check (master `fda1929c`, branch `feat/gagos-type-check`)

- **The operator's word.** Asked whether the frontend (the body) is 10/10: measured, about 6.5. He: "that honest real hard and long work for GAGOS itself to make GAGOS frontend (body) infra honest 10/10 and complete". GAGOS does the work; Claude Code builds what it needs and reviews; he merges.
- **Measured on master:** `strict` unset and `noImplicitAny: false` (with both on: 2 errors in production code, 114 in tests); 52 production files plain JS/JSX that TypeScript never checks; `SuperbrainHUD.tsx` (2,028 lines) imported by three modules for one type; `SuperbrainScene.LEGACY.tsx` (2,180 lines) imported by 11; `MaterializedTab.tsx` 2,571 lines; 106 ESLint warnings.
- **What GAGOS could not do:** files over 40,000 characters (whole-file answers), create, rename or delete files, or know whether a change keeps TypeScript happy. Four steps give it those; this is the first.
- **The type check.** The frontend sandbox runs `tsc --noEmit` with the change in place, and again without it when it finds errors. A change that adds TypeScript errors the base does not have is BROKE before review, whatever its tests did. A clean check changes no verdict (it never makes an untested change tested); a check that cannot run is said in the verdict and left to CI. The runner script is baked into the image, so the image is now named by the lock file and the runner together (with no runner, the name is the lock's alone, as before); the image is rebuilt once this merges.
- **Tests:** seven new; two updated to the new call order. Every test file that uses the sandbox or the workshop: 378 passed, 8 skipped (the skips need the real images). Bandit and the register unchanged.

## 2026-11-11, D15's first batch, and a timer that outlived its component (master `b0792e7a`, branch `fix/cognition-toast-timers`)

- **D15's first live batch (03:50 UTC)** ran as designed: every proposal got its arm (ON writers were shown the rule's 3 entries, OFF writers none), 4 Claude proposals passed their checks, tests and review, the credit was settled and `no-unused-vars` was reflected on again (6 entries). Population: 2 ON, 2 OFF. Three Codex calls hit the operator's OpenAI usage limit; the Bedrock key is still refused.
- **GAGOS's PR #617** carries the four accepted changes. Its `frontend-tests` failed with every test file passing: one unhandled `ReferenceError: window is not defined`, from a verify-toast timer in `useCognitionBus.js` firing after the test environment was gone. The timers' cleanup was returned from inside the bus callback, which the bus never calls, so they outlived an unmount. Now the timers belong to the effect and are cleared with it.
- **Test:** `useCognitionBus.test.js`, new: the toast shows, leaves and goes; no timer is left after an unmount, with or without reduced motion (without the fix the two unmount cases fail). With the hook's other caller's tests: 29 passed. ESLint clean.

## 2026-11-11, D15's seed, and three fixes found the hour it began (master `20dd6250`, branch `fix/d16-reflector-parse`)

- #615 (D15) merged at 03:14 UTC; the operator then asked whether the learning and memory infrastructure was "10/10 for a perfect D15 result". Said honestly: no. The design holds, but supply and throughput make a clear answer unlikely within 30 days, and a dry run found a flaw in the first batch.
- **The flaw.** The first batch would have spent about eight scarce retries before any playbook existed. At the operator's word the reflector seeded all nine rules ahead of its pace (deviation D16, `docs/learning/PAYOFF_PREREGISTRATION.md`).
- **Found while seeding.** Seven of nine answers were malformed JSON, and the code marked those rules reflected; a reflection repeated within an hour reused its request id. Re-run with a parser that reads each entry of a malformed answer: 22 entries kept across 9 rules, all before D15's first batch. 17 Sonnet calls in all, not the 9 first said.
- **Fixed here:** the tolerant parser; nothing readable means tried next batch; a unique request id per reflection; a finding waits while its rule has verdicts but no reflection yet.
- **Throughput, at the operator's word** ("use as many sonnet and haiku models simultaneously"): a batch takes up to 20 findings, the Claude writers up to 16 (were 10 and 4), up to 4 writers at once (was 2), fewer when free memory is short (each writer is a process of about 0.4 to 0.6 GB; the laptop had about 3 GB free), and reviews up to 20 a run. The bound is the laptop's memory, not his plan.
- **Tests:** five new, one updated; every test file that uses the workshop, its ledger or its Foundry: 349 passed, 6 skipped.

## 2026-11-11, D15: a playbook per rule, so the learning can show whether it helps (master `e3f1a830`, branch `feat/d15-workshop-playbook`)

- **The operator's word.** An outside review (Fable 5.2, 2026-11-10) proposed taking memory recall and the reflex off the default turn, since Phase 8, D12 and D13 showed no lift. He answered: "I don't want to lose direction to my north-star vision" and "I want to make them work think hard research on Internet may be there be some hope", then "Yes" to this design.
- **What the research said.** The studies that measure a lift from agent memory share what the D-runs lacked: general strategies and pitfalls rather than facts about one module, recurring kinds of task, entries pruned by later outcomes, strong models, winners contrasted with losers, and small curated updates (ReasoningBank, ACE, Agent Workflow Memory, Training-Free GRPO, Dynamic Cheatsheet, subtask-level SWE memory, the experience-following study). GAGOS's hourly workshop already has recurring kinds of task, strong writers and real verdicts.
- **Pre-registered first.** D15 is in `docs/learning/PAYOFF_PREREGISTRATION.md`, committed before its code (`50883137`, with the pacing clarified in `423838e2`, still before any code or data): treatment, randomisation by finding, supply, outcome, population, H1 and H1c with Holm, harm, power (about 135 decided per arm for 50% to 65%, so a null will most likely mean too few) and the stopping rule (240 decided, or 30 days).
- **Built.**
  - A `playbook` per rule in GAGOS's ledger: at most 8 active entries, one sentence each, strategy or pitfall, no path; a curator in code that keeps entries whole, drops repeats and pathlike text, and retires the lowest-scoring past 8.
  - A reflector after each batch's reviews: Claude Sonnet on the operator's plan, through the one gateway, reads the reasons behind a rule's recent accepted and not-accepted proposals (never code, scrubbed) and proposes at most 3 entries; at most 3 rules a batch; a failed call changes nothing.
  - Credit: an ON proposal's outcome is credited to the entries its writer saw; an entry harmful at least 3 times and twice its helpful plus one is retired.
  - Each finding's arm from SHA-256 of its path, rule and base; the ON writer sees the rule's playbook, the OFF writer does not; both keep the last three refusal reasons. Recorded: arm, entries shown, entries active.
  - Supply: a finding never accepted may be tried again, at most 3 answered attempts, a day apart.
  - `outcome_of`: one rule for an outcome, now shared by the writers' records and D15.
  - `gagos_daily.py d15` shows the counts per arm; `--final` runs the one analysis. The report shows counts only.
- **Tests:** ten for D15 in `tests/test_gagos_daily.py`; deliberately breaking the playbook injection or the attempt cap fails them (breaking the OFF guard in the credit changes nothing: an OFF proposal never records entries shown). All workshop, ledger and Foundry test files with the architecture, Bandit, register and currency tests: 412 passed, 6 skipped.
- **Not yet.** No data: the run begins with the first hourly batch after this merges. The local model and the counter's turns are not in D15.

## 2026-11-11, an outside review of the whole codebase, and what it found that is true (master `e3f1a830`, branch `fix/review-verified-defects`)

The operator shared a review of master `307f8ab` by Fable 5.2 ("GAGOS (ai-editor) — Whole-Codebase Review", 2026-11-10). Its grades: security spine A-, verification discipline A, CI B+, frontend B, backend architecture C, product value D, repo hygiene D. Its verdict: a security spine worth respecting around an agent that does little, in a codebase (about 420,000 lines) too large for one operator to hold. Every concrete defect it named was checked against the code before anything was changed.

- **True, and fixed here:**
  - `aios/core/replay_writes.py` carried a twin of `stop_permits_autonomy` with the same body; it is now an alias of the one predicate, with a guard and a register row.
  - CI installed mypy 2.3.1 over the lock's 2.4.1. CI now pins 2.4.1 (the spine's type gate passes on it: 0 errors), and a new guard fails when any tool a workflow pins disagrees with `requirements.txt` (it fails on the old line).
  - README's proven row said the private Executor Service "never receives the Docker socket"; compose gives it exactly that, by design, and the cited test asserts the control plane lacks it. The row now says so.
  - `SECURITY.md` named the branch `main` (it is `master`), called approval tokens HMAC-signed (they are random single-use tokens stored as SHA-256 digests), and cited two lines of a 824-line `main.py`; it now names the three call sites of the injection check.
  - The face's CSP let it connect to any `https://` or `wss://` host; nothing in it connects outside, so `connect-src` is the API origin and the local backend.
  - `pytest.ini` declared a `fast` marker as "the default CI subset"; no test carried it and no job selected it. It is removed.
  - Six stale files at the root (`a.txt`, `backend_log.txt`, three test-output dumps, `sse.patch`) and three stray frontend patch scripts are deleted; nothing referenced them.
- **True, and not mine to fix (frozen core, `aios/security/*`, the operator's section VIII process):**
  - Audit key rotation under a pinned key: `rotate_audit_key` keeps the new private key only in memory and stores its public half, while `verify_chain` with a pinned key trusts pinned keys only, so every entry signed after a rotation would read as invalid and a restart loses the key.
  - `MAX_RED_ACTIONS_PER_SESSION` is inert: past the ceiling the gateway returns `REQUIRE_HUMAN` with a different message, the same decision as below it.
  - The shell policy (substring regexes, `git status` and `npm test` RED, `xyz touch a` YELLOW) needs the table the review proposes, an amendment.
- **True, and the operator's decision:** shrink before adding; take memory recall and the reflex off the default turn until a pre-registered run shows a lift (Phase 8, D12 and D13 did not); split `stream_generate` (1,673 lines); turn ruff and mypy on repo-wide with a shrink-only budget; consolidate the 26 databases; delete the dead frontend modules and the one-off scripts; one outside install.
- **Said plainly about this session's own work:** the review's last line is "do not add an organ, a queen, a ledger or a proof script". #611, merged the same day, added a scoreboard table, a claims table, a spend record and a pre-screen: measured, tested and asked for, and also more of what the review counts as the project's real risk. This PR adds no machinery: one alias, one guard, corrections and deletions.
- **Tests:** the affected files, 904 passed; architecture, register, Bandit and currency, 94 passed after the CI pin was restored with Bandit's (the Bandit gate requires a pin in the workflow); register 46 of 46; thesis audit ok. No organ entrypoint changed.

## 2026-11-10, #611 merged; its organ evidence on master (master `307f8abf`, branch `evidence/after-611`)

- The operator merged #611 as squash `307f8abf`, which orphaned the branch tip its evidence was gathered at (`44cfc20c`). `phase4_live_evidence.py --tip 307f8abf` passed every claimed organ, Docker available; attached, the organ doc and the release manifest rebuilt. The organ ledger, currency and manifest tests: 323 passed, 1 skipped. The expected cost of a squash merge, as #606 after #604.
- The daily backend still runs `bd8a75c9`, the main checkout's code; #609, #610 and #611 reach it when the operator's checkout is updated and the backend restarted. GAGOS's hourly job runs master's code by itself.

## 2026-11-10, cloud spend measured and bounded; the swarm's burst follows the profile; one review vocabulary and the council's pre-screen (master `fe27925c`, branch `feat/gagos-scoreboard`)

The rest of the operator's "plz honestly do all 1-5", from Codex's design conditions of 2026-11-02 and the consistency plan.

- **Actual usage.** Until now the gateway discarded the tokens providers report, and GAGOS's spend was a character-count estimate. Each metered adapter now records the tokens its provider reports, for a call and for a stream, in `<data>/cloud_spend/<UTC month>.jsonl` (`aios/core/cloud_spend.py`; no prompt, no output):
  - Bedrock (a Converse response's `usage`, a stream's closing `metadata`);
  - Gemini (its `usage_metadata`, thinking counted as output);
  - Anthropic (`usage`, and a stream's `message_start` and `message_delta`);
  - OpenAI-compatible and Vertex (`usage`; a stream that reports none is recorded from its characters, marked `estimated`).
  - The dollars are still not the bill: one deliberately high price for every metered model ($1 in, $4 out per million tokens), the workshop's since 2026-11-02, now one source.
- **One ceiling over every metered call.** `model_calls.observe`, which every adapter calls before a request leaves, refuses a metered call once this UTC month's recorded spend reaches `AIOS_CLOUD_MONTHLY_USD` (default 100, the operator's word of 2026-11-02), whatever its entrance. The refusal is recorded (`refused_for: spend ceiling`) and is an `LLMError`, so a turn's failover moves on, the local brain last. The local brain and his plans are never metered. The ceiling is checked before each call against calls already recorded, so the calls in flight when it is reached can pass it, by cents at GAGOS's sizes: a bound, not a hard cap (AWS Budgets is delayed too).
- **The workshop** settles each writer's spend from the reported tokens and reads the one price and the one ceiling; its report says so.
- **The swarm's burst.** `AIOS_SWARM_CLOUD_BURST` is retired and ignored (config warns once if it is set). A burst leg needs the active runtime profile's `swarm_cloud_burst` AND the egress law for its task. The profile field existed and was never read; only `autonomous` allows it, so the operator's `operator` profile, which sends reasoning and coding to the cloud, still sends no swarm leg there. Retiring the switch without the profile would have widened that profile; it was not done. Not yet measured live: a swarm turn on his backend is still his to run.
- **One review vocabulary.** `aios/domain/reviews.py` holds the schema a deciding reviewer answers in, the one parser, and the one mapping of a council queen's verdict onto accept, defer or reject (an unknown word is defer, never consent). The workshop reads them.
- **The council's pre-screen.** After each proposal's sandbox run, the council's Critique queen (deterministic, no model, nothing leaves the machine) says whether the pass was earned: did a test runner assert behaviour, and did what ran exercise the change. Its word is on the proposal, in the reviewer's evidence and in the report; it decides nothing (Codex: "advisory and cannot replace dual review or grant authority").
- **Register:** `cloud-spend` and `review-vocabulary` rows; 44 of 44 guarded. AGENTS.md §XI, README, `DATA_OWNERSHIP.md`, `AUTHORITY_MAP.md`, the env template and the thesis audit say what changed.
- **Tests:** `tests/test_cloud_spend.py` (8), `tests/test_review_vocabulary.py` (3), two more in `tests/test_gagos_sandbox.py`, one in `tests/test_gagos_daily.py`, and six that pinned the old switch now pin the profile. Every test file touching the providers, the ledger or failover: 2032 passed, 1 skipped; the swarm, profiles, doctor, audit and workshop files: 2092 passed, 11 skipped; architecture and register: 214 passed with the organ currency test failing until the re-gather below.
- **Organs.** The changes reach organ 32's (`model_calls.py`, `generate_pipeline.py`), 50's (the four adapters), 53's and 54's (`doctor.py`) entrypoints; their evidence is re-gathered at this branch's tip, and again on master after the merge.

## 2026-11-10, GAGOS's writers through the Foundry, and its files claimed (master `fe27925c`, branch `feat/gagos-scoreboard`)

- **Why.** Two items from the same audit, at the operator's word ("plz honestly do all 1-5"):
  - the consistency plan's "one engine for work" left the workshop's writers on a thread pool of their own, by Claude's judgement (they are tool-less calls), recorded on 2026-11-09 as not done;
  - Codex's design conditions of 2026-11-02 asked for durable, atomic claims on the files a batch writes.
- **The writers.** Each writer of a batch is now a worker the Worker Foundry admits (`aios/application/workers/workshop_foundry.py`, as the swarm's legs are):
  - the operator's emergency stop is checked at admission; an engaged stop admits no writer, and the findings stay for a later hour;
  - the scheduler runs `WRITERS_AT_ONCE` (2) at a time;
  - each writer's lifecycle (requested, admitted, started, completed or failed, dissolved) is appended to the cortex bus's outbox, which the backend reads, named by the writer and its files;
  - one writer's failure never stops the others; a writer past 30 minutes fails and frees its slot.
  - What a writer does is unchanged: one governed call through the one gateway, which already obeyed the stop, then the unattended checks.
- **The claims.** Before any writer is asked, each job's files are claimed in GAGOS's ledger (a `claims` table), all of a job's or none, in one immediate transaction. A file another batch holds is left alone; claims are released when the batch ends, and lapse after three hours (a batch that died). Before, only the hourly run claimed its hour; a run started by hand could write the same file as the hourly one.
- **Not built, because it was built already.** The going-over of the session on 2026-11-10 listed "a confined test runner" as not built. That was wrong: GAGOS's sandbox step (#582, and the frontend's in D14) runs each proposal's tests before review in the executor's container with no network, read-only, all capabilities dropped, memory, CPU and time bounded and no host environment, and `tests/test_gagos_sandbox.py` with `tests/test_gagos_sandbox_containment.py` pin that and that it catches a broken test.
- **Register.** `worker-engines` now names the workshop's Foundry route and two more guards; 42 of 42 still guarded. `SUBSYSTEM_REGISTRY.md` and `AUTHORITY_MAP.md` describe it.
- **Tests:** `tests/test_workshop_foundry.py` (5) and six more in `tests/test_gagos_daily.py`. Every test file that uses the workshop, its ledger or a Foundry: 723 passed, 7 skipped. The architecture, register, gateway, Bandit and currency tests: 122 passed.

## 2026-11-10, GAGOS's completion scoreboard (master `fe27925c`, branch `feat/gagos-scoreboard`)

- **Why.** The operator said yes to it on 2026-11-03, and it was never built: his cross-system consistency request came next and the scoreboard was left. Going back over the whole session on 2026-11-10 found it, with the other items not done; he asked for all of them.
- **What it measures.** Each hourly batch, on master and before any model is asked (an hour the cloud is refused is measured too):
  - the warnings the checks find, split into the rules GAGOS works on and those whose fix can change behaviour or span files;
  - frontend modules with no test beside them;
  - test files with a skip in them (a skip may be conditional, such as Docker or a model being absent);
  - organs green out of the organ ledger.
  - Whether the Python checks ran is recorded too, so a count without them is known as one. An organ count that cannot be read is left out, never guessed.
- **Where.** A `measures` table in GAGOS's ledger, one row an hour. `python tools/gagos_daily.py score` prints the latest against the first hour and the hour before. The daily report has a "Completion" section.
- **What it is not.** It describes; it is not a test and has no target. The first row is the first hour after this merges, not GAGOS's beginning.
- **Tests:** four in `tests/test_gagos_daily.py`. The workshop's test files pass: 316 passed, 6 skipped.
- **On the laptop the same day (not in git):**
  - 113 old git worktrees, mine from finished work and Codex's from September and October, were removed, with the operator's word. Before that, each one's uncommitted changes were saved as patches in `C:\Users\kumar\worktree-archive-2026-11-10` (25 MB, with a `MANIFEST.json`), and the three heads on no branch were kept as `archive/wt-*` branches. Free disk went from 37 GB to 66 GB. Kept: the main checkout, `C:\gdw` (GAGOS's hourly job), `C:\oc\ai-editor-selfcorpus` and `work\ai-editor`.
  - **The removal broke the main checkout's frontend packages.** Many of those worktrees' `frontend/node_modules` were junctions to the main checkout's, and deleting the worktrees followed them: 105 of the 354 packages in `frontend/node_modules` were deleted, with Vite's dependency cache. This was already written down as a step to take first (remove the junction with `rmdir`), and it was not taken. Tracked files, `data/` and the venv were not touched. GAGOS's 03:50 UTC batch then refused, its ESLint failing to load. The operator stopped his dev server; `npm ci` reinstalled every package from the lock file (308 required, none missing; jsdom 31.0.0, vite 8.3.6, as #601, #602 and #607 pinned, which his face had not had yet); `daily_backend.py up` restarted the face; a dry run of GAGOS's batch found its 69 warnings again.
  - `data/services/gagos_quiet.py` now checks a quiet marker's process by its start time as well as its id. Windows reuses ids, so a stale marker could have kept GAGOS aside for as long as an unrelated process with the same id lived.

## 2026-11-09, GAGOS's last finding went to a writer that cannot answer (master `bd8a75c9`, branch `fix/gagos-probe-takes-no-only-finding`)

- **Found by the review loop.** From 13:51 to 19:51 UTC, seven runs in a row, GAGOS had one finding left (`frontend/src/workbench/MaintenanceCenterPanel.test.jsx`). Each run gave it to a Bedrock writer whose last call was refused, tried again to see if it answers. Bedrock refused every time, while the plans' writers (Claude, Codex) stood idle.
- **The cause.** `tools/gagos_daily.py` gives one finding a batch to a refused writer and one to each writer at a usage limit, taking them from the end of the batch. With one finding, that was the only one.
- **Now** such a writer never takes the last finding a writer that answers could take. With two findings or more, it still gets one. With no writer that answers, it still gets the work.
- **Test:** `test_a_refused_writer_never_takes_the_only_finding_from_one_that_answers`. Without the fix it fails, the finding going to the refused writer. The GAGOS test files pass: 286 passed, 14 skipped.

## 2026-11-09, the leftovers, and the plan against what shipped (master `bd8a75c9`, branch `fix/verify-web-build-context`)

- **The operator, 2026-11-09:** "plz honestly do all ... and is honestly everything done to plan?"
- **The web sandbox image builds as documented.** The root `.dockerignore` excludes `frontend/`, so the command the sandbox prints when `aios-verify-web` is missing failed at its first COPY. `Dockerfile.verify-web.dockerignore`, which BuildKit reads in its place, keeps the context to the three files copied. Built from the root with it: the same eleven layers as the image in use. A new register fact, `web-image-build-context` (42 of 42), is guarded by a test that fails without the file.
- **The whole backend suite ran locally**, on master plus this branch, in six chunks: 8924 tests, 8874 passed, 50 skipped, 0 failed.
  - The one failure seen earlier today is not reproduced. That run was killed by its timeout and only its last character, an `F`, was kept, so which test failed is not known. It ran on `c1cff3f3`, before #605, #607 and #608.
  - **Fixed on the way:** the operator's user-wide `AIOS_ROUTER_CLOUD_TASKS` made two tests of the local-only default fail on his laptop and nowhere else. `tests/conftest.py` no longer lets the suite inherit it.
- **Not done: the face's packages.** `frontend/node_modules` still holds jsdom 30.1.3 and vite 8.3.5 (the lock has 31.0.0 and 8.3.6). Stopping the running dev server was refused by Claude Code's safety classifier, so it waits for the operator.
- **The plan (`staged-napping-micali`) against what shipped.**
  - Shipped as planned:
    - the register and its audit;
    - one registry of brains (it lives in `aios/core/router.py` `PROVIDERS`, not a new `providers.py`) and its agreement test;
    - the swarm through the Worker Foundry;
    - guards on statuses, image tags, ports, the ledger path, plan model ids and privacy on every cloud egress path;
    - organ evidence re-gathered at master.
  - Shipped differently, each recorded in the register:
    - Model labels are pinned by an agreement test, not drawn from one table.
    - No test asserts 100%, so a new fact can be registered as open.
    - "Did the tests pass" turned out to be two questions, each with one rule. So the Testing queen and maintenance do not call the workshop's `run_change_tests`.
  - Not done:
    - **The workshop's writers are not Foundry workers.** The plan said they would be. They were kept apart because they are sealed calls with no tools, so they do not act. That was Claude's judgement, not the operator's decision. His decision covered the swarm.
    - **No shared review schema.** The Critique queen and the workshop's reviewer were to share one; they do not. Read closer, they answer different questions: the queen is a rule over the Testing queen's verdict, and the reviewer is a model judging a code change.
    - **`AIOS_SWARM_CLOUD_BURST` is not retired.** The plan retired it after measuring the burst live, which has not happened. Since #604 it is a second opt-in on top of the egress law, which is stricter, not looser.
    - **None of the plan's live checks ran on the operator's backend:**
      - a coding turn reaching a plan brain;
      - the council's dissent offered a plan brain;
      - a swarm turn with workers side by side;
      - the face's task panel showing every status.

      The image-tag agreement is the exception: `daily_backend.py check` passes. The swarm turn needs his session.
  - **Docs:** `SUBSYSTEM_REGISTRY.md`, `AUTHORITY_MAP.md` and AGENTS.md §XI now describe the registry, the swarm's Foundry route and the burst's two gates. `CURRENT_RUNTIME_MAP.md` keeps its dated baseline and gains a pointer. The two `activeCastes` stores are documented, and whether a swarm turn reaches both is to be observed live.

## 2026-11-09, the open PRs merged (master `c1cff3f3`, branch `evidence/after-604`)

- **The operator, 2026-11-09:** "plz honestly fx all oPen PRs and merged them sequnetially".
- **Merged today:** #603, #601, #602 and #604.
  - #603: GAGOS's Python is formatted as CI requires.
  - #601: troika-three-text stays at 0.52.5. @react-three/drei 10.7.9 requires ^0.52.4, and 0.53.1 installed a second copy, which failed twelve caption tests. Dependabot now holds it until drei accepts 0.53.
  - #602: jsdom 31. jsdom 31 substitutes custom properties and computes no style for a detached element, as browsers do. Three layout tests now assert the values the variables resolve to and attach their root. The code is unchanged.
  - #604: cross-system consistency, the section below.
- **#599 was superseded by #605.** Dependabot regenerated the Python group, again with pydantic 2.14.3 and its core left at 2.50.2, which pip cannot resolve. The core pin and the Dependabot ignore bound move to 2.50.4. #605 merges after this PR.
- **#604 needed two test fixes after it was opened:**
  - `tests/test_config.py` imported the copy of the cloud-task parser that #604 removed. It now tests the law's own parser.
  - A maintenance-executor test assumed the old private default, production. It now asks for production, and still asserts the production executor has its client.
- **Master went red after #604's squash merge.** The operator merged it while its final backend run was still in progress. Master's own run then failed exactly three tests, on macOS and Ubuntu, and nothing else: the tests that catch evidence citing a commit the squash discarded (`478b3c51`).
- **This branch re-gathers that evidence at master's tip `c1cff3f3`**, without re-pointing it:
  - every claimed organ passed, with Docker up;
  - organ 33's live clerk run passed: qwen2.5:0.5b, 10 passed, 0 skipped;
  - the three tests pass on it locally.

## 2026-11-09, the ant colony runs through the Foundry (branch `feat/swarm-in-foundry`, on `feat/consistency-guards`)

- **The operator's question, 2026-11-04:** "can be multiple workers working that's y o made queens and ant-colony inspired workers are we honestly using those". They were not: from 2026-07-15 production refused every swarm turn (`strategy_unavailable`, "route it through WorkerFoundry before enabling"). His decision on 2026-11-09: "Swarm into the Foundry".
- **Now a swarm turn runs, every caste leg a worker the Worker Foundry admits.** The legs are scout, decomposer, cloud broker, workers, quorum and synthesizer (`aios/application/workers/swarm_foundry.py`).
  - The emergency stop is checked at each admission: an engaged stop refuses the next leg, and the swarm ends saying so.
  - A bounded scheduler runs the legs, and each leg's lifecycle lands on the cortex bus: requested, admitted, started, completed or failed or awaiting approval, dissolved.
  - The swarm runs inside the same governed turn wrapper (privacy target, receipt) as a single agent, so a leg's every tool stays behind the executor gate and the operator's approvals.
- **Several workers at once.** Worker legs run side by side on a cloud or plan brain (`AIOS_SWARM_CLOUD_CONCURRENCY`, 3), and one at a time on the local brain: on a 16 GB laptop, parallel local legs fight over one model.
- **A privacy fix in the newly reachable path.** A cloud-burst leg was given the turn's private recall, while the governed path strips recall from anything bound for the cloud. Such a leg now gets the operator's contract and no recall. Cloud burst stays off by default.
- **Kept apart, and pinned:**
  - the role pass is still refused;
  - the operator's main turn runs its own tool agent outside the Foundry, by his choice;
  - the workshop's writers are sealed model calls through the gateway with no tools, so they do not act.
  - Every tool agent in production comes from the generate pipeline's two factories, so an agent built anywhere else fails a guard.
- **Tests:**
  - The swarm Foundry's own tests: each leg admitted, a stopped colony refused, three workers meeting at once, a paused leg awaiting approval.
  - A real `/api/generate` swarm turn passes, with its legs admitted and nothing sent to the cloud with burst off.
  - The reachability tests, written to fail if the gate went, were rewritten deliberately.
  - 243 tests across the turn, architecture and gateway suites pass.
- **Settings read twice** (2026-11-09).
  - The rule for when a missing signing key may fall back to a test placeholder was spelled out in four modules (verification, promotion, checkpoint, API-token rotation). It is written once now, in `aios/core/signing_keys.py`.
  - Every other setting read in several files agrees on its default, or is named with its reason (`SETTING_EXCEPTIONS`).
- **The rollback setting.** `AIOS_ROLLBACK_DIR` named both the rollback engine's git directory and the promotion checkpoints' store; set, both landed in one directory. Checkpoints read their own `AIOS_CHECKPOINT_DIR` now, with the same default (the system temp directory). The operator's environment set neither, so nothing moves.
- **Brain availability.** One classification of a failed call (`aios/core/model_availability.py`): a model refused, a usage limit that lifts by itself, or anything else. The router and the workshop read failures through it.
  - A plan writer at its session or weekly limit is no longer "refused". It is tried on one finding every batch, instead of waiting behind every writer AWS refused.
  - Its stated reset time is not parsed: that needs the named time zone, and this Windows Python has no tzdata.
- **The register: 41 of 41 registered facts guarded (100%), from 12 of 35 on 2026-11-04.** Each guard was shown to fail on its drift.
  - What 100% means: every fact the register names has one source, or a test that fails when its places disagree.
  - What it does not mean: that GAGOS holds no other duplicate. A fact nobody registered is not measured. When one is found, it is added open and the score drops until it is guarded.
  - Measured over the code. Most of it has not run on the operator's live backend, and the full backend suite runs only in CI here, where memory allows.
- **What the two adversarial reviews found, fixed** (each pinned by a test in `tests/test_swarm_foundry.py`):
  - **High.** Two legs that ran side by side and both paused for approval: only the first request reached the operator, and the other legs' work was dropped unsaid. The turn now names every leg still waiting, and its command, before it pauses; each asks again when the turn resumes.
  - **High.** One hung leg could hold every slot of the process's swarm scheduler, so another turn's legs waited forever: no leg timeout was enforced. A leg now fails at its timeout (600 s) and frees its slot, and the process runs four turns' worth of legs. Its thread cannot be killed; it stops at its agent's own next check, as a single agent's would.
  - **Medium.** A leg's own crash was reported as a refusal, unlogged, with the exception text unredacted. It now raises as a single agent's would. A real refusal is logged on the server and passes the secret scanner before it reaches the stream.
  - **Cloud burst obeyed only its own switch,** past the one egress law every other cloud route obeys. It now needs the switch and the law (the router's own `policy_allows`) to let this task leave the machine.
  - **Tests.** Each test Foundry is now closed, so none leaks its loop.
- **Kept as it is, said plainly:**
  - An approval is of a command, not of the leg that asked: approving one leg's command lets another leg in the same turn run the identical command. A single agent already may re-run an approved command in its turn, so the swarm does not widen what one approval permits; it spreads it across legs.
  - A leg already running when the emergency stop engages stops at its agent's own next check, as a single agent does; the next leg is refused at admission.
  - A cloud-burst leg (off by default, and now under the law) receives the turn's conversation, filtered by the cloud client's PrivacyFilter as every cloud call is, and no recalled memory.
- **Not measured yet:** a live swarm turn on the operator's own backend. It needs his session, so it is his to try once merged.

## 2026-11-09, consistency guards (branch `feat/consistency-guards`, on `feat/one-brain-registry`)

- **The third step:** the facts that are not about brains or workers. Each disagreement found is fixed where one place can be the source, and pinned by a test where two places must stay separate. `tests/test_consistency_guards.py` holds the guards; each was shown to fail on its drift before being kept.
- **Fixed:**
  - **The cloud-task law.** The security test and the thesis audit checked a copy of the default in `aios/config.py`, while the law's own default in the frozen `limits.py` went unchecked: it could have changed under a green test. They now read the law itself (`tools/thesis_audit.shipped_cloud_tasks`, from its source). The dead copy is gone, and the `.env` template names the law's classes.
  - **The Ollama address.** Bootstrap checks and writes `OLLAMA_HOST`, the name the runtime reads, not `AIOS_OLLAMA_URL`, which nothing read.
  - **Store file names.** The launcher's provenance command opened a file nothing writes (every trace came back empty). `missions.db` was named four times, `system_portrait.db` and `council_state.db` twice each, and eleven tools rebuilt config's names. Each name now has one home.
  - **The face's states.** It repairs REOPENED and VERIFICATION_FAILED findings too, as the backend allows. Its skill states are the backend's, so one new backend state can no longer blank the Skill Library.
  - **The daily backend.** It asks the sandbox for the image name, and points the executor at the backend's own staging root, which the guard checks the frozen scope lock pins.
  - **GAGOS's ledger path** is written once.
  - **The CLIs.** The Claude Code and Codex commands are sealed once, in `plan_cli`, for the workshop and the counter. The workshop also found Codex with `shutil.which` alone, so it would have launched a `.cmd` shim the plan client refuses.
- **Pinned:** the default ports of the counter, executor and face, read from each place's source; and GAGOS's task statuses against the face's styles.
- **The profile, the operator's decision (2026-11-09).** `AIOS_PROFILE` was read in 8 files: development by default in most, production in the private executor service and the launcher, so one process held two profiles.
  - Unset now means `development` for dev and test runs, through one reader, `config.profile()`. The daily backend says `production`, so every command on his counter crosses the private executor with isolation proof.
  - `aios/core/executor.py` is not edited by this work: its default is pinned to the one default. The launcher's default stays production; it is the profile it launches, not the one it runs as.
  - Live on his backend under production: the backend, executor and face boot and answer, and readiness passes. An approved command through the private executor was not exercised, since that needs his approval. Until this merges, a reboot brings his backend back as development (the watchdog runs master's `up`).
- **Found, not fixed (open):**
  - 18 of 196 `AIOS_*` settings were read in more than one file; `AIOS_PROFILE` is now settled, and the rest is its own step.
  - `AIOS_ROLLBACK_DIR` and `AIOS_EXECUTOR_WORKSPACE_ROOT` each mean two different things.
  - The sandbox image tag hashes the checkout's bytes, so a Windows (CRLF) and a Linux checkout name different images for one commit.
- **The test judges were two questions** (2026-11-09).
  - "Did this command succeed?" The Verifier and the VerificationAuthority both decide it on the exit code. The Verifier kept its own copy of the count parser; it now uses the shared one.
  - "Did this change break a test that passed before?" Only the workshop's sandbox asks it, against the base.
  - Maintenance asks the first of the command the operator approved, so a test already failing blocks a repair: it fails closed, by design.
  - The register now counts them as the two facts they are, each guarded.
- **A privacy fix** (2026-11-09).
  - Three of five calls in the generate pipeline passed every brain's client but Vertex's. One of them set the turn's privacy target, so a turn served directly by Vertex (an explicit `vertexmaas.*` model) had its governed context compiled for a LOCAL brain, private recall included, before it went to Google.
  - The chat route could not select a Vertex model at all.
  - Every call now passes every client, and `test_a_call_that_names_one_brains_client_names_them_all` fails a production call that names one brain's client and not the others. It found the chat route's omission on its first run.
- **Side jobs' cloud brain** (2026-11-09): the council's dissent, CRAG's cloud source and the swarm's cloud burst take one choice (`router_wiring.first_cloud_brain`): the registry's first configured cloud brain whose model this account has not refused. CRAG picked "gemini or bedrock" and the burst "bedrock or gemini", blind to refusals. Each keeps its own switch; both are off by default.
- **The register: 36 of 40 facts guarded (90%), from 18 of 37.** Open:
  - the worker engines (the one engine, next);
  - brain availability;
  - the rollback setting;
  - settings read twice.
- **Tests:**
  - Related backend suites reached 92% with no failure before Claude Code stopped them for low memory; the rest is CI's.
  - The 54 register and guard tests pass, as do the frontend's 26 tests for the two changed files and ESLint.
  - While formatting, ruff's `--fix` also removed pre-existing unused imports in three files. Those are GAGOS's work, so they were put back.

## 2026-11-04, one registry of brains (branch `feat/one-brain-registry`, on `feat/consistency-register`)

- **The second step.** `aios/core/router.py::PROVIDERS` is the one registry of GAGOS's seven brains: name, cloud or local, price, skills, the setting that enables each, its client getter and its client class. Every list the measurement found now reads it:
  - the failover's cloud and local sets, the privacy broker's local set;
  - the hiring broker's skills and prices, and its local checks;
  - the provider-health list, the readiness probe, the hiring service and its status route;
  - the council's dissent reasoner, which now also skips a model the account refused, as the router does;
  - the router's own prefixes and capabilities, `tools/preflight.py`'s constants.
- **Behaviour that changes, on purpose:**
  - a turn Vertex served outside failover is recorded as `vertexmaas`, not `ollama`: both directions of "name to client" read one mapping (`router_wiring.clients_by_provider`);
  - the health list, the readiness probe, the hiring status and the hiring service know Vertex and the operator's plans;
  - the hiring broker prices openai low, as the router always did;
  - the council's dissent reasoner can use Vertex or a plan when no other cloud brain is configured, and passes over a refused model.
- **Guards that derived their lists:** the privacy guard checks every cloud client the registry names (six; it checked four, without the plan and Vertex clients), and the boundary test's forbidden classes are the registry's (the hand-written set lacked `VertexMaaSClient`).
- **The register: 18 of 37 facts guarded (49%), from 12 of 35.** (One new fact registered on the way: three notions of whether a brain can serve now.) Hand-written provider lists: 5, from 17, each named with its reason in `tests/architecture/test_one_provider_registry.py`. Its guards were each shown to fail on their drift (the Vertex label bug, the broker's own openai price, a new hand-written list) before being kept.
- **Still open from this step:** CRAG's cloud source (gemini or bedrock) and the swarm's cloud burst (bedrock or gemini) pick by hand, the `side-job-cloud-brain` row; they belong to the one engine for workers.

## 2026-11-09, GAGOS's Python formatted as CI requires (branch `fix/gagos-formats-python`)

- **What stopped GAGOS for five days.** Its PR #598 (2026-11-04) held two correct E741 renames, the first fixes of its behaviour tier, and failed the required `format-gate`: one renamed line became too long. The workshop asked ruff what it warns about, never how it formats. While #598 stays open, GAGOS delivers nothing new.
- **The fix.** A writer's Python text is formatted by the project's own ruff (`python_static.format_python_text`) before its checks, in a finding's fix and in a task's files alike. What is checked, tested in the sandbox, reviewed and delivered is the layout the gate accepts. Formatting changes layout only and keeps the file's line endings; a text ruff cannot format comes back as it was, for the parser's check.
- **Found on the way.** The batch scanned Python only when `F401` or `F841` was among the day's rules, so a day narrowed to the behaviour tier's ruff rules (E402, E741, F821) scanned none. A rule is Python's now by its code's shape (`daily_work.is_python_rule`).
- **Tests.** Three new ones, on #598's own case, fail without the change. 260 of GAGOS's tests pass, and the Bandit, format, mypy and dead-code gates pass.
- **Since, the same day:**
  - #598 got one layout-only formatting commit at the operator's word, passed its gate and was merged.
  - Docker Desktop was started at his word, and the sandbox runs again.

## 2026-11-04, consistency measured (branch `feat/consistency-register`, off master `d7bd7ef0`)

- **The operator's request:** "I want u to make my cross-system consistency of my project 10/10 honestly 100%." This is the first of four steps: measure. Nothing in GAGOS behaves differently yet.
- **The register.** `.aios/state/CONSISTENCY_REGISTER.json` lists the facts two or more parts of GAGOS rely on, every place each is derived, and whether a test fails when they drift. `scripts/consistency_audit.py` checks every claim (a row cannot claim a guard that is not a real test) and generates the status in `docs/architecture/CONSISTENCY_REGISTER.md`.
- **The honest start: 12 of 35 registered facts guarded (34%).** The 12 are guards that already existed (the one gateway, the event vocabularies, the route registry, the one egress law, and so on). 100% will mean every *registered* fact is guarded; a fact nobody registered is not measured.
- **Eleven disagree today, two agree only under conditions** (staged work while `AIOS_DATA_DIR` is unset, the plan models only when the daily backend starts the counter), **and two guards have drifted**: the privacy guard over cloud clients lists four by hand and lacks the plan client (which does filter), and the workshop's Codex test pins a hand-written subset of the sealing flags. Among the eleven:
  - a turn served by Vertex outside failover is recorded as `ollama`, a local brain: `_provider_name` never checks the Vertex client;
  - the provider-health list, the readiness probe, the hiring broker, the council's dissent reasoner and the swarm's cloud burst each keep their own shorter list of brains, none with the operator's plans;
  - the hiring broker prices openai high, the router low;
  - three judges of "did the tests pass" can disagree (the sandbox judges against the base, the other two on exit code alone);
  - the `.env` template names cloud-task classes (`general`, `fast`) that the law silently drops;
  - the launcher's provenance command reads a database file nothing writes;
  - rollback checkpoints and the profile each have two defaults, and the Ollama address two setting names;
  - the face cannot repair a REOPENED finding, and its skill states differ from the backend's.
- **Seventeen hand-written lists of provider names** remain in `aios/` and `tools/`, counted by the same script.
- **A correction.** On 2026-11-04 I told the operator the ant-colony swarm runs when he switches swarm on. It does not: production refuses it (`generate_pipeline.py`: "route it through WorkerFoundry before enabling"). The swarm is switched off, not merely unused.
- **Next:** one registry of brains, then one engine for all workers (the swarm entering the Foundry), then guards on the rest, each its own PR.

## 2026-11-04, GAGOS's behaviour-changing warnings (branch `feat/gagos-self-complete`)

- **The operator's request:** "I want GAGOS HONESTLY 100% complete itself". The warnings whose fix can change behaviour become GAGOS's own work: `react-hooks/set-state-in-effect` (17), `react-hooks/exhaustive-deps` (3), and ruff's `E402` (3), `E741` (5) and `F821` (1), 29 of the 75 counted on 2026-11-04.
- **The bar is higher than for a lint fix.** The fix must still remove its warnings and add none.
  - It may reach 12 lines from its warning, or anywhere in the file for a rename (E741).
  - Its writer is told behaviour must not change and that tests will run.
  - It reaches a reviewer only if the sandbox ran tests that exercise its file, and they passed. A fix with no such test is refused; when the sandbox cannot run, the fix waits, unreviewed.
- **Left out:** `react-refresh/only-export-components` (10), since its fix moves exports into a new file, and a task changes files that exist; and one warning ESLint reports without a rule, not yet identified. (A first draft of this line said 11: a miscount, corrected the same day.)
- **Tests:** `tests/test_gagos_self_complete.py`, 6 tests, 5 of which fail without the change; all 210 of GAGOS's tests pass.
- **The full backend suite reached 92%** before Claude Code stopped it for low memory, with two failures. Both fail on master too, only because the operator's user-wide `AIOS_ROUTER_CLOUD_TASKS=reasoning,coding` reaches the tests, and both pass with it unset. CI runs the rest.

## 2026-11-04, D14 ready (branch `feat/gagos-d14`, off `evidence/after-591`)

- **The operator's request:** "plz honestly do all than we will be ready for D14". Three things were still not done:
  - changes across several files;
  - a frontend sandbox;
  - the face coming back after a reboot.
- **How it was built.** I wrote the contract (`7aba0794`/`a9d759b6`): up to `MAX_TASK_FILES = 5` per task, grouped proposals, one sandbox entry for a set of changes. Three Sonnet builders worked in parallel worktrees, then two adversarial reviewers.
  - The sandbox builder and both reviewers were cut off by a usage limit. The sandbox builder's uncommitted work was intact, including a built image. A fresh run finished it, and the reviewers ran after it.
  - I reviewed and integrated everything, and fixed what the reviewers found.
- **Several files.** A task names up to five files. Each file must be one GAGOS may edit, and they must fit one answer together: 30,000 characters, measured as sent.
  - One writer call returns every changed file, labelled.
  - Each file is checked. One proposal per file is recorded under the task's group, and the group is all or nothing.
  - The sandbox runs the group's tests once, with every change in place. One review covers the group, and its verdict is recorded on every file.
  - One commit delivers it, and it fails or goes stale together.
- **The frontend sandbox.** Image `aios-verify-web:326b5b186735` (980 MB): Node 24 and the frontend's dependencies from `package-lock.json`.
  - It runs through the unchanged `DockerRunner`: no network, a read-only root and workspace, only `/tmp` writable, not root.
  - The frontend (9.1 MB) is copied into `/tmp`, and vitest runs `related`, judged against the base as Python's tests are.
  - Live:
    - a harmless change to `ErrorBoundary.jsx` passed, 8 tests in 21 s;
    - the same module broken was BROKE, with 7 tests named, in 26 s;
    - a two-file change passed, 336 tests in 59 s, with the copy restored byte for byte.
  - The containment probe passes 8 of 8 in real containers. CI does not build the web image, so its probe skips there.
- **The face after a reboot.** `daily_backend.py up` starts the face (vite on :5173, no window, a process group of its own) when it does not answer. So the existing 15-minute watchdog brings it back, with no scheduled-task change.
  - `down` stops only the face it started.
  - Live, from the branch: it started in 8 s, answered, and was recognised as its own; `down` stopped exactly it.
- **What the reviewers found, fixed with tests that fail without the fix:**
  - **High (both reviewers).** `down` killed a recorded face pid whenever anything answered on :5173, but a pid outlives a reboot. The face is now recorded with its process's creation time, and stopped only while that pid still has it. Windows' socket listings (`netstat`, `Get-NetTCPConnection`) missed live listeners on this laptop, measured that night, so identity does not rest on them.
  - **Medium.** The several-file bound summed the unmasked files, but a placeholder can be longer than what it hides.
- **Tests.**
  - The backend suites pass, 611 tests (GAGOS's, the counter's and its route guards, gateway, failover, the boundary).
  - The frontend: 218 pass; ESLint and `tsc` are clean.
  - Bandit passes, and no organ entrypoint changed.

## Night of 2026-11-03 (branch `evidence/after-591`, off master `fd161709`)

- **The operator merged #591, the counter's plan brains.**
  - It went in as a rebase merge, ending at `fd161709`, so the branch commit `a2d3562b` its organ evidence cited is not on master.
  - Before the merge, CI had failed on all three systems in the same two workshop tests. A client built where neither Claude Code nor Codex is installed had the model `''`. Fixed in `b82909e1`: the client keeps its configured model and names the missing tool, and the tests now simulate CI's missing tools.
- **The counter runs it.** I pulled his checkout and restarted the backend with its tool. It runs `fd161709`, reports "auto routing: cloud-eligible for reasoning,coding", and offers Sonnet and Haiku, plus gpt-6.1-sol, gpt-6.1-terra and gpt-6-luna. Whether he uses it is measured by his turns in the daily store.
- **Organs re-gathered at master's tip `fd161709`:**
  - the Phase 4 live wave passed, with Docker live;
  - organ 33's live local-clerk suite ran against the real Ollama with `qwen2.5:0.5b`: 10 passed, 0 skipped (`release/organ-33-37/clerk-junit-fd1617098921.xml`);
  - the organ guards pass.

## Evening of 2026-11-03 (branch `feat/counter-plan-brains`, off master `0624892a`)

- **Usefulness, measured honestly when the operator asked.** His daily store has 0 user turns in November. The last was 10-30 04:23, a proof script, and the last ordinary turn was 07-10. GAGOS's own work in two days was 20 changes: unused imports and variables, one `any`, and the first test files. That is real hygiene, but it did not help him. He works through Claude Code and Codex, not GAGOS.
- **Why the counter went unused.** Two causes, both measured:
  - **It ran old code.** His checkout was 64 commits behind master: `f6206755` against `0624892a`, so the tasks feature was not live. An executor started on 11-02 at 21:08 and not tracked by the tool held port 8081, so restarts kept the old one answering.
  - **It ran a small brain.** Cloud tasks were off at the counter, so the local `qwen3.5:9b` answered him. The strong models (Sonnet, Haiku, Opus) worked only in the workshop.
  - **Done at about 10:20 UTC:** I fast-forwarded his checkout, stopped the stray executor, and restarted the backend with its tool. It now runs `0624892a`, with the sandbox image `aios-verify:40909f67de63`.
  - The frontend still needs `npm ci` (its dependencies changed) before the new panel shows. That waits for his word.
- **The operator's choice: "connect codex models to counter also and C".** That means Claude through Claude Code on his Pro plan, and the GPT models through Codex on his OpenAI plan. No API key is involved. On this branch:
  - **The client.** `aios/core/plan_cli.py` (`PlanCliClient`) sits behind one router provider, `plan`.
    - Each call is sealed as the workshop runs them: no tools of their own, no session, none of his MCP servers or plugins, an empty directory.
    - The PrivacyFilter runs before anything leaves.
    - Every call goes through `model_calls.observe`, so the one-gateway law refuses a production call outside an entrance (tested).
    - The agent's tools are answered through structured output.
  - **The policy.** `plan` is a cloud provider, eligible only for his cloud tasks.
  - **The launch default.** The daily backend now launches with his own user-wide cloud tasks, `reasoning,coding`, while general and fast turns stay local. It offers Sonnet and Haiku, and `gpt-6.1-sol`, `gpt-6.1-terra` and `gpt-6-luna`. Opus is left out, because it would spend the plan he shares with his own sessions fastest.
  - **Live.** Haiku through Claude Code and GPT-6 luna through Codex each answered a tool turn with a correct `read_file` call (9 s and 15 s) and a plain turn (6 s).
  - **Two adversarial reviewers.** Their findings, all fixed with tests that fail without the fix:
    - **High:** failover's own cloud list lacked `plan` (and, before this branch, `anthropic`), so a turn could try two clouds in a row.
    - **Medium:** the call ledger attributed `plan` calls to the client, not the caller.
    - **Medium:** the architecture guard did not forbid constructing `PlanCliClient`.
    - **Medium:** the ops doc still said cloud tasks default to none.
    - **Low:** three smaller hardenings.
  - **Organ evidence.** Organs 25, 27, 28, 29, 32, 33, 34, 38, 42, 50 and 53 were re-gathered at the branch tip `a2d3562b`. The live wave passed with Docker live. Organ 33's live local-clerk suite ran against the real Ollama with `qwen2.5:0.5b`: 10 passed, 0 skipped (`release/organ-33-37/clerk-junit-a2d3562b4fb0.xml`). None is a spine organ.
  - **Not yet:**
    - The frontend's model picker does not list the plan models. `auto` uses them for reasoning and coding.
    - After the merge, his checkout must be pulled and the backend restarted.
    - Whether he uses the counter will be measured the same way, by counting his real turns.
- **Then, at the operator's word ("plz honestly complete which is not done yet"):**
  - **The face runs on current code.** I ran `npm ci` in his checkout (323 packages, 39 s), so its dependencies now match master's lock file. GAGOS's worktree links the same `node_modules`, so its lint ran on stale packages until now. The dev server was started hidden and logs to `data/services/frontend.log`; `http://localhost:5173` answers "GAGOS — The Voyaging Mind". Nothing starts it after a reboot; that stays a manual start.
  - **A correction.** I had said the frontend's model picker did not list the plan brains. The superbrain has no picker: it always sends `auto`, so its reasoning and coding turns reach his plans through the router. The workbench's expert toggle offered only Local and Gemini, and no Gemini key is held. It now cycles Local, Auto, Sonnet and GPT (his plans, chosen outright through `plan.<model>`). A saved choice no longer offered shows Local. The 148 workbench tests pass, ESLint shows the same 12 warnings as master, and `tsc` is clean.
  - **The Codex writers.** GPT-6.1 terra and GPT-6 luna join GAGOS's writers on his OpenAI plan. Each plan has its own share of a batch (Claude 4, OpenAI 4), and Claude Code stays the reviewer. Every plan writer is now the counter's own `PlanCliClient`, one sealed path, and `ClaudeCodeWriter` is gone. Live: GPT-6.1 terra wrote a 29-line first test for `starterPathData.ts` that passed the static checks (`gd-e61dde2b13`, 14 s).
  - **Still not done, and bigger:**
    - Changes across several files.
    - A frontend sandbox (a Node image) so frontend proposals' tests run before review.
    - Nothing restarts the face after a reboot.

## Afternoon of 2026-11-03 (branch `feat/gagos-tasks`, off master `634b484d`)

- **The operator merged #586 (GAGOS's three Python fixes) and #587 (the test-name fix).** #587 went in linear, as `634b484d`.
- **The two proposals the test-name bug had blocked are accepted.** I reopened them with `review --again` at 07:31 UTC, and Claude Code accepted both: Haiku's `doc_ingest.py` and Sonnet's `curriculum_miner.py`.
- **GAGOS takes tasks the operator writes, in its workshop, counter and face.**
  - **The request.** The operator asked why GAGOS's changes are only one or two lines. I answered honestly that so far it is held to lint fixes that keep behaviour, one file at a time, with a reach check. He replied: "Yes there is lot of work ... in every infra-end of GAGOS plz start that multi-agent workflow". Workshop, counter and face are my own earlier names for GAGOS's hourly worker, its backend, and its frontend.
  - **How it was built.**
    - I wrote the shared contract myself (`bcf9e58c`): a `tasks` table in GAGOS's ledger. A task is his words plus one file, and it moves once: from open to taken, refused or cancelled.
    - A workflow ran three Sonnet builders in parallel worktrees, then two adversarial reviewers.
    - I reviewed every diff, integrated the three, and fixed the one bug both reviewers found.
  - **The workshop.**
    - Open tasks go first in each batch.
    - A task on a file GAGOS may not edit is refused before any model is asked: the frozen core, an organ's entrypoint, or a file that does not exist.
    - His words are scrubbed before any model reads them.
    - A failed model call leaves the task open for the next hour.
    - The checks: the change parses, no lint count rises, nothing is silenced, and something changes. There is no reach check.
    - The reviewer judges the change against his words. The commit says it was his task.
    - `task add/list/cancel` on the command line.
  - **The counter.** `GET /api/gagos/tasks` (GREEN), plus `POST /api/gagos/tasks` and `POST /api/gagos/tasks/{task_id}/cancel` (YELLOW, so each asks for his approval). All three need the privileged operator. They never call a model and never return his principal.
  - **The face.** A "GAGOS tasks" panel under Expert, next to Maintenance: write a task and watch it through writer, sandbox, review and PR. It uses the existing guarded command client and existing tokens only. I have not looked at it in a browser.
  - **The bug both reviewers found, fixed.** A task and a lint fix on the same file became two proposals on one base, so one would go stale. Now a file a task takes gets no lint fix in that batch. The new test fails without the fix.
  - **Organ evidence.** The counter had to touch three organ entrypoints: `aios/policy/kernel.py`, where every route must be declared; `aios/domain/actions/envelope.py`; and `aios/api/main.py`. Organs 7, 25, 26, 27, 30, 32, 42, 45 and 52 were re-gathered at the branch tip `725a2e1c`: every claimed organ passed, with Docker live. None is a spine organ. A squash merge will orphan that tip, so they need re-gathering on master afterwards, as before.
  - **Tests.**
    - The tasks suites, GAGOS's suites, and the route, policy, action and organ guards pass.
    - The panel's tests and the shell's pass, 67 of 67. ESLint and `tsc --noEmit` are clean.
    - The Bandit gate passes.
  - **A third egress gap, found at 08:50 UTC and fixed on this branch.** Sonnet and Haiku wrote three whole new frontend test files (56-124 lines); all three were refused as unshowable. The privacy filter alters a relative import (`'../superbrain/components/qualityTierContext'`), a regex it takes for a path (`/last-known/`) and a fixed test UUID, none of which were in the module, so the module's mask did not cover them. Now what a writer adds that the scrubbers would redact is hidden behind placeholders of its own, for every kind of proposal; the reviewer is told so. The new test fails without the fix; all three real proposals are showable now (3-11 placeholders each), to be reopened with `review --again` after merge.
  - **Not yet:** changes that span several files; a frontend sandbox; and Codex writers (GPT-6.1 terra and GPT-6 luna each answered one call today), which come next.

## Later on 2026-11-03 (branch `fix/gagos-sandbox-names-egress`, off master `e71d2694`)

- **The operator merged #584 (GAGOS's two frontend fixes) and #585 (the Claude writers) by 05:14 UTC.**
  - #585 went in as a merge commit after GitHub's "Update branch", although master's protection requires linear history.
  - Master's tree is exactly #584's two commits plus #585's change set, and master's CI on `e71d2694` passed.
- **GAGOS's first hour with Claude writers (05:50 UTC), on master `e71d2694`:**
  - **Writers.** Sonnet took 3 findings and Haiku 1. The 5 Bedrock writers were refused last time, so only Mistral Large 3 was tried, on one finding, and AWS refused it again. 5 findings waited for a later hour: the plan's share is 4 a batch.
  - **Static checks.** All 4 Claude proposals passed.
  - **Sandbox tests.** 3 passed (90 to 217 tests each). 1 had no test that exercises its file.
  - **Review.** Claude Code accepted 2: Sonnet's `operator_model.py` and `project_passport.py` fixes. The other 2 were refused as unshowable, because of the bug below.
  - **Delivery.** GAGOS opened its own PR, #586, with those two and Haiku's accepted fix from the trial (`sqlite_mission_repository.py`). I checked each diff: every removed name occurs once on master, in its import only, and no other module imports it from there.
- **My sandbox step showed the reviewer a test name the privacy filter hides. Fixed on this branch.**
  - The two refused proposals (`gd-426622285d`, Haiku, `doc_ingest.py`; `gd-3d41608cd0`, Sonnet, `curriculum_miner.py`) are correct.
  - Each carried "1 fail without it too": `test_get_executor_and_rollback_engine_return_real_instances`, which fails on master as well. The privacy filter takes that name for something sensitive, so the whole review prompt counted as altered, and the change could not be shown.
  - The fix: GAGOS's report of its tests is scrubbed like everything else that leaves the machine, so the reviewer sees `[SENSITIVE: ...]` in place of that one name.
  - The new test uses the real filters. It fails without the fix (the same "cannot be shown" refusal) and passes with it.
  - Both proposals were refused only for how they were shown, so `review --again` can reopen them once this merges.

## 2026-11-03 (branch `feat/gagos-claude-writers`, off master `575e7695`)

- **The operator merged #582 and GAGOS's #583 at 03:17 UTC.** #582 is the squash `ca9641f3`; #583 went in as its five commits, ending at `575e7695`. Master's CI on `575e7695` passed.
- **The 51 findings the AWS refusals had used up are back.** Between 20:50 and 01:50 UTC every call was refused, and the old rule counted each as an attempt, leaving 0 by 02:50 UTC. A dry run on the new master counts 51 not yet attempted.
- **Both proposals refused only for how they were shown are accepted.** I re-ran `review --again` on `gd-a9f57600cf` and `gd-06ea4955fc` at 03:30 UTC, and Claude Code accepted both.
- **GAGOS's 03:50 UTC run delivered them as its own PR, #584.** `gd-a9f57600cf`'s delivery check failed on master without the change too. So it was committed with that stated, and CI judges it. This is #582's delivery rule on its first real case.
- **AWS still refuses the account.** At 03:37 UTC I made one call with GAGOS's key: `ValidationException: Error 002: Access to Bedrock models is not allowed for this account` (request id `e20dbb39-f9d6-4500-bd2a-9af0d8ce40c8`). The key itself was accepted; the account is refused. Restoring it is the operator's act.
- **The operator chose Claude writers through his own plan (about 04:00 UTC):** "GAGOS can use several SONNET AND HAIKU AGENTS", and then "For #2", the option of Claude Code on his Pro plan with no API key. I told him first that the plan's usage is shared with his own sessions and the reviews, and that I am not sure how Anthropic's terms treat round-the-clock automated use on a personal plan. On this branch:
  - **How they write.** Claude Sonnet 5.5 and Claude Haiku 5.5 run through `claude -p`, exactly as the chief reviewer does:
    - no tools, no session kept, and none of his MCP servers;
    - in an empty directory, with GAGOS's system prompt;
    - through the same governed gateway, and the same privacy filter Bedrock's client applies.
  - **The limit.** At most 4 findings a batch go to them. They cost nothing against the AWS ceiling.
  - **A refused writer.** A writer whose last call was refused (AWS now, the plan's usage limit later) gets one finding a batch until it answers again. The rest of the work goes to writers that answer, and without a Bedrock key the other writers still work.
  - **Live trial at 04:11 UTC, on two real findings:**
    - Haiku's F401 fix in `sqlite_mission_repository.py` (`gd-c4bc33ba4e`) passed the checks.
    - Sonnet's correct F401 fix in `admission.py` (`gd-c129fc7000`) was refused by the reach check, because of the bug below.
    - The base was `346d8320`, the head of GAGOS's #584 branch, where delivery had left `C:\gdw`; it was not master. Both files are the same on master.
- **A bug the trial found, fixed on this branch.** GAGOS's Python checker passed a CRLF file to ruff through a text-mode pipe, which on Windows doubles every line break.
  - So a warning on line 10 was recorded on line 19.
  - Until #582 this did no harm. Since #582's reach check compares line numbers, any Python fix far enough down a CRLF file is refused.
  - Ruff now gets the file's own bytes. The new test fails without the fix (19, not 10) and passes with it.
  - `gd-c129fc7000` stays refused, since no command re-judges a static refusal, and it counts once against Sonnet's record.

## Night of 2026-11-02 (branch `feat/gagos-efficiency`, off master `945d08b8`)

- **The operator merged #581 at 18:57 UTC (squash `945d08b8`).** Its tree equals the head I tested (`636ba2e7`). Master now has GAGOS's Python work (its backend and itself), first frontend tests, and one reviewer.
- **GAGOS's own placeholders made two correct proposals unshowable (found at 19:05 UTC).**
  - The cause: each masking chose a random hex prefix (`GAGOSMASK1D44CF_0011`). The secret scanner's entropy test sometimes took such a placeholder for a secret, so the review prompt failed the egress check and the proposal was refused. For `gd-a9f57600cf`, 53 of 60 maskings were refused. The scanner did its job; the placeholders were the fault.
  - This also hit me directly: re-reviewing `gd-a9f57600cf` with `review --again` (19:00 UTC) refused it for this reason, and today's other "cannot be shown" refusal, `gd-06ea4955fc`, had the same cause.
  - The fix on this branch: the prefix is the first of `GAGOSMASKQ_`, `GAGOSMASKQQ_`, ... that the file does not contain, never random. Both proposals now pass the egress check 10 times in 10. `review --again` reopens a proposal refused only for how it was shown; any other refusal stays.
- **Efficiency, measured first** (the operator: "cross-system efficiency").
  - In November so far, 1 of 18 proposals is accepted by review, at about $0.15 of estimated AWS spend per accepted change. 3 more were accepted by me and released by #581.
  - Where the rest were lost: 4 not sent (privacy filter or size, including the 2 placeholder cases above), 2 to the answer's form, 4 to the static checks, 4 to the reviewer.
  - On this branch a fix that changes lines more than 3 away from the nearest warning is refused before review. Replayed on the day's ledger, it refuses both over-broad changes I rejected and passes every change I accepted. GAGOS's report gains these numbers.
- **GAGOS's first hour on #581's code (19:50 UTC) opened its own PR, #583, as `gagos-swap821[bot]`.**
  - It holds five changes, each accepted by me:
    - the evening's two frontend test fixes (`PanelLauncher.test.jsx`, `measuredState.test.ts`);
    - GAGOS's first backend work: three unused imports removed (`model_router.py`, `checkpoint.py`, `router.py`).
  - I rechecked each diff on the PR. Every removed name is unused across the repository, and the test helper the TypeScript fix uses is in scope.
  - Of that hour's Python proposals, 6 passed the checks: I accepted 3 and rejected 3. All three rejected proposals came from Mistral's two models, and each also collapsed the file's two-blank-line spacing between definitions. The base files have that spacing, and Qwen's and DeepSeek's proposals kept it.
- **One accepted change was wrongly failed at delivery.**
  - `gd-8b79700958` (`EcosystemDashboard.jsx`, the unused `React` import) failed "the tests related to the frontend targets".
  - The same related-test run fails on master's unchanged tree. `FixtureJourneyPage.test.tsx` exceeds its 5-second timeout when 22 test files run at once on this laptop.
  - The change is innocent. The delivery check does not compare against the base, and a failed delivery is final and counts against its writer. Not fixed yet.
- **The sandbox step (the operator, about 20:20 UTC: "Yes honestly").** GAGOS's Python proposals now run their tests before review.
  - **Where they run.** In the executor's own sandbox (`DockerRunner`, unchanged):
    - no network;
    - a read-only root and a read-only copy of the code;
    - every capability dropped, and no-new-privileges;
    - limits of 2 GiB, 2 CPUs, plus process and file-size limits;
    - nothing from the host's environment.
  - **What they see.** A `git archive` copy of the proposal's base commit, so no `.git`, `.env` or `data/`. The image is `aios-verify:<sha12 of its requirements.txt>`. I built `aios-verify:40909f67de63` tonight; the old `83b20d9b8dbd` predates #568 and #573.
  - **Judged against the base.**
    - A test that fails with and without the proposal is never blamed.
    - A proposal that breaks a passing test is refused before review, and its writer is told which tests broke.
    - The reviewer reads what the tests did.
  - **Proven live tonight.**
    - The accepted `router.py` change (`gd-b72768572b`): 163 tests in 9 files pass. One test fails without it too (`test_data_dir_private`) and is not blamed. 94 s.
    - A deliberately broken `router.py`: 11 tests named as broken. 93 s.
    - The containment probe, in the real container:
      - no TCP and no DNS;
      - no write outside `/tmp`, and `/tmp` is writable;
      - no host secret, even with the whole host environment given to the `docker` client;
      - not root, and only its own copy is visible;
      - the in-container kill timer works.

      The probe joins CI's real-container containment step.
  - **Not yet:**
    - Frontend proposals: the sandbox image has no Node. The reviewer is told so, and their tests still run at delivery.
    - Multi-file work and written tasks: next.
- **The delivery bug, fixed on this branch.** A delivery check that fails on master without the change too says nothing about the change. The change is committed with that stated, and CI judges it. `gd-8b79700958` stays `failed` in the ledger: no command reopens a failed delivery.
- **Bedrock refused the AWS account at 20:50 UTC.**
  - All 10 of that hour's calls, across all 5 models, failed with `ValidationException ... Error 002: Access to Bedrock models is not allowed for this account`. The 19:50 run had worked.
  - GAGOS cannot write until access is restored. That is the operator's account, so restoring it is his act.
  - Fixed on this branch: a call the provider refused no longer uses up its finding. Ten findings were marked attempted at 20:50, and they return when this merges.
- **Who writes what.** GAGOS writes its own work (fixes and tests) and opens its own PRs as GAGOS. I write the workshop it runs on, because GAGOS's checks allow only bounded one-file changes and execute nothing before review. That boundary is why GAGOS cannot yet build its own workshop.

## Evening of 2026-11-02 (branch `feat/gagos-first-tests`, off master `012716a3`)

- **The operator merged #579 and #580 at 15:19 UTC (squash `c2477622`, then `012716a3`) with only the chief review. Codex could not review: its usage limit (below).**
  - #580's merged code is the head I accepted, `4e0011b6`. GitHub's update merge `3da1711e` added only #579's HONEST_STATE. Codex reviewed #580's first head `93ff5bb2` and found three P2s. It has not reviewed the fixes; it reviews them on master after its reset, and anything it finds is fixed.
  - Codex has not reviewed #579's last commit `653ecab5` (the line on its limit).
- **GAGOS works every hour from 15:50 UTC (21:20 IST), on master's tip,** whenever the laptop is awake and the operator is logged in. Each batch makes up to 10 proposals from five Bedrock writers, 2 at a time, within $100 a month.
  - Until Codex's reset, each proposal gets the chief's review and then waits for Codex's. None is delivered.
  - Its work on master is still three lint rules. At the 02:50 UTC scan, 16 findings under them had not been attempted, so the first batch or two use them up.
- **This branch adds GAGOS's second kind of work: a first test for each frontend module that has none** (133 of 273). A test is executed only at delivery, after both reviews.
  - The live smoke cost about $0.13 over three runs. On the last, 1 of 4 tests passed the static checks, and I rejected it: its Retry test clicks while the child still throws.
  - Why the tests are weak: GAGOS's privacy filter masks long code identifiers, so the writers cannot see the names they test. That affects 35 of the 43 modules targeted, about 600 masked spans. Changing the egress filter is the operator's decision, with both reviews.
- **GAGOS's daily backend (the API on :8000 and the executor) has been down all day (found at 15:30 UTC).** GAGOS's hourly work does not need it and is unaffected.
  - D13 kept the machine quiet until 02:10 UTC. Since then the 15-minute watchdog has refused to start the backend 52 times, because Docker's engine is not running and the sandbox needs it. Ollama is up.
  - The watchdog also stood aside once, at 15:20 UTC, for a D13 run that had already ended. D13's quiet marker was never removed, and another process briefly reused its process id. I moved the marker aside (`quiet.json.d13-ended-2026-11-02`). The check trusts a process id alone; a fix should also compare the process's start time.
- **The backend is back (16:00 UTC).** At the operator's word I started Docker Desktop and ran `daily_backend.py up`. The API and the executor answer health checks (200), and 3 of 11 reflexes are ready, as before D13.
- **Codex is out of the review chain, by the operator's decision** ("forget codex now we both r available so that's enough"). On this branch, a GAGOS change is accepted when Claude Code accepts it, and the operator merges. A reject from Codex, if one is ever recorded, still rejects. GAGOS's hourly runs no longer ask Codex. The record of how often the two disagreed while both reviewed is kept.
  - My own code (tools, not GAGOS's work) now has no second machine reviewer. Its checks are its tests, CI, and the operator's merge.
- **GAGOS's first hourly batch ran at 15:50 UTC on master `012716a3`.** It made 10 proposals from 5 writers in 5 minutes, for about $0.11 (an estimate pitched high).
  - 6 passed the static checks. 4 were refused: Kimi K2.5 twice gave no code block, one did not parse, and one left a warning.
  - Of the 6, one could not be shown to a reviewer (the privacy filter would redact the file). I accepted 3 and rejected 2; both rejected ones also changed lines they were not asked to fix.
  - Nothing was delivered: master's code still needs Codex's acceptance too, until this branch merges.
- **This branch also lets GAGOS improve its backend and itself** ("capable of improving its both backend and frontend and itself"). Its work now includes ruff's F401 (unused import) and F841 (unused local) in tracked Python under `aios/` and `tools/`; at `7302fa9d` that is 24 findings.
  - GAGOS never changes the frozen security core (`aios/security/`) or any organ's production entrypoint, which would make that organ's evidence stale. 6 files with findings are excluded for that. Without the organ ledger it changes no Python.
  - A removed import that another module takes from this one is refused. Delivery checks Python by compiling it and running the tests that import it.
  - GAGOS already learns from refusals: each prompt carries the last reasons that kind of work was refused, by the checks or by a reviewer.
- **Master's CI on `012716a3` passed** (CI and CodeQL).
- **One of my rejections was wrong, caused by a bug in what the reviewer is shown (found at 17:30 UTC).** `gd-a9f57600cf` fixed two `catch (err)` warnings in CouncilServicesPanel.jsx and changed nothing else. I rejected it for changing class names, which it never touched.
  - The cause: a hidden value that appears on several lines gets one placeholder per line in the original, but the proposal was masked by value, giving every occurrence the same placeholder. The diff I was shown had 22 changed lines; the real change has 4. Nothing leaked: every review prompt is still checked by the privacy filter before it leaves the machine.
  - The fix on this branch: lines the proposal keeps are shown exactly as in the masked original. Re-run on the ledger, the reviewer is shown 4 changed lines for `gd-a9f57600cf`; my other rejections today stand on real changes (26 and 17 lines).
  - `review --again` lets a verdict given on wrong evidence be given again by a fresh session; the new verdict replaces the old one and its reason. I will run it for `gd-a9f57600cf` once this branch merges.
- **The 22:20 IST batch (16:50 UTC) found only 2 frontend findings left on master.** It made 1 proposal, which I rejected: it also changed test behaviour beyond the 3 lines asked. Master's lint work is nearly used up; this branch adds the Python and first-test work.
- **Still open:**
  - Wake timers in the power plan (the operator's setting).
  - The monthly probe stays red until 1 December, or until the operator runs it by hand.

## Later still on 2026-11-02 (branch `docs/honest-state-after-578`, off master `dd7aa102`)

- **The operator merged #577, #576 and #578.**
  - **#577** (07:52 UTC, squash `824782ca`): the organ re-gather. Its tree equals the head both reviewers accepted. Master's CI on it passed on all three systems, and the three evidence failures are gone.
  - **#576** (10:33 UTC, squash `98fa9708`): Dependabot's lucide-react bump, 1.64.0 to 1.65.0. Codex reviewed the package metadata and its CI passed.
  - **#578** (10:34 UTC, merge commit `dd7aa102`): GAGOS's check now matches a region's end case-sensitively, as ESLint does. **This closes the residual Codex found in #574, on master.** Both reviewers accepted it.
- **Codex's post-merge reviews are done.** `2f153fab` (#574) gave the residual above, now fixed. `47d5a97d` (#575) gave no new finding.
- **The organ evidence is still current at `dd7aa102`.** Neither later PR touches an organ's entrypoint, and the evidence tests pass at the tip.
- **GAGOS's next day is the first to run with the clerk fix and the full static check.** Its batch runs at the first hourly tick of the UTC day (00:50 UTC on 11-03, 06:20 IST) if the laptop is awake and the operator is logged in, or at the first tick after that. Today's ran at 02:50 UTC only because GAGOS stood aside for D13 until 02:10. Its hourly runner moves to master's tip by itself.
- **The operator corrected how GAGOS's work was scheduled.** "GAGOS will work 24/7 continously"; the interval he asked Codex and Claude Code to agree on was for their own review loop.
  - We had applied it to GAGOS's work: one batch of 2 proposals a day, and the whole day blocked while GAGOS's PR was open. In its life so far GAGOS has made 4 proposals and delivered 1 merged two-line change (#565), on 2 days of work.
  - **#580** (open, for both reviews) runs a batch of up to 10 every hour. An open PR holds back only delivery, and files GAGOS's unmerged work touches are left alone.
  - The `\GAGOS\daily` task may now wake the laptop (WakeToRun). This has no effect until wake timers are allowed in the power plan, which is off on AC and battery; that system setting is the operator's.
- **GAGOS's workforce, on #580 at the operator's word** ("$100 a month for AWS and codex s ready u start honestly"). Codex agreed the direction, with conditions; its first review of #580 found three P2s, all fixed on the PR.
  - Five Bedrock writers (Devstral 2, Qwen3 Coder Next, DeepSeek V3.2, Mistral Large 3, Kimi K2.5), 2 calls at a time. Work follows each writer's accepted record within one rule.
  - Every call first holds its worst case against $100 a month. The spend is an estimate pitched high, not AWS's bill, and it counts only GAGOS's work, not other Bedrock use through the gateway.
  - A live batch on a throwaway ledger: 5 findings to 5 writers in 2.5 minutes. 3 passed GAGOS's static checks and 2 were refused by them, for about $0.07.
  - Still limited: three lint rules. At GAGOS's 02:50 UTC scan, 16 findings under them had not been attempted; that day's 2 refusals stay attempted. 133 of 273 frontend modules have no test file of the same name. The superbrain's 212 port-managed files stay excluded until the lab/product port is decided.
- **Master's CI on `dd7aa102` passed:** CI, Nightly and CodeQL.
- **Codex cannot review until 5 November (found at 14:45 UTC).** Its last action was at 11:39 UTC. Every hourly check since 12:38 UTC failed at once on its ChatGPT usage limit, which resets on 11-05 at 17:49 local time (12:19 UTC).
  - #580 and #579 wait for its review. Their CI passed (19 checks, 2 skipped, on each). Nothing merges on one review.
  - GAGOS's own Codex reviewer uses the same account, so until the reset no proposal can be accepted by both reviewers, and nothing is delivered. Until #580 merges, GAGOS runs one batch a day.
  - Waiting for the reset or buying Codex credits is the operator's call.
- **Still open:**
  - The monthly probe stays red until it runs on 1 December, or until the operator runs it by hand.

## Later on 2026-11-02 (branch `evidence/after-575`, off master `1eb39c27`)

- **The operator merged #571 to #575** (06:14 to 06:17 UTC). Master `1eb39c27` is `c6c54652` plus exactly those five PRs' changes. I checked this: each pushed head's own patch reverse-applies on `1eb39c27`, and the changed files match.
  - **#571:** the D13 write-up: not met, harm not detected.
  - **#572:** GAGOS's clerk can now summarise a disagreement. Tomorrow's day is the first to use it.
  - **#573:** torch is held at 2.14.1, so the macOS suite completes again.
  - **#574 fixes the P3 from #567 for every case found before the merge.** GAGOS's static check now aligns everything a disable comment silences line by line, and lints once more with inline configuration off. It reads directives only from the comments ESLint's parser found.
    - **Codex's post-merge review found one residual, still open on master.** The check reads a region's end without regard to case, so an uppercase `/* ESLINT-ENABLE rule */` ends protection, though ESLint (case-sensitive) ignores it. A fix follows in its own PR.
  - **#575:** the probe's six NO VERDICTs were an order-dependent test, now fixed. S17 is killed by a test that reaches the fallback, the pre-route site has its own mutation (S26), and a failed control now says which test failed.
  - **Two commits were merged before Codex re-reviewed them:** #574's `2f153fab` (directives read from real comments) and #575's `47d5a97d` (the failing test kept first in a report). Codex's earlier findings on both are fixed by those commits. Codex reviews them on master after the fact.
- **Organs re-gathered at master's tip `1eb39c27`** (this branch), as #559 did. The PR adds evidence and docs only.
  - 48 proofs, all passed (Docker off, as at the last gather).
  - 42 organs re-attached, replacing the 42 rows that cited `8e4b5069be65`, which the squash of #566 had orphaned.
  - The 5 frozen-spine organs are untouched: they are the operator's.
  - Master's three evidence tests pass on this branch, as do the 17 test files that read the ledger, the organ doc or the manifest.
- **Still open:**
  - Codex's post-merge review of `2f153fab` and `47d5a97d`.
  - Master's CI on the merges, and on this PR once it merges.
  - **The monthly "Learning guards" probe stays red until it runs again.** Its next scheduled run is 1 December. A manual run (six shards, up to 5 hours of runner time) is the operator's call.

## State on 2026-11-02 (branch `docs/d13-judged`, off master `c6c54652`)

- **D13 is judged: not met, and harm not detected** (`docs/learning/PAYOFF_D13_RESULT.md`). Its fourth launch ran to the end (2026-10-31 17:52 UTC to 11-02 02:10 UTC, run `20261031T175215-bbaba5ab`).
  - With only lessons about the named code, the local student earned 33 of 141 with lessons and 40 of 141 without. That is 5 targets better and 9 worse (Holm p = 0.48).
  - Against a placebo of the same size: 4 better and 6 worse (p = 0.85). Both members point the wrong way.
  - 38 of 85 targets are not comparable because of 420 s timeouts. The lesson-carrying arms timed out more (ON 39 and PLACEBO 39 of 255 samples, OFF 29); their prompts are about 1.8 times longer. Only 14 targets were discordant, against about 30 planned.
  - Three judged families (Phase 8, D12, D13) have now found no benefit from lessons prepended to a prompt. The usefulness gate reads D13 and stays FAIL. D14 (real use) continues.
  - The trail, the verdict and a test that recomputes the verdict from the trail are committed on this branch.
- **The operator merged both #568 and #569** (02:21 UTC). The merged trees are the reviewed ones: #568's equals its reviewed head, and #569 differs from its reviewed head only by #568's rebase.
  - **#568 went in unfixed, so master could not install:** pydantic 2.14.2 needs pydantic-core 2.50.2, and master pinned 2.50.1. Every backend CI job died at `pip install`.
  - **#570 fixed it.** It moves the core to 2.50.2 and the Dependabot ignore to `>2.50.2`.
    - I wrote it, at the operator's word ("start post D13 processes right now"). The operator merged it at 02:44 UTC as a merge commit (`c6c54652`), before Codex's review and before Windows CI finished. Its tree is the head I wrote (`fe0b7e3c`).
  - **#570's CI was the first real test of #568's other bumps** (torch 2.15.0, transformers 5.22.0, starlette 1.10.0, among others):
    - Ubuntu ran the whole suite (89% coverage) and failed only master's three evidence tests;
    - **macOS crashes**: a segmentation fault after 1,008 tests (about 11%), in both runs. It is new with #568: the macOS runs before it failed only the evidence tests;
    - Windows was still running.
  - **The macOS crash tracks torch 2.15.0.** There is one clean run so far on 2.14.1, so this is strong evidence, not a proven cause.
    - It crashed in 4 of 4 macOS runs (#570 and #571), inside a BERT forward pass (transformers under `torch.nn`).
    - The same tree with only torch at 2.14.1 ran the whole macOS suite and failed only the three evidence tests (run 41379538054).
    - **#573** holds torch at 2.14.1 and makes Dependabot ignore torch from 2.15.0 on.
  - #571's own CI adds nothing new. Ubuntu and Windows fail only the three evidence tests, and macOS crashes as above.
  - The local `.venv` still has the versions from before #568.
- **GAGOS's first real day ran** (02:50 UTC, master `c6c54652`). Nothing reached the reviewers.
  - It found 62 warnings in 298 editable frontend files; 16 were in the rules it may fix.
  - **Its own gates refused both of its proposals:** one did not parse, and one added an undefined `err` (ESLint no-undef). The gates did their job.
  - **Its clerk failed on a real bug.** The local model summarised the open 10-30 disagreement correctly (a summary and a crux). The local workforce service refused the answer as "Extra fields rejected", because GAGOS handed it a JSON Schema where the service reads field names. Its tests had faked the whole service.
    - **#572** fixes it, with a test that runs the real service. That test fails on the old code with the production error.
    - The failed record stays in GAGOS's ledger as it happened.
- **Still open, in order:** the P3 fix, the mutation-probe fix, then the organ re-gather at master's tip (last, which turns master's CI green, except the macOS crash if it is still open then).

## Later on 2026-11-01 (branch `chore/organs-after-567`, off master `bead0108`)

- **#567 is merged** (squash, `bead0108`; GitHub records 09:04 UTC). The operator merged it.
  - Codex's acceptance was scoped: the implementation fixes at `0faf61f1` and the doc follow-ups after it. It did not accept green CI, the evidence, or full merge qualification. CI and the evidence remained red.
  - Codex checked that the merged tree is identical to the reviewed head `fc38dfce`.
  - GAGOS's hourly task fetches origin/master into its own worktree (`C:\gdw`) on every run. So its first day, after D13, runs #567's code: publication bound to the exact commit, the day's claim kept, an App that fails closed.
- **Still open on master (P3, tracked):** a bounded disable/enable region can hide a warning that a proposal moved into it.
  - Until the fix lands, the two reviewers are the only check for it.
  - The fix is planned (above) with no objection from Codex. It is built after D13, with real-ESLint tests.
- **Master's CI stays red on the three organ-evidence tests**, as expected. The re-gather was never on #567's branch, so its squash orphaned nothing new.
- **The monthly "Learning guards" mutation probe is newly red on master** (run 41303837576, 11:52 UTC; found by Codex's hourly check, then confirmed by me in the CI log and the source).
  - It classified 704 mutations: 675 killed, 22 inert, 6 with no verdict, and 1 that survived.
  - **The survivor, `4c2:S17`, is a real coverage gap. It is not a demonstrated leak:** today's code passes the caller's identity at both sites.
    - The mutation makes the turn's fallback reflex check match as no one.
    - Since reflexes are matched before routing (10-25), a fresh turn is matched earlier (`generate_pipeline.py` line 264). The fallback at line 791 runs only when that earlier check was not performed (an approval resume, or no cerebellum at that stage), so its test never reaches it.
    - The earlier site, the one every fresh turn uses, has no mutation in the catalogue at all.
    - The fix: a mutation for the earlier site, and a test that drives an approval resume through the fallback. The test must show that it reaches the fallback and that it kills S17 (Codex).
  - **No verdict ×6:** each shard has one, all `self_model_handler`, all judged by the same three test files.
    - Their tests failed on the unmutated code at the closing control, so none counts as a kill.
    - The probe discards pytest's output, so the cause is not recorded.
    - My hypothesis, not yet tested: those three files fail when run on their own. The baseline runs them in batches of 40 with other tests, which would explain why it passed.
  - The plan, after D13 (no test runs while it runs):
    - reproduce the three-file set at `bead0108`;
    - keep the tail of pytest's output for a failed control;
    - fix the cause;
    - add the S17 test and the new mutation.
- **Dependabot opened #568 (Python) and #569 (frontend) late on 11-01. #568 cannot install** (found by Codex's hourly review, then confirmed by me).
  - It bumps pydantic to 2.14.2 but leaves `pydantic_core` at 2.50.1. PyPI says 2.14.2 requires `pydantic-core==2.50.2`, and every backend job died at `pip install` with ResolutionImpossible (Ubuntu job 124987617897).
  - This is the #471 case that the comments in `requirements.txt` and `.github/dependabot.yml` already describe. The fix is to move the core to 2.50.2, update both comments, and raise the ignore bound to `>2.50.2`.
  - Its other bumps (torch 2.15.0, transformers 5.22.0, starlette 1.10.0 among them) are unverified until a fixed head installs. It must not merge as it stands.
  - Neither reviewer writes the fix; it waits until after D13.
  - #569 changes only `package.json` and its lockfile. Both reviewers accept it, scoped to that change. Its frontend jobs pass. Its backend jobs fail
    only on master's three evidence tests (Codex compared all six jobs; I checked Ubuntu). It is the operator's to merge, and merging it does not touch D13.
- **D13's timeouts are rising** (as of 22:24 UTC: 77 of 85 targets, 33 not comparable). Not-comparable targets were 9 of the first 30, then 20 of the next 31. The 420 s model timeouts fall on every arm, not on one.
- **A correction to my own advice:** I asked the operator for a merge commit, but master requires linear history. This was already recorded on 2026-09-25, and I repeated the mistake.
  - The working remedy is #559's: gather the evidence on a checkout exactly at master's tip, so it cites a commit on master, then squash as usual.
  - That is the plan after D13, on this branch.

## State on 2026-11-01 (branch `fix/gagos-daily-after-566`, off master `ad46f211`)

- **#566, GAGOS's own day, is merged** (squash, `ad46f211`). The loop's code is on master.
  - GAGOS's hourly task will run it, but only after D13 ends: until then it stands aside.
  - The operator merged #566 before Codex's second round, which its ChatGPT usage limit had cut off. That round runs after the reset as a post-merge review. Anything it finds is fixed before GAGOS's first day of its own.
- **Codex's post-merge review of #566 (2026-11-01): changes needed. All of it is real and all of it is fixed on this branch.** Codex reproduced each defect against the merged code with fakes; nothing live was touched.
  - **P1, publication:** an old PR could certify new, unpushed work. Publishing looked up "a PR for this branch" and took any URL, so later work on the same branch name could be marked delivered against an earlier, merged PR. Now delivery is bound to the exact commit: GAGOS pushes that commit (no force), and only a PR holding that commit counts. A PR at another commit refuses, and the day waits. A later delivery the same day gets its own branch.
  - **P1, merging:** "the App cannot merge" was not true. Its `contents: write` token could merge a PR whose checks pass: master requires checks, not reviews, and restricts no pusher. GAGOS has no code that merges (a test now pins that), and only the operator merges; the PR footer and the App's docstring now say so. Making it a GitHub lock is his repository setting to choose.
  - **P2, the day's claim:** a "blocked" record could erase it. Recording a blocked hour replaced the day's `ran` row, which let a second batch run the same UTC day. Codex reproduced this with PR states MERGED, UNKNOWN, MERGED. The claim is now its own row, written once; earlier ledgers keep theirs.
  - **P2, the port manifest:** a missing manifest made port-owned product files editable. Now a missing, unreadable or wrongly shaped manifest owns the whole port root.
  - **P2, Claude's reviewer:** a nonzero exit from Claude's process could still count as a verdict. It no longer does; the proposal keeps waiting.
  - **P2, the eye:** a failed screenshot deleted the previous one. It now captures to its own file and replaces the old one only on success.
  - **P3, the eye's URL:** text that Chrome would read as its own switch could be passed as the URL. Only http(s) pages are accepted now.
  - **P3, disable comments:** a changed comment got past the check, because it counted them. Every disable line must now be unchanged.
  - **Hardening:** a stored App that cannot act, or a key store that cannot be read, now stops publication. It no longer falls back to the operator's login.
  - **Checks:** 85 tests pass in the GAGOS test files, plus `test_gateway_enforcement`. Ruff, format and the bandit budget are clean. The full backend suite was not run locally, because D13 keeps the machine quiet; CI runs it.
- **Codex reviewed these fixes (PR #567 at `1bb3b93f`): changes needed, three more. All three are fixed.** Codex confirmed the publication and day-claim fixes against its own reproductions.
  - **A partly stored App still fell back to the operator's login** (for example, an id and slug but no private key). Now a partly stored App, or any failure of a stored one, stops publication. Only a wholly absent App uses his login.
  - **Chrome's exit code was ignored.** A failing Chrome that wrote partial bytes replaced the previous screenshot. Now it must exit 0 too.
  - **An unchanged disable comment could be retargeted** by deleting the line under it. Each disable comment is now bound to the line it protects.
  - 93 tests pass, plus 1 skipped; ruff, format and the bandit budget are clean.
- **Codex accepted the corrections at `0faf61f1`** (scoped acceptance, not merge authority). Its reproductions pass for all three, and its earlier ones still pass.
  - **Still open (P3, tracked):** the bounded disable/enable region case. A warning can be moved into an existing `/* eslint-disable rule */ … /* eslint-enable rule */` region; the static check passes it, and only the two reviewers would catch it. My earlier claim that a region could not hide a finding's rule was wrong for bounded regions.
  - ~~The planned fix: lint once more with inline configuration off, and require the finding's rule count to fall by exactly the warnings fixed.~~ Codex showed that counts cannot work: move a warning into the region and delete another, and the count still falls.
  - Codex's second advisory (06:42 UTC) showed that matching suppressed warnings by rule and message cannot work either. Function A's `x` inside a region can be deleted while function B's `x` moves in; the message is the same, but the binding is not.
  - **The revised plan (after D13):** align the lines of before and after.
    - Every line a disable comment covers, and every disable or enable line itself, must be an unchanged line in both versions. It must pair with a line the same comment covers on the other side.
    - So a proposal cannot edit, add, delete or move code into or out of anything silenced. It is refused instead.
    - A second lint with inline configuration off must then show no suppressed warning that the aligned before-line did not already have.
    - Codex's cases become real-ESLint tests.
- **CI on #567:** the backend jobs (macOS, Ubuntu, Windows) fail on exactly the three organ-evidence tests that fail on master, citing the orphaned `8e4b5069be65`; nothing else fails. Codex read the same logs. The re-gather after D13 makes them current.
- **Codex now checks its inbox hourly by itself:** a Windows task `\Codex\GAGOS hourly review`, at his authorisation. It sends every review straight to Claude Code's inbox, so he no longer relays messages.
- **Master's CI is red on three organ-evidence tests**, from 31 Oct (`75605cec`, #565's merge) onward.
  - Green organs cite commits that squash merges discarded: #564's, and now #566's.
  - Nothing else failed.
  - The fix is a re-gather, as #567's last commit, which the operator merges with a merge commit (a squash would orphan it again). It waits until D13 ends, because an evidence run is CPU-heavy and D13's registration keeps the machine quiet.
- **D13's fourth launch is running** (since 2026-10-31 17:52 UTC), slowly. The first hour reached 2 of 85 targets, with 4 of 14 attempts timing out at 420 s. By 2026-11-01 03:08 UTC it had reached 30 of 85 targets: 261 attempts, 30 timed out, and 9 targets not comparable (an arm never reached the model; these are counted, never scored). By 06:51 UTC: 39 of 85 targets, 343 attempts, 40 timed out, 14 not comparable. At this pace it ends early on 2 November.
  - At the operator's word, Chrome, Edge and WSL were shut at about 18:55 UTC, raising available memory from 1.5 to 2.7 GB. This is recorded for D13's result.

## State on 2026-10-31 (branch `feat/gagos-daily-review`, off master `af233f66`)

- **GAGOS's first own PR is merged: #565, merged by the operator with a merge commit** (`75605cec`). This is D14's first merged improvement.
  - The change removes an unused import in `BudgetMicroBar.jsx`.
  - GAGOS's commit `aa01b7ac` is on master as GAGOS authored it. Its trailers name who proposed it and its reviewers, Codex and Claude Code.
- **Codex reviewed this branch (#566) and requested changes: six real findings, all fixed in `554bd53d`.**
  - Its second round was cut off by its ChatGPT usage limit; it resets 2026-11-01 03:25 local.
  - The same limit applies to GAGOS's daily loop. When Codex cannot review, a proposal waits; it never ships on one review.
- **#564 was merged by squash** (`af233f66`). Its branch-tip organ evidence was orphaned; it is re-gathered at this branch's tip.
- **GAGOS starts with Windows, by his request (10-30).** Windows Update is never paused, because Defender needs it. GAGOS survives the restarts instead.
  - Two tasks run under his user:
    - `\GAGOS\backend`, at logon and every 15 minutes, runs `daily_backend.py up`, which is idempotent;
    - `\GAGOS\daily`, at logon and every hour, runs GAGOS's day on merged master code only.
  - Its first run, 2026-10-30 09:50 UTC, started the backend by itself (exit 0).
  - After an update restart they start at sign-in. He turned on "Use my sign-in info to automatically finish setting up after an update" (10-31), so Windows signs him in by itself after an update, and GAGOS comes back with no one at the keyboard.
- **His steps are all done (10-31):**
  - GAGOS's GitHub App `gagos-swap821` is created and installed on `swap821/ai-editor`, with its key in his keystore. GAGOS's next PR opens under its own name.
  - The clerk's `qwen3.5:9b` is granted `summarise_disagreement`, its first real role.
  - The Bedrock key is in GAGOS's keystore.
  - Automatic sign-in after updates is on.
- **A judged run can keep the machine to itself.** While a quiet marker names a live process, both tasks stand aside. When that process ends, or a restart ends it, GAGOS resumes by itself.
- **D13: the operator asked for it again, honestly (10-30), after D14 had said it would not be re-run.** A dated correction is under D14.
  - Its fourth launch waits for at least 6 GB of available memory, because a starved 9B is what spoiled the second attempt.
  - At 16:14 UTC 3.0 GB of 15.4 was available: Windows services 2.3 GB, Edge 1.0 GB, the WSL VM 1.0 GB.
  - **D13 is running since 17:52 UTC.**
    - It launched once 7.0 GB was available, with no heavy job running.
    - Harness `e6e8d668`, store `90c009d9` / `f95c7d7d` verified, argv identical to all three earlier attempts, 85 targets.
    - Log: `C:\d13out\judged-local`. GAGOS's tasks stand aside until it ends.
- **Keys: GAGOS's jobs read only its keystore, never a file.**
  - The operator stored the Bedrock key there on 10-31. GAGOS's first call with it went through the gateway (entrance `route`), and Mistral Large 3 answered.
  - Nothing reads the old key file any more.
- **Three actions were refused by Claude Code's own permission check, each correctly the operator's:**
  - writing the key into the keystore ("Secret-Store Writes");
  - stopping Docker and WSL ("Interfere With Workloads");
  - registering the tasks the first time ("Unauthorized Persistence"). They were registered on his explicit request.
- **This branch also adds:**
  - GAGOS's daily direction from him (`gagos_daily.py direct`);
  - its own eye, its own Chrome (`tools/gagos_eye.py`). It sees, but does not judge yet;
  - GitHub App support. Creating the App is his act;
  - credits for the models and the clerk;
  - `daily`, under the rules agreed with Codex.

## State on 2026-10-30 (the operator's daily backend, master `f6206755`)

- **Three reflexes now serve his daily turns, from three real modules** (`docs/learning/daily_reflexes_2026-10-30/`).
  - The backend was started by `tools/daily_backend.py up`, with turns bound to `work/ai-editor` and routing local only.
  - **The gateway reflex survives a restart.** Playbook 17 served after the restart: 8 of 8 checks, zero model calls. `check` had predicted it ready.
  - **Two new reflexes**, each earned, activated by him, compiled and serving with zero model calls (12 of 12 checks each): playbook 18 for `tests/test_failover.py` and playbook 19 for `tests/test_privacy_filter.py`.
  - `check` now reports 3 of 11 reflexes ready.
- **The local model derails on simple turns.** In 5 of 14 model-answered turns, `qwen2.5-coder:7b` repeated a verify that had already passed, and the loop guard stopped the turn.
- **A defect: those stopped turns were still learned.** The library recorded each one as a successful two-step arc ("verify; verify").
  - One of these, `arc-c46f6a5f…`, reached review-ready from stopped turns alone.
  - It was never activated, and nothing becomes a reflex without his activation, so no harm was done. The fix is a separate PR.
- **The agent's proof script had a bug that cost him three approvals.** It followed the wrong arc. It is fixed, and the evidence README records it.
- **An inspection of the memory and learning system, measured on his store, read-only.** He asked what is stopping usefulness.
  - **No real use.** User turns: June 743, July 347, August 0, September 0, October 21, and all 21 in October were proof scripts. The last ordinary turn was on 2026-07-10. His real work happens in other tools.
  - **What it holds came from its own harnesses.**
    - 228 lessons, every one from practice or prover tasks. Only 5 have a recorded outcome.
    - 95 facts, all prover debris. 94 were never approved, and none is about him.
    - 232 of 240 semantic memories predate signing, so recall refuses them.
  - **A reflex fires only on the exact command string.** It matched `run pytest ai-editor/tests/test_gateway_enforcement.py -q`, but not "run the gateway enforcement tests".
  - **Measured payoff:** D12 was not met (12 better against 18 worse, p = 0.21). D13 has no verdict.
  - **The conclusion:** the machinery works, but usefulness can only come from real, recurring use. Proving more of the mechanism will not supply that.

## Later on 2026-10-30: D13 stopped; GAGOS starts real daily work on its own frontend (branch `feat/frontend-daily-repair`, off master `2103fdae`)

- **D13 was stopped at the operator's word, with no verdict.** 06:54 UTC, 5 of 85 targets, 41 graded attempts, 5 model errors (420 s timeouts), no trail written. Kept as `C:\d13out\stopped-by-operator-20261030`. It will not be re-run.
- **D14 is registered** (`docs/learning/PAYOFF_PREREGISTRATION.md`): the payoff is now measured on real use, GAGOS's daily work on its own frontend, not on a harness.
  - A frontier model proposes, and static checks run unattended.
  - Two independent reviewers decide: Codex and Claude Code. A change ships only if both accept, in one daily PR that CI gates and he merges.
  - He decided not to approve every diff himself. Reviewing them is the agents' daily job.
- **Built on this branch, tested, not yet live:**
  - the unused-import scanner and its registered repair, run by both executors;
  - staged copies that skip `node_modules`;
  - a repair preview showing the exact diff;
  - a step-by-step repair flow in the Maintenance panel.
- **A gap closed: the promotion check used to wave frontend files through.** A target set with no `.py` file passed with "no Python targets", so nothing was checked. A frontend target must now parse, have no ESLint error and pass the tests that import it. A missing toolchain fails the check.
- **The deterministic supply is small.** Unused imports are in 11 of 504 files. 9 of those are owned by the lab-to-product port and excluded, so 2 are repairable. The daily supply is ESLint's ~124 warnings, which needs the frontier proposer (next PR).
- **Codex reviews with his configured model, GPT-6.1 sol (his choice).** In the morning it was refused non-interactively for a ChatGPT-account login. By the afternoon, after his setup, it reviewed non-interactively with GPT-6.1 sol.
  - The loop records the model behind every Codex verdict.
  - When Codex cannot review, the proposal waits. It never ships on one review.
- **The first real day of D14, the same afternoon.**
  - The loop's code is on branch `feat/gagos-daily-review`; its PR follows this one.
  - **The proposals.** GAGOS made 2 proposals, using Mistral Large 3 on Bedrock through the one gateway, bound to his identity and constitution. Both passed the unattended checks.
  - **One change delivered.** In `BudgetMicroBar.jsx` it removes the unused default `React` import. Codex (GPT-6.1 sol) and Claude Code (Opus 5.5) both accepted it. It was re-checked on master and delivered as #565, the first daily PR.
  - **One change rejected.** Removing `React` from the same file's test was rejected by Codex: nothing it was shown established the automatic JSX runtime. Claude Code accepted it.
    - That is the first recorded disagreement. A change ships only if both accept, so it did not ship.
    - The reviewers are now shown that fact, read from `tsconfig.json`.
  - **The privacy filter would have changed most files.** Bedrock's filter would alter 264 of the 298 editable files, false positives included, so the proposer would have been working from a different file.
    - Instead, what GAGOS's egress scrubbers would redact is masked locally and restored exactly. With masking, 276 files can be sent unaltered. The other 22 are refused, not sent.
- **Roles (his words): GAGOS is the workforce.**
  - It makes its own PRs for its own work. Claude Code is chief reviewer and Codex is a reviewer; both must accept.
  - He comes in as CEO, on his own time.
  - #565's commit was re-authored as GAGOS. The frontier model that wrote a change is credited as its co-author, and the reviewers are named with their models.
- **The loop interval was agreed with Codex,** after asking it (GPT-6.1 sol):
  - events wake the loop, with a 60-minute fallback;
  - at most one batch of at most 2 proposals per UTC day, rejections included;
  - no batch while GAGOS's previous PR is open; blocked days are recorded and never caught up.
- **Built on branch `feat/gagos-daily-review`, not live:**
  - `tools/gagos_daily.py daily`, GAGOS's whole day under those rules;
  - its own GitHub App support;
  - the clerk's first real job: summarising, locally, each disagreement between the reviewers;
  - an hourly starter that runs only code merged on master, in GAGOS's own worktree.
- **What GAGOS cannot do yet, honestly.** It isn't 24/7: it's a laptop with no supervisor. It doesn't improve itself beyond what a checker can prove: today, 3 lint rules. And it can't judge a UI: there is no visual check.
- **Waiting on him, each his own act:**
  - creating and installing GAGOS's GitHub App (`tools/gagos_github_app.py create`);
  - registering the hourly task. Claude Code's request to create it was blocked as unauthorized persistence, which is right: it is his to set up;
  - admitting a clerk model (`python -m aios clerk approve <model>`). Until then, the clerk's refusals are recorded;
  - storing the Bedrock key (`gagos keys set AWS_BEARER_TOKEN_BEDROCK`).
- **Tests still read his user-wide `AIOS_ROUTER_CLOUD_TASKS`.** Two tests fail on this laptop because of it, and pass without it. This finding is already recorded, and is still open.

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
