**Goal:** Complete the GAGOS R15 Sovereign Intelligence and Maintenance Flywheel with executable, fail-closed evidence; do not start R16.

**Last completed+verified step:** Repaired `MaintenanceFindingRepository.list_findings()` to use its defined `_connection()` context manager. Added coverage for empty, one, multiple/stable ordering, restart persistence, same-fingerprint update, and reopened-finding persistence; the focused repository suite passed 7/7 and the adjacent maintenance domain suite passed 17/17. Ruff, formatting, and diff checks are clean.

**Next action:** Commit and push this maintenance repository slice, inspect the source-tip hosted CI/CodeQL results, then hand off the hash-pinned tree for independent review before beginning the Local Workforce API slice.

**Open approvals/blockers:** R15 remains NOT ACCEPTED. No admitted local clerk means the 30-task benchmark cannot honestly run. The private Executor is unavailable locally (hosted strict proof is green). The acceptance matrix still needs truthful population, and no independent non-builder verdict exists. Do not self-approve R15 or start R16.

**Active files:** `aios/domain/maintenance/repository.py`, `tests/domain/test_maintenance_repository.py`, `.aios/state/R15_PROGRESS.md`, `.aios/state/RESUME.md`, `.aios/memory/experiences.jsonl`, `.aios/memory/mistakes.jsonl`.

**Notes:** The initial red-first run failed six new list tests with the existing `_connect()` typo; the production fix made all pass. No security spine or admission threshold changed. The next API slice must use mounted HTTP tests and canonical dependencies, not direct route calls or manual authorization dispatch.
