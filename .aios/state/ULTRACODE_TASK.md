# ULTRACODE TASK — current build hand-off

> Single current task ultracode (Claude-web) implements, then opens one focused PR.
> Claude Code (local) reviews on evidence + merges (the #1–#8 loop). Overwritten per task.
> Architecture is decided below — implement it as written; flag (don't silently change) anything wrong.

---

## TASK T2 — Self-Analysis **propose-diff** (generate a fix proposal; NEVER apply)

**Why:** the marquee tier. Turn `open` findings into candidate fixes a human can review — **without
touching source.** T0/T1 (index + diagnose) are done; **T2 PROPOSES** a diff and stores it; **T3** (later)
applies behind the full gate; **T4** is the frozen core (RED). This PR is T2 ONLY.

**Hard invariants (do not regress):**
- **GREEN / propose-only.** T2 may READ source (to draft a fix) and WRITE the `self_analysis_report`
  table (the proposal), but it **NEVER writes a source file and NEVER applies a diff.** The existing
  read-only proof must still hold — add one asserting `propose_*` leaves every source file byte-identical.
- **LLM is injected + fail-soft.** Use the project's completion `LLMClient` (the one the Planner/Reflection
  use via `get_llm_client` — has `.complete()`), NOT the loop's chat client (`self.llm`, which may be cloud
  Bedrock with no `.complete()`). No client / an `LLMError` / empty or junk output → **skip that finding
  (it stays `open`), never crash.** Advisory: T2 is never a security block and is never reflected on.
- `aios/security/` untouched · **no frontend** (proposals surface via the report + the tool summary; a
  review/approve UI lands with T3) · fingerprint/reconcile (PR #5) semantics preserved.

### Design (implement exactly)

**Scope of proposals:** ALL `open` finding types (operator's choice — the human review is the filter).

**1. `aios/memory/schema.sql`** — add `proposed_by TEXT` to `self_analysis_report` (after
`proposed_diff`), comment `-- who proposed the fix (§6.3 groundwork for T3's no-self-approval guard)`.
`finding_type`/CHECK unchanged.

**2. `aios/memory/db.py` `_migrate`** — add `proposed_by` to existing DBs idempotently, mirroring the
`fingerprint` migration exactly (PRAGMA table_info → if absent `ALTER TABLE self_analysis_report ADD
COLUMN proposed_by TEXT`). No index needed.

**3. `aios/agents/self_analysis_agent.py`**
- Import the completion `LLMClient` type (same one the Planner uses; type-only/optional import is fine).
- `__init__(..., llm: Optional[LLMClient] = None, frozen_subdirs: tuple[str, ...] = ("security",))` — store
  both. `llm` is the injected completion client; `frozen_subdirs` are package subdirs that map to RED
  (defaults to `aios/security/`, matching CLAUDE.md §XI frozen core).
- `_classify_target(self, rel_path: str) -> str` — deterministic would-be-apply zone: if the path is under
  `<package>/<frozen_subdir>/` (e.g. `aios/security/…`) → `"RED"`; else → `"YELLOW"`. (Findings are on
  `aios/` code, which is outside the sandbox, so nothing here is GREEN-to-apply — T3/T4 own the apply path.)
- `propose_fix(self, *, target_path: str, finding_type: str, evidence: str, llm: Optional[LLMClient] = None)
  -> Optional[str]` — read `path_root/target_path` (read-only; return `None` if unreadable); build a tight
  prompt — system: *"You produce a MINIMAL unified diff that fixes the described issue. Output ONLY a
  unified diff (---/+++/@@ …), no prose, no fences."*; user: the rel path + the file content + the
  `finding_type` + `evidence`. Call `llm.complete(...)`; return the diff string, or `None` on
  empty/`LLMError`/exception (fail-soft). **Scrub the returned diff with `scan_and_redact(...).scrubbed`
  before returning** (a fix must never surface a secret read from the file).
- `propose_open(self, *, limit: int = 25, llm: Optional[LLMClient] = None) -> int` — `init_memory_db`;
  `client = llm or self.llm`; if `client is None` return `0`. Read up to `limit` rows
  `WHERE status='open'` (reuse `read_findings(status="open", limit=...)`). For each, call `propose_fix`;
  when it returns a diff, **UPDATE that row** `SET proposed_diff=?, proposed_zone=?, proposed_by=?,
  status='proposed'` (proposed_zone = `_classify_target(target_path)`, proposed_by = a stable proposer id,
  e.g. `"self_analysis_agent"`). Count successes. **Only the report DB is written — never source.** Return
  the count.

**4. `aios/agents/tool_agent.py`**
- `__init__`: add `self_analysis_llm: Optional[LLMClient] = None` (the completion client; mirror how
  `planner_llm` is injected) and store it.
- `TOOL_SPECS`: add `propose_fixes` — optional `limit` (int, default 25). Description: *"Generate candidate
  fix diffs (PROPOSALS) for open Self-Analysis findings and store them for human review. Read-only: never
  edits source, never applies. Self-Analysis Tier T2."* Add the module-docstring tool bullet.
- `_dispatch`: route `propose_fixes` → `_propose_fixes(limit)`.
- `_propose_fixes(self, limit)`: construct a `SelfAnalysisAgent(scope_root=self.read_root/"aios",
  tests_root=self.read_root/"tests", path_root=self.read_root, llm=self._self_analysis_llm)`; if no llm →
  return `("[propose unavailable] no completion model configured.", "ok", False)` (graceful, not a block);
  else `n = agent.propose_open(limit=limit)`; return `(f"Proposed fixes for {n} finding(s) (status open→
  proposed); review with status='proposed' before any apply (T3).", "ok", False)`. Status `ok`,
  `failed=False` — GREEN, never reflected. Wrap in try/except → graceful `[propose error] …` (advisory).

**5. `aios/api/main.py` (`/api/generate`)** — pass `self_analysis_llm=Depends(get_llm_client)` into
`ToolAgent` (the SAME completion dep as `planner_llm`; NOT `chat_client`).

### Tests — `tests/test_self_analysis.py` (use a FAKE completion LLM, like the planner tests)
- a `FakeLLM` whose `.complete()` returns a canned unified diff. After seeding the report with `open`
  findings (via `write_report`), `propose_open(llm=FakeLLM())` flips them to `proposed` with
  `proposed_diff` set, `proposed_by` set, and `proposed_zone` correct.
- **zone classification:** a finding whose `target_path` is under `aios/security/…` (or the fixture's
  `<pkg>/security/…`) → `proposed_zone == "RED"`; a non-frozen path → `"YELLOW"`.
- **read-only:** hash the source tree before/after `propose_open`; assert byte-identical (only the DB
  changed).
- **fail-soft:** a `FakeLLM` that raises / returns `""` → `propose_open` returns 0, findings stay `open`,
  no exception.
- **tool path:** `propose_fixes` with no injected llm → status `ok` + `[propose unavailable]`, never
  reflects; with a FakeLLM → summary names the proposed count.
- the existing read-only / reconcile / golden tests stay green (the golden freezes T1 only — T2 adds a
  separate tool, no T1 change, so the golden is untouched).

### §6.3 note (scope boundary for this PR)
T2 records `proposed_by` + `proposed_zone` as GROUNDWORK. The **no-self-approval guard** and the
**two-snapshot integrity check** are ENFORCED in **T3** (apply), because T2 applies nothing — do NOT build
the apply path or the guard here; just lay the data so T3 can require a *human* (≠ proposer) approval.

### Acceptance
- Full `pytest -q` green. **Cloud (Linux) note:** the 2 pre-existing environmental `test_security.py`
  failures are NOT yours — confirm identical with changes stashed. Windows baseline **193 passed /
  1 skipped**; new tests add to it. (`radon`+`coverage` already installed.)
- Read-only-source proof green · `aios/security/` untouched · no frontend · `proposed_by` migration
  idempotent. One focused PR. Title: `Self-Analysis T2: propose-diff (generate fix proposals, never apply)`.

---

## Runway after T2 (each its own PR; I review+merge)
- **T3 — apply:** a human-approved `proposed` row → snapshot → write (the guarded out-of-sandbox path for
  `aios/`) → verify (run the suite) → audit → **auto-rollback on failure**. ENFORCE §6.3: no-self-approval
  guard (approver ≠ proposer, human-gated) + two-snapshot integrity check.
- **T4 — core edit (RED, frozen):** proposals against `aios/security/*` may be shown but applying is RED/blocked.
- Parallel, anytime: the **BREATHE** sandbox first-breath on Ollama (`qwen2.5-coder:7b`).
