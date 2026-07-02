# RESUME MANIFEST

Last updated: 2026-07-02T04:05Z

## Current Goal
Operator directive (2026-07-02): chemotaxis + reflex + emotion + narrative at
100% so the organism is ready for its WONDER phase. STATUS: the four
foundation layers are structurally complete and default-on — three verified
slices shipped this session, all UNCOMMITTED awaiting the operator's landing.

## Last Completed + Verified (this session, in order)
1. `curriculum-fuzzy-aliveness` (handoff 1c2ac940…): organic-prompt learning —
   deterministic fail-closed fuzzy curriculum matching, default on.
   Gate: exit 0, coverage 88.83%.
2. `layer-defaults-awaken` (handoff dced79a5…): CRAG local corrective recall +
   narrative self-model default ON; tests/test_aliveness_defaults.py pins
   foundations-awake AND wonder-organs-gated in both directions.
   Gate: exit 0, coverage 88.88%.
3. `facts-auto-extraction` (this handoff): supervised memory formation —
   deterministic extractor over OPERATOR statements only (questions never
   match; never file contents), capped 3/turn, proposals land in the NEW
   quarantined fact_proposals table (schema.sql; no recall path reads it),
   GET /api/v1/memory/facts/pending + approve/reject endpoints; approval
   promotes THROUGH the contradiction-aware add_fact. 17 new tests.
   Gate: exit 0, coverage 88.91%.

## Four-Layer Declaration (behavioral, default path, evidence-backed)
- CHEMOTAXIS 100%: alignment interpretation · CRAG corrective recall · typed
  SSE spine · router — all default-on.
- REFLEX 100%: approval gates · scope lock · verify + strength taxonomy ·
  hardened rollback · confidence pause — all default-on, spine frozen.
- EMOTION 100% structural: confidence gate (0.72) on the default path,
  calibrated by verified lessons/development/skills; reflect-on-failure on.
  Honest limit: reflection QUALITY is local-model-bound (7B) — anatomy done.
- NARRATIVE 100% structural: 4-layer memory · consolidation · compaction ·
  organic curriculum learning · self-model injection · supervised fact
  formation — all default-on, all human-gated where knowledge is minted.
- WONDER: deliberately caged (earned autonomy, council reasoning/origination,
  cloud burst, CRAG external arms) — pinned by the contract test.

## Single Next Action
OPERATOR: land the three slices (suggest one commit per slice, or one
"four-layer aliveness" commit). Then the wonder phase opens per fusion
roadmap §4: durable cortex bus design gate FIRST (needs sign-off), then
gated organs one at a time.

## Open Approvals / Blockers
- All three slices UNCOMMITTED (operator commits; trees hash-pinned via
  handoffs). Files: aios/config.py, aios/memory/{curriculum,facts,
  fact_extraction(NEW)}.py, aios/memory/schema.sql, aios/api/main.py,
  tests/{test_curriculum_fuzzy,test_aliveness_defaults,test_fact_extraction}.py (NEW).
- Reviewer assigned kimi on all three (Kimi may be out — Codex/operator review).
- Follow-up defects (reported, unfixed): env-coupled test_agent_coord handoff
  test; tree_snapshot PermissionError on OS-locked untracked files.

## Notes Not Yet Promoted
- Deferred seams (deliberate): facts.proposed SSE beat + approval UI (frontend,
  ships with the being's approval surface); /api/v1/chat pure-text path does
  not extract facts (only agentic generate); embedding-based fuzzy/extraction
  upgrades (lexical has no stemming).
- Gate discipline: short OUT-OF-REPO --basetemp; never pipe pytest through tail.
