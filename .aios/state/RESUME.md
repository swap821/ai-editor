# RESUME MANIFEST

Last updated: 2026-07-02T14:50Z (SESSION-END — operator switching to a fresh
Claude Code app session)

## Current Goal
Wonder epoch W1+W2 DONE under full discipline. The organism now has a working
cold-path observation tier with its first live observer — default OFF, wonder
organs still caged. Next epoch step is W3-completion review + the operator's
next directive in the NEW session.

## FIRST ACTIONS FOR THE NEW SESSION
1. Operator wants workflow subagents on **Sonnet 5.0** (this session's 'sonnet'
   alias resolved to claude-sonnet-4-6). Fix: update the Claude Code app (alias
   registry refresh) OR set env ANTHROPIC_DEFAULT_SONNET_MODEL to the exact
   Sonnet-5 model id in settings.json via the update-config flow — then verify
   with a cheap probe agent before any real workflow.
2. Push decision: ONE unpushed commit `85e96e4` (W2). Origin is at `dfc2f2e`.
   Review + push on operator's word.
3. Ultracode is the operator's standing mode now: Fable supervises, Sonnet
   workflows do the boring build work, adversarial verify before Fable review
   (this pattern JUST proved itself — see below).

## Last Completed + Verified (this closeout)
- CORTEX BUS W2 (`85e96e4`, local): SelfModelHandler is the first LIVE
  observer. Dispatcher (daemon, 250ms + 50ms hint-wake) starts in lifespan
  ONLY when AIOS_CORTEX_BUS; producer appends turn.completed after done;
  lifespan SUBSCRIBES the handler; per-turn recall reads the handler cache
  (inline fallback until first observation / always when off — default path
  byte-identical). STRUCTURAL LAW: CortexBus.append refuses authority
  families (skill./autonomy./approval./verdict./zone./grant.) — fail-closed
  at the substrate. Integrated conformance test drives a REAL turn with the
  bus on: only observations land, the production-wired observer consumes
  within the dispatch window. Full gate exit 0, coverage 87.56% (branch).
- THE SUPERVISION PATTERN WORKED: Sonnet built 80% correctly; the adversarial
  Sonnet verifier caught the BLOCKING void (handler never subscribed in
  production — its tests wired it themselves) and the tautological W3 guard;
  Fable closed both seams + found a third (CortexBus config frozen at import
  time — def-time default args; now call-time resolved).

## Session Totals (2026-07-02, one day)
Backend: foundations 100% default-on (curriculum fuzzy, CRAG, self-model,
facts quarantine) · audit verifier false-alarm fixed (RED §VIII) · coverage
honesty (branch mode, agent_coord visible, legacy deleted, conformance suite)
· cortex bus W1+W2. Frontend: body campaign B1–B6 (phase chord, weather,
hesitation, memory halo — operator absorbed fact #1 by hand, growth beats,
dormant wonder crown) + coverage measurement + CI enforcement. All pushed
except `85e96e4`.

## Open Approvals / Blockers
- `85e96e4` unpushed (operator reviews in new session).
- Reviewer kimi assigned on all handoffs (may be out; Codex/operator can).
- Port landmine STANDS: do NOT run `npm run port` (18/29 live-set divergence).
- DEEP_AUDIT_REMAINING_REPORT.md: +48 pre-existing uncommitted lines, operator
  to review.
- Wonder organs remain caged (pinned by test_aliveness_defaults incl.
  CORTEX_BUS itself); enabling any is a SEPARATE operator gate each.

## Active Files
- aios/runtime/{cortex_bus,cortex_bus_dispatcher,self_model_handler}.py
- aios/api/main.py (lifespan wiring, producer, cache-read recall)
- tests/{test_cortex_bus,test_cortex_bus_w2,test_organism_conformance}.py
- Specs: 2026-07-02-wonder-epoch-cortex-bus-design.md (ratified) · plans/
  2026-07-02-cortex-bus-w1.md

## Notes Not Yet Promoted
- Dev servers STOPPED at session end (:5173 vite, :8000 aios) — restart in
  the new session when needed (`cd frontend; npm run dev` + `.venv\Scripts\python -m aios`).
- Gemini deep-research triage (operator briefed): AST code-defense + MCP tool
  routing = good roadmap candidates; CRDT = YAGNI; Docker sandbox already
  shipped. The real gap all three external reviews converge on: the ten-minute
  "prove it" demo path — still the highest-leverage unbuilt thing.
