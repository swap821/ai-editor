<!-- ============================================================= -->
<!-- 2026-07-02 ADDENDUM appended below the original 2026-07-01 run -->
<!-- (per doc-currency convention: add, never rewrite dated evidence) -->
<!-- Jump to the addendum: search "PER-FILE + CROSS-SEAM PASS"       -->
<!-- ============================================================= -->

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

---

# PER-FILE + CROSS-SEAM PASS (2026-07-02 addendum)

**Date:** 2026-07-02
**Baseline:** master `629d373`.
**How:** the last two un-run parts of the exhaustive audit — the **per-file crawl** (all 82 `aios/**/*.py`, risk-ranked) and the **cross-seam pass** (8 subsystem boundaries) — were run on **qwen2.5-coder:32b** on the operator's GCP L4 VM (`gagos-ollama-l4`, recreated in **us-central1-c** after us-central1-a/b stocked out), driven through the SSH tunnel `:11435`. Claude did only file-glue + the final human review-gate; **all analysis reasoning ran on the operator's 32B / credits.** Pipeline: per-file review → seam review → 1-vote adversarial refutation → neutral tiebreak on every disputed CRITICAL/HIGH/seam finding → completeness critic → **Claude reads the actual code for every survivor.**

## Result: 0 real new defects at per-file/seam depth

| Stage | Count |
|---|---|
| Files audited (per-file) | 82 / 82 |
| Seams audited | 8 / 8 |
| Raw findings (per-file 115 + seam 23) | 138 |
| Survived 32B adversarial refutation | 0 as REAL; 5 CRITICAL kept only as "disputed" |
| Survived 32B neutral tiebreak (judge sided with finder) | 5 |
| **Survived Claude's code-grounded review-gate** | **0** |

**All 5 tiebreak-upheld "CRITICAL" findings are false positives** when read against the real code + system design:

1. `memory/semantic.py:132` "data loss on persist failure" — **REFUTED.** The `DELETE` at line 138 is a deliberate *compensating* action (comment explains it): a failed vector persist removes the just-inserted DB row to prevent durable DB/index drift. That IS the rollback, not a loss. Consistent with prior note obs#6034 (double-lock intentional).
2. `agents/tool_agent.py:1148` "command injection in `_execute`" — **REFUTED.** `execute_terminal` running a terminal command is the worker's *intended* execution surface, gated by the caste `allowed_tools` check (line 1132) and the frozen-RED security gateway/scope-lock in `tool_handlers`. The 32B saw `tool_agent.py` in isolation and mistook the designed, guarded exec path for an injection. (Matches obs#796 "tool agent loop is fully gated".)
3. `core/failover.py:63` "`_is_cloud_provider` false positives" — **REFUTED.** The substring OR-check is *fail-safe*: an ambiguous name classified as cloud triggers MORE privacy protection, never less. The tiebreak judge even misdescribed the code ("any character" — it iterates provider *strings*).
4. `core/model_selector.py:170` "`installed: object` type hint" — **REFUTED.** Pure style nit (explicitly excluded by the audit prompt); the code defensively filters non-strings via `isinstance(m, str)`.
5. `memory/retrieval.py:147-165` "errors indistinguishable from empty" — **REFUTED.** The `[]` returns (lines 102/112/127) are all genuinely-empty cases; a real DB/embedder error *raises* (no swallowing try/except). Premise is factually wrong.

## Seams checked (contract audit)
api-council-origination · council-worker-birth · worker-rollback-snapshots · sse-event-spine · router-providers-privacy · memory-retrieval-generate · security-gate-executors · session-approvals-api — **no confirmed cross-boundary defect survived review.**

## The real, honest finding: the 32B is a weak reviewer
The headline is not "0 bugs" — it is **calibration**: a per-file + seam + adversarial-verify + neutral-tiebreak pipeline run *entirely on the 32B* still surfaced **138 raw → 5 "upheld critical" → 0 real**. Every survivor died on contact with the actual code + the system's security design (gateway, caste gate, compensating writes) that a single-file-context model cannot see. Two structural limits confirmed:
- **False positives leak** even through self-adversarial verification when refuter + judge are the *same* weak model (it rubber-stamps its own plausible-but-wrong claims). The human review-gate was load-bearing.
- **False negatives too:** this run did NOT resurface the known-real `retrieval.py` timestamp-parse recency bug (obs#5820/#5785) — so the 32B misses genuine defects while inventing fake ones.
- **Method blind spot:** the seam pass used grep-windowed excerpts, so defects spanning >2 files or requiring runtime-state understanding are structurally invisible to this method.

## Convergence
Consistent with the paused thematic deep-audit (**no critical/high confirmed**, obs "Deep-audit PAUSED") and the prior 32B thematic run (dead code already removed; rollback wired). **At per-file + seam depth, the `aios` backend has no confirmed new defect.** The actionable debt remains what was already known and tracked: `api/main.py` monolith → router split (plan item B); `queen_verdict.py`/`tool_handlers.py` lack direct tests (plan item D).

## Provenance
Raw artifacts (gitignored `.aios/tmp/`): `audit_inventory.json`, `audit_perfile_findings.jsonl`, `audit_seam_findings.jsonl`, `audit_verified.jsonl`, `audit_second_opinion.jsonl`, `audit_critic.json`. Drivers: `audit_driver.py`, `seam_driver.py`, `verify_driver.py`, `second_opinion.py`, `critic_driver.py`. VM stopped post-run (credit guard).

---

# FINDINGS-REVIEW CLOSEOUT (2026-07-06 addendum)

**Date:** 2026-07-06 · **Baseline:** master `63797ff` · **How:** every held finding re-verified against the CURRENT tree by an 18-agent workflow (9 mechanical verifiers + 9 adversarial refuters re-checking each verdict's cited evidence in both directions). Operator directive: review, then fix whatever survived as open.

## Disposition of all held findings

| Finding | Verdict | Evidence anchor |
|---|---|---|
| swarm_conflict.py / swarm_parallel.py / swarm_adaptive.py / swarm_scout.py orphaned | **FIXED** | deleted in `d151fc0` (2026-07-01) with regression guard `tests/test_dead_code_hygiene.py` |
| policy/constitution.py, policy/policy_evolution.py, runtime/leases.py orphaned | **FIXED** | same commit + same regression guard |
| swarm_patterns.py dead-code candidate | **STALE** | live production import (swarm.py:34, main.py:52) + real multi-file test coverage — do not delete |
| memory/pheromones.py dead-code candidate | **STALE** | 4 live route imports in sovereignty.py; flag-gated (`AIOS_PHEROMONE_ENABLED`), not orphaned |
| rollback_engine.py untested + "rollback theater" (rollback_id never populated) | **FIXED** | direct tests exist; rollback_id wired through the council worker path |
| self_analysis_agent.py untested | **FIXED** | direct tests; 91% coverage in current CI table |
| retrieval.py timestamp-parse recency bug (obs#5820) | **FIXED** | recency parse verified correct on current code |
| consolidation.py / conversation.py untested | **FIXED** | direct coverage landed in the coverage arc |
| reflection_agent / tool_handlers / confidence_filter "no direct test file" | **NAMING NIT** | real direct coverage exists under differently-named files (test_reflection.py, test_agents_pkg_gaps.py §567+, test_confidence.py) — no functional gap |
| **queen_verdict.py zero test references** | **WAS OPEN → FIXED 2026-07-06** | `tests/test_queen_verdict.py` added (16 tests): fail-closed unknown-risk→RED, deny/defer blocking, metadata shape/isolation/JSON-safety |
| **main.py monolith** | **MAJOR TRANCHE LANDED 2026-07-06 (same day, operator "Proceed")** | Router-extraction arc executed: NEW `aios/api/deps.py` (21 stateless providers, kills the council-style dependency-override proxy trap by construction) + 3 new routers — `routes/memory.py` (16), `routes/development.py` (12), `routes/models.py` (4). main.py 4,252 → ~3,350 lines; 54 → 22 inline routes. Byte-equivalent moves, 88/88 routes accounted, override identity preserved — adversarially reviewed (3 lenses, all clean). REMAINING for a future pass: the generate/chat/terminal giants + approvals/security/reflect/plan/execute/self-analysis/auth/onboarding/intent groups (entangled with main-owned process singletons) |

## Residual items from the ORIGINAL 17 thematic findings (memory-tracked, not in this report's dimensions) — also closed 2026-07-06

| # | Finding | Disposition |
|---|---|---|
| 5 | `websearch.py` egress scrubs secrets but NOT file paths | **FIXED**: outbound query now runs `privacy_filter.redact_paths()` after secret scrubbing (+ egress test capturing the wire payload) |
| 6 | worker `run_command` no gateway re-check at exec boundary | **FIXED**: hostile-content RED classes (destructive/network/env-mutation/injection/credentials/shell-escape) re-checked fail-closed at the exec boundary; chat-context stages (SCOPE_ROOTS, auto-execute allowlist) deliberately out of jurisdiction — the worker's workspace+container+contract allowlist owns containment there (2 new tests: `rm -rf /` and `curl` exfil blocked even when contract-declared) |
| 10 | verify-toast `setTimeout` leak (`GagosChrome.jsx`) | **ALREADY FIXED** on current master (cleanup handlers present at the toast effect) |
| 4 | `.venv` broken cp314 extensions | **MOOT**: system Python canonical since 2026-07-02; env refreshed 2026-07-06 |
| 16/17 | stale merged branch + redundant worktrees | **FIXED**: `council-runtime-v01` + 4 stale branches deleted, 4 stale worktrees removed (dirty ones inspected first — stale June-2 styling edits to the pre-superbrain App.jsx, zero value). Bonus recovered: unmerged `22833e8` (Windows MAX_PATH conftest fix, 28→9 failures in deep worktrees) cherry-picked to master before its branch was deleted |

## Net position
After adversarial re-verification, the deep audit closes with **one** surviving item (the monolith split — tracked, scoped, awaiting a dedicated arc) and zero untracked debt. The 32B-era findings are fully dispositioned; the dead-code regression guard makes the biggest class (orphan reintroduction) structurally impossible to regress silently.
