# Staleness & Drift — Time/Environment-Based Re-Verification Design

Date: 2026-07-06
Status: Design approved for v1.0 (implementation post-v1.0)
Builds on: cerebellum decompile-on-replay-failure (`aios/core/cerebellum.py`),
skill-trail decay ranking (`aios/memory/skills.py`), the facts quarantine ladder
(`aios/memory/facts.py`), verification-strength floors.

## The open problem

"Verified" is a **timestamped** claim, not a permanent one. A playbook compiled
in June replays commands whose world may have moved by August: dependencies
bumped, files renamed, Python upgraded, the OS changed. Verified facts age the
same way. Today the system handles drift **reactively and partially**:

- Cerebellum: 2 consecutive replay failures → decompiled. Correct, but the
  damage (one or two hollow replays) has already happened.
- Skill trails: decay-weighted *ranking* (stale trails rank lower) — retrieval
  freshness, not verification freshness. A stale trail can still be walked.
- Facts: contradiction detection fires only when a *conflicting* fact arrives;
  a fact the world quietly invalidated stays active forever.

The gap: nothing re-verifies on a clock or on an environment change. This design
closes it with three mechanisms, all reusing existing machinery.

## Mechanism 1 — freshness windows (`verified_at` horizons)

Every trusted artifact gets (or already has) a `verified_at` timestamp refreshed
on each verified success. A per-class window makes trust expire into *probation*,
never silently:

| Class | Proposed window | Past the window → |
|---|---|---|
| Compiled playbooks | 14 days since last verified replay | probation replay (Mechanism 2) |
| Verified skills | 30 days since last verified success | recalled with a staleness note; next verified use refreshes |
| L3 verified facts | 45 days since verification | status → `aging`: recalled at reduced confidence, queued for operator re-confirmation |
| Verified lessons | none (lessons state past failures — they do not decay) | — |

Windows are config (`AIOS_FRESHNESS_*`), operator-tunable, with the defaults
above. Expiry NEVER deletes: it demotes trust and routes to re-verification.
The quarantine-ladder shape is reused — an aging fact re-enters the same
pending/approve surface the operator already knows.

## Mechanism 2 — re-verify-on-use (probation replay)

When the cerebellum matches a playbook that is past its window, it replays in
**probation mode** instead of blind reflex:

1. Replay the steps as normal (same gateway, same audit) — the playbook's own
   `verify` steps are already part of the compiled sequence.
2. Require a strength-floor pass from those verify steps *this replay*.
3. Pass → refresh `verified_at`; the reflex is re-earned at the cost the replay
   was already paying (no extra work on the happy path).
4. Fail → decompile **immediately** (skip the wait for a 2nd consecutive
   failure — a stale artifact that fails probation has no benefit of the doubt).

The UI distinction is honest and cheap: probation replays emit the existing
`cerebellum_*` events plus a `probation: true` field, so the body can render a
"checking its muscle memory" variant of the reflex phase.

## Mechanism 3 — environment fingerprint (drift without a clock)

Time is a proxy; the real invalidator is environment change. At compile/verify
time, stamp artifacts with a fingerprint: hash of (Python `major.minor`, OS,
the requirements lockfile digest). At match/recall time, compare against the
current fingerprint — a mismatch marks the artifact stale **immediately**,
regardless of age, routing it to Mechanism 2. The check is one string compare;
the fingerprint is computed once per process start.

Dependency bumps (a routine event in this repo — see the dependabot cadence)
thus trigger probation exactly when they should, instead of waiting for a
replay to fail in production use.

## What is deliberately reused (no new trust machinery)

- Probation failure paths call the existing `invalidate_for_skill` /
  decompile machinery — no second demotion system.
- Aging facts ride the existing proposal/approval surface — the operator
  re-confirms in the same place facts were born.
- Strength floors gate probation passes exactly as they gate promotions —
  a WEAK green cannot refresh trust any more than it could mint it.
- Trail decay ranking stays as-is (retrieval-side); this design adds the
  verification-side counterpart, not a replacement.

## Sequencing & scope

- **v1.0 ships this design** plus the already-live reactive demotion; that is
  the honest claim the README makes ("mitigated, not solved").
- Implementation order post-v1.0: fingerprint stamp (cheapest, highest value)
  → playbook probation → fact aging windows. Each is a small, separately
  testable slice touching `cerebellum.py`, `skills.py`, `facts.py`, `config.py`.
- Out of scope: web-content freshness (Product Phase P4 inherits this design's
  vocabulary — freshness windows + re-verify-on-use — when it arrives), and any
  change to the RED frozen security spine.

## Verification plan (for the implementation slices)

Unit: window expiry math, fingerprint mismatch detection, probation
pass-refreshes / fail-decompiles (fakes for clock + fingerprint). Integration:
a compiled playbook with a back-dated `verified_at` must replay in probation and
refresh on pass; the same playbook with a broken fixture must decompile on the
FIRST probation failure. The learning-loop prover gains an optional staleness
phase (back-date via test hook, assert probation events) once the mechanisms land.
