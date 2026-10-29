# The work scope: real code GAGOS may act on

*Operator decision, 2026-10-28: "widen the scope and sandbox honestly". He chose
this design from three: a `work/` scope root, rather than a checkout inside
`lab/` or per-task scope binding. Per-task binding inside it was added on
2026-10-29 (below).*

## Why

Until now the operator's backend could not verify a single test of this
repository:

- its scope roots were `training_ground/` and `lab/` only, so `pytest tests/...` was out of scope;
- its sandbox image (`aios-worker:local`) carried only pytest, and `tests/conftest.py` imports FastAPI.

Every learned reflex that served a live turn was therefore a prover toy. The
2026-10-28 real-code proof had to run on a separate proof backend
(`docs/learning/organic_reflex_proof_2026-10-28/`).

## What it is

| | |
|---|---|
| Scope roots | `training_ground;lab;work`, **training_ground first** so commands still run from the repository root (`scope_lock.command_cwd()` is the parent of the first root) |
| `work/` | gitignored; holds working checkouts, today `work/ai-editor`, a git worktree of this repository on branch `gagos/work` |
| Sandbox image | `aios-verify:<sha12>`, built from `Dockerfile.verify`: `requirements.txt` with CPU torch, git, and no copy of the code. The first build, `aios-verify:83b20d9b8dbd`, is 2.39 GB, against 18 GB for the CUDA app image. Same sandbox flags as every image |
| Command budget | `AIOS_EXECUTOR_TIMEOUT_S=120`. The default stays 30 s, bounded to 5–600. At 30 s, every test file that loads the API app was killed (33–41 s measured) |
| Set where | only in the backend's launch environment (below). `AIOS_SCOPE_ROOTS` is a frozen guardrail, read from the process environment and ignored in `.env`. Setting it user-wide would leak into test runs |

## What it allows, and what it does not

- **GAGOS can read, test and, with the operator's approval, edit code in `work/ai-editor`.**
  - The checkout is not the one running.
  - Its changes reach master only as a commit on `gagos/work` that the operator turns into a reviewed PR.
- **The live checkout stays out of scope.** That includes its `aios/security/` spine, `.aios/state/` ledgers, `data/` stores and `.env`.
  - An edit there is still refused.
  - The sandbox still mounts the repository root read-only and makes only the scope roots writable.
- **`work/ai-editor` has its own copy of the frozen spine, and GAGOS can edit that copy.** It changes nothing that runs. A PR touching it meets the frozen-core checks and the operator.
- **"Clear the sandbox" cannot wipe `work/`.** That route is RED, refused at the action boundary; `tests/test_security_api.py` asserts 403 and that the files survive.
- **Everything learned earlier stops matching.**
  - Skills and exact-command approvals are keyed to the scope identity, which becomes `lab,training_ground,work`.
  - So the prover-toy reflexes (playbooks 5 and 6), the self-corpus one (15) and the one recorded approval no longer apply.
  - Real reflexes are re-earned on `work/ai-editor`.

## Running the backend with it

PowerShell, from the repository root:

```
$env:AIOS_SCOPE_ROOTS = "$PWD\training_ground;$PWD\lab;$PWD\work"
$env:AIOS_CONTAINER_IMAGE = "aios-verify:<sha12>"
$env:AIOS_EXECUTOR_TIMEOUT_S = "120"
.venv\Scripts\python -m aios
```

## Keeping it honest

- **Rebuild the image when `requirements.txt` changes.**
  - The tag and the `requirements.sha256` label name the requirements it holds.
  - A stale image turns a missing package into an `ImportError` that reads as a failing test.
- **Refresh the checkout before relying on it:** `git -C work/ai-editor pull --rebase origin master`. A verify measures `work/ai-editor` as it stands, not master.
- **Paths need care.**
  - Commands resolve against the repository root, so `pytest work/ai-editor/tests/test_relevance.py -q` works.
  - File tools resolve a *relative* path against the first root, `training_ground/`. To edit the checkout, give them an absolute path, such as `C:\Users\kumar\ai-editor\work\ai-editor\...`.

## Per-task binding (2026-10-29)

`work/` is one root for every turn, so a turn about one project could still
change another. A forge turn can now be confined to one directory
(`aios/application/turns/task_scope.py`).

**Where the scope comes from**, in order:
1. the request's `scopeRoot`, which the client declares;
2. `AIOS_TASK_SCOPE`, set in the backend's launch environment;
3. neither: no binding, exactly as before.

It never comes from the model. A scope the model could pick would be a sandbox
it chose for itself.

**What can be bound:** a declared root, or a directory directly inside one,
which is one project, such as `work/ai-editor`. The server lists these itself.
The client's string is only compared with those names and never handed to the
filesystem.

**It can only narrow.** The frozen scope lock judges the resolved directory, so
a link that points outside is refused. A declared scope that cannot be honoured
is refused with a 400, never run unbound.

**What a bound turn changes:**
- **Containment.** The gateway's command check, the file tools, and the
  executor's working directory and writable mounts all read the bound root.
  Creating, editing and running commands are narrowed. Reads are not: the file
  tools still read anywhere in the project.
- **Where commands run.** Commands run from the bound root's **parent**
  (`scope_lock.command_cwd`). Bound to `work/ai-editor`, that is `work/`, so a
  test is `pytest ai-editor/tests/test_relevance.py -q`. The model is told this
  in the turn's system guidance, because the tool descriptions name only
  `training_ground/`.
- **What earned trust is filed under.** Approvals, earned autonomy and
  reflexes are keyed to the active scope (`autonomy.workspace_id`,
  `reflex_contract.scope_identity`). Something earned in a bound turn applies
  only to turns bound the same way. A reflex the operator wants to serve daily
  turns must be earned under the scope those turns run in.

**How it is bound.** The turn coordinator advances the forge's stream on
thread-pool threads, each step in a fresh copy of the request's context. So the
turn is prepared inside the binding, and the binding is opened and closed around
each step, inside it.

**Proof** (`tests/test_task_scope.py`): the same model asks to
`mkdir training_ground/build`.
- Unbound, or bound to `training_ground`: it pauses for approval.
- Bound to `lab`: it is a scope violation.
- Bound to `aios`: the request is a 400.

Without the route's wiring, the last two fail.

**To bind every turn to the checkout**, add this to the launch environment
below:

```
$env:AIOS_TASK_SCOPE = "work\ai-editor"
```

## Measured, 2026-10-28 (master `c62e85ef`)

All of these ran with the settings above, through the backend's own `deps.get_executor().execute_approved`, the path a human-approved command takes.

| Check | Result |
|---|---|
| `pytest work/ai-editor/tests/test_relevance.py -q` | OK: 4 passed, about 13 s |
| `pytest work/ai-editor/tests/test_security_api.py -q` | OK: 10 passed, 35 s. TIMEOUT at the 30 s default |
| `pytest work/ai-editor/tests/test_activate_skills_tool.py -q` | OK: 17 passed, 30 s. TIMEOUT at the 30 s default |
| `pytest tests/test_relevance.py -q` (the live checkout) | BLOCKED, RED: "Human approval cannot authorise a RED action: Scope violation" |
| The gateway on `rm -rf work/ai-editor` | RED |
| Scope of the live `aios/security/`, `tests/`, `.aios/state/`, `.env` and `data/` by absolute path, and of a `work/../` traversal | out of scope |
| Which `aios` a `work/` test imports, under `pytest` and with the live root first on `sys.path` | `/workspace/work/ai-editor/aios` in both cases: the checkout under test, never the live code |
