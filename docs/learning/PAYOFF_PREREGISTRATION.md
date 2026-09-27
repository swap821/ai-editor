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
