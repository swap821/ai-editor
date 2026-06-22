# START HERE — running the AI-OS build with coding agents

Plain-language quickstart. The idea in one line: **coding agents share a notebook
on disk (`.aios/`) so they can continue where the previous agent stopped, and a
small helper can reopen Claude Code right where it left off.**

> Note on brains: the web (Opus) chat and Claude Code (in VS Code) are *separate*
> — nothing auto-carries between them. This repo is the Claude Code side.

---

## The pieces (one line each)
- **`AGENTS.md`** — the canonical shared rulebook for Claude Code, Codex, and
  future coding agents. `CLAUDE.md` is only Claude Code's compatibility loader.
- **`.aios/`** — the notebook on disk. `state/RESUME.md` = "where we are / do this
  next"; `memory/` = lessons and experiences.
- **`aios-resume.ps1`** (Windows) / **`aios-resume.sh`** (Git Bash) — the helper
  that checks "can I work right now?" and reopens Claude Code where you stopped.
- **`.vscode/tasks.json`** — lets you run that helper from VS Code's Run Task menu.
- **`agent_coord.py`** — local Claude/Codex inboxes, task routing, one-writer
  lease, and hash-pinned review handoffs.

---

## Every session (the easy loop)
1. Open this folder in VS Code and start Claude Code (`claude` in the terminal),
   **or** double-click-run the resume task: `Terminal > Run Task >
   "AI-OS: resume Claude Code"`.
2. It reads `.aios/state/RESUME.md` and tells you, in a sentence, where you left
   off and the single next step.
3. You say **go**. It does the safe work on its own (read, plan, write code, run
   tests) and **pauses to ask** before anything risky (edit, install, delete).
4. Out of usage for now? Just stop — your spot is already saved in `RESUME.md`.
   When the window resets (~5 h on Pro), open the folder again and continue.

## Claude + Codex working together

They communicate through the ignored local control plane at
`.aios/state/coordination.db`; neither can directly wake the other.

```powershell
.venv\Scripts\python agent_coord.py brief --agent codex
.venv\Scripts\python agent_coord.py brief --agent claude
```

Only the active builder lease may edit. The reviewer stays read-only and records
a verdict against the exact hash-pinned handoff tree. Claude and Codex are
equally prioritized; automatic builder assignments balance toward 50/50, and
either may review the other's work at any time. Full commands are in
`.aios/coordination/README.md`.

## Verify the build is healthy anytime
```powershell
.venv\Scripts\python -m pytest -q          # expect a green run (556 passed / 1 skipped as of 2026-06-15; grows as tests land)
```

## Run the actual app (to see it work)
```powershell
# terminal 1 — backend
.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000
# terminal 2 — frontend
cd frontend; npm run dev                   # http://localhost:5173
```
Leave the model dropdown on `Auto`; it routes to the best installed compatible
local model for the task.

---

## The honest part (so you're never surprised)
- **A prompt can't wake itself.** When your usage limit is hit, no agent is
  running, so nothing in `AGENTS.md` can "auto-resume." The helper script does the
  clock-watching *outside* the model. The script resumes your **context and plan**
  with **approvals ON** — it never runs edits/installs/deletes by itself.
- **Auto-run-on-open is OFF by default, on purpose.** Silently auto-launching a
  script that bypasses Windows' script policy would weaken the exact guardrail
  this whole project is about. If you want it, enable it yourself — see the steps
  at the top of `.vscode/tasks.json`.

## Want longer hands-off runs? (optional, when you trust a component)
Allowlist routine actions so Claude Code stops asking for the safe ones:
```
/permissions add Edit
/permissions add "Bash(pytest:*)"
/permissions add "Bash(git commit:*)"
```
Irreversible actions (delete, secrets, env, network) still always ask. Never use
`--dangerously-skip-permissions` — it turns off the approval gate that is the
point of this project.
