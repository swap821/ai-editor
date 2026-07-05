# RESUME MANIFEST

Last updated: 2026-07-05 (V1.0-ready loop session — both operator bars cleared,
Bedrock fully fixed, sandbox-cwd bug fixed, all pushed to master @ `3c6b92c`.
Prior state: backend-coverage-90 arc (2026-07-04, see experiences.jsonl) —
5 gap-test files STILL uncommitted/untracked, unchanged by this session.)

## Current Goal
Operator set two "V1.0 ready" bars and ran a self-pacing `/loop` toward them.
BOTH CLEARED:
- **Bar 1**: one golden mission (`tools/golden_mission_runner.py`) reaches
  `passed: true`. DONE — `error-handling` via Gemini, run_id
  `20260705T132036`, real Docker-sandboxed pytest, 7/7 passed, strength=STRONG.
- **Bar 2**: a real (non-fallback) AI chat reply visibly renders through the
  frontend's BodySpeech path on BOTH Ollama and a cloud provider. DONE — both
  providers screenshotted live (see `.aios/state/V1_LOOP_LOG.md` for paths).

## SINGLE NEXT ACTION
Two independent items, neither blocking the other:
1. **Still pending from the prior arc**: operator's word to commit the 5
   untracked gap-test files (`tests/test_api_main_gaps.py`,
   `test_cloud_providers_gaps.py`, `test_routes_gaps.py`,
   `test_runtime_gaps.py`, `test_agents_pkg_gaps.py`, ~550 tests) — unchanged
   by this session, still sitting untracked.
2. **New, optional**: Bedrock's Nova-Lite model occasionally produces a
   malformed tool-use sequence or loops without progress on complex
   multi-file missions — confirmed to be a Nova-Lite model-capability quirk,
   NOT a `_to_converse` protocol bug (that class of bug is fully fixed and
   verified gone). Not investigated further; not a blocker for anything.

## What landed this session (all pushed to origin/master @ `3c6b92c`)
- `aios/core/bedrock.py::_to_converse`: fixed THREE distinct AWS Converse API
  toolUse/toolResult pairing defects (orphan synthetic ids, dropped dangling
  toolResults, toolResult/text block mixing) — commits `67da6dc`→`9795290`.
  Reconciled a duplicate/stale independent fix (PR #112) in favor of the more
  complete version (merge `3c6b92c`).
- `aios/core/executor.py::_scope_cwd` + `aios/agents/tool_agent.py::_auto_verify`:
  fixed a structural bug where the sandbox ran pytest from `training_ground/`
  itself instead of the repo root, so `from training_ground.X import Y` (the
  import style every mission + existing file uses) could never resolve — this
  was silently causing most multi-file golden-mission failures all session,
  on every provider, independent of any provider-specific bug. Landed via
  Ultraplan PR #111. `config.SCOPE_ROOTS` itself was deliberately left
  untouched (security review confirmed the real containment boundary is
  `scope_lock.py`'s path-token check, independent of cwd).
- `frontend`: new Local/Gemini chat model selector (Ultraplan PR #110) so
  cloud-provider chat is reachable through the real UI, not just the API.
- `Dockerfile.executor` image built locally (`aios-executor:local`) — it had
  never been built on this machine, silently masking every container-backed
  verify as an infra failure until discovered.
- 3 frontend bugs fixed: nerve-animation phase bug, TrustHalo path+CSS bug,
  BodySpeech troika-sync permanent-stall bug (watchdog).
- `tools/preflight.py` (P0.1 engine round-trip check) + `aios/core/telemetry.py`
  (Phase-1 lap-counter schema) — both built+tested, NOT yet wired into the
  live dispatch path (deliberately deferred, not requested this session).

## Hard-won gotcha: backend has no --reload
The uvicorn backend on :8000 is started with NO `--reload` flag — a
long-running process silently keeps serving OLD code after any commit/merge.
This cost significant time mid-session (a stale process from 15:02 served
every "post-fix" test for ~2 hours, across two separate fixes, before being
caught). **Before trusting any live test result, verify the serving process's
StartTime postdates the relevant commit**:
```powershell
$p = Get-NetTCPConnection -LocalPort 8000 -State Listen; Get-Process -Id $p.OwningProcess | Select Id, StartTime
git log -1 --format=%cI HEAD
```
Full writeup: memory `backend-staleness-gotcha`. The frontend Vite dev server
is the OPPOSITE case — it hot-reloads automatically, this gotcha doesn't apply.

## Product seams found in the prior arc (REPORT-ONLY — still open, operator to triage)
1. main.py ~2807 `_verify_target_keys`: `.py` endswith-check runs BEFORE
   lowercasing — uppercase `.PY` tokens lose per-file verify attribution.
2. worker_entry `_default_forbidden_probe`: `lstrip("./")` turns a `.env`
   rule into directory rule `env/` — likely unintended for the canonical
   secret file.
3. swarm scout/decomposer/broker `stopped` branches unreachable via approval
   pause (castes hold read-only tools); only backend errors trigger them —
   code comments imply otherwise.
4. council.py has a LOCAL `get_approval_store` proxy distinct from main.py's;
   dependency_overrides keyed on the wrong one silently no-op (test trap).
5. SQLite connections not always closed (ResourceWarning flood in full runs).
6. No subprocess-coverage wiring (COVERAGE_PROCESS_START) — worker subprocess
   paths read as uncovered even where e2e-exercised.

## Windows verify gotchas (hard-won, still true)
- PS `2>&1 | Tee | Select` exits 1 on ANY stderr (NativeCommandError) even
  when pytest exits 0. Capture truth via cmd:
  `pytest ... > log 2>&1 & echo PYTEST_EXIT=%ERRORLEVEL%`.
- Local `-q` stacks with addopts `-q` = `-qq`: green runs print NO summary
  line — verify via progress-char F/E count, not absence of "passed".
- .pytest_cache lastfailed is ROLLING history; stale/deleted test names
  persist. Never read it as current-run truth alone.

## Standing laws (unchanged)
Poster tetrad; superbrain.css frozen; never `npm run port`; security spine
RED/§VIII; commit only on operator ask; supervision pattern standing (Fable
supervises, Sonnet fleet builds, adversarial verify mandatory); never change
`config.SCOPE_ROOTS`, `aios/security/scope_lock.py`, or
`aios/probe_common.py`'s allowlist regexes without explicit operator sign-off.
