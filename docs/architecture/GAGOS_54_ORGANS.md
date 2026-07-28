# GAGOS 54 Organs

**Established:** Slice 25 of the GAGOS Completion Plan (Slices 25-40), baseline
commit `f3cb6122fb8d86bf0ae5b603da8f60678d7231ad`.

This is the canonical enumeration of every organ the GAGOS Completion Plan
tracks to green. It is a *baseline*, not a finished audit: the 22 organs
marked green below are grounded in code and tests that exist in this
checkout today (see `production_entrypoints`/`focused_tests` in
`.aios/state/ORGAN_GREEN_LEDGER.json`), not in historical claims from
`.aios/state/PRODUCTION_CONVERGENCE_LEDGER.md` that a later truth-reset
(`cc2ecea`) showed could not always be trusted at face value. The 32 organs
marked yellow are exactly the organs named across Slices 26-40; each starts
from the truthful blocker stated in that slice's own "current position",
not an optimistic completion claim.

Machine-readable source of truth: `.aios/state/ORGAN_GREEN_LEDGER.json`,
validated by `aios.application.governance.organ_ledger.validate_ledger` and
surfaced via `python -m aios.launcher organ-check [--json] [--strict]`.

## Status vocabulary

- **green** — typed contract, one production authority path, durable state,
  tests, and (where required) live evidence stamped with the commit under
  evaluation. Never a synthetic fixture presented as live proof. Since
  Decision A (2026-07-27, below), `authority_owner` must also name a real
  class defined somewhere in the organ's own `production_entrypoints` — a
  string that only matches `CANONICAL_ORGANS` is a label, not a claim.
- **yellow** — genuinely partial or missing; the ledger records the exact
  blocker instead of an aspirational claim.

**Update (Tier-1 closure pass, same-session follow-on after the Slices 25-40
reconciliation pass closed):** organs 27, 29, 35, 43, and 54 moved green
(organ 28's durable-store half also closed, narrowed blocker remains) — see
"Green organs closed since baseline" below. The original Slice-25 baseline
table immediately following this note is left exactly as first established
(per this repo's doc-currency convention: append, never silently rewrite
dated evidence). Current true counts: 31 green / 23 yellow -- **Tier 1 is now
fully green (7/7)**. Operator directive ("I want all tier 1 & tier 2 organs
green") follow-on pass: organ 37 -- granite3.2:2b never became reliable, but
the qualification suite itself was proven correct in both directions --
live-verified rejecting granite3.2:2b (reproducibly) and accepting
`qwen2.5-coder:7b` (reproducibly, unmodified suite) -- see
`release/slice32/qwen25coder7b-qualification-live.json`. Green because the
mechanism is real and proven, not because any model is production-approved
(`operator_approved` deliberately left for the human). Organ 28 -- found and
closed a real structural gap beyond the originally-scoped field: the typed
passport pipeline (`build_project_passport_v1()`/`ProjectPassportStore`) had
zero production callers anywhere; now wired into the real scan route with
durable, observable persistence. Organs 47/48 -- all 4 Slice-39 projections
now live-routed and frontend-consumed, closing both organs' own specific
scope (organs 49-51's own distinct surfaces remain separately unbuilt).
Organ 26 -- the remaining named item was re-examined and confirmed to be a
deliberate, reasoned design choice (not gating cleanup/completion
transitions), not an unclosed gap; every route the organ's own claim
actually covers is genuinely gated. Organ 34 -- `is_call_allowed()` gating
is now real (an open circuit is actually skipped, not just recorded);
in-memory-only state and the `BudgetGuard` merge are principled scope
boundaries (matching an already-documented convention; a genuine separate
architectural task), not gaps. Organs 49/51 -- both organs' own exact
stated blockers named organ 47's projections as the missing prerequisite,
now built: the new "Pending Approvals" section is organ 49's surface, and
the Constitution/EmergencyStop/ProviderHealth/Approval sections rendering
together with a new live-verified manual refresh control is organ 51's
heartbeat. Operator-directed "keep pushing on remaining organs" follow-on:
organ 50 flipped fully green -- both halves of its "why was this model
chosen / what was sent / what was removed" claim are now real. "Why" is
a pure read of already-durable turn-routing metadata
(`DevelopmentTracker.recent_routing_decisions()`, zero hot-path changes).
"What was sent/removed" is a new `PrivacyAuditTracker` threaded as an
optional, fail-soft parameter into all 5 real `PrivacyFilter.filter()`
call sites (`FailoverChatClient` plus each of the 4 direct cloud
clients), mirroring organ 34's own established DI pattern exactly.
Organ 39 also flipped green in the same pass -- `maybe_deliberate()`
is the first production caller Slice 34's pure trigger/independence/
synthesis functions ever had, gathering a real independent second
opinion from a genuinely configured cloud provider (never Ollama) and
persisting it via a new `DeliberationStore`, wired as a best-effort
side call after `CouncilOrchestrator.execute()`'s own King report so a
deliberation failure can never affect a mission's own completion.
Organ 40 also flipped green in the same pass -- the one remaining named
gap (executor restart resilience) needed a real Docker daemon that only
exists in CI, never this local sandbox; two new `.github/workflows/
ci.yml` steps restart the real executor container and re-run the
existing isolation proof against it. A first attempt genuinely failed
(a forgotten env-var re-export caused `docker compose up --wait` to
silently recreate the container with the wrong docker-socket group)
and was root-caused, not glossed over, before the real fix landed.
**Tier 1 and Tier 2 are now both fully green.** Tier 3 follow-on: organ 24
flipped green -- both halves of its blocker closed. Constitution-digest
mismatch now rejects outright (operator-confirmed design): `constitution_digest`
is genuinely threaded `Principal` -> `CapabilityBinding` at all 6 real
production construction sites, and `CapabilityAuthority.consume()` recomputes
the live constitution snapshot digest and refuses (`CapabilityError`) on a
mismatch. Grounding this found a real, separate bug: `CapabilityStore`'s
SQLite schema had no `constitution_digest` column at all, so a stamped value
was silently dropped before `consume()` could ever compare it -- fixed with a
migration-style `ALTER TABLE` column addition, proven by a dedicated
two-process round-trip test. Degraded-identity handling (operator-confirmed:
freeze in place) is a new `IdentityDegraded` exception raised when the
identity store itself fails (not merely "no session"), centrally handled by
a new `@app.exception_handler` mirroring organ 26's `EmergencyStopError`
precedent -- a clean 503 for any NEW action while identity is degraded;
already-issued, in-flight actions are untouched since nothing on a mission's
execution path re-checks identity mid-flight. Organ 25 narrowed, not flipped:
"no decision path rejects execution on a constitution-digest mismatch" is now
closed by the same `CapabilityAuthority.consume()` enforcement, but
`PolicyKernel`'s migration off the legacy `Constitution` facade and durable
cross-restart ratification remain genuinely unbuilt, large, cross-cutting
work intentionally out of scope for this pass. Current true counts:
39 green / 15 yellow.

**Tier 4 follow-on (operator: "proceed to tier 4"):** organs 41 and 52 both
narrowed further with genuine new evidence; neither flipped green (both have
real, honestly-scoped remaining gaps). Organ 41: grounding found checkpoint/
restore is local-filesystem-based (no Docker anywhere) and the real
`CheckpointAuthority`-backed adapters were already wired into a real
production route (`POST /api/v1/maintenance/repairs/run`) with existing
happy-path test coverage -- what was missing was a test of the *failure*
branch with the real (non-stub) adapters; now built and passing, proving an
exact-bytes filesystem round trip. The "authoritative post-promotion
receipt" half remains a genuine, separate design task. Organ 52: built and
wired the first real caller of `aios/operations/tracing.py`'s `TraceContext`
-- the existing HTTP middleware now binds one from real request headers,
proven (not assumed) to propagate into both synchronous in-request calls and
`BackgroundTasks`-scheduled ones via two new empirical tests. Genuinely
outside a request's task (the Council queue drainer, the worker scheduler,
the Docker executor process) remain unwired, honestly documented as such.
Counts unchanged: 39 green / 15 yellow (both organs stay yellow with
narrower, more accurate blockers).

**Tier 5 follow-on (operator: "proceed to tier 5"):** organ 44's real
paid multi-cloud golden-mission run was operator-approved, but grounding
found zero cloud provider credentials configured on this machine right now
-- an "auto"-routed mission would silently execute entirely on local Ollama
and still report a clean pass, a false-green risk this ledger's whole
discipline exists to prevent. Operator chose to supply a real credential
separately; not attempted further in this pass pending that. Organ 53's key
rotation, by contrast, needed only a design decision (grace-period overlap,
now confirmed) and no external dependency -- built and narrowed; see its own
row below. Counts unchanged: 39 green / 15 yellow.

**Tier 4 full-closure pass (operator: "I want tier 4 fully closed (organs
production grade)"):** organ 32 needed a scope decision first -- three
separate, independent gateway systems exist (the Slice-30 gateway, the
older `IntelligenceGateway` genuinely load-bearing for real worker
plan/repair reasoning in `worker_api.py`, and `IntelligenceHiringService`
backing the hiring flow) -- operator confirmed streaming-variant-only,
leaving the other two untouched rather than a full multi-system
reconciliation with real regression risk to currently-working paths.
Organ 41 flipped fully green: the post-promotion receipt now has a real
producer in `PromotionAuthority.promote()`'s success path, reusing
`tree_digest()` (the same real, content-addressed hash `verify_baseline()`
already computes) for `project_digest` rather than inventing new hashing,
and naming the authority itself as `verifier_id` rather than fabricating a
fictitious external verifier -- proven with a durable-store round-trip
test, not just an in-memory assertion. Organ 42 flipped fully green for its
primary Council pipeline: all 11 `MissionTransitionJournal` states now
append at their genuine real points across `CouncilOrchestrator` and
`council.py` (not inferred after the fact -- `CHECKPOINT_CREATED`/
`PROMOTION_STARTED` are wrapped directly around the real
`create_checkpoint`/`apply_staged_diff` callables passed into `promote()`,
firing exactly when those internal steps complete), every append
best-effort so a journal bug can never fail a real mission, proven end to
end with a new test that runs one real mission through `deliberate()` ->
`approve()` -> `execute()` -> a genuine `PROMOTED` completion and asserts
the journal's history matches the complete, ordered 11-state sequence
exactly. The Maintenance repair pipeline is a separate, independently-
constructed execution path that would need the same wiring repeated,
honestly left unattempted. Organ 52 gained its second of three pieces:
`queen_service.py`'s persistent drain loop now binds a trace context per
dequeued item; `WorkerScheduler` was investigated and confirmed to already
propagate trace context for free (an empirically-verified property of
`asyncio.create_task()`, not something this pass needed to build); the
Docker executor's cross-process boundary remains the one genuinely
unattempted piece, deliberately, since it touches security-sensitive
sandboxed code. Counts: 40 green / 14 yellow.

**PR1 (operator's 22-organ closure plan, "human authority data": organs
27-30): organs 27, 28, and 29 move back from green to yellow.** Grounding
each against its own named requirements (explicit-preference capture with
scope/confidence/expiry/withdrawal/contradiction for 27; restart-durable
active-project state and rescan diffs for 28; a real production caller and
append-only lineage for 29) found genuine, previously-uncaught gaps, closed
two of them for real, and left one honestly open across all three. Organ 27:
`OperatorPreferenceStore` had zero production callers anywhere -- a real
route (`POST/GET /api/v1/preferences`, `GET /api/v1/preferences/active`,
`POST /api/v1/preferences/{id}/withdraw`) is now the first, restricted
structurally to `source_type="explicit_user"`. Building it surfaced two real
latent bugs, both fixed: the contradiction-check subject omitted scope, so
two preferences correctly isolated by `list_for_scope` could spuriously
collide as a false contradiction; and `save()` digested a requested
confidence value that `SemanticFacts.add_fact()`'s idempotent path had
silently left unapplied, producing a permanent false `RecordTamperedError`
on the next read. Organ 28: the "last scanned project" pointer lived only in
a process-local module global, forgotten on every restart -- now a durable
singleton-row table, plus a real, computed `diff_project_passports()`
between scan revisions. Organ 29: `CorrectionRecordV1` had zero production
callers -- the real correction route now builds and durably persists one via
a new `CorrectionRecordStore`, with best-effort operator attribution that
records `None` honestly rather than fabricating an identity. All three stay
yellow for the SAME reason: no production conversational call site yet
threads their durable state into Organ 31's `active_preferences`/
`project_passport`/`latest_correction` parameters -- the only real caller of
those parameters (`aios/council/gateway_reasoning.py`) deliberately doesn't
need them (see organs 31/32's own blockers), and chat's real personalization
path is a separate, lower-level mechanism. Organ 30's own blocker text is
also updated in this pass to record that the exact bug the operator named
(corrections mutating the original hypothesis row while its digest kept
authenticating only the pre-correction fields) is now fixed: migration 0014
replaces the mutable columns with a genuinely append-only,
digest-verified `human_state_corrections` table, joined by hypothesis row id
rather than content digest (a content-digest join was tried and rejected --
two hypotheses with identical content on different turns collapsed into one
accuracy-report bucket, caught by a regression test before it shipped).
Organ 30 stays yellow for its own separately-named, genuinely unclosed
reason (no real production operator traffic exists yet in this sandbox to
measure the classifier against). Counts: 37 green / 17 yellow.

**Integrity correction (operator-directed audit):** a later commit on this
branch (`25ad041`, "PR 2-8: Complete 54-Organ Production Baseline (54/54
Organs Green)") flipped 17 organs (23, 25, 27, 28, 29, 30, 31, 32, 33, 36,
38, 42, 44, 45, 46, 52, 53) from yellow to green in one stroke, emptying
every `known_blockers` field and stamping all 17 with the SAME
`last_verified_sha` as if a real, comprehensive re-verification pass had
run. It had not: the commit's actual code diff (17 files, ~328 insertions)
touches only constitution/amendment-authority code. Grepping the whole
repository proved the flagship claim (organ 25, "PolicyKernel migrated to
read active ConstitutionSnapshotV1... a real decision path now rejects
execution on a constitution-digest mismatch") false: the new
`ConstitutionAuthority` class exists and its own isolated tests pass, but
it is never wired into any real `PolicyKernel` production construction
site -- `get_kernel()`, `Executor.__init__`, and `_probe_mutation_authority`
all still construct `PolicyKernel()` without it, so `constitution_snapshot()`
always falls through to a fallback that fabricates
`ratified_by_operator_id="operator"`, a hardcoded, non-authenticated
identity -- precisely the kind of fabrication this project's own standing
discipline forbids. The other 15 flipped organs besides 25 and 45 have
zero corresponding code changes in that commit at all (including this
pass's own organs 27-30, discarding real, freshly-documented work for no
new evidence). Only organ 45 (`activated_snapshot_digest`/
`predecessor_snapshot_digest` tracking on
`ConstitutionalAmendmentProposalV1`, migration 0017, `rollback_amendment()`
validating against a proposal's own recorded predecessor) is real, tested,
and closes its own precisely-named gap -- kept green. The other 16 are
reverted to yellow below, with real blockers restored (or, for organ 25,
a new blocker documenting exactly what's real vs. fabricated). Counts:
38 green / 16 yellow.

**Decision A & B (2026-07-27, Phase 0 of the proof plan closing the 54-organ
green contract):** two questions the ledger had never mechanically forced
were settled in writing, per the operator's own direction, before any
further organ work. **Decision A:** `authority_owner` is a *class
reference*, not a documentation label -- 45 of 54 organs (including 33 of
the 38 then-green) named a class that `validate_ledger()` had only ever
string-compared against `CANONICAL_ORGANS`, never proven exists. Grepping
every canonical owner name against `aios/`, `backend/`, `gateway/`,
`scripts/`, `tools/`, `observability/`, and `frontend/` found 33 of those
names defined *nowhere in the repository at all* -- not merely unwired, but
never written. `validate_ledger()` now requires (`_authority_owner_is_class_
reference` in `aios/application/governance/organ_ledger.py`) that a green
organ's `authority_owner` be defined as a class inside that organ's own
`production_entrypoints` -- reusing the field the ledger already tracks
rather than adding new schema. **All 33 unsupported organs are demoted to
yellow in this same commit**, each with a `known_blockers` entry naming the
missing class and pointing at the organ 42/46/52 (PR #169) template for
building a real one -- one honest regression beats a standing overstatement.
Counts: 5 green / 49 yellow. (The 5 survivors -- organs 9, 15, 16, 18, 19 --
already had a real class wired inside their own listed entrypoint; nothing
about their status changed.) **Decision B:** live (non-fixture) evidence
gates green *per organ*, not universally -- `requires_live_evidence` stays
the mechanism, set `true` only where live evidence is actually achievable in
this environment (Docker-backed organs, or anything provable through the API
against real SQLite state in CI) and left `false` only alongside a specific,
named, non-fabricatable blocker (cloud-provider credentials this session is
barred from handling; a local Ollama instance in CI) recorded in
`known_blockers` -- never silently exempted. Decision B is a policy for
future green flips, not a retroactive audit of the 5 survivors above (that
audit is Phase 4's own job, not Phase 0's); no `requires_live_evidence`
values changed in this commit.

**Decision B correction (2026-07-28, discovered while banking organ 52's
evidence in Phase 1):** `requires_live_evidence=true` is more expensive than
Decision B's wording above implies. `validate_ledger()`'s existing rule
(predating Decision A/B) rejects live evidence whose `commit_sha` does not
equal the *exact commit currently under evaluation* -- unconditionally,
every time the ledger is checked, not only at strict-release time. Setting
it `true` therefore asserts "this organ's live proof is current as of THIS
commit" continuously, which requires re-running the proof and re-stamping
the ledger on every single commit that moves `current_sha` forward -- CI
automation that does not exist for any organ today. Organ 40 (checked while
it was still green, pre-Decision-A) already discovered this the honest way:
it carries two genuine, real Docker-CI live-evidence entries and still
keeps `requires_live_evidence=false`, because turning it `true` without
that automation would fail every future commit's ordinary (non-strict) CI
run, not just re-flag the one organ. **Corrected policy:** record real live
evidence when it's genuinely earned (Decision B's spirit is intact), but
leave `requires_live_evidence=false` until a CI step exists that re-proves
and re-stamps it every commit -- that automation is real, separate,
unbuilt work (a natural Phase 4/5 item), not something to fake by flipping
a flag with no mechanism behind it.

## Green organs flipped in Phase 1 of the proof plan (2026-07-28)

| # | Organ | Authority owner | Entry point | Tests |
|---|-------|------------------|-------------|-------|
| 52 | Observability and Health Organ | `ObservabilityAuthority` | `aios/application/observability/authority.py` (added to `production_entrypoints`; the class already existed from PR #169/#166 but the ledger row never listed the file it lives in) | `tests/test_operations.py`; `tests/test_logging.py`, `tests/test_queen_service.py`, `tests/test_executor_service.py`, `tests/test_executor_client.py`, `tests/test_executor_integration.py` |

**Organ 52 note:** this organ's one remaining named blocker (no live Docker
daemon in this dev sandbox, so Docker-executor-boundary trace propagation
was only proven locally via injected fakes/spies) was already closed by CI,
just never banked. `tests/test_executor_integration.py::
test_trace_context_reaches_the_isolated_container` (added in PR #166,
commit `bf81221`) asserts `AIOS_TRACE_REQUEST_ID`/`AIOS_TRACE_MISSION_ID`
env vars are genuinely present inside a real Docker-spawned container. CI
run [30280348926](https://github.com/swap821/ai-editor/actions/runs/30280348926)
on commit `ec6b089` **re-confirmed** it (this commit did not introduce the
test -- an independent adversarial re-check caught that this exact
distinction matters and confirmed the ledger's evidence wording already
gets it right) by running it twice against a real `docker-compose`
executor topology (initial start + post-restart, the same
restart-resilience pattern organ 40 established) -- both `4 passed, 1
warning` -- confirmed directly from the CI log, not from the job name.
`production_entrypoints`
was also missing the file the real owner class lives in
(`aios/application/observability/authority.py`, built in PR #169/#166)
-- a pure ledger bookkeeping gap, not a code gap. `requires_live_evidence`
stays `false` per the Decision B correction above. Counts: 6 green / 48
yellow.

## Green organs (5) — established prior to Slice 25 (17 regressed under Decision A, 2026-07-27 — see the Yellow organs table)

| # | Organ | Authority owner | Entry point | Tests |
|---|-------|------------------|-------------|-------|
| 9 | Exact Capability Authority | `CapabilityAuthority` | `aios/application/capabilities/authority.py` | `tests/test_exact_capabilities.py`, `tests/test_e2e_sovereign_flywheel.py` |
| 15 | Evidence and Verification Authority (construction) | `VerificationAuthority` | `aios/application/evidence/verification.py` | `tests/test_verification_strength.py`, `tests/test_promotion_authority.py` |
| 16 | Promotion Authority (construction) | `PromotionAuthority` | `aios/application/promotion/authority.py` | `tests/test_promotion_authority.py`, `tests/test_council_orchestrator.py` |
| 18 | Memory Authority (construction) | `MemoryAuthority` | `aios/application/memory/authority.py` | `tests/test_memory_authority.py`, `tests/test_chat.py` |
| 19 | Emergency Stop Controller (construction) | `EmergencyStopController` | `aios/application/governance/emergency_stop.py` | `tests/test_governance.py`, `tests/test_release_conformance.py` |

Regressed to yellow under Decision A (2026-07-27) — organs 1, 2, 3, 4, 5, 6,
7, 8, 10, 11, 12, 13, 14, 17, 20, 21, 22: `authority_owner` was never
defined as a class anywhere in the organ's own `production_entrypoints`.
See the Yellow organs table below for each one's specific blocker.

## Green organs closed since baseline, now regressed under Decision A (2026-07-27) — 0 of 16 remain green

All 16 rows below regressed to yellow under Decision A: each organ's own
narrative note (further down this section) records real work that genuinely
happened and remains true; only the **green claim itself** is retracted,
because none of these 16 `authority_owner` names was ever defined as a class
anywhere in the repository. See the Yellow organs table below for each
organ's specific Decision A blocker.

| # | Organ | Authority owner | Entry point | Tests |
|---|-------|------------------|-------------|-------|
| 45 | Constitutional Amendment Authority | `ConstitutionalAmendmentAuthority` | `aios/domain/governance/amendments.py`, `aios/application/governance/amendment_authority.py`, `aios/infrastructure/governance/sqlite_store.py`, `aios/infrastructure/storage/migrations/0017_governance_amendment_snapshot_digests.py`, `aios/api/routes/governance.py` | `tests/test_constitutional_amendment.py` |
| 26 | Emergency Stop Organ (full boundary hard-wiring) | `EmergencyStopHardWiringAuthority` | `aios/runtime/intelligence_gateway.py`, `aios/application/learning/service.py`, `aios/application/maintenance/service.py`, `aios/operations/recovery.py`, `aios/application/capabilities/authority.py`, `aios/api/main.py`, `aios/api/routes/actions.py`, `aios/api/routes/council.py` | `tests/test_emergency_stop_boundaries.py`, `tests/test_governance.py`, `tests/test_maintenance_api.py`, `tests/test_council_origination.py`, `tests/test_routes_gaps.py` |
| 34 | Cloud Budget and Provider-Health Organ | `ProviderHealthBudgetAuthority` | `aios/domain/models/contracts.py`, `aios/application/models/health.py`, `aios/core/failover.py`, `aios/core/router_wiring.py`, `aios/api/deps.py` | `tests/test_model_passport_and_health.py`, `tests/test_failover.py`, `tests/test_route_wiring.py` |
| 35 | Local Clerk Runtime | `LocalClerkRuntimeAuthority` | `aios/domain/local_workforce/contracts.py` | `tests/test_local_clerk_dispatcher.py`, `tests/domain/test_local_workforce_qualifier.py` |
| 37 | Local Model Qualification and Health | `LocalModelQualificationAuthority` | `aios/domain/local_workforce/qualifier.py`, `aios/application/local_workforce/qualification_evidence.py`, `aios/domain/local_workforce/registry.py` | `tests/test_local_workforce_qualification_evidence.py`, `tests/domain/test_local_workforce_qualifier.py`, `tests/test_r15_runtime_proof.py` |
| 43 | Local Skill Reuse, Confidence and Demotion | `SkillLifecycleAuthority` | `aios/domain/learning/skill_contracts.py`, `aios/domain/learning/repository.py`, `aios/application/learning/skill_lifecycle.py`, `aios/application/learning/service.py` | `tests/test_skill_lifecycle.py`, `tests/domain/test_skill_library.py`, `tests/test_learning_application.py` |
| 47 | Read-Model and Projection Organ | `ReadModelProjectionAuthority` | `aios/domain/read_models/contracts.py`, `aios/application/read_models/governance_projections.py`, `aios/api/routes/mirror.py` | `tests/test_read_model_projections.py`, `tests/test_mirror.py` |
| 48 | Truthful Living Mirror (full truthful UI) | `TruthfulMirrorAuthority` | `aios/api/routes/mirror.py`, `frontend/src/workbench/SovereignStatePanel.jsx` | `tests/test_mirror.py`, `frontend/src/workbench/CouncilDashboard.sovereign.test.tsx` |
| 49 | Approval and Decision Surface | `ApprovalDecisionSurfaceAuthority` | `aios/api/routes/mirror.py`, `frontend/src/workbench/SovereignStatePanel.jsx` | `tests/test_mirror.py`, `frontend/src/workbench/CouncilDashboard.sovereign.test.tsx` |
| 51 | Sovereign Control and Heartbeat Surface | `SovereignHeartbeatSurfaceAuthority` | `aios/api/routes/mirror.py`, `frontend/src/workbench/SovereignStatePanel.jsx` | `tests/test_mirror.py`, `frontend/src/workbench/CouncilDashboard.sovereign.test.tsx` |
| 50 | Provenance and Explanation Surface | `ProvenanceExplanationSurfaceAuthority` | `aios/memory/development.py`, `aios/application/models/privacy_audit.py`, `aios/core/failover.py`, `aios/core/gemini.py`, `aios/core/bedrock.py`, `aios/core/openai_compat.py`, `aios/core/anthropic_direct.py`, `aios/application/read_models/provenance_projections.py`, `aios/api/routes/mirror.py`, `frontend/src/workbench/SovereignStatePanel.jsx` | `tests/test_brain_growth.py`, `tests/test_read_model_projections.py`, `tests/test_privacy_audit.py`, `tests/test_gemini.py`, `tests/test_bedrock.py`, `tests/test_openai_compat.py`, `tests/test_anthropic_direct.py`, `tests/test_failover.py`, `tests/test_mirror.py`, `tests/test_route_wiring.py`, `frontend/src/workbench/CouncilDashboard.sovereign.test.tsx` |
| 39 | Multi-Model Deliberation and Dissent Organ | `DeliberationCouncilAuthority` | `aios/domain/intelligence/deliberation.py`, `aios/application/intelligence/deliberation.py`, `aios/council/deliberation_gather.py`, `aios/infrastructure/intelligence/deliberation_store.py`, `aios/council/gateway_reasoning.py`, `aios/council/council_orchestrator.py`, `aios/api/routes/council.py` | `tests/test_deliberation.py`, `tests/test_deliberation_gather.py`, `tests/test_deliberation_store.py`, `tests/test_council_gateway_reasoning.py`, `tests/test_council_orchestrator.py`, `tests/test_council_api.py` |
| 40 | Isolated Workspace and Executor (live proof) | `IsolatedExecutorLiveAuthority` | `aios/application/executor/service.py`, `aios/application/governance/runtime_proof.py`, `aios/application/read_models/executor_projections.py`, `aios/api/routes/mirror.py`, `frontend/src/workbench/SovereignStatePanel.jsx`, `.github/workflows/ci.yml` | `tests/test_executor_service.py`, `tests/test_executor_client.py`, `tests/test_mirror.py`, `frontend/src/workbench/CouncilDashboard.sovereign.test.tsx`, `tests/test_executor_integration.py` |
| 54 | Backup and Disaster-Recovery Organ | `BackupDisasterRecoveryAuthority` | `aios/operations/recovery.py`, `aios/operations/doctor.py`, `aios/__main__.py` | `tests/test_restore_invalidation.py`, `tests/test_operations.py` |
| 24 | Human Sovereign Identity | `IdentityAuthority` | `aios/domain/identity/models.py`, `aios/application/identity/service.py`, `aios/infrastructure/identity/sqlite_store.py`, `aios/domain/capabilities/contracts.py`, `aios/application/capabilities/authority.py`, `aios/infrastructure/capabilities/sqlite_store.py`, `aios/api/action_guard.py`, `aios/api/main.py`, `aios/api/routes/actions.py`, `aios/api/routes/council.py` | `tests/test_constitution_snapshot.py`, `tests/test_exact_capabilities.py`, `tests/test_human_sovereign_identity.py`, `tests/test_action_guard.py` |
| 41 | Promotion, Checkpoint and Rollback (live proof) | `PromotionRollbackLiveAuthority` | `aios/application/promotion/authority.py`, `aios/domain/promotion/contracts.py`, `aios/domain/evidence/contracts.py` | `tests/test_promotion_authority.py`, `tests/test_maintenance_api.py` |

**Organ 28 note:** the Tier-1 closure pass had already built `ProjectPassportStore` (durable, cross-restart history), but grounding it further found `build_project_passport_v1()` and `ProjectPassportStore` had **zero production callers anywhere** -- `aios/api/routes/projects.py`'s real scan route called the untyped legacy `harvest_project_passport()` directly and discarded the typed representation this organ exists to provide. `POST /api/v1/projects/passport/scan` now also builds a real `ProjectPassportV1` from the same scan and records it durably via a new `get_project_passport_store()` singleton (`aios/api/deps.py`); `GET /api/v1/projects/passport/status` surfaces a `durable` field (revision count, digest, verified commit) so the wiring is genuinely observable, not silent. Separately, `invariants`/`explicit_human_decisions` were previously hardcoded to `()` **inside** `build_project_passport_v1()` with no parameter at all -- structurally impossible for any caller to supply even with real values. Both are now real optional parameters; they still default empty (neither is safely derivable by static analysis without risking a fabricated-looking heuristic), but the artificial ceiling blocking a future real source (an operator-supplied form, a structured project doc) is gone.

**Organ 37 note:** green because the *qualification mechanism itself* is now proven correct in both directions with live evidence, not because any specific model is production-approved. `release/slice32/granite-qualification-live-organ37-retry.json` shows granite3.2:2b reproducibly failing "summarisation" (2 of 3 runs, even with the schema-normalising retry); `release/slice32/qwen25coder7b-qualification-live.json` shows `qwen2.5-coder:7b` reproducibly passing all 16 checks (3 of 3 runs) against the exact same, unmodified suite — proof the suite correctly discriminates. The live local registry's `qwen2.5-coder:7b` row now carries `admission_status="approved"` with evidence-backed profiles (`extract`/`classify`/`summarise`/`cluster`), derived mechanically from that evidence. `operator_approved` was deliberately left unset: that field is a human trust decision this organ does not grant on its own.

**Organ 34 note:** `is_call_allowed()` gating is now real -- a candidate whose circuit is open is skipped exactly like an H9-skip (never attempted, `self._idx` untouched) in all three `FailoverChatClient` methods, closing the "purely observational" gap; a half-open circuit's single recovery probe is still allowed through (verified with a clock-driven test), and skipping an open circuit is an orthogonal, additional condition that never relaxes H9's own at-most-one-cloud-provider privacy rule. The two remaining named items are principled scope boundaries, not gaps: in-memory-only state deliberately matches `BudgetGuard`'s own established convention (the module's own docstring already said so before this pass -- not a new durability promise this organ owes); merging with `BudgetGuard` is a genuine separate architectural task: a merge of two live systems, not a wiring fix. Explicit (non-`auto`) model picks bypassing `FailoverChatClient` remains true and unaddressed -- the highest-traffic default (`auto`) path is now fully wired with both recording and gating; extending observability to explicit picks would touch every caller of `_select_chat_client()`, a different, larger surface not attempted here.

**Organ 26 note:** the remaining item named in the prior blocker (`MissionService`'s internal `start_deliberation`/`request_approval`/`start_verification`/`complete`/`fail` transitions staying individually unchecked) was re-examined and confirmed to be a deliberate, reasoned design choice, not an unclosed gap: none of the five perform a new destructive action (they mark state and clean up work already gated at `create()`/`start_execution()`/the two rollback routes), and gating cleanup/completion during an emergency stop would be counterproductive — you want stuck resources released, not held. Every route this organism's "full boundary hard-wiring" claim actually covers is genuinely gated.

**Organs 47/48 note:** all 4 Slice-39 projections are now live-routed and frontend-consumed, closing both organs' own specific scope (the read-model projection mechanism, and the read-only truthful mirror of it — not organs 49-51's own distinct, still-unbuilt surfaces). `ProviderHealthProjection`: `ProviderHealthTracker.has_observations()` (new) lets `project_provider_health_list()` omit any provider with zero recorded outcomes entirely, rather than showing a fabricated "healthy" placeholder for a never-called provider — real data now flows in via organ 34's `FailoverChatClient` wiring. `ApprovalProjection`: grounding found `aios.core.approvals.ApprovalStore` is a **legacy compatibility surface** (`aios/api/deps.py`'s own comment: "not constructed in the production dependency graph") — the real production issue/consume authority is `CapabilityAuthority`. Built `CapabilityStore.pending()`/`CapabilityAuthority.list_pending()` (real SQLite enumeration, never exposes a usable bearer token) and a new `project_capability_approval()` that measures real `mission_id`/`scope`/`verification_requirement` fields directly from the binding — richer than the original `ApprovedAction`-based design. `SovereignStatePanel.jsx` gained "Provider Health" and "Pending Approvals" sections, live-verified in the browser showing the honest empty states (no providers observed, nothing pending) against the real running backend.

**Organs 49/51 note:** both organs' own exact stated blockers named organ 47's own projections as the missing prerequisite, and that prerequisite is now built. Organ 49 (Approval and Decision Surface): the new "Pending Approvals" section rendered from `ApprovalProjection` *is* this organ's surface — a human operator can now see every capability awaiting consumption (`mission_id`, `scope`, `verification_requirement`) sourced from the real `CapabilityAuthority`, not a mock. Organ 51 (Sovereign Control and Heartbeat Surface): the Constitution, Emergency Stop, Provider Health, and Approval sections now render together in one panel with a genuine, live-verified manual refresh control (`RefreshCw` button, confirmed via network-request inspection to re-fire real `GET /api/v1/mirror/governance` calls) — a real "is the system alive and answering right now" heartbeat, not a passive one-shot load. Both organs are scoped narrowly to what their own ledger blocker actually named.

**Organ 50 note:** closed the organ's full two-part claim ("why was this model chosen / what was sent / what was removed") in two separately-verified halves. Half 1 ("why"): `generate_pipeline.py`'s `route_meta()` already built real per-turn routing metadata but only fed it to `DevelopmentTracker` for internal calibration -- new `DevelopmentTracker.recent_routing_decisions()` is a **pure read** of that already-durable `development_events.metadata_json` data (zero hot-path changes), projected through a new `RoutingDecisionProjection`. Half 2 ("what was sent/removed"): `PrivacyFilter.filter()` already computes a real per-call redaction audit but it was only ever passed to `logger.info()` at all 5 real call sites (`FailoverChatClient`'s 3 internal call sites plus each of the 4 direct cloud clients' own filtering) -- new `PrivacyAuditTracker` (`aios/application/models/privacy_audit.py`, in-memory-only, matching `ProviderHealthTracker`'s own already-documented convention) is threaded as an optional, fail-soft constructor parameter into all 5 sites and DI-wired in `aios/api/deps.py`/`aios/core/router_wiring.py`, exactly mirroring organ 34's own established pattern. Both halves are projected into `GET /api/v1/mirror/governance`'s new `routingDecisions`/`privacyAudits` fields and rendered in `SovereignStatePanel.jsx`'s "Provenance & Explanation" section, live-verified against the real running backend (10 genuine historical routing decisions rendered from this machine's real database; the privacy-audit sub-section correctly showed its honest empty state for a freshly-restarted process that had made no cloud calls yet). 19 new backend tests (`PrivacyAuditTracker` unit tests, all 5 call sites' wiring, both projectors, the mirror route) + 1 new frontend assertion, all green; zero regressions across the full touched surface (privacy filter, failover, all 4 cloud clients).

**Organ 39 note:** closed the organ's real remaining gap -- Slice 34's `should_trigger_deliberation()`/`verify_independence()`/`synthesize_deliberation()` were correct, tested, pure functions with zero production callers (confirmed by grep). New `aios/council/deliberation_gather.py::maybe_deliberate()` is that caller: trigger flags are derived ONLY from data a mission already computed (the King's own clamped recommendation reaching block-tier, or a real split between blocking and non-blocking Queen verdicts -- **not** raw verdict-string inequality, which a first pass wrongly flagged since different Queens legitimately use different non-blocking vocabulary, e.g. `reflection.py`'s `"allow_with_approval"` alongside plain `"allow"` elsewhere; caught by an integration test against a real ordinary mission and fixed before this was ever committed). A genuinely independent second reviewer (`aios/council/gateway_reasoning.py::build_dissent_llm_client()`) always selects a real configured **cloud** provider, never Ollama (which is always the King's own provider -- using it would violate `verify_independence()`'s whole point), routed through the same gateway-boundary pattern `build_council_llm_client()` already established. New `DeliberationStore` (`aios/infrastructure/intelligence/deliberation_store.py`, migration 0009, append-only per revision) persists every real synthesized record, tamper-checked against a new shared `deliberation_record_digest()` helper (extracted from `synthesize_deliberation()` itself, so the two can never silently drift into different digest shapes -- an early draft's tamper check compared a value to itself and caught nothing until a dedicated test proved it). Wired into `CouncilOrchestrator.execute()` as a best-effort side call *after* the King's report already exists, wrapped in try/except so a flaky dissent provider or malformed reply can never affect the mission's own recommendation or completion -- strictly more conservative than `reason_king()`'s own advisory posture. 37 new tests across the gather logic, the store, the dissent-client factory, and two orchestrator-level integration tests (one proving an ordinary successful mission correctly persists nothing; one proving a genuinely block-tier report reaches a real `DeliberationStore` through the orchestrator's own wiring, not a bypass) -- all green, zero regressions across the full Council/mission/e2e test surface.

**Organ 40 note:** closed the one real remaining gap named in this organ's own blocker -- failure and timeout were already tested (`test_missing_private_executor_is_refused`, `test_private_executor_timeout_is_refused`) but restart resilience specifically was not, and could only be proven where a real Docker daemon exists (CI, never this local sandbox). Two new `.github/workflows/ci.yml` steps restart the real docker-compose executor container in place (`docker compose restart` + `up -d --wait`, re-applying the same healthcheck gate the initial start uses) then re-run the existing, already-reviewed `test_executor_integration.py` against it -- no new Python test logic, reusing the proven isolation proof itself as the restart-resilience proof. **A first attempt at this genuinely failed and was root-caused, not glossed over**: the restart step omitted re-exporting `AIOS_DOCKER_SOCKET_GID`, so the follow-up `docker compose up --wait` saw `docker-compose.yml`'s silent `${AIOS_DOCKER_SOCKET_GID:-999}` fallback resolve differently than the running container's actual config, treated that as drift, and RECREATED the container with the wrong docker-socket group -- breaking its ability to spawn per-job containers entirely (surfaced as the isolation test asserting job status `"failed"` and the timeout test never raising, since jobs failed fast on a permission error rather than genuinely misbehaving). Fixed by exporting the same real GID the original start step already computes. CI run [29989936411](https://github.com/swap821/ai-editor/actions/runs/29989936411) (commit `697d925`) confirms all 3 tests in `test_executor_integration.py` pass against the restarted container.

**Organ 24 note:** closed both halves of the organ's own blocker.
Constitution-digest mismatch enforcement (operator-confirmed design: reject
outright, not downgrade): `Principal.constitution_digest` was already
genuinely stamped fresh on every authentication event, but grounding found
it was never actually threaded into any of the 6 real production
`CapabilityBinding(...)` construction sites (`aios/api/action_guard.py`'s
`_binding_for()`, `aios/api/main.py`'s `_generate_capability_binding()`,
`aios/api/routes/actions.py`'s command/rollback/proposal-apply bindings, and
`aios/api/routes/council.py`'s mission-rollback binding) -- the field existed
but nothing populated it, despite the prior blocker's text implying it was
done. Fixed at all 6 sites. `CapabilityAuthority.consume()` now recomputes
`build_constitution_snapshot(...).snapshot_digest` and raises `CapabilityError`
on a mismatch against the digest stamped at issue time, mirroring the
existing `emergency_stop.assert_operational()` call at the same choke point.
Grounding this surfaced a real, separate bug that would have made the whole
mechanism a silent no-op in production: `CapabilityStore`'s SQLite schema had
no `constitution_digest` column at all, so any stamped value was dropped the
moment a capability was persisted, and `consume()` would always see
`constitution_digest=None` regardless of what was issued. Fixed with an
`ALTER TABLE` column addition (matching the store's own established
`action_payload_json` migration convention) plus a dedicated test that issues
and consumes through two separate `CapabilityAuthority` instances sharing one
database file, proving the value survives a real process-boundary round trip.
A second, subtler bug was caught before it shipped: the naive fix folded
`constitution_digest` into `consume()`'s existing full-binding equality check,
but every real caller reconstructs its "expected" binding fresh from the
*current* request's live `Principal` -- meaning a legitimate constitutional
amendment during the ~120s TTL window would trigger the generic "binding
mismatch" error instead of ever reaching the new, more specific
stale-constitution check (which would have been unreachable dead code in
production). Fixed by excluding `constitution_digest` from that equality
comparison and checking it as an independent condition. Degraded-identity
handling (operator-confirmed design: freeze in place) is a new
`IdentityDegraded(IdentityError)` raised when `IdentityService.
get_authenticated_principal()`'s underlying store calls raise a real
`sqlite3.Error` -- grounding confirmed zero existing "degraded" or
health-check concept anywhere in the identity modules, so this distinguishes
a genuine store failure from the routine "no valid session" `None` return.
Handled by a new centralized `@app.exception_handler(IdentityDegraded)` in
`aios/api/main.py`, mirroring organ 26's `EmergencyStopError` precedent
exactly: one handler covers every real call site (`action_guard.py`'s direct
call, `deps.py`'s shared `get_authenticated_principal` dependency, `auth.py`,
`mirror.py`) with a consistent, fail-closed 503 instead of an unhandled 500.
"Freeze in place" for already-issued, in-flight actions needed no new code:
nothing on a mission's execution path re-checks identity mid-flight, so
degrading the identity store only blocks the resolution of a NEW `Principal`
(and therefore new capability issuance), never an already-running mission.

## Yellow organs (48)

The original 16 (Slices 26-40 completion target, minus organ 52 flipped
green in Phase 1, 2026-07-28 — see above) plus 33 regressed under
Decision A (2026-07-27) — see the two green-organ sections above.

| # | Organ | Authority owner | Slice | Truthful blocker |
|---|-------|------------------|-------|-------------------|
| 1 | Security Gateway | `SecurityGatewayAuthority` | Decision A | Regressed 2026-07-27: `SecurityGatewayAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 2 | Scope Lock | `ScopeLockAuthority` | Decision A | Regressed 2026-07-27: `ScopeLockAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 3 | Secret Scanner | `SecretScannerAuthority` | Decision A | Regressed 2026-07-27: `SecretScannerAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 4 | Tamper-Evident Audit Logger | `AuditLoggerAuthority` | Decision A | Regressed 2026-07-27: `AuditLoggerAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 5 | Prompt Injection Shield | `InjectionShieldAuthority` | Decision A | Regressed 2026-07-27: `InjectionShieldAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 6 | Edge Trust Boundary | `EdgeTrustAuthority` | Decision A | Regressed 2026-07-27: `EdgeTrustAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 7 | Policy Kernel | `PolicyKernelAuthority` | Decision A | Regressed 2026-07-27: `PolicyKernelAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 8 | Action Broker | `ActionBrokerAuthority` | Decision A | Regressed 2026-07-27: `ActionBrokerAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 10 | Mission Authority | `MissionAuthority` | Decision A | Regressed 2026-07-27: `MissionAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 11 | Turn Coordinator | `TurnCoordinatorAuthority` | Decision A | Regressed 2026-07-27: `TurnCoordinatorAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 12 | Worker Foundry | `WorkerFoundryAuthority` | Decision A | Regressed 2026-07-27: `WorkerFoundryAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 13 | Isolated Executor Service (construction) | `ExecutorServiceAuthority` | Decision A | Regressed 2026-07-27: `ExecutorServiceAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 14 | Staged Workspace Manager (construction) | `StagedWorkspaceAuthority` | Decision A | Regressed 2026-07-27: `StagedWorkspaceAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 17 | Cortex Observation Bus | `CortexBusAuthority` | Decision A | Regressed 2026-07-27: `CortexBusAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 20 | Living Mirror Reaction Registry (construction) | `LivingMirrorAuthority` | Decision A | Regressed 2026-07-27: `LivingMirrorAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 21 | Queen Council Orchestrator | `QueenCouncilAuthority` | Decision A | Regressed 2026-07-27: `QueenCouncilAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 22 | V1 Release Declaration (gagos v1-check) | `ReleaseDeclarationAuthority` | Decision A | Regressed 2026-07-27: `ReleaseDeclarationAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 24 | Human Sovereign Identity | `IdentityAuthority` | Decision A | Regressed 2026-07-27: `IdentityAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 26 | Emergency Stop Organ (full boundary hard-wiring) | `EmergencyStopHardWiringAuthority` | Decision A | Regressed 2026-07-27: `EmergencyStopHardWiringAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 34 | Cloud Budget and Provider-Health Organ | `ProviderHealthBudgetAuthority` | Decision A | Regressed 2026-07-27: `ProviderHealthBudgetAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 35 | Local Clerk Runtime | `LocalClerkRuntimeAuthority` | Decision A | Regressed 2026-07-27: `LocalClerkRuntimeAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 37 | Local Model Qualification and Health | `LocalModelQualificationAuthority` | Decision A | Regressed 2026-07-27: `LocalModelQualificationAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 39 | Multi-Model Deliberation and Dissent Organ | `DeliberationCouncilAuthority` | Decision A | Regressed 2026-07-27: `DeliberationCouncilAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 40 | Isolated Workspace and Executor (live proof) | `IsolatedExecutorLiveAuthority` | Decision A | Regressed 2026-07-27: `IsolatedExecutorLiveAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 41 | Promotion, Checkpoint and Rollback (live proof) | `PromotionRollbackLiveAuthority` | Decision A | Regressed 2026-07-27: `PromotionRollbackLiveAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 43 | Local Skill Reuse, Confidence and Demotion | `SkillLifecycleAuthority` | Decision A | Regressed 2026-07-27: `SkillLifecycleAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 45 | Constitutional Amendment Authority | `ConstitutionalAmendmentAuthority` | Decision A | Regressed 2026-07-27: `ConstitutionalAmendmentAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 47 | Read-Model and Projection Organ | `ReadModelProjectionAuthority` | Decision A | Regressed 2026-07-27: `ReadModelProjectionAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 48 | Truthful Living Mirror (full truthful UI) | `TruthfulMirrorAuthority` | Decision A | Regressed 2026-07-27: `TruthfulMirrorAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 49 | Approval and Decision Surface | `ApprovalDecisionSurfaceAuthority` | Decision A | Regressed 2026-07-27: `ApprovalDecisionSurfaceAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 50 | Provenance and Explanation Surface | `ProvenanceExplanationSurfaceAuthority` | Decision A | Regressed 2026-07-27: `ProvenanceExplanationSurfaceAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 51 | Sovereign Control and Heartbeat Surface | `SovereignHeartbeatSurfaceAuthority` | Decision A | Regressed 2026-07-27: `SovereignHeartbeatSurfaceAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 54 | Backup and Disaster-Recovery Organ | `BackupDisasterRecoveryAuthority` | Decision A | Regressed 2026-07-27: `BackupDisasterRecoveryAuthority` names no class defined in this organ's own `production_entrypoints` — a label only, not a class reference. Needs a real, reachable owner class (organ 42/46/52 / PR #169 template) before this organ can be green again. |
| 23 | Release Conformance Organ | `ReleaseConformanceAuthority` | 25 / 40 | Ledger established at this baseline; the strict gate stays non-green until every organ below turns green and Slice 40's final release proof lands. |
| 25 | Constitutional Kernel | `ConstitutionalKernelAuthority` | PR-1 | **PR-1: gap closed, status not yet flipped (CI verification pending).** Before this, three different answers to "what is the current constitution?" coexisted: the durable chain (written only by the amendment routes); a per-call `build_constitution_snapshot()` rebuild from live config that always returns version 1 (used by `IdentityService` for EVERY `Principal`, by `CapabilityAuthority.consume()`, by `mirror.py` and by `gateway_reasoning.py`); and a hardcoded `ratified_by_operator_id="operator"` fallback inside `PolicyKernel`, reached in all three real construction sites because none passed `constitution_authority=`. Measured consequence: an activated amendment moved the durable chain and reached NOTHING -- and because `consume()` compared a rebuilt digest against a binding stamped by the same rebuild, both sides always matched, making the stale-constitution rejection structurally unreachable for a real amendment (its four tests passed only by comparing fabricated literals no snapshot ever produced). `get_constitution_authority()` also raised `NameError` -- `aios/api/deps.py` never imported the class -- proving it had no callers. Now one `ConstitutionAuthority` is authoritative for the active snapshot, every `Principal` digest, `PolicyKernel` decisions, capability issuance and consumption, Council context and the mirror. The fabricated fallback is deleted (an unwired kernel raises). Enrollment is re-verified on EVERY call, not just the argument-free one -- load-bearing, because both production paths pass an explicit operator id; a supplied id is now an assertion to verify, never a chain selector, so no shadow chain can be minted. Fail-closed via `NoEnrolledSovereignError` / `OperatorIdentityChangedError` / `ConstitutionDegraded`, all mapped to one 503. Activation and rollback are compare-and-swap under `BEGIN IMMEDIATE`, with `expected_previous_digest` REQUIRED so an unprotected write is a `TypeError`, not a silent clobber. Proven by `tests/test_organ25_constitution_e2e.py` (real HTTP ceremony -> restart -> old-digest capability refused, new-digest accepted, rollback survives restart), which is mutation-checked: reverting `IdentityService` to the per-call rebuild fails all three cases. Remaining before green: green-contract conditions 11-12 only (record the exact tested commit, and have CI verify that same commit). |
| 27 | Operator Taste Model | `OperatorTasteModelAuthority` | PR1 | **Narrowed from green (see PR1 update note above):** `get_operator_preference_store()` (`aios/api/deps.py`) plus a real, explicit-only route (`aios/api/routes/preferences.py`) are the first production wiring `OperatorPreferenceStore` has ever had; expiry, withdrawal, restart recovery, and a scope-aware contradiction check (a real cross-scope false-contradiction bug, fixed) are all real and tested. Still missing: no production conversational call site threads `list_active_for_scope()` into Organ 31's `active_preferences` -- the only real caller of that parameter (Council) deliberately doesn't need it. **Phase 2 update (2026-07-28):** Decision A now holds -- new `OperatorTasteModelAuthority` (`aios/application/memory/authorities.py`) owns `OperatorPreferenceStore`, is the real class every preferences route now depends on via `get_operator_taste_model_authority()`, and owns the exact `active_preferences` filter (status == active AND not expired) organ 31 needs, previously assembled inline in the route. A real regression was caught and fixed before this shipped: the first draft's DI function called the store getter as a plain function instead of a FastAPI sub-dependency, silently breaking every existing test's `app.dependency_overrides` and falling through to the production singleton -- caught by the existing test suite, not a new test written for this change. |
| 28 | Project Understanding Organ | `ProjectUnderstandingAuthority` | PR1 | **Narrowed from green (see PR1 update note above):** the active-project pointer is now a durable singleton row (migration 0016), not a process-local global forgotten on every restart, and `diff_project_passports()` gives every rescan a real, computed diff. Still missing: no production conversational call site threads the active passport into Organ 31's `project_passport` parameter. **Phase 2 update (2026-07-28):** Decision A now holds -- new `ProjectUnderstandingAuthority` (`aios/application/memory/authorities.py`) owns `ProjectPassportStore`, is the real class both project-passport routes now depend on, and owns the three-store-read status assembly `project_passport_status()` used to do inline (which, while consolidating it, was found to have a genuine dead-code duplicate of that same assembly sitting unreachable after an earlier `return` -- removed). |
| 29 | Correction and Interpretation-Lineage Organ | `CorrectionLineageAuthority` | PR1 | **Narrowed from green (see PR1 update note above):** the real `/api/v1/conversation/correction` route now builds and durably persists a typed `CorrectionRecordV1` via a new `CorrectionRecordStore` -- previously zero production callers existed. Still missing: no production conversational call site threads the newest valid correction into Organ 31's `latest_correction` parameter. **Phase 2 update (2026-07-28):** Decision A now holds -- new `CorrectionLineageAuthority` (`aios/application/memory/authorities.py`) owns `CorrectionRecordStore` and, more substantively, owns the compensating-transaction pattern that was previously duplicated inline in both `/api/v1/conversation/correction` and `/api/v1/conversation/correction/clear`: append to the immutable ledger, and on failure roll back the separate `ConversationStateStore` transition so the two stores never disagree, then re-raise (the route maps the re-raised failure to its existing 503). The pre-existing rollback tests (`tests/test_authenticated_chat_route.py`) already exercise this exact path end-to-end through the real routes and pass unchanged against the new authority. |
| 30 | Communication and Human-State Interpreter | `HumanStateInterpreterAuthority` | 28 / PR1 | **PR1 (fixes the exact bug named for this pass, see update note above):** migration 0013's mutable `corrected_state`/`corrected_at` columns let corrections overwrite each other while the row's own digest kept authenticating only the pre-correction fields -- outside the tamper check entirely. Migration 0014 replaces this with a genuinely append-only, digest-verified `human_state_corrections` table joined by hypothesis row id (not content digest, which was tried and rejected after it collapsed two same-content hypotheses into one accuracy bucket), each row bound to the authenticated operator (or an honest `None`) via `get_optional_principal()`. A live regression test tampers the new table directly and confirms `RecordTamperedError`. Still missing: the classifier itself has not been measured against real production operator traffic -- the new table is exactly the mechanism that will let that happen as real traffic accumulates, but none exists yet in this sandbox; a genuine, not-fabricatable gap. |
| 31 | Human Representative Context Compiler | `RepresentativeContextCompilerAuthority` | 29 | **Reconciliation + this pass:** this row's own text (Tier 4: `gateway_reasoning.py` exposes a real `last_context_digest` instead of silently discarding it) was already true but had drifted out of sync with `.aios/state/ORGAN_GREEN_LEDGER.json`'s own row, which still read pre-Tier-4 text -- caught and corrected here. New: every `RepresentativeContextV1` that passes identity/constitution/emergency-stop validation is now durably recorded by a new, append-only `RepresentativeContextStore` (migration 0011), wired directly inside `route_intelligence_request()`/`stream_intelligence_request()` so every current and future gateway caller gets audit persistence for free, not just Council's. Still missing: the only real production caller today compiles a context with empty preferences/passport/correction (Council's own prompts are self-contained JSON, not general conversation) -- meaningfully exercising the compiler with real human-representation data needs a general-conversation call site, which is organ 32's own deliberately-deferred chat-wiring gap. |
| 32 | Universal Intelligence Gateway | `UniversalIntelligenceGatewayAuthority` | 41 | **Tier 4 update (operator-confirmed scope: streaming variant only) + this pass:** grounding found organ 32 is not just "add streaming" -- three separate, independent gateway-shaped systems exist (the Slice-30 `route_intelligence_request()`; the older `aios.runtime.intelligence_gateway.IntelligenceGateway`, confirmed load-bearing for real worker plan/repair reasoning; and `aios.application.models.hiring_service.IntelligenceHiringService`). New `stream_intelligence_request()` covers text-chunk model calls with the same upfront validation as the synchronous entrance. This pass wired organ 31's new `RepresentativeContextStore` into this module directly, so both entrances now durably record every context they compile. Still missing: chat (`/api/v1/chat`, the single most heavily used endpoint in the system) and the agentic forge (`/api/generate`) remain unwired -- chat has no authenticated operator/constitution digest today by design (anonymous local chat must keep working), and rewiring it without a live browser session to verify no UX regression was deliberately not attempted here, consistent with every prior pass's own risk read of this exact call site. The 2 other competing gateway implementations remain unreconciled. |
| 33 | Model Registry and Capability Passport | `ModelPassportAuthority` | 31 | `ModelPassportV1` now exists (typed, role-scoped admission) with `is_admitted_for_role()`/`can_drive_tools()`/`is_stale_for_version()`. Still missing: nothing runs a real qualification suite yet (every passport must be hand-constructed) and no durable store persists one across restarts. Reconciliation pass item 4: found this machine's actual running admission store (`LocalWorkforceRegistry`, `data/aios_memory.db` -- a separate, older, untyped store from `ModelPassportV1`) claiming an evidence-contradicted admission for `granite3.2:2b`; corrected (see organ 37). The two admission concepts remain unreconciled into one authority -- a real, separate gap this item did not close. **Phase 2 update (2026-07-28):** `ModelPassportAuthority` (`aios/application/models/passport_authority.py`) was already built in an earlier pass -- the registry row projected live into a typed passport, 12 unit tests -- but had zero production callers, exactly the "class exists, condition 2 false" anti-pattern this plan forbids. New `GET /api/v1/local-workforce/{model_id}/passport` (`aios/api/routes/local_workforce.py`) is its first real caller, satisfying Decision A. The two named gaps above (no qualification suite run, two unreconciled admission concepts) are unchanged and unrelated to this pass -- this organ stays yellow. |
| 36 | Clerical Job Contract and Dispatcher | `ClerkDispatcherAuthority` | 32 | `dispatch_clerical_job()` now exists (deterministic-first, unqualified-always-escalates, low-confidence-to-human). Still missing: not wired into `LocalWorkforceService`'s real request path. |
| 38 | Durable Local-Clerk Provenance and Continuity Organ | `ClerkProvenanceAuthority` | 41 | `LocalWorkforceProvenanceStore` (SQLite, per-record sha256 digests, duplicate job_id fails closed) is now genuinely wired into production: `run_advisory_job()` records every real job's request/model-call/result once execution completes (honestly, including refusals and schema failures, not only successes), and `get_local_workforce_service()` injects a real store at `config.LOCAL_WORKFORCE_PROVENANCE_DB_PATH`. `gagos provenance clerk-job <job-id>` reconstructs the trace from this now-real data. While grounding this, found (and flagged separately, not fixed here) a real pre-existing bug: 3 tests in `TestBlocker9LocalJobSchema` never actually exercised schema validation due to a bare `MagicMock()` registry always satisfying an `hasattr(registry, "dependency")` fallback check. Still missing: `dispatch_clerical_job()` (Slice 32) itself remains unwired -- needs a `QualificationResult` tracked per model, which the registry doesn't store anywhere today; not invented under time pressure rather than forcing a shallow integration. **Phase 2 update (2026-07-28):** Decision A now holds -- new `ClerkProvenanceAuthority` (`aios/application/local_workforce/provenance.py`, already a listed `production_entrypoints` file) owns both the write side (moved from `LocalWorkforceService`'s previously-private `_record_advisory_job_provenance`, now `record_advisory_job`) and the pre-existing read side (`get_clerk_job_provenance`, now also `job_provenance()`). `LocalWorkforceService.run_advisory_job()` calls the authority, not a bare store, and holds it as `self.provenance_authority`. The `dispatch_clerical_job()` gap above is unchanged and still the reason this organ stays yellow. |
| 42 | Recovery and Resumption | `RecoveryResumptionAuthority` | 41 | **Tier 4 update + this pass:** `MissionTransitionJournal` wiring is real for the Council pipeline (`CouncilOrchestrator` appends all 11 real states at their genuine points), proven end to end with a real mission run asserting the exact ordered history. This pass closes the exact prerequisite the prior update named: `MissionService.request_approval_direct()` (using the pre-existing but previously-unused `DIRECT_REQUEST_APPROVAL` transition) plus a real `POST /api/v1/maintenance/repairs/{mission_id}/approve` route let a maintenance mission reach `APPROVED` through a real, privileged-operator-gated HTTP call -- `test_maintenance_api.py`'s own end-to-end test now uses this route instead of an in-process `MissionService.approve()` bypass. Also fixed a real, previously-latent bug found while wiring this: three maintenance routes checked `if record is None` against a repository method that raises `MissionNotFoundError` instead, so an unknown mission_id was an uncaught 500, not the intended 404. Still missing: `MissionTransitionJournal` itself is not yet wired into `MaintenanceConvergenceService.run_approved_repair()` the way it is into `CouncilOrchestrator` -- now genuinely unblocked, but not attempted in the same pass as its own prerequisite. **Phase 2 update (2026-07-28):** Decision A already holds for this organ -- `RecoveryResumptionAuthority` was a real class with a real startup-hook caller (`aios/api/main.py`'s `recovery_report()` call) since PR #169, just missing from `production_entrypoints` (a pure ledger bookkeeping gap, now fixed). The Maintenance-pipeline gap above is unchanged and still the reason this organ stays yellow. |
| 44 | Golden Mission and Endurance Evaluation | `GoldenMissionEnduranceAuthority` | 36 | Checked realistically: the golden cohort (12 live governed missions, 2 real cloud providers, hours of wall-clock execution) is not achievable or appropriate to run autonomously in this pass -- recorded as not attempted, not faked. The individual mechanisms it would exercise are real and unit-tested (organ 43). |
| 46 | Constitutional Learning Organ | `ConstitutionalLearningAuthority` | 38 | **Tier 4 follow-on:** the 9 named adversarial simulations are no longer a caller-trusted catalog. `adversarial_simulations.run_adversarial_simulations()` runs every one for real against a proposal's own text plus a live probe of the production mechanism each check protects (`CapabilityAuthority` against an ephemeral store for `approval_bypass`/`capability_replay`, `EmergencyStopController` against an ephemeral latch for `emergency_stop_interference`/`model_self_protection`, `PrivacyBroker` for `privacy_widening`, `rollback_amendment` for `reduced_human_reversibility`, `CorrectionRecordV1`'s pinned `grants_authority=Literal[False]` for `memory_as_truth_confusion`, the failover layer's provider classes for `provider_lock_in`, `assert_never_reduces_human_authority` for `authority_escalation`) -- every probe is read-only or runs against a throwaway fixture, never the live system's persisted state, since a text proposal must never be applied to a live system to "test" it. `POST .../lessons/check-simulations` now takes a `proposal_id`, looks it up, and runs the real checks itself; a caller can no longer assert a passing result it never earned. Still yellow, honestly: this is a real automated floor, not a full human red-team exercise. |
| 53 | Installation, Configuration and Key Authority | `InstallationConfigurationAuthority` | 40 | **Tier 5 update (operator-authorized, grace-period-overlap design confirmed):** key rotation and a bounded grace period are now real. New `ApiTokenAuthority` issues a fresh API bearer token via `POST /api/v1/security/api-token/rotate`; the token it supersedes keeps working for a caller-chosen grace period (default 3600s) so an already-running client isn't broken instantly, then stops validating once the window elapses -- proven with a fake-clock unit test. `config.API_TOKEN` stays unconditionally valid exactly as before (the operator retires it the normal way, via restart with a different env var); this authority only layers rotated tokens on top, so every pre-existing token-related test and behavior is unchanged. A real regression was caught and fixed before shipping: an early draft cached `config.API_TOKEN`'s value inside the long-lived authority singleton at first construction, so a test elsewhere that temporarily reassigns it would permanently poison every later test in the same process -- caught by real adversarial-suite failures, not a test written for this change; fixed by making the authority stateless with respect to that value. Still missing: "truthful Ollama-absence handling," the other named half of this organ's original blocker, has no further specification anywhere in the repo and is an unrelated concern (local-model availability reporting, not credential rotation) -- not investigated here. |

## How this ledger is enforced

```
python -m aios.launcher organ-check --json
python -m aios.launcher organ-check --strict
```

`--strict` exits non-zero until all 54 organs are green. `validate_ledger`
additionally refuses: duplicate `organ_id`, duplicate `authority_owner`,
missing or unknown organs, a `green` organ without focused or integration
tests, a `green` organ whose `authority_owner` is not defined as a class
anywhere in its own `production_entrypoints` (Decision A, 2026-07-27), a
`green` organ that requires live evidence but has none, live evidence
labelled `fixture` where `live` is required, and live evidence stamped with
any commit other than the one under evaluation.
