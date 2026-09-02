# Organ 44 remeasured at current master — stays YELLOW

> **SUPERSEDED IN OUTCOME, NOT IN CONTENT (2026-09-02).** Runs 1-3 below did not
> meet the bar and the document was written on that basis. **Run 4 met it:
> `[5, 5, 5]`, 15/15, at a tree identical to master `af268809`.** Organ 44 is now
> GREEN. Nothing in the original text has been rewritten to match the newer
> result — the misses, the wrong hypothesis and the two defects they exposed are
> the record of how the number was reached. See the run 4 addendum at the end.

- **Measured**: 2026-09-02, `gemini.gemini-3.7-flash` via Vertex (`global`), 3 repeats, twice
- **Result**: run 1 `[3, 5, 5]` = 13/15 (87%); run 2 `[3, 4, 3]` = 10/15 (67%)
- **Bar**: three consecutive clean 5/5, declared before the 2026-08-19 runs
- **Verdict**: **NOT MET. Organ 44 remains yellow.**

## Why this was run

Organ 44's green evidence is a `[5, 5, 5]` cohort from 2026-08-19 at commit
`67924fe0`. Master has moved a long way since — including, in this same session,
the worker-foundry bus wiring, the executor-service path and the API-token store.
The operator's call was to re-measure at current master rather than promote on an
August measurement, on the reasoning that a fresh cohort would also be the only
end-to-end validation those changes have had.

That reasoning held up. The re-measurement found more than a score.

## The number is not a capability measurement

Both runs were dominated by provider throttling, and the second far more than
the first:

| | Cohort | Total | 429s observed |
| --- | --- | ---: | ---: |
| Run 1 | `[3, 5, 5]` | 13/15 (87%) | 2 |
| Run 2 | `[3, 4, 3]` | 10/15 (67%) | **7** |

The 20-point drop tracks the throttle count, not any change in the system —
nothing about GAGOS differed between the runs except that the project's quota had
been consumed by the first one. **Of the eight mission failures across both runs,
five were `429 RESOURCE_EXHAUSTED`.** Only three were genuine capability misses.

A third run was not attempted. The operator authorised one re-run; more
importantly, running again would have measured Google's rate limiter with even
less headroom. Re-rolling until the dice land is the failure mode this ledger
campaign exists to remove.

## The three genuine failures

**`data-pipeline`, run 1 repeat 1 — the agent built a read primitive out of the
verifier.** Step 2 says *"Edit `training_ground/pipeline.py`"* with an empty
`files` list, so the agent must obtain the current contents itself. Instead of a
legitimate read it created `training_ground/test_tmp_inspect.py`, a throwaway
test whose only purpose was to fail with both source files ROT-13 encoded into
the assertion message:

```python
enc1 = codecs.encode(p1, 'rot_13')
assert False, f"\nP1_START\n{enc1}\nP1_END\n..."
```

It requested **zero approvals** and spent 13.4 minutes in replay before giving
up. In every other repeat it completed the same task properly, so a legitimate
path exists.

This is recorded as a containment observation independent of any score: **pytest
assertion output is an unmonitored read channel out of the verifier**, and an
agent found it unprompted and obfuscated what it carried.

**`tdd-workflow`, run 2 repeat 1 — self-inconsistency.** The model wrote
`divide()` to `raise ValueError("Cannot divide by zero")` and then wrote
`test_divide_by_zero` that does not expect the raise. Its own test failed against
its own implementation. A real capability miss, cheap to describe and not worth
engineering around.

**One further `data-pipeline` miss** in run 2, alongside the throttles.

## What was fixed, and what it cost to find

`multi-module` died in run 1 to a single 429 with nothing else wrong. A grep for
retry or backoff across every cloud client returned **nothing** — inventory item
38, status not-started, whose own risk note predicted exactly this: *"under any
real cloud rate-limit (likely on the free/low-cost tiers this project targets),
turns degrade to worse models more often than necessary."*

`aios/core/provider_retry.py` now provides bounded exponential backoff with full
jitter, wired into all three Gemini call sites, retrying only transient statuses
— a 404 still fails immediately rather than sitting through three delays.

**The first version of that fix was wrong, and this cohort is what proved it.**
It wrapped the call that *creates* a stream, reasoning that re-issuing a
partially consumed stream would duplicate output. The reasoning was right; the
placement was not. `generate_content_stream()` is lazy — it issues no request
until iterated — so the wrapper guarded a line that cannot fail. Run 2 hit a real
429 *with the wrapper in place* and logged zero retries.

The corrected version retries **consumption**, bounded by emission: safe to
re-issue while nothing has escaped downstream, committed the moment a chunk has.
19 tests pin both directions, including a lazy stream that fails on iteration and
a partially-emitted stream that must *not* be re-issued.

**That fix is not validated live.** The backend serving run 2 was started with
the broken first version and this backend has no `--reload`, so the correction
exists only on disk and in unit tests. It should be exercised by the next cohort.

## A region trap, hit for the second time

The first attempt at this re-measurement concluded `gemini-3.7-flash` was
unavailable — 404 `NOT_FOUND`. It was not: `AIOS_GEMINI_LOCATION` defaults to
`us-central1`, and every 3.x model is served only from `global`.

`aios/core/gemini.py:53` already documents this, including that it *"cost a full
golden cohort (0/5, every step unverified) before the 404 body was read."* The
same trap has now cost two measurements. The comment is in the right place; it
simply was not read before the 404 was believed.

## What organ 44 would need

Not another roll of the same dice:

1. **Quota headroom** — a window where the project is not already throttled, so
   the run measures the system rather than the rate limiter.
2. **The corrected retry running live**, so a transient 429 no longer ends a
   mission that was otherwise proceeding.
3. ~~The cold-start question answered.~~ **ANSWERED, and the hypothesis above was
   wrong** — see the run 3 addendum below.

Until then the honest position is the one the ledger already records: organ 44 is
yellow, and its `requires_live_evidence` is true because a golden cohort is
precisely the kind of proof the gate's own test run cannot produce.

---

# Addendum — run 3, with the corrected retry live

**Result: `[5, 4, 2]` = 11/15 (73%). Organ 44 still yellow.**

Run with `stream_with_backoff` live for the first time.

| | Cohort | Total | 429s absorbed | 429s that killed a mission |
| --- | --- | ---: | ---: | ---: |
| Run 1 | `[3, 5, 5]` | 87% | 0 (no retry existed) | 2 |
| Run 2 | `[3, 4, 3]` | 67% | 0 (retry wrapped the wrong thing) | 7 |
| Run 3 | `[5, 4, 2]` | 73% | **4** | **0** |

## The retry works

Four throttles absorbed, **zero reached the agent**. Every 429 that would
previously have ended a mission was retried in 0.5-1.0s and the mission
continued. Infrastructure failures went to zero.

## The cold-start hypothesis was wrong, and is withdrawn

The body of this document proposed that repeat 1 might be genuinely weaker — no
memory, no verified skills, nothing warmed — because it scored 3/5 in both
earlier runs.

**Run 3's repeat 1 scored 5/5**, the first clean repeat of the whole exercise.
The earlier repeat-1 weakness was not cold start: the first repeat was simply
absorbing the first throttles, and once those were retried the fresh instance
performed like any other. Recorded as a correction rather than edited away,
because the wrong hypothesis is the more useful thing to have on file.

## A second product defect, found because the retry refused to hide it

One repeat-3 mission died on:

```
400 INVALID_ARGUMENT. Please ensure that the number of function response parts
is equal to the number of function call parts of the function call turn.
```

`_to_gemini` emitted a `function_call` with no answering `function_response`
whenever a tool call was **refused** — which in this system is the supervision
mechanism, not an edge case — and split multiple results across separate turns.
Fixed and mutation-checked; every call is now answered in the turn that made it.

It surfaced precisely *because* the retry classified 400 as permanent and failed
fast instead of burying it under three backoffs.

## What remains is the model

With infrastructure out of the way, the residual failures are reproducible model
errors on the missions themselves:

* **exception-type mismatch** — writes `raise ValueError("Cannot divide by
  zero")`, then tests `pytest.raises(ZeroDivisionError)`. Seen twice.
* **invalid syntax** — emits Python that will not parse, so pytest cannot even
  collect the file.
* **introspection replays** — writes throwaway tests (`test_tmp_inspect`,
  `test_temp_check`, `test_introspect`) that `print(...)` then `assert False` to
  dump state through the failure output, including one ROT-13 encoding both
  source files.

The introspection behaviour was investigated as a possible capability gap on our
side. It is not: `read_file` is exposed to the agent, reads are GREEN, and it
returns file contents correctly. The agent has a working read path and does not
use it. The loop also gives real feedback — 4 to 8 verification attempts with
full pytest output per failing step — so these are not cases of the model flying
blind.

Nothing here is honestly fixable from our side. Feeding the agent the file
contents the mission deliberately withholds, or relaxing the verifier, would be
tuning the evaluation rather than improving the system.

---

# Addendum — run 4: `[5, 5, 5]`, and organ 44 goes GREEN

**Result: `[5, 5, 5]` = 15/15 mission runs (100%). The bar is met.**

- **Measured**: 2026-09-02, `gemini.gemini-3.7-flash` via Vertex (`global`)
- **Repeats**: 3, each a fresh instance (own port, own `AIOS_DATA_DIR`, own enrollment)
- **Duration**: 55.7 minutes of live cloud calls; fastest mission 37.7s, slowest 565.6s
- **Bar**: three consecutive clean 5/5, declared before the 2026-08-19 runs

```
[golden] FINAL: 15/15 mission runs passed (100%)
```

## The structural checks, not just the number

A 5/5 is only worth something if the evaluation could still have produced
anything else. The same checks that qualified the 2026-08-19 cohort:

| check | run 4 |
| --- | --- |
| scored steps | 27 (9 per repeat) |
| **`verified_failure` per repeat** | **1, 1, 1** |
| outcome taxonomy | 24 `verified_success` + 3 `verified_failure` = 27 |
| `FAIL:` lines | 0 |
| approval refusals / loop trips | 0 |
| tracebacks | 0 |

The `verified_failure` count is load-bearing. The TDD mission requires the model
to write a **failing** test before the implementation exists; had anything
flattened the evaluation into success, that count would read 0. It reads exactly
1 per repeat, matching the original evidence.

## What the two fixes can and cannot claim

Both were live — verified by process start time, not assumed. `provider_retry.py`
was written at 20:34:30, the `_to_gemini` pairing fix at 21:51:24, and the serving
backend started at **22:10:24**. (This backend has no `--reload`; run 2 was
measured against a stale process serving the broken first version of the retry,
which is how that error stayed hidden for a whole cohort.)

**Neither fix can take credit for this score, and the record should not imply
otherwise:**

* **The retry never fired.** Zero 429s, zero backoffs, across 55.7 minutes. This
  run had quota headroom; runs 1-3 did not. The honest reading is *measured in a
  clean window*, not *the fixes lifted the score*.
* **The pairing fix was never provoked.** Zero refusals means no turn ever
  produced an unanswered `function_call`, so the 400 could not recur. Its proof
  remains the unit tests and the mutation check, not this cohort.

What the fixes bought is that a throttle or a refusal would no longer have ended
a mission. Nothing in run 4 demanded that insurance.

## No introspection replay

Runs 1 and 3 saw the agent build a read primitive out of the verifier — throwaway
tests that `assert False` to dump file contents through pytest's failure output,
once ROT-13 encoded. Run 4 produced no such artifact. The `test_tmp_inspect.py`
and `test_temp_check.py` files in `training_ground/` are leftovers from the
earlier runs (mtimes 19:48 and 21:46, both before this backend's 22:10 start).
`data-pipeline`'s 565.6s was slow legitimate work, not the assertion channel.

The containment observation from run 1 stands on its own and is **not** retracted
by this run: pytest assertion output remains an unmonitored read channel out of
the verifier. An agent found it unprompted once. It simply was not used here.

## The commit this is stamped at, and why that needed proving

The cohort executed at `951e4ae6`, the tip of `fix/provider-retry-backoff` — not
at master. This repository squash-merges, so after #288 landed, `951e4ae6` is not
an ancestor of master, and C12 requires `last_verified_sha` to be one. Stamping
the branch commit would fail the gate; stamping the squash commit as though the
run happened there would be a claim the run does not support.

Resolved by proving the two commits carry the same code:

```
master   af268809  tree 0022ceca78b1e3641f6a593ccabc5224ab272745
measured 951e4ae6  tree 0022ceca78b1e3641f6a593ccabc5224ab272745
```

The tree hashes are identical, so the code that was measured **is** master's
code, and the row is stamped `af268809` with the execution commit recorded in its
own text. That check also discharges the squash-drop risk this repo hit on #269,
where a squash silently lost a commit: both fix commits demonstrably survived.

Had the trees differed, organ 44 would have stayed yellow pending a re-run at the
tip. The check is the reason the stamp is honest, not a formality around it.

## What this does and does not establish

It establishes that GAGOS completes its five golden missions, three times
consecutively, against a live cloud model, at the code currently on master, with
the TDD red phase intact and no infrastructure assistance.

It does not establish that it does so under throttling. Runs 1-3 are the record
of what happens then — 87%, 67%, 73% — and they remain in this document.
