# Organ 44 — the golden cohort's distribution, and a fix that did not move it

**Date:** 2026-08-16
**Measurement:** 4 complete post-fix cohort runs — **2/5, 0/5, 2/5, 0/5**
**Mean: 1.00 of 5.** Pre-fix mean, over 3 runs: also **1.00**.
**Conclusion: #222 did not raise the score.**

This is the strongest evidence organ 44 has for its own number. Every previous
figure in this organ's history rested on a single run.

## Why these runs were made

`#222` fixed a real defect: Gemini 2.5 was thinking past its 1024-token output
budget and being truncated mid-thought, which reached the agent loop as a turn
that did nothing. The first cohort after that fix scored **2/5**, up from three
consecutive 1/5 runs.

That looked like an improvement. It was not established as one, and the
standard for not claiming it had already been written down in
`2026-08-16-cohort-breakdown.md`:

> Any future claim that a change moved this score needs repeats, not one run.

So four repeats were run before making any claim. Applying that rule against my
own change is the entire point of having written it.

## The distribution

| run | score | missions passed |
|---|---|---|
| 1 | 2/5 | `multi-module`, `error-handling` |
| 2 | **0/5** | — |
| 3 | 2/4 — truncated by the 400 defect, excluded from the mean | `multi-module`, `error-handling` |
| 4 | 2/5 | `multi-module`, `error-handling` |
| 5 | **0/5** | — |

Complete runs: **2, 0, 2, 0**. Mean **1.00**, min 0, max 2.

The single 2/5 reported earlier was the top of a bimodal distribution, not a new
level. Reading it as improvement would have been wrong, and it was the default
reading.

## What DID change, and survives repetition

**Zero "produced no output" failures across 24 missions.** Before the fix that
was 2 of 4 failures in a single run. This is categorical rather than
statistical, it is consistent across every post-fix run, and it is the real
result of #222.

There is also a structural shift worth recording. Before the fix, three runs
each passed a *different* mission (`data-pipeline`, then `multi-module`, then
`error-handling`). After it, the same two missions — `multi-module` and
`error-handling` — pass together whenever a run passes anything at all. The
randomness moved from *which* mission succeeds to *whether the run succeeds*,
which is what removing one noise source among several looks like.

## Honest reading

* #222 eliminated a genuine defect. The model is no longer truncated mid-thought.
* #222 did **not** improve the cohort score, and the ledger says so.
* Organ 44's honest number is a **mean of 1.00 of 5**, now backed by seven runs
  (3 pre-fix, 4 complete post-fix) rather than one.
* The organ stays **yellow**. Counts unchanged: 52 green / 2 yellow.

## Remaining failure causes

From the post-fix runs, in order of frequency:

1. **`unverified`** — the model writes the implementation and no sibling test,
   so the verifier has nothing to run.
2. **`error — Agent loop detected`** — the loop-safety control stopping a turn
   that repeated itself.
3. **the `400` after a session refresh** — undiagnosed, and now the third run
   it has truncated (endurance run 4, cohort run 3 here, and one earlier
   cohort). Ruled out so far: session mismatch (the route ignores the body's
   `sessionId`), prompt injection (all nine mission prompts pass, including
   with the vector shield loaded), duplicate cookies, and the refresh path
   itself (forcing a 401 by clearing cookies recovers cleanly).

## Reproduce

```
docker compose --profile build-only build worker
AIOS_DATA_DIR=<fresh> AIOS_GEMINI_PROJECT=<project> python -m aios     # detached
# enroll once, capture enrollmentCredential -> AIOS_OPERATOR_CREDENTIAL
python tools/golden_mission_runner.py run --model gemini.gemini-2.5-pro
```

Each cohort takes ~850s and must run as its own process: a fresh process gets a
fresh operator session, which restarts the 15-minute privileged window and
keeps the run inside it.

Turn-level evidence: `.aios/audit/golden-mission-runs.jsonl`, rows at or after
`2026-08-16T09:08`.
