# Organ 44 — the first endurance measurement

**Date:** 2026-08-16
**Verdict:** RED — `success_rate 0.611` against a `0.80` bar.
**Machine:** laptop, live Gemini (`gemini.gemini-2.5-flash`) via Vertex ADC,
real containerised pytest (`aios-worker:local`), Docker 29.5.2.

Organ 44 is *"Golden Mission **and Endurance** Evaluation"*. Until today only
the golden half had ever produced a number. This is the first time the
endurance half has executed at all.

## The result

Computed with the harness's own authority
(`GoldenMissionEnduranceAuthority.evaluate_endurance`), not by hand:

```
duration covered : 1794.5s of the 1800s window
turns            : 18
outcomes         : verified_success 11 | verified_failure 5 | unverified 1 | error 1
success_rate     : 0.611          (threshold 0.80)
latency p50/p95  : 100.06s / 178.92s   baseline_p95 100.92s
latency_stable   : True            (p95 <= 2x baseline)
GREEN            : False
```

**Latency is the good news and it is not a small one.** p95 of 178.92s against
a 100.92s baseline is inside the 2x bar, across half an hour of sustained load
with no upward drift. Memory stability could not be sampled (`memory_mb` is
`None` throughout — a separate gap, recorded below rather than glossed).

The failing 39% is not the harness. It is the model's own tests disagreeing
with the model's own code:

```
DID NOT RAISE ValueError          chunk_list(items, size) with size < 0
assert False == True              is_palindrome('123ab321')
assert 0 == 3                     count_vowels('h3ll0 w0rld!')
```

The same shape the golden cohort shows: the model writes a test asserting an
edge case, then writes an implementation that does not satisfy it.

## Why this took four attempts, and what each one found

Every attempt failed differently, and three of the four failures were real
defects rather than noise. Recorded because "we ran it and it was red" would
hide the more useful finding: **the harness had never been capable of
completing its own default duration.**

| # | Died at | Cause | Verdict |
|---|---|---|---|
| 1 | turn 0 | `requests.post` with no session, no CSRF, no 428 replay | real defect — endurance could never have run once |
| 2 | turn 6, 15.0 min | `401` — the 900s privileged window lapsed | real defect |
| 3 | turn 6, 9.6 min | `ConnectionReset` — I killed the backend | my process handling, not a system fault |
| 4 | turn 18, 29.9 min | `400` on the post-refresh retry | real defect, still open |

### Attempt 2 — the 15-minute wall

`aios/application/identity/service.py` records the reauthentication event with
`expires_at = time.time() + 900`. The harness defaults to
`--duration-minutes 30`. **No endurance run could ever have completed its own
default duration**, regardless of how well the system behaved — which is worth
stating plainly, because "error recovery / graceful handling of transient
failures" is one of the four things endurance claims to measure.

Fixed in the client, not the server. The 900s window is a real control and
widening it to make a test pass is the trade this repo refuses.

### The fix that was wrong, and how it was caught

The first attempt at that fix called `/api/v1/auth/reauth` alone. It looked
sufficient. The backend log disagreed, on consecutive lines:

```
POST /api/generate        401 Unauthorized
POST /api/v1/auth/reauth  401 Unauthorized
```

By the time the privileged window has lapsed the *session* has lapsed with it,
so reauth has nothing to attach to. The corrected refresh does `login` then
`reauth` — the same two steps `bootstrap()` always performed.

The unit tests had passed against the wrong version, because they mocked
`_post` to return one status for every auth call and so could not tell login
from reauth. They now take `login_status` and `reauth_status` separately and
assert on call **order**. That is the difference between testing that something
was called and testing that the right things were called in the right order.

Proof it worked, from this run's backend log:

```
POST /api/generate        401 Unauthorized
POST /api/v1/auth/login   200 OK
POST /api/v1/auth/reauth  200 OK
POST /api/generate        200 OK          <- recovered, ran 15 more minutes
```

## Open defects this run exposed

1. **`400` on the post-refresh retry.** The second refresh authenticated
   cleanly (`login 200`, `reauth 200`) and the retried `/api/generate` returned
   `400`, killing the run on its final turn. The first refresh in the same run
   returned `200` and recovered, so this is not the refresh itself. Most likely
   a request bound to the pre-refresh session (an approval token or CSRF value)
   being replayed against the new one. **Not yet diagnosed.**
2. **`memory_mb` is `None` for every turn.** Memory stability is one of the four
   advertised measurements and it is silently absent, not failing. A metric
   that reports `None` forever looks like data until someone checks.
3. **The harness can only run once per instance.** `ProbeSession` enrolls once
   and the credential is a one-time secret; a second run against the same
   instance dies with "an operator is already enrolled". `AIOS_OPERATOR_CREDENTIAL`
   is documented nowhere in the repo. Worked around here by capturing the
   credential at enrollment; the durable fix is auth ergonomics and is the
   operator's call.

## What this does and does not settle

It **discharges** the blocker "endurance has not been run and still carries the
authentication defect". Endurance now runs, and has a number.

It **does not** make organ 44 green, and replaces one blocker with a smaller,
better-specified one: endurance measures 0.611 against a 0.80 bar. Organ 44
stays yellow, correctly.

Earlier in this session I reported endurance as "GREEN" from a 2-turn sample.
That was too small to support the claim and this supersedes it. The three
truncated runs (0.50 and 0.67) are likewise not results — they were cut short
by the defects above and are recorded here only so they are not mistaken later
for measurements.

## Reproduce

```
docker compose --profile build-only build worker
AIOS_DATA_DIR=<fresh> AIOS_GEMINI_PROJECT=<project> python -m aios     # detached
# enroll once, capture enrollmentCredential -> AIOS_OPERATOR_CREDENTIAL
python tools/endurance_tester.py run --duration-minutes 30 \
    --cooldown-s 5 --model gemini.gemini-2.5-flash
```

Turn-level evidence: `.aios/audit/endurance-test.jsonl` (`endurance-turn` rows
carry `outcome`, `latency_s` and, since this session, the `[VERIFY ...]`
evidence and failure reason that made the assertions above readable at all).
