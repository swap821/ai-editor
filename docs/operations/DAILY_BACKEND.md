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
0. Makes sure the face answers (see "The face" below). This comes first because the face does not depend on the backend, and a refusal in the steps below must not leave him without one.
1. Starts Ollama if it is down, and Docker Desktop if it is not reachable.
2. Refuses if the sandbox image for the current `requirements.txt` is not built, and prints the build command.
3. Reads the keys it needs from Windows Credential Manager, in memory only.
4. Starts the executor service on :8081 and the backend on :8000, writes `data/services/daily.json`, and runs `check`.

## The face

*2026-11-03, the operator's ask: "plz honestly do all than we will be ready for D14".* The frontend dev server on :5173 used to be started by hand, so after a reboot it was simply gone.

| Command | What it does about the face |
|---|---|
| `up` | If `http://localhost:5173` does not answer, starts `npm run dev -- --port 5173 --strictPort` through `cmd.exe` from `frontend/`: no window, detached, output to `data/services/frontend.log`. Records its pid under `face` in `data/services/daily.json` and reports it. If something already answers, it leaves it alone and says so; a server he started by hand is not recorded as ours. If `frontend/node_modules` is missing it starts nothing and says to run `npm ci` (never `npm install`). |
| `status` | Prints the face's health, and the pid when this tool started it. |
| `down` | Stops only a face this tool started, the whole process tree (`cmd.exe`, npm, node). It does so only while that face still answers: a pid recorded before a reboot may belong to another process by now. |

The face's start does not change `up`'s exit code or anything about the backend: a face that is not up is reported, and the backend's own result decides the exit code.

The watchdog task `\GAGOS\backend` already runs `up` every 15 minutes, so the face now comes back after every reboot and after any crash, with no change to his scheduled tasks. `--strictPort` makes a busy :5173 a visible failure in `frontend.log` instead of a silent move to :5174.

## What it sets

| Setting | Value | Decided |
|---|---|---|
| `AIOS_SCOPE_ROOTS` | `training_ground;lab;work`, in that order | 2026-10-28 (`WORK_SCOPE.md`) |
| `AIOS_TASK_SCOPE` | `work\ai-editor` | 2026-10-29 (#554) |
| `AIOS_CONTAINER_IMAGE` | `aios-verify:<first 12 of the sha256 of requirements.txt>` | 2026-10-28 |
| `AIOS_EXECUTOR_TIMEOUT_S` | `120` | 2026-10-28 |
| `AIOS_REPLAY_APPROVED_COMMANDS` | `1` | 2026-10-19 |
| `AIOS_ROUTER_CLOUD_TASKS` | `reasoning,coding`, his own user-wide choice; `--cloud-tasks ""` keeps every turn local | 2026-11-03 |
| `AIOS_PLAN_CLAUDE_MODELS` | `claude-sonnet-5-5,claude-haiku-5-5`, through Claude Code on his plan | 2026-11-03 |
| `AIOS_PLAN_CODEX_MODELS` | `gpt-6.1-sol,gpt-6.1-terra,gpt-6-luna`, through Codex on his plan | 2026-11-03 |

`AIOS_ROUTER_CLOUD_TASKS` is always set by the tool, so a value inherited from the user environment never decides where a turn goes.

On 2026-11-03 the operator connected his own plans to the counter ("connect codex models to counter also and C"; `aios/core/plan_cli.py`). Reasoning and coding turns on `auto` may now go to them; general and fast turns stay local. Opus is left out: it would spend the plan he shares with his own sessions fastest.

The user-wide `reasoning,coding` still reaches every other process he starts. Removing it is his choice:

```
[Environment]::SetEnvironmentVariable('AIOS_ROUTER_CLOUD_TASKS', $null, 'User')
```

Separately, Bedrock is no longer offered when no credential could sign a request (`aios/core/bedrock.py::credentials_available`). With `auto` opted into the cloud and no AWS key loaded, a turn now goes straight to the local model, and no Bedrock attempt is made or ledgered.

## The audit key

The audit chain signs every entry with `AIOS_AUDIT_PRIVATE_KEY`. Until it is stored, the following holds:
- Every backend start signs with a throwaway key. The daily backend's log says so: "ephemeral Ed25519 key pair".
- The frozen audit logger's trust anchor is the public half of this seed, so without the seed there is no anchor, and the live chain can never verify.
- Until 2026-10-29 the keystore did not even know the name.

Now `up` loads it when it is stored. Storing it is the operator's act:

```
.venv\Scripts\python.exe -m aios.launcher keys generate AIOS_AUDIT_PRIVATE_KEY
```

From then on, new entries are signed by one key that survives restarts.

The entries already written stay unverifiable: 351 unsigned June entries, and the rest signed by throwaway keys. Fixing those is the operator-signed epoch boundary in `docs/security/PROPOSAL_AUDIT_EPOCH_BOUNDARY.md`. That proposal changes frozen code, so it is his decision.

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
