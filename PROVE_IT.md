# Prove It — the ten-minute supervised-loop demo

This is the shortest path to **witnessing** this AI-OS organism's core thesis end
to end: an operator directive causes the mind to plan; a risky (YELLOW) write
**pauses for human approval**; the approved action executes **scoped in a
sandbox**; a **forced auto-verify** judges the result with real evidence; and
the organism **records what it learned**. Every claim below is backed by
something you can see with your own eyes — a file on disk, a database row, an
HTTP status, a paused chat turn.

Two ways to prove it:
1. **`prove_it.py`** — a scripted checklist prover you run from a terminal. Prints
   PROVED/FAILED per step with real evidence on every line. Takes under a minute.
2. **The browser** — the same loop, but you watch the being itself present the
   approval gate and react to it live. This is the "ten minutes, witnessed" part.

---

## Prerequisites

- Windows, this repo, `.venv` already provisioned (`.venv\Scripts\python` exists).
- For the **browser** run: `frontend/` npm dependencies installed (`cd frontend; npm install` if you haven't).
- Optional, for a **live LLM** instead of the scripted brain: [Ollama](https://ollama.com)
  running locally with a tool-calling-capable model pulled (e.g. `ollama pull qwen2.5-coder:7b`).
  Not required — `prove_it.py --scripted` and the browser run both work without any LLM,
  using the app's real machinery end to end.

---

## Step 1 — Pre-flight: run the scripted prover

```
.venv\Scripts\python prove_it.py
```

This auto-picks `--scripted` (deterministic, no LLM, no spawned server — an
in-process TestClient against the real FastAPI app) unless it detects a usable
local Ollama model, in which case it picks `--live` (spawns a real
`python -m aios` server and drives a real model). Force either explicitly:

```
.venv\Scripts\python prove_it.py --scripted
.venv\Scripts\python prove_it.py --live
```

You'll see a numbered checklist. Every `[PROVED]` line carries real evidence
(a file path, an HTTP frame count, a database row count). A `[FAILED]` line
always prints **WHY** and the run exits non-zero — it never fakes a green step.

The banner at the top and bottom of the run tells you which brain drove it:

- `MODE: SCRIPTED BRAIN (SIMULATED)` — the LLM's tool-call decisions were
  pre-scripted; every other subsystem (executor, approval store, verifier,
  skills/development stores) is the real thing, running on hermetic temp DBs.
- `MODE: LIVE BRAIN` — a real spawned server, a real local Ollama model,
  nothing scripted.

This step never leaves a server process running when it exits, and it leaves
`training_ground/` exactly as it found it (any file it creates for the demo is
deleted afterward — it snapshots the sandbox before and diffs it after).

---

## Step 2 — The witnessed run: watch the being do it in the browser

This is the actual point of the exercise — not the terminal checklist, but
*seeing* the supervised loop happen in the product's real UI.

1. **Backend**, in one terminal:
   ```
   .venv\Scripts\python -m aios
   ```
   Wait for it to report healthy (it binds `127.0.0.1:8000` by default).

2. **Frontend**, in a second terminal:
   ```
   cd frontend
   npm run dev
   ```

3. Open **`http://localhost:5173`** — and only that port. The backend's CORS
   allow-list is `:5173` / `:4173` / `:3000` only; any other port (or file://)
   gets a silent `Failed to fetch` with no useful browser error (see
   Troubleshooting below).

4. Type this exact directive into the being's chat:

   > create reverse_string.py — a function that reverses a string plus a
   > pytest test — then verify it by running pytest

   (If `training_ground/reverse_string.py` already exists from a previous
   session, ask for a distinctly-named file instead, e.g.
   `witness_reverse_string.py`, so the write is a fresh creation rather than a
   no-op — a create that already matches the existing file **does not** pause
   for approval, since there's nothing new to approve.)

5. **Watch for these four beats, in order:**
   - The being **pauses** — presents the pending write (the diff / new file
     content) centre-stage and asks for your approval. Nothing has been
     written to disk yet at this point.
   - You **approve** it in the UI.
   - The being **executes** the write, scoped to its sandbox
     (`training_ground/`) — you can open the file yourself afterward and see
     it appear on disk.
   - The being runs its **forced auto-verify** (pytest, automatically, no
     extra approval needed for this system-run check) and shows the verify
     beat — pass or fail, with real output.

   If the model calls `create_file` twice (once for the module, once for its
   test), you'll see this pause/approve cycle **twice** — that's expected, not
   a bug; approve both.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Browser shows `Failed to fetch` with no other detail | You opened a port other than 5173/4173/3000, or the frontend dev server is on a different port than you typed | Confirm the frontend terminal printed `http://localhost:5173` and use exactly that URL |
| `prove_it.py --live` says "No reachable/tool-capable local Ollama model detected" | Ollama isn't running, or no tool-calling model is pulled | Start Ollama, then `ollama pull qwen2.5-coder:7b` (or any model in `PREFERRED_LIVE_MODELS` in `prove_it.py`); or just use `--scripted` — it proves the same machinery without needing a real model |
| `prove_it.py --live` completes BOOT/DIRECTIVE but SUPERVISION fails with "the live model did not attempt a gated write" | The local model is too weak / didn't call `create_file` reliably after a few nudges | This is an honest degrade, not a bug in the prover — retry with a stronger model (`qwen2.5-coder:7b`) or fall back to `.venv\Scripts\python prove_it.py --scripted` |
| Port 8000 (or whatever `--port` you passed) is already in use | Another `python -m aios` (or unrelated process) is bound to it | Stop the other process, or pass `prove_it.py --live --port 8010` |
| The chat directive doesn't pause for approval at all | `training_ground/reverse_string.py` already exists with byte-identical content from a prior run, so there's nothing new to approve | Use a fresh filename in your directive (see step 4 above) |
| Verify step shows a PASS but at a lower strength than expected | A known, already-flagged environment finding: pytest's `-q` flag can suppress its own summary line under this repo's inherited `pytest.ini` addopts, which starves the strength parser of a passing count even though the test genuinely passed. This is a real product-code gap, not something this doc can paper over — `prove_it.py`'s checklist reports it honestly (FAILED, with the full root-cause trail) rather than claiming a false STRONG. |
| `docker version` fails / Docker Desktop not running | The approved-command execution backend defaults to a container runner; without Docker the auto-verify and any approved raw command fail closed | Expected on a laptop without Docker Desktop running. `prove_it.py --scripted` sidesteps this by using an explicit host runner for its own hermetic run (mirrors the documented dev-only `AIOS_APPROVED_EXECUTION_BACKEND=host` opt-out — no repo default is changed). For the **browser** run, either start Docker Desktop first, or expect the verify beat to show a fail-closed container-unavailable message rather than a pytest result. |

---

## What you just proved

If you watched the four beats in Step 2 (or read a fully-PROVED `prove_it.py`
checklist), here is what each one maps to in the architecture:

1. **The being paused on its own for a risky write, and nothing was written
   before you approved it.** This is the supervised YELLOW gate — the
   product's central thesis — not a demo trick. `create_file`/`edit_file`
   unconditionally require a human-issued, single-use, session-bound approval
   token before anything touches disk.
2. **A RED action (anything destructive/irreversible) is never even offered
   for approval.** The same gateway that paused this YELLOW write refuses RED
   outright, with no approval path that can override it — one click cannot
   authorize what fail-closed security has already refused.
3. **The auto-verify's pass/fail is graded by strength, not just exit code.**
   A recognized test runner reporting real passing assertions is what the
   verification-strength taxonomy calls STRONG evidence; a weaker signal
   (or a spoofed one) cannot forge that floor. (This run's own checklist may
   have surfaced a real gap in reaching that floor in this environment — see
   Troubleshooting — which is itself proof the taxonomy is checking something
   real, not rubber-stamping.)
4. **The organism recorded what happened, not just what you saw.** A
   `development_events` row exists for this turn whether or not the write
   passed; a `procedural_skills` attempt row exists specifically for a
   strength-eligible success — skill learning is gated on genuine evidence,
   not on the model's own narration.
5. **None of this happened silently in the background.** The observation-only
   cortex bus (event substrate for future self-model/emotion features) ships
   default-OFF; this loop's approval gate, sandboxed execution, and verify
   step are the whole visible mechanism today — nothing about the supervised
   loop depends on an always-on background agent you can't see.

---

*Written as part of the additive-only `prove_it.py` slice. If a step above
ever contradicts what you actually saw, trust what you saw and file it as a
finding — the whole point of this document is that it should never need you
to take its word for anything.*
