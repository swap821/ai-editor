# RESUME MANIFEST

Last updated: 2026-07-02T13:50Z

## Current Goal
Wonder epoch, opened under discipline: ratified design → plan → W1 built. The
cortex bus is the cold-path observation tier the wonder organs will need;
built and proven BEFORE any organ is enabled.

## Last Completed + Verified
- CORTEX BUS W1 SUBSTRATE (`1a63752`, local): durable SQLite outbox in
  aios/runtime/cortex_bus.py. append (durable→commit→wake-hint, fail-soft cap),
  dispatch_pending (append-order = per-entity order, mark-after-success =
  at-least-once idempotent replay), poll_once/hint_pending (dispatcher tick,
  lost-hint-safe), sweep (age-out + config-lowered reclaim; never sweeps
  pending). AIOS_CORTEX_BUS default OFF — zero producers/consumers, no behavior
  change. 13 TDD tests. TDD caught a real subtlety: append's fail-soft cap
  bounds COUNT, so sweep's real job is the TIME window (test corrected to prove
  it). Gate: exit 0, coverage 87.55% (branch), cortex_bus.py 95%.
  test_aliveness_defaults.py still green (nothing enabled).
- Process: brainstorming skill → 3 forks ratified (outbox+250ms/hint,
  per-entity signature, self-model as W2 observer) → writing-plans skill →
  inline TDD execution. Spec `2026-07-02-wonder-epoch-cortex-bus-design.md`,
  plan `2026-07-02-cortex-bus-w1.md`.

## Single Next Action
OPERATOR: (a) push decision on the W1 commit (held per your review preference),
and (b) go/no-go on W2 — the self-model rebuild moved off the hot path onto the
bus (its own review gate per the spec). W2 needs its own plan (writing-plans)
before build. Do NOT start W2 without a go.

## Open Approvals / Blockers
- W1 commit `1a63752` local, NOT pushed (awaiting operator).
- Earlier coverage-honesty commits + design/plan docs ARE pushed (origin at
  ffdebdd before W1). W1 sits on top locally.
- W3 (conformance guard: authority NEVER on the bus) is designed, not built —
  it lands with the W2 wiring, not before, since W1 has no producer to guard.
- .aios/state/DEEP_AUDIT_REMAINING_REPORT.md still has +48 pre-session
  uncommitted lines — operator to review/land.

## Wonder-Epoch Ledger (spec §4)
- W1 substrate — DONE (this session), default-off, reviewed-ready.
- W2 self-model observer — NEXT (separate plan + gate; acceptance = turn
  latency before/after + self-model fresh within ~1s).
- W3 authority-never-on-bus conformance guard — with W2.
- W4 facts-off-hot-path — optional, only if profiled.
- Phase-4 organs (council/autonomy/cloud burst) — each a SEPARATE later gate.

## Active Files
- aios/runtime/cortex_bus.py (NEW) · aios/config.py · tests/test_cortex_bus.py (NEW)
- docs/superpowers/specs/2026-07-02-wonder-epoch-cortex-bus-design.md
- docs/superpowers/plans/2026-07-02-cortex-bus-w1.md

## Notes Not Yet Promoted
- Gate discipline held all session: short OUT-OF-REPO --basetemp, explicit
  exit capture, never pipe pytest through tail.
- The cortex_bus is deliberately import-clean (only aios.config) so it never
  entangles the memory engine or the frozen spine.
