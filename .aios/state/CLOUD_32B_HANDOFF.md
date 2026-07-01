# Cloud 32B via ruflo — Handoff to Codex

**From:** Claude · **Date:** 2026-07-01 · **State:** VM stopped, ready for on-demand use.

A GCP L4 GPU runs `qwen2.5-coder:32b` and ruflo can drive it — so orchestration/analysis runs on the operator's credits, **not** on any single model's session budget. Proven working this session (`agent_execute → RUFLO_CLOUD_32B_OK`).

## Facts
- VM `gagos-ollama-l4`, **zone `us-central1-a`**, project `ai-editor-498414`. g2-standard-8 + 1× L4 (24GB). Model `qwen2.5-coder:32b` (~12 tok/s). **Currently STOPPED.**
- `.mcp.json` already wires ruflo → `OLLAMA_BASE_URL=http://localhost:11435`, `RUFLO_PROVIDER=ollama`. (Loads on MCP-daemon restart.)
- Cost guard installed: `/etc/cron.d/idle-shutdown` auto-powers-off after 30 min idle.

## Use it (in order)
```bash
# 1. start (if stocked out here, sweep zones + recreate — GPU disks can't move zones)
gcloud compute instances start gagos-ollama-l4 --zone=us-central1-a --project=ai-editor-498414
# 2. tunnel (Ollama is localhost-only; keep this process alive)
gcloud compute ssh gagos-ollama-l4 --zone=us-central1-a --project=ai-editor-498414 --strict-host-key-checking=no -- -L 11435:localhost:11434 -N &
# 3. PRE-WARM (agent_execute has a 60s cap; cold-load of 19GB exceeds it)
curl -s http://localhost:11435/api/generate -d '{"model":"claude-sonnet-4-6","keep_alive":"30m","stream":false,"options":{"num_predict":3},"prompt":"ok"}'
# 4. now ruflo agent_spawn(model=sonnet) + agent_execute() run on the 32B
# 5. STOP when done (protect credits)
gcloud compute instances stop gagos-ollama-l4 --zone=us-central1-a --project=ai-editor-498414
```

## Two non-obvious gotchas (both already applied, persist on disk)
1. **Model aliasing:** ruflo passes *Claude* model IDs even to Ollama → 404. Aliases created via `ollama cp qwen2.5-coder:32b claude-sonnet-4-6` (+ `claude-haiku-4-5-20251001`, `claude-opus-4-8`). Persist across stop/start. Spawn agents with `model=sonnet`/`inherit`.
2. **Pre-warm** before `agent_execute` (step 3 above), else 60s timeout.

## Audit findings to act on (from the 32B run)
Full report: `.aios/state/DEEP_AUDIT_REMAINING_REPORT.md`. Top items:
- **[HIGH]** `aios/agents/rollback_engine.py` untested + rollback theater (audit #7: `rollback_id` never wired to the Council worker) — the #1 v1.0-stability gap.
- **[HIGH]** `swarm_conflict.py` (1220L) + `swarm_parallel.py` (1053L) orphaned/unimported dead code (+ swarm_adaptive/scout, pheromones, policy/*). Test-or-delete.
- **[MED]** `aios/api/main.py` 3761-line monolith → split.
- Not run: the 402-file per-file/seam crawl (impractical at ~12 tok/s — do selectively).

## Shared memory (query it)
ruflo `gagos` namespace: `gagos-cloud-gpu` (this setup), `gagos-audit-remaining-done` (findings), `gagos-workflow-recipes`, `gagos-architecture/frontend-laws/operator-profile/process-conventions/…`.

— Claude handing the tree back; I'm read-only from here (one writer per tree).
