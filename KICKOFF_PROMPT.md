# KICKOFF PROMPT

The `.aios/` brain and `CLAUDE.md` already exist in this repo (set up on
2026-06-02), so you normally do **not** need a kickoff — just open the folder and
Claude Code runs the Bootstrap Protocol from `CLAUDE.md`.

Use the block below only to **re-anchor** a session (e.g. after a long gap, or if
`RESUME.md` looks stale). Paste it into Claude Code:

```
You operate under CLAUDE.md in this repo (the local-first AI-OS: Python `aios/`
backend + React `frontend/`).

Do exactly this, in order:

1. BOOTSTRAP. Read .aios/state/RESUME.md, then warnings.md and the last ~10
   entries of .aios/memory/experiences.jsonl. Summarise in one short paragraph:
   the goal, the last completed+verified step, and the single next action.

2. VERIFY STATE. Run `.venv\Scripts\python -m pytest -q` and report the exact
   pass/skip/fail counts. If anything is red, that becomes the next action — fix
   it before any new feature.

3. REAL INVENTORY (trust the code, not the blueprint's "~35%"). Confirm BUILT /
   PARTIAL / MISSING with a file path + one line of evidence for: memory L2/L3/L4,
   hybrid retrieval, security gateway, audit hash-chain, reflection + mistake DB,
   planner, executor, rollback, the agentic /api/generate loop, and the React↔FastAPI wiring.

4. PROPOSE the next task and a short plan. STOP and show me the plan before
   writing any code.

OPERATING RULES (every session):
- Run autonomously in GREEN (read, analyse, scaffold, write code, write+run tests).
- For YELLOW (file edits, installs, git writes) or RED (delete, secrets, env,
  network, sys config): show me the diff/command and wait for approval. Never use
  --dangerously-skip-permissions.
- After each unit of work: verify (tests pass + exit 0), append one Experience
  Object to .aios/memory/experiences.jsonl, log any failure to mistakes.jsonl, and
  OVERWRITE .aios/state/RESUME.md with the updated state + single next action.
- Build one component fully and test it before starting the next.
```
