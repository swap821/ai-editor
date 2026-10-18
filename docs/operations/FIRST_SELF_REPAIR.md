# First self-repair: GAGOS removes its own dead imports

*Written 2026-10-12. The operator chose this mission: GAGOS on itself, with the
vulture as the apex predator's scavenger. This is the first run of the
maintenance pipeline on a real project. Until now it had only repaired a
marker string in a test fixture.*

## What happens

1. **The vulture scans the project.** The scanner `vulture_dead_imports` reports one finding per file. An import counts as dead only if no file in the project takes it:
   - it isn't imported, patched or reached through an alias anywhere else;
   - it isn't a `noqa: F401` or `__all__` re-export;
   - its module isn't consumed dynamically.
2. **You approve a YELLOW repair mission.** This needs your privileged, freshly re-authenticated session and the server's capability exchange.
3. **A worker proposes `REMOVE_DEAD_IMPORTS_V1` and the executor applies it in a staged copy.** The executor works out which imports to remove from the copy itself, using the same rule, and refuses any edit it cannot make safely.
4. **A rescan of that file in the copy must find nothing.**
5. **Promotion applies the change with a checkpoint.** The smoke check then runs:
   - the file must compile;
   - its module must import in a fresh interpreter;
   - every test file that imports it must pass. For `aios/api/main.py` that is 88 files.

   If any of these fails, the checkpoint is restored.
6. **A final rescan resolves the finding.**

The smoke report is written to `data/maintenance_smoke/<mission>-<time>.json`.

## Before the run

**A clean worktree.** Staging the live checkout is refused: it holds `data/`, where staging lives, and the copy would include itself. Measured: the copy nested itself until it hit the Windows path limit. The worktree is where the repair lands; you turn it into a commit and a PR afterwards.

```powershell
git -C C:\Users\kumar\ai-editor worktree add C:\gm origin/master
```

**The executor service.** Repairs run inside its process, so Docker is not needed for this mission. Give it and the backend the same token; storing it is your act.

```powershell
$env:AIOS_EXECUTOR_TOKEN = "<your token>"
$env:AIOS_EXECUTOR_WORKSPACE_ROOT = "C:\Users\kumar\ai-editor\data\staged_maintenance"
python -m uvicorn aios.executor_service:app --host 127.0.0.1 --port 8081
```

**The backend**, restarted with the following settings (it has no `--reload`):

```powershell
$env:AIOS_MAINTENANCE_PROJECT_ROOT = "C:\gm"
$env:AIOS_EXECUTOR_URL = "http://127.0.0.1:8081"
$env:AIOS_EXECUTOR_TOKEN = "<the same token>"
```

## The run

```powershell
python tools/maintenance_repair.py --scan
python tools/maintenance_repair.py --findings
python tools/maintenance_repair.py --repair <fingerprint of aios/api/main.py> --i-am-the-operator "Swapnil"
```

The repair request lasts as long as the smoke check, which can be many minutes. While it runs, the backend answers other requests slowly.

## Results

| Result | Meaning |
|---|---|
| `VERIFIED_RESOLVED` | `C:\gm` holds the repair, and its tests passed. Commit it there and open a PR: CI is still the gate to master. |
| `PROMOTION_FAILED` with `rolled_back` | The smoke check proved the repair wrong, and `C:\gm` is restored. The smoke report names the failing step. This is the system working: a test found a use that no static rule could see. |
| `WORKER_FAILED`, `EXECUTOR_*` or a verification failure | Nothing was promoted. The reason names the stage. |
