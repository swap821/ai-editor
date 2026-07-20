**Goal:** Truthfully complete GAGOS R15 Sovereign Intelligence and Maintenance Flywheel with executable production evidence; do not start R16.

**Working Verdict:** `R15 BLOCKED — FINAL AUTHORITATIVE REPAIR IN PROGRESS`

**Last completed+verified step:** Truth reset. The prior `READY FOR INDEPENDENT REVIEW` handoff was withdrawn as non-authoritative: the `release/r15/final/*.json` "live proofs" were synthetic in-process generator output (invented IDs, hard-coded digests) and were deleted together with `scripts/generate_r15_authoritative_proofs.py`; FIXTURE-labelled copies remain under `release/r15/fixtures/`. Residual insecure signing-key defaults were removed from `aios/config.py`. The private Executor now emits the shared `ExecutorRepairReceipt`, maintenance parses it fail-closed with independent staged-digest recomputation, and `record_reuse_outcome` accepts only a full `ReuseOutcomeReference` with durable SQLite idempotency.

**Single next action:** Close R15-09 (persist LocalJobRequest/ModelCall/Result records through repositories in the local-job flow), then R15-06 (wire the typed post-promotion verification receipt through the promotion runtime), then produce live/operator evidence.

**Open approvals/blockers:** Live Ollama/Granite, a separate authenticated private Executor process, an operator browser walkthrough, and exact-tip hosted CI/CodeQL are unavailable to this builder environment — R15-04/05/07/08/09/13/14/15/16 remain blocked on them. See `.aios/state/R15_FINAL_AUTHORITATIVE_REPAIR_LEDGER.md`.

**Active files:**
- `.aios/state/R15_FINAL_AUTHORITATIVE_REPAIR_LEDGER.md`
- `.aios/state/R15_INDEPENDENT_REVIEW_REQUEST.md`
- `release/r15/acceptance-report.md`
- `aios/executor_service.py`, `aios/application/maintenance/service.py`
- `aios/application/learning/service.py`, `aios/domain/learning/reuse_outcome_repository.py`
- `tests/test_r15_final_blockers.py`
