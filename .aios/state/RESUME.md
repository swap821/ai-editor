# RESUME MANIFEST — .aios/state/RESUME.md
<!--
  Claude Code OVERWRITES this file at every checkpoint (see CLAUDE.md §IV).
  It is the single source of truth a future session reads first.
  Keep it under one screen. Long history belongs in experiences.jsonl, not here.
-->

## Current goal
Drive the local-first AI-OS (Python `aios/` backend + React `frontend/`) from its
current state to a polished, demoable MVP per the v4 blueprint — memory-driven,
security-gated, human-supervised, self-correcting.

## Status  (read from the CODE, not the blueprint's "~35%")
- **Reality: the backend is ~75–80% of the blueprint MVP, well past the doc's estimate.**
- Stack: Python 3.12 `.venv`, FastAPI + uvicorn, SQLite (WAL) + FAISS, Ollama (local LLM). Node backend archived on branch `legacy-node` / tag `legacy-node-v1`.
- Tests: **94 passed, 1 skipped** (`.venv/Scripts/python -m pytest -q`). The 1 skip = Windows symlink-privilege case (environmental, not a failure).
- Last completed + verified step: **Phase 4h DONE + premium polish pass DONE.** 4h live-verified (llama3.2:3b): pinned approval bar (YELLOW badge, clean prompt, always-visible Run/Reject). Then a 3-part chat polish on the WORKING components (eslint+build clean each step): #1 message entrance + agent-step cascade + bubble depth (`4f87dbc`); #2 global tactile button press + smooth transitions; #3 chat top scroll-fade (`7099a8a`). All motion gated by prefers-reduced-motion. Live run (llama3.2:3b) showed the card; fixed in sequence: (1) prompt leaked the classifier's raw regex → plain language; (2) step-spinner span forever on pause → `settled` flag; (3) **the Run/Reject buttons were clipped inside the scroll log → re-architected the approval as a PINNED action bar (flex-shrink-0) above the composer, premium-styled (glassmorphism + slide-up + glow), so controls are always visible.** 94 backend tests green; eslint+build clean. Lesson: never put a blocking decision inside a scroll container.

### BUILT & committed (per-phase commits on `master`)
- **Memory L2/L3/L4** — episodic, semantic (FAISS `IndexIDMap`), mistake pool; hybrid BM25+FAISS+decay retrieval `R = 0.25·BM25 + 0.45·FAISS + 0.30·e^(−0.05·Δt)`. `[aios/memory/]`
- **Security gateway** — deterministic fail-closed 3-zone (regex + scope-lock canonicalization + Shannon-entropy secret scan). `[aios/security/]`
- **Audit log** — SHA-256 hash chain, secret-scrubbed payloads, O(n) verify endpoint. `[aios/security/audit_logger.py]`
- **Reflection agent** — LLM post-mortem → Mistake pool (strict JSON, delta clamp, recurrence, pending→verified). `[aios/agents/reflection_agent.py]`
- **Planner** (0.72 confidence gate) · **Executor** (gateway-guarded, sandboxed, audited) · **Rollback** (GitPython snapshots). `[aios/core/, aios/agents/]`
- **FastAPI** — `/health`, `/api/v1/{memory/search, security/classify, audit/verify, reflect, plan, execute, approval/req, rollback, models/local}`, `/api/generate` (SSE), `/api/terminal`. `[aios/api/main.py]`
- **React frontend wired to FastAPI** (`:8000`, CORS), model picker lists installed Ollama models, Local/Cloud badge. `[frontend/]`
- **Agentic chat that acts + learns** — `/api/generate` runs a security-gated tool loop (read_file / read_directory / execute_terminal), recalls memory, persists + consolidates each turn into L2/L3, reflects on failures (🧠 lesson), promotes lessons pending→verified on a corrective success, and recalls a session's pending lessons across turns. `[aios/agents/tool_agent.py]`
- **Resumable in-chat approval (Phase 4h)** — a YELLOW command pauses the turn with a `human_required` event; the UI shows the approval card, and on approve the frontend re-sends the turn with the command in `approvedCommands`, so it runs via `executor.execute_approved` (RED still refused). Pausing records no answer, so the resend cleanly replays the same turn. `[aios/agents/tool_agent.py · aios/api/main.py · frontend/src/App.jsx]`

## Next action  → do this first on resume
**PHASE 1+2 DONE; SLICE 1 (1a+1b) DONE & GREEN (2026-06-03).** Full suite **124 passed,
1 skipped**. `PLAN.md` targets **100% / no left-outs** (fundamentals-first; deferrals are
later phases, not dropped).
- **Slice 1a — security-scope hardening (FROZEN CORE): DONE & committed (`e7bba3c`).**
  Fixed 3 live scope bypasses an xhigh review found in the prior `command_stays_in_scope`
  rewrite (`~/…` home, shell-metachar-glued abs paths, bare `..` — all had classified
  GREEN). `_SHELL_OPS` pre-split + `~` refusal + `..` guard; 5 regression tests; legit
  `.venv\Scripts\python.exe`/`&&` cases still YELLOW.
- **Slice 1b — API contract tests: DONE & GREEN (uncommitted).** 8 HTTP tests in
  `tests/test_api.py` for `/plan,/execute,/approval/req,/rollback`; the 4 route handlers
  are now fully covered. The `/approval/req` test pins the D1 hard-block at the HTTP layer.
- **D1 (RED policy): DECIDED — keep hard-block** (RED always refused even after approval;
  stricter than the blueprint, by choice). Recorded in `PLAN.md` + memory.
- Operator memories saved (independent dev; 100% goal; CEO role) + `CEO_LOG.md` (Advice #1).
  Commits: `e39a3f8` v6 · `e7bba3c` scope fix · `2b657dd` blueprint cleanup · `ba5d838` planning.
- **Slice 2 — file-edit tool (patch-style `edit_file`), backend: DONE & GREEN.** Per
  operator, built as search/replace (unique old_string → unified-diff preview → YELLOW
  pause → pre-write snapshot + write + audit on approval), scope-locked to sandbox roots.
  5 tests in `test_tool_agent.py`. Live path stays SAFE: `edit_file` always pauses until
  Slice 4 wires `approvedEdits` + the snapshot/diff UI. Full suite **129 passed, 1 skipped**.
**Next action:** commit Slice 2, then **Slice 3 — frontend test harness (Vitest + RTL)**.
⚠ Slice 3 needs `npm install` (YELLOW, network) — get operator OK for the install before
running it. Operator said "do all on your order"; honor that for GREEN code work but still
gate the package install.
**Parked:** 4 untracked premium CSS files (intentional, for a later polish phase).

--- (prior Phase-4h candidates, retained for context) ---
**Phase 4h is DONE and committed.** Pick the next build step. Candidates, in rough
priority (propose one, then STOP for the operator's go before writing code):
1. **Live e2e demo pass (RAM-gated).** Load `llama3.2:3b`, run backend + frontend,
   and walk the full happy path: chat → YELLOW command → approval card → resume →
   command runs → reflection. This is the highest-value next step (proves 4h end-to-end)
   but needs ~4 GB free RAM (close other apps). Set `AIOS_INDEX_CHAT=false` /
   `AIOS_REFLECT_ON_FAILURE=false` on a tight run to avoid extra model loads.
2. ~~Reject-on-resume polish~~ **DONE** — `handleRejectAction` now clears the
   approval whitelist + pending action and posts "Rejected — the command was not run."
3. **Offline voice (Whisper + Piper)** — fully local STT/TTS; bigger scope.
4. **Docker + Prometheus/Grafana** — packaging/observability; bigger scope.

The next *substantive* step is the live e2e demo (RAM-gated, operator-driven) — see
the runbook; free ~3 GB first (only 1.31 GB free at last checkpoint).

Note: approval whitelist is **per-request** (frontend resets `approvedCommands` on each
new user message; grows it only across an approve→resume chain). That's the intended
security boundary — re-check it if you change the resume flow.

Deferred (unchanged): offline voice; Docker + Prometheus/Grafana.

### Frontend stabilization (after a parallel rewrite broke it)
A concurrent "premium 2026" rewrite landed uncommitted in the tree (rewritten
`MessageBubble.jsx`/`LivePreview.jsx` with **incompatible props** — `{message,isUser}`
vs the `{msg}` the app passes — plus new `styles/{App,design-system,nexgen-3d,nexgen-layout}.css`
imported into App.jsx/index.css). It broke the chat render. Per operator choice we
**stabilized**: restored the working components + clean `index.css` baseline, stripped
the foreign imports, and **parked the 4 new CSS files untracked+unimported** (preserved,
not deleted) for the upcoming incremental polish. App builds clean; pinned approval bar kept.
**Next (polish phase):** layer premium polish onto the WORKING components one increment at a
time (verify build each step); optionally mine the parked CSS for ideas. Don't re-import it wholesale.

### Cloud inference (AWS Bedrock) — NEW, opt-in
Local Ollama CUDA-OOMs on the 4GB RTX 3050, so a **Bedrock cloud provider** was
added (`aios/core/bedrock.py`, Converse API + tool-use; routed in `/api/generate`
via `_select_chat_client`). Local-first stays the default; Bedrock is **off**
unless a region is set. Auth uses the operator's new **Bedrock API key** (`ABSK…`,
a bearer token — NOT an IAM `AKIA…` key) via `AWS_BEARER_TOKEN_BEDROCK`. The model
defaults to `amazon.nova-lite-v1:0`, so only **region + key** are needed:
```
$env:AIOS_BEDROCK_REGION      = "us-east-1"   # the operator's region
$env:AWS_BEARER_TOKEN_BEDROCK = "ABSK..."     # the Bedrock API key (env only)
# optional: $env:AIOS_BEDROCK_MODEL = "<other model/inference-profile id>"
```
Then in the UI pick a **Cloud (Bedrock)** model → routes to Bedrock on THAT model
(the selected id is passed through to Converse). Secrets live only in env.

**Model picker DONE:** `BedrockClient.list_models()` (control-plane
ListFoundationModels, TEXT+ON_DEMAND) → `/api/v1/models/bedrock`; the frontend
shows a real "Cloud (Bedrock)" group (curated fallback if discovery is blocked).
107 tests pass. NOTE: the test suite now stubs `aios.api.main.hybrid_search` in
the `client` fixture — live app usage had populated the on-disk FAISS index, so
generate tests were loading the real embedder and **segfaulting torch**; the stub
isolates tests from live `data/` (no model side-effects in tests).

## Open approvals / blockers
- Live happy-path is gated by host RAM (7.5 GB). Close other apps so `llama3.2:3b` fits (~4 GB free). `AIOS_INDEX_CHAT` and `AIOS_REFLECT_ON_FAILURE` each add an extra model load — set them `false` on tight runs.

## Active files  (Phase 4h — committed; touched these:)
- `aios/agents/tool_agent.py` · `aios/api/main.py` · `tests/test_tool_agent.py` · `tests/test_api.py` · `frontend/src/App.jsx`

## Notes not yet promoted to memory
- Run backend: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000`. Run frontend: `cd frontend; npm run dev` (:5173). Tests: `.venv\Scripts\python -m pytest -q`.
- The repo uses per-phase commits on `master` (not `main`). Keep that cadence.

---
_Last updated: 2026-06-02 by Claude Code (Phase 4h checkpoint)_
