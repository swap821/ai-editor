# Learning loop, stage 1 — a write compiles as a check — 2026-09-07

**Result: playbooks containing `create_file` are compilable for the first time,
and replay still cannot write.** Not "does not write" as a property of careful
code — cannot, as a property of the control flow.

## What was actually wrong

`_COMPILABLE_TOOLS` excluded `edit_file` and `create_file`, and the reason was
never safety. It was that **the content was never recorded.** `_workflow_step`
kept only `command / filepath / path / goal`, so a write step was stored as:

```
create_file: filepath=notes.txt
```

There is nothing in that to replay. So the Cerebellum's compiler, which requires
*every* step to parse, refused the whole playbook — a nine-step workflow with one
`create_file` in the middle was discarded entirely and all nine steps re-ran
through the LLM.

## What stage 1 does

Record a **digest, not content**:

```
create_file: filepath=notes.txt, content_sha256=5891b5b5…be03
```

Content itself would be the wrong fix. These step strings go to L3 semantic
memory and are scrubbed on the way, so file bodies would become a standing
secret-leak surface — the scrubber would be the only thing between a written
credential and long-term storage. A digest is replayable-as-a-check and carries
nothing to leak.

Replay semantics, deliberately narrow:

```
target exists AND digest matches  ->  success, no write   (idempotent)
target missing OR digest differs  ->  ABSTAIN, decompile
```

**Stage 1 can only confirm what is already correct.** That is the whole of it.
Real replayed writes are stage 2 and are not in this change.

## Why "cannot write" rather than "does not write"

`replay` intercepts `_CONFIRM_ONLY_TOOLS` **before `dispatch_fn` is reached**.
There is no path from a replayed `create_file` to the filesystem — not a guarded
one, none. A future stage wanting real writes has to delete that set, which is a
visible change in a diff rather than a silent loosening.

`test_stage_one_has_no_path_from_a_replay_to_a_write` pins the ordering, so the
interception cannot drift below the dispatch by accident.

## Containment: one derivation, not a second copy

`_confirm_write` asks `scope_lock.is_path_in_scope` — the same function the
gateway asks — rather than resolving paths itself against `config.SCOPE_ROOTS`.

That distinction is not stylistic. `SCOPE_ROOTS` is the **process-start default**;
`get_scope_roots()` is the **live, re-declarable** authority. Deriving containment
from the former while execution uses the latter is precisely the drift recorded
in `ScopeLockAuthority._default_base`, where it was a real escape. A confirm-only
step is read-only, and read-only is not a reason to widen reach.

## Shown failing, three ways

Mutation-tested rather than asserted:

| Mutation | Caught by |
|---|---|
| digest comparison always passes | `test_a_differing_file_makes_the_replay_abstain` |
| interception removed, writes dispatch | all three replay tests |
| scope check removed | `test_a_confirm_only_step_cannot_read_outside_the_sandbox` |

The abstain tests assert the file is **byte-identical afterwards**, so an
abstention that quietly wrote would fail rather than pass.

## The recorder/parser seam

`_workflow_step` (`aios/api/turn_pipeline.py`) writes the step; `_parse_step`
(`aios/core/cerebellum.py`) reads it. That seam has drifted before — when one
left a `key=` prefix the other did not expect, every replay aborted as an unknown
RED command. `test_the_recorder_and_the_parser_agree` asserts the round trip
rather than two independently plausible formats.

The digest is taken off the **end** of the step, as fixed-width hex, so a comma
inside a filepath cannot split it wrongly.

## What this does not establish

Stage 1 has not been observed on a real recorded workflow — it is exercised by
tests and by a round trip through the real recorder, not by a live session that
compiled a playbook and replayed it. The **rate** at which confirmations succeed
in practice is therefore unknown: if recorded files are usually stale by replay
time, every such playbook abstains and the practical gain is zero. That number
needs a live run to know, and this change does not have one.

`edit_file` is digested but still uncompilable — an edit's result is not
determined by its own content the way a create's is.
