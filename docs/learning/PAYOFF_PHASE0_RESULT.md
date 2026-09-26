# Learning payoff — Phase 0 baseline result

*Run `20260925T085914-44216455`, 2026-09-25. Pre-registered in
`PAYOFF_PREREGISTRATION.md` (sha256 `bca5d2fd…` at run time) under Deviation D1.
Trail: `payoff_phase0_baseline_trail.json`.*

| | |
|---|---|
| Model | `ollama.qwen2.5-coder:7b`, 420 s timeout |
| Measured code | corpus `53eb1f0c` (master at the time) |
| Harness | `0feaf5f9` (arms restored before every arm, D1) |
| Targets | the 30 frozen in `payoff_targets_phase0.txt` (25 never practised, 5 practised) |
| Positive control | passed: the grader earns a known-correct test |
| Attempted / comparable | 30 / 28 |

## The judged number: NOVEL (transfer to unpractised work)

| ON earned | OFF earned | ON-only | OFF-only | exact McNemar |
|---|---|---|---|---|
| 4 / 26 | 3 / 26 | 1 | 0 | p = 1.00 |

**H1 (transfer): not met. H2 (no harm): not violated.**

Under the registration's own outcome table, this is "a direction, not a
finding", and a thin one: a single discordant pair. The honest reading is **no
measurable transfer** from what the system remembers (recalled lessons plus
verified skills) to new work, for this model on this task.

SEEN (context only): ON 0/2, OFF 0/2. ALL comparable: ON 4/28, OFF 3/28, with
the same single discordant pair.

Not comparable (excluded, never scored as losses): `normalize_command` and
`is_loopback_http_url`. An arm timed out at 420 s in both of this run's pairs
for those targets, and in run 1's too. See D2.

## What Phase 8 is compared against

This run. Phase 8 re-runs the same 30 targets, in the same order, with the same
model, and H3 compares the ON arm between the two runs. Run 1
(`20260925T045128-40a08711`) is reported in D1 and is **not** the baseline: its
corpus was never reset between arms, so 37 of its 60 arms were rejected for an
earlier arm's leftovers.

## A limit to decide on before Phase 8, not after

At this base rate the test has almost no power. Both arms earn about 11–14% of
pairs, and they mostly agree, so this run produced one discordant pair. An exact
two-sided McNemar at α = 0.05 needs **at least 6 discordant pairs, all in one
direction**, before any result can be significant. Unless hardening changes how
often the arms disagree, Phase 8's H1 cannot be met at N = 30 whatever the
memory is worth.

Any of these would change that: a larger N, a stronger primary model, or an
easier task. Each changes the experiment, so each needs a Deviation recorded
**before** Phase 8 runs. None is taken here, and choosing one is the operator's
call. Choosing after seeing Phase 8 would be exactly what the stopping rule
forbids.

## Anchoring

Master requires linear history, so #371 landed by squash and the harness
commit this run cites, `0feaf5f9`, is not on master. It stays fetchable with
`git fetch origin refs/pull/371/head`. The measured corpus, `53eb1f0c`, is on
master. The harness on master is not byte-identical to `0feaf5f9`: it carries
D2's later `clean -fdx` change, which applies to runs after this one.
