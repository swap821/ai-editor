# ULTRACODE TASK — current build hand-off

> Single current task ultracode (Claude-web) should implement, then open one focused PR.
> Claude Code (local) reviews on evidence + merges (the #1–#7 loop). Overwritten per task.
> Architecture is decided below — implement it as written; flag (don't silently change) anything wrong.

---

## TASK (c) — golden-regression harness for the Self-Analysis analyzer

**Why:** lock the analyzer's deterministic T1 findings against a FROZEN fixture, so any future change
that alters diagnosis (a refactor, a threshold tweak, a radon version bump) is caught by a failing test
— protecting the marquee feature's output before T2 starts turning findings into proposals.

**Scope:** **tests + a committed fixture + a golden JSON ONLY.** No changes under `aios/`. **No new deps**
(radon is already a dep from PR #7). No security surface, no frontend.

### Design

**1. A committed, never-changing fixture** under `tests/golden/fixture/` that deterministically exercises
every T1 finding type (lay it out so the expected findings are stable and cover `missing_test`, `smell`,
`todo`, `complexity`):
- `pkg/__init__.py` — empty (not testable).
- `pkg/orphan.py` — defines a function, has NO `tests/test_orphan.py` → **missing_test**.
- `pkg/tidy.py` + `tests/test_tidy.py` — small, tested, simple → **no finding** (proves the harness
  doesn't over-flag).
- `pkg/bloated.py` — contains a `# TODO: …` marker (→ **todo**) and a function longer than the
  long-function threshold (→ **smell**); give it a `tests/test_bloated.py` so it does NOT also trip
  missing_test (keep the golden minimal/intentional).
- `pkg/tangled.py` + `tests/test_tangled.py` — a function with high cyclomatic complexity (a chain of
  `if/elif` branches well over the threshold) → **complexity** (radon).
  Use the default thresholds, OR pass explicit thresholds in the test and bake the SAME thresholds into
  how the golden was generated — be explicit so the golden is reproducible.

**2. The golden file** `tests/golden/expected_findings.json` — a SORTED JSON array of
`{"target_path","finding_type","evidence","symbol"}` objects (project-relative `target_path`,
machine-independent because `path_root` = the fixture root).

**3. The test** `tests/test_golden_analysis.py`:
- `pytest.importorskip("radon")` at the top — the golden freezes radon's cyclomatic values, and radon is
  a pinned dep, so the golden is meaningful only with radon present (without it the proxy would differ).
- Build `SelfAnalysisAgent(scope_root=<fixture>/pkg, tests_root=<fixture>/tests, path_root=<fixture>,
  db_path=tmp_path/"g.db")` with **no `coverage_data_path`** (so `uncovered` stays dormant and out of the
  golden — note in a comment that a committed synthetic `.coverage` could freeze `uncovered` later).
- `actual = sorted([{ "target_path":f.target_path, "finding_type":f.finding_type, "evidence":f.evidence,
  "symbol":f.symbol } for f in agent.analyze().findings], key=lambda d: (d["target_path"], d["finding_type"], d["symbol"], d["evidence"]))`.
- **Regeneration:** if `os.environ.get("AIOS_UPDATE_GOLDEN") == "1"`, write `actual` to
  `expected_findings.json` (pretty-printed, sorted, trailing newline), print a clear "golden updated"
  note, and pass. Otherwise load the golden and `assert actual == expected`; on mismatch raise with a
  helpful message listing the added/removed findings (set difference both ways) and the hint
  *"re-run with AIOS_UPDATE_GOLDEN=1 if this change is intended."*
- Document the regenerate command in the module docstring:
  `AIOS_UPDATE_GOLDEN=1 .venv/Scripts/python -m pytest tests/test_golden_analysis.py -q`.
- **Also freeze a light T0 invariant** (cheap drift signal on the map): assert the analyzed module count
  and one known intra-package import edge from `analyze().import_map` (e.g. a fixture module that imports
  another fixture module). Keep this to 1–2 assertions.

**4. (Optional, include only if clean) a drift-catch self-test** proving the harness actually fails on
drift: e.g. build the agent with a deliberately different `complexity_threshold`, compute findings, and
assert they differ from the golden set — demonstrating the comparison is load-bearing. Skip if it makes
the PR noisy.

### Determinism notes
- Sort findings before comparing (order independence).
- The fixture content is fixed and radon is pinned (`radon==6.0.1`), so the cyclomatic numbers in the
  golden are stable. If a future radon bump changes them, THIS TEST FAILING is the intended signal
  (regenerate the golden deliberately).

### Acceptance
- The golden test passes against the committed golden; `AIOS_UPDATE_GOLDEN=1` regenerates it.
- Full `pytest -q` green. **No new deps. No `aios/` change.** **Cloud (Linux) note:** the 2 pre-existing
  environmental `test_security.py` failures are NOT yours — confirm identical with your changes stashed.
  Windows baseline is **190 passed / 1 skipped**; your new test(s) add to that.
- One focused PR. Title: `Self-Analysis: golden-regression harness for the analyzer (freeze T1 findings)`.

---

## Runway after (c) — order (each its own PR; I review+merge, reset onto origin/master)
- **(d)** document the frozen core in `CLAUDE.md` — a §VIII controlled-self-modification: Claude Code
  PROPOSES the diff, operator approves (NOT an ultracode job).
- Then **T2** (propose-diff, YELLOW + diff preview; needs the no-self-approval guard + the two-snapshot
  integrity check, §6.3) → **T3** (apply: snapshot→verify→audit→auto-rollback) → **T4** (core edit, RED, frozen).
- Parallel, anytime: the **BREATHE** sandbox first-breath on Ollama (`qwen2.5-coder:7b`) — now richer
  (the agent can `create_file` new files in `training_ground/`).
- OPS: the local root `.coverage` is stale (1 file) + gitignored; run a full `pytest --cov` to make the
  `uncovered` join meaningful, or `rm .coverage` to keep it dormant.
