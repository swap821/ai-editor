# Learning payoff: cloud cohort baseline result

*Run `20260927T172315-ae60a9ae`, 2026-09-27/28. Registered under D4, D5 and D6
(`PAYOFF_PREREGISTRATION.md`). Trail: `payoff_cloud_baseline_trail.json`. The
frozen target list for Phase 8 is `payoff_targets_cloud_baseline.txt`.*

**This is the cloud cohort's baseline, as Phase 0 is the 7B's. It is reported,
not judged.** The judged numbers come from the Phase 8 runs, Holm-corrected
over {H1-cloud, H1c-cloud, H1-7B}.

| | |
|---|---|
| Model | Bedrock `qwen.qwen3-coder-30b-a3b-v1:0`, temperature 0.1, 420 s timeout |
| Credentials | from the operator's env file, loaded into the run process only |
| Measured code | corpus `f27c5995` (master at the time) |
| Harness | `94609b62` (#397; D6's 120 s pin-test bound) |
| Design | 150 never-practised targets (calibration excluded), K = 3, OFF / ON / PLACEBO, pilot mode |
| Skill library | 0 active skills, so ON's memory was lessons only |
| Positive control | passed |
| Comparable | 150 / 150 (149 NOVEL, 1 SEEN); PLACEBO matched on 149 / 149 |
| Integrity | 0 unreached samples, 0 throttling retries, 3 samples hit the 120 s bound (graded as D6 says) |
| Prompt length (median chars) | OFF 1,594; ON 2,474; PLACEBO 2,465, so PLACEBO controls length almost exactly |

**The pre-registration hash.**
- **Recorded:** `2dbd6873…`. That is the SHA-256 of the file in the run's
  checkout, which Git wrote with CRLF line endings. That checkout was
  byte-clean (`git status` showed no change).
- **Committed blob:** with the carriage returns stripped, the file hashes to
  `4d1be969…`, the committed blob at `94609b62`. Same text.
- **The calibration's** recorded hash is likewise the CRLF form of D4's blob.
- **Proposed fix:** the harness should hash line-ending-normalised text, so a
  recorded hash can be checked with `git show`. The fix and its note belong
  before Phase 8.
- **Fixed 2026-09-28, before Phase 8.** `tools/learning_payoff.py` now hashes
  the registration and the exclusion list as LF-normalised text
  (`text_sha256`), and every trail row records `hash_basis: lf-normalised`.
  A test checks the hash against `git show HEAD:<path>`. Rows without
  `hash_basis`, this baseline's and the calibration's included, hashed the
  checkout's bytes; strip the carriage returns to reproduce them.

## The numbers (NOVEL targets)

| Comparison | Earned samples | Targets where the first arm earned more / fewer | Difference (points) | 95% CI (bootstrap over targets) | Exact sign-flip p |
|---|---|---|---|---|---|
| ON vs OFF (H1 question) | 146 vs 138 of 447 | 21 / 20 | **+1.8** | **[−3.6, +7.4]** | 0.58 |
| ON vs PLACEBO (H1c question) | 146 vs 132 of 447 | 22 / 11 | **+3.1** | **[−1.3, +7.6]** | 0.21 |
| PLACEBO vs OFF (context) | 132 vs 138 of 447 | | −1.3 | [−6.7, +4.0] | |

- **SEEN, context only:** 1 target. ON earned 0 of 3 samples and OFF 2 of 3.
- **Target heterogeneity:** OFF earned 0 of 3 on 92 targets and 3 of 3 on 37;
  only 20 were mixed. Most targets are all-or-nothing for this model.
- **The CI:** 20,000 resamples of the 149 targets, seed 20260928. It is
  reported beside the registered test, not instead of it.

## What this says

- **No measurable benefit from this memory, for this model, on this task.** The
  difference is +1.8 points. Effects larger than about +7.4 points are unlikely,
  and so are losses beyond about −3.6. A small benefit, in the +2 to +7 range
  the design can barely see, is neither shown nor ruled out.
- **The content comparison leans positive but is not significant.** Recall's
  five verified lessons beat five other stored lessons on 22 targets and lost on
  11 (+3.1 points, p = 0.21). The lengths match, so this is not a prompt-length
  effect. The label confound D5 recorded still applies: the placebo lessons
  mostly display `[pending; …]`. Part of the gap is PLACEBO running slightly
  *below* OFF (−1.3), which is noise-sized.
- **The memory tested is thin.** The calibration showed recall gives every task
  the same five of the store's seven verified lessons, and no skill was active.
  This baseline measures that fixed block. It says nothing about per-task
  transfer, which the system does not currently do.
- **Honest summary:** the learning loop's memory, as it stands, does not
  measurably help a capable model write pin tests. The instrument is now able to
  see a moderate effect, and this is the first number from GAGOS's payoff
  benchmark that was designed to be able to answer.

## What Phase 8 compares against

This run. Phase 8 re-runs the frozen 150 targets in the same order, with the
same model, K, placebo seed and exclusions. H3 compares the ON arm between the
two runs. The first baseline attempt (`20260927T142947-8abefcd9`) produced no
number (D6).
