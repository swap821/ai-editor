# AUDIT.md — Evidence-Based Status Ledger (refreshed 2026-07-06)

> **2026-07-06 refresh** by Claude Code. Supersedes the 2026-06-07 audit (git history
> retains it). This file is the **official evidence ledger** behind `README.md` — the
> README states the thesis; THIS file carries the perishable facts. Rule unchanged: a
> component is **BUILT** only if code exists **AND** tests exist **AND** they pass.
> **Standing rule: a live run always outranks the numbers written here.**

## 0. Ground truth (2026-07-06)

- **CI (the authoritative gate):** run `28794157393` (workflow "CI", master @ `4b2b695`,
  2026-07-06, success).
  - Backend job (windows-latest): full suite green; coverage gate output:
    `Required test coverage of 85% reached. Total coverage: 92.28%`.
    The repo's pytest config suppresses the "N passed" summary line **by design** —
    judge the suite by exit code + the coverage floor, never by grepped output.
  - Frontend job (ubuntu-latest): **72 test files / 468 tests passed**, type-check
    green, production build green.
- **Static census:** ~2,500 `def test_` functions under `tests/` (grep, 2026-07-06).
  Last local live collect: 2,532 backend tests (2026-07-05/06 sessions). The old
  README/PLAN figure "326 frontend tests" is stale — the suite has grown to 468.
- Tree at refresh: master @ `4b2b695`, working tree clean, local == origin.

## 1. What changed since the 2026-06-07 audit (150 → ~2,500 tests)

The 06-07 audit predates most of the current system. Landed since, all test-backed:
- **Verifier wired into the live loop** (the 06-07 audit's #1 recommendation — DONE; see §3).
- **Reflection loop closed in-loop**: failure hook → Mistake DB → lesson recall → confirm-hook promotion.
- **Skills → Cerebellum compiled-playbook layer**: verified-skill compile, reflex replay, demotion-invalidation.
- **Verification-strength system**: strength tokens stamped by the Verifier; promotion floors on every skill/memory write (anti-laundering: provenance-gated evidence).
- **Earned autonomy** (default-ON), **swarm + role-pass orchestration**, **CRAG-style gated retrieval on by default**.
- **Cross-provider router** (Ollama + Bedrock + Gemini + Anthropic + OpenAI-compat) behind the operator-owned privacy boundary; per-turn `route` SSE.
- **Council Runtime R0–R2 + Dashboard-lite** (KingReport API/panel, approve/reject artifacts).
- **Self-Analysis module T0–T3 surface**: proposals list/apply/reject endpoints (T4 core-edit stays RED/frozen).
- **Telemetry wired** into `/generate` + `/chat` (including aborted-turn rows); observability stack (Prometheus/Grafana/Alertmanager) in docker compose.
- **Voice** (STT/TTS routes + UI), **monolith split tranches 1–2** (`aios/api/deps.py` + 9 routers; `main.py` 4,252 → ~2,650 lines), Python 3.12 alignment, Docker hardening.
- **Single-frontend collapse**: GAGOS points-being at `/` is the only UI.

## 2. Component status (2026-07-06)

**BUILT + tested + in the live loop:** security gateway (3-zone, fail-closed, rate limit) ·
scope-lock · secret scanner · audit hash-chain (Ed25519, boot attestation) · injection
vector shield · L1/L2/L3/L4 memory + facts/contradiction quarantine · hybrid
BM25+FAISS+decay retrieval · confidence gate (every turn) · sandboxed executor +
rollback engine · file-edit diff-approval · agentic tool loop · **Verifier (in-loop)** ·
reflection agent + mistake pool · skills/trails + cerebellum replay · knowledge-graph
ingestion + inference · router + privacy filter + failover · earned autonomy ·
swarm/role-pass castes · telemetry · council runtime (R0–R2) · self-analysis T0–T3 ·
voice · session/auth · API routers (memory/development/models/system/auth/actions).

**BUILT, not in the live loop:** Planner as a *mandatory* stage (see §3).

**DESIGNED, not built:** Project Passport (P3) · Web Navigator (P4) · Taste Memory (P5).

## 3. 🔑 Integration reality (corrects the 06-07 gap table)

| Component | Built & tested | In the live `/api/generate` loop? |
|---|---|---|
| Planner (+0.72 gate) | ✅ | ⚠️ **partial — the real remaining gap.** Runs as the model-discretionary `plan` tool (`aios/agents/tool_agent.py:1384-1445`) and standalone `POST /api/v1/plan` (`routes/actions.py:141`). The scalar confidence gate DOES run every turn (`main.py:~1669-1701`); the unconditional plan *stage* does not exist yet. |
| Verifier | ✅ | ✅ **WIRED — the 06-07 "wired to nothing" row is CLOSED.** Only trusted verify-tool output counts as evidence (provenance gate, `main.py:~2104-2119`); strength floors gate every skill/memory promotion (`main.py:~1998-2007`); verified skill → cerebellum compile (`aios/memory/skills.py:188-189`). |
| Reflection loop | ✅ | ✅ wired (failure hook `main.py:~1267` → Mistake DB → `_recall_lessons` `main.py:~1164`). Missing only the end-to-end **demo artifact** — a harness gap, not a code gap. |
| Earned autonomy | ✅ | ✅ wired, **default-ON** (`config.py:182`), ≥5 consecutive verified successes per action class (`config.py:183`), streak reset on failure, revoke via `POST /api/v1/development/autonomy/revoke`, RED never earnable. |

## 4. Open gaps — the thesis→v1.0 work plan

1. **Learning-loop prover** (`tools/learning_loop_prover.py`, to be built): drives failure →
   lesson → recall → promotion → compile → reflex replay end-to-end and records the
   Phase-2 demo artifact under `.aios/audit/`.
2. **Mandatory plan stage** in `generate()` behind `AIOS_PLAN_STAGE` (ship default-OFF;
   flip after the prover is green with the stage enabled).
3. **Continuous sovereignty surface** (UI): swarm→cognition bridge, swarm toggle,
   Self-Analysis proposals panel, read-only Sovereign State tab (trails · autonomy
   ledger + revoke · pending facts · curriculum proposals — all endpoints live today).
4. **Two genuinely open hard problems** (design docs due at v1.0, systems later):
   verification confidence (are the checks the right checks — mutation-probe design)
   and staleness/drift (freshness windows, re-verify-on-use).
5. Product seams (report-only, from RESUME): swarm caste `stopped` branches unreachable
   via approval pause; `council.py` local `get_approval_store` proxy (test trap); no
   subprocess-coverage wiring.

## 5. Phase crosswalk — README Product Phases (P) ↔ roadmap-spec Runtime Phases (R)

The README tells the **product** story (P0–P6). The spec
(`docs/superpowers/specs/2026-06-27-sovereign-ai-os-roadmap.md`) tracks **runtime
architecture** phases (R0–R10, with a 30-day MVP scoped inside). Different axes — a
"Phase 2" on one is not a "Phase 2" on the other.

| Runtime phase (spec) | Status (evidence) |
|---|---|
| R0 Schema Lock + Skeleton | ✅ implemented (PLAN.md banner, 2026-06-27) |
| R1A Deterministic Worker Birth | ✅ implemented |
| R1B Hybrid Intelligence Worker Birth | ✅ implemented |
| R2 Simulated Council Loop | ✅ implemented |
| — Dashboard-lite (KingReport API/panel) | ✅ implemented |
| R3A/R3B Queen wrappers/services | ⬜ not claimed complete; council/queen surface partially live — verify before claiming |
| R4 Pheromone Memory | ⬜ seeded (skill trails + reuse pheromone live) — full phase not claimed |
| R5–R9 (worktree swarm · healing · policy evolution · mature dashboard · isolation) | ⬜ not started |
| R10 Sovereign AI-OS v1.0 | ⬜ target |

Product-side mapping, roughly: P0 ≈ R0 foundations (LOCKED) · P1 ≈ R1A/R1B + the plan-stage
close-out · P2 ≈ R2 + the R4 seed (demo artifact pending) · P3–P6 sit beyond the
implemented runtime frontier (largely R4–R10 territory).

## 6. Structural debt — status of the 06-07 findings

1. Rollback snapshots inside tracked `training_ground/` → **RESOLVED**: rollback now
   lives under the data dir (`config.py:111` `ROLLBACK_DIR = DATA_DIR / "rollback"`,
   registry DB `config.py:411`).
2. Tests sharing `DATA_DIR` with the live app → **not re-verified this refresh**;
   carried forward for a future session to confirm or close.
3. Self-edit scope (`SCOPE_ROOTS` = `training_ground/` only, `config.py:220`) → still
   true and now **deliberate**: the security spine is frozen (RED, §VIII flow), and the
   Self-Analysis module proposes diffs for human review instead of widening scope.

## 7. Honest completion estimate (2026-07-06)

- Backend core: built + test-backed at scale (CI-gated ≥85% coverage, currently 92.28%).
- Live pipeline integration: **≈85%** — the mandatory planner stage is the one
  remaining organ-level gap; everything else in the README organ table is in-loop.
- Full spec vision (R10 sovereign runtime + P3–P6 product arcs): the runtime frontier
  is at R2 of R10; the product frontier at P2 of P6. Substantial, real, not finished —
  and reported as such.

## 8. Learning-loop prover — first live runs (2026-07-07)

The Phase-2 runtime proof (`tools/learning_loop_prover.py`) was run live for the first
time (Gemini `gemini-2.5-flash` driver, fresh backend, `lab/` sandbox). **Result: 16/19
checks green, stable across 3 runs.** Per the close-out plan's fail-closed rule the
prover is NOT green, so **`AIOS_PLAN_STAGE` was left default-OFF** (unchanged). The core
learning loop is proven end-to-end (fail→fix→confirm→recall; 3× STRONG→promote→compile;
mutation-probe soundness). The 3 remaining checks are now fully root-caused:

- **`lesson.reflect-step` + `lesson.confirm-step`** — the emission plumbing is CORRECT and
  was proven live (the probe-phase verify failure DID surface a structured lesson,
  `mistake_id=84`). These fail only when the reflection LLM returns no parseable lesson
  for the lesson-phase failure — i.e. **best-effort reflection variance**, by design: the
  failure hook defensively swallows `ReflectionError` so a bad reflection never breaks
  chat. Confirm depends on a pending reflect, so the two flake together. Not a code
  defect; making them deterministic needs reflection-reliability work (retry / stronger
  reflect model), a scoped follow-up.
- **`reflex.cerebellum-done`** — a REAL compilation bug: `_workflow_step` (main.py)
  serializes tool calls as `verify: command=<cmd>`, and cerebellum's `_parse_step` kept
  the `command=` prefix, so every compiled playbook command was malformed and classified
  Zone.RED ("not on the auto-execute allowlist") on replay. Fixing the prefix makes the
  replay complete — **but that then exposed a deeper soundness bug**: the compiled
  playbook's `goal_pattern` is a generic prefix ("verify exactly this command:") that
  lexically matches DIFFERENT-command requests, so a passing reflex playbook would replay
  its stale command for the broken probe and FABRICATE a green verdict (the mutation probe
  correctly caught this). A naive "only match when the command is named in the request"
  guard breaks the existing paraphrase-tolerant matching (3 unit tests). This is a genuine
  cerebellum **matching-soundness redesign**, not a one-line fix — reverted to the
  known-sound HEAD state pending a dedicated arc.

Infra fixes that took the prover 3→16 (all sound, tests green): cloud-egress privacy
filter over-redaction (path-shaped tokens no longer scrubbed); `lab/` sandbox scope root
(so prover fixtures pass the security scanner — **note: this widens `SCOPE_ROOTS` beyond
`training_ground/`; §6.3 above is now superseded — `lab/` is a gitignored scratch space,
operator-approved**); container `PYTEST_ADDOPTS` coverage-summary clearing; verify-tool is
now a first-class learning-loop citizen (surfaces reflect/confirm on the verify path);
suite-order test-isolation flake fixed.

_Recorded 2026-07-07 by Claude Code (Fable). Prover artifact:
`.aios/audit/learning-loop-runs.jsonl`. STOP-for-review per fail-closed plan; flag NOT
flipped; cerebellum reverted to sound state._

---
_Refreshed 2026-07-06 by Claude Code. Next actions, in order: learning-loop prover
(P2 demo artifact) → mandatory plan stage (`AIOS_PLAN_STAGE`) → sovereignty surface →
the two hard-problem design docs. Trust `RESUME.md` for session-level state._
