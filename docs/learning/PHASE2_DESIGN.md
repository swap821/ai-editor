# Phase 2 — one learning authority on the live path

*Design of record, 2026-09-25. Built on a read-only ground-truth map (four
mappers, every claim quoted from code at master `0740f294`) that overturned the
original plan's premise. Operator decision: migrate the live learning data into
the institutional skill library.*

## What is true today

| | Live learning stack | Institutional skill library (organ 43) |
|---|---|---|
| Code | `aios/memory/skills.py`, `aios/core/cerebellum.py`, `aios/memory/mistake.py`, `aios/memory/curriculum.py` | `aios/domain/learning/*`, `aios/application/learning/*`, `/api/v1/skills/*` |
| Store | `aios_memory.db`: `procedural_skills` (80), `compiled_playbooks` (13), `mistake_pool` (106), `curriculum_tasks` (6) | `aios_operational_state.db`: `institutional_skills` (**0**); `expert_trajectories` and `reuse_outcomes` do not exist |
| Identity / states | `signature_v2` arc; candidate / verified / superseded | `skill_id` + `version`; 11 states |
| Reached by | every `/api/generate` turn | `/api/v1/skills/*` only; 3 of 5 service methods have no production caller |
| Governed? | no | yes (organ 43 green), over no data |

- `MemoryAuthority` (organ 18) is already the live path's composition root
  (R11, enforced statically and at runtime), but it is a pure passthrough with
  no skill policy.
- The cerebellum and curriculum are outside it. `get_cerebellum` builds a
  fresh cerebellum on every request, and it issues about 10 raw SQL statements.
- The skills and lessons singletons carry no cerebellum or facts wiring.
  `get_skill_memory`'s docstring says it is "wired to the same cerebellum";
  that is false, and compile-on-promotion happens a request later, through
  `get_cerebellum`'s sweep.
- The institutional state graph has a latent `KeyError`: `qualified` is
  declared but absent from the transition table.

## Target

`MemoryAuthority` is the one object through which every learning write and
every recall into a prompt passes. Behind it, the institutional library is the
skill store, so organ 43 governs the data the turn actually runs on.

- **Skills** (80): migrated to institutional skills. `skill_id` comes from
  `signature_v2`, at version 1; the procedure is the arc's steps; counts and
  confidence carry over; provenance records `migrated from procedural_skills
  id N`.
- **States:** candidate → candidate. verified (8) → candidate, **flagged ready
  for review, not active**: activation needs the operator's capability proof.
  superseded → superseded.
- **Lessons** (106) do not migrate, because the library has no lesson concept.
  `mistake_pool` stays, under the authority.
- **Playbooks** are not copied. They are recompiled from *active* skills only,
  and the existing 13 are retired with a recorded reason.
- **Consequence (told to the operator):** activation becomes human-only, so
  skill recall and reflexes go quiet until the operator activates the 8
  review-ready skills.

## Organ exposure: the cost model

A change to a green organ's entrypoint stales that organ. Master requires
linear history, so evidence must be re-gathered at master's tip after every
squash.

| Files | Green organs |
|---|---|
| `aios/api/deps.py` | 25, 27, 28, 29, 33, 34, 38, 42 |
| `aios/api/main.py` | 25, 26, 30, 32, 42, 52 |
| `aios/application/turns/generate_pipeline.py` | 32 |
| `aios/application/turns/conversation_pipeline.py` | 30, 32 |
| `aios/application/memory/authority.py` | 18 |
| `aios/domain/learning/{repository,skill_contracts}.py`, `aios/application/learning/skill_lifecycle.py` | 43 |
| `aios/application/learning/service.py` | 26, 43 |
| bootstrap, adapters, `turn_pipeline`, `tool_agent`, reflection agent, cerebellum, skills / mistake / curriculum, `db.py`, `schema.sql`, `routes/skills.py` | none |

**Rule:** do the work in unowned files where possible. Batch every edit to an
owned file so each organ is staled and re-gathered once per slice, never
incidentally.

## Slices

Each slice is one PR, with tests that fail without it and mutation checks.
After each squash, the reel and full suite run on master and owned organs are
re-gathered.

| Slice | What | Owned files it must touch |
|---|---|---|
| **2.1** | The chokepoint. Cerebellum and curriculum become authority adapters built once in `bootstrap.py`. Compile-on-promotion is wired for real, and the false docstrings are fixed. Live learning writes go only through the authority. An AST enforcement test fails if production code writes a learning table or calls a learning-store write method any other way. | `deps.py` (providers), `generate_pipeline.py` (fallbacks), `authority.py` (new operations): organs 18, 32, and the 8 of `deps.py` |
| **2.2** | The institutional store behind the authority. Fix the `qualified` defect. Lift the transition graph out of `SkillRepository` as pure policy. One emergency-stop mechanism (`learning_freeze`), including the three unguarded service methods. A review queue for candidates. | institutional stack files: 43, and 26 if `service.py` changes |
| **2.3** | Migration tool: dry-run by default, backup first, row counts asserted, idempotent, provenance recorded. **The operator is asked before it runs on live data.** | none (a script) |
| **2.4** | Switch: the authority's skill operations read and write the institutional store. `procedural_skills` becomes read-only history. The cerebellum compiles from active skills. The payoff harness follows. | `authority.py`, adapters: 18 |
| **2.5** | Re-pin `tests/test_documented_reachability.py` to "one learning authority". Rewrite the Learning Ledger L2–L5 records (LC1 owner class, LC2 live callers). Re-gather every organ the phase touched at master's tip. | ledgers |

## Slice 2.1: what was done, and what was deliberately not done

**Done:**
- `Cerebellum` and `CurriculumManager` are R11-tracked types, recorded by the
  runtime construction ledger and listed in the static quarantine scan. They
  are built once, in `bootstrap.py`, as authority adapters.
- `deps.py` serves those single instances; before this slice it built a fresh
  cerebellum on every request.
- The skill store is wired to that cerebellum, so compile-on-promotion now
  happens in the same request. The `get_skill_memory` docstring that claimed
  this while it was false is corrected.
- The `facts=` hook on the skill and lesson stores stays unwired **on
  purpose**: it would launder learned text into "approved" facts (T16). A test
  pins it.
- The shared cerebellum's cache is swapped whole, so concurrent requests
  cannot trip "dictionary changed size", which callers would read silently as
  "no reflex".
- One writer per learning table: an AST scan of every SQL write in `aios/`
  against an owner map discovered from the code fails on any new writer.

**Not done, deliberately:** the live path's `owns_store` fallbacks are not
removed. In production they are unreachable, because R11 guarantees a single
authority-owned instance of each store. Removing them would edit
`generate_pipeline.py` (organ 32) and break tests that pin fake-store
preservation, for no production effect. The store switch in slice 2.4 happens
behind the authority either way.

**Organ cost:** `deps.py` changes, so organs 25, 27, 28, 29, 33, 34, 38 and 42
are re-gathered: at the PR's head so the PR is green, then at master's tip
after the squash.

## Found while starting

- **Hotfix #375:** a regression from #373. While the stop was engaged, the
  read-only skills, trails and mirror-snapshot routes answered 503, because
  `get_cerebellum`'s per-request compile sweep raised. Fixed in the
  cerebellum, which owns no organ.
