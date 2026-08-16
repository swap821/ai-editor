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
  string that only matches `CANONICAL_ORGANS` is a label, not a claim. The
  Phase 2 CI/launcher boundary checks this for every non-frozen row, including
  yellow rows; organs 1–5 are an explicit yellow-only exception because their
  production entrypoints are the frozen RED security spine.
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
never written. `validate_ledger()` now provides an explicit Phase 2 owner-attestation gate
(`enforce_owner_attestation=True`, implemented beside
`_authority_owner_is_class_reference` in `aios/application/governance/organ_ledger.py`)
that requires every non-frozen row, yellow or green, to define its
`authority_owner` as a class inside that organ's own
`production_entrypoints` -- reusing the field the ledger already tracks
rather than adding new schema. The launcher and CI verifier enable that gate;
the five frozen security-spine organs are forbidden from green claims but are
not required to edit their frozen entrypoint modules merely to satisfy it. **All 33 unsupported organs are demoted to
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

## Green organs flipped in Phase 2 of the proof plan (2026-07-28)

| # | Organ | Authority owner | Entry point | Tests |
|---|-------|------------------|-------------|-------|
| 36 | Clerical Job Contract and Dispatcher | `ClerkDispatcherAuthority` | `aios/application/local_workforce/dispatcher.py` (new class), `aios/application/local_workforce/service.py` (now calls through it) | `tests/test_local_clerk_dispatcher.py`, `tests/test_local_workforce_api.py`, `tests/test_organ_authority_owners.py` |
| 25 | Constitutional Kernel | `ConstitutionalKernelAuthority` | `aios/application/governance/constitution_authority.py` (the durable snapshot/enrollment/activation authority now has the exact Decision-A owner name; compatibility callers resolve to the same class) | `tests/test_constitution_authority.py`, `tests/test_organ25_constitution_e2e.py`, `tests/test_organ_authority_owners.py` |
| 30 | Human-State Interpreter | `HumanStateInterpreterAuthority` | `aios/application/memory/human_representation.py` (owns the fixed-priority classifier), `aios/api/deps.py`, `aios/api/main.py`, `aios/application/turns/conversation_pipeline.py` | `tests/test_human_state_interpreter.py`, `tests/test_conversation_pipeline.py`, `tests/test_organ_authority_owners.py` |
| 31 | Human Representative Context Compiler | `RepresentativeContextCompilerAuthority` | 29 | **Re-audit (2026-07-28):** the durable `RepresentativeContextStore` remains wired inside all three current gateway entrances, and authenticated `/api/v1/chat` plus `/api/generate` are real production callers. It resolves operator preferences, active project passport, verified correction lineage, human-state evidence, identity, and constitution before `stream_intelligence_request()`; the context receipt is persisted before provider chunks. The authenticated route and gateway suites pass (98 tests, 1 warning). The prior claim that only Council called the compiler with empty representation data is stale and withdrawn. Still yellow honestly: anonymous chat intentionally remains on its compatibility facts/recall path because it has no authenticated identity/constitution binding; live/exact-tip/remaining green-contract evidence is not claimed. |
| 32 | Universal Intelligence Gateway | UniversalIntelligenceGatewayAuthority | 41 | **Phase 2/3 update (2026-07-29):** the authority now owns synchronous, plain-text streaming, structured forge-event, and anonymous compatibility entrances. Authenticated `/api/v1/chat` and `/api/generate` compile identity/constitution-bound representative context, enforce the emergency stop, persist a strict receipt before provider iteration, and return gateway-redacted output; the structured scrubber preserves exact command/edit/create payloads needed by the approval broker. Anonymous compatibility conversation now enters `stream_compatibility_intelligence_request()` through `conversation_pipeline`; because it has no authenticated operator identity/constitution digest, that entrance is intentionally local-only, applies emergency-stop and output-redaction gates, and makes no representative-receipt claim. The real Council background paths use gateway-routed Planner/King and independent dissent clients with durable identity/constitution binding; the legacy worker `IntelligenceGateway` and authenticated hiring route now carry the same binding and enter this gateway, while missing binding fails closed before provider execution. Focused gateway, Council, runtime, hiring, conversation, and generate regressions pass. The authenticated forge planner, alignment interpreter, failure-triggered reflection completions, and standalone `/api/v1/reflect` route now enter this authority through GovernedAdvisoryCompletionClient and record a context before provider calls; route proofs cover the real failure-to-reflection path and preserve JSON mode. The local-clerk skill-applicability path now enters CompatibilityAdvisoryCompletionClient through the explicit local-only compatibility entrance; focused gateway and service tests prove JSON mode, input/output redaction, and emergency-stop refusal. The real `/api/generate` CRAG judge and optional cloud source now enter GovernedAdvisoryCompletionClient with authenticated context; route proofs record the local and cloud desired outcomes. Direct CRAG helpers retain their narrow legacy unit seams but have no production caller. Local-workforce health and qualification probes now enter the explicit local-only CompatibilityAdvisoryCompletionClient boundary, with read-only metrics delegated for the qualification resource gate; the maintenance convergence service has no direct model call and is not a bypass. No live cloud proof or exact-tip strict-release attestation is claimed. |
| 33 | Model Registry and Capability Passport | `ModelPassportAuthority` | 31 | `ModelPassportV1` is typed and role-scoped, and the authority projects it from the durable `LocalWorkforceRegistry` rather than maintaining a second admission truth. **Phase 2/3 re-audit (2026-07-28):** the real refresh -> approve -> qualify API path persists admission, roles, qualification-suite/evidence, artifact, and expiry fields in SQLite; a fresh registry instance is then read by the real passport route and returns the same passport digest. `tests/test_local_workforce_api.py::test_passport_route_projects_durable_registry_after_restart` proves this end to end; the Organ 33/owner focused suite passed 63 tests with 1 warning. The prior blocker claim that no durable store persists a passport is withdrawn for the local path. Still yellow honestly: no authorized live Ollama qualification evidence is available here, cloud/provider passport fields remain a separate intentional projection boundary, and exact-tip strict-release/remaining green-contract conditions are not claimed. |
| 38 | Durable Local-Clerk Provenance and Continuity Organ | `ClerkProvenanceAuthority` | 41 | `LocalWorkforceProvenanceStore` (SQLite, per-record sha256 digests, duplicate job_id fails closed) is genuinely wired into production: `LocalWorkforceService.run_advisory_job()` records every real job's request/model-call/result once execution completes, including refusals and schema failures, and `get_local_workforce_service()` injects the real store. The owner now controls both write and read-side reconstruction, and the persisted qualification lookup remains a separate fail-closed dispatcher boundary owned by organ 36. **Dedicated re-audit (2026-07-28):** the prior claim that `dispatch_clerical_job()` was still unwired was stale and is withdrawn; the service reads `LocalWorkforceRegistry.get_qualification()` and routes through `ClerkDispatcherAuthority`. Focused provenance, service, dispatcher, launcher, and owner-reachability suites pass, including tests/test_local_workforce_service_provenance.py::test_full_job_trace_reconstructs_after_process_restart, with one existing warning. Fresh-process reconstruction proves the persisted request, model call, result, and hash-linked provenance chain are readable and verifiable after the writer process exits. Still yellow honestly: no live model evidence or exact-tip strict-release attestation has been attached, and no additional implementation blocker was found in this re-audit. |
| 42 | Recovery and Resumption | `RecoveryResumptionAuthority` | 41 | **Tier 4 update + this pass:** `MissionTransitionJournal` wiring is real for the Council pipeline (`CouncilOrchestrator` appends all 11 real states at their genuine points), proven end to end with a real mission run asserting the exact ordered history. This pass closes the exact prerequisite the prior update named: `MissionService.request_approval_direct()` (using the pre-existing but previously-unused `DIRECT_REQUEST_APPROVAL` transition) plus a real `POST /api/v1/maintenance/repairs/{mission_id}/approve` route let a maintenance mission reach `APPROVED` through a real, privileged-operator-gated HTTP call -- `test_maintenance_api.py`'s own end-to-end test now uses this route instead of an in-process `MissionService.approve()` bypass. Also fixed a real, previously-latent bug found while wiring this: three maintenance routes checked `if record is None` against a repository method that raises `MissionNotFoundError` instead, so an unknown mission_id was an uncaught 500. **Phase 2 correction (2026-07-28):** the remaining maintenance-pipeline claim was stale: `MaintenanceConvergenceService` is now wired through the same `RecoveryResumptionAuthority.journal` dependency used by startup recovery, and its real creation, approval, execution, verification, checkpoint, promotion, post-promotion verification, completion, and failure paths append transitions at their actual execution points. `test_maintenance_api.py::test_a_maintenance_repair_leaves_an_ordered_transition_journal` proves the exact 11-state success history and contiguous sequence numbers end to end; focused Organ 42/owner tests pass, including the fresh-process restart proof, with one existing warning. Fresh-process SQLite restart proof now runs through tests/test_maintenance_api.py::test_recovery_authority_reads_interrupted_mission_after_process_restart and reports the nonterminal mission with integrity verified. Still yellow honestly: no actual crash/interruption of a running repair or exact-tip CI evidence has been attached; FAILED/ROLLED_BACK escape paths remain covered by focused assertions rather than a live interruption recovery run. |
| 44 | Golden Mission and Endurance Evaluation | `GoldenMissionEnduranceAuthority` | 36 | **Phase 2 update (2026-07-28):** `GoldenMissionEnduranceAuthority` now owns ordered golden-step verification and endurance threshold evaluation in the two runnable tools listed in the ledger. `tests/test_organ_authority_owners.py` drives the real runner compatibility entrypoint and spies on the named owner. The 12-mission, two-provider, multi-hour live cohort remains honestly unattempted because this environment has no authorized cloud credentials/budget and cannot fabricate that evidence. |
| 46 | Constitutional Learning Organ | `ConstitutionalLearningAuthority` | 38 | **Tier 4 follow-on:** the 9 named adversarial simulations are no longer a caller-trusted catalog. `adversarial_simulations.run_adversarial_simulations()` runs every one for real against a proposal's own text plus a live probe of the production mechanism each check protects (`CapabilityAuthority` against an ephemeral store for `approval_bypass`/`capability_replay`, `EmergencyStopController` against an ephemeral latch for `emergency_stop_interference`/`model_self_protection`, `PrivacyBroker` for `privacy_widening`, `rollback_amendment` for `reduced_human_reversibility`, `CorrectionRecordV1`'s pinned `grants_authority=Literal[False]` for `memory_as_truth_confusion`, the failover layer's provider classes for `provider_lock_in`, `assert_never_reduces_human_authority` for `authority_escalation`) -- every probe is read-only or runs against a throwaway fixture, never the live system's persisted state, since a text proposal must never be applied to a live system to "test" it. `POST .../lessons/check-simulations` now takes a `proposal_id`, looks it up, and runs the real checks itself; a caller can no longer assert a passing result it never earned. Still yellow, honestly: this is a real automated floor, not a full human red-team exercise. |
| 53 | Installation, Configuration and Key Authority | `InstallationConfigurationAuthority` | 40 | **Tier 5 update (operator-authorized, grace-period-overlap design confirmed):** key rotation and a bounded grace period are now real. New `ApiTokenAuthority` issues a fresh API bearer token via `POST /api/v1/security/api-token/rotate`; the token it supersedes keeps working for a caller-chosen grace period (default 3600s) so an already-running client isn't broken instantly, then stops validating once the window elapses -- proven with a fake-clock unit test. `config.API_TOKEN` stays unconditionally valid exactly as before (the operator retires it the normal way, via restart with a different env var); this authority only layers rotated tokens on top, so every pre-existing token-related test and behavior is unchanged. A real regression was caught and fixed before shipping: an early draft cached `config.API_TOKEN`'s value inside the long-lived authority singleton at first construction, so a test elsewhere that temporarily reassigns it would permanently poison every later test in the same process -- caught by real adversarial-suite failures, not a test written for this change; fixed by making the authority stateless with respect to that value. Still missing: "truthful Ollama-absence handling," the other named half of this organ's original blocker, has no further specification anywhere in the repo and is an unrelated concern (local-model availability reporting, not credential rotation) -- not investigated here. |

**Organ 36 note:** this organ's one ever-named blocker ("`dispatch_clerical_job()`
... not wired into `LocalWorkforceService`'s real request path") was
already stale -- PR #165 (commit `db07922`, 2026-07-27, "earn admission
from evidence, and make the chain a chain") had already wired a real,
persisted qualification lookup (`LocalWorkforceRegistry.get_qualification()`,
a genuine `SELECT` against the `local_worker_models` table, honestly `None`
for an unqualified model, never a fabricated pass) into the dispatch
decision inside `_execute_advisory_job()`, replacing an earlier
call-site-fabricated `QualificationResult(passed=True)` that PR #165's own
message documents finding and removing. This session's actual work was
narrower: build the missing `ClerkDispatcherAuthority` class (Decision A --
the class had never existed, only the bare function), and make
`LocalWorkforceService` call through `self.dispatcher_authority.dispatch()`
instead of importing the function directly. A new end-to-end test
(`test_the_dispatcher_authority_escalates_an_unqualified_model_through_the_
real_service`) drives the real `run_advisory_job()` entrypoint with an
unqualified model and proves the job is rejected with `"Dispatched to
frontier_escalation"` **and** the local LLM client is never called --
genuinely proving the escalation, not just that some rejection occurred.
Independently adversarially re-verified (fresh agent) before flipping:
confirmed the qualification wiring predates this session, confirmed no
other gap for this organ exists anywhere in this document's history, and
in the process of that check **found and corrected a real, separate stale
claim in organ 38's own row** (below) -- a prior pass had asserted the
dispatch gap was "unchanged" in a commit dated *after* PR #165 had already
fixed it, without re-verifying against the code. Counts: 7 green / 47
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

**Superseded baseline note (2026-07-28):** the historical yellow-table Organ 32 row below records the pre-Phase-2 state. The current Organ 32 verdict is the Phase 2/3 row above; its remaining blockers are intentionally listed there.

## Yellow organs (47)

**Superseded (2026-08-02):** this heading and the table below are a dated
snapshot from immediately after Decision A regressed 33 organs
(2026-07-27), before Phases 2 through 6 of the proof plan flipped most of
them back to green with real evidence. Most rows already carry their own
inline "Phase-2 re-audit"/"Phase 2 update" narrowing note recording that
re-verification, but the table's own **(47)** count and each row's
**yellow** status were never updated in place — per this doc's own
append-only convention (dated evidence is never silently rewritten), that
correction lives in a new section instead: see
"[Current reconciled state (2026-08-02)](#current-reconciled-state-2026-08-02)"
at the end of this document for the 38 green / 16 yellow split as of
2026-08-02, sourced directly from `.aios/state/ORGAN_GREEN_LEDGER.json` and
`release/phase6/organ23-shortfall.md`. Read every row below as history,
not current status.

**That 38/16 figure is itself now history.** The machine ledger reports
**46 green / 8 yellow** at master tip; see
"[Prose-to-ledger reconciliation (appended 2026-08-04)](#prose-to-ledger-reconciliation-appended-2026-08-04)"
at the very end of this document, which is the current section. Note that
`release/phase6/organ23-shortfall.md` is also pinned at the older 38/16
snapshot and carries its own currency banner.

The original 16 (Slices 26-40 completion target, minus organs 52 and 36
flipped green in Phase 1/2, 2026-07-28 — see above) plus 33 regressed
under Decision A (2026-07-27) — see the green-organ sections above.

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
| 34 | Cloud Budget and Provider-Health Organ | ProviderHealthBudgetAuthority | Decision A | **Phase-2 re-audit:** ProviderHealthBudgetAuthority is the concrete owner in the ledger-listed health entrypoint; ProviderHealthTracker is only its compatibility alias, and the shared API dependency returns the exact authority instance used by router/failover construction. The failover path consults is_call_allowed() and skips open circuits before provider calls, with focused tests proving the decision-bearing behavior. The organ remains yellow honestly: no live evidence, exact-tip strict-release attestation, or remaining green-contract conditions are claimed.
| 35 | Local Clerk Runtime | LocalClerkRuntimeAuthority | Decision A | **Phase-2 re-audit:** LocalClerkRuntimeAuthority is the concrete owner in the ledger-listed contracts entrypoint, and LocalWorkforceService invokes its eligible_models() decision before dispatch. Only installed, operator-approved, approved, healthy models with the requested earned profile can continue; no admitted model or failed qualification is turned into a fabricated passing result. Focused admission, dispatcher, API, provenance, and owner tests pass. The organ remains yellow honestly: no live evidence or exact-tip strict-release/remaining green-contract conditions are claimed.
| 37 | Local Model Qualification and Health | LocalModelQualificationAuthority | Decision A | **Phase-2 re-audit:** LocalModelQualificationAuthority is the concrete qualification suite in the ledger-listed qualifier entrypoint, and LocalWorkforceService invokes that exact factory before recording the result and changing admission. Qualification evidence is persisted and feeds fail-closed dispatch/profile checks; unsupported automatic profile derivation remains deliberately unclaimed. Focused qualification, evidence, API, dispatcher, runtime-proof, and owner tests pass. The organ remains yellow honestly: no live Ollama evidence or exact-tip strict-release/remaining green-contract conditions are claimed.
| 39 | Multi-Model Deliberation and Dissent Organ | DeliberationCouncilAuthority | Decision A | **Phase-2 re-audit:** DeliberationCouncilAuthority is the concrete gather/synthesis owner in the ledger-listed Council entrypoint, and the live QueenCouncilAuthority orchestrator invokes it for the advisory second-reviewer path. The path requires independent participants, uses a configured cloud provider for dissent rather than Ollama, and persists the resulting record through DeliberationStore when warranted. Focused deliberation, Council, API, store, and owner tests pass. The organ remains yellow honestly: live multi-model evidence and exact-tip strict-release/remaining green-contract conditions are not claimed.
| 40 | Isolated Workspace and Executor (live proof) | IsolatedExecutorLiveAuthority | Decision A | **Phase-2 re-audit:** IsolatedExecutorLiveAuthority owns the truthful authenticated executor-health projection in the ledger-listed executor read-model entrypoint, and the real mirror executor route calls it directly. Runnable executor service, client, mirror, and owner tests pass; local Docker integration tests are skipped because this sandbox has no Docker daemon. Existing CI-backed Docker isolation and restart evidence remains historical live evidence and is not newly restamped here. The organ remains yellow honestly: no new live evidence or exact-tip strict-release/remaining green-contract conditions are claimed.
| 41 | Promotion, Checkpoint and Rollback (live proof) | PromotionRollbackLiveAuthority | Decision A | **Phase-2 re-audit:** PromotionRollbackLiveAuthority owns the fail-closed checkpoint target contract in the ledger-listed promotion contracts entrypoint, and PromotionAuthority's real rollback callback gate invokes its checkpoint-id validation. Promotion and maintenance suites prove checkpoint creation, exact filesystem round-trip, promotion failure restoration, and forged-target refusal. The organ remains yellow honestly: the integration path uses injected checkpoint callbacks rather than a live Docker-backed checkpoint runtime, and no exact-tip strict-release/remaining green-contract conditions are claimed.
| 43 | Local Skill Reuse, Confidence and Demotion | SkillLifecycleAuthority | Decision A | **Phase-2 re-audit:** SkillLifecycleAuthority is the concrete owner in the ledger-listed lifecycle entrypoint, and all four real LearningService reuse/outcome paths invoke it. The owner records outcomes, applies confidence-driven demotion, and performs human revocation through the repository; lifecycle, learning-application, domain, and owner tests pass. The organ remains yellow honestly: no live evidence or exact-tip strict-release/remaining green-contract conditions are claimed.
| 45 | Constitutional Amendment Authority | `ConstitutionalAmendmentAuthority` | Decision A | **Phase-2 re-audit:** The concrete `ConstitutionalAmendmentAuthority` class in the ledger-listed amendment entrypoint owns the fail-closed ratification capability gate, and the real ratification route delegates to it only after the server has consumed an exact operator-bound capability. Activation and rollback then use the shared `ConstitutionAuthority` plus durable `ConstitutionSnapshotStore` chain, with compare-and-swap protection and focused API/store/owner tests passing. The organ remains yellow honestly: live adversarial simulation evidence, exact-tip strict-release attestation, and the remaining green-contract conditions are not claimed. |
| 47 | Read-Model and Projection Organ | `ReadModelProjectionAuthority` | Decision A | **Phase-2 re-audit:** The concrete `ReadModelProjectionAuthority` in the ledger-listed projection entrypoint owns the consolidated truthful governance surface, and the real `/api/v1/mirror/governance` route calls that authority directly with live constitution, emergency-stop, provider-health, pending-capability, routing, and privacy inputs. Focused projection, mirror, and owner suites pass. The organ remains yellow honestly: browser-surface verification, live evidence, exact-tip strict-release attestation, and the remaining green-contract conditions are not claimed. |
| 48 | Truthful Living Mirror (full truthful UI) | `TruthfulMirrorAuthority` | Decision A | **Phase-2 re-audit:** The concrete `TruthfulMirrorAuthority` in `frontend/src/workbench/SovereignStatePanel.jsx` owns governance/executor normalization and total-outage handling, and the live panel load path reaches that authority for both mirror endpoints. Focused frontend authority/dashboard tests pass 11/11 and the production bundle builds successfully. The organ remains yellow honestly: browser-session verification, live evidence, exact-tip strict-release attestation, and the remaining green-contract conditions are not claimed. |
| 49 | Approval and Decision Surface | `ApprovalDecisionSurfaceAuthority` | Decision A | **Phase-2 re-audit:** The concrete `ApprovalDecisionSurfaceAuthority` in `frontend/src/workbench/SovereignStatePanel.jsx` owns pending-decision accounting and the explicit fact approve/reject action calls; the live panel buttons reach that authority. The backend mirror projection exposes real pending capabilities without exposing bearer tokens, while capability consumption remains server-gated. Focused pending-approval/mirror tests and frontend authority tests pass. The organ remains yellow honestly: browser-session verification, live evidence, exact-tip strict-release attestation, and the remaining green-contract conditions are not claimed. |
| 50 | Provenance and Explanation Surface | `ProvenanceExplanationSurfaceAuthority` | Decision A | **Phase-2 re-audit:** The concrete `ProvenanceExplanationSurfaceAuthority` in `frontend/src/workbench/SovereignStatePanel.jsx` owns the routing/privacy explanation projection and the live panel reaches it. Backend `DevelopmentTracker` routing metadata is durably recorded and projected through the real mirror route; `PrivacyAuditTracker` receives audits from the real privacy-filter/provider call sites and projects measured redaction fields without fabrication, but remains a process-local diagnostic ring buffer by design. The full focused backend evidence suite and frontend authority tests pass. The organ remains yellow honestly: browser-session verification, durable privacy-history proof, live evidence, exact-tip strict-release attestation, and the remaining green-contract conditions are not claimed. |
| 51 | Sovereign Control and Heartbeat Surface | `SovereignHeartbeatSurfaceAuthority` | Decision A | **Phase-2 re-audit:** The concrete `SovereignHeartbeatSurfaceAuthority` in `frontend/src/workbench/SovereignStatePanel.jsx` owns measured stop-badge normalization: engaged is STOPPED, clear is operational, loading/unknown is unavailable or reconnecting, never silently clear. The live panel passes the real mirror emergency-stop envelope into it; backend `EmergencyStopController` state is durable and its fail-closed boundaries are covered by mirror and emergency-stop tests. The organ remains yellow honestly: browser-session verification, live evidence, exact-tip strict-release attestation, and the remaining green-contract conditions are not claimed. |
| 54 | Backup and Disaster-Recovery Organ | `BackupDisasterRecoveryAuthority` | Decision A | **Phase-2 re-audit:** The concrete `BackupDisasterRecoveryAuthority` in the ledger-listed recovery entrypoint owns verified backup installation and post-restore authority invalidation; the recovery CLI/compatibility path delegates to its singleton. It verifies archive hashes and safe paths, stages restores, retains a pre-restore safety backup, and invalidates stale sessions/capabilities/approvals after installation. Restore-invalidation, operations, owner, and launcher suites pass with focused Ruff. The organ remains yellow honestly: live disaster-recovery execution, exact-tip strict-release attestation, and the remaining green-contract conditions are not claimed. |
| 23 | Release Conformance Organ | `ReleaseConformanceAuthority` | 25 / 40 | Ledger established at this baseline; the strict gate stays non-green until every organ below turns green and Slice 40's final release proof lands. |
| 25 | Constitutional Kernel | `ConstitutionalKernelAuthority` | PR-1 | **PR-1: gap closed, status not yet flipped (CI verification pending).** Before this, three different answers to "what is the current constitution?" coexisted: the durable chain (written only by the amendment routes); a per-call `build_constitution_snapshot()` rebuild from live config that always returns version 1 (used by `IdentityService` for EVERY `Principal`, by `CapabilityAuthority.consume()`, by `mirror.py` and by `gateway_reasoning.py`); and a hardcoded `ratified_by_operator_id="operator"` fallback inside `PolicyKernel`, reached in all three real construction sites because none passed `constitution_authority=`. Measured consequence: an activated amendment moved the durable chain and reached NOTHING -- and because `consume()` compared a rebuilt digest against a binding stamped by the same rebuild, both sides always matched, making the stale-constitution rejection structurally unreachable for a real amendment (its four tests passed only by comparing fabricated literals no snapshot ever produced). `get_constitution_authority()` also raised `NameError` -- `aios/api/deps.py` never imported the class -- proving it had no callers. Now one `ConstitutionAuthority` is authoritative for the active snapshot, every `Principal` digest, `PolicyKernel` decisions, capability issuance and consumption, Council context and the mirror. The fabricated fallback is deleted (an unwired kernel raises). Enrollment is re-verified on EVERY call, not just the argument-free one -- load-bearing, because both production paths pass an explicit operator id; a supplied id is now an assertion to verify, never a chain selector, so no shadow chain can be minted. Fail-closed via `NoEnrolledSovereignError` / `OperatorIdentityChangedError` / `ConstitutionDegraded`, all mapped to one 503. Activation and rollback are compare-and-swap under `BEGIN IMMEDIATE`, with `expected_previous_digest` REQUIRED so an unprotected write is a `TypeError`, not a silent clobber. Proven by `tests/test_organ25_constitution_e2e.py` (real HTTP ceremony -> restart -> old-digest capability refused, new-digest accepted, rollback survives restart), which is mutation-checked: reverting `IdentityService` to the per-call rebuild fails all three cases. Remaining before green: green-contract conditions 11-12 only (record the exact tested commit, and have CI verify that same commit). |
| 27 | Operator Taste Model | `OperatorTasteModelAuthority` | PR1 | **Narrowed from green (see PR1 update note above):** `get_operator_preference_store()` (`aios/api/deps.py`) plus a real, explicit-only route (`aios/api/routes/preferences.py`) are the first production wiring `OperatorPreferenceStore` has ever had; expiry, withdrawal, restart recovery, and a scope-aware contradiction check (a real cross-scope false-contradiction bug, fixed) are all real and tested. **Phase 2 update (2026-07-29):** `OperatorTasteModelAuthority.active_preferences_for_scopes()` now owns the authenticated multi-scope decision: owner isolation, active/non-expired filtering, and project-over-global precedence. The real `/api/v1/chat` dependency graph resolves that authority, and `tests/test_authenticated_chat_route.py` proves the authority method is called with the authenticated owner and global/project scopes while the receipt/provider assertions prove the project preference is included and the superseded global preference is excluded. Still yellow honestly: no live operator-traffic/provider or exact-tip strict-release evidence is claimed, and the anonymous compatibility chat path intentionally remains separate.
| 28 | Project Understanding Organ | `ProjectUnderstandingAuthority` | PR1 | **Narrowed from green (see PR1 update note above):** the active-project pointer is now a durable singleton row (migration 0016), not a process-local global forgotten on every restart, and `diff_project_passports()` gives every rescan a real, computed diff. **Phase 2 update (2026-07-29):** Decision A now holds -- `ProjectUnderstandingAuthority` (`aios/application/memory/authorities.py`) owns the durable project store, active-project lookup, and stale/unverified passport rejection. The real `/api/v1/chat` dependency graph now resolves that authority, and `tests/test_authenticated_chat_route.py` proves the authority method is called with the authenticated owner and commit lookup while the receipt/provider assertions prove the project revision and passport reach Organ 31's context. Still yellow honestly: no live operator-traffic/live provider or exact-tip strict-release evidence is claimed, and anonymous compatibility chat intentionally has no authenticated project binding.
| 29 | Correction and Interpretation-Lineage Organ | `CorrectionLineageAuthority` | PR1 | **Narrowed from green (see PR1 update note above):** the real `/api/v1/conversation/correction` route now builds and durably persists a typed `CorrectionRecordV1` via a new `CorrectionRecordStore`. **Phase 2 update (2026-07-29):** Decision A now holds -- `CorrectionLineageAuthority` owns the correction store, compensating transaction, and the identity/event-bound `authenticated_active_projection()` selection used by authenticated chat. The real `/api/v1/chat` dependency graph resolves that authority, and `tests/test_authenticated_chat_route.py` proves the authority method is called with the authenticated operator/event while the correction is included in Organ 31's context before provider output and survives source-store restart. Still yellow honestly: anonymous chat intentionally has no authenticated correction authority, and live/exact-tip/remaining green-contract evidence is not claimed.
| 30 | Communication and Human-State Interpreter | `HumanStateInterpreterAuthority` | 28 / PR1 | **PR1 (fixes the exact bug named for this pass, see update note above):** migration 0013's mutable `corrected_state`/`corrected_at` columns let corrections overwrite each other while the row's own digest kept authenticating only the pre-correction fields -- outside the tamper check entirely. Migration 0014 replaces this with a genuinely append-only, digest-verified `human_state_corrections` table joined by hypothesis row id (not content digest, which was tried and rejected after it collapsed two same-content hypotheses into one accuracy bucket), each row bound to the authenticated operator (or an honest `None`) via `get_optional_principal()`. A live regression test tampers the new table directly and confirms `RecordTamperedError`. Still missing: the classifier itself has not been measured against real production operator traffic -- the new table is exactly the mechanism that will let that happen as real traffic accumulates, but none exists yet in this sandbox; a genuine, not-fabricatable gap. |
| 31 | Human Representative Context Compiler | RepresentativeContextCompilerAuthority | 29 | **Reconciliation + Phase-2 evidence:** every validated RepresentativeContextV1 is durably recorded by the append-only RepresentativeContextStore inside both route_intelligence_request() and stream_intelligence_request(). Council is a real caller, and authenticated /api/v1/chat now resolves operator preferences, active project passport, verified correction lineage, human-state evidence, identity, and constitution before entering the streaming gateway; its receipt is persisted before provider chunks. The prior claim that only Council called the compiler was stale and is withdrawn. Still yellow honestly: anonymous chat remains on its compatibility facts/recall path because it has no authenticated identity/constitution binding, and live/exact-tip/remaining green-contract evidence is not claimed.
| 32 | Universal Intelligence Gateway | `UniversalIntelligenceGatewayAuthority` | 41 | **Tier 4 update (operator-confirmed scope: streaming variant only) + this pass:** grounding found organ 32 is not just "add streaming" -- three separate, independent gateway-shaped systems exist (the Slice-30 `route_intelligence_request()`; the older `aios.runtime.intelligence_gateway.IntelligenceGateway`, confirmed load-bearing for real worker plan/repair reasoning; and `aios.application.models.hiring_service.IntelligenceHiringService`). New `stream_intelligence_request()` covers text-chunk model calls with the same upfront validation as the synchronous entrance. This pass wired organ 31's new `RepresentativeContextStore` into this module directly, so both entrances now durably record every context they compile. Still missing: chat (`/api/v1/chat`, the single most heavily used endpoint in the system) and the agentic forge (`/api/generate`) remain unwired -- chat has no authenticated operator/constitution digest today by design (anonymous local chat must keep working), and rewiring it without a live browser session to verify no UX regression was deliberately not attempted here, consistent with every prior pass's own risk read of this exact call site. The 2 other competing gateway implementations remain unreconciled. |
| 33 | Model Registry and Capability Passport | ModelPassportAuthority | 31 | **Phase-2 re-audit:** Decision A is satisfied and the local passport path is proven through a real caller and durable state. GET /api/v1/local-workforce/{model_id}/passport reaches ModelPassportAuthority, which projects from LocalWorkforceRegistry's SQLite row; the real refresh, approve, and qualify flow persists admission, role, qualification-suite, qualification-evidence, artifact, and expiry fields, and a fresh registry instance returns the same passport digest after restart. The prior claim that no durable store persists a passport is stale for the local path and is withdrawn. Still yellow honestly: this is deterministic injected-API evidence, not live Ollama qualification evidence; cloud/provider passport fields remain a separate intentional projection boundary, and exact-tip strict-release/remaining green-contract conditions are not claimed.
| 38 | Durable Local-Clerk Provenance and Continuity Organ | ClerkProvenanceAuthority | 41 | **Dedicated re-audit:** ClerkProvenanceAuthority owns both the production write and read-side reconstruction. LocalWorkforceService.run_advisory_job() records completed, refused, and schema-failed jobs through the injected SQLite LocalWorkforceProvenanceStore; the launcher reads the same durable trace, and a fresh-process test reconstructs the request, model call, result, and verified hash-linked chain after the writer exits. The old claim that dispatch_clerical_job() remained unwired was stale and is withdrawn; the persisted qualification lookup and ClerkDispatcherAuthority are separate, already-tested boundaries. Still yellow honestly: no live model evidence or exact-tip strict-release/remaining green-contract conditions are claimed.
| 42 | Recovery and Resumption | RecoveryResumptionAuthority | 41 | **Phase-2 re-audit:** RecoveryResumptionAuthority owns the durable MissionTransitionJournal shared by startup recovery, CouncilOrchestrator, and MaintenanceConvergenceService. The privileged maintenance approval route and repair execution record the exact ordered 11-state success history with contiguous sequence numbers; a fresh-process SQLite test reports an interrupted nonterminal mission with integrity verified. Failed/rolled-back escape paths remain covered by focused assertions. Still yellow honestly: no actual crash/interruption of a running repair or exact-tip CI evidence is attached.
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
tests, a non-frozen organ whose `authority_owner` is not defined as a class
anywhere in its own `production_entrypoints` when the Phase 2
`enforce_owner_attestation` gate is enabled (yellow rows included), a frozen
security-spine organ claiming green, a `green` organ that requires live
evidence but has none, live evidence labelled `fixture` where `live` is
required, and live evidence stamped with any commit other than the one under
evaluation.

## Current reconciled state (2026-08-02)

This section is the authoritative summary of the ledger's current status,
appended after a full hands-on re-audit of all 38 green organs (every
`condition_verdicts` claim checked against real code and real test runs,
not narrative). It exists because the historical tables above stop tracking
status changes partway through Phase 2 — each organ's own inline note is
kept up to date, but the section headings/counts around them ("Yellow
organs (47)", the Phase 1/2 tables) are dated snapshots, per this doc's
own append-only convention. Machine-readable source of truth remains
`.aios/state/ORGAN_GREEN_LEDGER.json`; the itemized non-green breakdown is
`release/phase6/organ23-shortfall.md`.

**Counts: 38 green / 16 yellow / 54 total.** Evaluated at commit
`b5ef592864363ca9882277801cde92bff90b15d7`; `python
scripts/verify_organ_contracts.py` and `--require-sha-ancestry` both pass
with zero contract violations.

### Green (38)

| # | Organ | Authority owner | Production entrypoint(s) |
|---|-------|------------------|---------------------------|
| 6 | Edge Trust Boundary | `EdgeTrustAuthority` | `aios/interfaces/http/edge_security.py` |
| 7 | Policy Kernel | `PolicyKernelAuthority` | `aios/policy/kernel.py` |
| 8 | Action Broker | `ActionBrokerAuthority` | `aios/application/action_broker.py` |
| 9 | Exact Capability Authority | `CapabilityAuthority` | `aios/application/capabilities/authority.py` |
| 10 | Mission Authority | `MissionAuthority` | `aios/application/missions/mission_service.py` |
| 11 | Turn Coordinator | `TurnCoordinatorAuthority` | `aios/application/turns/turn_coordinator.py` |
| 12 | Worker Foundry | `WorkerFoundryAuthority` | `aios/application/workers/foundry.py` |
| 13 | Isolated Executor Service (construction) | `ExecutorServiceAuthority` | `aios/executor_service.py` |
| 14 | Staged Workspace Manager (construction) | `StagedWorkspaceAuthority` | `aios/application/workspaces/staged.py` |
| 15 | Evidence and Verification Authority (construction) | `VerificationAuthority` | `aios/application/evidence/verification.py` |
| 16 | Promotion Authority (construction) | `PromotionAuthority` | `aios/application/promotion/authority.py` |
| 17 | Cortex Observation Bus | `CortexBusAuthority` | `aios/runtime/cortex_bus.py` |
| 18 | Memory Authority (construction) | `MemoryAuthority` | `aios/application/memory/authority.py` |
| 19 | Emergency Stop Controller (construction) | `EmergencyStopController` | `aios/application/governance/emergency_stop.py` |
| 21 | Queen Council Orchestrator | `QueenCouncilAuthority` | `aios/council/council_orchestrator.py` |
| 22 | V1 Release Declaration (gagos v1-check) | `ReleaseDeclarationAuthority` | `aios/application/governance/v1_declaration.py` |
| 24 | Human Sovereign Identity | `IdentityAuthority` | `aios/domain/identity/models.py`, `aios/application/identity/service.py`, `aios/infrastructure/identity/sqlite_store.py` |
| 25 | Constitutional Kernel | `ConstitutionalKernelAuthority` | `aios/application/governance/constitution_authority.py` (+ 11 more, see ledger) |
| 26 | Emergency Stop Organ (full boundary hard-wiring) | `EmergencyStopHardWiringAuthority` | `aios/runtime/intelligence_gateway.py`, `aios/application/learning/service.py`, `aios/application/maintenance/service.py` (+ 5 more) |
| 27 | Operator Taste Model | `OperatorTasteModelAuthority` | `aios/domain/memory/human_representation.py`, `aios/application/memory/human_representation.py`, `aios/infrastructure/memory/human_representation_store.py` (+ 6 more) |
| 28 | Project Understanding Organ | `ProjectUnderstandingAuthority` | `aios/domain/memory/human_representation.py`, `aios/application/memory/human_representation.py`, `aios/infrastructure/memory/human_representation_store.py` (+ 4 more) |
| 29 | Correction and Interpretation-Lineage Organ | `CorrectionLineageAuthority` | `aios/domain/memory/human_representation.py`, `aios/application/memory/human_representation.py`, `aios/infrastructure/memory/human_representation_store.py` (+ 4 more) |
| 30 | Communication and Human-State Interpreter | `HumanStateInterpreterAuthority` | `aios/domain/memory/human_representation.py`, `aios/application/memory/human_representation.py`, `aios/application/turns/conversation_pipeline.py` (+ 2 more) |
| 31 | Human Representative Context Compiler | `RepresentativeContextCompilerAuthority` | `aios/domain/intelligence/representative_context.py`, `aios/application/intelligence/context_compiler.py`, `aios/application/intelligence/gateway.py` (+ 2 more) |
| 32 | Universal Intelligence Gateway | `UniversalIntelligenceGatewayAuthority` | `aios/application/intelligence/gateway.py`, `aios/council/gateway_reasoning.py`, `aios/application/intelligence/authenticated_chat.py` (+ 8 more) |
| 34 | Cloud Budget and Provider-Health Organ | `ProviderHealthBudgetAuthority` | `aios/domain/models/contracts.py`, `aios/application/models/health.py`, `aios/core/failover.py` (+ 2 more) |
| 36 | Clerical Job Contract and Dispatcher | `ClerkDispatcherAuthority` | `aios/application/local_workforce/dispatcher.py`, `aios/application/local_workforce/service.py` |
| 38 | Durable Local-Clerk Provenance and Continuity Organ | `ClerkProvenanceAuthority` | `aios/infrastructure/local_workforce/sqlite_store.py`, `aios/application/local_workforce/provenance.py` (+ 4 more) |
| 39 | Multi-Model Deliberation and Dissent Organ | `DeliberationCouncilAuthority` | `aios/domain/intelligence/deliberation.py`, `aios/application/intelligence/deliberation.py`, `aios/council/deliberation_gather.py` (+ 4 more) |
| 41 | Promotion, Checkpoint and Rollback (live proof) | `PromotionRollbackLiveAuthority` | `aios/application/promotion/authority.py`, `aios/domain/promotion/contracts.py` |
| 42 | Recovery and Resumption | `RecoveryResumptionAuthority` | `aios/application/recovery/authority.py` (+ 10 more, see ledger) |
| 43 | Local Skill Reuse, Confidence and Demotion | `SkillLifecycleAuthority` | `aios/domain/learning/skill_contracts.py`, `aios/domain/learning/repository.py`, `aios/application/learning/skill_lifecycle.py` |
| 45 | Constitutional Amendment Authority | `ConstitutionalAmendmentAuthority` | `aios/domain/governance/amendments.py` (+ 10 more, see ledger) |
| 47 | Read-Model and Projection Organ | `ReadModelProjectionAuthority` | `aios/domain/read_models/contracts.py`, `aios/application/read_models/governance_projections.py`, `aios/api/routes/mirror.py` |
| 50 | Provenance and Explanation Surface | `ProvenanceExplanationSurfaceAuthority` | `aios/memory/development.py`, `aios/application/models/privacy_audit.py`, `aios/core/failover.py` (+ 7 more) |
| 52 | Observability and Health Organ | `ObservabilityAuthority` | `aios/api/main.py`, `aios/council/queen_service.py`, `aios/operations/tracing.py` (+ 4 more) |
| 53 | Installation, Configuration and Key Authority | `InstallationConfigurationAuthority` | `aios/domain/security/api_token.py`, `aios/infrastructure/security/api_token_store.py`, `aios/application/security/api_token_authority.py` (+ 6 more) |
| 54 | Backup and Disaster-Recovery Organ | `BackupDisasterRecoveryAuthority` | `aios/operations/recovery.py`, `aios/operations/doctor.py`, `aios/__main__.py` |

### Yellow (16) — exact residual, from `release/phase6/organ23-shortfall.md`

| # | Organ | Authority owner | Residual |
|---|-------|------------------|----------|
| 1 | Security Gateway | `SecurityGatewayAuthority` | frozen spine — section VIII controlled release required before green/live claim |
| 2 | Scope Lock | `ScopeLockAuthority` | frozen spine — section VIII controlled release required before green/live claim |
| 3 | Secret Scanner | `SecretScannerAuthority` | frozen spine — section VIII controlled release required before green/live claim |
| 4 | Tamper-Evident Audit Logger | `AuditLoggerAuthority` | frozen spine — section VIII controlled release required before green/live claim |
| 5 | Prompt Injection Shield | `InjectionShieldAuthority` | frozen spine — section VIII controlled release required before green/live claim |
| 20 | Living Mirror Reaction Registry (construction) | `LivingMirrorAuthority` | browser-session — truthful UI live evidence requires operator browser session at :5173 (not inventable headless) |
| 23 | Release Conformance Organ | `ReleaseConformanceAuthority` | Phase 6 gate — organ 23 stays yellow until every below-organ is honestly green |
| 33 | Model Registry and Capability Passport | `ModelPassportAuthority` | no Ollama — live local-model / passport qualification evidence needs live Ollama in CI or self-hosted runner |
| 35 | Local Clerk Runtime | `LocalClerkRuntimeAuthority` | no Ollama — live local clerk runtime evidence needs live Ollama |
| 37 | Local Model Qualification and Health | `LocalModelQualificationAuthority` | no Ollama — live model qualification suite needs live Ollama |
| 40 | Isolated Workspace and Executor (live proof) | `IsolatedExecutorLiveAuthority` | no Docker — Docker Desktop daemon unavailable on this Windows host; historical CI Docker isolation evidence retained, not tip-restamped |
| 44 | Golden Mission and Endurance Evaluation | `GoldenMissionEnduranceAuthority` | Outside-machine — cloud-provider credentials barred; cannot invent cloud golden-cohort live evidence |
| 46 | Constitutional Learning Organ | `ConstitutionalLearningAuthority` | no Ollama — live constitutional learning / human red-team path needs live Ollama and/or Outside-machine cloud; human red-team still absent by design |
| 48 | Truthful Living Mirror (full truthful UI) | `TruthfulMirrorAuthority` | browser-session — truthful UI live evidence requires operator browser session at :5173 (not inventable headless) |
| 49 | Approval and Decision Surface | `ApprovalDecisionSurfaceAuthority` | browser-session — truthful UI live evidence requires operator browser session at :5173 (not inventable headless) |
| 51 | Sovereign Control and Heartbeat Surface | `SovereignHeartbeatSurfaceAuthority` | browser-session — truthful UI live evidence requires operator browser session at :5173 (not inventable headless) |

None of the 16 are yellow because of a hidden defect found in this
re-audit — every one blocks on a genuinely outside-machine residual
(frozen security spine pending its own §VIII controlled release, no
Ollama/Docker on this host, UI evidence that requires an operator
browser session, or cloud credentials this session is barred from
supplying). The one real defect this re-audit did find was narrow and
non-status-affecting: organs 16 and 41 both cited
`checkpoint_id_is_valid()` (a trivial format validator) as their `C4`
tamper-evidence proof in `condition_verdicts`, when the real proof is
`tests/test_promotion_authority.py::test_apply_or_smoke_failure_restores_exact_bytes_via_real_checkpoint_authority`,
which drives the actual production `CheckpointAuthority`-backed adapters
through a genuine filesystem round trip. Both citations were corrected in
the ledger; neither organ's green status changed.

---

## Prose-to-ledger reconciliation (appended 2026-08-04)

**This section changes no organ's status. It corrects this document, which
had fallen eight organs behind the machine ledger it is supposed to
narrate.**

### The drift

`.aios/state/ORGAN_GREEN_LEDGER.json` at `fe6f1661` (master tip) reports:

| | machine ledger | this document, before this section |
|---|---|---|
| green | **46** | 38 (§ above, line ~595) |
| yellow | **8** | 16 (§ "Yellow (16)" table above) |
| yellow ids | **1, 2, 3, 4, 5, 23, 44, 46** | 1–5, 20, 23, 33, 35, 37, 40, 44, 46, 48, 49, 51 |

Eight organs are recorded green in the machine ledger while the "Yellow (16)"
table above still lists them yellow, in several cases with a residual reason
(*"no Ollama"*, *"browser-session"*) that the ledger's own evidence says was
subsequently satisfied:

| # | Organ | Stale reason in the table above | `last_verified_sha` recorded in the JSON ledger |
|---|-------|--------------------------------|--------------------------------------------------|
| 20 | Living Mirror Reaction Registry | browser-session | `14856c23` |
| 33 | Model Registry and Capability Passport | no Ollama | `90830647` |
| 35 | Local Clerk Runtime | no Ollama | `4cd9f155` |
| 37 | Local Model Qualification and Health | no Ollama | `4cd9f155` |
| 40 | Isolated Workspace and Executor (live proof) | no Docker | `14856c23` |
| 48 | Truthful Living Mirror (full truthful UI) | browser-session | `5c64cd54` |
| 49 | Approval and Decision Surface | browser-session | `5c64cd54` |
| 51 | Sovereign Control and Heartbeat Surface | browser-session | `5c64cd54` |

The remaining 8 yellows are unchanged and unchallenged: organs 1–5 (frozen
security spine, pending its own §VIII controlled release), 23 (release
conformance, gated on every below-organ), 44 (paid-cloud endurance cohort)
and 46 (constitutional learning / human red-team).

### Why it happened, and the standing rule

PRs #185, #186 and #187 (2026-08-02→03) updated
`.aios/state/ORGAN_GREEN_LEDGER.json` and left this document untouched; its
last content commit is `158d1824`. The failure is exactly the one this
document's §"Machine-readable source of truth" line already anticipates — the
prose is a narration, not an authority, and it decayed.

**The machine ledger is the only status authority.** When they disagree, the
JSON wins and this document is the defect. Any PR that moves an organ's
`status` must append here in the same change.

### Scope of this section — read this before citing it

This is a **reconciliation, not a re-audit**. What was actually checked to
write it: the `status` field of all 54 rows in the JSON ledger, and the
`last_verified_sha` / `live_evidence` fields of the eight organs tabulated
above, read directly from the file at master tip.

What was **not** checked here, and is not claimed: that those eight organs'
evidence is sound, that their `condition_verdicts` hold, or that the SHAs
above are ancestors of tip. Those are `scripts/verify_organ_contracts.py
--require-sha-ancestry`'s job in CI, and this section deliberately does not
restate its verdict as if independently confirmed. The last independent
hands-on re-audit recorded in this document remains the 38-green pass above;
the eight flips have not been re-audited by hand since.

---

<!-- BEGIN GENERATED: CURRENT ORGAN STATUS -- do not hand-edit -->

## Current organ status (generated)

**This section is generated by `scripts/build_organ_ledger_doc.py` from
`.aios/state/ORGAN_GREEN_LEDGER.json`. Do not hand-edit it.** Everything
above it is dated, hand-written history and is preserved verbatim; only
this region tracks current truth. If you moved an organ's status, run the
script (then `build_release_manifest.py`) rather than editing here.

- **Counts:** 52 green / 2 yellow / 54 total
- **Source ledger sha256:** `b8730a4c29ba775ad7d4427b9397af284e2c72ec1e2c618dfad45fb856645671`

Status, owner, evidence SHA and residuals below are copied mechanically
from the ledger. This section asserts only that it faithfully reflects
the JSON -- not that the underlying evidence is sound. That judgement
belongs to `scripts/verify_organ_contracts.py` and to the dated hands-on
re-audits recorded above.

### Green (52)

| # | Organ | Authority owner | Evidence SHA | Proof |
|---|-------|------------------|--------------|-------|
| 1 | Security Gateway | `SecurityGatewayAuthority` | `f3cb6122fb8d` | live |
| 2 | Scope Lock | `ScopeLockAuthority` | `f3cb6122fb8d` | live |
| 3 | Secret Scanner | `SecretScannerAuthority` | `f3cb6122fb8d` | live |
| 4 | Tamper-Evident Audit Logger | `AuditLoggerAuthority` | `f3cb6122fb8d` | live |
| 5 | Prompt Injection Shield | `InjectionShieldAuthority` | `f3cb6122fb8d` | live |
| 6 | Edge Trust Boundary | `EdgeTrustAuthority` | `5d482164707c` | live |
| 7 | Policy Kernel | `PolicyKernelAuthority` | `5d482164707c` | live |
| 8 | Action Broker | `ActionBrokerAuthority` | `5d482164707c` | live |
| 9 | Exact Capability Authority | `CapabilityAuthority` | `5d482164707c` | live |
| 10 | Mission Authority | `MissionAuthority` | `5d482164707c` | live |
| 11 | Turn Coordinator | `TurnCoordinatorAuthority` | `5d482164707c` | live |
| 12 | Worker Foundry | `WorkerFoundryAuthority` | `5d482164707c` | live |
| 13 | Isolated Executor Service (construction) | `ExecutorServiceAuthority` | `5d482164707c` | live |
| 14 | Staged Workspace Manager (construction) | `StagedWorkspaceAuthority` | `5d482164707c` | live |
| 15 | Evidence and Verification Authority (construction) | `VerificationAuthority` | `5d482164707c` | live |
| 16 | Promotion Authority (construction) | `PromotionAuthority` | `5d482164707c` | live |
| 17 | Cortex Observation Bus | `CortexBusAuthority` | `5d482164707c` | live |
| 18 | Memory Authority (construction) | `MemoryAuthority` | `5d482164707c` | live |
| 19 | Emergency Stop Controller (construction) | `EmergencyStopController` | `5d482164707c` | live |
| 20 | Living Mirror Reaction Registry (construction) | `LivingMirrorAuthority` | `14856c23e08b` | live |
| 21 | Queen Council Orchestrator | `QueenCouncilAuthority` | `5d482164707c` | live |
| 22 | V1 Release Declaration (gagos v1-check) | `ReleaseDeclarationAuthority` | `5d482164707c` | live |
| 24 | Human Sovereign Identity | `IdentityAuthority` | `5d482164707c` | live |
| 25 | Constitutional Kernel | `ConstitutionalKernelAuthority` | `5d482164707c` | live |
| 26 | Emergency Stop Organ (full boundary hard-wiring) | `EmergencyStopHardWiringAuthority` | `5d482164707c` | live |
| 27 | Operator Taste Model | `OperatorTasteModelAuthority` | `5d482164707c` | live |
| 28 | Project Understanding Organ | `ProjectUnderstandingAuthority` | `5d482164707c` | live |
| 29 | Correction and Interpretation-Lineage Organ | `CorrectionLineageAuthority` | `5d482164707c` | live |
| 30 | Communication and Human-State Interpreter | `HumanStateInterpreterAuthority` | `5d482164707c` | live |
| 31 | Human Representative Context Compiler | `RepresentativeContextCompilerAuthority` | `5d482164707c` | live |
| 32 | Universal Intelligence Gateway | `UniversalIntelligenceGatewayAuthority` | `5d482164707c` | live |
| 33 | Model Registry and Capability Passport | `ModelPassportAuthority` | `90830647e40c` | live |
| 34 | Cloud Budget and Provider-Health Organ | `ProviderHealthBudgetAuthority` | `5d482164707c` | live |
| 35 | Local Clerk Runtime | `LocalClerkRuntimeAuthority` | `4cd9f1550cf1` | live |
| 36 | Clerical Job Contract and Dispatcher | `ClerkDispatcherAuthority` | `5d482164707c` | live |
| 37 | Local Model Qualification and Health | `LocalModelQualificationAuthority` | `4cd9f1550cf1` | live |
| 38 | Durable Local-Clerk Provenance and Continuity Organ | `ClerkProvenanceAuthority` | `5d482164707c` | live |
| 39 | Multi-Model Deliberation and Dissent Organ | `DeliberationCouncilAuthority` | `5d482164707c` | live |
| 40 | Isolated Workspace and Executor (live proof) | `IsolatedExecutorLiveAuthority` | `14856c23e08b` | live |
| 41 | Promotion, Checkpoint and Rollback (live proof) | `PromotionRollbackLiveAuthority` | `5d482164707c` | live |
| 42 | Recovery and Resumption | `RecoveryResumptionAuthority` | `5d482164707c` | live |
| 43 | Local Skill Reuse, Confidence and Demotion | `SkillLifecycleAuthority` | `5d482164707c` | live |
| 45 | Constitutional Amendment Authority | `ConstitutionalAmendmentAuthority` | `5d482164707c` | live |
| 46 | Constitutional Learning Organ | `ConstitutionalLearningAuthority` | `3dc7323d74cc` | live |
| 47 | Read-Model and Projection Organ | `ReadModelProjectionAuthority` | `5d482164707c` | live |
| 48 | Truthful Living Mirror (full truthful UI) | `TruthfulMirrorAuthority` | `5c64cd54ca52` | live |
| 49 | Approval and Decision Surface | `ApprovalDecisionSurfaceAuthority` | `5c64cd54ca52` | live |
| 50 | Provenance and Explanation Surface | `ProvenanceExplanationSurfaceAuthority` | `5d482164707c` | live |
| 51 | Sovereign Control and Heartbeat Surface | `SovereignHeartbeatSurfaceAuthority` | `5c64cd54ca52` | live |
| 52 | Observability and Health Organ | `ObservabilityAuthority` | `5d482164707c` | live |
| 53 | Installation, Configuration and Key Authority | `InstallationConfigurationAuthority` | `5d482164707c` | live |
| 54 | Backup and Disaster-Recovery Organ | `BackupDisasterRecoveryAuthority` | `5d482164707c` | live |

### Yellow (2) — exact residual, from the ledger's own `known_blockers`

| # | Organ | Authority owner | Residual |
|---|-------|------------------|----------|
| 23 | Release Conformance Organ | `ReleaseConformanceAuthority` | Phase 6 gate — organ 23 stays yellow until every below-organ is honestly green |
| 44 | Golden Mission and Endurance Evaluation | `GoldenMissionEnduranceAuthority` | MEASURED: golden cohort mean 1.00 of 5, from 4 complete runs scoring 2/5, 0/5, 2/5, 0/5 on gemini-2.5-pro (2026-08-16). Pre-fix mean over 3 runs was also 1.00 (each 1/5). This is the first time this organ's number rests on a distribution rather than a single run, and it supersedes every earlier single-run figure. FIXES THAT DID NOT MOVE IT: three agent-loop defects (loop detection killing the edit-test-edit-test cycle; the no-sibling-test note not naming the file; failure detail truncated to 500 chars), surfacing empty turns (#220), and the Gemini truncation fix (#222, the model was thinking past a 1024-token output budget and being cut off mid-thought). Each fixed a real defect; none raised the score. A single post-fix run scored 2/5 and looked like improvement -- repeats showed it was the top of a bimodal distribution, not a new level. WHAT DID CHANGE: zero 'model produced no output' failures across 24 post-fix missions, against 2 of 4 failures before -- categorical, not statistical. Also structural: pre-fix, three runs each passed a DIFFERENT mission; post-fix, multi-module and error-handling pass together whenever a run passes at all. REMAINING CAUSES, by frequency: (1) unverified -- implementation written with no sibling test, so nothing to verify; (2) error -- the loop-safety detector stopping a repeating turn; (3) FIXED #224: the post-refresh retry replayed a capability bound to the replaced session (binding mismatch -> 400); it truncated three long runs. Green would require the missions to actually pass, which they do not. Evidence: release/organ-44/2026-08-16-cohort-distribution.md.<br>Outside-machine — this is a laptop run. CI has neither cloud credentials nor the aios-worker/aios-executor images.<br>MEASURED endurance 0.611 (18 turns, 11 verified_success) against a 0.80 bar — RED. First endurance run this organ has ever had: the harness posted to /api/generate with no session, no CSRF and no 428 replay, so it could never have completed a turn. Two further defects were found by running it: the 900s privileged window (identity/service.py) lapsed mid-run and no client refresh existed, so no run could ever finish the harness's own 30-minute default; and the first refresh fix called reauth without login, which the backend refused (401 on /api/v1/auth/reauth). Latency held: p95 178.92s vs 100.92s baseline, stable across 29.9 minutes. The failing 39% is the model's own tests disagreeing with its own code (DID NOT RAISE ValueError on chunk_list(size<0); is_palindrome('123ab321')), the same shape as the golden cohort. Evidence: release/organ-44/2026-08-16-first-endurance-measurement.md; tests/test_probe_drivers_authenticate.py. Memory stability was NOT measured in that run (see #226); the 0.611 verdict rests on success-rate and latency only, and stands.<br>Open, found by the first endurance run: the harness can only run once per instance, because the enrollment credential is one-time and AIOS_OPERATOR_CREDENTIAL is documented nowhere. RESOLVED since: (a) the post-refresh 400 (#224) -- a capability is bound to the principal, so re-login invalidated any approval token in flight; reproduced live (400) and verified fixed (200); (b) memory sampling (#226) -- it used `resource` (absent on Windows, so every turn recorded None) and, where it did work, read RUSAGE_SELF, i.e. the test driver rather than GAGOS. It now samples the process LISTENing on the API port, states a reason when it cannot, and reports first/last/peak/growth. Verified live: 126.5MB -> 135.3MB, growth 8.8MB. |

<!-- END GENERATED: CURRENT ORGAN STATUS -->
