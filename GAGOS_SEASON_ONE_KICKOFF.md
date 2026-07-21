# GAGOS — SEASON ONE KICKOFF
**For:** Claude Code, operating in `C:\Users\kumar\ai-editor`
**From:** A full-repo audit + 17-turn design review with the operator (Swap), 2026-07-05
**Relationship to other docs:** `AGENTS.md` governs conduct; `FOUNDATION_LOCK.md` and Security Queen `_PROTECTED_PATTERNS` still apply. **This doc governs priority and order.** Where an idea here conflicts with a settled decision below, the settled decision wins — do not re-litigate design.

---

## 0. Verified current state (re-measured against the live working tree, 2026-07-05 — supersedes the original "clean sandbox" pass below; trust these numbers, not the README)

| Surface | Result |
|---|---|
| Backend test suite | All green, **92%+ branch coverage** (2,476+ tests; the original 84.8%/450-test figure reflected the committed state before 8 already-written test files landed) |
| `prove_sovereignty.py` | **18/18 pass cold** — no API keys, no network |
| Adversarial suite (`tests/adversarial/`) | **434/434 pass** (original doc understated this by ~5.9x) |
| Audit ledger live attack | Row edit, row delete, forged re-insert — **all 3 detected**, `broken_at` correct |
| Backend boot | `from aios.api.main import app` clean — **92 routes** |
| Frontend | `npm ci` clean, **0 vulnerabilities**; typecheck ✅; production build ✅ (~9s); **455 tests / 72 files pass** (450 baseline + 5 regression tests from this session's bug fixes) |
| Historical "blank-screen boot bug" | **Not reproducible** — treat as fixed unless live run says otherwise |

**Known architecture facts (verified in code):**
- Cerebellum `match()` = deterministic token-set cosine (`aios/memory/relevance.py::relevance`) — paraphrase-blind by design; safe fail-through to LLM.
- Council = 5 **deterministic** Queens + one LLM King under a **strengthen-only caution clamp** (`aios/council/king_reasoning.py::clamp_recommendation`). This clamp is load-bearing. Never weaken it.
- LLM layer is a **selector switch + series failover**: exactly one `asyncio.create_task` in the backend, zero `asyncio.gather`; all five provider clients (`llm.py` Ollama, `bedrock.py`, `gemini.py`, `openai_compat.py`, `anthropic_direct.py`) share a duck-typed `chat()` interface; all are **blocking** (urllib/boto3).
- Default weights are five distinct families: Ollama local · `amazon.nova-lite-v1:0` · `gemini-2.5-flash` · `gpt-4o-mini` · `claude-sonnet-4-20250514`.
- `cortex_bus.py` docstring is law: *"It carries what HAPPENED, never what is PERMITTED."*

---

## 1. Prime directives for this season (settled — enforce, don't debate)

1. **Evidence before claims.** No percentage, superlative, or capability claim enters code comments, docs, or README without a measurement behind it. Banned words in docs: *ultimate, perfectly, 100%, AGI-ready, improves every second*. Approved framing: *supervised agentic runtime that earns autonomy through verified evidence.*
2. **Nothing skips the gate.** LLM output, cabinet consensus, imported skills, web-derived facts, parallel-branch results — all are narration until verified. Unanimous ≠ verified.
3. **Parallel where you generate, series where you decide.** Any parallelism sits *upstream* of the single series safety path (gateway → approval → verifier). A branch that can reach execution without the series path is a defect.
4. **Safety signals pierce all filters.** Any summarization/reporting layer may compress routine telemetry; it must pass YELLOW/RED events, clamp triggers, and gateway blocks through **uncompressed**.
5. **Authority flows down the command line only; judgment is a separate wire.** Command: Operator → sovereign brain (proposes, never originates final authority) → orchestrator → workers (scoped kit via Scope Lock). Judgment: Queens judge *work product* from the side and report toward gateway/ledger, never up the management chain. The wires touch at exactly one point: the approval gate.
6. **Communication is protocol, not personality.** Typed contracts (`runtime/contracts.py`) on the cortex bus. No LLM relay agents. `king_report.py` is the only human-boundary summarizer.
7. **Scope freeze:** no new organs/agents/layers until Phase 0–2 below are complete **and** the lap counter has ≥50 real requests logged.

---

## 2. PHASE 0 — Out-lap (grid-blockers; nothing else matters until the car completes one real lap)

> A passing build is scrutineering, not a lap. These four tasks produce the first real lap.

**P0.1 — Engine keyed in** *(operator does keys; you do verification)*
Build `tools/preflight.py`: checks exactly one configured provider end-to-end — config present → client constructs → one real `chat()` round-trip ("reply with OK") → prints provider, model, latency. Exit non-zero with a plain-language fix hint on any failure. Prefer Ollama (free, local, sovereign) as the default engine.

**P0.2 — One-command race start**
`race.ps1` (Windows-first; mirror `race.sh`): starts backend (`uvicorn aios.api.main:app --port 8000`), waits for `/health` (add a trivial health route if absent), starts frontend dev server, runs `preflight.py`, fires one canned chat request through the real API, prints PASS/FAIL summary. Idempotent; Ctrl-C tears both down.

**P0.3 — Cockpit connection, live**
With both halves running: verify the browser UI sends a message and renders a response (CORS, cookie session, SSE stream all real, not mocked). Document any fix in `docs/`.

**P0.4 — Engine-failure behavior (the one untested unknown)**
Kill the backend mid-request; slow-start it; wrong port. The organism UI must degrade visibly and recover — **no white screen**. Add a frontend test if a gap is found.

**Acceptance for Phase 0:** operator runs one command, sends one message in the UI, gets one answer, and can unplug the backend without killing the page.

---

## 3. PHASE 1 — The Lap Counter (the single most important build of the season)

**Why:** The system's entire thesis is "superior every run." Today that is unmeasurable. This instrument makes every future design debate (cabinet, ministers, parallel, skill import) *empirically decidable*.

**Module:** `aios/core/telemetry.py` + table in the existing SQLite memory DB.

```sql
CREATE TABLE IF NOT EXISTS run_telemetry (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  session_id TEXT,
  task_signature TEXT,          -- reuse relevance.signature()
  dispatch_path TEXT NOT NULL CHECK (dispatch_path IN
    ('playbook','native_plan','kg','llm','refused_offline')),
  provider TEXT, model TEXT,
  verified_outcome TEXT CHECK (verified_outcome IN
    ('pass','fail','unverified','aborted')),
  latency_ms INTEGER, tokens_in INTEGER, tokens_out INTEGER,
  max_zone TEXT                  -- highest zone touched (GREEN/YELLOW/RED)
);
```

**Hook points (observation-only, fail-open):** the exact decision sites where a request resolves to cerebellum replay vs native plan vs KG answer vs LLM fallback (chat flow in `aios/api/main.py` + cerebellum/native-planner dispatch). A telemetry write failure must **never** abort a request — log and continue. Per the cortex-bus law, telemetry records what happened; it grants nothing.

**Report:** `python -m aios.telemetry.report` prints, per session and cumulative:
- **Sovereign hit-rate** = non-`llm` dispatches ÷ total
- Verified-success rate per dispatch path
- Cost per verified success (tokens; Ollama = 0)
- **The curve:** does session N+1 beat session N on hit-rate? (This is "superior every run," as a number.)

**Tests:** unit tests for schema/report math; integration test proving a playbook replay and an LLM fallback each land one correctly-labeled row; a test proving a broken telemetry DB does not break chat.

**Acceptance:** after 20 real requests through the UI, the report prints a hit-rate and a trend line.

---

## 4. PHASE 2 — Coverage 84.8% → 90% (bounded, one-to-two sessions)

The uncovered 15% is network-edge code. Pattern: **fake the transport, not your own code.**

| Priority | Module | Cov | Missed | What's uncovered |
|---|---|---|---|---|
| 1 | `core/bedrock.py` | 63% | 116 | stream event loop (toolUse start/delta/stop, trailing finalize), error paths |
| 1 | `core/anthropic_direct.py` | 59% | 95 | SSE `data:` line parser, HTTPError→LLMError scrub |
| 1 | `core/gemini.py` | 69% | 94 | stream handling, error translation |
| 1 | `core/openai_compat.py` | 63% | 77 | chunk parse |
| 1 | `core/failover.py` | 71% | 98 | cascade branches, stream failover |
| 2 | `api/main.py` | 76% | 527 | lazy client factories (~636–701), lifespan branches, SSE endpoints, error handlers |
| 2 | `api/routes/council.py` / `sovereignty.py` | 78/75% | 91/77 | TestClient + SSE + rejection branches |
| 3 | `core/voice.py` | 27% | 99 | inject fakes at lazy-import seams; WAV byte math is pure |
| 3 | `runtime/worker_entry.py` | 72% | 61 | bootstrap guards, failure exits |

Per-provider stream cases: text-only · single tool call · interleaved · malformed JSON fragment skipped · `[DONE]` · trailing unclosed tool block · non-dict events · HTTPError with/without readable body (assert secret scrubbing) · timeout message includes model name. Factories: monkeypatch config + fake clients raising `LLMError` in `__init__`; assert `None`, singleton reuse, double-checked lock.

**After landing:** raise CI gate to `--cov-fail-under=90`; update the `pytest.ini` comment block. Keep `branch = True`.
*(Bonus alignment: these five adapters are also the ParallelDispatch transformer bank — this hardening is prerequisite work for the backlog.)*

---

## 5. PHASE 3 — Cold-start seed

New install shows **≥1 LLM-free playbook replay in the first session**, not week three. Use `training_ground/` + `curriculum_seed.json` + `curriculum_evidence_driver.py` to pre-earn 3–5 genuinely useful skills (e.g., run tests, summarize a file, git status report) through the real verification path — **seeded means pre-practiced, never pre-trusted**. No hand-inserted "verified" rows.

---

## 6. BACKLOG — designed and approved in review; **DO NOT BUILD** until the lap counter shows ≥50 logged requests

Each item ships only with its measurement gate.

**B1. ParallelDispatch** (`aios/core/parallel_dispatch.py`)
Modes: `race` (hedge: first acceptable answer wins, cancel rest), `quorum` (fan-out to N branches, gather, combine), `shard` (swarm workers hold different clients inside their own worktrees). Mechanics: `asyncio.gather(*[asyncio.to_thread(client.chat, …)])`, per-branch timeouts, partial-result tolerance (2-of-3 proceeds), existing failover kept *inside* each branch. **Distinct-family guard:** quorum members deduped on model identity, never provider name (Bedrock-serving-Claude + direct-Claude = one generator, reject). Combiner output is a proposal → King clamp → gate. *Metric: quorum answer quality vs single-model on a held-out set; added cost per request.*

**B2. Cabinet (one, at the top)**
Multi-model deliberation seated on distinct families via ParallelDispatch quorum. Convened **only** on triggers: confidence below threshold, YELLOW/RED zone, novel task signature. Output through the King clamp. Workers never get cabinets; they get playbooks + Scope-Locked kit. *Metric: **cabinet lift** = decision win-rate vs single model on ambiguous tasks; cost per decision.*

**B3. Skill Import Pipeline**
Ingest external skill folders → hash-pin in `skills-lock.json` → secret-scan + injection-shield **at import** → quarantine tier (candidacy, not trust) → curriculum runs → promotion only via the standard ≥3-verified-successes path. *Metric: hit-rate before vs after import.*

**B4. Source-strength taxonomy (web facts)**
Mirror of `verification_strength.py` for provenance: web-derived facts enter the KG as low-confidence candidates with source-dependent priors (official docs > maintainer repo > blog > forum), promoted only via corroboration or execution; same `find_conflict`/`reconcile` gate. The internet is commentary, not telemetry.

**B5. FastF1 stint-analysis skill (the motorsport measured demo)**
One real race-engineer workflow (stint report / tyre-deg summary from FastF1 data) built as a GAGOS skill. *Metric: hand-time vs agent-time, error counts — the only legitimate way to ever say "X% faster."*

---

## 7. Definition of Done — Season One
One command boots everything · one live provider verified · UI survives backend death · lap counter live with ≥50 real requests and a visible hit-rate curve · coverage ≥90% gated in CI · first-session sovereign replay works on a fresh install · README/docs pass the banned-words check.

## 8. First instruction to execute
Start at **P0.1**. Work strictly in phase order. After each task: run the relevant tests, show the diff, stop for operator review before the next task. If any settled decision above seems wrong mid-build, flag it with evidence — do not silently redesign.
