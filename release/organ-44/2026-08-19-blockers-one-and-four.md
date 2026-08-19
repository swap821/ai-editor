# Organ 44 — blockers 1 and 4, 2026-08-19

Operator decisions taken 2026-08-19. Every number below was produced after the
change it is attributed to, and the runs are recorded whether or not they
flattered the change.

## Blocker 1 — DISCHARGED at [5, 5, 5]

### The defect: the gate refused the command the harness itself runs

`build_auto_verify_command` is the single source of the forced auto-verify:

```
python -m pytest -o addopts= "training_ground/test_x.py" -q
```

`_auto_verify` surfaces that exact string to the model as the `target` of a step
that just succeeded. `ALLOWED_CMD_RE` refused it:

```python
>>> ALLOWED_CMD_RE.match(build_auto_verify_command("training_ground/test_calculator.py"))
None
```

So a model that imitated the form the loop had just demonstrated had its
mission terminated — recorded in the ledger as model performance.

Two derivations of "what may run" disagreeing: the same shape as the containment
escapes `tests/adversarial/test_control_consistency.py` was written to catch,
here between the verifier and the gate that judges it. **~450 payload-style
refusal cases never found it**, because each asked *is this dangerous?* and none
asked *do these two layers agree?*

`-o addopts=` is load-bearing, not convenience: this repo's `pytest.ini`
contributes a second `-q` (stacking to `-qq`, which suppresses the `N passed`
line the strength parser needs for STRONG) plus `--cov=aios`.

**Widening, and its limit.** Admitted: `-o addopts=` with an EMPTY value.
Refused, and why the general form never can be: `-o` overrides any ini option,
so `-o addopts=--pdb` is flag injection wearing the costume of the one form the
harness needs. The lookahead pins the value to empty — the only shape that can
remove inherited config and never add behaviour.

### First measurement: [5, 4, 5], mean 4.667 — NOT discharged

| run | score | refusals | cause |
|---|---|---|---|
| 1 | 5/5 | 0 | — |
| 2 | 4/5 | 1 | `pytest -v test_sorted_insert.py -o console_output_style=classic` |
| 3 | 5/5 | 0 | — |

The fix worked — 4.333 → 4.667, two runs clean where every prior run lost one.
Run 2 found a *different* output-only `-o` key. pytest's own help calls
`console_output_style` display-only: *"classic, or with additional progress
information"*. The model wrote correct code and lost a mission on formatting.

### The structural finding

That would have been the sixth flag widening: `-v`, `--no-header`, `-s`,
`--tb=`, `-o addopts=`, `console_output_style`. Every one individually correct;
every time a different model reached for a different spelling, because nothing
ever told the agent what would be approved.

**The space of output-formatting spellings is open-ended, so enumeration cannot
close it.** The cohort was partly measuring the agent's ability to guess an
unpublished rule — which is not what organ 44 exists to measure.

### The fix: state the policy (operator decision)

A real operator says what they will sign off. `approval_policy_text()` is that
sentence, prepended to each turn by `compose_turn_text`.

* **Not a widening.** `ALLOWED_CMD_RE` is untouched and still refuses everything
  it refused before, `-o console_output_style=classic` included.
* **Not a mission edit.** The mission prompt passes through verbatim;
  `test_the_mission_prompt_is_sent_unmodified` asserts it survives as an exact
  substring and comes last. Organ 44's forbidden list opens with *no editing the
  missions*.
* **Not free to drift.** A hand-written description of a regex is a THIRD
  derivation, free to drift exactly as `build_auto_verify_command` had. So it is
  pinned from both sides: every example it offers must be admitted by the gate,
  and every flag it calls refused must actually be refused. Narrowing the gate
  now breaks the policy tests instead of silently misleading the agent.

### Second measurement: [5, 5, 5], mean 5.000 — DISCHARGED

Bar set in advance: discharge only on three consecutive clean 5/5.

```
scores       [5, 5, 5]
mean         5.0
clean sweep  True
rep 1: 5/5  steps 9/9  refusals 0  loops 0  tracebacks 0  container_deaths 0
rep 2: 5/5  steps 9/9  refusals 0  loops 0  tracebacks 0  container_deaths 0
rep 3: 5/5  steps 9/9  refusals 0  loops 0  tracebacks 0  container_deaths 0
```

**Verified rather than reported**, because a perfect score deserves the scrutiny
a zero gets:

* 5 missions and 9 scored steps per run, matching the mission definitions — no
  mission silently skipped or shortened;
* **the TDD red phase survived**: exactly one
  `got=verified_failure expected=verified_failure` per run. The model still has
  to write a failing test first. Had the change flattened everything into
  success, this count would be 0 — it is the single most load-bearing check here;
* zero expectation mismatches, and both outcome types present, so the result is
  not a degenerate all-success;
* the local `aios-worker:local` image was confirmed present before measuring, so
  no run was scored against a sandbox that could not start (the defect that made
  the CI job report OK on a 0/1 — see `2026-08-19-cohort-job-fixed.md`).

**What did not change:** the missions, the verifier, the `[VERIFY]` taxonomy,
what counts as a pass, or the 3-of-3 bar. The bar was set before the runs.

## Blocker 4 — DISCHARGED by decision

The enrollment credential is one-time, so a non-TTY run cannot capture it and
repeated runs need a fresh `AIOS_DATA_DIR`. The previous text called that *"a
workaround, not a fix"*.

Operator decision 2026-08-19: **a fresh instance per non-TTY run is the correct
design, not a compromise.** Nothing is shared between runs except the code under
test, which is what a measurement harness should guarantee. Both three-run
measurements above used it — each repeat got its own port, data dir and backend,
and each enrolled cleanly with zero `ProbeAuthError`.

The alternative — a pre-provisioned credential in CI — was rejected as
reintroducing a long-lived stored secret, against AGENTS.md §VII.4.

No code was written for this discharge, because none was needed: the behaviour
already existed and is pinned by 7 tests in
`tests/test_probe_enrollment_credential.py`, including
`test_nothing_is_written_to_disk` and `test_the_source_never_opens_a_file`. What
was missing was a decision about whether the behaviour counted as a fix.
Inventing code to make the discharge look more substantial would have been
theatre.
