# D12 judged result: cloud members

*Dated evidence, written 2026-10-21. Do not rewrite: add a superseded banner if
the local members change the family picture. Design:
`PAYOFF_PREREGISTRATION.md` D12. Practice, fact-check and re-admission:
`D12_PRACTICE_AND_FACTCHECK_RESULT.md`. Trail: `payoff_d12_cloud_trail.json`.*

> **Superseded status, 2026-10-28.** The local members have run and the D12
> family is judged: **not met, with no harm.** See "Local members and the
> family verdict (2026-10-28)" at the end. Everything above it is the dated
> evidence of 2026-10-21, kept as written.

## Status

| Member | Question | Status |
|---|---|---|
| H1-cloud-D12 | NOVEL targets: ON vs OFF | **run, not met** |
| H1c-cloud-D12 | NOVEL targets: ON vs PLACEBO | **run, not met** |
| H1-local-D12 | NOVEL targets: ON vs OFF, local student | not run (the operator decides; about 2–3 days) |
| H1c-local-D12 | NOVEL targets: ON vs PLACEBO, local student | not run |

The family is Holm at family-wise α = 0.05 over all four. A member is met only
if its direction is positive and its Holm-adjusted p is below 0.05 (D4). Holm
never lowers a p-value. Both cloud members have raw p of 0.72 or above, so
**neither can be met, whatever the local members show.** The family verdict waits
for the local run; `tools/judge_payoff_family.py` gains the D12 family when it
exists.

## The run

| | |
|---|---|
| Run id | `20261021T033650-0043a38f` |
| Ran | 2026-10-21, 09:06 to 17:08 IST (about 8 h) |
| Model | `qwen.qwen3-coder-30b-a3b-v1:0`, unchanged from Phase 8 |
| Route | AWS account 424123861008, us-east-1, the operator's IAM key (the 2026-10-18 amendment) |
| Harness and corpus | `501c2536` (master) |
| Pre-registration sha256 | `e847fe16742d1ded83652913114c718cacb431d3673fc688ce3b7c79cc0572a8` |
| Targets | the 150 frozen cloud-baseline targets, with the 20 calibration targets excluded, K = 3 per arm |
| Store | a copy of the operator's live store made after his re-admission: 117 lessons admitted (Phase 8: 11), 0 active skills |
| Comparable | **150 of 150**: no model errors and no hollow runs |

## Results

| | Pairs | ON earned | Other arm earned | Targets ON did better | Targets ON did worse | Raw p | Direction |
|---|---|---|---|---|---|---|---|
| **H1-cloud-D12**: ON vs OFF, NOVEL | 141 | 114 / 423 | OFF 114 / 423 | 18 | 16 | **1.000** | zero |
| **H1c-cloud-D12**: ON vs PLACEBO, NOVEL | 141 | 114 / 423 | PLACEBO 109 / 423 | 21 | 16 | **0.721** | positive |
| H2 harm (cloud, all pairs) | 150 | 126 / 450 | OFF 125 / 450 | 20 | 18 | 1.000 | **no harm** |
| SEEN (context only) | 9 | 12 / 27 | OFF 11 / 27 | 2 | 2 | 1.000 | — |

All p-values are the harness's own exact sign-flip tests over targets.

**Against Phase 8's cloud run** (same model and same targets), the D12 store did
not move the result:

| | Phase 8 | D12 |
|---|---|---|
| Lessons admitted | 11 | 117 |
| Targets with no lesson recalled | 65 of 150 | **0 of 150** (every target recalled 5) |
| ON vs OFF, by target | 17 vs 11 (p = 0.43) | 18 vs 16 (p = 1.00) |
| ON vs PLACEBO, by target | 12 vs 10 (p = 1.00) | 21 vs 16 (p = 0.72) |

## What this says, honestly

- **More lessons, and truer ones, did not help the cloud student.** Every one of the 150 targets now recalled lessons, where Phase 8 left 65 empty. The store was 10× larger and fact-checked: 5% false, against D11's 21–40%. ON and OFF still earned exactly the same: 114 of 423 each.
- **Content leans positive, but within noise.** Real lessons beat a placebo of the same size on 21 targets and lost on 16 (p = 0.72). It is the right direction for "what the lesson says matters", but far from evidence.
- **No harm.** Lessons did not make the student worse.
- **This matches the prediction stated before any number.** The pre-registration said, before the run: "Cloud: the effect may still be small. The student is a capable model, and most cloud targets were all-or-nothing in Phase 8." 107 of 141 novel targets tied between ON and OFF.
- **What is still open.** The pre-registration names the local student as the member "most likely to show a benefit, if there is one", because it has more headroom. That member has not been run.

## Observations

- **`can_drive_tools`: earned 7 of 9 in Phase 8, 0 of 9 here, with unchanged code.**
  - In every arm the model wrote a test that builds `ModelPassportV1(tool_protocol_status="verified")` with a single field. The class requires about 7 more, so validation fails before the test runs. Phase 8's OFF arm made the same error in 2 of 3 samples.
  - In Phase 8, both ON and PLACEBO earned 3 of 3: some prepended text steered the model to a valid construction. Here, a different store's recall did not.
  - Not an instrument fault. It is one more sign that the text prepended to the task changes behaviour whether or not it is relevant: the same position effect PLACEBO exists to separate from content.
- **Which lessons were recalled per target is not in the trail.** Only the count is recorded (5 on every target). So this result cannot show whether recall varied by task, or returned similar lessons everywhere (the Phase 8 calibration finding, D9). Recording the recalled ids is a harness change worth making before the local run.
- **Attempts took 13–23 s**, slower than Phase 8's ~10 s, through the new account and region. Run time was about 8 h, not the 3 h first estimated.

## Local members and the family verdict (2026-10-28)

*Dated evidence, written 2026-10-28. Trail: `payoff_d12_local_trail.json`.
Verdict: `payoff_d12_judged_result.json`, written by
`tools/judge_payoff_family.py --family d12`. That rule was committed in the
2026-10-21 amendment, before any local datum existed.*

### The verdict: D12 is not met

| Member | Pairs | ON earned | Other arm earned | ON better | ON worse | Raw p | Holm p | Met |
|---|---|---|---|---|---|---|---|---|
| H1-cloud-D12: ON vs OFF | 141 | 114 / 423 | OFF 114 / 423 | 18 | 16 | 1.000 | 1.000 | no |
| H1c-cloud-D12: ON vs PLACEBO | 141 | 114 / 423 | PLACEBO 109 / 423 | 21 | 16 | 0.721 | 1.000 | no |
| **H1-local-D12**: ON vs OFF | 83 | **91 / 249** | OFF **103 / 249** | 12 | 18 | 0.209 | 0.837 | no (direction negative) |
| **H1c-local-D12**: ON vs PLACEBO | 66 | **80 / 198** | PLACEBO **87 / 198** | 9 | 12 | 0.410 | 1.000 | no (direction negative) |

- **The family is not met.** No member is positive with a Holm-adjusted p below 0.05 (D4).
- **H2, harm: not seen in either cohort.**
  - Cloud: 20 vs 18 over 150 pairs, p = 1.00.
  - Local: 13 targets better with lessons, 18 worse, over 87 pairs, p = 0.26.
  - The registered rule flags harm only when ON is worse with p below 0.05.
- **SEEN, context only:** 4 comparable local targets, ON 8 of 12, OFF 7 of 12.
- All p-values are the harness's exact sign-flip tests over targets.

### The run

| | |
|---|---|
| Run id | `20261025T144556-a373c682` |
| Ran | 2026-10-25 20:15 IST to 2026-10-28 05:44 IST: about 57.5 h, of which the laptop spent 2.6 h in standby |
| Model | `ollama.qwen3.5:9b@nothink` (think = false), digest `56671c2ab938…`: the student the D12 rule chose |
| Route | local only. Ollama on the laptop; every cloud credential was removed from the run's environment |
| Corpus | `501c2536`, the cloud run's code (`--ref`, as amended) |
| Harness | `9dcb9d8d` (#528, which records recall ids) |
| Pre-registration sha256 | `ffa75d3a289882d27a251fe840234d20728c8736c038a1a6613ad7638dd034ba`: the file at `9dcb9d8d`, including the 2026-10-21 amendment |
| Targets | the cloud half's 150 frozen targets (identical list), the same 20 calibration targets excluded (same sha256), K = 3, OFF / ON / PLACEBO, 420 s timeout |
| Store | the snapshot taken before the operator activated skills: 117 of 140 lessons recallable, 0 skills. This was the cloud run's starting state (`aios_memory.db` sha256 `90c009d9…`, `aios_operational_state.db` `f95c7d7d…`) |
| Comparable | **87 of 150** for ON vs OFF, and 66 novel pairs for ON vs PLACEBO |

**Why only 87 of 150 count.**
- 200 of 1,350 attempts hit the 420 s timeout: ON 70, OFF 53, PLACEBO 77.
- A target with any ON or OFF sample that never got an answer is left out. It is not scored as a loss. That is the registered rule, and the cloud half used it too: there, no target was lost.
- Locally, 63 targets were lost to it. This costs power, not honesty.

### Conditions during the run, disclosed

- **Windows Update was not paused.** It was the operator's decision at launch, and no update reboot happened.
- **The laptop was in standby on 2026-10-26, 07:46 to 10:23 IST, and the run was suspended.**
  - One ON attempt spanned it: 9,502 s of wall time.
  - It was answered and graded normally.
  - The 420 s timeout did not fire, because the whole machine was suspended.
- **Memory was tight.** The model takes about 6 GB, and free memory fell as low as 0.6 GB.
- **The agent read the run log during the run, to report interim tallies to the operator.**
  - These reads were read-only. Nothing in the run's checkout, store or corpus was touched.
  - The run's own containment checks passed, with outcome `completed`.

### What this says, honestly

- **Lessons did not help either student.**
  - Cloud: ON and OFF earned exactly the same.
  - Local: ON earned less than OFF (91 vs 103), and was worse on 18 targets against better on 12. This is not significant, and it is not harm by the registered rule.
- **The member named most likely to benefit leaned the other way.** The pre-registration named the local student, because of its headroom.
- **What the lessons say did not matter either.** Real lessons against a same-size placebo came out 9 vs 12 locally. Recall's picks did no better than lessons selected for other work.
- **Most targets cannot move.** 53 of the 83 local novel pairs tied: the model solved them every time, or never, whatever it was shown.

### Diagnostics: not part of the verdict

The trail now records which lessons each target was shown. That answers a question the cloud trail could not.

- **Recall varies by task.**
  - The 150 targets got 138 different sets of 5 lessons.
  - 93 of the 117 recallable lessons were recalled at least once.
  - So the task-invariant recall seen in the Phase 8 calibration did not happen here.
- **Recall is rarely about the target.**
  - 27 of 150 targets were shown a lesson from the same module.
  - 13 were shown a lesson whose text names the target function.
  - On the 13 comparable targets that saw a same-module lesson, ON earned 9 and OFF 15.
  - One lesson (#171, about `plan_with_llm`) was recalled on 109 of 150 targets.
- **Lessons almost double the prompt.**
  - The mean prompt was 3,770 characters ON, 3,523 PLACEBO and 1,966 OFF.
  - ON and PLACEBO timed out more than OFF: 70 and 77 against 53, of 450 each.

**Hypotheses, not findings.** Testing any of these is a new pre-registered experiment, not a re-grade of D12.

1. The lessons are specific facts about functions that were practised. By construction, such facts do not transfer to novel functions.
2. The fact-check excluded the 24 `about_test` lessons. Those say how this repository's tests are written, which may be exactly the knowledge that transfers to a test-writing task.
3. A small local model is distracted by long prepended text that is not about its task.

### What it changes

- **The usefulness gate** (`tools/production_readiness.py`) now reads this verdict, not Phase 8's. It stays FAIL.
- **Learning usefulness has now been judged by two pre-registered families,** Phase 8 and D12. Neither found a benefit; neither found harm.
