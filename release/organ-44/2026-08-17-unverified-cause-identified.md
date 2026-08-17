# Organ 44 — what `unverified` actually is, and a fix of mine that missed it

**Date:** 2026-08-17
**Measurement:** 4 complete cohort runs — **1/5, 2/5, 2/5, 0/5**, mean **1.25**
**Prior 4 runs (post-#222, pre-#238):** 2/5, 0/5, 2/5, 0/5, mean **1.00**
**Conclusion:** the score did not measurably move; the CAUSE is now identified.

## The number

| window | runs | mean |
|---|---|---|
| post-#222, pre-#238 | 2/5, 0/5, 2/5, 0/5 | 1.00 |
| post-#238 (this) | 1/5, 2/5, 2/5, 0/5 | 1.25 |

Spread is 0–2 in both windows. At four runs each, 1.00 vs 1.25 is not
distinguishable from the variance this cohort already demonstrates, so **no
claim is made that #238 moved the score.** Combined across all eight
post-#222 runs the mean is **1.125**.

## #238 fixed a real defect that almost never happens

`#238` made a no-op write actionable: re-creating an already-correct file used
to answer "nothing to write", a dead end, and the traced failure showed a model
burning all five iterations that way.

Across these 4 runs — 20 missions — **that hint fired zero times.** The no-op
dead end is real (it was traced) and rare. I generalised from a single trace,
which is the same error as reading one cohort run as a trend, and it is worth
recording against the fix rather than leaving the impression it addressed the
main case.

## The dominant cause, measured

Of 10 `unverified` failures across 20 missions:

| shape | count |
|---|---|
| **zero evidence — no verification ran at all** | **7** |
| `[VERIFY SKIPPED]` — implementation written, no sibling test | 3 |
| the #238 no-op hint fired | 0 |

Every one of the 7 zero-evidence steps is an **edit** step
(`iterative-refinement` step 1, `data-pipeline` step 1). Traced:

```
read_file  training_ground/pipeline.py   -> content
edit_file  old_string=...                -> BLOCKED
                 [ERROR] old_string not found in training_ground/pipeline.py.
read_file  training_ground/pipeline.py   -> re-reads, tries again
```

`edit_file` requires an exact byte match. The model reads the file, builds an
`old_string`, and it does not match — so no write lands, `_auto_verify` never
fires (it is gated on `status == "ok"`), and the step ends `unverified` carrying
no evidence whatsoever.

### The system-side explanation was checked and eliminated

`read_file` returns `scan_and_redact(...).scrubbed`. If redaction altered the
text, the model would be editing against bytes that do not exist on disk — the
same class as the path false-positive fixed in #216. Tested directly against
`pipeline.py` and `test_pipeline.py`:

```
scrub_changes_content = False
```

So `read_file` is handing over the file unchanged. The mismatch is the model
failing to reproduce exact bytes, not the system corrupting them.

## What remains, and what is not yet known

`unverified` is now attributed rather than mysterious:

* **7 of 10** — `edit_file` blocked on `old_string not found`
* **3 of 10** — no sibling test written

The `edit_file` failure message is `"old_string not found in X."` — a dead end
in exactly the shape #215 and #238 addressed elsewhere: it states a failure and
offers no way forward. A message showing near-misses or the real surrounding
bytes is the obvious candidate.

**Whether that would convert into passing missions is unknown.** #238 was also
a plausible message fix on a traced failure and moved nothing measurable. The
honest position is that the cause is identified and the remedy is unproven.

## Standing rule, reaffirmed

Any future claim that a change moved this score needs repeats, not one run. This
record exists because that rule was applied to my own fix and the answer was
"no measurable change".

## Reproduce

```
docker compose --profile build-only build worker
AIOS_DATA_DIR=<fresh> AIOS_GEMINI_PROJECT=<project> python -m aios     # detached
# enroll once, capture enrollmentCredential -> AIOS_OPERATOR_CREDENTIAL
python tools/golden_mission_runner.py run --model gemini.gemini-2.5-pro
```

One cohort per process (~850s): a fresh process restarts the 15-minute
privileged window. Turn-level evidence:
`.aios/audit/golden-mission-runs.jsonl`, rows at or after `2026-08-17T08:15`.
