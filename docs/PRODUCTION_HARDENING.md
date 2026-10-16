# Production hardening — the bar, measured

*Started 2026-10-11 at the operator's request: "honest hardening, worthy
enough, for cage + animal, clerk / one law, sovereign / local-first, cloud +
local intelligence — all production hardened ready."*

**The check is the claim.** Readiness is whatever this prints on the
operator's machine, and nothing else:

```
python tools/production_readiness.py          # add --json for machine output
```

## What "production" means here

- **One operator, this machine, all the time.** GAGOS runs the production
  profile (Docker Compose: API, executor, gateway, monitoring) on the
  operator's Windows laptop. It stays up across crashes (restart policies)
  and reboots (start at login).
- **Local model first.** Cloud models are optional brains; nothing requires
  them.
- **Not a multi-tenant server.** Nothing here claims otherwise.

## The four states

| State | Meaning |
|---|---|
| PASS | Measured, and the bar is met. |
| FAIL | Measured, and it is not. The evidence says why. |
| ERROR | The probe broke, so nothing was measured. It is never read as either verdict. |
| NOT_MEASURED | Nothing has measured it yet: no probe exists, or its instrument produced no measurement (a drill never run here, or one that never reached what it tests). Named, with the step that would measure it. |

Ready means every gate is PASS.

The drill gates read `<data>/drills/sovereignty.json`, which
`python tools/sovereignty_drills.py` writes (Ollama needed, no cloud key: the
drill controls the cloud transport itself). A drill that never reached what it
tests is NOT_MEASURED, never PASS.

## The gates

| Pillar | Gate | The bar |
|---|---|---|
| Cage | `v1_check` | `gagos v1-check` ready in this machine's environment: executor, staged workspaces, verification, promotion all proven |
| Cage | `organ_ledger` | every organ green |
| Cage | `nightly` | the last 3 nightly runs green |
| Cage | `master_ci` | master's latest CI green |
| Animal | `signing_key` | the live learning key present (env or the OS keystore, by name only) and its public key pinned (otherwise everything learned is refused) |
| Animal | `guards_scheduled` | the red-team reel and mutation probe run on a schedule |
| Animal | `usefulness` | what the animal learned reaches a live turn (a read-only census through the production recall gate: rows admitted to their owner) **and** the pre-registered Phase 8 run met H1 under Holm (`docs/learning/payoff_judged_result.json`) |
| Clerk | `admitted_model` | a local model the dispatcher would give a job (approved, qualified, healthy, with a role) |
| Clerk | `live_roles_earnable` | every role production code asks the clerk for is one a qualification test can grant |
| Clerk | `real_jobs` | the clerk has done real jobs, recorded in its provenance store |
| Clerk | `one_gateway` | every production model call on this machine in the last 7 days passed an Organ 32 gateway entrance, read from the model-call ledger (`docs/ONE_GATEWAY.md`) |
| Sovereign | `production_started` | the production launcher has run here |
| Sovereign | `backend_ready` | the backend answers its readiness probe |
| Sovereign | `backups` | a restorable backup newer than the staleness limit |
| Sovereign | `compose_local_model` | the production container can reach the host's local model |
| Sovereign | `compose_keys` | the production container receives its keys |
| Sovereign | `offline_drill` | the last drill run here passed `offline` within 7 days: a turn served by the local model with the network cut |
| Sovereign | `privacy_drill` | the last drill run here passed `privacy` within 7 days: no credential or local path in what the cloud transport received |
| Intelligence | `local_model` | the configured local model is served |
| Intelligence | `cloud_provider` | at least one cloud provider's key present for production (env or the OS keystore, by name only) |
| Intelligence | `failover_drill` | the last drill run here passed `failover` within 7 days: cloud failing → the local model answers |

## First measurement — 2026-10-11, master `ae778527`

**NOT READY: 2 of 21 gates pass** (`master_ci`, `local_model`). Read-only,
and the live data directory was verified unchanged after the run.

Findings, each from the measurement or from reading the code:

1. **The production profile has never run on this machine.** There is no
   launcher state and no launcher log. Docker Desktop is installed but stopped.
2. **Even if it ran, production has no local model.** In the `aios` container,
   `OLLAMA_HOST` defaults to `127.0.0.1:11434`, which is the container itself,
   not the host's Ollama. Local-first is broken in exactly the profile meant
   to be production.
3. **The production container is never given its keys.** These include the
   verification key (promotion refuses without it), the learning key
   (everything learned is unsigned and refused) and any cloud key.
4. **`v1-check`: 12 of 17 gates pass, all at fixture level.** The 5 failures
   are the execution cage: no container runtime and no verification key.
5. **The clerk has never done a job.** 0 of 13 local models are admitted. The
   only operator-approved one (`qwen2.5:1.5b`) failed qualification on
   2026-08-03: it attempted one authority mutation and accepted one tool
   request. That is the gate working.
6. **The clerk's one live job can never be granted.**
   - The only production code that calls the clerk asks for `select_skill`.
   - Qualification can grant only extract, classify, summarise and cluster.
   - So that job always escalates to the cloud, however good the model.
7. **No restorable backup exists.** The files in `data/backups` are ad hoc
   database copies that recovery cannot restore. Nothing schedules backups.
8. **The nightly has been red since 2026-10-07 with no backend change.** The
   endurance gate read a weak CI model as a broken backend (fixed in H1).
9. **51 of 59 organs are green.** Not green: 20, 40, 44, 46, 48, 49, 51, 55.

Found the same day while building H3 to H5, by reading code and reproducing:

10. **The clerk's live job could not have succeeded even with a role.**
    - Its prompt embedded an example answer that already said
      `"applicable": true`, and it gave the clerk none of the skill's criteria.
    - It declared a 3-field output schema while asking for 7 fields. The job
      runner refuses extra fields, so an obedient model was always refused.
    - Four roles had qualification tests all along but were never mapped.
11. **A backup could not be taken while GAGOS runs.**
    - On Windows it failed outright: `PermissionError` on SQLite's locked
      sidecar file.
    - Where it succeeded, the databases were copied raw beside a `-wal`
      captured at another instant, and each file was read twice (hash, then
      archive).
12. **The production compose had never been exercised on Docker Desktop for
    Windows.** The open questions are listed in `docs/PRODUCTION_BRING_UP.md`
    (H3), and the drill exists to answer them.

## The slices

Each is its own PR: tests verified to fail without the change, the full
suite green, organs re-gathered at master's tip after any squash. "Operator"
marks steps only the operator can take on his own machine.

| Slice | What | Moves |
|---|---|---|
| **H1** | Endurance gate scores a model's failure as a failed turn, not a broken backend; CI pins one Ollama image | `nightly` |
| **H2** | This scoreboard and this document | the measurement itself |
| **H3** | Production bring-up: keys in Windows Credential Manager (operator decision 2026-10-11) → launcher → containers; the container reaches the host's Ollama; AGENTS.md §VII.4 amended for that one store. Operator: start Docker Desktop at login, store the keys, `gagos start --profile production` | `compose_*`, `production_started`, `backend_ready`, `v1_check`, `signing_key`, `cloud_provider` |
| **H4** | Clerk alive: an operator CLI to approve and qualify a model (his act); a qualification test for `select_skill`, or live callers for the roles qualification can grant (classify, summarise: the README's clerk); qualify `qwen2.5:3b` | `admitted_model`, `live_roles_earnable`, `real_jobs` |
| **H5** | Backups safe while GAGOS runs (SQLite snapshots), on a daily schedule the operator installs, plus a restore drill | `backups` |
| **H6** | Live drills: offline, privacy, cloud failover | three `*_drill` gates |
| **H7** | One law: the constitution is the ceiling on cloud egress; effective cloud tasks = constitution ∩ runtime profile (operator decision 2026-10-11) | correctness, no gate |
| **H8** | Best cloud + local intelligence, measured: only callable models ranked, Kimi K3 usable, a 50-task benchmark as the router's prior (`docs/BEST_INTELLIGENCE.md`) | correctness, no gate |
| **H6b** | This scoreboard reads the drill report and the OS keystore (until then, keys stored as the bring-up guide says still read FAIL) | three `*_drill` gates, `signing_key`, `cloud_provider` |
| **H10** | One gateway, measured: a model-call ledger written by every provider adapter, a real-app inventory (62/62 calls gated; it found `/api/v1/plan` ungated and `/api/v1/chat` 500ing on "what is…"), the gate reading this machine's ledger (`docs/ONE_GATEWAY.md`) | `one_gateway` |
| **H11** | Usefulness, measured: a read-only census of what learned memory reaches a live turn, and the judged Phase 8 payoff result (`docs/learning/payoff_judged_result.json`) | `usefulness` |
| next | Learning-guards on a schedule (operator: CI minutes) | `guards_scheduled` |
| **H9** | The 8 yellow organs, each against its named blockers | `organ_ledger` |

**What hardening cannot do:** make the learning loop *useful*. Hardening
makes it safe, observable and reversible. Whether it helps is a measurement
(H8), and it is reported whatever it says.
