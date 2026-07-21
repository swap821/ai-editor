# GAGOS R15 + R16 MASTER CONVERGENCE PLAN

## From Governed Architecture to Autonomous Sovereign Intelligence

**Project:** GAGOS — Governed Agentic Guided Operating System  
**Repository:** `swap821/ai-editor`  
**Starting baseline:** `master@b810d918f1556711a47ea0639025ea86b59290a2`  
**Target classification:** Autonomous Sovereign Intelligence (Local + Cloud) Agentic AI-OS Alpha Research Prototype

---

# 1. Final North-Star Definition

GAGOS is not attempting to create one permanently trusted artificial genius.

GAGOS is building:

> A sovereign technical institution for one Human operator that can hire frontier intelligence, assign temporary workers, preserve verified expertise, perform routine cognitive work locally, maintain itself under supervision, and complete bounded missions without transferring authority to any model.

The system combines four distinct forces.

## 1.1 Human Sovereign

The Human controls:

- Goals.
- Taste.
- Privacy.
- Cost.
- Risk tolerance.
- Project enrollment.
- Approval boundaries.
- Policy changes.
- Trusted-memory promotion.
- Final veto.
- Emergency shutdown.

The Human should not be interrupted for every ordinary step.

The Human must be interrupted when authority, risk, uncertainty, privacy exposure, cost or irreversibility crosses a declared boundary.

## 1.2 Sovereign deterministic institution

GAGOS owns:

- Identity.
- Sessions.
- Policy.
- Capabilities.
- Mission state.
- Scope.
- Budgets.
- Execution boundaries.
- Verification truth.
- Promotion.
- Rollback.
- Memory trust.
- Audit evidence.
- EmergencyStop.

Models do not own these.

## 1.3 Hireable frontier intelligence

Frontier models are temporary expert consultants.

They may provide:

- Architecture.
- Complex reasoning.
- Difficult debugging.
- Research.
- Repair design.
- Code generation.
- Security analysis.
- Verification-plan design.
- Alternative evaluation.

They may not manufacture permission or certify their own success.

## 1.4 Local sovereign workforce

Small operator-qualified 2–3B local models perform replaceable routine cognitive labour:

- Classification.
- Extraction.
- Summarisation.
- Formatting.
- Triage.
- Duplicate grouping.
- Report preparation.
- Evidence packet preparation.
- Skill selection.
- Routine procedure parameterisation.

The local workforce is not expected to act like Gemini, Claude or another frontier model.

It is expected to reliably perform narrow clerical jobs under schemas, limits and deterministic validation.

---

# 2. Definition of Autonomy

For GAGOS:

> Autonomy means verified useful work completed with few meaningful Human interruptions, not unrestricted model authority.

The primary autonomy metric is:

```text
Verified useful missions completed
───────────────────────────────────
Meaningful Human interruptions
```

A Human interruption is meaningful when it is required for:

- New external data exposure.
- Secret access.
- Scope expansion.
- Dependency installation.
- Destructive action.
- Policy mutation.
- High cost.
- Weak or contradictory verification.
- Irreversible promotion.
- Trusted skill generalisation.
- Emergency recovery.
- A genuinely new uncertainty class.

Routine classification, scanning, context preparation, retries and report writing should not bother the Human.

---

# 3. Definition of Learning

Small local models do not magically absorb a frontier model’s intelligence after one mission.

R15 implements institutional learning through:

```text
Frontier expertise
→ staged execution
→ deterministic verification
→ verified trajectory
→ reusable skill candidate
→ applicability qualification
→ local skill-guided execution
→ verification
→ confidence update or re-escalation
```

The first learning mechanism is procedural memory, not continuous weight training.

## R15 and R16 explicitly exclude

- Automatic fine-tuning after every mission.
- Unreviewed synthetic training.
- Self-modifying local model weights.
- Continuous LoRA generation.
- Treating a successful response as a reusable skill.
- Allowing similarity search alone to authorise skill reuse.

Weight adaptation may become a later research phase after a sufficiently large verified dataset exists.

---

# 4. Constitutional Invariants

These rules apply throughout R15 and R16.

1. The Human Sovereign remains the final authority.
2. Models produce intelligence, not permission.
3. PolicyKernel remains the policy authority.
4. CapabilityAuthority remains the exact side-effect grant authority.
5. MissionService remains the mission lifecycle authority.
6. TurnCoordinator remains the directive spine.
7. WorkerFoundry remains the temporary-worker admission boundary.
8. Production execution remains inside the private Executor Service.
9. Production work uses staged workspaces.
10. VerificationAuthority determines technical success.
11. PromotionAuthority owns promotion and recovery transitions.
12. MemoryAuthority determines what may become trusted experience.
13. Cortex transports observations, never authority.
14. Living Mirror reflects backend truth and never creates it.
15. RED actions remain unapprovable.
16. Unknown operational state fails closed.
17. No model may approve its own action.
18. No worker may expand its own scope.
19. No scanner may silently mutate the project.
20. No local model may suppress or resolve a deterministic finding.
21. No cloud provider may receive data merely because it is available.
22. No automatic local-model downloading occurs during routing.
23. No hidden host execution fallback is permitted in production.
24. Every meaningful side effect must remain attributable and auditable.
25. A passing process exit alone is not sufficient proof.
26. Memory cannot become trusted merely because a model repeated it.
27. Every release claim must have executable evidence.
28. No new Queen, authority or database is added unless an existing canonical organ cannot satisfy the requirement.
29. R16 freezes major architecture.
30. Product truth is more important than feature count.

---

# 5. Branch and Coordination Strategy

## R15 branch

```text
antigravity/r15-sovereign-intelligence-flywheel
```

## R16 branch

Create only after R15 receives a hash-pinned non-builder verdict:

```text
antigravity/r16-product-readiness
```

## Before every state-changing Antigravity session

Run:

```text
python agent_coord.py status
```

Then:

1. Read the coordination inbox.
2. Confirm Antigravity owns the active builder lease.
3. Refuse edits when another builder owns the worktree.
4. Read `AGENTS.md`.
5. Read `.aios/state/RESUME.md`.
6. Read warnings and recent experiences.
7. Read the current phase plan completely.
8. State one exact next slice.
9. Identify affected authorities.
10. Begin only after the working context is grounded.

Every handoff must be hash-pinned.

Final acceptance for each major phase must come from a non-builder reviewer.

---

# 6. Required State Documents

Create at the start of R15:

```text
.aios/state/GAGOS_R15_R16_MASTER_PLAN.md
.aios/state/R15_PROGRESS.md
.aios/state/R15_DECISIONS.md
.aios/state/R15_RISK_REGISTER.md
.aios/state/R15_ACCEPTANCE_MATRIX.md
.aios/state/R15_DEFERRED.md
```

At R16 start, add:

```text
.aios/state/R16_PROGRESS.md
.aios/state/R16_DECISIONS.md
.aios/state/R16_RISK_REGISTER.md
.aios/state/R16_ACCEPTANCE_MATRIX.md
.aios/state/R16_DEFERRED.md
```

## Progress file requirements

Every slice entry records:

- Exact baseline SHA.
- Goal.
- Files inspected.
- Files changed.
- Tests written.
- Commands executed.
- Pass/fail counts.
- Coverage changes.
- Runtime evidence.
- Known limitations.
- Security impact.
- Exact next action.

## Acceptance matrix columns

```text
requirement
implementation
unit proof
integration proof
runtime proof
frontend proof
operator proof
status
blocking reason
evidence location
```

---

# PART I — R15

# R15: Sovereign Intelligence and Maintenance Flywheel

## R15 mission

R15 must prove that GAGOS can:

1. Perform routine cognitive work through a small local workforce.
2. Hire frontier models only when stronger intelligence is required.
3. Capture successful frontier expertise as verified institutional knowledge.
4. Attempt future matching work locally through qualified procedures.
5. Escalate again when local knowledge is insufficient.
6. Detect internal problems through deterministic maintenance organs.
7. Convert maintenance findings into governed repair missions.
8. Complete work through the existing Council, mission, capability, worker, executor, verification, promotion and memory architecture.
9. Display the complete lifecycle truthfully.
10. Reduce Human interruptions without weakening sovereignty.

R15 is not product polishing. It is the final major functional convergence wave.

---

# R15 Slice 0 — Baseline Freeze and Independent Handoff

## Goal

Preserve R14 as a known-good control baseline and perform the currently pending non-builder/operator review before introducing new functionality.

## Actions

- Confirm `HEAD` and `origin/master`.
- Confirm clean worktree.
- Run backend compile checks.
- Run Ruff.
- Run complete backend test and coverage gate.
- Run frontend tests.
- Run frontend typecheck.
- Run frontend lint.
- Run production frontend build.
- Run current `gagos v1-check --strict`.
- Run the supported hosted or Compose release-authority proof.
- Record unavailable local Executor behaviour truthfully.
- Perform the hash-pinned non-builder review.
- Record all operator usability failures without fixing them in this slice.

## Gate

R15 cannot begin until:

- Existing R14 tests remain green.
- Current runtime proof remains green at the declared boundary.
- The tree is hash-pinned.
- A non-builder verdict is recorded.
- Baseline limitations are listed.

## Suggested commit

```text
docs(r15): freeze reviewed R14 baseline
```

---

# R15 Slice 1 — Canonical Intelligence Boundary Audit

## Goal

Inventory every active local and cloud model call and establish one future canonical path.

## Target architecture

```text
Caller
→ ModelCallRequest
→ PrivacyBroker
→ IntelligencePolicy
→ Local Workforce Admission or Frontier Hiring
→ Provider Adapter
→ ModelCallRecord
→ Cortex Observation
```

## Audit every active caller

Inspect:

- Chat generation.
- Turn planning.
- Council reasoning.
- King reasoning.
- Critique.
- Reflection.
- CRAG.
- Self-analysis.
- Worker strategies.
- Swarm adapters.
- Maintenance.
- Research.
- Summarisation.
- Onboarding.
- Voice-related reasoning.

Classify each path:

```text
canonical
compatibility
test-only
dead
unverified
```

## Deliverables

- `INTELLIGENCE_CALL_INVENTORY.md`
- Call-site architecture test.
- Approved provider-adapter allowlist.
- Migration order for active compatibility paths.

## Gate

No active call path may remain unclassified.

## Suggested commit

```text
audit(r15): inventory all intelligence call paths
```

---

# R15 Slice 2 — Curated Local Workforce Domain

## Goal

Create the minimal product model for one small local clerk, not a marketplace of models.

## Core contracts

### LocalWorkerModel

```text
model_id
provider
family
parameter_size
quantization
installed
operator_approved
health
admission_status
admission_reason
max_context
max_output
max_parallelism
allowed_job_profiles
last_success
failure_count
metadata_confidence
```

### LocalJobProfile

Initial profiles only:

```text
classify
extract
summarise
cluster
triage
format_report
prepare_briefing
select_skill
parameterise_skill
```

### LocalJobRequest

```text
job_id
job_profile
input_schema_version
evidence_references
redacted_payload
token_budget
deadline
required_output_schema
```

### LocalJobResult

```text
job_id
model_id
structured_output
schema_valid
evidence_references_preserved
unsupported_claims
latency
status
failure_reason
```

## Hard restrictions

The local clerk receives:

- No shell.
- No filesystem tools.
- No Git tools.
- No network.
- No direct project-write ability.
- No mission-state mutation.
- No capability issuance.
- No memory-trust mutation.

It returns structured advisory data only.

## Gate

Domain tests prove that no authority field exists in local job outputs.

## Suggested commit

```text
feat(local-workforce): add bounded local clerk contracts
```

---

# R15 Slice 3 — Durable Local Workforce Registry

## Goal

Persist the Human operator’s approved local workforce configuration.

## Required capabilities

- Discover installed Ollama models.
- Reconcile current installation state.
- Preserve operator approval across restart.
- Preserve job-profile assignment.
- Preserve context/output/concurrency ceilings.
- Preserve health history.
- Retain records for removed models.
- Truthfully mark missing metadata.
- Never pull or delete a model.

## API

```text
GET  /api/v1/local-workforce
GET  /api/v1/local-workforce/{model_id}
POST /api/v1/local-workforce/refresh
POST /api/v1/local-workforce/{model_id}/approve
POST /api/v1/local-workforce/{model_id}/deny
POST /api/v1/local-workforce/{model_id}/profiles
POST /api/v1/local-workforce/{model_id}/health-check
```

All mutations must pass through the existing action-governance path.

## Gate

Configuration remains identical after backend restart.

## Suggested commit

```text
feat(local-workforce): persist operator-governed model registry
```

---

# R15 Slice 4 — Qualification and Hardware Admission

## Goal

Prove that the chosen 2–3B model can perform its designated clerical work reliably on the operator’s actual laptop.

## Qualification suite

Create a fixed, versioned fixture set covering:

- Finding classification.
- Error extraction.
- Evidence summarisation.
- Duplicate grouping.
- Missing-information detection.
- Council briefing preparation.
- Exact identifier preservation.
- Authority-injection refusal.
- Unsupported-claim avoidance.
- Valid JSON output.

## Required admission thresholds

```text
schema validity: 100%
identifier preservation: 100%
authority mutation attempts accepted: 0
tool requests accepted: 0
secret reproduction: 0
unsupported-claim rate: below declared threshold
timeout rate: below declared threshold
memory use: within configured ceiling
parallelism: 1 by default
```

## Resource admission inputs

- Available system RAM.
- Current GAGOS runtime profile.
- Active Docker/Executor workload.
- Active local inference count.
- Requested context.
- Requested output.
- GPU information only when reliably measurable.
- Frontend rendering pressure when measurable.

Unknown GPU state remains `unknown`.

## Gate

The model becomes `admitted` only after:

- Operator approval.
- Health check.
- Qualification pass.
- Resource admission.

Installed does not mean admitted.

## Suggested commit

```text
feat(local-workforce): qualify and admit bounded local clerk
```

---

# R15 Slice 5 — Structured Local Clerical Runtime

## Goal

Wire the local clerk into real routine work without giving it authority.

## Implement job runners for

- Deterministic scanner summary.
- Error/log extraction.
- Finding grouping.
- Routine priority suggestion.
- Missing evidence identification.
- Hibernation report formatting.
- Council packet preparation.
- Skill applicability pre-classification.

## Validation pipeline

```text
Local model output
→ JSON parse
→ schema validation
→ identifier validation
→ evidence-reference validation
→ forbidden-field validation
→ unsupported-claim detection
→ advisory result
```

Malformed output is rejected.

No automatic free-text fallback is allowed for operational jobs.

## Failure posture

When Ollama or the model is unavailable:

- Deterministic work continues.
- The clerical result becomes unavailable.
- No fabricated summary appears.
- No silent cloud fallback occurs for local-only work.

## Gate

At least 100 fixture executions complete with:

- 100% valid schema after allowed bounded retries.
- Zero authority violations.
- Zero invented finding IDs.
- Measured resource use within the declared laptop budget.

## Suggested commit

```text
feat(local-workforce): run validated routine cognitive jobs
```

---

# R15 Slice 6 — Frontier Intelligence Hiring Broker

## Goal

Make cloud intelligence explicitly hireable, policy-governed and replaceable.

## Hiring request

```text
problem_id
mission_id
purpose
task_class
required_capabilities
data_classification
context_manifest
privacy_budget
cost_budget
latency_budget
candidate_providers
verification_requirements
```

## Hiring decision

```text
eligible_providers
selected_provider
selected_model
reason
redactions
external_data_scope
cost_limit
fallback_order
human_approval_required
```

## Requirements

- PrivacyBroker runs before provider selection.
- Local-only and secret classifications cannot leak externally.
- Provider availability does not imply eligibility.
- Model choice remains replaceable.
- Every call records provider, model, purpose, cost class, latency and status.
- Cloud output is advisory until executed and verified.
- `ollama.auto` remains local-only.
- Cross-provider automatic selection uses a distinct identity.
- No model may choose a provider outside the deterministic eligible set.

## Canonicalisation

Migrate all active production provider calls through the canonical intelligence boundary.

ToolAgent may consume an already selected client, but may not independently bypass hiring policy.

## Gate

Code search and architecture tests prove no active production provider call exists outside approved adapters.

## Suggested commit

```text
refactor(intelligence): enforce canonical frontier hiring boundary
```

---

# R15 Slice 7 — Verified Expert Trajectory Capture

## Goal

Capture what a frontier expert contributed without treating raw model output as trusted learning.

## Trajectory record

```text
problem_signature
project_digest
expert_provider
expert_model
context_digest
proposal_digest
actions_attempted
failed_attempts
successful_actions
tool_observations
verification_plan
verification_results
promotion_result
rollback_result
human_interventions
final_outcome
```

## Separation rules

Store separately:

- Expert proposal.
- Worker action.
- Tool output.
- Verification result.
- Human decision.
- Final promoted state.

Never merge them into one narrative and call it truth.

## Gate

A trajectory is eligible for skill extraction only when:

- The mission contract is known.
- The resulting change is known.
- Verification is sufficiently strong.
- Promotion or recovery is known.
- Evidence provenance is complete.

## Suggested commit

```text
feat(learning): capture verified expert mission trajectories
```

---

# R15 Slice 8 — Institutional Skill Library

## Goal

Turn verified trajectories into bounded reusable procedures.

## Skill states

```text
candidate
human_reviewed
qualified
active
degraded
superseded
deprecated
blocked
```

## Skill contract

```text
skill_id
version
problem_signature
applicability_conditions
known_exclusions
required_inputs
required_project_state
procedure
allowed_tools
allowed_scope_pattern
expected_observations
verification_plan
escalation_conditions
source_trajectory_ids
confidence
success_count
failure_count
last_validated_versions
```

## Critical rule

Semantic similarity alone never means applicability.

A skill can be used only when:

- Required inputs exist.
- Project/version constraints match.
- Scope is compatible.
- No known exclusion matches.
- Verification remains available.
- Policy permits the procedure.
- Skill status is active.
- Confidence floor is met.

## Local role

The local clerk may:

- Classify a task against candidate skills.
- Extract required parameters.
- Identify missing prerequisites.
- Recommend “no qualified skill.”
- Prepare a skill-execution packet.

It may not decide final applicability alone.

## Gate

Every active skill has:

- At least one verified source trajectory.
- A declared verification plan.
- Explicit failure/escalation conditions.
- Versioned provenance.

## Suggested commit

```text
feat(learning): add evidence-backed institutional skill library
```

---

# R15 Slice 9 — Local Skill Reuse and Re-Escalation

## Goal

Allow repeated work to be attempted locally without pretending the small model has acquired frontier intelligence.

## Runtime flow

```text
New task
→ deterministic signature
→ candidate skill retrieval
→ local clerk extracts parameters
→ applicability engine validates conditions
→ ordinary governed mission
→ bounded worker executes procedure
→ VerificationAuthority
→ confidence update
```

## Failure flow

```text
No qualified skill
or applicability mismatch
or local execution uncertainty
or verification failure
→ Frontier Hiring Broker
→ new expert trajectory
→ skill repair, narrowing or supersession
```

## Confidence updates

Increase confidence only after new independent verified reuse.

Decrease confidence after:

- Verification failure.
- Applicability mismatch.
- Version drift.
- Human correction.
- Rollback.
- Unexpected side effects.

One failure may disable automatic reuse until reviewed.

## Gate

Demonstrate at least three task families:

1. First occurrence requires frontier expertise.
2. Verified procedure is extracted.
3. Similar second occurrence is attempted locally.
4. Local result passes verification.
5. A deliberately altered case fails applicability and correctly escalates.

## Suggested commit

```text
feat(learning): reuse qualified skills with fail-closed escalation
```

---

# R15 Slice 10 — Durable Maintenance Finding Lifecycle

## Goal

Unify Vulture, EcosystemScanner, SelfAnalysis and future maintenance sensors behind one durable finding system.

## Finding contract

```text
finding_id
fingerprint
scanner_id
scanner_version
kind
severity
confidence
evidence_quality
target_id
target_digest
source_digest
first_seen
last_seen
occurrence_count
status
deterministic_evidence
local_clerk_enrichment
frontier_analysis
mission_id
verification_ids
resolution_evidence
human_disposition
```

## Finding states

```text
OPEN
ACKNOWLEDGED
TRIAGED
PROPOSAL_READY
MISSION_CREATED
REPAIRING
VERIFYING
VERIFICATION_FAILED
VERIFIED_RESOLVED
FALSE_POSITIVE
HUMAN_SUPPRESSED
REOPENED
```

## Rules

- Stable fingerprints ignore irrelevant line movement.
- Process globals are not authoritative.
- Findings survive restart.
- Local models cannot alter severity or status.
- Cloud models cannot mark resolution.
- A missing scan result alone does not prove resolution.
- `VERIFIED_RESOLVED` requires current deterministic rescan plus matching verification evidence.
- Reappearance reopens the finding.

## Gate

Vulture and Ecosystem truth routes read durable findings instead of process-global last scans.

## Suggested commit

```text
feat(maintenance): unify durable evidence-backed findings
```

---

# R15 Slice 11 — Autonomous Maintenance Force

## Goal

Create low-interruption, bounded maintenance without creating a privileged repair daemon.

## Trigger classes

### Synchronous safety ingress

Run before unsafe content is trusted:

- Uploaded documents.
- Web content.
- Cloud research.
- Proposed skills.
- Proposed lessons.
- External instructions.
- Policy proposals.

### Cold-path Cortex maintenance

Trigger from observations such as:

- Verification failure.
- Promotion completion.
- Rollback.
- Project digest change.
- Repeated provider failure.
- Memory proposal.
- Hibernation.
- Runtime-proof failure.
- Audit anomaly.

## Maintenance service may

- Choose a scanner.
- Run bounded read-only scans.
- Reconcile findings.
- Request local clerical enrichment.
- Request frontier analysis when policy permits.
- Prepare a governed repair proposal.
- Emit observations.

## Maintenance service may not

- Approve repair.
- Issue capabilities.
- Mutate source directly.
- Change policy.
- Promote memory.
- Close findings without rescan.
- Clear EmergencyStop.

## Bounded scan contract

```text
allowed_root
max_files
max_total_bytes
max_file_bytes
deadline
max_findings
network_allowed=false
git_history_allowed
```

## Hibernation behaviour

Hibernation may:

- Refresh Project Passport.
- Preview compaction.
- Reconcile findings.
- Run low-cost local scans.
- Prepare reports.
- Prepare proposals.

It may not perform unapproved writes or cloud calls.

## Gate

A project event causes a bounded maintenance scan and durable finding without automatic mutation.

## Suggested commit

```text
feat(maintenance): activate bounded local maintenance force
```

---

# R15 Slice 12 — Maintenance-to-Mission Repair Bridge

## Goal

Convert a maintenance finding into a normal governed mission.

## Required flow

```text
Finding
→ local clerk briefing
→ optional frontier diagnosis
→ Council origination
→ MissionContract
→ Human approval when required
→ exact capability
→ WorkerFoundry
→ staged workspace
→ private Executor
→ evidence
→ verification
→ promotion or rollback
→ exact scanner rescan
→ finding reconciliation
→ verified lesson proposal
```

## Mission binding

Every maintenance mission binds:

- Finding ID.
- Finding fingerprint.
- Scanner ID.
- Scanner version.
- Target digest.
- Allowed files.
- Forbidden files.
- Allowed tools.
- Verification plan.
- Required post-repair rescan.
- Maximum repair attempts.
- Escalation condition.

## No duplicate organs

Do not add:

- MaintenanceExecutor.
- MaintenanceApprovalStore.
- MaintenanceMissionService.
- MaintenanceCapabilityAuthority.
- MaintenancePromotionAuthority.

## Gate

A harmless controlled defect completes the full lifecycle and closes only after scanner rescan.

## Suggested commit

```text
feat(maintenance): repair findings through canonical mission governance
```

---

# R15 Slice 13 — Living Mirror Product Activation

## Goal

Expose the complete intelligence, skill and maintenance lifecycle through truthful operator surfaces.

## Local Workforce panel

Display:

- Installed model.
- Operator approval.
- Qualification status.
- Health.
- Resource admission.
- Active jobs.
- Job-profile limits.
- Failure history.
- No-authority declaration.

## Intelligence Hiring panel

Display:

- Why frontier expertise is required.
- Eligible providers.
- Selected expert.
- Privacy classification.
- Data leaving the machine.
- Cost class.
- Redactions.
- Advisory status.
- Verification requirements.

## Skill Library panel

Display:

- Skill status.
- Provenance.
- Applicability conditions.
- Known exclusions.
- Success/failure count.
- Version compatibility.
- Last verification.
- Escalation reason.

## Maintenance Center

Display:

- Findings.
- Deterministic evidence.
- Local clerk summary.
- Frontier analysis separately.
- Related mission.
- Worker state.
- Staged diff.
- Verification evidence.
- Promotion/rollback.
- Resolution rescan.
- Human disposition.

## Mission Control

The operator must see:

- Goal.
- Scope.
- Risk.
- Council verdict.
- Exact capability request.
- Worker identity.
- Allowed tools.
- Current stage.
- Diff.
- Tests.
- Evidence strength.
- Recovery state.
- Final report.

## Truth rule

Ambient animation may be aesthetic.

Operational state must originate from canonical backend events or measured snapshots.

## Gate

The full acceptance mission can be understood without inspecting SQLite, logs or terminal internals.

## Suggested commit

```text
feat(frontend): expose sovereign intelligence and maintenance lifecycle
```

---

# R15 Slice 14 — Runtime Proof and Benchmark Expansion

## Preserve all R14 proofs

Add executable proof for:

```text
local_workforce_registry
local_workforce_qualification
local_workforce_non_authority
hardware_admission
canonical_intelligence_hiring
privacy_gated_cloud_use
expert_trajectory_provenance
skill_applicability
skill_re_escalation
maintenance_finding_persistence
maintenance_canonical_repair
maintenance_rescan_resolution
```

## Required failure demonstrations

- Capability replay refused.
- Out-of-scope edit refused.
- Local model unavailable.
- Cloud unavailable.
- Secret-classified task blocked from cloud.
- Skill applicability mismatch.
- Verification failure prevents promotion.
- Scanner still detects issue after green tests.
- EmergencyStop blocks queued maintenance work.
- Mirror refuses malformed events.

## GAGOS Personal Developer Benchmark v1

Create 30–50 controlled tasks across:

- Bug diagnosis.
- Small features.
- Frontend/backend integration.
- Test repair.
- Dependency analysis.
- Documentation.
- Refactoring.
- Maintenance.
- Recovery.
- Security inspection.

Compare:

```text
Human + frontier assistant
Ordinary coding agent
GAGOS without skills
GAGOS with learned skills
GAGOS with cloud unavailable
```

Measure:

- Verified completion.
- Human interruptions.
- Cloud calls.
- Cloud cost class.
- Local completion rate.
- Skill reuse rate.
- Incorrect reuse.
- Scope violations.
- Regression rate.
- Recovery success.
- Time to completion.
- Operator understanding.

## Gate

R15 functional acceptance requires:

- Zero authority bypasses.
- Zero accepted capability replays.
- Zero unapproved scope expansion.
- 100% local job-schema validity after bounded retries.
- At least three demonstrated cloud-to-local skill transfers.
- At least one correctly refused skill reuse.
- At least one maintenance repair closed by rescan.
- At least one failed repair remaining unpromoted.
- EmergencyStop proof.
- Full backend/frontend/CI/CodeQL/runtime gates green.

## Suggested commit

```text
test(r15): prove sovereign intelligence flywheel end to end
```

---

# R15 Slice 15 — R15 Handoff

## Required artifacts

```text
docs/r15/
├── LOCAL_WORKFORCE.md
├── FRONTIER_INTELLIGENCE_HIRING.md
├── VERIFIED_SKILL_LEARNING.md
├── AUTONOMOUS_MAINTENANCE.md
├── R15_TRUST_MODEL.md
├── R15_DEMO_SCRIPT.md
└── R15_KNOWN_LIMITATIONS.md

release/r15/
├── runtime-proof.json
├── acceptance-report.md
├── benchmark-results.json
├── environment-manifest.json
├── model-qualification-redacted.json
├── maintenance-evidence.json
└── test-summary.txt
```

## Final R15 handoff

- Freeze source SHA.
- Release builder lease.
- Request non-builder review.
- Require architecture, security, frontend and operator verdicts.
- Fix only findings that block R15 acceptance.
- Do not start R16 until verdict is recorded.

---

# PART II — R16

# R16: Product Readiness, Research Credibility and Alpha Release

## R16 mission

R16 must not expand the organism.

R16 transforms the R15 system into:

- An installable product.
- A truthful operator experience.
- A reproducible research artifact.
- A stable public alpha.
- A credible demonstration for recruiters, engineers and researchers.

R16 is successful when someone who did not build GAGOS can install it, operate it, understand it, reproduce its evidence and explain its limitations.

---

# R16 Architectural Freeze

After R15 acceptance, major new architecture is prohibited.

## Allowed

- Consolidation.
- Removal of duplicate paths.
- Reliability repairs.
- Security hardening.
- UX completion.
- Performance work.
- Packaging.
- Documentation.
- Tests.
- Observability.
- Accessibility.
- API stabilisation.
- Migration safety.

## Not allowed

- New Queens.
- New orchestration spine.
- New authority.
- New memory system.
- New event bus.
- New executor.
- New swarm architecture.
- New model marketplace.
- New autonomous browser system.
- New weight-training pipeline.
- Major visual redesign.
- Speculative features.

Any new capability must prove that it is required for product readiness rather than architectural curiosity.

---

# R16 Slice 0 — Product Truth Audit

## Goal

Create an exact inventory of what is:

```text
production default
optional but tested
experimental
adapter-only
deprecated
dead
not implemented
```

## Audit

- Routes.
- Providers.
- Workers.
- Queens.
- Swarm strategies.
- Maintenance.
- Voice.
- Memory stores.
- Frontend panels.
- Events.
- Config flags.
- Runtime profiles.
- Documentation claims.
- Release commands.

## Gate

Every public feature claim maps to a reachable product path and executable evidence.

## Suggested commit

```text
audit(r16): establish exact product truth inventory
```

---

# R16 Slice 1 — Canonical Path Consolidation

## Goal

Remove or quarantine duplicated and compatibility execution paths.

## Targets

- Provider routing.
- Mission origination.
- Approval compatibility.
- Worker strategy registration.
- Memory reads and writes.
- Event schemas.
- Maintenance state.
- Mirror snapshots.
- Configuration sources.
- Launcher paths.

## Rules

- One canonical path per authority.
- Compatibility adapters remain only where migration requires them.
- Deprecated paths emit clear warnings.
- Dead paths are deleted with tests.
- Public APIs do not expose experimental strategies as production-ready.

## Gate

Architecture tests enforce canonical ownership.

## Suggested commit

```text
refactor(r16): converge product on canonical authority paths
```

---

# R16 Slice 2 — One-Command Installation and Launch

## Goal

A fresh operator can install and launch GAGOS without hidden developer knowledge.

## Required commands

Aim for:

```text
gagos doctor
gagos setup
gagos start
gagos stop
gagos status
gagos v1-check --strict
```

## `gagos doctor`

Check:

- Python.
- Node.
- Docker.
- Ollama.
- Ports.
- Writable data directories.
- Executor availability.
- Frontend build.
- Required model presence.
- Cloud-provider configuration.
- Identity state.
- Database compatibility.
- Disk space.
- RAM profile.

It must show:

```text
ready
optional missing
blocking missing
unknown
```

## Setup requirements

- Generate local non-secret configuration.
- Explain secrets without storing them improperly.
- Run migrations idempotently.
- Create directories safely.
- Refuse unsupported configurations clearly.
- Never silently weaken isolation.

## Gate

A clean Windows VM or user profile completes setup from documentation alone.

## Suggested commit

```text
feat(r16): deliver one-command truthful installation and launch
```

---

# R16 Slice 3 — Human Sovereign Onboarding

## Goal

Make identity, privacy and authority understandable.

## Onboarding flow

1. Explain what GAGOS controls.
2. Enroll the Human Sovereign.
3. Create secure credentials.
4. Explain local versus cloud intelligence.
5. Configure provider permissions.
6. Enroll project roots.
7. Configure risk posture.
8. Configure cost budget.
9. Configure local workforce.
10. Run system health proof.
11. Enter the Living Mirror.

## Human decisions

- Which data may leave the machine.
- Which cloud providers are allowed.
- Maximum cost class.
- Allowed project roots.
- Autonomy posture.
- Local workforce approval.
- Telemetry posture.
- Retention policy.

## Gate

No critical authority setting depends on editing `.env` manually without explanation.

## Suggested commit

```text
feat(r16): complete Human Sovereign onboarding
```

---

# R16 Slice 4 — Mission Control UX Completion

## Goal

A non-builder can operate the entire mission lifecycle through the product.

## Required states

```text
PROPOSED
DELIBERATING
BLOCKED
AWAITING_APPROVAL
APPROVED
WORKER_STARTING
EXECUTING
VERIFYING
PROMOTING
ROLLING_BACK
COMPLETED
FAILED
CANCELLED
STOPPED
```

## Approval view

Before approval, display:

- Exact action.
- Exact project.
- Exact files or scope.
- Exact tools.
- Risk class.
- Privacy effect.
- Estimated cost.
- Reversibility.
- Verification requirements.
- Capability expiry.
- Why approval is needed.

## Gate

No generic “Approve” action exists without an exact contract summary.

## Suggested commit

```text
feat(r16): finish exact Human mission-control experience
```

---

# R16 Slice 5 — Living Mirror Reliability and Accessibility

## Goal

Make the interface truthful, resilient and usable rather than merely impressive.

## Requirements

- Durable event cursor recovery.
- Snapshot refresh after stale state.
- Reconnection after backend restart.
- Clear unknown states.
- No fictional worker activity.
- No success animation before verification.
- Keyboard navigation.
- Accessible labels.
- Readable text contrast.
- Reduced-motion mode.
- Resource-aware visual quality.
- Mobile or narrow-screen read-only governance view.
- Graceful WebGL context recovery.
- No loss of critical controls when 3D fails.

## Gate

The core product remains operable when the 3D canvas is unavailable.

## Suggested commit

```text
fix(r16): harden truthful Living Mirror operation
```

---

# R16 Slice 6 — Crash Recovery and Idempotency

## Goal

Prove that interruption does not corrupt authority or state.

## Test failures during

- Approval issuance.
- Capability consumption.
- Worker creation.
- Executor request.
- Evidence persistence.
- Verification.
- Promotion.
- Rollback.
- Memory proposal.
- Maintenance scan.
- SSE delivery.

## Requirements

- Mission state survives restart.
- Consumed capabilities remain consumed.
- Incomplete promotions are detected.
- Staged workspaces are reconciled.
- Orphan workers are handled.
- Audit chains remain valid.
- Duplicate callbacks are idempotent.
- Findings remain consistent.
- Operator sees recovery state.

## Gate

Kill-and-restart tests pass at each critical transition.

## Suggested commit

```text
test(r16): prove crash-safe mission and authority recovery
```

---

# R16 Slice 7 — Security Hardening

## Goal

Perform an adversarial audit rather than adding new security branding.

## Threat-model categories

- Session theft.
- CSRF.
- Origin confusion.
- Capability replay.
- Capability substitution.
- Contract tampering.
- Path traversal.
- Symlink escape.
- Command injection.
- Prompt injection.
- Secret exfiltration.
- Cloud routing bypass.
- Worker privilege escalation.
- Executor impersonation.
- Audit tampering.
- Memory poisoning.
- Skill poisoning.
- Scanner suppression.
- EmergencyStop bypass.
- Malformed Mirror events.
- Dependency compromise.

## Required evidence

- Threat model.
- Attack trees.
- Negative tests.
- Fuzzing where practical.
- Dependency scan.
- Secret scan.
- Security limitations.
- Recovery procedures.

## Gate

Every high-risk boundary has a negative test or documented untested limitation.

## Suggested commit

```text
security(r16): complete adversarial product hardening
```

---

# R16 Slice 8 — Laptop Resource and Performance Profiles

## Goal

Make GAGOS reliable on the operator’s actual Dell G15 instead of assuming server hardware.

## Profiles

```text
safe
normal
performance
offline
demo
production
```

## Manage

- Local-model context.
- Local-model concurrency.
- Worker concurrency.
- Docker memory.
- Executor CPUs.
- Frontend quality.
- Memory indexing.
- Planner calls.
- Reflection calls.
- Cloud burst.
- Hibernation scans.
- Log retention.

## Requirements

- No silent OOM recovery that changes authority.
- No model auto-selection that exceeds admission.
- Thermal/resource pressure is visible.
- Resource refusal explains the reason.
- Frontend remains responsive during local inference.
- Production profile never falls back to unsafe host execution.

## Gate

A full accepted demonstration runs on the laptop without uncontrolled resource exhaustion.

## Suggested commit

```text
perf(r16): enforce resource-aware single-laptop operation
```

---

# R16 Slice 9 — Observability, Audit and Evidence Export

## Goal

Allow operators and reviewers to understand what happened without reading internal databases.

## Export one mission dossier containing

- Human principal.
- Goal.
- Contract.
- Council verdicts.
- Capabilities.
- Worker identities.
- Model calls.
- Data-classification decisions.
- Tool actions.
- Diff.
- Evidence.
- Verification.
- Promotion/rollback.
- Memory proposals.
- Maintenance findings.
- Cortex events.
- Final status.
- Digests and timestamps.

## Privacy

Exports are redacted by default.

Secrets and raw credentials never appear.

## Gate

A reviewer can audit one complete mission from the exported dossier alone.

## Suggested commit

```text
feat(r16): export complete redacted mission evidence dossiers
```

---

# R16 Slice 10 — Documentation and Claim Hygiene

## Goal

Remove stale truth and make every public claim defensible.

## Required documents

```text
README.md
ARCHITECTURE.md
TRUST_MODEL.md
SECURITY.md
THREAT_MODEL.md
PRIVACY.md
LOCAL_WORKFORCE.md
INTELLIGENCE_HIRING.md
SKILL_LEARNING.md
MAINTENANCE.md
OPERATOR_HANDBOOK.md
FIRST_RUN.md
DEMO_SCRIPT.md
KNOWN_LIMITATIONS.md
TROUBLESHOOTING.md
CONTRIBUTING.md
RESEARCH_METHOD.md
PRIOR_ART.md
```

## Claim categories

Each feature is labelled:

```text
Implemented and runtime-proven
Implemented but optional
Experimental
Planned
Not supported
```

## Approved public description

> GAGOS is an open-source alpha research prototype of Autonomous Sovereign Intelligence: a model-agnostic AI operating system where local and cloud intelligence can be hired as replaceable cognitive labour, temporary agents execute bounded missions, verified expert experience becomes reusable institutional knowledge, and deterministic local authorities preserve Human sovereignty over permissions, execution, memory and truth.

## Narrow originality wording

> To our knowledge, GAGOS is the first publicly reproducible single-operator prototype combining exact capability-based Human sovereignty, governed local-plus-cloud intelligence, permanent cognitive organs, temporary ant-colony workers, evidence-gated promotion, verified institutional learning, autonomous maintenance and a truthful living interface.

Always preserve “to our knowledge” until a serious independent prior-art review supports stronger language.

## Suggested commit

```text
docs(r16): align every public claim with executable product truth
```

---

# R16 Slice 11 — Research Evaluation

## Goal

Produce evidence that GAGOS improves the workflow of one developer.

## Evaluation questions

1. Does GAGOS reduce meaningful Human interruptions?
2. Does it complete useful tasks without increasing regressions?
3. Does verified skill reuse reduce repeated cloud dependence?
4. Does it refuse invalid skill reuse?
5. Does the sovereignty architecture block unsafe model behaviour?
6. Does maintenance detect and close real controlled issues?
7. Can an operator understand why the system acted?
8. Can the same institution use different frontier models without changing authority?

## Publish

- Benchmark methodology.
- Task fixtures.
- Baselines.
- Raw redacted results.
- Limitations.
- Failed hypotheses.
- Statistical summary where meaningful.
- Reproduction instructions.

## Gate

Research conclusions cannot exceed the collected evidence.

## Suggested commit

```text
research(r16): publish reproducible single-developer evaluation
```

---

# R16 Slice 12 — Clean-Room Non-Builder Acceptance

## Goal

A person who did not build GAGOS completes the full workflow.

## Acceptance run

The operator must:

1. Clone the tagged candidate.
2. Run doctor/setup/start.
3. Enroll as Human Sovereign.
4. Configure one local clerk.
5. Configure or intentionally omit a cloud provider.
6. Enroll a sample project.
7. Submit a bounded feature or repair goal.
8. Review Council output.
9. Approve an exact capability.
10. Watch temporary-worker execution.
11. Inspect staged changes.
12. Inspect verification evidence.
13. Observe promotion or rollback.
14. Trigger a maintenance scan.
15. Review the local clerk’s report.
16. Complete a governed maintenance repair.
17. Inspect a learned skill.
18. Demonstrate invalid skill escalation.
19. Engage EmergencyStop.
20. Export the mission dossier.

## Acceptance rule

Any undocumented intervention by the original builder is a product-readiness failure.

## Gate

The non-builder signs a hash-pinned verdict containing:

```text
PASS
PASS WITH DECLARED LIMITATIONS
BLOCK
```

## Suggested commit

```text
docs(r16): record clean-room operator acceptance
```

---

# R16 Slice 13 — Alpha Release

## Release identity

Use an honest alpha tag, such as:

```text
v1.0.0-alpha.1
```

Do not call it production-ready.

## Release package

```text
release/
├── source-manifest.json
├── environment-manifest.json
├── runtime-proof.json
├── test-summary.txt
├── benchmark-results.json
├── security-report.md
├── threat-model.md
├── acceptance-report.md
├── known-limitations.md
├── mission-dossier-example.json
├── architecture-code-grounded.png
└── checksums.txt
```

## Release gates

- Clean worktree.
- Version consistency.
- Migrations tested.
- Backend full gate green.
- Frontend full gate green.
- CI matrices green.
- CodeQL green.
- Runtime proof green.
- Security negative tests green.
- Clean-room acceptance recorded.
- Documentation current.
- No secrets.
- Dependency licenses reviewed.
- Release artifacts reproducible.
- Known limitations explicit.

## Suggested commit

```text
release: prepare GAGOS v1.0.0 alpha research prototype
```

---

# R16 Slice 14 — Public Demonstration and Outreach Package

## Demonstration length

Create:

- A 3-minute overview.
- An 8–12-minute complete mission demonstration.
- A deeper architecture walkthrough.
- A written technical report.

## Demonstration sequence

```text
Human goal
→ Council deliberation
→ exact authority request
→ frontier expert hired
→ temporary worker born
→ staged execution
→ verification
→ promotion
→ skill extraction
→ similar local reuse
→ maintenance finding
→ governed repair
→ rescan resolution
→ EmergencyStop refusal
→ mission evidence export
```

## Show failures deliberately

Include:

- Scope refusal.
- Capability replay refusal.
- Skill applicability refusal.
- Verification failure.
- Cloud-unavailable local continuity.
- EmergencyStop.

This proves the system is not a scripted success animation.

## Outreach focus

Do not lead with “many agents.”

Lead with:

> GAGOS allows AI to work independently without allowing intelligence to become authority.

Then prove:

- Model replaceability.
- Lower Human interruption.
- Verified institutional learning.
- Local maintenance continuity.
- Evidence-backed completion.
- Human-owned control.
