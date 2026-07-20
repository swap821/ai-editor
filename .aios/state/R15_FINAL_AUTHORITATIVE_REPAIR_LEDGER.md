# GAGOS R15 Final Authoritative Repair Ledger

START_SHA: `daac8b37770ff906f5bf61f651d0c5641d64813f` (working branch before merge of `antigravity/r15-sovereign-intelligence-flywheel` tip `dd2a0505e95c68a14dbb57c9ab0a85a16569e905`)
CURRENT_BRANCH: `copilot/antigravityr15-sovereign-intelligence-flywheel-again`
WORKTREE_STATE: `IN PROGRESS`

Current Working Verdict: `R15 BLOCKED — FINAL AUTHORITATIVE REPAIR IN PROGRESS`

The previous ledger revision claimed `R15 READY FOR INDEPENDENT REVIEW` with `Live Proof PASS`
and `Operator Proof PASS` on every row. Those claims were false and are withdrawn:

- No LIVE_PROVIDER (real Ollama/Granite) run exists in this evidence set.
- No LIVE_PRIVATE_EXECUTOR (separate authenticated Executor process) run exists.
- No OPERATOR walkthrough exists (`release/r15/final/frontend-operator-walkthrough/` was never created).
- The former `release/r15/final/*.json` artifacts were produced by an in-process generator
  (`scripts/generate_r15_authoritative_proofs.py`) using invented IDs (`m-r15-proof-1`,
  `job-granite-1`) and hard-coded digests (`0000…`, `1111…`, `2222…`). They were synthetic,
  not runtime evidence, and have been deleted along with their generator. Labelled FIXTURE
  copies remain only under `release/r15/fixtures/` with
  `{"proof_level": "FIXTURE", "synthetic": true, "acceptance_eligible": false}`.

Proof levels used: FIXTURE < UNIT < INTEGRATION < HOSTED_COMPOSITION < LIVE_PROVIDER /
LIVE_PRIVATE_EXECUTOR < OPERATOR < INDEPENDENT_REVIEW. No lower level satisfies a higher
requirement.

| Defect ID | Defect Summary | Source Files | Required Proof | RED Test | Impl | Focused Test | Regression | Hosted | Live | Operator | Independent | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R15-01 | Skill activation mounted skill_id bug & legacy paths | `aios/application/learning/service.py`, `aios/api/routes/skills.py` | INTEGRATION + OPERATOR | PASS | PASS (single `SkillActivationAuthorization` path) | PASS | PASS | PENDING | N/A | **ABSENT** | ABSENT | BLOCKED (operator proof missing) |
| R15-02 | Consumed proof synthesized in action guard | `aios/application/capabilities/authority.py`, `aios/api/action_guard.py` | INTEGRATION | PASS | PASS (`CapabilityAuthority.consume` returns durable proof) | PASS | PASS | PENDING | N/A | N/A | ABSENT | REPAIRED (integration level) |
| R15-03 | Promotion capability token/digest guessing | `aios/application/promotion/authority.py`, `aios/api/deps.py` | INTEGRATION | PASS | PASS (`PromotionAuthorization` wired) | PASS | PASS | PENDING | N/A | N/A | ABSENT | REPAIRED (integration level) |
| R15-04 | CheckpointAuthority external storage & signed manifest | `aios/application/promotion/checkpoint.py` | INTEGRATION + LIVE_PRIVATE_EXECUTOR | PASS | PASS | PASS | PASS | PENDING | **ABSENT** | N/A | ABSENT | BLOCKED (live proof missing) |
| R15-05 | Two-phase transactional rollback | `aios/application/promotion/authority.py` | INTEGRATION + LIVE_PRIVATE_EXECUTOR | PASS | PASS | PASS | PASS | PENDING | **ABSENT** | N/A | ABSENT | BLOCKED (live proof missing) |
| R15-06 | Authoritative post-promotion verification receipt | `aios/application/promotion/*`, `aios/application/evidence/verification.py` | INTEGRATION + LIVE_PRIVATE_EXECUTOR | PARTIAL | PARTIAL — `WorkspacePromotionRuntime.post_promotion_smoke` is still a boolean tree-digest check; typed receipt not wired through the promotion runtime | PARTIAL | PASS | PENDING | **ABSENT** | N/A | ABSENT | BLOCKED |
| R15-07 | Shared ExecutorRepairReceipt schema & strict maintenance parsing | `aios/executor_service.py`, `aios/application/maintenance/service.py`, `aios/domain/executor/receipt.py` | LIVE_PRIVATE_EXECUTOR | PASS | PASS (this session: Executor emits `ExecutorRepairReceipt`; maintenance parses fail-closed, recomputes staged digests) | PASS | PASS | PENDING | **ABSENT** | N/A | ABSENT | BLOCKED (live private-Executor HTTP proof missing) |
| R15-08 | Canonical Granite advisory contract end-to-end | `aios/domain/learning/contracts.py`, `aios/application/learning/service.py` | LIVE_PROVIDER | PARTIAL | PARTIAL — `SkillApplicabilityAdvisoryV1` exists; end-to-end use in the live local-job flow is unproven without a live Granite call | PARTIAL | PASS | PENDING | **ABSENT** | N/A | ABSENT | BLOCKED |
| R15-09 | Local Workforce job/model-call provenance persistence | `aios/domain/local_workforce/contracts.py` | LIVE_PROVIDER | PARTIAL | **OPEN** — `LocalJobRequestRecord` / `LocalModelCallRecord` / `LocalJobResultRecord` contracts exist but no repositories persist them in the local-job flow | ABSENT | N/A | PENDING | **ABSENT** | N/A | ABSENT | BLOCKED |
| R15-10 | Mandatory authority-derived reuse lineage + durable idempotency | `aios/application/learning/service.py`, `aios/domain/learning/reuse_outcome_repository.py` | LIVE_PROVIDER + LIVE_PRIVATE_EXECUTOR | PASS | PASS (this session: `record_reuse_outcome(ReuseOutcomeReference)` only; in-memory dedupe set deleted; SQLite append-only idempotency) | PASS | PASS | PENDING | **ABSENT** | N/A | ABSENT | BLOCKED (live proof missing) |
| R15-11 | Secure signing key configuration | `aios/config.py` | HOSTED_COMPOSITION | PASS | PASS (this session: residual insecure defaults deleted; effective defaults are empty; `validate_authority_signing_keys` blocks missing/short/equal/historical keys) | PASS | PASS | PENDING | N/A | N/A | ABSENT | REPAIRED (pending hosted proof) |
| R15-12 | Fully executable blocker test suite | `tests/test_r15_final_blockers.py` | INTEGRATION | PASS | PASS (this session: executor-receipt and reuse-lineage groups invoke production behavior) | PASS | PASS | PENDING | N/A | N/A | ABSENT | REPAIRED (integration level) |
| R15-13 | Genuine live runtime evidence artifacts | `release/r15/final/` | LIVE_PROVIDER + LIVE_PRIVATE_EXECUTOR | N/A | **BLOCKED** — synthetic in-process artifacts and their generator deleted; live infrastructure (Ollama/Granite, separate Executor process) is unavailable in this environment, so no `release/r15/final/*.json` may exist | N/A | N/A | N/A | **ABSENT** | N/A | ABSENT | BLOCKED |
| R15-14 | Frontend operator walkthrough evidence | `release/r15/final/frontend-operator-walkthrough/` | OPERATOR | N/A | **BLOCKED** — requires a real Human in a real browser; cannot be produced by the builder | N/A | N/A | N/A | N/A | **ABSENT** | ABSENT | BLOCKED |
| R15-15 | Exact-tip hosted CI & CodeQL green | `.github/workflows/` | HOSTED_COMPOSITION | N/A | PENDING — must be confirmed on the final pushed SHA; old runs do not count | N/A | N/A | **PENDING** | N/A | N/A | ABSENT | BLOCKED |
| R15-16 | Independent-review handoff | `.aios/state/R15_INDEPENDENT_REVIEW_REQUEST.md` | INDEPENDENT_REVIEW | N/A | WITHDRAWN — prior handoff claimed proofs that did not exist; a new hash-pinned request may be created only after all builder blockers close | N/A | N/A | N/A | N/A | N/A | **ABSENT** | BLOCKED |

No row may be marked passed before its required proof actually exists.
