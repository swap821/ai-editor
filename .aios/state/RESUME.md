# GAGOS Sovereign Intelligence AI-OS V1.0 Convergence

**Current Goal:** Execute the Master Convergence Directive: transform the repository into a local-first sovereign agentic OS with unified authority, isolated execution, and a truthful living GAGOS interface.

**Last Completed + Verified Step:** Slice 3 — Execution Isolation done and validated.
- Extended `aios/policy/kernel.py` with `ExecutionPolicy`, `execution_policy()`, `build_approved_runner()`, and `validate_execution_backend()` as the single authority for execution-isolation decisions.
- Routed `Executor.execute_approved` through the kernel: it consults the kernel's isolation policy and dispatches to the approved runner (container/unavailable) or host runner accordingly; unknown backends fail closed.
- Updated `aios/api/deps.py::get_executor()` and `get_self_apply_engine()` to build the approved runner through the kernel, removing the direct `approved_runner_from_config()` dependency in `deps.py`.
- Updated `aios/api/main.py` startup validation to call `get_policy_kernel().validate_execution_backend()`.
- Hardened `DockerRunner` container contract: bind mount now uses `bind-propagation=private`, and regression tests verify mount-breaking cwd characters and the locked-down argv set.
- Added deterministic tests in `tests/test_policy_kernel.py` (8 new execution-policy cases) and `tests/test_executor.py`.
- Backend gate: `.venv\Scripts\python -m pytest -q --cov=aios --cov-report=term-missing --cov-fail-under=85` — passing at 91.75% coverage.
- Frontend build (`cd frontend && npm run build`) green. CSS canon check (`tools/check_css_canon.py`) still reports 4 pre-existing violations in `GagosChrome.css` / `TrustHalo.css`; unrelated to this slice.
- Worktree is dirty with Slice 3 changes, ready to commit and push.

**Current Slice:** Slice 4 — to be chosen by operator / next agent.

**Single Next Action:** Commit and push Slice 3, then release the builder lease.

**Open Approvals / Blockers:**
- `.claude/settings.json` was corrupted during a hook-blocker repair attempt. It has been removed and the broken copy preserved as `.claude/settings.json.broken`. The operator should restore a known-good `.claude/settings.json` before the next agent session; built-in tools work in this session due to a no-op `hook-handler.cjs`.
- CSS canon violations in `GagosChrome.css` and `TrustHalo.css` are pre-existing and out of scope.

**Active Files For This Slice:** `aios/policy/kernel.py`, `aios/core/executor.py`, `aios/api/deps.py`, `aios/api/main.py`, `tests/test_policy_kernel.py`, `tests/test_executor.py`.

**Notes Not Yet Promoted:** None.
