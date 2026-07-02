# RESUME MANIFEST

Last updated: 2026-07-02T18:25Z (W3 shipped — wonder-epoch cortex-bus design
doc COMPLETE; CI healed twice this session)

## Current Goal
The wonder epoch's enabling infrastructure is DONE: W1 (durable bus) + W2
(first live observer + structural authority gate) + W3 (permanent conformance
guard) are all green, reviewed, and pushed. The bus is default OFF and every
wonder organ remains caged. The next move is the operator's: either a wonder
organ's own gate (council triggers first, per the roadmap) or the standing
highest-leverage alternative — the ten-minute "prove it" demo path.

## FIRST ACTIONS FOR THE NEW SESSION
1. Nothing is blocked. Master == origin, CI green end to end.
2. Offer the operator the fork: wonder-organ gate (council deliberation
   triggers, its own design+approval cycle) vs the "prove it" demo path
   (external reviews' convergent gap). Do NOT enable any wonder flag without
   a per-organ operator decision.
3. Sonnet-5 alias: RESOLVED — probe-verified `sonnet` → claude-sonnet-5
   (2026-07-02). Workflows are correctly armed; no env override needed.

## Last Completed + Verified (this session)
- PUSHED W2 (`85e96e4` + `1f6a662`) on operator's word.
- CI HEALED #1 (`c69492d`): master had been red since 09:39Z — e8de86b added
  tests/test_audit_recovery.py (real Ed25519 signing tests) but `cryptography`
  was never in requirements.txt (local venv only), and the breaking commit's
  own CI run was CANCELLED so the gap surfaced under a docs commit. Fix:
  declare cryptography==49.0.0 (NOT skip the tests — signing is a shipped
  feature; CI now tests it armed). Verified green: run 28601126357.
- Dependabot red rows in Actions = historical residue: the failing update
  jobs targeted /legacy/legacy_node which was already deleted from master;
  open alerts now 0 (auto-resolved). Nothing recurs, nothing to do.
- W3 (`8864501`): test_skill_promotion_is_synchronous_and_never_rides_the_bus
  in tests/test_organism_conformance.py — three real STRONG-verified turns,
  bus ON, dispatcher neutered for causal isolation; skill 'verified'
  synchronously while all three observations sit undrained; outbox
  observation-only. Non-tautology proven by FIVE mutation red-proofs (builder
  M1-M3 + two independent adversarial mutations) — every one turned the guard
  red at the assertion naming the broken invariant. Full gate exit 0 @ 87.59%.
- Supervision pattern (2nd run): Sonnet builder + adversarial Sonnet verifier
  (CONFIRMED, zero harness intrusion) + Fable seam-close (docstring). The
  gate agent died on the 5hr session limit — Fable ran the full gate itself
  via Bash instead of resuming (no agents needed for pytest). Worker model
  probe-verified claude-sonnet-5 in the transcripts (48/48 calls).

## Open Approvals / Blockers
- None blocking. Wonder organs caged (pinned by test_aliveness_defaults.py);
  each needs its own operator gate.
- Port landmine STANDS: do NOT run `npm run port`.
- DEEP_AUDIT_REMAINING_REPORT.md: +48 pre-existing uncommitted lines,
  operator to review.
- Repo-root junk for operator triage: `'pointfield_v19'`, `'pointfield_v20'`
  (literal quotes in the filenames) + large untracked `.agents/skills/` tree.

## Active Files
- tests/test_organism_conformance.py (W3 guard lives here)
- aios/runtime/{cortex_bus,cortex_bus_dispatcher,self_model_handler}.py
- Spec: docs/superpowers/specs/2026-07-02-wonder-epoch-cortex-bus-design.md
  (§7 updated: W1–W3 shipped, epoch definition-of-done met)

## Notes Not Yet Promoted
- Dev servers still stopped (:5173 vite, :8000 aios) — restart when needed.
- Gemini deep-research triage stands: AST code-defense + MCP tool routing =
  good roadmap candidates; CRDT = YAGNI. The ten-minute "prove it" demo path
  remains the highest-leverage unbuilt thing per all three external reviews.
