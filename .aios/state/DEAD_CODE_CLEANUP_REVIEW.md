# Review — Dead-Code Cleanup (Codex)

**Reviewer:** Claude (read-only review-gate) · **Date:** 2026-07-01 · **Base:** master `d116434` + uncommitted working tree · **Snapshot:** `5e9c208d31c2…`

## Verdict: ✅ PASS — the removals are safe, tests are green, and a regression guard is in place.

Closes deep-audit findings **#1/#2/#3** (orphaned `swarm_conflict.py` 1220L, `swarm_parallel.py` 1053L, and the doubly-suspect `swarm_adaptive/scout` cluster) plus the `pheromones` / `policy/*` / `leases` dead-code candidates.

## What Codex removed (8 modules)
`aios/agents/swarm_adaptive.py`, `swarm_conflict.py`, `swarm_parallel.py`, `swarm_scout.py`, `aios/memory/pheromones.py`, `aios/policy/__init__.py`, `aios/policy/constitution.py`, `aios/policy/policy_evolution.py`, `aios/runtime/leases.py`.
**Preserved (correctly):** `aios/agents/swarm.py` (the shipped swarm path) + `aios/agents/swarm_patterns.py`.

## Independent verification (not taken on trust)
1. **No lingering references — static.** Grepped the whole repo (py+json+yml+md+cfg) for every deleted basename. **Zero references in `aios/` product code.** All hits are docs/state/roadmap/memory files (expected — history, not imports) and the new hygiene test.
2. **No lingering references — dynamic.** Grepped all `aios/**/*.py` for `importlib` / `__import__` / `import_module`. **No matches at all** — there is no dynamic-import path that a static grep could have missed. This was the #1 risk and it's clean.
3. **`tests/test_swarm.py` "scout" tests are safe.** `test_swarm_scout_recalls_pattern…` / `…falls_back_to_decomposer…` import only `from aios.agents.swarm import run_swarm` — they exercise scout *behavior inside the preserved `swarm.py`*, not the deleted `swarm_scout.py`. No orphaned import.
4. **Package imports cleanly.** `import aios.agents.swarm, swarm_patterns, runtime.snapshots, king_report, api.main` → OK.
5. **Full backend suite green (my run, not asserted):** **1391 passed, 1 skipped, 89% TOTAL coverage** in 160s. Matches Codex's reported 89.11%. No regression from the deletions.
6. **`tests/test_dead_code_hygiene.py`** is a sound guard: it fails if any of the 9 confirmed-orphaned paths quietly re-enters `aios/`, with a message that says "wire and test it, or keep it outside `aios/`." Good — prevents silent resurrection.
7. **`agentdb.rvf*` gitignored** — correct; that's ruflo's memory DB (my session's side-effect), must not be committed.

## Minor (not blocking — for you to sweep on commit)
- **`.coveragerc` is now stale.** Its `omit =` block (lines 4–9) still lists the 4 deleted swarm files with the comment *"include these in coverage when they are wired in."* They're gone, so the omit entries are dead config (coverage.py silently ignores non-existent paths — harmless, but should be pruned). Prune all four; the comment is moot.
- **Doc/roadmap staleness (informational, don't churn):** `GAGOS_FINAL_ROADMAP_council.md:29` still calls `swarm_conflict.py` "real", and `docs/superpowers/specs/2026-06-27-sovereign-ai-os-roadmap.md` lists `pheromones.py`/`policy/*` as target paths. These are aspirational/historical docs — the hygiene test's message ("keep it outside `aios/`") already captures the intent, so no urgent fix, but worth a note if those specs get revived.

## Bottom line
Clean, well-guarded deletion of ~4.5k lines of never-imported research code. Safe to commit. Recommend folding the `.coveragerc` prune into the same commit so the omit block doesn't outlive the files it names.

— Claude (read-only; tree is yours)
