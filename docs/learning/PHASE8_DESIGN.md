# Phase 8 design: the cage governs the learning loop

*Plan: "the learning loop, held to the cage's standard", Phase 8. Property 15:
"the cage governs it -- learning organs in the organ ledger, on the live path,
with a reachability test so they can never again be green over code that
doesn't run."*

## 8a as built (2026-10-05): four learning organs, 56-59

**Operator decision (2026-10-05):** add four organs, as the plan proposed,
rather than folding the properties into existing organs or deferring. The
ledger goes from 55 organs to 59.

### Why reachability comes first

F1, the finding this plan opened with: the governed learning stack was organ
43, green, while every live turn learned through a different, ungoverned
stack. A green organ over code the turn never runs is the failure the organ
ledger exists to prevent. So each new organ's C2 is proven against the
**process** authority (the one `aios/application/memory/bootstrap.py` builds
and every live turn uses) or the real route's wiring. A class that works only
in isolation does not pass.

### The organs

| # | Organ | Owner | What it governs | C2: the live path |
|---|---|---|---|---|
| 56 | Learning Integrity and Provenance | `ProvenanceWriter` | Signed provenance on every learned row (Phase 3): Ed25519 over content and provenance, per-source keys, no laundering of unsigned state. | The process authority's lessons, semantic and facts adapters sign through ONE writer, and the skill library through its own; both use the process's one signer, as live rows. A lesson written and promoted through the live adapter ends on a signed record. |
| 57 | Reflex Authority | `Cerebellum` | Reflexes (Phases 2, 5, 6): only from operator-activated skills, only on the operator's own words, only where the skill applies, retired only to the operator's re-activation. | `/api/generate` resolves `get_cerebellum`: the ONE cerebellum the process authority owns, gated by its skill library. |
| 58 | Recall Isolation | `RecallGate` | What reaches a prompt (Phases 0b, 3c, 4): signed rows only, the asking principal's only, inside the data envelope. | The process authority's lessons, semantic and facts adapters admit through ONE gate. A lesson the live path wrote is recalled for its owner only through that gate. |
| 59 | Learning Freeze | `LearningFreezeAuthority` | The emergency stop's reach into learning (Phases 0b, 6). | Frozen, the process authority's lesson and skill writes and its reflex compiler all ask the ONE `LearningFreezeAuthority`, and each is refused, naming its boundary. |

**Organ 59's owner is new, and thin.** `aios/memory/learning_freeze.py` had
functions and no class.
- `LearningFreezeAuthority` owns no latch. It reads the operator's durable
  latch through the canonical `EmergencyStopController` (organ 19), so there
  is one stop rule, not a second spelling of it.
- `learning_permitted` and `assert_learning_permitted`, which every boundary
  imports, now delegate to its singleton. A boundary that bypassed the
  authority would be caught: that hand mutation is killed by C2.

**Organ 43 is re-scoped to the unified authority.** The institutional library
(`aios/application/memory/institutional_skills.py`) is the live skill store,
and it applies every reuse outcome through organ 43's
`SkillLifecycleAuthority`. It joins 43's entrypoints, and 43's C2 now proves
that path.

### C3, C4, C5: each cites a test that runs in the gate

| # | C3 durable | C4 integrity | C5 fail-safe |
|---|---|---|---|
| 56 | A signed record verifies through a store a later process opens. | An edited provenance record breaks its signature. | Without the key a write is recorded UNSIGNED, never a plausible signature. |
| 57 | A new cerebellum replays what was compiled, never what was retired. | A demoted skill flipped back to active in the database is refused. | An unreadable library activates nothing. |
| 58 | A gate a later process builds admits only what was signed, for its owner. | A signed lesson edited in the database is refused. | A recall that names no one gets nothing. |
| 59 | The engaged latch freezes a later process. | N/A-BY-DESIGN: the freeze holds no state; the latch's integrity is organ 19's. | An unreadable latch freezes learning. |

### Live evidence (C10)

`scripts/phase4_live_evidence.py` gained a probe for each organ. Each runs the
production classes against real SQLite in the run's scratch directory:

- **56:** a lesson is signed (record and promote); it verifies through a
  reopened store; a writer with no key appends unsigned; an SQLite edit is
  refused at recall.
- **57:** an unactivated candidate compiles nothing. After activation, the
  owner's request fires the reflex, and another principal's turn and quoted
  text do not. The reflex survives a restart, and once retired it stays
  retired for a new instance.
- **58:** the gate admits the owner only, and an anonymous recall gets
  nothing. Recalled text reaches the prompt inside the envelope, and a
  command carried from memory is tainted.
- **59:** a lesson lands before the stop. Once the stop is engaged, a fresh
  read freezes learning and the next write is refused. The probe engages its
  own latch, so the rest of the run is not frozen; the refusal path is
  production's.

The signing key in 56 and 58 is generated for the probe's own store. It lives
only in the run's memory and is never printed or written.

### Evidence

- **Live evidence:** `scripts/phase4_live_evidence.py` at `77d62129`, 48 of
  48 proofs passed, including 56-59's (`release/phase4/live-evidence-77d62129ebb5.json`).
  Organs 43 and 56-59 carry that row, and organ 43 keeps its still-valid
  `f40b8090` row.
- **The twelve-condition verifier** (`verify_organ_twelve_conditions.py
  --enforce-condition-proofs --allow-unexecuted-frontend`, at `8f86cf82`):
  - 140 referenced test files, **2,750 passed, 0 failed**;
  - **0** C3/C4/C5 greens without a mechanical proof;
  - **0** live rows resting on operator attestation;
  - organs **23, 43, 56, 57, 58 and 59 survive the mechanical re-read**.
  - It reported two failures, organs 33 and 37. Both are C10 citations of
    live-model tests whose results CI supplies to that step
    (`--extra-junit clerk-junit/clerk-junit.xml`) and a laptop does not.
    Phase 8 touches neither.
- **The 16 organ-ledger suites, plus the owner and organ suites, pass.**
- **Reachability is mutation-checked.** I broke the production wiring each C2
  guards eight times (key-less writer, unsigned lessons, a fresh cerebellum
  per request, ungated lessons, a gate ignoring the owner, a module bypassing
  the freeze authority, a skill save skipping the freeze, an anonymous recall
  admitted). Six breaks were caught. The two survivors are inner checks that
  another layer also enforces on that path (the store's principal column; an
  earlier freeze boundary), and each is pinned by its own suite.

### Cost of the change

- **Organ 23 re-gathered.** Its entrypoints include
  `tests/test_organ_release_conformance.py`, whose count pins moved. Its
  conformance suite passed at `f35b0351`, where the pins and the 59-row
  ledger first agree (56 passed, 0 failed), and its row is re-stamped there.
- **Organ 57 lists `aios/agents/tool_agent.py`.** Replay's auto-approval and
  the composition cap live there. A large, often-edited file will stale 57
  more often than its peers. That is the honest consequence of where the code
  is; leaving it out would let 57 stay green while that code moved.

## Not in 8a

- **CI wiring.** The plan also asks for the mutation probe gated, the red-team
  reel nightly, and the learning-ledger job extended. The full probe takes
  about 2.5 hours, which is too long for a per-PR gate; a weekly or dispatch
  job is the practical form, and its CI-minute cost is the operator's call.
  This is 8b.
- **The judged payoff run.** It needs the operator's D8 steps: pin the live
  key, readmit lessons with `--principal`, and set `AIOS_PAYOFF_PRINCIPAL`.
