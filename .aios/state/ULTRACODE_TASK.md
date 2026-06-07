# ULTRACODE TASK — current build hand-off

> Single current task ultracode (Claude-web) should implement, then open one focused PR.
> Claude Code (local) reviews on evidence + merges (the #1–#6 loop). Overwritten per task.
> Architecture is decided below — implement it as written; flag (don't silently change) anything wrong.

---

## TASK (b) — static tooling: real cyclomatic complexity (radon) + a coverage join

**Why:** the Self-Analysis `diagnose()` (T1) currently uses an AST **branch-count proxy** for
`complexity` and a **file-existence** convention for `missing_test`. Before T2 turns findings into
*proposals*, sharpen the signal so the agent proposes from real metrics, not coarse proxies (a noisy
diagnosis → noisy proposals). Replace the proxy with **radon** cyclomatic complexity, and add a
**coverage** join that flags modules the test suite never executes.

**Dependencies:** `coverage` (7.14.1) and `pytest-cov` (7.1.0) are ALREADY in `requirements.txt` — do
NOT re-add them. The ONLY new dep is **`radon`** → add one pinned line (e.g. `radon==6.0.1`) to
`requirements.txt`, alphabetically near the others.

**Non-negotiable invariants (do not regress):**
- `analyze()` stays **PURE / read-only**: radon only *parses* source; the coverage join only *reads* an
  existing `.coverage` data file. **Never run tests / never execute coverage** inside the agent. The
  read-only proof `test_analyze_never_writes_to_any_source_file` MUST stay green.
- **Fail-soft imports** (match the project's lazy-optional-dep style): if `radon` is missing, fall back
  to the existing branch-count proxy; if `coverage` is missing or no `.coverage` exists, emit no coverage
  findings. The module must import and the suite must run even if `radon` is absent (degraded).
- **Fingerprint stability (from PR #5 reconcile):** the `complexity` finding keeps `symbol = the bare
  function/method name` (radon `block.name`, NOT `Class.method`), so switching proxy→radon UPDATES
  existing open rows (evidence refreshed) instead of duplicating them.
- `aios/security/` untouched · **no `tool_agent.py` change** (the `_self_analyze` summary already counts
  finding types generically, so new types flow through) · **no frontend change**.

### Files & changes

**1. `requirements.txt`** — add `radon==6.0.1` (or latest 6.x). Nothing else.

**2. `aios/agents/self_analysis_agent.py`**
- **Fail-soft imports** near the top:
  ```python
  try:
      from radon.complexity import cc_visit as _radon_cc_visit
  except Exception:        # radon optional — degrade to the AST proxy
      _radon_cc_visit = None
  try:
      import coverage as _coverage
  except Exception:        # coverage optional — skip the coverage join
      _coverage = None
  ```
- **radon complexity (replace the proxy in `_scan_source_findings`).** Keep the long-function `smell`
  block as-is. Replace ONLY the branch-count `complexity` block:
  - If `_radon_cc_visit` is available: `blocks = _radon_cc_visit(src)`; for each block that is a function
    or method with `block.complexity > self.complexity_threshold`, emit
    `Finding(rel_path, "complexity", f"cyclomatic complexity {block.complexity} (> {self.complexity_threshold})", symbol=block.name)`.
    (radon's `cc_visit` is read-only AST analysis. Use `block.name` for the symbol — bare name — for
    fingerprint stability. radon may raise on exotic source: wrap in try/except and fall back to the
    proxy for that file.)
  - Else (radon absent): keep the EXISTING branch-count proxy exactly (don't delete it — it's the
    fallback), same `symbol=node.name`.
  - Keep `_BRANCH_NODES` (used by the fallback).
- **coverage join (a new `uncovered` finding in `diagnose`).** Add `__init__` param
  `coverage_data_path: Optional[Path] = None`. In `diagnose`, resolve it ONCE:
  `cov_path = self.coverage_data_path or (self.path_root / ".coverage")`; use it only if
  `_coverage is not None and cov_path.exists()`. Then:
  ```python
  data = _coverage.CoverageData(basename=str(cov_path)); data.read()
  measured = {os.path.realpath(f) for f in data.measured_files()}
  ```
  For each **testable** module (same rule as `missing_test`: defines a func/class, not `__init__`)
  whose resolved absolute path is **NOT** in `measured` (the suite never executed it), emit
  `Finding(rel_path, "uncovered", "module has no executed lines in the coverage data", symbol="")`.
  When no `.coverage` exists or `coverage` is absent → emit nothing (dormant; the convention-based
  `missing_test` still stands). Document that this is a binary "never-executed" signal; partial-coverage
  percentages are a later refinement (keep it deterministic + cheap now).
- Update the `diagnose` docstring + the `Finding.finding_type` comment to include `uncovered`. Leave the
  `# TODO(radon)` / `# TODO(coverage)` comments resolved (remove or update them). **dead_code is DEFERRED**
  (it would need a 3rd dep, `vulture`) — leave a one-line note, don't implement it.

**3. `aios/memory/schema.sql`** — the `finding_type` column is free-text (CHECK is only on `status`),
so `uncovered` needs NO schema change. Just update the `finding_type` comment to list it.

### Tests — `tests/test_self_analysis.py`
Add (deterministic, over the fixture tree / synthetic data):
- **radon complexity:** plant a function with genuinely high cyclomatic complexity (many `if/elif`
  branches) under a low `complexity_threshold`; assert a `complexity` finding whose evidence contains
  `cyclomatic complexity` and whose `symbol` is the bare function name.
- **radon fallback:** `monkeypatch.setattr(self_analysis_agent, "_radon_cc_visit", None)` → the same
  high-complexity function still yields a `complexity` finding via the proxy (no crash).
- **coverage `uncovered`:** build a synthetic coverage DB in a tmp file via the coverage API
  (`cd = coverage.CoverageData(basename=str(tmp/".coverage")); cd.add_lines({abs_covered_file:[1,2]}); cd.write()`),
  point the agent at it via `coverage_data_path`, and assert a testable module that is ABSENT from the
  data gets an `uncovered` finding while a module present in the data does not.
- **coverage dormant:** no `.coverage` (or `coverage_data_path` points nowhere) → zero `uncovered`
  findings (the rest of diagnosis unchanged).
- The existing **read-only** test must still pass unchanged (add an assertion that running `diagnose`
  with a coverage path does not modify any source file).

### Acceptance
- `radon` added to `requirements.txt`; `pip install -r requirements.txt` clean.
- Full `pytest -q` green. **Cloud (Linux) note:** the 2 pre-existing environmental `test_security.py`
  failures are NOT yours — confirm identical with your changes stashed; do not "fix" them. Windows
  baseline is **185 passed / 1 skipped**; your new tests add to that.
- `analyze()` read-only proof still green · `aios/security/` untouched · no `tool_agent.py` / frontend
  change. One focused PR. Title: `Self-Analysis: radon complexity + coverage join (sharper T1 diagnosis)`.

---

## Runway after (b) — order (each its own PR; I review+merge, reset onto origin/master)
- **(c)** golden-regression harness for the analyzer (freeze findings over a fixture; catch drift). No new deps.
- **(d)** document the frozen core in `CLAUDE.md` — a §VIII controlled-self-modification: Claude Code
  PROPOSES the diff, operator approves (not an ultracode job).
- Then **T2** (propose-diff, YELLOW + diff preview; needs the no-self-approval guard + two-snapshot
  integrity check, §6.3) → **T3** (apply: snapshot→verify→audit→auto-rollback) → **T4** (core edit, RED, frozen).
- Parallel, anytime: the **BREATHE** sandbox first-breath on Ollama (`qwen2.5-coder:7b`) — now richer
  since `create_file` lets the agent author new files in `training_ground/`.
