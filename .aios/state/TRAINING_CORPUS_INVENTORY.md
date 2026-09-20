# Training-corpus inventory — 2026-09-20

**Question asked:** which local projects have a runnable, currently-green test
suite, and can therefore serve as a real training corpus instead of the
synthetic `training_ground/` toys?

**Answer: none of them.** This is a read-only inventory; nothing was copied,
run, or modified.

## What is on the machine

Enumerated every git repository under the user profile (depth 2), then excluded
pytest scratch worktrees under `pt/`, agent skill directories, and
`ai-editor-frontend-living-mirror` (Codex's worktree — out of scope by
standing instruction). Six real projects remain:

| Project | Stack | package.json files | Any test script? | Test files found |
|---|---|---|---|---|
| `campus-placement` | MERN (backend + react-frontend) | 2 | no (one is the npm `exit 1` default) | 0 |
| `chat-app-project` | MERN (backend + frontend) | 2 | no | 0 |
| `crypto-tracker` | single-package JS | 1 | no | 0 |
| `kanban-project` | kanban-api + kanban-board | 2 | no | 0 |
| `mini-ecommerce` | client + server | 2 | no | 0 |
| `my-portfolio` | portfolio-backend + frontend | 3 | no (one is the npm `exit 1` default) | 0 |

Eleven `package.json` files in total. Not one declares a real `test` script, and
a recursive search for `test_*.py`, `*.test.{js,ts,jsx,tsx}`, and
`*.spec.{js,ts}` (excluding `node_modules`) found **zero** test files anywhere.

## Why this blocks the plan as written, rather than merely complicating it

The plan's two constraints for a real-project corpus were "never train in
place" and "only projects whose suites already pass". The second is not a
preference — it is load-bearing all the way down:

- `verification_strength.derive_strength` mints **STRONG** only from a
  recognized test runner reporting `passed_count > 0` and `failed_count == 0`.
- **STRONG is the promotion floor** for skills, lessons, and curriculum mastery.
- Therefore a training run against a project with no test suite can produce at
  most a WEAK or MEDIUM success, and **no skill can promote, no reflex can
  compile, and no curriculum level can master.**

A run like that would look busy and change nothing — the learning scoreboard
would stay flat and the run would be a vacuous result of exactly the kind this
repo spends its effort refusing. Running one anyway would not be a partial
result; it would be a misleading one.

## The options, honestly stated

1. **Make "add a test suite to this real project" the curriculum itself.**
   The task is real, and its success is genuinely test-runner-verifiable: the
   suite the agent wrote either runs green against unmodified source or it does
   not. It also converts each project into a usable corpus for everything
   after. The open risk is real and needs a design answer, not a hope: an agent
   that writes both the tests and the code can satisfy its own grader, and the
   STRONG definition does not catch that.

2. **Use `ai-editor` itself, via a git worktree copy.** It is the one
   repository on this machine that meets the stated bar — a large suite that is
   currently green. "Never train in place" is satisfiable exactly as the plan
   describes (worktree isolation, source tree byte-identical before and after).
   The consideration is that the system would be learning on its own source.

3. **Clone public repositories with green suites.** Weakest of the three:
   it adds a network and trust surface for a benefit the first two options
   already deliver.

No option was chosen here. The inventory's purpose was to determine whether D2
is worth anything as specified, and the finding is that it is not — the
precondition it rests on does not hold on this machine.
