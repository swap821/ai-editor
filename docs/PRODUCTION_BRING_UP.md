# Production bring-up

*How the production profile first comes up on the operator's machine. It
starts with a drill on a restored copy of the data, never the only copy.
Measured by `python tools/production_readiness.py`
(docs/PRODUCTION_HARDENING.md).*

## What changed to make this possible (2026-10-11)

- **Keys at rest in Windows Credential Manager** (operator decision;
  AGENTS.md §VII.4 amended for that one store).
  - `gagos keys` stores them; nothing prints one.
  - `gagos start --profile production` hands them to Compose in memory.
  - Secrets are no longer read from `.env`.
- **The production container reaches the host's Ollama.**
  - `OLLAMA_HOST` points at `host.docker.internal`. Before, it dialled
    127.0.0.1, which is the container itself, so production had no local
    model.
- **The container is given its keys:** verification, learning, and any cloud
  key stored.
- **The container sees the pinned learning keys.**
  - `.aios` is not in the image, so the pin file is mounted read-only.
  - Production refuses to start until the stored learning key's public half
    is pinned.
- **The data directory is the launcher's** (`AIOS_DATA_DIR`), so a drill can
  run on a copy.
  - The executor's job workspace defaults to `<data>/executor-jobs`.

## The drill (operator)

Run these in your own PowerShell terminal, from a clean checkout of `master`.

`gagos` below is `python -m aios.launcher`: the same command. The short name
exists only once the package is installed (`pip install -e .` in that
checkout). Without it, PowerShell answers "The term 'gagos' is not recognized"
(found 2026-10-12), so the module form is what is written here.

1. **Docker Desktop.**
   - Settings → General → *Start Docker Desktop when you sign in*.
   - Start it now.
2. **A restorable backup of today's data:**
   ```
   python -m aios backup create
   ```
3. **A copy to drill on.** Restore that archive into a separate directory:
   ```powershell
   $env:AIOS_DATA_DIR = "C:\gagos-drill\data"
   python -m aios backup restore --input <the archive from step 2>
   ```
4. **Keys.** This is your act; the values are never shown.
   ```powershell
   python -m aios.launcher keys generate --missing
   python -m aios.launcher keys pin
   python -m aios.launcher keys set AWS_BEARER_TOKEN_BEDROCK   # optional, one per cloud key
   python -m aios.launcher keys status
   ```
   Commit `.aios/state/LEARNING_PUBLIC_KEYS.json`: the verifier trusts what is
   pinned there.
5. **Start production on the copy:**
   ```powershell
   $env:AIOS_DATA_DIR = "C:\gagos-drill\data"
   python -m aios.launcher start --profile production
   ```
6. **Measure:**
   ```powershell
   $env:AIOS_DATA_DIR = "C:\gagos-drill\data"
   python tools/production_readiness.py
   ```

## Known unknowns: the drill exists to find these

None of these has ever been exercised on Docker Desktop for Windows. Each is
answered by the drill, not assumed:

- **Ollama from inside a container.** Does `host.docker.internal:11434`
  reach Ollama listening on the host's 127.0.0.1? Docker Desktop forwards it;
  this is still to be measured.
- **Starting jobs.** The executor asks the daemon to bind-mount
  `AIOS_EXECUTOR_HOST_WORKSPACE_ROOT` (a Windows path) into each worker
  container. It may also need `AIOS_DOCKER_SOCKET_GID` set for Docker
  Desktop's socket.
- **SQLite over a Windows bind mount.** WAL mode over Docker Desktop's file
  sharing is a known source of locking errors. If the drill shows them,
  production data moves to a named Docker volume, and backup and restore
  become the way in and out.

Production switches from the copy to the real data only after the drill
passes. A dev backend and production must never run against the same data
directory at once.
