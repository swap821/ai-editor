# Learning payoff — pre-registration

*Registered 2026-09-25, before any official run of `tools/learning_payoff.py`.
Every run records the sha256 of this file (`preregistration_sha256` in
`.aios/audit/learning-payoff.jsonl`). A result produced under a different hash
was produced under a different hypothesis, and says so.*

## Why this exists

The payoff benchmark is the number the learning loop is judged by. A judged
number whose hypothesis, sample, model or success line can be chosen after the
results are visible is not a measurement — it is a narrative. Everything below
is fixed now. Changing any of it is allowed only through the **Deviations**
section, dated, with a reason, **before** the run it affects.

## The question

Does what this system remembers make its model measurably better at real work
it has **not** practised before?

## Design

- **Task:** pin the behaviour of a real function in this repository with a
  pytest test, graded by `grade_pin_test` (passes clean, fails when the
  function is mutated, source untouched, suite still green). Unchanged.
- **Arms:** OFF = the production task prompt; ON = the same prompt with
  recalled lessons and verified skills prepended through the production recall
  path. Arm order alternates by target index.
- **Pairing:** each target is its own control (ON vs OFF, same model, same
  corpus commit).
- **Before/after:** the **Phase 0 baseline** run (before any hardening) and the
  **Phase 8 judged** run use the **same frozen target list** and the same model.
  The Phase 0 run's chosen targets are exported to
  `docs/learning/payoff_targets_phase0.txt` and committed; Phase 8 runs with
  `--target-labels docs/learning/payoff_targets_phase0.txt`.

## Fixed parameters

| Parameter | Value |
|---|---|
| Model (primary, judged) | `ollama.qwen2.5-coder:7b` — the product's default local model |
| Model (secondary, descriptive only) | the strongest available cloud model, if credentials are present; never the judged number |
| Targets | **30**, chosen by `select_targets` (alternating never-practised / practised) at the Phase 0 run, then frozen |
| Measured code | `--ref origin/master` at the time of the run (fetched first); corpus sha recorded |
| Model timeout | 420 s |
| Grader | `tools/self_corpus_grading.py::grade_pin_test`, positive control (`run_self_check`) required first |

## Hypotheses and tests

All tests are **exact two-sided McNemar** on discordant pairs, α = 0.05.

- **H1 — transfer (THE JUDGED NUMBER).** On NOVEL pairs (no recalled item
  recorded on that target), ON earns more often than OFF.
  *Met* iff ON-only > OFF-only **and** p < 0.05.
- **H2 — no harm.** On ALL comparable pairs, ON does not earn significantly
  *less* often than OFF. *Violated* iff OFF-only > ON-only and p < 0.05.
- **H3 — hardening preserves utility.** Across Phase 0 → Phase 8, on the same
  frozen targets, the ON arm's earned outcome does not drop significantly
  (McNemar over the ON arm's paired outcomes between the two runs).
  *Violated* iff Phase-0-only > Phase-8-only and p < 0.05.

SEEN-pair results are reported as context and carry no test.

## Exclusions (decided now)

- A pair is **not comparable** — excluded from every test, and counted — when
  recall returned nothing (identical prompts) or either arm never reached the
  model. Not-comparable pairs are never scored as losses.
- A run refused by containment, the positive control, the hollow-suite guard,
  the memory-store guard or the corpus-restore guard (added by D1) produces
  **no number**. It is re-run in full; the refusal is kept in the trail. There
  is no partial result.

## Stopping rule

One analysis per run, at the fixed N. No interim looks, no extending N because
a result is close, no re-running because a result is disliked. A re-run is
permitted **only** after a refusal listed above, and the reason is recorded.

## What each outcome means

| Outcome | Reported as |
|---|---|
| H1 met, H2 not violated | Memory helps on new work. |
| H1 not met, direction positive | A direction, not a finding — reported as such. |
| H1 not met, no discordant pairs | No measurable difference. A result, not a failure to measure. |
| H2 violated | **Memory hurts.** The most important possible result; it is not explained away. |
| NOVEL has no comparable pairs | No judged number this run — recall had nothing relevant to transfer. |

## What this does not claim

Recall channels exercised: lessons and verified skills only — not semantic
memory, facts or the self-model. Recall is prepended, so a content effect is not
separated from a prompt-length effect. A 7B local model's behaviour is not a
frontier model's. These limits travel with every number.

## Deviations

*Each entry: date, what changed, why, and which run it applies to — recorded
before that run.*

### D1 — 2026-09-25 — the first run is not the baseline; arms are isolated; targets frozen

**Applies to:** the Phase 0 baseline re-run and every later run, Phase 8 included.

**What happened.** The first official run, `20260925T045128-40a08711`
(corpus `53eb1f0c`, this file's sha256 `8a432651…`), completed:
30 attempted, 28 comparable. NOVEL: ON earned 2/26, OFF 1/26, ON-only 2,
OFF-only 1, exact McNemar p = 1.00. **H1 not met, H2 not violated.** That result
is reported here and its trail row is committed
(`docs/learning/payoff_phase0_run1_trail.json`). It is not discarded.

**Why it is not the baseline.** The instrument was broken for most of it. The
corpus was never reset between arms: `run_arm` deleted only the test file it
wrote. At arm 23 a model-written test for `load_ledger` created
`temp_ledger.json` in the corpus root, and later tests added three more files.
None was ever removed. Because `source_is_untouched` grades `git status` over
the whole corpus, **every arm from 23 to 60 was rejected for files an earlier
arm left behind.** That is 37 of 60 arms and 19 of 30 pairs. At least one arm
whose own test passed clean (`hostname_resolves_only_to_loopback`, OFF) was
rejected for nothing but that. Those pairs could not produce a discordance, so
they inflate the denominator of a comparison they took no part in.

On the 11 pairs graded before the contamination (arms 1–22), the result is the
same, 2 ON-only against 1 OFF-only. The conclusion "no measurable transfer" does
not depend on the defect. The baseline must still come from a working
instrument, or Phase 8 is compared against an artefact.

**What changed (harness, not hypothesis).** `restore_pristine` returns the
corpus to its committed state before every arm (`git checkout -- .` and
`git clean -fd`, keeping ignored build artefacts) and then verifies it. **A
corpus that cannot be restored refuses the run.** That refusal joins the
exclusions list above: it produces no number, and the run is repeated in full.
The grading rule is unchanged: an arm whose own test litters the tree is still
rejected, but it can no longer be rejected for another arm's.

**What stays fixed.** The re-run uses the 30 targets run 1 selected, in the same
order, frozen in `docs/learning/payoff_targets_phase0.txt` and passed with
`--target-labels`. They were chosen before any arm was graded, since selection
reads practice history and never outcomes. Model, timeout, test, α and
exclusions are unchanged.

**Operational note.** Two of run 1's 30 pairs were excluded because Ollama timed
out at 420 s. Both ran while the same machine was running a large test suite,
which very likely caused it. The re-run runs with no concurrent heavy load.
Like run 1, it executes from a detached worktree of the harness commit, with a
copy of `data/aios_memory.db` whose `store_fingerprint` equals the live store's.

### D2 — 2026-09-25 — restore removes ignored paths too; D1's timeout attribution was wrong

**Applies to:** every run after the Phase 0 baseline, Phase 8 included.
Recorded after the baseline finished and before any other run.

**The Phase 0 baseline** is run `20260925T085914-44216455` (harness `0feaf5f9`,
corpus `53eb1f0c`, this file's sha256 `bca5d2fd…`, the 30 frozen targets). Trail:
`docs/learning/payoff_phase0_baseline_trail.json`. Result:
`docs/learning/PAYOFF_PHASE0_RESULT.md`.

**What changed.** An adversarial review found that D1's `restore_pristine` ran
`git clean -fd`, which never removes a gitignored path, and `git status`, which
never reports one. The grader excuses only `__pycache__`, `.pytest_cache`,
`*.pyc` and `.coverage`, while `.gitignore` hides `data/`, `.aios/`,
`node_modules/` and more. A model's test writing under an ignored path would
therefore have carried into later arms invisibly to both checks. From this
entry on, restore runs `git clean -fdx` and verifies with `--ignored`.

**Audit of the baseline, which ran with `clean -fd`.** Could ignored-path
litter have touched it? Its per-arm reasons, in execution order:

- "Source outside tests/ was modified" appears on exactly three arms (23, 24,
  32). Each names a file that arm's own test wrote (`temp_ledger.json`, then a
  different `test_ledger.json`, then `test_data/attestation.json`). None
  recurs, so D1's restore worked.
- No arm failed the guard suite. Every one of the 50 rejections includes
  "clean run not green", meaning the model's own test failed against correct
  code, which litter cannot cause.
- The arm run 1 rejected solely for leftovers
  (`hostname_resolves_only_to_loopback`, OFF) earned.

Nothing in the baseline is explained by leftovers, so it stands. Phase 8's
stricter restore can remove contamination but cannot add any.

**Correction to D1's operational note.** D1 attributed run 1's two
non-comparable pairs to concurrent load. The baseline ran with no concurrent
heavy load, and **the same two targets** (`normalize_command`,
`is_loopback_http_url`) timed out at 420 s again: three arms across the two.
The timeouts belong to those targets under this model, not to the machine.
They remain excluded as not comparable, exactly as the exclusions rule says.

### D3 — 2026-09-27 — the ON arm recalls skills through the live slot

**Applies to:** every run after this entry, Phase 8 included. It was recorded
before any run under it, and **by operator decision** ("Redefine now, record
deviations", 2026-09-27). The alternative recorded against it was to keep the
legacy store until the Phase 2 hard switch, to preserve the pairing.

**What changed.**
- The ON arm used to recall skills through a `SkillMemory` of its own, which is
  the legacy `procedural_skills` store.
- It now recalls through `live_skills_slot()`: the `skills` slot production
  builds for the configured `AIOS_SKILL_STORE_MODE`.
  - In `legacy` mode that is the same legacy store, so nothing changes.
  - In `shadow` mode it is the legacy store, reached through the dual adapter.
  - In `pilot` mode it is the institutional skill library, **ACTIVE skills
    only**.
- Lesson recall is unchanged.
- The library's tables (`institutional_skills`, `skill_trails`) are frozen for
  the run exactly like `MEMORY_TABLES`. They are fingerprinted after the slot is
  built, so its one-time setup is not read as learning.
- Every trail records `skill_store_mode` and `library_active_at_start`.

**Why.** The benchmark measures whether what this system *remembers* helps it.
Once pilot recall answers from the library, the legacy store is no longer what
the turn remembers skills from, and measuring it would describe a store the
operator has moved away from.

**What it costs, stated before any number exists:**

1. **The Phase 0 → Phase 8 pairing is broken for the skill channel.** The
   Phase 0 baseline recalled legacy *verified* skills. A pilot-mode run recalls
   library *active* skills. A Phase 8 result under D3 is therefore not a paired
   before/after comparison of the skill channel. It is reported as its own
   measurement, beside the baseline, never as a delta from it. The lesson
   channel is unchanged, so its pairing still holds.
2. **No skill learned during a run can ever be recalled in `pilot` mode.**
   Activation is the operator's capability-backed act, and a benchmark faking
   one would be the laundering the cage forbids. A pilot-mode ON arm can
   therefore gain only from lessons and from skills **the operator had already
   activated** before the run. `library_active_at_start: 0` means the skill
   channel was structurally empty. That result is a fact about activation, not
   a finding about the value of skills.

### D4 — 2026-09-27 — a powered cloud cohort, judged alongside the 7B

**Applies to:** the calibration run, the cloud cohort's baseline run, and every
Phase 8 run, including how the 7B's Phase 8 H1 is judged. It was recorded before
any run under it. The research behind it is `PAYOFF_POWER_RESEARCH.md`.

**Why.** At N = 30 with one sample per arm, the 7B design has a 3–9% chance of
detecting a real +10-point effect. Its null would describe the design, not the
memory.

**Operator decision (2026-09-27): "Both judged, corrected".** The alternatives
recorded against it were:
- the cloud cohort as the primary number, with the 7B as secondary;
- keeping the 7B as the only judged number.

**The cohort.**
- **Model:** Bedrock `qwen.qwen3-coder-30b-a3b-v1:0`, reached through the
  harness's product dispatch.
  - The temperature is the product default (`AIOS_LLM_TEMPERATURE`, 0.1).
  - The timeout is 420 s.
- **Skill store mode:** the launch environment sets
  `AIOS_SKILL_STORE_MODE=pilot` explicitly, because a `.env` is read from
  wherever the run is launched. `library_active_at_start` is recorded.
- **Arms:** OFF, ON and PLACEBO (`--placebo`). The arm order rotates by target
  index.
  - PLACEBO gets as many lessons and skills as ON.
  - They are recalled by the production path for *other* targets' tasks, in an
    order fixed by the chosen list, and none is an item ON saw.
- **Targets:** `--novel-only`, taken in `collect_targets`' fixed ranking, and
  `--exclude-targets` removes the calibration list. The baseline's chosen list
  is frozen and re-run at Phase 8 with `--target-labels`.
- **Credentials:** `AWS_BEARER_TOKEN_BEDROCK` and `AIOS_BEDROCK_REGION` exist
  only in the operator's terminal, which launches the run. They are never
  written to disk, and the agent never sees them.

**Calibration (never judged).**
- **Design:** the first 20 never-practised targets in the same ranking, with
  `--samples 3`, all three arms and the same model.
- **Freezing:** its target list is committed as
  `payoff_targets_calibration.txt` before the baseline runs.
- **Use of outcomes:** they are published and never enter a judged test.

**The sizing rule, fixed now and applied mechanically:**
- **K = 1** if fewer than 5% of the calibration's (target, arm) cells show any
  disagreement among their three samples, since at temperature 0.1 repeats may
  be near-identical. **Otherwise K = 3.**
- **N = 150** NOVEL targets, or every never-practised target left after the
  exclusion if fewer remain. This is a feasibility bound: 150 × 3 arms × 3
  samples takes about 15 hours on this machine.
- **Before the baseline, the design's minimum detectable effect is recorded.**
  It comes from the registered simulation, with target heterogeneity estimated
  from the calibration OFF arm. It is reported beside every result and **never**
  used to change N afterwards.

**Tests.**
- **With K = 1:** exact McNemar, as before.
- **With K > 1:** the exact sign-flip test on per-target differences in earned
  samples (`sign_flip_exact`). The target stays the unit, so K samples of one
  target are never K pairs.
- **Comparability:**
  - A pair is comparable only if every sample of ON and OFF reached the model.
  - The content comparison also needs every PLACEBO sample reached and the
    PLACEBO matched in lesson and skill counts. An unmatched or unreached
    PLACEBO removes the pair from H1c only.

**The judged family, at family-wise α = 0.05 by Holm (`holm_adjust`):**

| Test | Cohort | Question |
|---|---|---|
| H1-cloud | Phase 8 cloud run | NOVEL: ON vs OFF |
| H1c-cloud | Phase 8 cloud run | NOVEL: ON vs PLACEBO (content, not prompt length) |
| H1-7B | Phase 8 7B run (design unchanged) | NOVEL: ON vs OFF |

- **How a member is judged:**
  - It is *met* only if its direction is positive **and** its Holm-adjusted
    p is below 0.05.
  - No raw p from any single run is reported as a verdict. The harness prints
    such a p as "NOT a verdict on its own".
- **Which runs are judged:**
  - The cloud baseline run is reported as the cloud cohort's baseline, as
    Phase 0 is for the 7B, and it is not judged.
  - H3 is evaluated for each cohort on its own frozen targets.
  - H2 (harm) stays per cohort and uncorrected. Correcting would make harm
    *harder* to see.

**Transport.** A provider refusal made before any reply exists (throttling,
service unavailable, model not ready) is retried up to three times, at 15, 45
and 90 s, and every retry is recorded. A timeout or any other error is not
retried. An arm still unreached is not comparable, as before.

### D5 — 2026-09-27 — calibration applied; the placebo becomes other stored lessons

**Applies to:** the cloud cohort's baseline run and every later run, Phase 8
included. It was recorded after the calibration (`PAYOFF_CALIBRATION_RESULT.md`)
and before any other run.

**The sizing rule, applied as D4 fixed it:** K = 3 (repeat disagreement was
12.5%) and N = 150, excluding the 20 calibration targets
(`--exclude-targets docs/learning/payoff_targets_calibration.txt`).

**Minimum detectable effect:** about +6 points at α = 0.05, and +7 at Holm's
worst case. It is approximate, because the heterogeneity fit sat at its grid
bound. It is recorded now and never used to change N.

**What the calibration found.** Recall gave all 20 tasks the same five of the
store's seven verified lessons, and the skill channel was empty (0 activated).
D4's placebo, memory recalled for *other* targets' tasks, therefore matched on
**0 of 20** targets: nothing was left to draw.

**Operator decision (2026-09-27): "Other stored lessons".** The alternatives
recorded against it were:
- dropping H1c, which would make the family {H1-cloud, H1-7B};
- pausing the payoff to fix recall first.

**The placebo from now on:**
- **Size:** as many lessons as ON recalled.
- **Selection:** none of them one ON saw. They are drawn with the fixed seed
  `payoff-D5-20260927` per target label, from the store's **verified and
  pending** lessons. Superseded (retired) lessons are never used.
- **Format:** the same production block, with each lesson's **true** stored
  status. **Known confound, accepted knowingly:** only two verified lessons
  remain outside ON's five, so most placebo lessons display `[pending; …]`
  where ON's display `[verified; …]`.
- **Skills:** ON's skills block is kept unchanged, so ON and PLACEBO differ
  only in which lessons are shown.
- **Matching:** a target with no recalled lesson, or with too few other
  lessons, is unmatched and removed from H1c only.

**H1c, as it now reads:** on NOVEL targets, do the lessons recall picks beat
other stored lessons of the same kind and amount? It is no longer "memory for
this task versus memory for other tasks", because recall does not currently
choose per task. The judged family and the Holm correction are unchanged:
{H1-cloud, H1c-cloud, H1-7B}.

**Stated before any number exists:** with recall task-invariant, H1-cloud
measures the value of one fixed five-lesson block across all tasks. A positive
result would not be evidence of per-task transfer. It would say this block
helps this model on this task.

### D6 — 2026-09-27 — a pin test that never finishes is killed at 120 s; the first baseline attempt has no number

**Applies to:** the cloud baseline re-run and every later run, both cohorts'
Phase 8 runs included. It was recorded before any of them.

**What happened.** The first cloud baseline attempt,
`20260927T142947-8abefcd9` (harness `3a0d13c6`, this file's D5 text), stopped at
target 77 of 150. The ON arm's model-written test for
`aios/__main__.py::main` started the server and never returned.
- **The grader's only bound was `run_suite`'s 30-minute default.** Reaching it
  would have raised an uncaught `TimeoutExpired`, which ends the run with no
  number.
- **On Windows the kill reaches only the uv launcher.** The real pytest keeps
  the output pipes open.
- **The agent stopped the run after 20 minutes.** Under the exclusions above, a
  run the instrument cannot finish produces **no number** and is re-run in
  full. Its partial log is kept locally and was not analysed.

**What changed (the harness, not the hypothesis).**
- **`run_suite`:** at its timeout it kills the whole process tree and returns a
  red result marked `timed_out`. Its tail says so, so it is never mistaken for
  the "hollow" runner-died case.
- **The grader:** a model-written pin test gets **120 s**, against about 5 s
  typically.
  - A clean run that times out does not pass clean, so the arm is rejected with
    the note "TIMED OUT".
  - A mutated run that times out is **not** credited with catching the
    mutation. It is recorded as inconclusive, the conservative direction, as
    for a hollow run.
  - The repository's guard suite keeps its default bound.

**The calibration is unaffected.** Its longest arm took 29 s in total, so the
new bound would have changed none of its grades, and D5's sizing stands.

**The re-run** uses everything D4 and D5 fixed: the model, K = 3, N = 150, the
exclusions, the selection rule and the placebo seed. A timed-out arm is still
an arm that reached the model, so the pair stays comparable, exactly as a
failing test does.

### D7 — 2026-09-28 — practice history includes the skill library; the ON arm's slot has no mode

**What happened.** Phase 2 slice 2.4c-B made the institutional skill library
the only skill store. New arcs are learned there, and `procedural_skills` is
read-only history. `practice_history`, which decides whether a target is NOVEL,
read only `procedural_skills` and `mistake_pool`. A target practised after the
switch would therefore have looked never-practised, inflating NOVEL.

**What changed.**
- `practice_history` also reads every goal in the library beside the memory
  store. A library that exists but cannot be read makes the history unknown,
  and every target is then treated as practised, as for the memory store.
- `live_skills_slot()` builds the one slot there is. Runs record
  `skill_store_mode: "library"`; "pilot" in earlier trails read the same store.

**What it does not change.** The Phase 8 run re-uses the frozen list
`docs/learning/payoff_targets_cloud_baseline.txt` (D4), so no selection runs
and this has no effect on it. D3's statement about the skill channel stands:
an ON arm recalls only skills the operator activated before the run.

### D8 — 2026-10-04 — the ON arm recalls through the production gate; a run with nothing recallable is refused

- **What changed.** The ON arm recalls lessons through `live_lessons_slot`,
  the adapter a live turn's lesson recall passes through:
  - a lesson is admitted only if its newest provenance record verifies under
    the pinned live key and names the principal asking (plan Phases 3c and
    4c-1);
  - the gate reads a read-only provenance store, so recall cannot change the
    store being measured;
  - the principal is `AIOS_PAYOFF_PRINCIPAL`;
  - skills were already recalled through the gated library slot (4c-2).
- **The census.** Before anything migrates or writes the store, a read-only
  census (`gate_census`) counts what the gate would admit. A run whose ON arm
  could recall nothing is refused with the census as the reason. That is the
  existing rule ("NOVEL has no comparable pairs: no judged number"), applied
  before any model time is spent rather than after.
  `python tools/learning_payoff.py --census` prints it and asks no model.
- **Why.** What the benchmark measures must follow what the turn does: D3's
  reason, for lessons now. After Phases 3c and 4c a live turn recalls only
  signed rows that name the principal asking. Until D8 the ON arm read the raw
  store, ungated, as no one, so it measured memory no live turn can see.
- **The census on the live store (2026-10-04, read-only; both files'
  sha256 unchanged):** 23 candidate lessons (8 verified, 15 pending) and 0
  active skills. **Admitted: 0.** With no principal set, all 23 are refused as
  `no principal`. As `operator:swap`, all 23 are refused as `unsigned`.
- **Consequence: no D8 run produces a number yet.** Three things are needed,
  all the operator's acts:
  1. pin the live learning key (`AIOS_LEARNING_KEY_LIVE` in his environment,
     `LEARNING_PUBLIC_KEYS.json` committed);
  2. review and re-admit lessons with
     `tools/readmit_learning.py --apply --principal <his principal>`;
  3. set `AIOS_PAYOFF_PRINCIPAL`.

  Until then H3 ("hardening preserves utility") has one honest reading. The
  hardening withholds all legacy memory by design (operator decisions
  2026-09-25 and 2026-10-04), so the ON arm has nothing to recall. What
  re-admitted memory is worth through the gates is not yet measured.
- **Applies to** every run from this commit on.

### D9 — 2026-10-12 — lesson recall is task-specific; one lesson takes one slot

**Applies to** every run after this entry, both cohorts' Phase 8 runs
included. Recorded before any of them, **by operator decision** ("Improve
learning, then run", 2026-10-12). The alternatives recorded against it were:
- run the judged runs on today's memory now;
- the recall fix alone, then run.

**What was wrong.**
- **Relevance counted any shared word** (`relevance`: set overlap > 0). A
  long task and a long lesson always share generic words ("test",
  "function", "expected"). So recall returned one fixed block: D5's
  calibration found the same five lessons for all 20 tasks. The old rule,
  replayed on today's store, gives one identical 5-lesson block to 75 of the
  150 frozen cloud targets.
- **Copies were separate lessons.** On the live store one rule ("update the
  test to expect the function's actual behaviour") sat in eight rows, so one
  rule could fill the whole block.

**What changed (the product's recall, so a live turn and the ON arm
together).**
- **`specific_relevance`.** Overlap counts only *specific* tokens: not
  generic vocabulary, not a bare number, longer than two characters, with
  edge punctuation dropped (a sentence-final "it." had become a word that
  matched every task).
  - The generic vocabulary (`aios/memory/relevance.py`) is English function
    words, Python keywords and builtins, and general words of writing and
    testing code. It never names a module, function, file or domain.
  - Programming-domain words stay specific even where the task template uses
    them (`network`, `filesystem`, `config`): a lesson about network calls is
    a fair match for a task that mentions the network.
- **`distinct_lessons`.** Lessons with the same normalised text take one
  slot. This is decided **after** the recall gate, so a refused copy can
  never hide an admitted one.
- **Unchanged:** what a recalled lesson shows (type and lesson text only,
  never root cause or fix: RT-04), the gate, principal scoping, the limit,
  skills recall.

**How the vocabulary was fixed, disclosed in full.**
1. A first dry run used the **frozen evaluation targets' prompts**. No model
   was asked and no outcome was seen. It revealed the punctuation defect and
   generic coding words.
2. From then on, tuning used only a **development set**: 150 self-corpus
   targets that are in no frozen list (overlap checked: 0).
3. The list was then frozen, and the evaluation numbers were computed once,
   with no change after.

**The effect, measured without a model** (read-only copy of the live store,
recall ungated, because the gate admits nothing today):

| Targets | Old rule | New rule |
|---|---|---|
| Development (150) | template word "exactly" matched 148 | 37 recall anything, 11 distinct sets |
| Frozen cloud (150) | 20 distinct sets; one block on 75 | **29 recall anything**, 12 distinct sets |
| Frozen 7B (30) | 9 distinct sets; one block on 11 | **11 recall anything**, 8 distinct sets |

**Stated before any number exists.**
1. **With today's store, most judged pairs recall nothing.** Their ON and OFF
   prompts are identical, so they are NOT COMPARABLE, and the judged N shrinks
   to about 29 cloud targets. That is the true state of transferable memory
   today. It is why learning is improved (D10, planned) before the judged
   runs, not after.
2. **H3's Phase 0 → Phase 8 pairing is broken for lesson *selection*.**
   Phase 8's ON arm is reported as its own measurement, beside the baselines,
   never as a delta from them.
3. **The placebo (D5) is drawn as before:** as many other stored lessons as
   ON recalled. A target whose ON arm recalls nothing has no placebo, and
   leaves H1c as well as H1.

**Addendum, 2026-10-12, before any run.** A practice pilot on development
targets (D10) produced lessons about mocks. The task template says "No mocks",
so "mocks" would have matched every pin task. `mock`, `mocks`, `mocked`,
`mocking`, `patch`, `patched`, `patching`, `fixture` and `fixtures` join the
generic testing vocabulary, by the same principle as "pytest". No evaluation
target was consulted.

**Addendum 2, 2026-10-12, before any run.** The full practice run (D10)
produced 32 verified lessons. A dry run on the **development** targets (the
practice pool, none judged) showed template words driving recall: `symbol`
and `constant` recalled one lesson for 153 of 154 targets, and `python`,
`literal` and `raises` did the same for others. They are generic programming
words, like `variable` and `value`, so `constant(s)`, `symbol(s)`,
`literal(s)`, `python` and `raise(s/d)` join the generic vocabulary. After
this, recall on the development set is driven by domain words (`digest`,
`status`, `provenance`). No evaluation target was used to choose these.

### D10 — 2026-10-12 — lessons state a specific fact; practice never touches a judged target

**Applies to** every run after this entry, both cohorts' Phase 8 runs
included. It was recorded before any of them, and it continues the operator's
decision behind D9 ("Improve learning, then run", 2026-10-12).

**What was wrong.**
- The reflection prompt asked for "a generalised rule to avoid this class of
  error", and the model complied.
- On the live store, 1 of 23 lesson texts names a code identifier, while 17
  of 23 root causes do. The specific knowledge was in the row, and the text
  recall shows threw it away for advice any model already follows ("ensure
  test cases accurately reflect the expected behaviour", eight rows of it).
- Practice (`tools/organic_chain_run.py`) took the top N targets of
  the ranking the frozen judged lists were drawn from. That is how today's
  lessons came to be about judged targets.

**What changed.**
- **The reflection prompt asks for the ONE specific, checkable fact that would
  have prevented the failure.** The fact names the module, function, setting
  or convention.
  - The examples come from another codebase, so no repository fact enters
    through the prompt.
  - A failure that teaches nothing specific is recorded as "No specific
    lesson", and **nothing is stored**.
- **lesson_text states a fact, never a command to run, a URL or an
  instruction.** Recall still shows type and text only. The security cost of
  more specific text is measured by re-running the behavioural red-team
  (RT-04) before the judged runs.
- **Practice takes `practice_targets`:** the ranking minus every frozen judged
  list, at an offset. If a frozen list is missing, the run refuses rather than
  excluding nothing.

**Measured (pilot, isolated store, no judged target touched).**
- **Paired replay:** the same 12 failures (one practice run, development
  targets), reflected with the same model (Bedrock Qwen3-Coder-30B) under
  master's prompt and under this one.

  | | Old prompt | New prompt |
  |---|---|---|
  | lessons stored | 12 | 12 |
  | naming a code identifier | **3 / 12** | **11 / 12** |
  | "No specific lesson" | 0 | 0 |

  - Old lessons read "When testing functions that parse structured strings,
    always verify…".
  - New ones read "`recalled_channels` requires the format
    `RECALL_CHANNELS: channel_name` and splits on ':'…".
- **Specific is not correct.** At least one new lesson states a confident
  falsehood: it calls a test file a module that "applies encryption or
  hashing". The guard is unchanged: a lesson reaches another task only once
  it is **verified**, when the identical command later passes. The judged
  run measures whether that guard is enough.
- **The pilot found two harness defects in practice, both fixed:**
  - A cloud model could never reflect. `BedrockClient` has no `complete()`,
    so every reflection raised, and every stored lesson came from
    local-ladder runs.
  - All targets in a run shared one task id, so different failures of the
    same error type collapsed into the first lesson.

**Stated before any number exists.**
- Lessons now accumulate only from practice targets, which are disjoint from
  the judged lists. Any transfer to a judged target is therefore transfer to
  code the animal has never practised: exactly H1's question.
- H3's pairing stays broken, as D9 says.

### D11 — 2026-10-12 — a lesson is written from the fix that worked; a guess is never promoted

**Applies to** every run after this entry, both cohorts' Phase 8 runs
included. Recorded before any of them, by operator decision ("Ground lessons
in the fix", 2026-10-12). The alternative recorded against it: admit the
true lessons from the first practice run and run the judged runs at once.

**What was wrong.** "Verified" meant the identical command later passed. The
lesson itself was a diagnosis written at the moment of failure, before anyone
knew the answer, and nothing ever tested it. The first full practice run
(D10, 151 development targets, Bedrock Qwen3-Coder-30B) produced 32 verified
lessons. Each was checked against the code:

- **true: 5**; partly true: 3;
- **false: 13**. For example, it said `approved_organ_ids` raises, when it
  returns an empty set. It said `collect_meta_loop_evidence` takes
  `context=`, when it takes `reflections=`, …;
- about the test's own mocks or generic Python: 9;
- secret-scanner artefacts: 2.

**What changed.**
- **`ReflectionAgent.reflect_resolution`.** The reflector sees the failure
  AND the change that made the same command pass, and states the fact the
  passing change proves.
  - The lesson is recorded under `<task>#resolved` and promoted at once with
    STRONG evidence.
  - "No specific lesson" stores nothing.
- **Practice (`ground_on_success`).** When a target passes after failing:
  - the failing test is diffed against the passing one;
  - a grounded lesson supersedes the failure-time guesses;
  - with no grounded fact, the guesses stay pending. Pending lessons are
    recalled only within their own practice task. **A guess is never
    promoted.**
- **Scope: practice only.** A live turn's confirm hook still promotes the
  failure-time lesson. Grounding it needs the edits between failure and
  success, and is follow-up work.

**Measured: the second full practice run** (the same 151 development targets,
same model, run in batches after a memory stop). 19 grounded lessons were
checked against the code:

| | Run 1 (guesses) | Run 2 (grounded) |
|---|---|---|
| false | 13 / 32 (41%) | **4 / 19 (21%)** |
| true and useful | 5 / 32 (16%) | **6 / 19 (32%)** |
| true but empty | — | 2 / 19 |
| about the test or mocks | 9 / 32 (28%) | 6 / 19 (32%) |
| secret-scanner artefact | 2 / 32 | 1 / 19 |

- One guess and its grounded replacement show the effect. Run 1's guess said
  `approved_organ_ids` raises; run 2's grounded lesson says it returns an
  empty frozenset, which is true.
- **What it did not fix:** the reflector never once wrote "No specific
  lesson" (0 of 18 resolutions). Fixes that only repaired the test's own
  mocks still became lessons.
- **The secret scanner** (frozen, `aios/security/*`) redacted a function
  name, a module path in task ids, and expected hash values in generated
  tests. It is the source of every artefact lesson. Recorded for the
  operator; not changed.

**Stated before any number exists.**
1. Across both runs, **11 true lessons and 3 partly true ones** are
   candidates for the operator's review. Each is about one function.
2. This is thin memory: a judged run measures whether a handful of narrow,
   true facts help on never-practised work, and a small or null effect is
   the expected honest result.
3. Only lessons the operator re-admits after reading them reach a turn.

### D12 — 2026-10-12 — a strong teacher writes the lessons; the local student is chosen by a rule; a second judged family

**Applies to** the practice runs and the judged runs after this entry. Recorded
after the Phase 8 verdict (`PAYOFF_PHASE8_RESULT.md`: H1 not met, no harm,
hardening kept utility), and before any D12 practice or judged run. The
operator decided, on 2026-10-12, three things:
- a strong cloud model is "the teacher that writes the lessons";
- the pairing is a cloud teacher with the best local student;
- budget is not a constraint.

**Phase 8's verdict stands.** D12 is a new experiment with its own family. It
is not a re-run of Phase 8 under different conditions.

**Why.** Phase 8 located the bottleneck in the memory, not the model:
- only 11 lessons were admitted;
- 65 of 150 cloud targets recalled nothing;
- ON earned exactly what PLACEBO earned (64 vs 64).

Under D11 the student still wrote its own lessons, and 4 of 19 grounded
lessons were false.

**Practice.**
- **Ladder:** the student `qwen.qwen3-coder-30b-a3b-v1:0` attempts first, then
  the teacher. Each gets `--retries 2`.
- **The teacher writes every lesson** (`--teacher`, #479): the failure-time
  reflection, and D11's grounded lesson from the passing fix.
- **Targets:** every target in the `practice_targets` ranking, **156**. Every
  frozen list is excluded (D10).
  - They are partitioned by `--offset` across parallel workers.
  - Each worker has its own store, corpus worktree and trail.
- **One pass over the 156.** No target is re-practised to raise the yield.
- **Teacher pilot, run first.** Two candidates each practise the first 20
  targets of the ranking (offsets 0–19):
  - `global.moonshotai.kimi-k3`. Corrected 2026-10-12, after #482 merged and before any D12
    run: the plain id `moonshotai.kimi-k3` is refused on demand in ap-south-1 (it needs an
    inference profile), and the global profile is the id the 2026-10-11 intelligence
    benchmark used. Practice sends only practice-target code, so cross-region routing is
    acceptable here. The model is unchanged; only its id is;
  - `qwen.qwen3-coder-480b-a35b-v1:0`.

  The rule for choosing between them:
  1. Every grounded lesson is checked against the code, as D11's were: true
     and specific, partly true, false, about the test or its mocks, or a
     scanner artefact.
  2. The teacher with more true-and-specific lessons teaches the remaining 136.
  3. On a tie, the one with fewer false lessons teaches them.
  4. Still tied: Qwen3-Coder-480B.
  5. Both pilots' lessons remain candidates.
- **The critic** (`--critic`, #483), added by the operator's direction the
  same day ("multiple cloud models with the local one"): the pilot's other
  model, shown the module source, the passing change and the lesson. A lesson
  it does not call true is not proposed.
  - **The pilot runs without a critic,** so the teachers are compared on their
    own lessons.
  - **The critic is checked before it is trusted.** It is then run on every
    pilot lesson, and its verdicts are compared with the fact-check. It is used
    in practice only if it agrees with the fact-check on at least 80% of the
    pilot lessons. Otherwise practice runs without it, and that is reported.
  - **Rejected lessons are not lost.** They are logged with their text, and
    the fact-check covers them too, so false rejections are counted.
- **Two practice streams, one pass each over the 156:**
  - **Cloud:** the cloud student, partitioned across 3 parallel workers.
  - **Local:** the local student chosen by the rule below, on 1 worker (one
    local model fits in memory). Its lessons come from the local model's own
    mistakes, the ones the local judged member is about.
  - The same teacher and critic serve both streams. The streams may run at the
    same time: the cloud models run on AWS, and the laptop only grades.
- **Order:**
  1. Local student chosen by the rule.
  2. Teacher pilot.
  3. Critic check.
  4. Both practice streams.
  5. Fact-check, then re-admission.
  6. The judged runs.

**Admission (unchanged).**
- Every grounded lesson is checked against the code at the practice corpus
  commit.
- Only lessons the operator reads and re-admits reach a turn.
- The count and truth rates are published whatever they are.

**The local student, chosen first (the local practice stream needs it), by a rule.**
- **Candidates:** the installed models the clerk has qualified, called as the
  product calls them:
  - `qwen2.5-coder:7b`;
  - `qwen3.5:9b`, with `think: false` (#481);
  - `granite4.2:8b`.
- **The rule:** each candidate runs the 20 calibration targets
  (`payoff_targets_calibration.txt`, never judged), OFF arm only, K = 1. The
  candidate that earns the most is the student.
- **Why this rule:** Phase 8 found `qwen2.5-coder:7b` at the floor, earning 1
  to 2 of 18. A student that cannot earn without memory leaves memory nothing
  to lift.
- **Tie-breaks:** the smaller model, then the faster one.

**The judged runs, once, after admission.** Both use a copy of the operator's
live store, made after his re-admission.

- **Cloud:**
  - **Design:** Phase 8's cloud design, unchanged: the same model and the same
    150 frozen targets (`payoff_targets_cloud_baseline.txt`), `--novel-only`,
    calibration excluded, K = 3, OFF / ON / PLACEBO.
  - **Members:** H1-cloud-D12 (NOVEL: ON vs OFF) and H1c-cloud-D12 (NOVEL: ON
    vs PLACEBO).
- **Local:**
  - **Design:** the chosen student, on the same 150 frozen targets, K = 3, OFF
    / ON / PLACEBO, 420 s timeout. It is expected to run overnight.
  - **Members:** H1-local-D12 and H1c-local-D12.
  - **Why this design:** Phase 0's 30-target, K = 1 design could only have seen
    a very large effect.
- **The family:** {H1-cloud-D12, H1c-cloud-D12, H1-local-D12, H1c-local-D12},
  Holm at family-wise α = 0.05.
  - A member is met only if its direction is positive and its Holm-adjusted p
    is below 0.05 (D4).
  - H2 (harm) stays per cohort and uncorrected.
- **Recording:** `tools/judge_payoff_family.py` gains the D12 family. Its
  verdict is written to a D12 result file beside Phase 8's, and the usefulness
  gate reads the newer one.

**Stated before any number exists.**
1. **Lesson count:** the teacher should write truer lessons than the student
   did. One pass over 156 targets will likely yield tens of grounded lessons,
   not hundreds; the pool is the limit.
2. **Cloud:** the effect may still be small. The student is a capable model,
   and most cloud targets were all-or-nothing in Phase 8.
3. **Local:** the student has more headroom. That is the member most likely
   to show a benefit, if there is one.
4. **Null results:** a null result on all four members is a possible honest
   outcome, and would be reported as such.

**Amended 2026-10-18, before any D12 judged run: a hollow suite run is measured
again.**
- **What happened.** The D12 cloud practice (one worker, Kimi K3 teaching)
  aborted 31 minutes into its 136 targets. One run of the pre-existing guard
  suite died before pytest printed anything (Windows rc `0xC0000142`, DLL
  init failed). The grader rightly refused to score that run, but its only
  response was to end the whole run.
- **The change** (`tools/self_corpus_grading.py`, used by practice and by the
  judged harness alike). A HOLLOW run (no output at all, so it measured
  nothing) is run again, up to twice, after 10 s and then 30 s. Each re-run is
  written into the verdict's notes. A run that stays hollow still aborts, as
  before.
- **Why it cannot favour an arm.** It applies identically to ON, OFF and
  PLACEBO. It changes no verdict a non-hollow run would give. And it never
  turns a hollow run into a score: the verdict always comes from a run that
  reported. It replaces an abort with a measurement, not a failure with a pass.
- **The practice run is re-run from the start** with the same command. The
  aborted run's partial store is kept, labelled invalid, as before.

**Amended 2026-10-18, before any D12 judged run: the same models, reached
through us-east-1 with the operator's IAM key.**
- **What happened.** Between 13 and 18 October, Bedrock stopped running models
  for the stored Bedrock API key (account 908499290745): every model, every
  region answered "Operation not allowed". Practice run #3 was stopped by hand
  after 819 refusals in two minutes; it is kept as
  `invalid-bedrock-blocked-practice-cloud`. Two other routes were checked and
  were also closed:
  - a second key is explicitly denied by its AWS organisation's policy;
  - NVIDIA retired Kimi K3 on 2026-10-15.
- **The route now.** An IAM access key in account 424123861008, region
  **us-east-1** (the plan said ap-south-1).
  - Before practice used it, it was checked live: Kimi K3 (global profile) and
    Qwen3-Coder-30B each answered 5 of 5.
  - It was only usable after the operator fixed the IAM user's permissions
    boundary and attached a Bedrock policy.
- **What did not change.** The model ids are the same:
  - student `qwen.qwen3-coder-30b-a3b-v1:0`;
  - teacher `global.moonshotai.kimi-k3`;
  - ladder, retries, timeouts and targets.

  Only the account and the entry region differ. The teacher's global profile
  already routed across regions, which this plan accepted for practice code.
- **The run.** Practice run #4 started at 2026-10-18 14:57 IST from harness
  `83f8c3ce` (it includes the hollow-run re-measure and the
  provider-unavailable stop). Its launch record names the route and
  credential, never the key.
- **Judged runs** will state the account and region they ran through in their
  run records.

**Amended 2026-10-21, after the D12 cloud judged run and before the D12 local
judged run: what is recorded, what code is measured, and how it is judged.**
- **The cloud result is already fixed.** It is in `PAYOFF_D12_RESULT.md`:
  - H1-cloud-D12: 18 vs 16, raw p = 1.000;
  - H1c-cloud-D12: 21 vs 16, raw p = 0.721.

  This amendment changes nothing about it, and nothing about how the local
  members are run: same student, same 150 frozen targets, K = 3,
  OFF / ON / PLACEBO, the 420 s timeout, the calibration exclusion.
- **The trail records ids** (`tools/learning_payoff.py`, `Pair`).
  - **What it adds:** for each target, the lesson and skill ids recall showed ON, and the lesson ids the placebo drew. The cloud trail held only counts (5 lessons on every target), so it could not say whether recall varied by task.
  - **What it leaves unchanged:** no prompt, no arm order, no grade. A test pins the ON and PLACEBO prompts byte-for-byte to what recall and the placebo produced. All five mutants of the recording were killed.
- **The local run measures the cloud run's code:** `--ref 501c25369c32`.
  - Between that commit and the harness commit only `requirements.txt` changed (certifi 2026.10.19, PYSEC-2026-4320).
  - `aios/` and `tests/` are identical, so both halves of the family measure the same code.
  - The harness itself runs from master, with the recording.
- **The judgement was written before any local datum existed.**
  - `tools/judge_payoff_family.py --family d12` judges the four members with the same D4 rule as Phase 8 (one shared function, `family_verdict`). It refuses to write a verdict while either trail is missing.
  - The usefulness gate reads `payoff_d12_judged_result.json` once it exists, as D12 said.
- **Duration.** The plan said the local run "is expected to run overnight". Measured practice speed (about 7 tokens/s; 23% of attempts reaching 420 s) puts 150 × 3 × 3 = 1,350 graded attempts at about **2–3 days**. Only the estimate changes, not the design.

### D13 — 2026-10-28 — a task that names code is shown only lessons about that code; a local-only family

**Applies to** the D13 judged run, after this entry. Recorded after both the
Phase 8 and the D12 verdicts (no benefit, no harm), and before any D13 run.
**Operator decision**, 2026-10-28: "Retrieval fix, then a new run". The
alternatives recorded against it were:
- measure the payoff of reflexes in daily use;
- park lessons as "not shown".

**D12's verdict stands.** D13 is a new family. It is not a re-grade of D12.

**Why.** D12's local trail recorded which lessons each target was shown
(`PAYOFF_D12_RESULT.md`, diagnostics):
- recall varied by task, but was rarely about it: 27 of 150 targets saw a
  lesson from their own module;
- one lesson (#171, about `plan_with_llm`) was shown on 109 of 150;
- lessons almost doubled the prompt.

D12 named three hypotheses. D13 tests the third, that **a small local model is
distracted by long text that is not about its task**, together with relevance:
show only lessons about the code the task names, or none.

**Evidence against, stated first.** On the 13 comparable D12 targets that saw a
same-module lesson, ON earned 9 and OFF 15. Those targets also saw unrelated
lessons beside it, which is the condition D13 removes. Hypothesis 1 (specific
facts about practised functions do not transfer by construction) is not
addressed by D13.

**What changed (the product's recall, so a live turn and the ON arm together).**
- **A task that names code** (a module path with a directory, or an `aios.`
  dotted name) is shown a verified lesson only if the lesson is about that code
  (`names_the_same_code`, `aios/memory/relevance.py`):
  - the lesson's module, from the task it was learned on or from its own text,
    is named by the task as a path or an import path, matched whole (never
    inside a longer name); or
  - for a dotted name such as `aios.pkg.mod.func`, a prefix of three or more
    parts is; or
  - a function the lesson was learned on is named by the task as a whole word,
    and that name is distinctive (12 or more characters, or two or more
    underscores: `distinctive_name`, now shared with `about_this_target`).
- **A task that names no code** keeps D9's rule unchanged. So plain
  conversation recalls as before.
- **Unchanged:** what a recalled lesson shows (type and text only: RT-04),
  ranking by `specific_relevance`, the limit of five, `distinct_lessons`, the
  gate, principal scoping, skills recall, and the placebo rule (D5: as many
  other stored lessons as ON was shown, none of recall's picks).

**How the rule was fixed, disclosed in full.** As in D9, the rule was checked
offline: no model was asked and no outcome was read.
1. The first check ran on all corpus targets, D12's 150 judged ones included.
   One lesson (#195) was shown on 143 of D12's 150. Two leaks:
   - the secret scanner had cut its task id's path to `ce.py`, a substring of
     `service.py`, `reference.py` and others;
   - a bare filename in a lesson's prose (`auth.py`) counted as a home.
2. Fixed: a path needs a directory, and names match whole. Each leak has a test.
3. The rule was then frozen and the numbers below computed once.

**The effect, measured without a model** (D12's snapshot, the operator's gate):

| | D12's recall | D13's rule |
|---|---|---|
| D12's 150 judged targets shown any lesson | 150 | 51 |
| Targets shown the most-shown lesson | 109 (#171) | 9 |
| Never-practised, non-calibration targets shown any lesson | | 107 |

**The judged run, once.**
- **Store:** D12's pre-activation snapshot, unchanged: `C:\d12out\local-store-pre-activation`,
  `aios_memory.db` sha256 `90c009d9e5b5d52d…`, `aios_operational_state.db`
  `f95c7d7d83705fc6…`. 117 admitted lessons, 0 active skills. The only
  difference from D12's local run is the recall rule.
- **Corpus:** `--ref 501c25369c32`, D12's.
- **Student and arms:** `ollama.qwen3.5:9b@nothink`, K = 3, OFF / ON /
  PLACEBO, 420 s timeout, `--novel-only`, calibration excluded. Local only:
  every cloud credential is removed from the run's environment, as in D12.
- **Harness:** master after this entry merges; its commit is recorded in the
  run.
- **Targets:** `docs/learning/payoff_targets_d13.txt`, **85**, frozen
  (LF-normalised sha256 `09bcac0819ed36d1…`). Derived by
  `tools/payoff_d13_targets.py`, which asks no model and reads no outcome. A
  target is in it when it:
  - was never practised;
  - is not a calibration target;
  - is shown at least one lesson by the rule above;
  - is shown no lesson about itself (such a pair is reported apart from NOVEL,
    so running it would measure nothing judged).

  42 of the 85 are D12 judged targets. Order is the corpus ranking. The
  selection report is `docs/learning/payoff_d13_selection.json`.
- **The family:** {H1-local-D13 (NOVEL: ON vs OFF), H1c-local-D13 (NOVEL: ON
  vs PLACEBO)}, Holm at family-wise α = 0.05.
  - A member is met only if its direction is positive and its Holm-adjusted p
    is below 0.05 (D4).
  - H2 (harm) for the local cohort, uncorrected.
- **Recording:** `tools/judge_payoff_family.py --family d13`, written now,
  refuses a verdict without the trail. The usefulness gate reads the newest
  judged family.

**Stated before any number exists.**
1. **Power.** D12's local run had 30 discordant targets among 83 comparable. At
   that rate, D13's 85 targets give about 30. Holm over two members needs a p
   below 0.025 for the first, so about **22 targets better against 8 worse**.
   Only a large effect can be seen.
2. **A null result is likely** given the evidence above, and would be reported
   as such. Together with Phase 8 and D12, it would mean that prompted lessons
   do not help this student, even when they are about the code.
3. **If H1 is met and H1c is not,** relevant lessons beat none, but not other
   lessons. Then the effect may be about any added text, not this content.
4. **Duration:** 85 × 3 × 3 = 765 graded attempts. At D12's measured pace,
   about **1.5 days** of the laptop. The operator is asked before it starts.
5. **The live product changes too:** a turn that names code is shown fewer
   lessons, or none. Plain conversation is unchanged.

### D14 — 2026-10-30 — real use: the payoff is GAGOS's daily work on its own frontend; the harness family ends

**Applies to** GAGOS's daily frontend work, from its first daily run after this
entry. **Operator decision**, 2026-10-30: usefulness "is starved of real use —
not of more harnesses. So stop D13". He also decided that he will not approve
every diff: reviewing them is the agents' daily job, Claude Code and Codex
together.

**D13 has no verdict and will not be re-run.** Stopped at the operator's word on
2026-10-30 06:54 UTC: 5 of 85 targets, 41 graded attempts, 5 model errors (420 s
timeouts). No trail was written, so nothing can be judged. Its output is kept as
`C:\d13out\stopped-by-operator-20261030`, beside the two earlier attempts.
Phase 8 and D12 stand: not met, no harm.

**Why.** Three judged families have measured whether prompted lessons help a
model on practised-looking tasks. None found an effect, and the inspection of
2026-10-30 found why usefulness is starved: no ordinary turn since 2026-07-10,
and everything the store holds came from its own harnesses. A fourth harness
would measure the same machinery again. D14 measures the one thing missing:
GAGOS doing real work that lands in the product.

**The work, each day.**
1. GAGOS lints its own frontend with the project's ESLint. Files the
   lab-to-product port owns (`frontend/superbrain-source.json`) are excluded
   until that drift is reconciled.
2. Up to N findings are taken, one file and one rule each.
3. A frontier model proposes the whole corrected file: Bedrock, Mistral Large 3
   by default, through the one gateway, as the `coding` task.
4. **Static checks, unattended.** The file must still parse, the rule's warnings
   in it must be gone, and no new warning or error may appear. The proposal must
   not add a disable comment, and its change is bounded. Nothing the model wrote
   is executed before review.
5. **Two independent reviewers**, neither of them the proposer: Codex
   (`codex exec`, read-only sandbox) and Claude Code (a fresh non-interactive
   session, read-only tools). Each reads the file, the warnings and the diff,
   and accepts or rejects with a reason. **A proposal ships only if both
   accept.** Every disagreement is listed for the operator.
6. Accepted proposals are applied to one daily branch off master, the tests that
   import each file run, and one PR is opened. CI gates it, and the operator
   merges it. His merge is the only human act.

**Recorded per proposal,** in a durable ledger: refused by the static checks,
and why; each reviewer's verdict and reason; delivered; merged; reverted later.

**Reported, every day, descriptively.** Real use is not randomised, so no
significance test is claimed.
- **Harm, first.** A merged improvement that is reverted, or that breaks CI or a
  test.
- **Improvements merged** per day.
- **Master's ESLint warnings** (CI's warning budget, `.aios/state/FRONTEND_WARNING_BUDGET.json`),
  which should fall by the warnings fixed.
- **Honesty of the pipeline:** the static-check pass rate, each reviewer's
  accept rate, and how often the reviewers disagree.
- **Learning from real use.** The reasons a rule's earlier proposals were
  refused, by a check or a reviewer, are shown to the proposer for that rule.
  Reported: the share accepted by both reviewers, over the first 30 proposals
  against the next 30. A rise is a direction, not a finding.

**Stopping:** none. This is daily operation, not a run. The first summary comes
after 7 days or 30 proposals, whichever is first.

**What this does not claim.** Lint warnings are a narrow slice of "better"; types,
accessibility and design come later, each with its own checks. Two reviewers can
be wrong together; CI and the operator's merge remain. A rising acceptance rate
can come from easier rules being left, not from learning; the report names the
rules.
