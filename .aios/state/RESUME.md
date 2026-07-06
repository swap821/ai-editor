# RESUME MANIFEST

Last updated: 2026-07-06 (sync-and-resolve session — everything landed: the
5 gap-test files finally committed, CI red→green after a two-round root-cause
hunt, all 5 dependabot PRs resolved, repo hygiene done. Master @ `7837b6c`,
working tree PRISTINE (0 modified, 0 untracked), local == origin, CI green.
Prior state: V1.0-ready loop session 2026-07-05, both operator bars cleared.)

## Current Goal
None in flight — the repo is at a clean resting point. Everything the operator
asked for this session ("sync local and github", "resolve pull requests and
remaining issues", cleanup) is DONE and verified. V1.0-ready bars remain
cleared (see 2026-07-05 entry in git history for evidence paths).

## SINGLE NEXT ACTION
Operator's call on the next directive. Nothing is blocking.

SUPERSEDED SAME-DAY (2026-07-06 afternoon): the deep audit was CLOSED (review
+ fixes shipped, `156220d`) and the monolith split's FIRST MAJOR TRANCHE
LANDED (`ed15f1c`, CI green): NEW `aios/api/deps.py` (21 providers, override
identity preserved, proxy-trap killed by construction) + routers
memory(16)/development(12)/models(4); main.py 4,252 -> ~3,350 lines,
54 -> 22 inline routes; byte-equivalence adversarially reviewed (3 lenses,
0 findings above LOW). Remaining candidates, none urgent:
1. Monolith tranche 2: generate/chat/terminal giants + approvals/security/
   auth/onboarding/intent groups (entangled with main-owned singletons).
2. Two surviving product seams: swarm `stopped` branches unreachable via
   approval pause; no subprocess-coverage wiring. (The council proxy-trap
   seam is structurally addressed by deps.py for new routers; council.py's
   own local proxy still exists.)
3. Optional: Bedrock Nova-Lite model-capability quirk (NOT a harness bug).

## What landed this session (all pushed, master @ `7837b6c`, CI green)
- **`b0d18f2`** — the 2026-07-05 session backlog, finally committed (~2,770
  lines): telemetry wiring into `/generate`+`/chat`, Docker hardening (root
  drop, restart policies, resource limits), Python 3.12 alignment
  (CI/Dockerfile/.python-version), SQLite connection-leak fixes via closing
  context managers (ApprovalStore/CouncilState/RateLimiter/CortexBus), 5 new
  test suites (voice core/routes, anthropic-direct, deployment-hardening,
  telemetry-wiring), council-deliberation-keepers spec, 5 state docs. This
  CLOSED the oldest pending decision (the 5 gap-test files).
- **approvals.py rescue**: a broken shell command at 02:49 had truncated
  `aios/core/approvals.py` to 0 BYTES (destroying the leak fix) and littered
  ~85 zero-byte junk files. Restored from HEAD, fix re-applied to match
  sibling modules. Memory: `shell-accident-clobber-check`.
- **`a300842` + `e051dea`** — CI red→green, two root-cause rounds:
  - Product gap closed: all three advisory early exits in `/generate`
    (clarify-ask, confidence-gated, tool-loop construction failure) now
    record an `aborted` telemetry row; previously they ended turns with
    `done` and ZERO rows.
  - TRUE root cause of the CI/local split: the telemetry tests never
    overrode `get_llm_client`, so the alignment interpreter talked to the
    operator's LIVE local Ollama (high-confidence proposal → gate passes);
    CI has no Ollama → fallback frame confidence 0.4 → 0.72 confidence gate
    diverts the turn. Fix = house `FakeLLM` pattern (`AlignedLLM` +
    `_isolate_turn_memory()` in `tests/test_telemetry_wiring.py`).
    Memory: `suite-order-advisory-gate-gotcha`.
- **All 5 dependabot PRs resolved**:
  - #113 MERGED (29 python bumps: fastapi 0.139, starlette 1.3.1, torch
    2.12.1, transformers 5.13 …) after reverting 4 unresolvable pins
    (pydantic_core/mando/mpmath/tokenizers — each blocked by a sibling's
    constraint; verified via `py -3.12 -m pip install --dry-run`) and fixing
    `test_doc_ingest` route introspection for Starlette ≥1.3 (`hasattr(r,
    "path")` — app.routes now contains `_IncludedRouter` objects).
  - #117 MERGED (TypeScript 6.0.3): tsconfig migrated off deprecated
    `baseUrl` (paths are ./-relative already), TS6 narrowing fix in
    voiceSpeak test mock, lockfile conflict with #116 resolved.
  - #115 (piper-tts), #116 (14 frontend bumps) MERGED.
  - #114 CLOSED: setuptools 83 unresolvable while `torch==2.12.1` pins its
    constraint; dependabot will re-propose when torch moves.
- **Repo hygiene**: ~90 junk/scratch paths triaged. `.gitignore` now covers
  `.agents/skills/` (claude-flow generated), `.codex/`, `.aios` scratch
  (cov_agent_*/fable_*/tmp_shots), and `training_ground/*` (curriculum runs
  generate arbitrary artifacts; curated tracked files unaffected; deliberate
  additions use `git add -f`). Curriculum artifacts + secret-scanner
  redaction stubs deleted.
- **Local pip env updated** to the new requirements and the FULL suite passes
  locally on the new versions (pytest exit 0). Local now matches CI.

## Hard-won gotchas (this session — full writeups in auto-memory)
- **Shell-accident clobber check**: junk-named untracked files (`$(echo`,
  `(null)`, `dict[str`…) mean a broken redirect may have TRUNCATED a tracked
  file. Before committing, inspect `git diff --stat` for all-deletion files
  (empty-blob hash `e69de29`). It happened here; it will happen again.
- **/generate tests MUST override `get_llm_client`** (FakeLLM pattern) or
  they silently depend on live local Ollama and split local-vs-CI.
- **Judge pytest by exit code only**: this repo's pytest config suppresses
  the "N passed" summary line; pipes also mask the exit code. Use
  `pytest > out.txt 2>&1; echo $?`.
- Two pre-existing global-env cohabitants conflict with the new pins
  (dbt-snowflake wants older certifi; pyopenssl wants cryptography<49) —
  NOT ai-editor deps, harmless to it, flagged 2026-07-06.

## Hard-won gotcha: backend has no --reload (still true)
The uvicorn backend on :8000 serves OLD code after any commit until
restarted. Before trusting any live test result, verify the serving process's
StartTime postdates the relevant commit:
```powershell
$p = Get-NetTCPConnection -LocalPort 8000 -State Listen; Get-Process -Id $p.OwningProcess | Select Id, StartTime
git log -1 --format=%cI HEAD
```
Memory: `backend-staleness-gotcha`. The Vite dev server hot-reloads; this
gotcha does not apply to the frontend.

## Product seams (REPORT-ONLY — 3 of the original 6 remain open)
FIXED by `b0d18f2` this session: uppercase-`.PY` verify attribution (main.py
`_verify_target_keys` now lowercases first); worker_entry `.env`→`env/`
lstrip rule bug; SQLite connection leaks (closing context managers + tests).
Still open, operator to triage:
1. swarm scout/decomposer/broker `stopped` branches unreachable via approval
   pause (castes hold read-only tools); only backend errors trigger them —
   code comments imply otherwise.
2. council.py has a LOCAL `get_approval_store` proxy distinct from main.py's;
   dependency_overrides keyed on the wrong one silently no-op (test trap).
3. No subprocess-coverage wiring (COVERAGE_PROCESS_START) — worker subprocess
   paths read as uncovered even where e2e-exercised.

## Windows verify gotchas (hard-won, still true)
- PS `2>&1 | Tee | Select` exits 1 on ANY stderr (NativeCommandError) even
  when pytest exits 0. Capture truth via cmd:
  `pytest ... > log 2>&1 & echo PYTEST_EXIT=%ERRORLEVEL%`.
- Local `-q` stacks with addopts `-q` = `-qq`: green runs print NO summary
  line — verify via exit code, never absence of "passed".
- .pytest_cache lastfailed is ROLLING history; stale/deleted test names
  persist. Never read it as current-run truth alone.

## Standing laws (unchanged)
Poster tetrad; superbrain.css frozen; never `npm run port`; security spine
RED/§VIII; commit only on operator ask; supervision pattern standing (Fable
supervises, Sonnet fleet builds, adversarial verify mandatory); never change
`config.SCOPE_ROOTS`, `aios/security/scope_lock.py`, or
`aios/probe_common.py`'s allowlist regexes without explicit operator sign-off.
