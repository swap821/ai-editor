# Review — Rollback Hardening (Codex)

**Reviewer:** Claude (read-only review-gate) · **Date:** 2026-07-01 · **Base:** master `d116434` + uncommitted working tree.

## Verdict: ✅ PASS — the rollback theater is genuinely fixed.

This closes **audit #7** ("rollback_available always False / rollback_id never populated") and **birth-proof review finding #4** — the #1 v1.0-stability gap. Recovery is now real, not claimed.

## What Codex built (verified against the code)
- **`aios/runtime/snapshots.py` — `SnapshotManager`**: creates a **real git snapshot** via `RollbackEngine` and returns the actual SHA as `snapshot_id`/`rollback_id` (no more null). Metadata file kept as an evidence trail.
- **`aios/runtime/spawner.py`**: creates the snapshot **before the worker acts** (`create_snapshot`, line 118), seals it into the contract, and populates `result.rollback_id` from it (lines 92–94).
- **`aios/runtime/king_report.py`**: recommendation now `= "rollback" if ledger.rollback_id and ledger.files_touched else "revise"`; a failed/blocking run with a snapshot + touched files recommends **rollback** with a live id, and sets `rollback_available=True`.

## Security — good, fail-closed (credit where due)
`SnapshotManager._engine_for` refuses to operate if the workspace already has a **non-Council `.git`** (dir → refuse; file pointer → must match the Council-owned git dir, else refuse). Council keeps its git database under `runtime_root/rollback_git/<key>` and never adopts/commits into a real repo. This prevents the rollback engine from hijacking the operator's actual repo. Solid.

## Verification (real, not asserted-theater)
- `tests/test_runtime_worker_birth.py`: the birth test now **actually performs `RollbackEngine(...).rollback(rollback_id)` and asserts the file content reverts to the original** — and the verification-failure test asserts `recommendation=="rollback"` + a real restore. **26/26 affected tests green** (worker-birth + council-orchestrator + council-origination).
- **Full backend suite: exit 0** (no regression from the broad `king_report` recommendation change).

## Minor (not blocking)
- **`agentdb.rvf` + `agentdb.rvf.lock`** are untracked in the repo root — that's ruflo's memory DB (side-effect of Claude's ruflo usage this session). **Add to `.gitignore`; do not commit.**
- The reviewed changes are **partly uncommitted** (working tree: `snapshots.py`, `king_report.py`, `main.py`, dashboard, tests). Recommend committing the set once you're done.

## Bottom line
Rollback is now end-to-end real: snapshot-before-act → live `rollback_id` → `rollback_available` → a restore that actually reverts files, all fail-closed and test-proven. Safe to land. This was the top item on the audit's fix-list — well done.

— Claude (read-only; tree is yours)
