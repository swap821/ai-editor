# ULTRACODE TASK — current build hand-off

> Single current task ultracode (Claude-web) implements, then opens one focused PR.
> Claude Code (local) reviews on evidence + merges (the #1–#9 loop). Overwritten per task.
> Architecture is decided below — implement it as written; flag (don't silently change) anything wrong.
> **This is the highest-risk tier in the project (first automated write to the OS's OWN source). Favour
> refusing over guessing everywhere; fail-closed is always correct.**

---

## TASK T3a — Self-Analysis **apply engine** (apply an approved proposal to `aios/`, gated + verified + reversible)

**Why:** T2 stores candidate fix diffs (`status='proposed'`). T3 lets a **human** approve one and apply it
to the real `aios/` source — but ONLY through a dedicated, audited, **reversible** path with a hard safety
net. This PR is the **backend engine + endpoints + tests** (T3a). The review/approve **UI is T3b**, the
immediate next PR — do NOT build UI here.

### THE SECURITY MODEL (the core of this task — get this exactly right)
1. **No agent tool can ever apply.** Do NOT add any `apply_*` entry to `tool_agent.py` `TOOL_SPECS`. The
   agent proposes (T2 tool) but has **no tool to apply** — so it can never apply its own proposal. Applying
   is reachable ONLY via a **human-called HTTP endpoint**. This is the structural no-self-approval guard.
2. **No-self-approval (defensive, §6.3).** The apply endpoint takes `approved_by` (a human id). Refuse if
   `approved_by` is empty OR equals the row's `proposed_by` (`"self_analysis_agent"`). Record `approved_by`.
3. **Zone gate.** RE-DERIVE the zone from the row's `target_path` at apply time (never trust the stored
   `proposed_zone` alone). `aios/security/*` (frozen core, CLAUDE.md §XI) → **RED → REFUSE** (that's T4).
   Only **YELLOW** (other `aios/`) may apply.
4. **Single-file confinement.** Parse the `proposed_diff`; it must touch **exactly one file == the row's
   `target_path`**. Any diff that references another path, multiple files, or escapes `PROJECT_ROOT`
   (`../`/abs/symlink) → REFUSE. (Reuse the `_resolve_within(PROJECT_ROOT, target_path)` style resolver.)
5. **Snapshot → apply → verify → audit → auto-rollback (the safety net).**
   - **before_bytes** = read the target file (snapshot #1).
   - **apply** via `git apply` (no new dep — git is already used): `git apply --check <diff>` first; if it
     fails → REFUSE (the diff doesn't apply cleanly; the row stays `proposed`). On check-pass, `git apply`.
   - **two-snapshot integrity check (§6.3):** after writing, re-read the file (snapshot #2) and assert the
     on-disk result equals `before_bytes` with the approved diff applied (i.e. nothing other than the
     approved diff changed). On mismatch → restore `before_bytes`, REFUSE.
   - **verify:** run the suite through the existing `Verifier`/gated `Executor`. **Verify command =
     `.venv/Scripts/python -m pytest tests/ -q`** (scoped to `tests/`, NOT bare `pytest` — the
     `training_ground/` breath seed fails by design and would force spurious rollbacks).
   - **pass →** keep the change; `log_action` it (SHA-256 audit); set `status='applied'`,
     `applied_audit_id=<id>`, `approved_by=…`.
   - **fail/timeout/blocked →** **auto-rollback**: restore `before_bytes` to the file; `log_action` the
     rollback; set `status='rolled_back'`. The tree is left exactly as before. **Fail-closed everywhere:** a
     snapshot/audit/apply error → restore + refuse, never leave a half-applied or unlogged change.

### Files
**1. `aios/core/self_apply.py` (NEW) — `SelfApplyEngine`.** Injectable deps (so tests use fakes, no real
shell/model/network): a `verifier` (or an executor to build one), an `audit_log` callable, `db_path`,
`project_root`, and the proposer/verify-command as config. One method:
`apply(proposal_id: int, *, approved_by: str) -> ApplyResult` implementing the flow above. Return a small
`ApplyResult` dataclass: `status` (`applied`|`rolled_back`|`refused`), `reason`, `audit_id` (opt),
`verify` summary (opt). Pure orchestration — all file writes are this engine's, confined to `target_path`.
- `_classify_target(rel_path)` — reuse the SAME logic as `SelfAnalysisAgent._classify_target` (frozen
  subdir → RED). Factor it to a shared helper or import it; do not duplicate divergently.

**2. `aios/api/main.py` — three endpoints (read + apply + reject):**
- `GET /api/v1/self-analysis/proposals` (optional `?status=proposed`) → list rows (id, target_path,
  finding_type, evidence, proposed_zone, proposed_diff, status). Read-only (for the T3b UI).
- `POST /api/v1/self-analysis/proposals/{id}/apply` body `{ "approvedBy": "<human id>" }` → call
  `SelfApplyEngine.apply(id, approved_by=…)`; return the `ApplyResult` as JSON. Inject the engine via
  `Depends(...)` using the SAME local completion/executor deps the rest of the API uses (the verify
  Executor is the gated one).
- `POST /api/v1/self-analysis/proposals/{id}/reject` → set `status='rejected'`; return ok.
- These are the ONLY way to apply. No SSE, no agent involvement.

**3. `aios/memory/` — schema/db:** add an `approved_by TEXT` column to `self_analysis_report` (mirror the
`proposed_by` idempotent `_migrate` ALTER). `status` CHECK already allows `applied`/`rolled_back`/`rejected`.

**4. NO `tool_agent.py` change** (no apply tool — see security model #1). **NO frontend** (T3b). **NO
`aios/security/` change.**

### Tests — `tests/test_self_apply.py` (NEW; use fakes, never a real shell/model)
Drive `SelfApplyEngine` directly with a seeded temp DB + a tiny temp `project_root` containing a fake
`aios/` file, a fake `audit_log` (list), and a fake verifier whose verdict is parametrizable:
- **happy path:** a YELLOW proposal whose diff applies + verify PASSES → file updated, `status='applied'`,
  `applied_audit_id` set, audited.
- **verify fails → auto-rollback:** same but verify FAILS → file restored byte-identical to before,
  `status='rolled_back'`, both apply+rollback audited.
- **no-self-approval:** `approved_by=""` and `approved_by="self_analysis_agent"` → refused, file untouched.
- **RED refused:** a proposal whose `target_path` is under `…/security/` → refused (T4), file untouched,
  verify NEVER run.
- **diff doesn't apply (`git apply --check` fails):** refused, row stays `proposed`, file untouched.
- **multi-file / foreign-path / `..` diff:** refused (single-file confinement), file untouched.
- **two-snapshot integrity:** if the post-write bytes don't equal before+diff → restore + refuse.
- **not-proposed:** applying a row that is `open`/`applied`/`rejected` → refused.
- `approved_by` migration smoke (fresh has it; legacy gains it).

### Acceptance
- Full `pytest -q` green. **Cloud (Linux) note:** the 2 pre-existing environmental `test_security.py`
  failures are NOT yours — confirm identical with changes stashed. Windows baseline **199 passed /
  1 skipped**; new tests add to it.
- `aios/security/` untouched · no `tool_agent.py` change · no frontend · `approved_by` migration idempotent.
- One focused PR. Title: `Self-Analysis T3a: guarded apply engine (apply approved proposals to aios/, verify + auto-rollback)`.

---

## Runway after T3a (each its own PR; I review+merge)
- **T3b — review/approve UI:** list `proposed` rows + `DiffView` + Approve (→ the apply endpoint, supplying
  the human `approvedBy`) / Reject. This is the chosen option (A); it lands right after the engine.
- **T4 — core edit (RED, frozen):** `aios/security/*` proposals may be shown but applying stays RED/blocked
  (already enforced by T3a's zone gate; T4 is the explicit policy + any review surfacing).
- Parallel: the **BREATHE** retry with the explicit "use the `edit_file` tool" prompt.
- OPS / tech-debt worth a tiny PR sometime: set `testpaths = ["tests"]` so bare `pytest` ignores the
  `training_ground/` seed (today the seed must be parked before a full-suite count; T3a's verify already
  scopes to `tests/`).
