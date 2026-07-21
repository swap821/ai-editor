# .aios/state/ — Index

This directory is a flat, undated pile of ~80 planning docs, audit reports,
and design proposals accumulated over the project's history. Filenames carry
no date or "superseded" marker, so there was previously no structural way
to tell which of several plausibly-competing docs on the same topic (e.g.
the GAGOS_* or FRONTEND_* clusters below) is current.

**This index does not judge content currency** — that requires actually
reading each file, which is a separate, ongoing exercise (see the
doc-currency convention: refresh Tier-1 docs after a feature, add a
"superseded by X" banner at the top of a doc when you know it's stale,
never silently rewrite dated evidence). What this index DOES give you is an
objective, verifiable signal — each file's last-commit date — sorted so a
reader can at least triage "newest first" before opening anything, plus a
grouping by naming cluster so competing docs on the same topic are visible
side by side.

**Rule going forward:** when you write a new planning/audit doc into this
directory, add its row to the table below (date + one-line purpose). When a
doc is superseded, add a `> SUPERSEDED by X.md (YYYY-MM-DD)` banner as the
very first line of the old file — don't delete it (it's dated evidence) and
don't silently leave it looking current.

## Newest first (by last git commit touching the file)

| Date | File | Cluster |
|---|---|---|
| 2026-07-10 | FULL_GREEN_AUDIT.md | audit |
| 2026-07-09 | AUDIT.md | audit |
| 2026-07-09 | GAGOS_ULTRA_PLAN.md | GAGOS plan |
| 2026-07-09 | RESUME.md | session-continuity |
| 2026-07-09 | SYSTEM_TRUE_PICTURE.md | true-picture |
| 2026-07-09 | V10_INTEGRATION_AUDIT.md | V10 |
| 2026-07-09 | V10_INTEGRATION_PLAN.md | V10 |
| 2026-07-08 | GAGOS_REMAINING_INVENTORY.md | GAGOS plan |
| 2026-07-08 | PLAN.md | plan |
| 2026-07-08 | V7_INTEGRATION_AUDIT.md | V7 |
| 2026-07-08 | V7_INTEGRATION_PLAN.md | V7 |
| 2026-07-07 | LAB_SYNC_2026-07-06.md | lab-sync |
| 2026-07-06 | CEO_LOG.md | CEO log (append-only, always current) |
| 2026-07-06 | CODEX_KEEPERS_HANDOFF.md | handoff |
| 2026-07-06 | DEEP_AUDIT_REMAINING_REPORT.md | audit |
| 2026-07-06 | GAGOS_ARCHITECTURE.md | GAGOS plan |
| 2026-07-06 | GAGOS_ORGANISM_FREEDOM_RECOMMENDATIONS.md | GAGOS plan |
| 2026-07-06 | RUFLO_MEMORY_MIGRATION_TASK.md | ruflo |
| 2026-07-06 | V1_LOOP_LOG.md | V1 loop |
| 2026-07-03 | FRONTEND_BEAUTIFICATION_BLUEPRINT.md | frontend plan |
| 2026-07-01 | BIRTH_PROOF_RESPONSE_2026-07-01.md | birth-proof |
| 2026-07-01 | BIRTH_PROOF_REVIEW_2026-06-30.md | birth-proof |
| 2026-07-01 | CLOUD_32B_HANDOFF.md | handoff |
| 2026-07-01 | CODEX_FUSION_HANDOFF.md | handoff |
| 2026-07-01 | DEAD_CODE_CLEANUP_REVIEW.md | audit |
| 2026-07-01 | FRONTEND_HEALTH.json | frontend plan (data) |
| 2026-07-01 | ROLLBACK_HARDENING_REVIEW.md | audit |
| 2026-06-30 | RENOVATION_PLAN.md | renovation |
| 2026-06-27 | FUTURE_FRONTIER.md | future-frontier |
| 2026-06-25 | ARCHITECT_REVIEW_2026-06-14.md | audit |
| 2026-06-25 | BACKEND_TRUE_PICTURE.md | true-picture |
| 2026-06-25 | FRONTEND_HARMONY_MAP.md | frontend plan |
| 2026-06-25 | FRONTEND_RENOVATION_BLUEPRINT.md | frontend plan |
| 2026-06-25 | HIDDEN_KNOWLEDGE.md | hidden-knowledge |
| 2026-06-25 | JARVIS_VOICE_PLAN.md | voice |
| 2026-06-24 | SWARM_FUSE_WOW_SPEC.md | swarm |
| 2026-06-23 | GAGOS_POSTER_GAP_AUDIT.md | GAGOS plan |
| 2026-06-23 | MOTION_WOW_PLAN.md | motion |
| 2026-06-23 | PERF_BUDGET.md | perf |
| 2026-06-23 | PROOF_SWEEP.md | proof |
| 2026-06-22 | GAGOS_POLISH_FINDINGS.json | GAGOS plan (data) |
| 2026-06-22 | GAGOS_RTX_DOSSIER.md | GAGOS plan |
| 2026-06-22 | GAGOS_WEBGPU_PORT_MAP.json | webgpu (shelved) |
| 2026-06-22 | GAGOS_WEBGPU_SPIKE.md | webgpu (shelved) |
| 2026-06-22 | HUD_REFERENCE_LANGUAGE.md | HUD |
| 2026-06-22 | HUD_RENOVATION_SPEC.md | HUD |
| 2026-06-22 | NEXT_ANALYSIS.md | analysis |
| 2026-06-22 | RENOVATION_RESUME.md | renovation |
| 2026-06-22 | RENOVATION_REVIEW.md | renovation |
| 2026-06-21 | GAGOS_RENOVATION_NORTHSTAR.md | GAGOS plan |
| 2026-06-19 | ALIVE_BRAIN_MASTER_PLAN.md | alive-brain |
| 2026-06-19 | ATMOSPHERE_MEMORY_RESEARCH.md | research |
| 2026-06-19 | FORGE_RESEARCH.md | research |
| 2026-06-19 | NERVE_FORM_RESEARCH.md | research |
| 2026-06-19 | NERVOUS_SYSTEM_REIMAGINATION.md | nervous-system |
| 2026-06-19 | NODE_BRAIN_RESEARCH.md | research |
| 2026-06-19 | WORKING_BRAIN_CANON_RESEARCH.md | research |
| 2026-06-15 | PREMIUM_FRONTEND_PLAN.md | frontend plan |
| 2026-06-15 | SUPERBRAIN_NEXTGEN_DESIGN.md | superbrain design |
| 2026-06-14 | ACTIVE_BRAIN_BADGE_PROPOSAL.md | proposal |
| 2026-06-14 | MULTI_LLM_PLAN.md | multi-llm |
| 2026-06-13 | NERVOUS_SYSTEM_REDESIGN.md | nervous-system |
| 2026-06-13 | RECOVERED_micro_detail_findings.md | recovered |
| 2026-06-13 | SHELL_REDESIGN.md | shell |
| 2026-06-13 | backend_true_picture.json | true-picture (data) |
| 2026-06-13 | future_frontier_advice.json | future-frontier (data) |
| 2026-06-13 | nervous_system_designs.json | nervous-system (data) |
| 2026-06-13 | recovered_846e66ec.json | recovered (data) |
| 2026-06-13 | shell_redesign_designs.json | shell (data) |
| 2026-06-13 | vetted_polish_findings.json | polish (data) |
| 2026-06-13 | whole_system_lenses.json | audit (data) |
| 2026-06-12 | EVIDENCE_CURRICULUM.md | curriculum |
| 2026-06-08 | ULTRACODE_TASK.md | ultracode |

## Clusters with more than one doc — check dates above, no single doc
## in each cluster is confirmed authoritative by this index

- **GAGOS plan**: GAGOS_ULTRA_PLAN.md, GAGOS_REMAINING_INVENTORY.md, GAGOS_ARCHITECTURE.md,
  GAGOS_ORGANISM_FREEDOM_RECOMMENDATIONS.md, GAGOS_POSTER_GAP_AUDIT.md, GAGOS_RTX_DOSSIER.md,
  GAGOS_RENOVATION_NORTHSTAR.md, GAGOS_POLISH_FINDINGS.json — 8 docs. Per session memory,
  GAGOS_ULTRA_PLAN.md (v3, 2026-07-09) is the current master plan; the others are earlier
  passes or narrower sub-topics, but that is a memory claim, not something this index verifies.
- **frontend plan**: FRONTEND_HARMONY_MAP.md, FRONTEND_RENOVATION_BLUEPRINT.md,
  FRONTEND_BEAUTIFICATION_BLUEPRINT.md, FRONTEND_HEALTH.json, PREMIUM_FRONTEND_PLAN.md — 5 docs,
  spanning 2026-06-15 to 2026-07-03.
  FRONTEND_BEAUTIFICATION_BLUEPRINT.md is newest.
- **renovation**: RENOVATION_PLAN.md, RENOVATION_RESUME.md, RENOVATION_REVIEW.md — 3 docs.
  RENOVATION_PLAN.md (2026-06-30) is newest.
- **V7/V10 integration**: V7_INTEGRATION_AUDIT.md, V7_INTEGRATION_PLAN.md,
  V10_INTEGRATION_AUDIT.md, V10_INTEGRATION_PLAN.md — 4 docs, V10 (2026-07-09) postdates V7
  (2026-07-08).
- **nervous-system**: NERVOUS_SYSTEM_REDESIGN.md, NERVOUS_SYSTEM_REIMAGINATION.md,
  nervous_system_designs.json — 3 docs.
- **audit**: FULL_GREEN_AUDIT.md, AUDIT.md, DEEP_AUDIT_REMAINING_REPORT.md,
  ARCHITECT_REVIEW_2026-06-14.md, DEAD_CODE_CLEANUP_REVIEW.md, ROLLBACK_HARDENING_REVIEW.md,
  whole_system_lenses.json — 7 docs spanning the project's whole history; FULL_GREEN_AUDIT.md
  (2026-07-10) is newest.
- **true-picture**: SYSTEM_TRUE_PICTURE.md, BACKEND_TRUE_PICTURE.md, backend_true_picture.json —
  3 docs.
- **handoff**: CODEX_KEEPERS_HANDOFF.md, CLOUD_32B_HANDOFF.md, CODEX_FUSION_HANDOFF.md — 3 docs.
- **research**: ATMOSPHERE_MEMORY_RESEARCH.md, FORGE_RESEARCH.md, NERVE_FORM_RESEARCH.md,
  NODE_BRAIN_RESEARCH.md, WORKING_BRAIN_CANON_RESEARCH.md — 5 docs, all dated 2026-06-19
  (same research push).

Regenerate the date table with:

```
for f in .aios/state/*.md .aios/state/*.json; do
  echo "$(git log -1 --format=%ad --date=short -- "$f")|$(basename "$f")"
done | sort
```
