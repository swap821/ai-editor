# ULTRACODE TASK — current build hand-off

> Single current task ultracode (Claude-web) should implement, then open a PR.
> Claude Code (local) reviews on evidence + merges (the #1–#4 loop). Overwritten per task.
> Architecture is already decided below — implement it as written; flag (don't silently change)
> anything you believe is wrong.

---

## TASK (a) — Report-row hygiene: fingerprint-based reconcile for `self_analysis_report`

**Why (the one nit that bites T2):** the Self-Analysis report table (added read-only in PR #4)
is written by `SelfAnalysisAgent.write_report`, which does a plain `INSERT … VALUES` per finding,
always at `status='open'`. Every `self_analyze` run re-inserts the whole batch, so re-runs
accumulate **duplicate `open` rows**. T2 (propose-diff) will read `open` findings and flip them
`open→proposed`; with duplicates it proposes the same fix N times and the status lifecycle is
ambiguous. Fix the data model **now**, before T2 turns findings into proposals.

**Scope:** backend + schema + tests ONLY. **No frontend change.** Do NOT touch `aios/security/`
(frozen core). Keep `analyze()` pure/read-only — reconcile only ever touches the DB, never source.

### Design — reconcile by stable fingerprint (implement exactly this)

A finding's **logical identity** = `fingerprint = sha256(f"{target_path}\x1f{finding_type}\x1f{symbol}")`,
where `symbol` is a line-number-free discriminator within the file:

| finding_type            | `symbol`                                              |
|-------------------------|------------------------------------------------------|
| `missing_test`          | `""` (one per module → (path,type) already unique)   |
| module-level `smell`    | `""` ("N LOC but defines nothing" — one per module)  |
| long-function `smell`   | the function name                                    |
| `complexity`            | the function name                                    |
| `todo`                  | the **trimmed text** of the marker line (NOT the line number — stable when the TODO moves) |

The point: `evidence` keeps the human-readable line numbers and refreshes each run, but the
**fingerprint stays stable** across unrelated edits so a finding keeps its identity (and its
lifecycle status) across runs.

Known v1 limitations (acceptable — note in a docstring, don't over-engineer): two identically
named functions in one module, or two identical TODO lines in one file, collapse to one
fingerprint. Refine later if needed.

### Files & changes

**1. `aios/agents/self_analysis_agent.py`**
- Add a 4th field to the frozen `Finding` dataclass: `symbol: str = ""` (default keeps the existing
  positional `Finding(rel_path, "missing_test", evidence)` call sites valid).
- At each construction site, pass `symbol`:
  - `missing_test` and module-level `smell`: leave `symbol=""`.
  - long-function `smell` and `complexity` (in `_scan_source_findings`): `symbol=node.name`.
  - `todo` (in `_scan_source_findings`): `symbol=line.strip()` (the trimmed marker line text).
- Add a module-level helper:
  ```python
  import hashlib
  def finding_fingerprint(target_path: str, finding_type: str, symbol: str) -> str:
      return hashlib.sha256(f"{target_path}\x1f{finding_type}\x1f{symbol}".encode("utf-8")).hexdigest()
  ```
- Add a small frozen result dataclass:
  ```python
  @dataclass(frozen=True)
  class ReconcileResult:
      inserted: int
      updated: int
      closed: int
      skipped: int     # fresh findings already in a decided/in-flight status
      open_total: int  # open rows under the analyzed scope after reconcile
  ```
- **Rewrite `write_report(findings) -> ReconcileResult`** as a reconcile, confined to the analyzed
  scope (derive the scope prefix from the agent itself: `prefix = self._rel(self.scope_root)`):
  1. `init_memory_db(self.db_path)` (now also runs the migration — see file 3).
  2. Compute `fresh = {finding_fingerprint(f.target_path, f.finding_type, f.symbol): f for f in findings}`.
  3. In ONE `get_connection` transaction, load existing rows **under the scope prefix**:
     `SELECT id, fingerprint, status FROM self_analysis_report WHERE target_path = ? OR target_path LIKE ?`
     with params `(prefix, prefix + "/%")`. (If `prefix == ""`, omit the WHERE so the whole table is
     reconciled — defensive; in practice the tool always passes a non-empty sub-path.)
  4. Build `open_by_fp = {fp: id}` for rows with `status='open'`; `decided_fps = {fp}` for rows with
     `status != 'open'`.
  5. For each `(fp, f)` in `fresh`:
     - `fp in decided_fps` → **skip** (already proposed/approved/applied/rejected/rolled_back — never
       duplicate or re-open a decided finding). `skipped += 1`.
     - `fp in open_by_fp` → `UPDATE … SET evidence=? WHERE id=?` (refresh line numbers). `updated += 1`.
     - else → `INSERT INTO self_analysis_report (target_path, finding_type, evidence, fingerprint)
       VALUES (?,?,?,?)` at default `status='open'`. `inserted += 1`.
  6. **Close vanished:** for every `fp` in `open_by_fp` whose `fp` is NOT in `fresh` →
     `DELETE FROM self_analysis_report WHERE id=?`. `closed += 1`. (An `open` row is undecided and
     deterministically regenerable, so deleting it when the issue is gone keeps the open set a clean
     mirror of the current scan. **Never** delete a non-`open` row — that's the decision/audit lineage.)
  7. `open_total` = `SELECT COUNT(*) … WHERE status='open' AND (target_path=? OR target_path LIKE ?)`.
  8. Return `ReconcileResult(inserted, updated, closed, skipped, open_total)`.
- `read_findings` is unchanged (it already `SELECT *`, so `fingerprint` rides along).

**2. `aios/memory/schema.sql`**
- Add the column to the `self_analysis_report` CREATE TABLE (for fresh DBs only): a
  `fingerprint TEXT` column (nullable — old rows pre-migration may be NULL). Put it right after
  `evidence`. Do **NOT** add any index that references `fingerprint` here (see the ordering note).

**3. `aios/memory/db.py` — idempotent migration (CRITICAL ordering)**
- `init_memory_db` currently just `executescript(schema.sql)`. On an **existing** DB,
  `CREATE TABLE IF NOT EXISTS` is a no-op, so the new `fingerprint` column is NOT added. Add a
  `_migrate(conn)` step, called **inside the same `get_connection` block, AFTER `executescript`**:
  ```python
  def _migrate(conn: sqlite3.Connection) -> None:
      cols = {row[1] for row in conn.execute("PRAGMA table_info(self_analysis_report)")}
      if cols and "fingerprint" not in cols:
          conn.execute("ALTER TABLE self_analysis_report ADD COLUMN fingerprint TEXT")
          # Drop pre-migration undecided rows (no fingerprint, regenerable). NEVER touch decided rows.
          conn.execute("DELETE FROM self_analysis_report WHERE status='open' AND fingerprint IS NULL")
      # Enforce the invariant: at most one OPEN row per fingerprint. Created HERE (not in schema.sql)
      # so it runs only after the column is guaranteed to exist on both fresh and migrated DBs.
      conn.execute(
          "CREATE UNIQUE INDEX IF NOT EXISTS idx_sar_open_fp "
          "ON self_analysis_report(fingerprint) WHERE status='open'"
      )
  ```
  (`cols` is empty when the table doesn't exist yet — that can't happen after `executescript`, but the
  `if cols` guard is harmless defense.)

**4. `aios/agents/tool_agent.py` — `_self_analyze` summary (lines ~797–838)**
- `write_report` now returns a `ReconcileResult`, not an `int`. Update the summary line to use it,
  e.g.:
  `f"Self-analysis of '{path}': {len(report.modules)} module(s), {len(report.findings)} finding(s) "`
  `f"[{by_type}]; {res.open_total} open in report ({res.inserted} new, {res.closed} resolved)."`
  **Keep the substrings** `Self-analysis of '{path}'` and `finding(s)` in the output (a test asserts
  them). Everything else about `_self_analyze` stays (still status `ok`, `failed=False`, read-only).

### Tests — `tests/test_self_analysis.py`

Update the one existing persistence test, then add the reconcile suite. The existing read-only test
(`test_analyze_never_writes_to_any_source_file`) and the tool tests MUST stay green.

- **Update** `test_write_report_persists_open_findings`: `write_report` now returns a
  `ReconcileResult`; assert `res.inserted == len(report.findings) > 0` and
  `res.open_total == len(report.findings)` on the fresh DB; the row-count / status / NULL-column
  assertions stay.
- **Add** `test_write_report_is_idempotent_on_rerun`: analyze+write the same fixture twice → row
  count identical; 2nd run `inserted==0`, `updated==len`, `closed==0`; no duplicate `open` rows
  (assert one row per fingerprint).
- **Add** `test_reconcile_does_not_reopen_a_decided_finding`: write once; manually
  `UPDATE … SET status='proposed'` on one finding's row; re-run → that finding is `skipped` (still
  exactly one row for it, status still `proposed`, NOT a new `open` duplicate).
- **Add** `test_reconcile_closes_a_vanished_finding`: write once; mutate the fixture so one finding
  disappears (e.g. delete the TODO line from `bigconfig.py`); re-analyze+write → that finding's
  `open` row is gone (`closed>=1`), others intact.
- **Add** `test_fingerprint_stable_when_todo_moves`: same TODO **text** on a different line (prepend
  blank lines) → same fingerprint → still ONE open row, with `evidence` refreshed to the new line
  number (`updated==…`, not a new insert).
- **Add** `test_reconcile_is_scope_confined`: seed an `open` row for a path OUTSIDE the analyzed
  sub-tree, then analyze a sub-path → the out-of-scope `open` row is untouched.
- **Add** `test_migration_adds_fingerprint_to_legacy_db`: create a DB, manually create a
  `self_analysis_report` table WITHOUT the `fingerprint` column + insert a legacy `open` row, then
  call `init_memory_db` → the column exists, the legacy NULL-fingerprint open row is dropped, and a
  subsequent `write_report` works.

### Acceptance criteria
- Full `pytest -q` green. **Note for the cloud (Linux) runner:** the suite shows **2 pre-existing,
  environmental** `test_security.py` failures on Linux (a `C:\…` Windows path classifying GREEN, and a
  random `/tmp/pytest-…` dir tripping the entropy scanner). They are NOT yours — confirm they fail
  **identically with your changes stashed**, and do not "fix" them. Windows baseline is 171 passed /
  1 skipped; your new tests add to that.
- `aios/security/` untouched. No frontend change. `analyze()` remains pure (the read-only
  before/after SHA-256 test still passes).
- PR title suggestion: `Self-Analysis: fingerprint-reconcile for the report table (pre-T2 hygiene)`.
  Keep it a single focused PR.

---

## Runway after (a) — order (each its own PR; I review+merge, then reset onto origin/master)
- **(b)** static tooling — replace the branch-count proxy with **radon** cyclomatic complexity; join
  **coverage.py** for real `missing_test`/uncovered-lines; optional `dead_code`. (Heavy: new deps →
  good ultracode job; spec issued after (a) merges so it reflects (a)'s shape.)
- **(c)** golden-regression harness for the analyzer (freeze findings over a fixture; catch drift).
- **(d)** document the frozen core in `CLAUDE.md` — a §VIII controlled-self-modification: Claude Code
  PROPOSES the diff, operator approves (not an ultracode job).
- Then **T2** (propose-diff, YELLOW + diff preview; needs the no-self-approval guard + two-snapshot
  integrity check, §6.3) → **T3** (apply: snapshot→verify→audit→auto-rollback) → **T4** (core edit, RED, frozen).
