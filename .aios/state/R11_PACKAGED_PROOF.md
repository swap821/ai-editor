# R11 packaged proof — the definition, and the first runtime evidence

**2026-09-13.** R11 ("One Memory Authority") has read *"Packaged runtime proof
stays open"* in `PRODUCTION_CONVERGENCE_LEDGER.md` since July. It is the only
PARTIAL wave.

It never closed because **the obligation had no definition.** Nobody had written
down what would satisfy it, and a proof obligation with no definition cannot be
discharged by any amount of work.

## What was standing in for it, and why neither is the proof

**A static AST scan.**
`tests/test_memory_architecture.py::test_legacy_memory_construction_is_explicitly_quarantined`
asserts that only `bootstrap.py` names a legacy constructor. It matches
`ast.Name` only. Measured against six ways to construct a store:

| shape | static scan |
|---|---|
| `SkillMemory()` | caught |
| default-arg at import time | caught |
| `skills.SkillMemory()` — module attribute | **invisible** |
| `from ... import SkillMemory as S; S()` | **invisible** |
| `getattr(m, "SkillMemory")()` | **invisible** |
| `factory(SkillMemory)` — indirection | **invisible** |

Four of six. This is the same blind spot found in the governed-wiring ratchet a
week earlier — matching `ast.Name` and missing `ast.Attribute` — in a different
file.

**The `memory_provenance` runtime probe.** It constructs `MemoryAuthority`
itself, on a scratch database, and checks the authority's *own* semantics:
unverified recall stays advisory, promotion preserves provenance, the record is
durable. All true, and none of it shows the deployed system using the authority.

Both answer *"does a file NAME a constructor"*. R11 claims something else: that a
**running** system routes through the authority. Artefact-exists versus
behaviour-happens — the same distinction that turned 54 green organs into 13 in
the same week this was written.

## The definition

> In a real run, every physical memory store constructed must have been built by
> `aios/application/memory/bootstrap.py` — read from the run itself, not from
> source text.

## The observable

`aios/memory/construction_ledger.py`. The nine legacy store types
(`EpisodicMemory`, `SemanticMemory`, `SemanticFacts`, `SkillMemory`,
`MistakeMemory`, `PheromoneStore`, `WorkingMemory`, `CouncilMemory`,
`DevelopmentTracker`) record their own construction and the file that asked for
them.

* **Durable**, to `<data_dir>/memory-construction.jsonl` — because the process
  that *asks* ("was anything built outside bootstrap?") is not the process that
  *answered*. A packaged proof runs beside the server, not inside it.
* **Cheap** — `sys._getframe` rather than `inspect.stack()`, which resolves
  source context for every frame and has no business in a constructor. Each
  `(type, origin, line)` is recorded once per process, so a hot path cannot grow
  the file without bound.
* **Never raises.** A tripwire that can break a constructor converts an audit
  feature into an outage.
* **Gated** by `AIOS_MEMORY_CONSTRUCTION_LEDGER` (default on), read live rather
  than captured at import — capturing at import would make it untestable, since
  a test would have to win a race against module import.

`violations()` is the pass condition expressed as code.

## First runtime evidence

A real FastAPI application boot, 2026-09-13:

```
constructions during a real API boot: 7
    7  aios/application/memory/bootstrap.py

constructions OUTSIDE bootstrap.py: 0
```

**This is the first evidence for R11's claim that is not a source scan.**

Proven to bite, not assumed: `tests/test_memory_construction_ledger.py` plants
the four shapes the static scan calls invisible and watches the tripwire record
every one, then confirms the real bootstrap path produces zero violations.

## What this does NOT close

Stated plainly, because the point of this document is that vague obligations
never close:

* **The tripwire observes a RUN, not all possible runs.** A code path never
  exercised is never checked. This is strictly stronger than a static scan and
  strictly weaker than a proof over all executions.
* **Promoting R11 out of PARTIAL additionally requires the full packaged Compose
  lifecycle** — all seven services up together, with the gateway fronting real
  traffic. Measured 2026-09-13, that is assembled **nowhere**: not CI, not
  local, not nightly. Only the `executor` service is ever brought up.

**That, and not this proof, is now R11's blocker** — and it is a concrete,
nameable one rather than an undefined obligation.

## How to discharge it

1. Bring the packaged stack up (`docker compose up` — all services, not just
   `executor`).
2. Drive real memory-producing work through the gateway.
3. Read `<data_dir>/memory-construction.jsonl` from the host and assert
   `violations()` is empty.

Step 1 is the part nothing currently does.
