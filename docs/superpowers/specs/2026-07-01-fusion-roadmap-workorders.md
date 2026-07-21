# Fusion Roadmap — Work Orders for Kimi & Codex

**Status:** Ready to hand off · **Date:** 2026-07-01 · **Author:** Claude · **Reviewer:** Claude (read-only, against hash-pinned handoffs)
**Parent spec:** `docs/superpowers/specs/2026-07-01-cortex-core-fusion-adr.md` (read §2 scorecard + §4 decision before starting)

> **What this is.** Executable, disjoint-file work orders derived from the verified ADR. Two lanes — **Kimi (Lane K, independent quick wins)** and **Codex (Lane C, the spine)** — designed so the two builders never touch the same file. Every task carries scope, exclusive file list, steps, acceptance gates (exact commands), invariants, and a done-signal.
>
> **This roadmap adds no new modules.** The goal is: put the already-built brain on the guaranteed turn path, give backend+frontend one event vocabulary, and land the verified quick wins. Fusion = wiring + subtraction, not accumulation.

---

## 0. Global invariants — apply to EVERY task, both lanes (non-negotiable)

1. **Frozen security spine is untouchable.** `aios/security/{gateway,scope_lock,secret_scanner,audit_logger,injection_shield}.py` are RED/frozen (AGENTS.md §XI, §VIII). No task here edits them. `privacy_filter.py` lives in `aios/core/` and IS editable — but **strengthen-only**: never reduce redaction to make a test pass.
2. **Authority stays synchronous.** Do NOT move skill-promotion, autonomy-crediting, or verification onto any async/event path. The verifier's return value is the authority; an event payload is not. (ADR §4.1 — this is the one line the external blueprint got dangerously wrong.)
3. **Fail-closed; never disable a guardrail.** No `--dangerously-skip-permissions`. Unclear risk → stop and escalate.
4. **Additive / backward-compatible SSE.** The frontend cognition bus already consumes the SSE stream (`frontend/src/superbrain/lib/aiosAdapter.ts`, `startAiosPolling`). New event fields must be **additive** — do not remove or rename existing frame fields, or you break the being. **Do not hand-edit `frontend/src/superbrain/*`** (port-generated, overwritten by `npm run port`); this roadmap requires **zero** frontend edits.
5. **Tests are the gate.** `.venv\Scripts\python -m pytest -q` must stay green — trust the LIVE count (baseline at handoff: **1391 passed / 1 skipped / ~89%**). Coverage floor 85%: `--cov-fail-under=85`. Every behavior change ships with a new test (TDD: red → green). No network/model/shell side-effects in test paths — use fakes + `Depends(...)` overrides (AGENTS.md §XI).
6. **Config is centralized.** New flags go in `aios/config.py` only, `_env_bool`/env-driven, default **off/local** so nothing changes behavior until the operator opts in.
7. **Do NOT commit or push.** The operator commits. Signal done via `agent_coord.py handoff` (hash-pins the tree) + a `.aios/state/RESUME.md` update + one `experiences.jsonl` line. No broad-glob deletes — explicit paths only.
8. **One writer per tree.** Hold the `worktree` lease before editing (`python agent_coord.py status`). Lanes K and C are file-disjoint (§4) so they can run in separate worktrees; if sharing one tree, run **Lane K first, then Lane C** (recommended — see §5).

---

## 1. The DO-NOT-FIX list (verified non-bugs — skip these)

The external analyses flagged these; verification proved them false or misattributed. **Do not "fix" them** — you'd be changing correct code and burning review cycles:

- The `||` autonomy delimiter → it's a single `|`, SHA-256 hashed, normalized (`autonomy.py:84-116`). Fine.
- `self_apply` lock "hardcoded next to file" → it's centralized in `config.DATA_DIR` (`self_apply.py:119-122`). Fine.
- `semantic.py remove()` "rebuilds FAISS" → there is no `remove()`; deletes are O(1) SQL `supersede` (`semantic.py:173-194`). Fine.
- "`generate` has 12 return points" → 10 across nested closures, 1 real. Not a defect.
- "Cloud gets a blind generic-stub prompt" → the stub is dead code; real prompt is redacted in place. (You MAY delete the dead `_GENERIC_SYSTEM_PROMPT` constant as cleanup, but the behavior is fine.)
- "`training_ground/` relative paths are redacted" → they are not matched by the path regexes; they pass through. No change needed.
- "Curriculum auto-matching isn't wired" → it runs every verified turn (`main.py:3473`). Fine.

---

## 2. LANE K — Kimi (independent quick wins; parallel-safe; no `main.py`)

**Exclusive files for Lane K:** `requirements.txt` (+ optional new `requirements-optional.txt`), `aios/core/bedrock.py`, `aios/core/gemini.py`, `aios/core/privacy_filter.py`, `aios/core/model_selector.py`, `aios/memory/facts.py`. **Kimi does not touch `aios/api/main.py`, `aios/core/events.py`, `aios/core/planner.py`, `aios/core/confidence_filter.py`** (Lane C owns those).

### K1 — Dependency triage + live import graph  *(Phase 0 · small · low risk)*
- **Scope:** Resolve the verified supply-chain smells. Produce the real post-deletion import graph.
- **Steps:**
  1. Investigate `httpx2==2.3.0` and `httpcore2==2.3.0` — are these needed at all? Grep imports (`import httpx2`, `httpcore2`) across `aios/`. If unimported → remove from `requirements.txt`. If imported → document exactly which module needs the 2.x API and why standard `httpx==0.28.1` can't serve it. **Flag if they are typosquat-shaped (no legit provenance).**
  2. Same import-existence check for `sympy`, `hf-xet`, `shellingham`, `mando`, `truststore`, `rank-bm25`. Move genuinely-optional/cloud-only deps (`google-genai` pattern) into a `requirements-optional.txt` or a documented block; keep the core install lean. Do not remove a dep that is actually imported.
  3. Emit `docs/superpowers/specs/2026-07-01-import-graph.md`: the actual `aios/` internal import edges (what imports what) + a "live vs orphaned" column. This is the graph the ADR §1 "step zero" needs.
- **Acceptance:** `pytest -q` green; a clean `pip install -r requirements.txt` still resolves; import graph doc committed; every removed dep proven unimported (grep evidence in the handoff note).
- **Invariant:** do not change pinned versions of deps that ML stack needs (torch/transformers/faiss/sentence-transformers) — Python-version skew is already a known pain (memory 5891). Removal only, no upgrades, unless a removal forces a re-pin (then document).

### K2 — Cloud streaming (client layer only)  *(quick win · medium)*
- **Scope:** Give `bedrock.py` and `gemini.py` streaming-capable methods so a turn can yield tokens as they arrive. **Client layer only** — the `main.py` endpoint wiring to consume the stream is a Codex follow-up (C4), noted as a seam so Kimi never touches `main.py`.
- **Steps:** Add `converse_stream`-backed (`bedrock.py`) and streaming (`gemini.py`) generator methods behind the existing client interface (keep the current non-streaming method working). Cover with **fake-transport unit tests** (no live cloud calls — inject a fake client per §XI). Keep secret-scrubbing/privacy-filter application intact on the streaming path.
- **Acceptance:** new streaming methods + tests green; existing non-streaming callers unaffected; no live network in tests.
- **Seam note:** leave a one-line `# STREAM SEAM (C4): main.py generate() may consume this` marker; do not wire it.

### K3 — Privacy-filter leak + adaptive history  *(quick win · medium · strengthen-only)*
- **Scope:** Close the verified under-redaction gap and make the cloud history window task-aware.
- **Steps:**
  1. `privacy_filter.py:304-305` — the `>500 char / <3 newline` blob rule lets a many-line non-code blob >500 chars pass. Change to **truncate-not-redact** (send first N lines + `[...truncated...]`) AND close the newline gap so large blobs can't slip through unredacted. This STRENGTHENS privacy.
  2. Make `_HISTORY_WINDOW` (currently `=2`, `privacy_filter.py:73`) task-aware with a **floor of 2** — never drop below 2; allow a few more turns for coding tasks. Config-driven, default preserves current behavior for non-coding.
- **Acceptance:** new tests prove (a) a large multi-line non-code blob is now truncated/redacted before cloud send, (b) history floor holds at 2; `pytest -q` green.
- **Invariant:** strengthen-only. If any change would send MORE raw content to cloud than before, it's wrong.

### K4 — Micro-correctness: regex precompile + CTE hard-stop  *(quick win · small)*
- **Scope:** Two verified low-risk hardenings.
- **Steps:** (a) `model_selector.py:208-221` — precompile the ~41 `_CODING_HINTS`/`_REASONING_HINTS` patterns once at module load; `infer_task` uses the compiled objects. (b) `facts.py:204-222` — add a `LIMIT` row-cap to the recursive CTE as defense-in-depth (depth already bounds it; this caps pathological fan-out).
- **Acceptance:** behavior identical (same task classification, same traversal results within depth); new test asserts the CTE cap; `pytest -q` green.

---

## 3. LANE C — Codex (the spine; sequential C1→C2→C3; owns `main.py`)

**Exclusive files for Lane C:** `aios/api/main.py`, `aios/core/events.py` (NEW), `aios/core/planner.py`, `aios/core/confidence_filter.py`, plus new tests. **Codex does not touch any Lane K file.**

### C1 — Shared event schema + typed SSE  *(Phase 1 · small/medium · highest value)*
- **Scope:** Give the backend one typed event vocabulary that the existing frontend cognition bus already understands, emitted additively over the current SSE stream.
- **Steps:**
  1. Create `aios/core/events.py`: a typed `Event` dataclass — `type` (enum), `phase` (enum: chemotaxis/reflex/emotion/narrative/wonder), `turn_id`, `payload: dict`, `timestamp`, `seq: int` (monotonic per turn, for ordering). `to_json()`/`from_json()`. Enum values must MATCH the frontend cognition vocabulary (grep `frontend/src/superbrain/**` for `publishCognition` event `type` strings and align — read them, don't invent).
  2. In `generate` (`main.py`), emit the existing SSE frames THROUGH this schema **additively** (keep every current field; add `phase`/`seq`). The `route` frame (AGENTS.md §XI) and existing frame consumers must keep working byte-for-byte on the fields they already read.
- **Acceptance:** `pytest -q` green; a test asserts old frame fields are unchanged (backward-compat) and new fields present; **no frontend edits** and the SSE contract is a superset of today's.
- **Invariant:** additive only (Global §4). This is pure plumbing — no behavior change to the turn.

### C2 — Wire the confidence gate onto the default path  *(Phase 2 · medium · the one real missing hot-path behavior)*
- **Scope:** On a normal turn, when interpreted confidence is below `CONFIDENCE_THRESHOLD` (0.72, `config.py:206`), pause and ask the user to clarify — instead of proceeding blind. Today confidence is computed only inside the planner, which is off the default path (ADR §2/§3).
- **Steps:** In the default `generate` flow, after alignment/interpretation, compute (or reuse) the confidence signal and add a gating branch that emits a typed `confidence.gated` event (C1 schema) and yields a clarification request, halting the tool loop. Reuse the existing alignment "ask" pause plumbing (`main.py:3191-3198`) as the pattern — do not build a parallel mechanism.
- **Acceptance:** new test: a low-confidence turn pauses and asks (no tool execution); a high-confidence turn proceeds unchanged. `pytest -q` green. Existing turns above threshold are byte-compatible.
- **Invariant:** the gate ADDS a pause; it must never auto-execute anything. Fail-closed: if confidence can't be computed, treat as low (ask), not high.

### C3 — Put planner calibration on the guaranteed path  *(Phase 3 · medium)*
- **Scope:** The planner already queries `MistakeMemory` and applies skill bonuses (`planner.py:143-211`) — but only runs when the model calls the `plan` tool. Close the loop so the default turn benefits from mistake-recall + skill-weighting as **behavior**, not just prompt text (today lessons/skills are recalled into the prompt at `main.py:3213,3231` but don't calibrate the loop).
- **Steps:** Choose the lighter-touch option and document why: either (a) run a lightweight calibration pre-pass on every turn that surfaces relevant verified mistakes/skills into the loop's decision (confidence/step-gating), or (b) have the default loop consult `mistakes.relevant_verified` / `skills.relevant_verified` directly. Keep it cheap (these are local calls; respect the AGENTS.md note that extra model loads are opt-in flags).
- **Acceptance:** new test proving a prior verified mistake changes a subsequent turn's behavior on the default path (not just prompt inclusion); `pytest -q` green; turn latency measured before/after and reported in the handoff (must not regress meaningfully on a local run).
- **Invariant:** **authority stays synchronous** (Global §2). Recall/calibration may inform the loop, but skill-promotion and autonomy decisions remain in-band on the verifier's return value — do not route them through C1 events.

### C4 — (deferred seam) consume K2 cloud streaming in `generate`
- After K2 lands and is reviewed, wire `generate` to yield cloud tokens as they stream (using the C1 typed frames). Small; do last. Keep non-streaming fallback.

---

## 4. Phase 4 — Durable cortex tier (NOT YET; design-gate first)

The async cold-path bus for cold, re-derivable observers (self-model rebuild, facts extraction, self-analysis scans, council deliberation triggers) is **out of scope for this roadmap** and requires its own design sign-off AFTER C1 lands (it needs the schema to exist). When greenlit it is Codex-owned and MUST honor ADR §4.2-4.4: **durable (append-to-SQLite-then-dispatch), per-signature ordering, cross-process-safe (workers are subprocesses), and it never carries authority-bearing events.** Do not start it as part of this roadmap. Turning on the gated organs (self-model, facts auto-extract) happens here — one at a time, each behind its existing flag, each latency+green-gated.

---

## 5. Sequencing, coordination & review

- **Recommended order (shared tree):** Lane K first (K1→K4, independent, fast, low risk), handoff, then Lane C (C1→C2→C3, sequential). If the operator wants true parallelism, run the lanes in **separate git worktrees** — the file sets are disjoint, so merges are clean.
- **Per-task loop (both builders):** claim the `worktree` lease (`python agent_coord.py status`) → TDD the task → run the acceptance gates → update `RESUME.md` + append one `experiences.jsonl` line → `python agent_coord.py handoff` (releases lease, hash-pins tree). **Do not commit/push.**
- **Review (Claude, read-only):** against each hash-pinned handoff, I independently re-run the gates, verify the invariants (esp. Global §2 authority + §4 SSE backward-compat), and write a verdict to `.aios/state/<TASK>_REVIEW.md` (PASS/CHANGES). Verdict fails closed if the tree changed after handoff (AGENTS.md §III-A). Final approval is mine as non-builder; the operator commits.
- **Definition of done (whole roadmap):** Lanes K + C green and reviewed; `import-graph.md` + updated Tier-1/RESUME docs current; turn latency non-regressed; no frozen-spine edits; no phantom-bug "fixes"; Phase 4 left as a gated design item.

### 5a. ruflo shared brain — cross-agent memory (mandatory)

`agent_coord.py` is the **lease/hash-pin control plane** (who may write). ruflo (claude-flow MCP, `mcp__claude-flow__*`) is the **shared semantic memory** (what we've learned) — use BOTH; they are complementary, not redundant.

- **On task start:** `memory_search` the `gagos` namespace for the task area (e.g. "confidence gate", "privacy filter", "cloud streaming") and read `gagos-*` keys before building — do not cold-start (AGENTS.md §III, §XII). The roadmap itself is stored at key **`gagos-fusion-roadmap`**.
- **On task done (with the file handoff):** `memory_store` (`upsert`) a `gagos-fusion-<task-id>` entry — what changed, files, verdict-relevant evidence (test count, latency), and any lesson — so the next agent/session resumes from it. This mirrors the `experiences.jsonl` line into the searchable shared brain.
- **Coordination, not authority:** ruflo memory is advisory data (AGENTS.md §III-A.7) — it never grants approval or a write lease. The lease is still `agent_coord.py`; final approval is still Claude's read-only verdict. Do not treat a ruflo note as permission to edit.
- **Claude's review verdicts** also land in ruflo (`gagos-fusion-<task-id>-reviewed`) alongside `.aios/state/<TASK>_REVIEW.md`, so Kimi/Codex see PASS/CHANGES on their side without a live session.

---

## 6. One-paragraph brief for the builders (paste at top of the task packet)

> You are wiring an already-built organism, not adding to it. Your lane's files are exclusive — do not touch the other lane's. Keep the security spine frozen and authority synchronous (never move skill/autonomy decisions onto events). Every change is TDD'd, keeps `pytest -q` green at ≥85% coverage, and keeps the SSE stream a backward-compatible superset so the frontend being never breaks. Don't fix the §1 non-bugs. Don't commit — hand off hash-pinned via `agent_coord.py` for Claude's read-only review. Small, verified, reversible steps; report latency and evidence, not adjectives.

— Grounded in AGENTS.md (§III-A coordination, §XI gates, §VIII frozen core) + the verified ADR. Every file assignment checked disjoint.
