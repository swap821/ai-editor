**Goal:** Truthfully complete GAGOS R15 Sovereign Intelligence and Maintenance Flywheel with executable production evidence; do not start R16.

**Working Verdict:** `R15 BLOCKED — FINAL AUTHORITATIVE REPAIR IN PROGRESS`

**Last completed+verified step:** Truth reset plus fail-closed production repairs, all integration-verified:
- Prior `READY FOR INDEPENDENT REVIEW` handoff withdrawn; synthetic `release/r15/final/*.json` "live proofs" (in-process generator, invented IDs, hard-coded digests) deleted with `scripts/generate_r15_authoritative_proofs.py`; FIXTURE-labelled copies remain in `release/r15/fixtures/`.
- Residual insecure signing-key defaults removed from `aios/config.py` (effective defaults empty; `validate_authority_signing_keys` enforced).
- Private Executor emits the shared `ExecutorRepairReceipt`; maintenance parses it fail-closed (empty/malformed stdout, missing/extra fields, job/contract/op/target/backend/version/exit/timestamp mismatches all refuse) and independently recomputes staged target + workspace digests.
- `record_reuse_outcome(reference: ReuseOutcomeReference)` is the only path (legacy kwargs raise TypeError); idempotency is durable append-only SQLite (`ReuseOutcomeRepository`); restart cannot double-increment.
- Maintenance no longer fabricates `ConsumedCapabilityProof`: the route passes the action-guard/authority-produced proof into `run_approved_repair`; with no proof, promotion refuses `capability_binding_missing`. Tests consume real capabilities via `CapabilityAuthority` (`tests/helpers.consume_real_capability_proof`).

**Single next action:** Close R15-09 (persist LocalJobRequest/ModelCall/Result records through repositories in the local-job flow), then R15-06 (wire the typed post-promotion verification receipt through the promotion runtime), then produce live/operator evidence.

**Builder gate results (this session, local run on final tree):**
- Full backend suite: green, `--cov=aios --cov-fail-under=85` → **87.59%**.
- Pre-existing failures at branch tip repaired: `tests/test_promotion_authority.py` (7, loose PromotionRequest fields → real `PromotionAuthorization` via `CapabilityAuthority`) and `tests/test_exact_capabilities.py` (1, `action_payload` moved to `inspect()`).
- CI-scoped Ruff check + format gate: green (formatted pre-existing drift in `aios/application/governance/runtime_proof.py`).
- `python -m compileall`, `scripts/security_scan.py`, conformance suites (release/launcher/governance/v1/route-registry/operations/executor-service/deployment-hardening): green.
- Frontend: typecheck, lint, test:coverage, build — all green.
- SBOM + licence inventory generation: green.
- `git diff --check`: clean.
- NOT run here (unavailable): hosted CI/CodeQL on exact tip, Compose topology/strict runtime proof (needs Docker), live Ollama/Granite, separate Executor process, operator walkthrough.

**Open approvals/blockers:** Live Ollama/Granite, a separate authenticated private Executor process, an operator browser walkthrough, and exact-tip hosted CI/CodeQL are unavailable to this builder environment — R15-04/05/07/08/09/13/14/15/16 remain blocked on them. See `.aios/state/R15_FINAL_AUTHORITATIVE_REPAIR_LEDGER.md`.

**Active files:**
- `.aios/state/R15_FINAL_AUTHORITATIVE_REPAIR_LEDGER.md`
- `.aios/state/R15_INDEPENDENT_REVIEW_REQUEST.md`
- `release/r15/acceptance-report.md`
- `aios/executor_service.py`, `aios/application/maintenance/service.py`, `aios/api/routes/maintenance.py`
- `aios/application/learning/service.py`, `aios/domain/learning/reuse_outcome_repository.py`
- `tests/helpers.py`, `tests/test_r15_final_blockers.py`
