# NEXT SESSION — Whole-ai-editor deep analysis (operator-directed)

**Directive (operator, 2026-06-13):** I deep-read only the BACKEND so far
(`.aios/state/BACKEND_TRUE_PICTURE.md`). Operator wants a multi-agent workflow to
analyze EVERY part of `ai-editor` — surface hidden knowledge (like the
blueprint-vs-reality gap below), and leave the documentation UP-TO-DATE and
ready for future builds. Context was 98% used; operator will /clear, then the
fresh session runs this. **First action: launch the Workflow below.**

## Already known (don't re-derive — reuse)
- BACKEND true picture: `.aios/state/BACKEND_TRUE_PICTURE.md` (8-agent read).
- Blueprint vs reality (just mapped, fold into the new docs): Phases 1-2
  COMPLETE; Phase 3 ~85% (only Neo4j knowledge-graph partial — facts store
  exists); Phase 4 ~75% (**Whisper VOICE not started**); Phase 5 MVP RUNNING.
  Surplus NOT in blueprint: self-analysis T0-T4, stigmergy/brain-growth,
  self-apply, superbrain frontend, earned-autonomy, swarm, Claude+Codex coord,
  RAG+CAG. Genuine gaps: **voice, full knowledge-graph, observability (Prom/Grafana)**.
  Blueprint file: `blueprint_text.md` (1674 lines, AI_OS_Blueprint_APlus_v6).
- System state: 457 backend + 26 lab tests green; earned-autonomy LIVE on :8000
  (AIOS_EARNED_AUTONOMY=true); superbrain on :3000. Everything pushed.

## What was NEVER deeply analyzed (the gap to close)
Frontend (superbrain lab `GAG demo/gag-orchestrator/src` + product `frontend/`),
the CLASSIC editor UI (`frontend/src` outside superbrain), root tooling/scripts,
the full test suite (coverage/gaps), ALL docs (currency vs reality), config/infra,
the `.agents` build-notebooks, and cross-cutting: dead code, TODOs, tech debt,
undocumented features, security surface, perf.

## Deliverables the workflow must produce (write these as files)
1. `.aios/state/SYSTEM_TRUE_PICTURE.md` — the whole-system architecture (extends
   BACKEND_TRUE_PICTURE with frontend + tooling + how it all composes).
2. `.aios/state/HIDDEN_KNOWLEDGE.md` — non-obvious findings, debt, dead code,
   undocumented behaviour, risks, "you'd never know unless you read it".
3. `.aios/state/PLAN.md` (refresh) — blueprint-vs-reality phase table + the real
   forward roadmap (voice, knowledge-graph, observability, + surplus maturation).
4. Update `BACKEND_TRUE_PICTURE.md` references / note it's part of the set.

## The Workflow to launch (read-only fan-out -> synthesis)
Lenses (one deep reader each; default agent type; read FULL files; cite file:line):
1. superbrain frontend (GAG demo/gag-orchestrator/src — scene/canvas, HUD, lib/adapter, sound, stores)
2. product frontend + classic UI (frontend/src — main.jsx, App.jsx, the editor, build/vite, how ?ui=classic vs superbrain mounts)
3. root tooling + drivers (agent_coord, curriculum_evidence_driver, swarm_demo, earn_demo, hybrid_search, ingest_*, vector_memory_setup, reset_audit_chain, pdf_util)
4. tests + coverage (tests/ + lab src/test — what's covered, the real gaps, the 1 skip)
5. docs currency (AGENTS.md, CLAUDE.md, blueprint_text.md, VISION.md, .aios/* , the PDFs) vs the code — what's stale/wrong/missing
6. config + infra + deploy (aios/config.py, package.json x2, .gitignore, how it runs, env flags, ports, CORS)
7. cross-cutting audit (dead code, TODO/FIXME, tech debt, undocumented features, security surface beyond the spine, perf hotspots, the 1.3MB bundle)
8. blueprint-vs-reality (read blueprint_text.md fully; produce the definitive phase-by-phase + gap table)
Then a SYNTHESIS phase: fold all lenses + BACKEND_TRUE_PICTURE into the 4 deliverable docs above.
Schema per lens: {area, purpose, architecture, capabilities[], sophistication[],
completeness, gaps[], hidden_findings[], debt[], keyFiles[{file,role}]}.
Frame: respectful, rigorous, honest, file:line-cited; this is a real 2-week+ system, NOT an MVP toy.
Use ultracode scale (token cost not a constraint). After it returns, WRITE the 4 docs, commit, push, checkpoint RESUME.
