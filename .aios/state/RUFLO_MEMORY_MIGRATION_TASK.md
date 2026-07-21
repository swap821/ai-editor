# Task → Codex — Complete the ruflo memory migration (to ~100%)

**From:** Claude · **Date:** 2026-07-01 · **Type:** mechanical transcription (NOT curation)
**Why:** operator asked for the full 1-month+ memory AND each workflow in ruflo. Claude only did a partial ~17-key thematic consolidation (substance ~70-80%, not 1:1, workflows not individual). Finish it.

## Source (read-only)
Claude's memory files — plain markdown on disk:
```
C:\Users\kumar\.claude\projects\C--Users-kumar-ai-editor\memory\*.md
```
`MEMORY.md` in that dir is the INDEX (one line per memory). There are ~38 memory files.

## What to do
For **every** `*.md` file in that dir (except `MEMORY.md` itself):
1. Read it.
2. `mcp__claude-flow__memory_store` into namespace **`gagos`**, key **`gagos-mem-<slug>`** (slug = the file's `name:` frontmatter, e.g. `gagos-mem-stigmergy-direction`), value = the file's body **verbatim**, `upsert: true`, tags `["memory-migration", "<metadata.type>"]`.
3. Preserve the file's own dates and wording. **Do NOT re-judge currency, "fix", or summarize** — a memory is a point-in-time record. Copy it faithfully.

For **workflows**, also store one key each (`gagos-workflow-<name>`) for the runnable/resumable workflows named inside the memories — at minimum:
- the **paused deep-audit** workflows + their `resumeFromRunId` values (see `deep-audit-paused.md` + `workflow-limit-recovery.md`),
- the **7-layer polish audit** run `wf_18b3419d-2ff` (see `alive-being-build-progress.md`),
- the recipes in `workflow-recipes` (already partly in `gagos-workflow-recipes`).

## Rules
- Faithful transcription only. If a workflow ID or detail is referenced but its specifics are NOT on disk (exist only in a Claude transcript), **flag it as a gap in your handoff — do not invent it.**
- This is memory-only work: no product code, no commits needed. It writes to ruflo (`.swarm`/agentdb), not the git tree.
- Use `upsert` so re-runs are idempotent; don't duplicate the 17 thematic keys already present (list them via `memory_list namespace=gagos` first) — the per-file `gagos-mem-*` keys are additive granularity alongside them.

## Done / verify
- `mcp__claude-flow__memory_list namespace=gagos` shows ~1 `gagos-mem-*` key per memory file + the `gagos-workflow-*` keys (≈55+ total).
- Report the final count and any flagged gaps back to the operator (and Claude for spot-review next session).
