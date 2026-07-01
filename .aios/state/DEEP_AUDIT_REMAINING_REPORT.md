# Deep Audit — Remaining Dimensions (run on cloud 32B via ruflo)

**Date:** 2026-07-01
**How:** the two thematic dimensions killed by the earlier session-limit (**architecture**, **tests**) were run on **qwen2.5-coder:32b** hosted on a GCP L4 VM (`gagos-ollama-l4`, us-central1-a), driven through **ruflo `agent_execute`** (via SSH tunnel `:11435`). Claude did only file-glue (gathering the real code signal); **all analysis reasoning ran on the operator's 32B / credits — zero Claude reasoning tokens.**
**Baseline:** master `c154d6b`. Merge with the 17 prior thematic findings; Codex already fixed #1/#2/#3/#9/#13/#14.

## Architecture dimension (32B findings)
1. **[HIGH] Orphaned code — `aios/agents/swarm_conflict.py`** (1220 lines): zero imports anywhere in `aios/`. Large yet unused → dead code. **Fix:** confirm unused, then remove/archive (or wire it in if intended).
2. **[HIGH] Orphaned code — `aios/agents/swarm_parallel.py`** (1053 lines): zero imports; same as above.
3. **[MEDIUM] Monolith — `aios/api/main.py`** (3761 lines): doing far too much. **Fix:** split into routers/modules (auth, council, generate/chat, memory-recall, etc.).
   - *(also unimported per the glue scan: `swarm_adaptive.py`, `swarm_scout.py`, `memory/pheromones.py`, `policy/constitution.py`, `policy/policy_evolution.py`, `runtime/leases.py` — dead-code candidates to confirm/remove.)*

## Tests dimension (32B findings)
1. **[HIGH] `aios/agents/rollback_engine.py` has no tests** — and it's the recoverability code behind the confirmed **rollback theater** (audit #7: `rollback_id` never populated). Untested + likely-broken recovery path. **Fix:** test it AND wire it to the Council worker.
2. **[MEDIUM] `aios/agents/self_analysis_agent.py` (754 lines) has no direct test** — large logic module, unverified.
3. **[MEDIUM] Orphaned + untested `swarm_adaptive/conflict/parallel/patterns/scout.py`** — doubly suspect (unimported *and* untested): **test or delete.**
4. **[LOW] Untested (but imported) modules:** `reflection_agent.py`, `tool_handlers.py`, `confidence_filter.py`, `queen_verdict.py`, `consolidation.py`, `conversation.py`. *(Correction to the 32B's wording: these are imported/live, just lacking direct test files — not orphaned.)*

## Honest scope notes
- The **per-file (402 files) + cross-seam + completeness-critic** pass was NOT run here: at the 32B's ~12 tok/s, a 402-file crawl would take hours and burn credits. Recommend running it **selectively** on the highest-risk files, or via a cheaper/faster route.
- 32B findings are grounded in real glue data (import scan, line counts, test-file matching), so they're reliable; one wording over-generalization corrected above.

## Convergence with prior findings
- **swarm_*** show up in BOTH architecture (orphaned) and tests (untested) → strong signal: these large files are dead weight; decide keep-and-wire-and-test vs delete.
- **rollback_engine** untested + rollback theater (#7) → the single most actionable v1.0-stability gap: recovery is claimed but neither wired nor tested.

## Provenance
Cloud 32B via ruflo proven operational this session (`agent_execute` → `RUFLO_CLOUD_32B_OK`). Setup + management commands in ruflo memory (`gagos-cloud-gpu`).
