# Phase 7 design: prove the guards bite

*Plan: "the learning loop, held to the cage's standard", Phase 7. Property 13:
"the guards bite, and the attacks were real ... Mutation probe covers every
decision branch of every guard."*

## 7a as built (2026-10-05): a standing mutation probe, with branch coverage

### What was there before

Every slice from Phase 0b to 4c-3 shipped with a mutation check: each guard
it added was broken on purpose, and a named test had to fail. Those checks
lived in throwaway harnesses, one per slice, run once. Nothing re-ran them,
and nothing said which branches of a guard no mutation had ever touched.

### The instrument

`scripts/learning_mutation_probe.py` with one catalogue,
`scripts/learning_mutation_catalogue.json`.

- **One catalogue.**
  - 251 carried entries: every slice's hand-written mutations that still
    apply to the code.
  - 270 generated entries: an `always` and a `never` mutation for each
    decision point of a named guard.
  - 74 retired entries: kept with the reason they no longer apply, never
    deleted.
- **Two numbers, never one.**
  - **Kill score.** A kill is pytest exit 1 only. A collection error, a
    missing test or a crash proves nothing about the guard.
  - **Branch coverage.** For each named guard function (61 of them, grouped
    by threat), the probe enumerates its decision points: every `if`/`while`
    condition, conditional expression and comprehension filter. It counts
    those a KILLED mutation's text overlaps. An unattacked branch is
    reported by line.
- **INERT is a reasoned exception, never a pass.**
  - A survivor named in `INERT` is reported as INERT with its reason.
  - Each reason was checked against the code before it was written: it
    names why no test could observe the mutation.
  - An INERT entry is still run every time. If a future test kills it, the
    report shows it.
- **Safe to run on a working tree.**
  - Refuses if any catalogue target has uncommitted changes.
  - The baseline (the named tests, unmutated) must pass.
  - Each mutation is journalled with the file's original bytes before it is
    written. A run killed mid-mutation (on Windows no handler runs) is
    restored by the next start, and its results are void.
  - Every file is verified byte-identical at the end.
- **Resumable, bound to its tree** (`--ledger PATH --budget S`). A full run
  takes hours, and on this machine long runs are reaped.
  - The ledger names the tree it was started on: HEAD's `aios`, `tests`,
    `scripts`, `tools`, `pyproject.toml`, `pytest.ini`, which must be clean.
    A ledger from another tree is refused, never extended.
  - The baseline runs once per ledger. Each result is recorded the moment it
    lands.
  - No mutation starts after the budget, so no run is killed mid-mutation to
    stop.

### How the generated mutations were triaged

For each of the 15 guard modules, the generated mutations ran first against
the module's full test set. That set was widened from the catalogue-derived
one, which had missed tests written for exactly those branches. Each survivor
was then either:

1. **killed by a new test**, with a positive control wherever the negative
   could pass vacuously; or
2. **documented INERT**, with the reason checked against the code.

No production code changed in Phase 7. Every survivor was an untested branch
or an equivalent mutation, not a defect. The branches worth naming:

| Branch | Why it matters |
|---|---|
| `operator_text`'s role filter | The model's own turns and the system prompt are not the operator's words, so a recalled command the model echoed is still memory's (`recall_taint`). Nothing pinned it. |
| `_recall_memory`'s judge selection | With the LLM judge on, the *governed* judge (advisory gate) is asked, never the bare default, which is an ungoverned model call. With the judge off, no judge is asked, even one a caller passes. |
| `CRAG_EXTERNAL` as master switch | Off, an enabled cloud source is never sent the query. A confident local recall never leaves the machine. |
| `LearningService.activate_skill`'s proof checks | The service re-checks the consumed capability proof behind the route's gateway. No refusal was driven at the service: expired, revoked, blank operator, other action, other skill's route, GET, an impostor object with a valid proof. Each now is, and moves nothing. |
| `stamp_for_activation` | An activation fills only what a candidate lacks. A reviewed skill's contract is never rewritten. |
| `plan_executable`'s base | A freshness plan is checked where the read happens (PROJECT_ROOT), a test runner's where the command runs (the scope root's parent). In the test tree the two coincide, which is why that mutation survived. The test separates them as production does. |
| Cerebellum: a reflex retired mid-match | A retirement that lands between loading the playbooks and choosing one, whose skill could not be suspended, is honoured. |
| Cerebellum: only true ties are "ambiguous" | M5 counts abstentions; a third, clearly weaker reflex is not one. |
| Cerebellum: a skill with an unreplayable step backs nothing | That is the retirement tool's question. Dropping `create_file` would make a playbook replaying its readable half look backed. |
| Recall under the emergency stop | A skill that cannot be numbered (a write) is left out of a read, not allowed to fail it (#375). |

### INERT, with reasons

| Mutation | Why no test can observe it |
|---|---|
| `gen:self_model_handler:SelfModelHandler.recall:117:never` | recall(None) looks up a None key, and none is ever stored: __call__ returns before caching a turn that names no principal. The answer is None either way; the early return is defence in depth. |
| `gen:tool_agent:ToolAgent._recall_taint:2044:never` | with no taintable argument or no recalled memory, recall_envelope.recall_taint finds nothing to match and returns [] -- the early return is a shortcut (checked directly: recall_taint('', m, o) == [] and recall_taint(c, '', o) == []). |
| `gen:tool_agent:ToolAgent._composition_capped:2004:never` | a read carries no command, and the gateway refuses an empty one (_gateway_refuses({}) is True), so a read is never held at the cap even without the early return; the return states the rule. |
| `gen:adapters:MistakeMemoryAdapter.promote:931:always` | prior is read only for the attestation, and _attest returns at once when the adapter has no provenance writer: the value is never used. |
| `gen:adapters:SemanticFactsAdapter._admitted_triples:396:never` | an empty triple set joins nothing in json_each: the query returns no rows and the result is the same empty set; the return saves a query. |
| `gen:adapters:SemanticFactsAdapter._admitted_triples:416:never` | 'the newest row decides': duplicate ACTIVE rows of one principal's triple cannot be written through the store (add_fact refuses them), and an older signed row of the same triple vouches for the same content (plan Phase 4c-3). |
| `gen:adapters:SemanticFactsAdapter.traverse_weighted:634:never` | ungated, _admitted_triples admits every asked triple, and the store's walk returns only edges on paths from the start: sorted by depth, each edge's subject is already reached, so the filter keeps exactly the edges the shortcut returns. |
| `gen:institutional_skills:InstitutionalSkillAdapter.record_reuse:715:never` | forces the reason to 'verification' on a success too, and SkillLifecycleAuthority.apply_reuse_outcome reads the reason only on a failure (record_success takes none; demotion is skipped on success). |
| `gen:cerebellum:Cerebellum.match:749:never` | a short-circuit: with no compiled playbook the loop adds no candidate and records no decision, so match returns None either way; the only work skipped is reading the library, and _activated swallows every error (it cannot raise). |
| `gen:cerebellum:Cerebellum._activated:562:always` | the comprehension filter sits inside `if steps and all(step is not None for step in steps)`, so there every step is not None and the filter is already always true. |
| `gen:reflex_contract:validated_version:161:always` | a missing target is hashed through read_directory's deterministic refusal ('[ERROR] Not a directory: <target>', blocked) instead of 'missing'. A version is only ever compared with one computed by the same function, so it stays a pure function of the target and its absence: staleness is unchanged. |
| `gen:recall_envelope:model_visible:173:never` | a short-circuit: _cloud_form('') is '' (the privacy filter leaves empty content empty, and on failure returns the text), so an empty text yields [text] either way. |
| `gen:service:LearningService.activate_skill:381:always` | stamp_for_activation returns the skill itself only when it changed nothing; saving that unchanged record is a no-op write SkillRepository.save allows in every activatable state (same state, no contract field rewritten). |
| `gen:service:LearningService.activate_skill:386:never` | SkillRepository.transition_state returns the record in the target state or raises (KeyError, or check_transition's refusal); it never returns None or another state. |
| `gen:turn_pipeline:_recall_memory:550:always` | refine_context(query, []) is '' by its contract ('empty when there is no real content'), the value the guard yields. |
| `gen:turn_pipeline:_recall_memory:561:always` | trusted is never empty here: an empty one returned None at `if not hits` (hits = trusted), so the condition is already always true. |
| `gen:turn_pipeline:_recall_memory:583:always` | as _recall_memory:561 -- trusted is never empty at the plain block. |
| `gen:turn_pipeline:_recall_memory:565:always` | unverified is [] (Phase 0b), and refine_context(query, []) is ''. |
| `gen:turn_pipeline:_recall_memory:565:never` | unverified is [] (Phase 0b): the condition is already always false. |
| `gen:turn_pipeline:_recall_memory:571:never` | unverified_body is '' because unverified is [] (Phase 0b): the condition is already always false. |
| `gen:turn_pipeline:_recall_memory:587:never` | unverified is [] (Phase 0b): the condition is already always false. |
| `gen:service:LearningService.activate_skill:391:never` | as activate_skill:386 -- transition_state returns the record in the target state or raises. |

**Dead code, stated.** Since Phase 0b (#372), `_recall_memory`'s
`unverified` list is the constant `[]`, so its branches can never run. Their
`always` mutations, which add an empty unverified section, are killed by a
test that no recall block ever carries one. Their `never` mutations are
INERT. Removing the dead branches is a cleanup for the organ-31 file's owner;
it is not done here.

### Evidence

- **The full run (2026-10-05).**
  - Report: `docs/learning/mutation/phase7_probe.json`, made with `--ledger`
    across fifteen processes.
  - **521 mutations: 499 killed, 22 INERT, 0 survivors.** Every mutation
    applied.
  - **Branch coverage: 192 of 193 decision points**, in 61 guard functions,
    attacked by a killed mutation. No named guard is missing.
- **The one unattacked branch is dead code.** It is
  `aios/api/turn_pipeline.py` `_recall_memory`, `if unverified` (the CRAG
  refinement of the unverified list). Both of its mutations are INERT,
  because no state reaches it since Phase 0b.
  - The probe counts it unattacked, and it is.
  - The number is 192/193, not 100%, until the dead branch is removed.
- **Bound to its tree.** The ledger's tree identity is `86aa3418…`:
  HEAD's `aios`, `tests`, `scripts`, `tools`, `pyproject.toml` and
  `pytest.ini`. The run was made at `d3cbccda`, before this branch was
  rebased onto master `f40b8090`.
  - The rebase changed none of those trees.
  - One later commit adds `tests/test_learning_properties.py`, which no
    catalogue entry names. It cannot change a probe result.
- **Property tests (7b, below):** six invariants, 24 tests. Ten hand
  mutations of the code they guard were all killed.
- **The structural red-team reel holds.**
  - `docs/learning/redteam_phase4c3_structural.json` ran at `886576a1`. Its
    `aios` tree `2026e6dd…` and runner sha256 `2e9643d0…` both equal this
    branch's, so its result is this tree's: **18 held, 0 breached, 0 not
    reached.**
  - **Six blocked.** Five are behavioural (RT-02, RT-04, RT-14, RT-15,
    RT-19): they need a model and the operator's credentials. RT-11 is not
    yet built: it needs a real sandboxed test run.

## 7b as built (2026-10-05): the core invariants, as properties

`tests/test_learning_properties.py`.
- Each invariant is checked on generated cases against an independent model
  of the rule, not on hand-picked examples.
- `hypothesis` is not installed, so cases come from a seeded
  `random.Random`, four seeds per invariant. A failure names its seed and
  case.

| # | Invariant | What the generator varies |
|---|---|---|
| 1 | The recall gate admits a row exactly when its newest record is signed by a pinned live key over its current content, naming the principal asking. | The writer (pinned live, unpinned live, harness, unsigned), the owner, who is asking (including no one), an edit, a later unsigned record. |
| 2 | A skill serves a principal exactly when the newest record of it is the operator's signed activation of its current content, for its owner. | Random lifecycle walks: allowed, refused and the operator's road, plus state flips written straight into the database. A walk must serve at least three times per seed, so it cannot pass by refusing everything. |
| 3 | Nothing fenced, `>`-quoted, quoted (straight, curly, guillemets) or forwarded reaches the reflex directive, and every authored word does. | The mix and order of authored and foreign segments, the quoting form, a forwarded tail. |
| 4 | Only user turns are authored, with recalled envelopes removed. | Roles, the count of turns, envelopes, string or list content. |
| 5 | The write cap admits exactly what the rolling window has room for, so never more than the cap per window. | The cap, the tables, the gaps between writes (the 60.0 s boundary included). |
| 6 | A skill's identity is one-to-one with (principal, arc). | Principals (including none), arcs. |

**Each property bites.** Ten hand mutations of the production code each
guards were all killed:
- the gate's owner check and its signature check;
- the transition journal;
- curly quotes, and the forwarded tail;
- the role filter, and envelope removal;
- the cap's `>=`, and the window boundary;
- the principal in the identity.

The first draft of property 2 passed while never serving a skill: its walk
sat in the terminal states. It now steers along the operator's road part of
the time and asserts that it served.

## Not in Phase 7's agent work

- **The behavioural red-team reel on the hardened tree.** It needs a model
  and credentials (operator). The structural reel stands at #440's tip:
  18 held, 0 breached. Phase 7 changed no production code, so the `aios`
  tree it ran on is this one.
- **One human-in-the-loop adversarial campaign** (organ 46's model). This is
  the operator's.
- **RT-11 (T9, a forged verifier report)** is not yet built. It needs a real
  sandboxed test run, to separate the runner's own report from stdout the
  test writes. Docker is absent here, and the container executor's Linux
  defects are open.
- **Removing `_recall_memory`'s dead unverified branches.** That is the one
  change that would make branch coverage 193/193. It edits organ 31's file,
  so it needs a re-gather, and it is a cleanup, not a guard. It is left to
  that file's next change.
