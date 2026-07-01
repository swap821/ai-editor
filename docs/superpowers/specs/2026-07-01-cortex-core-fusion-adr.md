# ADR — Cortex-Core Fusion: wiring the organism without imploding

**Status:** Draft for operator review · **Date:** 2026-07-01 · **Author:** Claude (grounded against the actual tree, not a remote read)

> **Provenance note.** This ADR was triggered by two long external analyses (the "Cortex-Core Pattern" + "fusion roadmap" documents). Those documents contain real insight **and** ~7 factually wrong claims about this codebase. Before writing anything here I verified every load-bearing claim against the source files (three parallel read passes, `file:line` evidence). **Section 2 is the verification scorecard — read it before acting on either external document.** The good idea survives; the phantom bugs are named and discarded.

---

## 1. The corrected premise

The external framing was "35 modules, fuse them all without pruning — it's the only way." That framing is wrong on two counts:

1. **The module count is inflated by corpses we just buried.** Earlier today Codex deleted 8 never-imported modules (`swarm_adaptive/conflict/parallel/scout.py`, `memory/pheromones.py`, `policy/*`, `runtime/leases.py`) — reviewed and confirmed dead (`.aios/state/DEAD_CODE_CLEANUP_REVIEW.md`). "Hold 35 modules" was never the real number. **Step zero of any fusion is a real live-dependency graph, not architecting around a count that includes bodies.**
2. **Pruning and bussing are not opposites.** You prune the dead ones *and* decouple the live ones. The real question is not "monolith-35 vs bus-35"; it is: *of the modules that actually do work, which few belong on the synchronous hot path and which many are cold-path observers?*

The genuinely correct instinct in both external docs: a **sync hot path** (security → tool loop → verify) that stays deterministic and fail-closed, plus an **async cold path** for growth modules (self-model, facts, curriculum, self-analysis, council) that must never add turn latency. That instinct is kept. The execution details are corrected below.

---

## 2. Verification scorecard (ground truth — do not skip)

### ✅ Verified TRUE (real, worth acting on)
| Claim | Evidence |
|---|---|
| Backend has **no event bus** (`aios/core/events.py` / `bus.py` absent) | confirmed absent |
| Frontend **has** a cognition bus (`publishCognition`/`subscribeCognition`) | 15 files incl. `frontend/src/superbrain/components/canvas/WorkspaceCanvas.tsx` |
| Confidence filter is **computed but does not gate the default loop** | `confidence_filter.py` used only in `planner.py:23,238`; no confidence branch in `generate` (`main.py:3106-3702`) |
| Self-model **off by default** | `AIOS_NARRATIVE_SELF=False` (`config.py:186`), guarded at `main.py:3266` |
| Earned autonomy **off by default / inert** | `AIOS_EARNED_AUTONOMY=False` (`config.py:181`); `autonomy.py:120-126` returns False |
| Council / role_pass / swarm **opt-in, off by default** | `AIOS_COUNCIL_ORIGINATION=False` (`config.py:142`); `role_pass`/`swarm` body flags default False (`main.py:871,875`) |
| Facts: **no auto-extraction** after read_file/browse_url | human-gated `promote_fact` only (`main.py:1432-1452`); tool_handlers extract text only |
| Privacy filter `_HISTORY_WINDOW = 2` | `privacy_filter.py:73` |
| Privacy filter has **no allowlist / no per-turn override** | no override mechanism in the file |
| Cloud clients **do not stream** | `bedrock.py:219 converse(`; `gemini.py:248 generate_content(` |
| Curriculum matches by **exact `WHERE prompt = ?`** | `curriculum.py:103-107` |
| `infer_task` runs ~41 **uncompiled** regex patterns per call | `model_selector.py:208-221,235-237` |
| Facts recursive CTE has **no `LIMIT` hard-stop** (depth-bounded only) | `facts.py:200-222` |
| Dependency smells real: `httpx2==2.3.0`, `httpcore2==2.3.0`, `annotated-doc==0.0.4`, `mando`, `shellingham`, `sympy`, `hf-xet`, `truststore` all pinned | `requirements.txt` |

### ❌ Verified FALSE (phantom bugs — do NOT "fix" these)
| Claim | Reality |
|---|---|
| "Cloud gets a generic stub system prompt / is blind" | `_GENERIC_SYSTEM_PROMPT` is **dead code**; the real prompt is redacted **in place**, not replaced (`privacy_filter.py:251-263`) |
| "`training_ground/` relative paths get redacted" | Path regexes only match **absolute / `~` / drive** paths; bare relative paths pass through untouched (`privacy_filter.py:53-57`) |
| "Curriculum auto-matching is not wired" | It **is** wired — `record_matching` runs every verified turn (`main.py:3473`) |
| "Autonomy signature uses `||`, collision-prone" | Single `|`, SHA-256 hashed, heavily normalized/secret-redacted first (`autonomy.py:84-116`) |
| "`self_apply` lock is hardcoded next to the proposal file" | Centralized in `config.DATA_DIR` (`self_apply.py:119-122`) |
| "`semantic.py` `remove()` rebuilds FAISS every delete" | `semantic.py` has **no `remove()`**; deletes are O(1) SQL `supersede` flags (`semantic.py:173-194`) |
| "`generate` has ~12 return points" | 10 across all nested closures; `generate` itself has **1** real return (`main.py:3704`) |

### ⚠️ PARTIAL (true in spirit, wrong in mechanism — the nuance IS the finding)
- **"Reflection lessons / skill bonuses never reach the planner."** The planner genuinely **does** query `MistakeMemory` and apply skill bonuses (`planner.py:143-211`). But the planner is only reachable via the **model-invoked `plan` tool** (`tool_agent.py:1227` → `tool_handlers.plan_task`), **not** the default control-flow. So the calibration exists and is correct — it just sits **off the hot path**. (This is the real architectural gap; see §3.)
- **Blob redaction** fully redacts `>500` chars only when `<3` newlines; a many-line non-code blob >500 chars can pass through (`privacy_filter.py:291-306`). This is an under-redaction leak, the opposite of the doc's "over-redaction" worry.

**Net accuracy of the external analysis: ~60-65%.** Useful as a lead generator; unusable as a spec without this filter.

---

## 3. The one real architectural gap

Strip away the phantom bugs and a single coherent gap remains:

> **The sophisticated "brain" runs off the hot path, and the "growth" organs are gated off.**

Concretely:
- The **default turn is a flat tool loop.** The planner — the component that does confidence calibration, mistake recall, and skill-bonus weighting — is a *tool the model may or may not call*, not a guaranteed phase. So on a normal turn, none of that calibration fires.
- **Self-model, earned autonomy, facts auto-extraction** are authored, tested, and **default-off**. They are structural columns holding up empty floors.
- The **backend has no event bus and no shared event schema with the frontend**, which already *is* event-driven. The two halves of the organism don't speak the same language: the backend streams ad-hoc JSON; the frontend has a typed `cognitionBus`.

This is what "fusion" should mean here — **not adding modules, but putting the already-built calibration on the guaranteed path and giving the two halves one nervous-system vocabulary.**

---

## 4. Architecture decision

Adopt a **sync-core / async-cortex** split — with four corrections to the external blueprint that are non-negotiable.

### 4.1 The sync core stays synchronous and keeps authority in the return value
Security gateway → scope lock → tool execution → **verifier → skill-promotion → autonomy** remain **synchronous, in-band, fail-closed**. The verifier's return value **is** the authority. This is the single most important rule and the external blueprint violated it: moving `SKILL_RECORDED` / autonomy-crediting onto an async bus turns a trusted object into a forgeable JSON payload — the exact "runner-token forge" / TOCTOU class this project's own reviews already caught twice. **Promotion and autonomy decisions never leave the synchronous verified path.**

### 4.2 The bus is two-tier: durable-if-stateful, best-effort-if-cosmetic
- **Durable tier** (append to SQLite/WAL *before* dispatch) for anything that changes future state or authority: lessons, skill attempts, facts, curriculum advances. An in-memory `asyncio.Queue` with `put_nowait` + `QueueFull → drop` is **silent data loss** — unacceptable for a verified-learning organism.
- **Best-effort tier** (in-memory, lossy OK) for pure UI/telemetry: the cognition stream the frontend renders. Dropping a "posture changed" event under load is fine.

### 4.3 Cross-process reality
Council workers are **subprocesses**. An in-process bus cannot receive their events. The durable tier (a shared table other processes append to) is the integration point, not an in-memory queue.

### 4.4 Ordering
Autonomy subscribes to both "credit" and "revoke" signals. Unordered `asyncio.gather` can process them out of order and credit something that should be revoked. The durable tier must preserve **per-signature ordering** (monotonic seq per `(turn, signature)`), which an unordered gather bus does not give you.

### 4.5 Shared schema
Define one `Event` schema (`type`, `phase`, `turn_id`, `payload`, `timestamp`, `seq`) that the **existing** frontend `cognitionBus` consumes directly. The backend emits into it; the frontend already knows how to listen. This is the cheapest, highest-value piece and should land first.

---

## 5. Invariants (must hold through every phase)

1. **Authority lives in the synchronous return value**, never behind a lossy or reorderable bus (§4.1).
2. **`aios/security/*` stays FROZEN RED** — strengthen-only, explicit operator approval, never weaken a guardrail to make a test pass.
3. **Fail-closed** — a cortex handler crashing must never crash the core or the turn; a durable-write failure must surface, not silently drop.
4. **Every phase is test-gated** — all 1391 backend tests stay green; turn latency measured before/after each module moves.
5. **One writer per tree** — the two-agent protocol holds; no big-bang refactor.

---

## 6. Phased migration (incremental, test-gated — NOT an 8-week gospel)

Effort/risk are honest estimates, not commitments. Each phase is independently shippable and reversible.

**Phase 0 — Live-dependency graph + supply-chain triage** *(small, low risk)*
- Generate the actual import graph of `aios/` (what imports what). Establish the real live-module count post-deletion.
- Triage the verified dependency smells: resolve or document `httpx2`/`httpcore2` (are these real forks or typosquat risks?); confirm `sympy`/`hf-xet`/`shellingham`/`mando` are needed transitives or drop them. Split core vs optional deps.

**Phase 1 — Shared event schema + best-effort cognition stream** *(small, low risk, highest value)*
- Add `aios/core/events.py` (typed `Event`, phases, event types) matching the frontend `cognitionBus` vocabulary.
- Convert the existing ad-hoc SSE JSON in `generate` to emit typed `Event`s. No behavior change; the frontend just gets a clean contract.

**Phase 2 — Wire the confidence gate (real, verified-missing)** *(medium)*
- On the default path, when interpreted confidence is below `CONFIDENCE_THRESHOLD` (0.72), pause and ask — the one genuinely-missing hot-path behavior. Emit a typed `confidence.gated` event.

**Phase 3 — Put the planner's calibration on the guaranteed path** *(medium)*
- The planner already queries MistakeMemory and applies skill bonuses; the gap is that it only runs via the `plan` tool. Decide: either always run a lightweight calibration pre-pass, or make the loop consult mistake/skill recall directly (it already recalls into the prompt at `main.py:3213,3231` — close the loop to *behavior*, not just prompt text).

**Phase 4 — Durable cortex tier for cold observers** *(medium/high)*
- Introduce the durable append-then-dispatch bus. Move **only** cold, re-derivable, non-authority modules onto it: self-model rebuild, facts extraction, self-analysis scans, council deliberation triggers, curriculum matching (already wired — becomes an event consumer).
- Turn on the gated organs **one at a time**, each behind its existing flag, each with a latency + green-tests gate before the next.

**Phase 5 — Product hardening (verified quick wins, see §7)** *(medium)*

**Explicitly deferred:** full council fan-out, backend `TurnStateMachine`, multi-worker uvicorn (the global `_EPISODIC`/`_SEMANTIC` singletons will desync under `--workers 2` — real, but not urgent while single-worker). Do not let the biology metaphor pull these forward before there's demand.

---

## 7. Verified quick wins (worth doing regardless of the bus)

1. **Cloud streaming** — `bedrock.py` (`converse_stream`) and `gemini.py` (streaming variant) buffer the whole response today; users wait 10-30s with no feedback. Real, verified, self-contained.
2. **Privacy-filter under-redaction leak** — the `>500 char / <3 newline` blob rule lets many-line non-code blobs through (`privacy_filter.py:304-305`). Tighten to truncate-not-redact *and* close the newline gap.
3. **Adaptive history window** — `_HISTORY_WINDOW=2` is aggressive for multi-turn coding sent to cloud; make it task-aware (keep 2 as the floor).
4. **`infer_task` precompile** — compile the ~41 regexes once at module load (`model_selector.py`).
5. **Facts CTE hard-stop** — add a `LIMIT` row-cap to the recursive CTE as defense-in-depth (`facts.py`), even though depth already bounds it.

---

## 8. What NOT to do (discard these)

- Do **not** "fix" the `||` delimiter, the `self_apply` lock path, the `semantic.py remove()` rebuild, or the "12 return points" — verified non-issues (§2).
- Do **not** un-redact `training_ground/` paths on the belief they're being redacted — they aren't.
- Do **not** move skill-promotion / autonomy onto the async bus (§4.1).
- Do **not** treat the biology metaphor as an acceptance test. It's a design compass. The deliverable is a well-factored async system with a durable log and a fast sync core — provably correct, not "awake."

---

## 9. Decision requested

1. Approve the sync-core + two-tier-durable-cortex direction (§4)?
2. Green-light **Phase 0 + Phase 1** as the first commit (schema + graph + dep triage) — lowest risk, unblocks everything?
3. Confirm the deferred list (§6) stays deferred.

— Grounded against the tree at `d116434` + working set; every §2 claim carries `file:line` evidence.
