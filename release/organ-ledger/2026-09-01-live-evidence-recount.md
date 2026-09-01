# Live-evidence recount — the organ ledger's true green count

**Date:** 2026-09-01  
**Evaluated commit:** `9381121b346f2645b8c9812b3ea3ae5ba89ba334`  
**Result: 54 green / 0 yellow → 5 green / 49 yellow.**

Nothing was disproven here and no test was weakened. The ledger reported 54/54
green with `requires_live_evidence: false` on all 54 organs, and 126 of 162
C3/C4/C5 verdicts were prose with no resolvable referent. This pass measured the
greens against the bar the twelve-condition contract already defined, and
recorded what fell out.

## Why the previous number survived so long

`.aios/state/condition_proof_budget.json` recorded a budget of 46 greens without
condition proofs, and the live gap was also exactly 46 — so the gate passed
"only by the coincidence that 46 == 46", in that file's own words. The budget
was the ceiling AND the measurement, so no amount of proof work could move it and
no missing proof could break it.

## Method — and why the number is not a judgement call

Demotion is driven by the **gate's own predicate**
(`scripts/verify_organ_twelve_conditions.py::_condition_proof_failures`, with
`require_execution=False`), never by the `requires_live_evidence` flag this same
pass assigns. That separation is deliberate: gating the count on a value chosen
in this pass would let the pass choose its own answer. Two independent buckets:

### Bucket A — no resolvable C3/C4/C5 referent (46 organs)

A verdict must name `tests/foo.py::test_bar`, or discharge C3/C4 with
`N/A-BY-DESIGN - path::symbol`. Prose that asserts the property is not a
referent, and rewording prose to *look* like a citation is the failure mode this
bar exists to prevent.

| Organ | Name | Missing | What it needs to return to green |
| ---: | --- | --- | --- |
| 6 | Edge Trust Boundary | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 7 | Policy Kernel | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 8 | Action Broker | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 9 | Exact Capability Authority | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 10 | Mission Authority | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 11 | Turn Coordinator | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 12 | Worker Foundry | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 13 | Isolated Executor Service (construction) | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 14 | Staged Workspace Manager (construction) | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 15 | Evidence and Verification Authority (construction) | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 16 | Promotion Authority (construction) | `C3,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 17 | Cortex Observation Bus | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 18 | Memory Authority (construction) | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 19 | Emergency Stop Controller (construction) | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 20 | Living Mirror Reaction Registry (construction) | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 21 | Queen Council Orchestrator | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 22 | V1 Release Declaration (gagos v1-check) | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 24 | Human Sovereign Identity | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 25 | Constitutional Kernel | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 26 | Emergency Stop Organ (full boundary hard-wiring) | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 27 | Operator Taste Model | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 28 | Project Understanding Organ | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 29 | Correction and Interpretation-Lineage Organ | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 30 | Communication and Human-State Interpreter | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 31 | Human Representative Context Compiler | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 32 | Universal Intelligence Gateway | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 33 | Model Registry and Capability Passport | `C3,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 34 | Cloud Budget and Provider-Health Organ | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 35 | Local Clerk Runtime | `C3,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 36 | Clerical Job Contract and Dispatcher | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 37 | Local Model Qualification and Health | `C3,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 38 | Durable Local-Clerk Provenance and Continuity Organ | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 39 | Multi-Model Deliberation and Dissent Organ | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 40 | Isolated Workspace and Executor (live proof) | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 41 | Promotion, Checkpoint and Rollback (live proof) | `C3,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 42 | Recovery and Resumption | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 43 | Local Skill Reuse, Confidence and Demotion | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 45 | Constitutional Amendment Authority | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 47 | Read-Model and Projection Organ | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 48 | Truthful Living Mirror (full truthful UI) | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 49 | Approval and Decision Surface | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 50 | Provenance and Explanation Surface | `C4,C5` | **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 51 | Sovereign Control and Heartbeat Surface | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 52 | Observability and Health Organ | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 53 | Installation, Configuration and Key Authority | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |
| 54 | Backup and Disaster-Recovery Organ | `C3,C4,C5` | **C3** — cite `tests/foo.py::test_bar` proving durable state survives a process restart, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ owns no durable store; **C4** — cite a test proving tamper-evidence / integrity, or discharge with `N/A-BY-DESIGN - path::symbol` if the organ keeps no journal; **C5** — cite a test proving fail-safe reporting (reports unavailable rather than a plausible zero). **C5 has no N/A-BY-DESIGN clause** and must be positively proven |

### Bucket B — runtime property, live evidence not at the evaluated commit (3 organs)

These three pass the referent bar. They were demoted because they assert runtime
properties, so `requires_live_evidence` is now true — and the ledger validator
requires such an organ's live evidence to be stamped at the **evaluated commit**.
Verified empirically before demoting: leaving them green with the honest flag
emits 13 violations of the form *"has evidence from commit X, not the evaluated
commit Y"*.

| Organ | Name | Evidence stamped at | What it needs to return to green |
| ---: | --- | --- | --- |
| 23 | Release Conformance Organ | `abf7346def48, abf7346def48` | regenerate live evidence at the evaluated tip |
| 44 | Golden Mission and Endurance Evaluation | `da5071c544dc, c2c1b71dd29a, e3b0b00365e6, 67924fe06fbd, 0b52e3208a07` | regenerate live evidence at the evaluated tip |
| 46 | Constitutional Learning Organ | `5ecad32e3c47, d4a4b0cf26f8, f2376171f4c8, ac8736c6fbd2, 3dc7323d74cc` | regenerate live evidence at the evaluated tip |

## Carve-out — 3 organs NOT demoted, and this is the operator's call

Organs 1–5 are covered by the signed spine attestation in
`.aios/state/spine_release_attestation.json`. Its `evidence_digest` covers
`status`, `condition_verdicts`, `live_evidence` and `known_blockers`, so
demoting one — or refreshing its evidence — invalidates a signature only the
operator can reissue. These three met bucket B's condition and were **reported,
not applied**:

| Organ | Name | Finding |
| ---: | --- | --- |
| 1 | Security Gateway | classified `requires_live_evidence=true`; live evidence stamped at `b5485d3b128e`, not the evaluated commit. Under an honest flag it cannot hold green today. |
| 4 | Tamper-Evident Audit Logger | classified `requires_live_evidence=true`; live evidence stamped at `b5485d3b128e`, not the evaluated commit. Under an honest flag it cannot hold green today. |
| 5 | Prompt Injection Shield | classified `requires_live_evidence=true`; live evidence stamped at `b5485d3b128e`, not the evaluated commit. Under an honest flag it cannot hold green today. |

**Consequence, stated plainly: of the 5 remaining greens, only organs 2 (Scope
Lock) and 3 (Secret Scanner) hold an unqualified green.** Both are pure
functions whose own verdicts state they own no durable store. The other three
are green because their status is inside a signature, not because the evidence
currently supports it. Re-attesting them is an operator action; this pass
deliberately did not touch it.

## The `requires_live_evidence` classification

All 54 organs were classified for whether their contract asserts a RUNTIME
property (durability across restart, tamper-evidence, isolation holding,
recovery restoring state, fail-safe reporting under fault, external liveness).
Every organ classified FALSE — the answer that preserves a green — was then sent
to an adversarial reviewer instructed to refute it. **7 FALSE classifications
were overturned to TRUE: organs 1, 5, 6, 11, 12, 34, 47.** Final tally: 48
require live evidence, 6 do not.

The single most consequential overturn was **organ 1 (Security Gateway)**, whose
own C3 verdict — *"rate-limiter state is process-local by design (not a durable
authority store)"* — is factually wrong about production. `get_policy_kernel()`
builds the kernel with `RateLimiter(db_path=config.APPROVAL_DB_PATH)`, commented
in `aios/api/deps.py` as *"DB-backed (durable, multi-process safe)"*. The verdict
describes the ephemeral module default, which production does not use.

Only 6 organs remain FALSE: 2, 3, 8, 22, 26, 36.

## Commands run, and their output

```
$ python -m aios.launcher organ-check --strict
GAGOS organ ledger: 5/54 green (CONFORMANT)
  no ledger violations
```

Exit code is now **1**, not 0: `--strict` means "all 54 green", which is no
longer true. The ledger is still **CONFORMANT with no violations** — the
demotions are internally consistent. No CI workflow invokes this command
(verified by grep across `.github/workflows/`), so nothing breaks on this change.

```
$ python scripts/verify_organ_twelve_conditions.py --enforce-condition-proofs
running 10 referenced test file(s) for C6/C7/C9 ...
test outcomes: 10 file(s), 437 passed, 0 failed
live evidence rows resting on operator attestation: 0
C3/C4/C5 greens without a mechanical proof: 0
green mechanical failures: 0
exit=0
```

## The condition-proof ratchet reached 0 — by demotion, not by proof

`greens_without_condition_proofs` is now **0**, down from 46. Read that with
care: **not one new proof was written.** The 46 greens that lacked referents are
no longer greens, so the gap is vacuously empty. The five remaining greens each
carry a resolvable referent or an N/A-BY-DESIGN cite.

Per that file's original terms — *"when it reaches 0,
`--enforce-condition-proofs` becomes the permanent default"* — the gate is now
armed for real: any organ promoted to green from here must name a referent that
runs and passes in the gate's own invocation. Recording 0 rather than leaving 46
as headroom is the point.

## Could this pass have made the number look better than it is?

Three places where it could have, and what prevented each:

1. **Choosing the demotion criterion.** Prevented structurally: demotion runs off
   the gate's predicate, not the flag assigned here. Concretely — the
   classification disagreements on organs 12 and 36 change the green count by
   **zero**, because both are already in bucket A.
2. **Classifying runtime organs as FALSE to keep them green.** Prevented by
   sending every FALSE to an adversarial reviewer told that FALSE is the
   flattering answer. It overturned 7, including two organs that survive
   demotion (1 and 5).
3. **Writing a thin test or rewording prose into a citation.** Not done. No test
   was added, no verdict text was rewritten, no threshold was lowered, no gate
   relaxed. The only ledger edits are `status`, `requires_live_evidence` and an
   appended `known_blockers` entry naming the specific missing referent.

The number that could still be *too generous* is 5, not too harsh — organs 1, 4
and 5 are green only because their status sits inside a signature this pass
would not forge.

## Follow-up decision: `requires_live_evidence` is being narrowed

Recorded here the same day, so this document is not read as endorsing a
definition already superseded.

This pass classified 45 organs `requires_live_evidence: true` by asking *"does
the contract assert a runtime property?"*. That question is broader than the
flag's mechanical meaning. The validator forces **every** `live_evidence` row's
`commit_sha` to equal the evaluated commit (`organ_ledger.py:554-571`); CI never
writes the ledger (grep-confirmed across `.github/workflows/`), and
`phase4_attach_ledger.py` appends rather than prunes. So an organ carrying this
flag breaks green on the very next commit — which is why all 54 sat at `false`,
not because anyone had judged them deterministic.

The operator's decision is to narrow it: **true only when the proof needs
something the gate's own pytest run cannot provide** — a real Ollama model,
cloud credentials, a browser session, a multi-hour run. A pytest test *is*
execution of the system; organ 4 proves tamper-evidence with an ordinary test
node. Under the narrow reading, an organ's honesty rests on C3/C4/C5 nodes that
re-execute on every push, which is strictly stronger evidence than a
hand-transcribed probe from a six-week-old commit.

**This does not move the count in this document.** Demotion was driven by the
mechanical predicate, never by the flag — that separation is why 5/49 is
unaffected by which definition is used. The flags will be re-set per organ as
each is restored.

## Reproduce

```bash
python -m aios.launcher organ-check --strict
python scripts/verify_organ_twelve_conditions.py --enforce-condition-proofs
python scripts/build_organ_ledger_doc.py --check   # doc matches the ledger
python -m pytest tests/test_condition_proof_ratchet.py -q
```
