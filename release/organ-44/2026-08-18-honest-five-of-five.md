# Organ 44 — an honest 5/5, and the nine defects between us and it

- **Measured**: 2026-08-18, `gemini-3.7-flash` via Vertex (`global`), 3 repeats
- **Result**: `[4, 4, 5]` — **mean 4.333 of 5**, with one clean **5/5**
- **Baseline this replaces**: `gemini-2.5-pro` at 1.125, then 2.667

## The 5/5 run, every step

```
tdd-workflow          2/2   verified_failure -> verified_success   (TDD cycle, correct)
iterative-refinement  2/2   verified_success x2
multi-module          2/2   verified_success x2
error-handling        1/1   verified_success
data-pipeline         2/2   verified_success x2

FINAL: 5/5 mission runs passed (100%)
rejected 0 | provider_errors 0 | loop_trips 0
```

No mission was edited, no verifier weakened, no pass criterion relaxed. Every
step met its declared expectation.

## The arc

| Configuration | mean |
|---|---|
| gemini-2.5-pro, original harness | 1.125 |
| + step budget (5 to 16) and evidence-based scoring | 2.667 |
| gemini-3.7-flash, adapter + allowlist fixed | 3.000 |
| **+ sandbox import fixed** | **4.333** |

## Nine infrastructure causes, every one looking like model quality

| # | Cause | Symptom | Origin |
|---|---|---|---|
| 1 | GEMINI_LOCATION=us-central1 | 404, "model does not exist" | pre-existing |
| 2 | thought_signature not replayed | 400 after the first tool call | pre-existing |
| 3 | Raw bytes in the conversation | TypeError mid-turn | introduced |
| 4 | History ending on a model turn | 400 | pre-existing |
| 5 | Allowlist refusing pytest -v | 4 of 5 rejected | pre-existing |
| 6 | Inherited 1024-token budget | empty turns, all unverified | introduced |
| 7 | Privacy filter corrupting tool args | 400, invalid JSON | pre-existing |
| 8 | Measurement branch missing fix 5 | rejected again | introduced |
| 9 | Sandbox conftest a stub | ModuleNotFoundError | pre-existing |

Six pre-existing and latent, three introduced while doing this work. Four of the
six were invisible because nothing had ever exercised that path: no Gemini 3.x
model had been called, and no OpenAI-compatible provider was configured.

## The one that mattered most, and how it was missed

Defect 9 was worth 1.333 missions per run on its own.

`training_ground/` carries an `__init__.py`, so it is a package, and the verify
command runs from the repo root. Under pytest prepend import mode a test inside
a package gets the package PARENT on sys.path and never the package directory,
so importing a module sitting beside the test raised ModuleNotFoundError. The
conftest that should have handled it was a one-line stub.

The correlation sat in the data for hours before anyone read it:

    multi-module          pass pass pass   <- the ONLY prompt naming the package path
    tdd-workflow          FAIL FAIL FAIL   <- No module named 'calculator'
    iterative-refinement  FAIL pass FAIL   <- No module named 'sorted_insert'

Those failures were recorded as `verified_failure` and reported as the model
writing a test that contradicts its own code -- a capability ceiling. The model
code was correct and the sandbox could not import it.

**A score is not a diagnosis, and neither is a failure category.**
`verified_failure` means the verifier returned a failing verdict; it says
nothing about whose fault that verdict was. Reading the actual error text was
the whole difference.

The operator's "this model should be able to do this" was better evidence than
the harness own classification. That instinct is worth treating as a signal to
look harder at the environment, not as a claim to be corrected.

## Remaining variance

The two non-perfect runs each lost exactly one mission, to a different flag:
one form the harness auto-verify itself relies on (clearing inherited addopts),
and `-k test`, which is correctly refused because it changes which tests run.

So the residue is flag roulette rather than capability. Whether the one form the
verifier itself uses should be admitted is an open operator decision,
deliberately not taken here.
