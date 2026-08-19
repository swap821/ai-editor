# Organ 44 — blocker 2, the cohort runs off the author's laptop

2026-08-19. Operator decision: close blocker 2 against the claim it actually
made, and carry cloud-score reproduction separately as non-blocking future work.

## What blocker 2 claimed

> The honest content of this blocker is not that the numbers are wrong but that
> every organ 44 figure was produced on ONE laptop, so nobody else could re-run
> any of it.

That is a reproducibility claim about the **harness**, not a claim that CI must
reproduce a cloud score.

## What now runs, on a machine that is not the author's

`golden-cohort-local` (`.github/workflows/ci.yml`, `workflow_dispatch`) starts a
real Ollama daemon, pulls and **warms** a model, builds `aios-worker:local`,
starts its own backend on its own port with a fresh `AIOS_DATA_DIR`, enrolls an
operator, and drives the real `tools/golden_mission_runner.py` through a golden
mission.

Verified end to end, run `32232677594`, 5 minutes:

```
[golden] mission=tdd-workflow: Full TDD cycle: write failing test, implement, verify green
    FAIL: got=unverified expected=verified_failure
[golden] FINAL: 0/1 mission runs passed (0%)
  score 0/1 (reported, NOT gated)
  1 step invocation(s) reached the model
harness integrity: OK
```

No missing image, no docker-reserved exit code, no allowlist refusal, no
provider error. The model was reached and answered; a 0.5b model simply did not
produce a verifiable artifact. **That is model weakness, and the gate passed
it** — which is the entire design.

## The gate is demonstrated in BOTH directions

A gate only ever seen passing is not evidence. This one has now been observed
doing each job on a real run:

| run | condition | verdict |
|---|---|---|
| `32221824132` | Ollama timed out (infrastructure) | `harness integrity: FAILED` |
| `32232677594` | 0.5b model scored 0 (model weakness) | `harness integrity: OK` |

Same code, opposite verdicts, for the right reasons.

## Five defects, each hidden behind the last

The job had existed and reported nothing useful. Every one of these surfaced
only by actually dispatching it:

| | defect | consequence |
|---|---|---|
| 1 | dispatch-only, so `skipped` on every push — **never executed once** | the ledger claimed CI coverage that had never run |
| 2 | never built `aios-worker:local` | every verify died at `exit 125`; gate said OK |
| 3 | build step added, compose vars missing | the build never started |
| 4 | build worked, model never warmed | first turn exceeded `AIOS_LLM_TIMEOUT_S` |
| 5 | warmed, but 3b too slow | 27 minutes, zero steps, cancelled at the cap |

Defect 2 is the one worth remembering: **the integrity gate passed a run that
proved nothing**, because a missing container image looked like a low score.
That is the exact confusion the gate exists to prevent, occurring inside the
guard against it. It is now pinned by the verbatim log, and by the counterpart
assertion that `exit 1` — a test the model genuinely failed — must still pass.

## What CI does NOT do, stated plainly

* It does **not** reproduce any organ-44 score, cloud or local. The 0.5b model
  is not asked to be good and its score is reported, never enforced.
* It does **not** run the cloud cohort. That needs a Workload Identity
  Federation pool bound to this repo — an IAM action on the operator's Google
  account that no agent can or should perform.

Cloud-score reproduction is recorded as **future work, not a blocker**: the
organ's contract is to evaluate golden missions and endurance, and it does, with
measurements anyone can now re-run. Reproducing a specific cloud number inside
CI is infrastructure convenience, and holding the organ yellow for it would be
holding it against a claim it never made.

## Why four rows are OPERATOR-ATTESTED and one is not

C10 requires every `proof_level=live` row to resolve as a `release/phase4`
artifact, a `tests/foo.py::test_bar` node, an `actions/runs/<id>` run, or an
explicitly declared `OPERATOR-ATTESTED` observation.

**Organ 44 cannot carry a phase4 artifact.** `scripts/phase4_live_evidence.py`
says so in its own docstring — *"Ollama / Outside-machine / frozen / browser /
Phase-6 organs are not claimed here"* — and contains zero references to organ 44.
So a laptop measurement has no machine-derivable anchor, by design.

That leaves exactly one machine-checkable route for this organ: a CI run. The
row citing run `32240063690` takes it. The four laptop rows are declared
`OPERATOR-ATTESTED`, on the operator's decision of 2026-08-19.

Two things were refused along the way:

* **Marking a 0/5 run "passed"** in a fabricated phase4 artifact to make it
  checkable. The 2026-08-11 rows record real failures and are deliberately
  retained; laundering them into a passing artifact would have destroyed the
  only thing they are good for.
* **Declaring `OPERATOR-ATTESTED` on the operator's behalf.** It is his
  signature. The verifier prints how many rows rest on attestation on every run,
  which is exactly the kind of number that should be visible rather than
  inferred — and the CI row's prose was reworded because merely *mentioning* the
  token inflated that count from 4 to 5.

## The run had to be made citable first

`_github_run_verifier` requires a cited run to have **succeeded**. Every
`workflow_dispatch` run concluded `failure`, because `release-strict-gate` shares
that trigger and is structurally red outside a release cut — so the cohort
evidence produced inside those runs could never be cited. Fixed by making that
gate advisory on dispatch and blocking on release tags, which is where tip
equality is the actual claim.

Run `32240063690`: `conclusion=success`, `head_sha=0b52e320`, matching the
evidence row's `commit_sha` and the organ's `last_verified_sha`.
