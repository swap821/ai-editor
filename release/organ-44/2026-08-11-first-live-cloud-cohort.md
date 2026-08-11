# Organ 44 — first live cloud golden cohort, and what it cost to get one

**Date:** 2026-08-11 · **Provider:** Google Gemini via Vertex AI
(`gemini-2.5-flash`, project `ai-editor-498414`, ADC) · **Result:** 0/5

## The residual was wrong

Organ 44 has carried this for months:

> *"Outside-machine — cloud-provider credentials barred; cannot invent cloud
> golden-cohort live evidence"*

Credentials were never the blocker. Three separate things were, and none of
them was a missing key:

**1. Gemini already worked.** `aios/core/gemini.py` was built for exactly the
laptop's `gcloud` ADC via Vertex. It was disabled solely because
`AIOS_GEMINI_PROJECT` was unset — `GEMINI_ENABLED = bool(GEMINI_PROJECT and
GEMINI_MODEL)`. Setting the project id turned it on with no code change:

```
GEMINI_ENABLED: True | project: ai-editor-498414 | model: gemini-2.5-flash
LIVE RESPONSE: 'LIVE'
```

**2. The runner could not authenticate at all.**
`tools/golden_mission_runner.py` sent no bearer token, no Origin, no session,
no CSRF. Every turn died before reaching a model:

```
403  Mutation requires a bearer token or a valid session, exact Origin,
     and session-bound CSRF proof
```

It was written when `/api/generate` was open. The API was secured afterwards
and nothing re-ran the driver, so organ 44's own production entrypoint had
been non-functional for as long as the API has been secure. Even with perfect
cloud credentials it could not have produced a single turn.

Establishing what the API actually wants took driving the real middleware
in-process rather than reading the code:

```
bearer only              -> 400  Host header is not configured for this API
bearer + origin + host   -> 401  authenticated operator session required
```

A bearer token was never sufficient. `/api/generate` needs a real operator
session: enroll -> login -> **reauthenticate** (a fresh reauth event on a
rotated session is required before any control-plane mutation) plus CSRF, plus
replaying the 428 capability challenge with the server-issued token.

**3. The model id silently routed to the wrong provider.**
`router_wiring.py` dispatches on a `gemini.` prefix — with a dot.
`gemini-2.5-flash` does not match it, falls through every branch, and lands on
the Bedrock default:

```
503 {"detail":"cloud model selected but AWS Bedrock is not configured"}
```

That error would have sent an operator to fetch a Bedrock key they did not
need. The correct id is `gemini.gemini-2.5-flash`.

## What now works

```
enroll -> login -> reauth -> session established
POST /api/generate -> 200
event: turn.started  {"mode":"conversation","phase":"chemotaxis",...}
event: alignment     {"goal":"acknowledge readiness","intent":"discuss",...}
```

Real operator session, real capability protocol, real Vertex call, streaming
turn. `aios/probe_session.py` performs the bootstrap over HTTP and
**deliberately refuses to invent a credential** — it fails loudly when an
operator is already enrolled, which is how the pre-existing enrollment on this
machine was discovered rather than silently impersonated.

## The cohort

Five golden missions, eight steps, ~14 minutes of live Vertex calls.

| Mission | Steps | Outcome |
|---|---|---|
| tdd-workflow | 2/2 | FAIL — `got=error` |
| iterative-refinement | 1/2 | FAIL — `got=error` |
| multi-module | 1/2 | FAIL — `got=verified_failure` |
| error-handling | 1/1 | FAIL — `got=rejected` |
| data-pipeline | 1/2 | FAIL — `got=verified_failure` |

**FINAL: 0/5 (0%)**

Raw log: `release/organ-44/2026-08-11-gemini-cohort.log`.

## Reading this honestly

Two separate claims live in this result and must not be collapsed:

**The harness works.** It executed five missions against a live cloud
provider, distinguished three different failure modes (`error`,
`verified_failure`, `rejected`), and reported 0/5 without inventing a single
success. C5 says *"runner does not invent cloud success without real
providers"* — this is that condition being satisfied under load rather than
asserted. The differentiated verdicts matter: a uniform 0/5 would suggest one
systemic plumbing fault, whereas three distinct outcomes across eight steps is
an evaluator actually evaluating.

**The system fails its own golden missions on this model.** 0/5 on
`gemini-2.5-flash`. Whether that is the model, the mission definitions, the
verifier's strictness, or the agent loop is not established by this run and is
not claimed here.

## Why organ 44 is still yellow

Green would assert the evaluation organ functions. It now does, for the first
time. But a reader seeing `status: green` on "Golden Mission and Endurance
Evaluation" would reasonably infer the golden missions pass, and they do not.
Flipping it on a 0/5 would be exactly the kind of technically-defensible,
practically-misleading green this ledger exists to prevent.

The residual is rewritten to say what is actually true instead of the
credentials story, so the next person starts from the real position:

* the harness runs, live, against a real cloud provider
* it scores 0/5 and the cause is not yet established
* endurance (`tools/endurance_tester.py`) has not been run and still carries
  the same auth defect this fixed for the golden runner
* nothing here is CI — this is a laptop run, and the residual still says so

## Reproduce

```
AIOS_GEMINI_PROJECT=ai-editor-498414 \
AIOS_API_TOKEN=<token> \
AIOS_DATA_DIR=<clean dir> \
AIOS_OPERATOR_CREDENTIAL=<enrollment credential> \
python tools/golden_mission_runner.py run --model gemini.gemini-2.5-flash
```

The credential is one-time material returned by `/api/v1/auth/enroll`. It is
held in memory by the driver and written nowhere in the repo.
