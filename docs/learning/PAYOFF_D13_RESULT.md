# D13 judged result: relevant lessons only, local student

*Dated evidence, written 2026-11-02. Do not rewrite: add a superseded banner if
anything changes. Design: `PAYOFF_PREREGISTRATION.md` D13. Trail:
`payoff_d13_local_trail.json`. Verdict: `payoff_d13_judged_result.json`, written
by `tools/judge_payoff_family.py --family d13`. That code was committed on
2026-10-28, before the run produced any data.*

## Verdict

**The D13 family is not met. Harm (H2) was not detected.**

| Member | Question | Targets ON better / worse | Raw p | Holm p | Direction | Met |
|---|---|---|---|---|---|---|
| H1-local-D13 | NOVEL targets: ON vs OFF | 5 / 9 | 0.240 | 0.480 | negative | no |
| H1c-local-D13 | NOVEL targets: ON vs PLACEBO | 4 / 6 | 0.848 | 0.848 | negative | no |
| H2 harm (local, all comparable pairs) | ON worse than OFF? | 5 / 9 | 0.240 | (uncorrected) | — | not seen |

A member is met only if its direction is positive and its Holm-adjusted p is
below 0.05 (D4). Both members point the wrong way, so neither could be met at
any sample size this run had.

## The run

| | |
|---|---|
| Run id | `20261031T175215-bbaba5ab` (the fourth launch) |
| Ran | 2026-10-31 17:52 UTC to 2026-11-02 02:10 UTC (23:22 IST to 07:40 IST), about 32 h |
| Student | `ollama.qwen3.5:9b@nothink`, local only. The launch record gives the model digest `56671c2ab9385f9c…` and says every cloud credential was removed from the run's environment |
| Harness | `e6e8d668` (master after #550, the D13 entry) |
| Corpus | `501c25369c32`, D12's |
| Pre-registration sha256 | `25bc1432bcd1d377…`, as the trail records. It matches `PAYOFF_PREREGISTRATION.md` at the harness commit (LF-normalised). The file has changed on master since (D14), as expected. |
| Store | D12's pre-activation snapshot, byte-copied, per the launch record: `aios_memory.db` `90c009d9e5b5d52d…`, `aios_operational_state.db` `f95c7d7d83705fc6…`. The run's census line: 117 of 140 lessons recallable, 0 skills |
| Targets | the 85 frozen D13 targets (`payoff_targets_d13.txt`), K = 3, OFF / ON / PLACEBO, 420 s timeout, `--novel-only`, 20 calibration targets excluded |
| Attempts | 765 recorded (85 × 3 × 3). 658 reached the model and were graded. 107 did not (ON 39, PLACEBO 39, OFF 29), and every one of those is an Ollama request that timed out at 420 s |
| Comparable | **47 of 85** for ON vs OFF; 37 of those for ON vs PLACEBO |
| Launch record | `payoff_d13_launch.json` (operator principal redacted) and `payoff_d13_pip_freeze.txt`. The freeze file's LF-normalised sha256 `b8d64be2…` is the one the launch recorded. These are statements made at launch, not measurements in the trail |

**Three earlier launches** wrote no trail, and nothing from them was tallied. As the launch record lists them:
- killed by Windows Update on 2026-10-29, at 8 of 85;
- stopped at the operator's word on 2026-10-29, at 2 of 85;
- stopped at the operator's word on 2026-10-30, at 5 of 85.

## Results

| | Pairs | ON earned | Other arm earned | Targets ON did better | Targets ON did worse | Raw p |
|---|---|---|---|---|---|---|
| **H1-local-D13**: ON vs OFF, NOVEL | 47 | 33 / 141 | OFF 40 / 141 | 5 | 9 | 0.240 |
| **H1c-local-D13**: ON vs PLACEBO, NOVEL | 37 | 32 / 111 | PLACEBO 34 / 111 | 4 | 6 | 0.848 |
| SEEN (context only) | 0 | — | — | — | — | — |

All p-values are the harness's own exact sign-flip tests over targets.

- Of the 47 comparable targets, 33 tied between ON and OFF, and 26 of those earned nothing in either arm.
- So 14 targets were discordant.

## What this says, honestly

- **Relevant lessons did not help the local student.** D13 removed the condition D12 suspected, unrelated lessons shown beside the relevant one:
  - every target was shown only lessons about the code it names (median 4, at most 5);
  - recall spread across 86 distinct lessons, and the most-shown one appeared on 17 of 85 targets (D12: one lesson on 109 of 150).
  - Even so, ON earned less than OFF (33 against 40) and less than a placebo of the same size (32 against 34).
- **This is the outcome stated before the run.** The pre-registration said: "A null result is likely … Together with Phase 8 and D12, it would mean that prompted lessons do not help this student, even when they are about the code." That is the reading here.
- **Harm not detected.** The negative lean (5 better against 9 worse) is within noise (p = 0.24), as D12's was (12 against 18, p = 0.21). A non-significant H2 does not show that there is no harm.
- **The test was weaker than planned.** The pre-registration expected about 30 discordant targets and needed about 22 better against 8 worse to be met. The run had 14 discordant targets, because 38 of 85 targets were excluded (below). A small positive effect cannot be ruled out by this run alone. But both point estimates are negative, and three judged families (Phase 8, D12 and D13) now agree.

## Conditions, disclosed

- **Who is compared differs per comparison.** A provider failure is never scored as a model failure.
  - **ON vs OFF (H1, and H2):** a target counts only if every ON and every OFF sample reached the model. That is 47 of 85. Each of the other 38 has at least one ON or OFF sample whose Ollama request timed out at 420 s.
  - **ON vs PLACEBO (H1c):** a target must also have every PLACEBO sample reach the model. 10 of the 47 fail that, which leaves 37.
- **Timeouts were not even across arms.** Of 255 samples per arm:

  | Arm | Did not reach the model (timed out) | Median prompt | Median time to answer, reached samples only |
  |---|---|---|---|
  | ON | 39 | 3,160 characters | 87 s (216 samples) |
  | PLACEBO | 39 | 3,065 characters | 86 s (216 samples) |
  | OFF | 29 | 1,774 characters | 87 s (226 samples) |

  The arms that carry lessons have prompts about 1.8 times longer, and they timed out more. Within each comparison, targets are dropped whole, so neither arm is scored on samples the other lacks. But the comparable set can lean toward targets whose long prompts fit within 420 s, and the direction of any such bias is unknown.
- **When the timeouts fell.** Excluded targets, in run order, by blocks of 17 targets:

  | Targets | 1–17 | 18–34 | 35–51 | 52–68 | 69–85 |
  |---|---|---|---|---|---|
  | Excluded | 7 | 4 | 11 | 10 | 6 |

  The middle of the run was the worst.
- **The machine, from the launch record:**
  - the run was started by a waiter, only once 6 GB had been free for 3 minutes and no heavy job was running;
  - GAGOS's own tasks stood aside while it ran (the quiet marker);
  - Windows Update was not paused (the operator's decision: Defender needs it). It did not interrupt this launch, which ran to the end.
- **The machine, as Claude Code observed it during the run.** These observations are not in any committed record:
  - a 16 GB laptop in the operator's normal use;
  - at the operator's word, Chrome, Edge and WSL were shut at about 18:55 UTC on 10-31, raising available memory from 1.5 to 2.7 GB;
  - late in the run, the 9B model's server held about 7.8 GB and free memory was 0.6 GB;
  - the reviewers' hourly checks were read-only (CI logs, PR diffs, git): no local tests ran, and no other local model was loaded.

## What the programme does with this

- **The usefulness gate** (`tools/production_readiness.py`, `animal_usefulness`) reads the newest judged family, which is now D13. It stays FAIL, and its message is now D13's summary.
- **D14 (real use)** is the measurement that replaced D13 on 2026-10-30, and it continues. D13 ran again only at the operator's word. This result does not change D14's design.
- **No new judged family is proposed here.** Three families have found no benefit from lessons prepended to a prompt, for a cloud student and a local one, with all lessons recalled and with only relevant ones. Whether to measure learning in another form is the operator's decision.
