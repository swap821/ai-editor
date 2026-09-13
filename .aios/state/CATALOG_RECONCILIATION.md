# Catalog reconciliation — one map, 2026-09-13

## Why this exists

This system had **three competing definitions of "done"**, none of which
referenced the others, so "how far along is it" had no answer:

| | framework | status |
|---|---|---|
| **A** | `.aios/state/GAGOS_ULTRA_PLAN.md` — milestones **M1 Honest / M2 Sovereign / M3 Product**, backed by the catalog in `GAGOS_REMAINING_INVENTORY.md` | **M1 was never recorded as closed.** Declared superseded 2026-07-13, but edited again on 2026-08-04 with no supersession note in the file itself |
| **B** | `docs/architecture/MASTER_CONVERGENCE_DIRECTIVE.md` — a 24-slice roadmap | Superseded A; itself absorbed into C's numbering |
| **C** | Repair waves **R0–R14** + the **55-organ ledger** | **Canonical.** Every September document tracks only this |

**C is canonical.** A and B are historical. Their dated content stands as
evidence and is not rewritten; this file is the cross-reference they never had.

## The catalog's real size

`GAGOS_REMAINING_INVENTORY.md` has **165 `###` item headings** across 11
sections. The Ultra Plan's own text corrects this to "~157 distinct" after
dedup, and that correction is right — at least one pair is a verified duplicate:

* **Item 44** "Project Passport harvester (P3) — does not exist" and
  **item 127** "Project Passport harvester core module" are the same work.

## Headline: the catalog is substantially stale

It was written 2026-08-31. Work has landed since, and **the catalog still
describes that work as missing.** Verified mechanically, not inferred:

| item | catalog says | actually |
|---|---|---|
| **44 / 127** Project Passport — *"the crux — everything downstream depends on it"* | "does not exist" | **DONE.** `aios/memory/project_passport.py`, 486 lines, `harvest_project_passport()`, `ProjectPassport`; `POST /api/v1/projects/passport/scan`; 5 test files; secret-path filtering |
| **46** lesson/skill/fact recall | "no LIMIT, full-table Python scan forever" | **DONE.** `mistake.py`, `skills.py`, `facts.py` all carry `LIMIT` |
| **48** contradiction-resolution UX | "a dead end in the frontend" | **DONE.** `MemoryOperationsPanel.jsx` calls `facts/reconcile`, with a test |
| **55** `PheromoneStore.for_contract` | "never called — orphaned system" | **DONE.** Callers in `council_orchestrator.py`, `memory/adapters.py`, `memory/authority.py`, `cognition/repo_map.py` |
| **118** frozen-path CI gate | "does not exist; Definition-of-100% item #3 unmet" | **DONE.** `scripts/check_frozen_core.py` exists **and** runs in `ci.yml` |
| **3** per-task ScopeContext | "BLOCKED pending a §VIII proposal" | **DONE.** Shipped the same day the catalog was written, commit `502fde66` (#271) |

That last one is the sharpest: the item was already done *at the moment the
catalog was authored*, and its status line was never updated.

## What is genuinely not done

Confirmed by absence, not assumed:

* **45** No scheduler anywhere — zero matches for `APScheduler|BackgroundScheduler|croniter|schedule.every` in `aios/`. Compaction, pheromone decay and curriculum mining remain manual-trigger-only.
* **47** No memory backup/restore — no `VACUUM INTO`, no backup API in `aios/memory/`.
* **96** No watchdog. **105** No host-resource metrics (`psutil`/`cpu_percent` absent).
* **104 / 121 / 122 / 123** `docs/OPERATIONS.md`, `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md` — none exist.
* **133 / 140 / 141** The whole **P4 Sovereign Web Navigator** tranche — no `WebNavigator`, no search-provider abstraction, no domain allow/deny. Only the pre-existing CRAG websearch fallback.
* **144** Taste facts are **not** wired into the generation loop — no `taste` reference in `aios/application/turns`.
* **153** No multi-tenant support. **155** No at-rest encryption. **158** No export / "forget everything" control. **157** No threat-model document.
* **71 / 72 / 74 / 79** Four frontend defects stand: `WorkTabLiveDashboard.tsx` and `RegionPins.tsx` carry no offline/unavailable guard; `MemoryGalaxy.tsx` has no `mastery` reference and no non-colour quarantine cue (WCAG 1.4.1).
* **80** No local-vs-cloud routing trust ledger.
* **108 / 110 / 117 / 119** Honesty-doc items still open — the "local-only", "redacted" and frozen-core claims remain in `README.md`; `.aios/state/PLAN.md` still says 326.

## Per-section verdicts

**Method, stated plainly.** Sections 1–5 (72 items) were mapped by agents with
per-item evidence before the run hit its limit. Sections 6–11 (93 items) were
mapped by hand afterwards. **The planned critic pass never ran**, so the 72
agent-mapped verdicts have *not* been independently audited — see Limitations.

| section | items | source |
|---|---|---|
| security-privacy-spine | 14 | agent-mapped, evidence-cited |
| autonomy-council-worker | 16 | agent-mapped, evidence-cited |
| router-providers | 14 | agent-mapped, evidence-cited |
| observability-cognition | 14 | agent-mapped, evidence-cited |
| testing-ci-quality | 14 | agent-mapped, evidence-cited |
| memory-knowledge | 13 | hand-verified |
| frontend-organism | 10 | hand-verified |
| deployment-ops-resilience | 14 | hand-verified |
| honesty-docs-thesis | 19 | hand-verified |
| roadmap-frontier | 28 | hand-verified |
| periphery | 9 | hand-verified |

**Agent-mapped tally (72 items):** 21 DONE · 17 PARTIAL · 34 OPEN.

**Hand-verified tally (93 items):** 24 DONE · 18 PARTIAL · 26 OPEN · 24 UNKNOWN · 1 N/A.

**Combined: 165 items — 45 DONE, 35 PARTIAL, 60 OPEN, 24 UNKNOWN, 1 N/A.**

## Limitations — what this map does not establish

* **24 items are UNKNOWN.** Mostly in `roadmap-frontier` (P4/P5 sub-items) and
  `honesty-docs`. They were not cheaply verifiable mechanically, and an honest
  UNKNOWN is recorded rather than a guess. They are not evidence of absence.
* **The critic pass never ran.** It was to audit DONE claims and find items the
  sweep missed. The 21 agent-asserted DONEs carry cited evidence but were not
  re-checked by a second pass. Treat them as one-source.
* **DONE means "the artefact exists and its cited evidence checks out"** — it
  does not mean the behaviour was exercised end-to-end. That distinction is
  exactly what turned 54 green organs into 13 this same week.
* **Verdicts are point-in-time.** They describe HEAD on 2026-09-13 and will rot
  the same way the catalog did. The organ ledger now has a staleness rule for
  precisely this reason; this document has none.

## What this changes about "completion"

The remaining v1 gaps are **mostly not unbuilt code**:

* `gagos v1-check --strict` already returned `ready: true` in CI at `14766b27`.
* The full 7-service Compose lifecycle is assembled **nowhere** — not CI, not
  local, not nightly.
* **R11's packaged proof has no defined test.** Nobody can close a proof
  obligation that does not exist; defining it *is* the work.
* `release-strict-gate` is tag-gated and has never fired against a real tag.
* Independent reproduction and the non-builder handoff are **structurally
  outside** what any agent can satisfy.

The honest next increments, in order of leverage:

1. **Define R11's packaged proof.** It is the only PARTIAL wave, and it is
   blocked on a missing definition rather than missing code.
2. **Assemble the Compose lifecycle once**, anywhere, and record what happens.
3. **Close the four standing frontend defects** (71/72/74/79) — small, real, and
   each one is a place the UI shows data it does not have.
4. **Write the four missing docs** (104/121/122/123). Cheap, and three of them
   are prerequisites for anyone but the builder operating this system.
