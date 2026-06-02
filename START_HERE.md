# START HERE — running the AI-OS build with Claude Code

Plain-language quickstart. The idea in one line: **Claude Code keeps a notebook on
disk (`.aios/`) so it never forgets where you stopped, and a small helper reopens
it right where you left off.**

> Note on brains: the web (Opus) chat and Claude Code (in VS Code) are *separate*
> — nothing auto-carries between them. This repo is the Claude Code side.

---

## The pieces (one line each)
- **`CLAUDE.md`** — the rulebook Claude Code reads automatically (how it remembers
  + stays safe). Auto-loaded; you never paste it.
- **`.aios/`** — the notebook on disk. `state/RESUME.md` = "where we are / do this
  next"; `memory/` = lessons and experiences.
- **`aios-resume.ps1`** (Windows) / **`aios-resume.sh`** (Git Bash) — the helper
  that checks "can I work right now?" and reopens Claude Code where you stopped.
- **`.vscode/tasks.json`** — lets you run that helper from VS Code's Run Task menu.

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

## Verify the build is healthy anytime
```powershell
.venv\Scripts\python -m pytest -q          # expect: 89 passed, 1 skipped
```

## Run the actual app (to see it work)
```powershell
# terminal 1 — backend
.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000
# terminal 2 — frontend
cd frontend; npm run dev                   # http://localhost:5173
```
Pick `llama3.2:3b` in the model dropdown. (Close other apps first so it fits in
RAM. `ollama pull llama3.2:3b` if you haven't.)

---

## The honest part (so you're never surprised)
- **A prompt can't wake itself.** When your usage limit is hit, no Claude is
  running, so nothing in `CLAUDE.md` can "auto-resume." The helper script does the
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
