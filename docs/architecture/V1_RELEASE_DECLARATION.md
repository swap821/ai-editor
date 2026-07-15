# GAGOS v1 release declaration

The repository exposes an evidence-backed declaration through:

```text
gagos v1-check
gagos v1-check --json
gagos v1-check --strict
```

The declaration reports two independent facts for every blocking gate:

- `source_present`: the named implementation artifacts exist in the checkout.
- `runtime_proven`: a real runtime probe or production integration test proved
  the behavior and authority boundary.

`source_present` is never sufficient for production readiness. A source-present
gate without runtime proof is `PARTIAL`, not passed. A missing source is
`BLOCKED`; only both facts being true produces `VERIFIED`. `--strict` exits
non-zero until every blocking gate is `VERIFIED`. It never substitutes a
synthetic metric or a model claim for an operator, capability, executor,
verification, rollback, Cortex, mirror, memory, or emergency-control invariant.

The declaration is intentionally not a production-ready claim merely because
the source compiles or a directory exists. In this checkout the strict
declaration remains blocked because production runtime proof for the durable
Human Sovereign identity and the exact capability layer is unavailable. The
isolated Executor Service, EmergencyStopController, and packaged production
authority matrix remain `PARTIAL` until their runtime wiring is proven.
PromotionAuthority is now verified at the bounded production/demo Council
integration boundary, but that does not substitute for the complete R14
runtime-proof matrix.
Docker unavailability independently blocks the executor runtime probe. The
Human Sovereign is the only authority allowed to resolve those blockers.

### Current convergence wave

R0 reset the declaration to executable source-versus-runtime truth. R1
self-verified the HTTP edge boundary: strict peer/Host/Origin allowlists,
session-bound CSRF for browser mutations, trusted-proxy handling, and removal
of privileged JSON body-session authorization. Claude and Kimi were unavailable
for this wave, so there is no independent reviewer verdict; the strict
declaration remains non-zero until Human Sovereign identity, exact capabilities,
and production runtime authority are proven.

The R2 identity foundation now persists exactly one operator record and local
device, stores only credential/recovery digests, records bounded login and
strong re-authentication events, and exposes only opaque cookie sessions with
rotation and revocation. Privileged mutations resolve the durable principal;
caller-supplied JSON authority fields and body session IDs are ignored. The
source and hermetic route proof are green, but production runtime authority
proof remains open.

R3 now provides the exact-capability core: complete operator/device/authentication
event/session/action/route/method/payload/resource/mission/contract/policy/scope/
verification binding, canonical digests, opaque token storage, server-owned replay
payloads, durable same-session grant cursors, expiry, atomic single-use
consumption, revocation, and a fail-closed verifier. Generate, terminal, execute,
rollback, and Council rollback issue exact capabilities. Production HTTP routes no
longer import or consume the legacy ApprovalStore; the legacy ApprovalStore
remains only as an explicitly isolated compatibility adapter with focused unit
coverage. R4 now places ordinary mutating routes behind the universal
`ActionEnvelope -> PolicyKernel -> ActionBroker` pre-dispatch boundary, while
the exact streaming/approval/rollback family retains its bespoke broker flow.
Production runtime proof is required before this gate can be `VERIFIED`; the
source and hermetic R4 route proof do not upgrade the declaration by themselves.

R5 now owns both production turn pipelines behind `TurnCoordinator`: the
application handlers contain conversational and generation preparation,
capability, approval-resume, tool/verification, and terminal lifecycle logic.
Focused handler and full backend gates are green. A real isolated
production-profile process proved identity/session rotation, normal chat and
generate lifecycle frames, two exact approval pauses/resumes,
no-write-before-approval, final verification, and durable Cortex
`turn.started`/`route.selected`/`turn.completed` plus `turn.failed` delivery
without filesystem mutation. R5 is `VERIFIED` at this declared boundary; the
overall declaration remains blocked by the other source-present/runtime-
unproven gates.

R6 now makes the SQLite mission repository authoritative for Human Sovereign
mission approval and rejection. The serialized transition records the real
operator, consumed exact-capability digest, authentication event, session,
contract digest, and runtime contract digest; synthetic/system approval actors,
altered contracts, duplicate approvals, approval after rejection, and execution
of an unapproved mission are refused. Council writes JSON decisions/reports and
schedules the worker only after the authoritative transition. Focused authority
proof is green, including concurrent approval races, restart durability,
projection tamper resistance, and real Council-originated execution. R6 is
verified at this declared boundary; the overall declaration remains partial,
and capability consumption plus mission transition still live in separate
stores pending the later executor/recovery waves.

R7 is verified at its declared WorkerFoundry boundary. WorkerFoundry’s default
production registry contains only the deterministic handler; all other
strategy adapters require explicit injection and no longer present a callable
path that fails with `StrategyUnavailable`. Worker lifecycle observations use
the canonical `worker.*` vocabulary and carry the derived principal plus
contract execution context. Direct generation `rolePass`/`swarm` requests fail
closed as experimental until Foundry owns their lifecycle. The full backend
gate is `3,123` tests collected with all non-skipped tests passing at `88.98%`
coverage. R8 is `VERIFIED` at its declared private Executor boundary: the
private client, production fail-closed wiring, disposable-worker handling, and
Compose/CI topology are present, and a live source-bearing no-socket control-
plane probe reached the private service and disposable worker. The probe proved
non-root execution, no network, staged-workspace confinement, bounded/truncated
output, timeout refusal, and missing-service refusal. The overall declaration
remains partial because staged workspaces, evidence/promotion, memory, mirror,
and recovery/emergency waves are incomplete.

Emergency stop is a separate durable latch in
`aios/application/governance/emergency_stop.py`. It persists before invoking
its five hooks, leaves the latch engaged if a hook fails, and requires a new
privileged authentication event to clear.

R9 is verified at the staged-workspace boundary. Production/demo Council
execution stages enrolled projects before WorkerFoundry mutation, with durable
mission leases, symlink/path/enrollment checks, deterministic baseline/diff
data, terminal cleanup, and failure retention for evidence inspection. The
focused R9 gate is `59 passed, 1 skipped`; the latest authoritative full
backend gate exits `0` at `88.99%` coverage.

R10 is verified at the bounded evidence/verification/promotion/rollback
boundary. `EvidenceBundle` binds mission, worker, contract, workspace, diff,
executor, environment, commands, output digests, verification strength,
targets, and timestamps. Production/demo Council execution now routes staged
worker output through `VerificationAuthority` and `PromotionAuthority`, which
revalidates the durable lease and baseline, creates a recovery checkpoint,
applies the exact staged diff, performs an exact-copy post-promotion smoke,
records evidence, and restores the checkpoint on failure. The focused R10 gate
is `66 passed, 1 skipped`; the authoritative full backend gate exits `0` with
all tests passing at `88.94%` coverage. The strict declaration remains blocked
until the remaining packaged runtime-proof gates are satisfied.

R11 remains `PARTIAL`: MemoryAuthority now owns recall trust semantics, the
memory route emits canonical phases, episodic turn writes/session restore and
semantic chat indexing cross authority adapters, production specialized recall
uses authority adapters, and production fact/development/skill/lesson/
reflection/consolidation/planner/compaction writes dispatch through authority
adapters. Council lesson recall and mission-scoped append-only deliberation
evidence also use scoped adapters. Contradiction reconciliation, supersession,
consolidator bulk status reads, default-chat confidence calibration reads, and
reflection lesson reads now dispatch through MemoryAuthority in the production
path, with direct-store bypass regressions covered. Advisory pheromone
operations, Council context, hibernation preview, and system onboarding
episodic counts also route through authority-owned adapters. The process-wide
working/semantic compactor facades, Cortex self-model production wiring,
consolidation and semantic-indexer dependencies, and development
metrics/skills/trails read routes and system metrics now use the authority as
well. Specialist dependency providers now return canonical
facts/development/skills/lessons stores while explicit injected fakes remain
supported. Mirror snapshot development/skill reads also use the authority.
Planner, ReflectionAgent, and the authority bootstrap's consolidator reuse
registered specialist stores; direct construction remains only in explicit
standalone/injected-fake compatibility paths. Generate-pipeline facts, skills,
lessons, self-model, and confidence-calibration reads now require authority
ownership before taking the authority path.
The post-write
affected gate is `340 passed, 2
skipped` across `342` collected tests. The follow-on planner/native-planner/
compaction gate is `73 passed` across `73` collected tests. The authoritative
package-wide gate exits `0` with `3,159` collected, `3,151 passed, 8 skipped`,
`91.04%` line coverage (`21,129/23,209`), and `80.57%` branch coverage
(`5,016/6,226`); combined coverage is `88.82%`. Packaged runtime proof remains
open: the canonical API health process returned `200`, while the legacy
daily-use mutation probe correctly returned `403` without an authenticated
session and CSRF proof. This wave does not
upgrade the strict declaration.
