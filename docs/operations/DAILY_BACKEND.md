# The daily backend

*2026-10-29, the operator's ask: "make the daily animal boring".*

The daily backend is started by one tool, with every setting the operator has chosen.
Before this, the settings lived in an agent's scratch script, and a backend started any other way failed silently:
- its scope identity differed, so every reflex he had earned stopped matching;
- or the live learning key was missing, so an activation could not be signed;
- or it inherited his user-wide `AIOS_ROUTER_CLOUD_TASKS=reasoning,coding`, so a coding turn on `auto` went to the cloud first.

## Use

From the repository root, in PowerShell:

```
.venv\Scripts\python.exe tools\daily_backend.py up       # start, then check
.venv\Scripts\python.exe tools\daily_backend.py check    # would each reflex serve?
.venv\Scripts\python.exe tools\daily_backend.py status
.venv\Scripts\python.exe tools\daily_backend.py down
```

`up` does the following, in order:
1. Starts Ollama if it is down, and Docker Desktop if it is not reachable.
2. Refuses if the sandbox image for the current `requirements.txt` is not built, and prints the build command.
3. Reads the keys it needs from Windows Credential Manager, in memory only.
4. Starts the executor service on :8081 and the backend on :8000, writes `data/services/daily.json`, and runs `check`.

## What it sets

| Setting | Value | Decided |
|---|---|---|
| `AIOS_SCOPE_ROOTS` | `training_ground;lab;work`, in that order | 2026-10-28 (`WORK_SCOPE.md`) |
| `AIOS_TASK_SCOPE` | `work\ai-editor` | 2026-10-29 (#554) |
| `AIOS_CONTAINER_IMAGE` | `aios-verify:<first 12 of the sha256 of requirements.txt>` | 2026-10-28 |
| `AIOS_EXECUTOR_TIMEOUT_S` | `120` | 2026-10-28 |
| `AIOS_REPLAY_APPROVED_COMMANDS` | `1` | 2026-10-19 |
| `AIOS_ROUTER_CLOUD_TASKS` | empty, so `auto` stays local; `--cloud-tasks reasoning` opts in for one launch | 2026-10-29 |

`AIOS_ROUTER_CLOUD_TASKS` is always set by the tool, so a value inherited from the user environment never decides where a turn goes.

The user-wide `reasoning,coding` still reaches every other process he starts. Removing it is his choice:

```
[Environment]::SetEnvironmentVariable('AIOS_ROUTER_CLOUD_TASKS', $null, 'User')
```

Separately, Bedrock is no longer offered when no credential could sign a request (`aios/core/bedrock.py::credentials_available`). With `auto` opted into the cloud and no AWS key loaded, a turn now goes straight to the local model, and no Bedrock attempt is made or ledgered.

## What `check` says, and what to do

`check` is read-only and calls no model. It asks `Cerebellum.readiness`, under the scope binding the backend uses, whether each learned reflex would serve its own request now. It exits 0 only when at least one reflex is ready and the sandbox image is present.

| Reason shown | Meaning | What brings it back |
|---|---|---|
| `not applicable: ...` (a scope) | The backend runs under a different scope identity from the one the reflex was earned in | Start the backend with this tool |
| `would ask for approval: replay of approved commands is off` | Started without `AIOS_REPLAY_APPROVED_COMMANDS=1` | Start it with this tool |
| `would ask for approval: no approval of exactly this command ...` | No recorded approval of that exact command, by him, in this workspace | Approve that exact command once in a normal turn |
| `stale, and the first matching turn will withdraw it` | A file the skill touches changed since he activated it, for example after refreshing `work/ai-editor` | Review the change, then re-activate with `tools/activate_skills.py`, **before** the matching request. A matching turn withdraws it, and after that only re-activation brings it back |
| `its skill is not active ...` | The skill was suspended or retired | Re-activate it; that is his act |
| `... is RED here` | The command is refused outright | Nothing; RED is never replayed |

After refreshing the work checkout (`git -C work/ai-editor pull --rebase origin master`), run `check` before relying on a reflex.

## Proving it

- **Earning:** a reflex is earned on a real test with the operator's proof script, run as `--target tests/<file>`: three approved turns, his activation, then a request served with zero model calls.
- **Serving:** `--serve-only --target ...` proves already-earned reflexes still serve after a restart.
- **Records:** the exact bytes of each script he runs are committed with its record under `docs/learning/`.
