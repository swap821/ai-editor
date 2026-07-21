# Mission Origination — chat → council, end-to-end (deliberate → approve → act)

Date: 2026-06-28
Status: Approved (operator; dashboard-form frontend)
Branch target: `council-runtime-v01` → fast-forward `master` on green

## Goal

Let a goal originate a real Council mission over HTTP and carry it through the full
loop under human supervision: **deliberate → King approves → worker acts → report**.
Closes the last gap ("nothing originates a mission from the product").

## Approval model (operator decision)

**Deliberate → approve → act.** The worker edits files ONLY after the King
approves. Origination runs deliberation only; approval triggers execution.

## Non-goals (YAGNI)

- Routing the main GAGOS chat box to council via intent detection (needs a
  scope-picker UX + classifier) — follow-up. This slice uses a dashboard form.
- SSE streaming of council progress (the dashboard already polls).
- Multi-file / cross-repo missions (single target file, as the worker slice).
- Changing the frozen security spine.

## Architecture — split the orchestrator into two phases

Today `CouncilOrchestrator.run()` deliberates AND executes in one coroutine. Split:

- **`deliberate(request) -> CouncilRun`** — claim the mission (atomic
  `claim_mission`), run Planner/Security/Memory, apply council context, persist
  verdicts/events. Write the ledger + a King report with status
  **`awaiting_approval`** (passed) or **`blocked`** (deny/defer). NO worker spawn.
- **`execute(contract, verdicts) -> CouncilRun`** — `spawner.run(contract,
  claim=False)` (deliberate already claimed) → Testing → enriched ledger → final
  King report. Persists worker_spawned/testing/report events.
- **`run(request)`** = `deliberate()` then `execute()` when not blocking → existing
  behavior + tests unchanged.

`WorkerSpawner.run(contract, *, claim: bool = True)`: default claims (direct use,
collision guard intact); the execute phase passes `claim=False` because deliberate
already claimed the mission dir. `_blocked_run` no longer claims (deliberate does).

`king_report.build_deliberation_report(contract, verdicts)`: a pre-execution
KingReport — status `awaiting_approval` (or `blocked` when a blocking verdict
exists), `approval_needed=True`, council summary from the verdicts, no worker files.

## The two-phase HTTP flow (fire-and-forget + poll)

1. **`POST /api/v1/council/missions`** (origination) — body
   `CouncilMissionOriginationRequest` `{goal, allowedFiles, workspaceRoot?,
   forbiddenFiles?, verificationCommands?, riskLevel?}`. Generates `mission_id`,
   schedules `deliberate()` via FastAPI `BackgroundTasks`, returns
   `{missionId, status: "deliberating"}` immediately. Dashboard polls
   `/missions/{id}` → verdicts + `awaiting_approval`/`blocked`.
2. **`POST /api/v1/council/approve`** (existing, extended) — on approving a mission
   whose stored report status is `awaiting_approval`, schedule `execute()` in the
   background (read the stored ledger → contract + verdicts). Reject → no execution.

## Safety (fail-closed, non-negotiable)

- **Scope explicit + validated, never LLM-inferred.** `allowedFiles` required +
  non-empty; each entry relative and confined to `workspaceRoot` (resolve-within-
  base, the same check used elsewhere); reject `..`/absolute/escaping entries.
  `workspaceRoot` defaults to `config.COUNCIL_WORKSPACE_ROOT` and must resolve
  inside it. RED `riskLevel` accepted into the contract but execution still
  honors RED policy (gateway forces local; King must approve; nothing auto-acts).
- Reuses the reviewed stack: narrow-only Planner, scoped `write_file`, allowlisted
  `run_command`, secret-scrubbing gateway, worker verification-required honesty.
- Behind `require_api_token` (global) AND **`AIOS_COUNCIL_ORIGINATION`** (default
  off → endpoint returns 404). Origination rate-limited per session like chat.

## Components

- `aios/council/council_orchestrator.py`: `deliberate()`, `execute()`, refactor
  `run()`, claim move.
- `aios/runtime/spawner.py`: `run(..., claim=True)`.
- `aios/runtime/king_report.py`: `build_deliberation_report`.
- `aios/config.py`: `COUNCIL_ORIGINATION` (default False), `COUNCIL_WORKSPACE_ROOT`
  (default `DATA_DIR/council_workspace`).
- `aios/api/main.py`: `CouncilMissionOriginationRequest`, `POST /council/missions`,
  extend `_write_council_decision`/`council_approve` to trigger execute, a
  `_validate_mission_scope` helper, a `get_council_workspace_root` dep.
- `frontend/src/workbench/CouncilDashboard.{jsx,css}`: an origination form (goal +
  allowed files) posting to `/council/missions`, plus a test.

## Error handling

- Background `deliberate`/`execute` failures: caught, persisted as a `failed`
  report + `council_event` (the poll surfaces it); never crash the server.
- Invalid scope / empty allowedFiles → 422 before scheduling.
- Approving an already-executed or blocked mission → no-op execute (idempotent
  guard on report status), still records the decision.
- Flag off → 404 on origination.

## Testing (deterministic)

- Orchestrator: `deliberate()` → awaiting_approval (pass) / blocked (deny, via a
  denying fake SecurityQueen); `execute()` after deliberate runs the worker with
  `claim=False` (no collision) → completed; `run()` unchanged (regression);
  collision guard still fires for direct double `spawner.run`.
- API (TestClient, deps overridden, flag on): originate → 200 + mission_id, report
  becomes awaiting_approval; approve → schedules execute (stub spawner / deterministic
  worker) → completed; reject → no execution; empty/escaping allowedFiles → 422;
  flag off → 404.
- Frontend: origination form posts the correct payload; existing dashboard test
  unaffected.
- Full backend suite + 85% floor; frontend tests + build; frozen spine untouched.

## Rollout

Off by default (`AIOS_COUNCIL_ORIGINATION=false`). Enabling it (with `WORKER_REASONING`
for real edits, or deterministic otherwise) gives: dashboard form → deliberation →
King approval → worker acts → King report — the supervised end-to-end loop.

## Adversarial review outcome (2026-06-28)

4-angle review. Containment held (no workspace escape, no protected-file access,
auth + flag-off clean), but the **single-supervised-execution** thesis was broken;
all fixed before merge:
- **[HIGH] Double-execute TOCTOU** — concurrent `/approve` both passed the
  status-only gate → two workers per approval. Fixed: an atomic one-shot
  `decision.lock` (`mkdir(exist_ok=False)`) in `_write_council_decision`; the
  second decision gets **409**.
- **[HIGH] Reject non-binding** — a rejected mission stayed approvable. Fixed by
  the same one-shot lock: reject claims it, so a later approve is **409** and never
  executes.
- **[HIGH] No rate limit on `/council/*`** (session-key spoofable) → authed DoS.
  Fixed: `/council/missions`, `/approve`, `/reject` added to `_RATE_LIMIT_ENDPOINTS`
  (IP-keyed, 20/30/30 per 60 s).
- **[MED] Wildcard scope-widening** — `allowedFiles:["*"]` passed. Fixed: reject
  glob metacharacters in `_validate_mission_scope`.
- **Defense-in-depth:** `_run_council_execution` re-runs `has_blocking_verdict` on
  the stored ledger before executing (guards a tampered-ledger confused-deputy).

### Tracked follow-ups (not blockers)
- A global semaphore bounding concurrent worker subprocesses (rate-limit caps the
  flood; a hard concurrency cap is stronger).
- Bind approval to a contract/verdict hash (not just `missionId`) and assert at
  startup that `COUNCIL_WORKSPACE_ROOT` is not an ancestor of the repo.
- Per-caller mission ownership (single-token deployment today).
