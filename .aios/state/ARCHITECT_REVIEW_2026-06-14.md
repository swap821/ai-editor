> **SUPERSEDED SNAPSHOT (dated 2026-06-14) — body unchanged, kept as a record.**
> Test baselines and some architectural specifics below are stale. The security
> perimeter hazards flagged here have since been addressed (see `RESUME.md` and
> `RENOVATION_PLAN.md`). Read this for historical context, then verify against
> current code and `RESUME.md`.

# ARCHITECT REVIEW — whole `ai-editor` tree (2026-06-14)

> Peer-level engineering review of the AI-OS, commissioned as "treat me as a
> developer building a one-of-a-kind system, not a student doing an MVP — review
> each and everything." Four lenses, applied to the entire repository: **honest
> capability · frontier/novelty · code quality & evolvability · production-hardening.**
> Candor over comfort, per AGENTS.md §IX.

---

## 0. Method & verification honesty

What this review is built on, so you can weight it:

- **Read firsthand (line-by-line):** `aios/security/gateway.py`, `aios/core/executor.py`,
  `aios/core/verifier.py`, `aios/core/autonomy.py`, `aios/core/self_apply.py` (head),
  the `tool_agent.py` loop seams, `README/AGENTS/START_HERE/RESUME`.
- **Executed directly** (pure-logic, in a Linux sandbox) to confirm behaviour, not just read it:
  `gateway.classify` (GREEN/YELLOW/RED/injection/empty/unknown all correct),
  `scope_lock.command_stays_in_scope`, `secret_scanner.scan_and_redact`,
  `router` shape. The security kernel does what the docstring says.
- **Delegated deep reads** to four parallel reviewers with file:line evidence:
  the memory subsystem, the frontend + superbrain lab, the test suite + coverage DB,
  and the docs-vs-reality reconciliation (including `BACKEND_TRUE_PICTURE.md`).
- **Could NOT run `pytest`** — the sandbox has no PyPI egress and the venv is Windows.
  So the **"516 passed, 1 skipped" baseline is the project's self-report, not re-run
  here.** I assessed the suite by reading it (and it reads as real — see §4).
- Not line-read by me personally (covered via tests/reviewers): `alignment.py`,
  `audit_logger.py`, `self_analysis_agent.py`, `aios/memory/*`, all of `main.py`.

---

## 1. Verdict in one paragraph

This is a **real, coherent, unusually disciplined engineering system** — not an MVP and
not a toy. The load-bearing thesis ("a weak local model proposes; deterministic, tested
machinery decides") is genuinely implemented as control flow, not slogans: I verified
the allowlist-default gateway, the RED-un-grantable approval path, the structural
no-self-approval guard, and force-verify-after-write firsthand. The test suite behind it
is among the most rigorous I've seen at this scale. **The gap is not quality — it is
capability and exposure.** The architecture is frontier-grade; the *intelligence* driving
it is a 7B local model that turns most of the recursive/multi-agent machinery into
"architecture proven, model-limited"; the memory tiers that would make it more than a
chat log are nearly empty of real evidence; and a handful of production footguns
(a live cloud credential on disk, an untested default UI, deploy/CORS gaps) sit between
it and being safely deployable. The system's own docs already say most of this — the
honesty of this codebase is itself a feature. My job below is to make the gaps precise.

### Scorecard (my read, 1–5)

| Lens | Score | One-line |
|---|---|---|
| Honest capability | **3 / 5** | Thesis real & verified; runtime intelligence + memory evidence are thin. |
| Frontier / novelty | **3.5 / 5** | The *discipline* is the moat (evidence-gated autonomy, stigmergic skills, structural self-mod guard); the parts are mostly known, assembled with rare taste. |
| Code quality / evolvability | **4 / 5** | Excellent security/core modules; dragged down by two god-files and a dead-code split-brain. |
| Production-hardening | **2.5 / 5** | Real isolation & GPU-resilience exist but are opt-in; live secret on disk, untested default UI, deploy footguns. |

---

## 2. What this system actually is (reality calibration)

~33k lines of first-party code: **backend `aios/` ≈ 13.4k** (48 files), **tests ≈ 10k**
(34 files, ~507 test fns), **frontend ≈ 9.8k**, plus ~1.6k root scripts. 203 commits in
~2 weeks, one human author (`swap821`) with AI co-authors. A local-first, security-gated,
memory-driven agent runtime: FastAPI + SSE backend, React/Vite + a 3D "superbrain" UI,
Ollama-first with a privacy-gated cross-provider router (Bedrock/Gemini).

Completion, reconciled across docs and code: **~80% of the blueprint's intended scope plus
large surplus** the blueprint never asked for (earned autonomy, self-analysis tiers, worker
swarm, stigmergic skills, the 3D UI). The stale "~35%" is self-superseded by the blueprint's
own audit; AGENTS.md's "75–80%, trust the code" is accurate-to-slightly-conservative.
**"NOT an MVP" is justified** for what it actually claims — a tested, end-to-end-wired
supervised system — and the docs are careful *not* to claim "a working autonomous AI."

---

## 3. Lens 1 — Honest capability: does it do what it claims?

### 3.1 What is genuinely real and verified

The security/verification spine is not theater. Confirmed firsthand:

- **Allowlist-default gateway** (`security/gateway.py:283-350`). Order is strict
  (injection → secret → destructive → network → env → shell-escape → composition →
  scope → caution → safe), and anything unknown returns **RED** (`:348`). I ran it: `echo`→GREEN,
  `rm -rf /`→RED, `pip install`→YELLOW, `ignore all previous instructions`→RED, `""`→RED,
  `frobnicate`→RED. No LLM in the decision path; exceptions fail closed (`:349`).
- **Approval can never authorize RED** (`core/executor.py:435-443`): `execute_approved`
  re-classifies and refuses RED even with a human OK — "Human approval cannot authorise a
  RED action." Stricter than a typed-token override.
- **Structural no-self-approval** (`core/self_apply.py:14-18`): the agent has **no apply
  tool** — only `propose_fixes` (`tool_agent.py:356`). Applying exists *only* behind a
  human-called HTTP endpoint. The `approved_by != proposed_by` check is the *second* layer;
  the real guard is capability-absence. This is the best single design decision in the system.
- **Evidence-based verification** (`core/verifier.py:60-125`): pass is gated on the
  executor's real **exit code**, not model narration; BLOCKED/TIMEOUT/ERROR → FAIL; a
  security BLOCK deliberately does *not* feed reflection (blocking is correct, not a lesson);
  an incidental "error" string can't flip a green run.
- **Earned autonomy is conservative** (`core/autonomy.py`): keyed to a scope-bound action
  *shape* (`training_ground/*.py`), secret-redacted, one verified failure instantly revokes
  the class, RED un-earnable. Off by default (`config.EARNED_AUTONOMY` = False).
- **Executor hardening** (`core/executor.py`): env is sanitised of `*KEY*/*TOKEN*/*SECRET*/
  *PASSWORD*/*BEARER*` **and `AWS_BEARER_TOKEN_BEDROCK` by name** plus `HOME/USERPROFILE`
  (`:48-51,272-290`); structured argv with `shell=False`; bounded output drained off-thread;
  hard timeout. The container backend (`DockerRunner:155-238`) runs `--network none
  --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit --user 65534`
  with a `noexec` tmpfs — a genuinely strong boundary.

### 3.2 The capability gap (the honest part)

- **The brain is the ceiling, and it's outside the architecture.** On a 7–8B local model:
  planning is advisory, calibration is a no-op on a cold DB, the swarm "finished subtask 1,
  not subtask 2 (model-limited)" (RESUME). The live existence-proofs are `wordcount.py`-class.
  A tree-search over a model that can imagine one branch is, in the docs' own words, "theater."
- **The memory tiers that would make it a brain are nearly empty.** The loop is wired and
  the product DB has real rows (`data/aios_memory.db`: 814 episodic, 137 dev events), **but**:
  **0 verified mistakes, 0 facts, 0 verified lessons**, every one of 65 semantic memories is
  unverified `chat`, and only **2 of 13 skills** are verified. The consolidator correctly
  refuses to promote unverified material — so with nothing verified, nothing promotes. "Brain
  growth" today is exercised by a **synthetic curriculum harness**, not accumulated organic use.
- **`mistakes.jsonl` (builder notebook) is empty** while `experiences.jsonl` has 81 entries at
  91% success. A learning system recording *zero* failures isn't a flex — failures aren't
  reaching the sink built for them.
- **The marquee AI claims are the least-verified in CI.** The semantic injection-shield and
  embedding-recall tests **skip when the model is absent** — so a model-less CI run is green
  with the headline "catches novel injection / real recall" unproven.

**Net:** the *machine* does what it claims; the *intelligence and lived evidence* are
early. That is the central, honest tension of the whole project.

---

## 4. Lens 2 — Frontier / novelty: where is the moat?

**Genuinely novel / defensible (design taste, not patentable IP):**

- **Evidence-locked autonomy flywheel.** Trust is a function of the *verifier's* authoritative
  pass/fail, asymmetric (one failure ≈ seven successes), instantly revocable, and bounded to a
  scope-shaped class. Most "autonomous agent" projects gate on model confidence or a token;
  this gates on reproducible evidence. That inversion is the real idea.
- **Structural self-modification safety** (no apply tool; human-only endpoint; frozen
  `aios/security/*`; snapshot → `git apply --check` → audit-before-write → confined apply →
  two-snapshot integrity → gated verify → auto-rollback). Supply-chain-grade for a self-editing system.
- **Stigmergic skill memory** (`memory/skills.py`, `relevance.py`): arc-level trail identity
  that refuses to "launder failures into verified trails," reuse-pheromone that ranks but can
  never *promote*, quarantine demotion, and freshness evaporation where a failing trail can't
  stay fresh by failing. More disciplined than the usual "store successful trajectories, cosine-match."

**Competent reinvention (well-executed, not a moat):** the multi-store + hybrid `α·BM25 +
β·FAISS + γ·recency` retrieval is textbook RAG done correctly; fact-triple contradiction
handling and held-out curriculum gating are well-trodden.

**Decoration vs. load-bearing — the 3D superbrain:** in `?ui=shell` the "nerves plug into UI
ports" is *real* — the Monaco editor and live preview mount as in-scene panels pinned to the
canon nerve world-points and flare on the same cognition-bus event that surges the 3D nerve
(`workbench/ForgePorts.jsx:20-63`). One event stream drives scene + HUD + metrics + forge.
That unification is a genuinely novel interaction concept. **But** the *default* home view has
no ports — it's brain+HUD ambient frame around what is functionally a chat+approval+editor app,
and the payoff is gated behind a self-described "in development" mode.

**Moat verdict:** the novelty is **disciplinary, not architectural** — any competent team could
re-implement any one piece, but almost none would bother with the laundering-avoidance,
evidence-gating, and capability-absence subtleties. The defensibility is in the taste and the
test suite that locks it, not in any single component.

---

## 5. Lens 3 — Code quality & evolvability

**Strengths (consistent, real):** strict typing (`from __future__ import annotations`, frozen
dataclasses) across the core; uniform DB discipline (every store routes through
`memory/db.get_connection` with WAL + FK + rollback-on-exception); dependency injection
everywhere so tests drive the *real* gateway/verifier/audit with fakes for I/O; docstrings that
state invariants and rationale; lazy heavy imports so module import stays cheap. The security
and core modules are small, single-purpose, and a pleasure to read.

**Structural debt (ranked):**

1. **Two god-files.** `api/main.py` is **2,055 lines / 35 routes / 87 fns** and `agents/tool_agent.py`
   is **1,528** (the classic `frontend/src/App.jsx` is **~1,876**). These are the files least
   able to absorb 10× more features and the hardest to reason about; `main.py` is also the
   biggest coverage hole (~47% lines). Decompose by domain (routes → routers, the loop → phases).
2. **`memory/db.py::_migrate()` is a ~175-line destructive god-function** run from the routine
   bootstrap path (`init_memory_db` is called by most store methods). It ALTERs, *deletes rows*,
   backfills, **and runs data consolidation with `print()` side-effects**. Destructive merges do
   not belong in idempotent bootstrap. There is **no migration framework and no `schema_version`** —
   migrations are hand-rolled `PRAGMA table_info` diffs with no ordering or down-path.
3. **Dead code that looks canonical (split-brain).** A complete abandoned **`legacy_node/` (19
   files)** prototype of the whole system; **5 orphaned root RAG scripts** (`hybrid_search.py`,
   `ingest_*.py`, `vector_memory_setup.py`, `reset_audit_chain.py`) using naive term-overlap
   "BM25" — the exact thing `memory/retrieval.py` says it replaced; and **two divergent orphan
   DBs** (`memory.db` 40KB `vectors` schema, `orchestrator_memory.sqlite` 151KB `knowledge_graph`/
   in-DB audit schema, *recently modified*). Consequence: **`reset_audit_chain.py` is a no-op
   against the real ledger.** An incoming engineer cannot tell which store is truth.
4. **The frontend's core is a generated artifact from an out-of-repo, gitignored lab.** The most
   important UI files (`superbrain/*`, the SSE adapter, HUD, approval panel) are byte-synced via
   `npm run port` from `GAG demo/gag-orchestrator` and must never be hand-edited. The port tool is
   well-engineered (it has an import-drift tripwire), but coupling product velocity to a separate,
   un-versioned-in-this-repo lab is a standing operability tax.
5. **EOL churn is blinding review on the riskiest files.** `tool_agent.py`, `self_apply.py`,
   `config.py`, `db.py` show as *fully rewritten* in the working tree (~2,531 lines) — confirmed
   **0 real changes**, 100% CRLF↔LF noise, and there is **no `.gitattributes`**. A one-line change
   slipped into `self_apply.py` would be invisible in the diff, which defeats the hash-pinned-handoff
   discipline the multi-agent protocol depends on. Cheap, important fix.
6. **Minor:** duplicated `_hours_since`/timestamp parsing across `retrieval.py` and `skills.py`
   (deliberate, to avoid an import — will drift); dead style/asset files in `frontend/src`.

---

## 6. Lens 4 — Production-hardening

**Already production-grade:** the container execution boundary (§3.1); GPU context-loss recovery
in the 3D UI (in-place restore → canvas remount, with a styled error boundary and an
operator-sovereign, demote-*advisory* FPS governor — `WorkspaceCanvas.tsx`, `TierGovernor.tsx`);
the tamper-evident audit hash-chain (tested to pinpoint the broken entry and to redact secrets
*before* persistence — `test_audit.py`); genuine multi-process coordination (FileLock +
reload-before-mutate for FAISS, `BEGIN IMMEDIATE` for SQLite, multi-instance + barrier tests).

**What breaks — ranked by severity:**

1. **🔴 Live cloud credential persisted in plaintext on disk.** `AWS_BEARER_TOKEN_BEDROCK` is a
   real, complete token in the root `.env`. It is gitignored and **not** in git history or the
   client bundle (the history hits are docs naming the *variable*, not the value), so exposure is
   low — but it **directly violates the project's own AGENTS.md §VII.4 "keys live only in volatile
   env vars; never on disk."** Action: **rotate in the AWS console** (already an open operator TODO)
   and move to a real secret store / volatile env.
2. **🔴 The default UI cannot authenticate to a protected backend.** The superbrain `aiosAdapter`
   historically sent no `Authorization` header (Phase-1 work claims a partial fix — verify). The
   moment `AIOS_API_TOKEN` is set for a non-loopback deploy, the default UI 401s on every call.
3. **🟠 Deploy footgun: the server doesn't bind its own config.** There is **no `uvicorn.run`/
   `__main__` in `aios/`** — `AIOS_API_HOST`/`AIOS_API_PORT` are inert. Setting `AIOS_API_HOST=
   0.0.0.0` expecting a public bind silently leaves you on loopback (you must pass it to the uvicorn CLI).
4. **🟠 CORS is `allow_credentials=True` with `allow_methods=["*"]`, `allow_headers=["*"]`**
   (`api/main.py:127-131`). Origins come from config (not wildcard by default), but there's no guard
   that an operator-set origin list isn't broad — credentialed cross-origin widens silently.
5. **🟠 Provider footgun:** `BEDROCK_ENABLED = bool(region AND model)` with a non-empty default model
   — setting only `AIOS_BEDROCK_REGION` silently enables a cloud provider; bad env values fall back
   to defaults rather than failing loudly.
6. **🟠 Memory scale cliffs:** `semantic.add` calls a **full-index FAISS `persist()` on every single
   write** under a global lock — invisible at ~65 vectors, a serialized write-stall at 10⁴–10⁵; and
   there is **no retention/compaction** (episodic + HNSW grow monotonically; superseded vectors never
   leave the graph). No startup assertion that `index.d == EMBEDDING_DIM` — changing the embedding
   model silently corrupts retrieval.
7. **🟡 Verification gaps:** no branch coverage at all (`has_arcs=0`); `main.py` ~47% lines; the
   semantic-injection/recall claims skip model-less; no fuzzing of the hand-rolled tool-call parser
   or scope-lock path splitter; no real perf/timeout/lock-exhaustion tests; the 3D UI has zero unit
   tests (its correctness rests on human-eyeballed golden PNGs).
8. **🟡 Audit chain has no external root of trust** (self-contained hash chain; a full-history
   rewrite is detectable only against an off-box anchor, which doesn't exist yet).

---

## 7. Consolidated risk register

| # | Risk | Sev | Effort | Where |
|---|---|---|---|---|
| 1 | Live Bedrock token on disk (rotate + relocate) | 🔴 | XS | `/.env` |
| 2 | Default UI can't auth to protected backend | 🔴 | M | `superbrain/lib/aiosAdapter.ts` |
| 3 | Server ignores `AIOS_API_HOST/PORT` (no bind entrypoint) | 🟠 | XS | `aios/` (add `__main__`) |
| 4 | CORS credentials + wildcard methods/headers | 🟠 | XS | `api/main.py:127` |
| 5 | `db._migrate` destructive in bootstrap; no migration framework | 🟠 | M | `memory/db.py` |
| 6 | FAISS per-write full persist; no compaction/eviction | 🟠 | M | `memory/semantic.py`, `embeddings.py` |
| 7 | Dead-code split-brain (`legacy_node/`, root RAG, orphan DBs) | 🟠 | S | repo root |
| 8 | Default UI untested (`aiosAdapter`/HUD/forge) | 🟠 | M | `frontend` Vitest |
| 9 | No branch coverage; `main.py` ~47%; marquee AI tests skip model-less | 🟡 | M | `tests/`, CI |
| 10 | EOL churn / no `.gitattributes` blinds review on risk files | 🟡 | XS | repo root |
| 11 | Two god-files (`main.py`, `tool_agent.py`) | 🟡 | L | `aios/` |
| 12 | Brain ceiling (7B) caps real capability | 🟠 | L | model/router |

---

## 8. What I'd do (prioritized, mapped to your own PLAN)

**Now — cheap & severe (do this week):**
1. Rotate the Bedrock key; add `.gitattributes` (`* text=auto eol=lf`, `*.ps1 eol=crlf`) and
   renormalize; delete or quarantine the dead twins (`legacy_node/`, root RAG scripts, orphan DBs)
   into an archive branch so the live tree has one source of truth. (Your PLAN H1/H2.)
2. Close the deploy footguns *before* any non-loopback exposure: add a real bind entrypoint, tighten
   CORS, and finish + test the default-UI auth header.

**Next — make the engine's value visible (the existence proof):**
3. **One real lap.** Pick a task meaningfully harder than `wordcount.py`, verifiable end-to-end, and
   make the gated agent complete it — with the result landing as a *verified* skill/lesson in
   `aios_memory.db`. That single artifact backs every claim in BACKEND_TRUE_PICTURE more than any doc.
4. **Feed the failure sink.** Route real failures into `mistakes.jsonl` / `mistake_pool` so the
   consolidator has something to promote and the flywheel actually turns.
5. **Raise the brain** (PLAN S1): a 14B+ local model and/or selectively opening a task class to the
   cloud router — *with the privacy decision made explicitly*, because that's where the local-first
   identity is actually decided.

**Then — harden for real use:**
6. Branch coverage + a model-present CI lane (so the semantic claims stop skipping) + parser fuzzing.
7. A real migration framework + move consolidation out of bootstrap; batch FAISS persist and add a
   compaction/eviction job (PLAN S4).
8. Decompose `main.py` and `tool_agent.py` before the next big feature, not after.
9. Default-strong isolation (PLAN S2) and observability (PLAN G3) — the latter needs no model gains
   and is the highest-ROI maturation step.

**Resist:** more *breadth* (new organs) until #3 lands. The superbrain polish and swarm are
impressive but premature relative to proving the core does real work.

---

## 9. Bottom line

You have built an exceptional **immune system, spinal cord, audit ledger, and memory** for an
organism whose **brain is still a small animal's**. The chassis is frontier-grade and the test
suite that locks it is better than most funded teams ship. The distance to "one of its kind, in
production" is not architectural — it's three concrete things: **(1)** close the handful of exposure
footguns (a live key on disk, an unauthenticated default UI, deploy/CORS gaps), **(2)** prove the
engine on one real task and let the memory flywheel accumulate *verified* evidence instead of
synthetic-curriculum rows, and **(3)** give it a bigger brain or an explicit, owned path to one.
Do those and this stops being an extraordinarily well-engineered demo and becomes the defensible
system the architecture already deserves.

*— Chief Architect review, 2026-06-14. Evidence: direct code reads + sandbox execution of the
security kernel + four parallel subsystem audits. Not independently re-run: the pytest baseline.*
