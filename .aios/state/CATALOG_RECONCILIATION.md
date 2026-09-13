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
mapped by hand afterwards. The planned critic pass never ran at the time, so the 72
agent-mapped verdicts were unaudited when this map first shipped. **That pass
has since been done by hand — see the completion pass at the end of this file.**

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

* **DONE means "the artefact exists and its cited evidence checks out"** — it
  does not mean the behaviour was exercised end-to-end. That distinction is
  exactly what turned 54 green organs into 13 this same week.
* **The per-item verdict map was never persisted.** Only the tallies above were
  written down; the 165 individual verdicts lived in a session and are gone.
  That is why the completion pass below can state which items it resolved but
  cannot restate the combined per-bucket tally precisely. The resolved table is
  written into this file so the same loss does not repeat.
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

---

# Completion pass — 2026-09-13

Both limitations recorded above are now closed.

## The 21 DONE claims: audited, 21/21 survive

The critic pass that never ran has now been done by hand. Every agent-asserted
DONE was re-checked against its own cited evidence — does the named file exist,
does it contain the named symbol, does the CI line actually invoke what is
claimed.

**21 of 21 confirmed. No unsupported claims.** The agent mapping was accurate.

The caveat from above still binds and is not weakened by this: **DONE means the
artefact exists and its cited evidence checks out** — not that the behaviour was
exercised end to end. The audit was performed at that same level.

**A second duplicate pair found:** items **#4** and **#14** are both
"per-workspace `AutonomyLedger` dimension" — the same work counted twice, like
44/127. The catalog's headline of 165 overcounts by at least two.

## The 24 UNKNOWNs: resolved

| item | verdict | evidence |
|---|---|---|
| 51 knowledge-chunk search | **OPEN** | `aios/memory/doc_ingest.py` uses `LIKE` (2 occurrences) — still a SQL scan, not FAISS-indexed |
| 53 curriculum self-mining | **PARTIAL** | `aios/memory/curriculum_miner.py` exists; single-domain claim not settled without reading its domain table |
| 54 operator-fact extraction | **UNKNOWN** | zero `re.compile` in `facts.py`; the extraction templates the item describes are not at the cited location |
| 73 memory metabolism panel | **PARTIAL** | `MemoryOperationsPanel.jsx` exists; whether it shows candidate/verified/quarantined/superseded unconfirmed |
| 97 RAM budget table | **PARTIAL** | `resource_mode` in `config.py` and `routes/v10.py`; no budget *table* located |
| 101 snapshot retention gc | **PARTIAL** | retention/prune present in `aios/runtime/rollback_registry.py`; not shown to be scheduled |
| 111 "goes dormant" claim | **DONE** | the word no longer appears in `README.md` — the false claim is gone |
| 112 autonomy docstring | **UNKNOWN** | the docstring discusses defaults; whether the specific inversion was corrected is not mechanically decidable |
| 113 planner confidence disclosure | **OPEN** | the claim is still in `README.md`, undisclosed |
| 114 injection-shield default-off | **OPEN** | no `INJECTION` disclosure in `README.md` |
| 115 `SWARM_CLOUD_BURST` disclosure | **DONE** | present in `README.md` |
| 116 boot attestation detection-only | **PARTIAL** | attestation discussed in `README.md`; "detection-only, non-blocking" not confirmed |
| 124 earned-autonomy STRONG ceiling | **OPEN** | no `STRONG` disclosure in `README.md` |
| 126 thesis-audit PARTIAL claims | **UNKNOWN** | `tools/thesis_audit.py` contains no `PARTIAL`; cannot tell reconciled from never-emitted |
| 136 cross-source verification | **OPEN** | no `cross_source`/`corroborat*` anywhere in `aios/` |
| 137 freshness TTL for web | **OPEN** | TTL exists for mirror/API, nothing web-sourced |
| 138 full-page fetch + extraction | **OPEN** | extraction exists in `doc_ingest.py` for uploads, not web pages |
| 139 web-content injection defense | **OPEN** | nothing matching web-specific injection defense |
| 142 web audit actor/endpoint | **OPEN** | none |
| 143 frontend citation display | **OPEN** | `citation` appears in canvas components generally, nothing web-provenance |
| 145 taste-category schema | **OPEN** | none |
| 146 editable taste-fact UI | **OPEN** | no `taste` anywhere in `frontend/src` |
| 147 alignment → taste bridge | **OPEN** | none |
| 148 taste staleness policy | **OPEN** | none |
| 149 per-project taste scoping | **OPEN** | none |
| 154 public docs / demo | **OPEN** | `docs/*.md` at top level: **zero**; all markdown sits in `adr/` and `architecture/` |
| 159 accessibility audit | **OPEN** | no `axe`/`jest-axe`/`a11y` in `frontend/package.json` |
| 162 cross-platform claim | **OPEN** | the claim is present in `README.md` and remains untested/undisclosed |

**Three remain UNKNOWN with the reason stated** (54, 112, 126) rather than being
promoted to a tidy verdict. Each names what would settle it.

**Tally, stated as far as it is honest to state it.** The catalog's 24 UNKNOWNs
all fall inside the 28 rows above — the sweep resolved a superset, because the
per-item verdict map from the original pass was never persisted and the exact
24-item subset cannot be recovered. What *is* certain: **UNKNOWN drops from 24 to
3.** The per-bucket combined tally (was: 45 DONE / 35 PARTIAL / 60 OPEN) is not
restated, because doing so would require the four already-classified rows to be
told apart from the twenty-four, and that information no longer exists. Inventing
the split would be exactly the kind of tidy number this document exists to refuse.

The largest single block of OPEN is the **P4 Sovereign Web Navigator and P5
Taste Memory tranches — 15 items with no implementation at all.** Not partially
built: absent. That is the honest shape of what remains.

## The restoration bill for the 41 demoted organs

They cannot be restored by re-running tests. All 41 clear every non-test
condition at HEAD, but all 41 carry `live_evidence` at `proof_level: "live"`
gathered ~199 commits ago, and as of this pass **C10 refuses stale evidence**
— so a re-stamp no longer works, by design.

Restoring any of them requires **re-gathering its live evidence at a current
commit**, which costs what the evidence originally cost:

| evidence shape | what re-gathering needs |
|---|---|
| `release/phase4/live-evidence-*.json` artifacts | a live probe run at a current tip |
| `tests/foo.py::test_bar` proof nodes | already re-run every gate run — cheapest class |
| `actions/runs/<id>` CI runs | a fresh CI run, then the row re-cited |
| `OPERATOR-ATTESTED` observations | the operator; no agent can supply these |
| browser-session rows | a real browser session |
| Docker/container probes | a Docker host — unavailable on this machine today |

The five frozen-spine organs need **both** halves: evidence re-gathered *and*
`scripts/spine_release_attest.py` re-run. Their attestation sits at `f3cb6122`
and their evidence at `b5485d3b`; `aios/security/gateway.py` has changed since
both.
