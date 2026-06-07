# AUDIT.md — Evidence-Based Backend Status (refreshed 2026-06-07)

> **2026-06-07 refresh** by Claude Code (acting CEO/Chief Architect). Supersedes the
> 2026-06-03 Phase-1 audit (git history retains it). Rule unchanged: a component is
> **BUILT** only if code exists **AND** tests exist **AND** they pass. Cross-referenced
> against `blueprint_text.md` (v6) and the v6 Assessment companion
> (`aiosv6_assessment_text.md`).

## 0. Ground truth
- Full suite: **150 passed, 1 skipped** (`.venv\Scripts\python -m pytest -q`). The skip is the
  Windows symlink-privilege case (environmental, not a failure).
- Backend: 28 modules in `aios/{core,memory,security,agents,api}`. **Zero** TODO/FIXME/stub
  markers found. Clean dependency-injection + centralized `config.py`.

## 1. What changed since the 2026-06-03 audit (111 → 150 tests)
The Phase-2 slices in `PLAN.md` are DONE, closing most prior gaps:
- ✅ Security scope hardening (Slice 1a) + API contract tests (1b)
- ✅ **File-edit tool + unified diff + approval** (Slice 2/4); path-resolution bug fixed + **live
  e2e verified on Bedrock 2026-06-07** (diff → Apply → write + pre-edit snapshot `dce2427`)
- ✅ Frontend test harness — Vitest/RTL (Slice 3)
- ✅ **Verifier component** `aios/core/verifier.py` (Slice 5)
- ✅ Prompt-injection **vector blocklist** `aios/security/injection_shield.py` (Slice 6)
- ✅ **L3 entity facts + contradiction detection** `aios/memory/facts.py` (Slice 7)
- ✅ AWS Bedrock cloud provider + real model picker

The 06-03 "PARTIAL/MISSING" rows for Verifier, L3 facts/contradiction, injection-vector,
file-edit-diff, and frontend-tests are now **BUILT**.

## 2. Component status (2026-06-07)
**BUILT + tested:** Security gateway (3-zone, fail-closed, rate limit) · scope-lock · secret
scanner · audit hash-chain · L1/L2/L3/L4 memory · FAISS + hybrid BM25+FAISS+decay retrieval ·
L3 facts + contradiction detection · Planner · Confidence filter · Executor (sandboxed) ·
Reflection agent · Mistake pool · Rollback engine · Verifier · injection vector shield ·
edit_file diff-approval · agentic tool-loop · Bedrock cloud · 8 v1 API contracts · frontend harness.

## 3. 🔑 KEY FINDING — the integration gap
The live path `/api/generate → ToolAgent` does: **recall → security-gated tools (read/edit/exec)
→ reflect-on-failure → audit.** Solid. But three finished components are **islands**:

| Component | Built & tested | In the live loop? |
|---|---|---|
| Planner (+0.72 gate) | ✅ | ❌ only standalone `/api/v1/plan` |
| Verifier (stage 8) | ✅ | ❌ **wired to nothing** — no endpoint, not in the loop |
| Confidence filter | ✅ | ❌ only via Planner → `/plan` |

⇒ The blueprint's pipeline (plan → retrieve → classify → approve → execute → **verify** → reflect →
audit) exists as *parts, not one flow*. **Highest-ROI next work is integration, not new features.**

## 4. Structural debt (found 2026-06-07)
1. **RollbackEngine inits a `.git` INSIDE the main-repo-tracked `training_ground/`** → embedded-repo
   wrinkle; snapshots never reach origin. (Verified live today: `training_ground/.git` now exists.)
2. **Tests share `DATA_DIR` with the live app** → a `hybrid_search` stub is needed to avoid a torch
   segfault. Couples tests to on-disk state.
3. **Self-edit scope:** scope roots = `training_ground` only, so the agent currently **cannot edit
   its own `aios/` code at all**. The planned Self-Analysis module (T2/T3) needs scope to include
   `aios/` with `aios/security/` excluded — a security-sensitive expansion to design carefully.

## 5. Genuinely missing — build targets
**Marquee (from the v6 Assessment doc) — the capability the operator most wants:**
- **Self-Analysis & Self-Improvement Module** `aios/agents/self_analysis_agent.py` — tiers T0
  index/explain → T1 diagnose → T2 propose-diff (YELLOW) → T3 apply (snapshot→verify→audit→auto-
  rollback) → T4 core edit (RED, frozen). Scoped to **code, not cognition**. Reuses gateway +
  rollback + audit unchanged. Prereqs (mostly met now): real tests ✅, wired Verifier (TODO),
  solid rollback (fix the nesting), static tooling (coverage+radon), golden tests, documented
  frozen core, stronger analysis model ✅ (16GB unlock).

**Blueprint P3/P4 (deferred):** Project Knowledge Graph (Neo4j — L3 facts are a seed) · Voice
(Whisper+Piper) · Observability + Deployment (Docker, Prometheus/Grafana/OTel) · chaos/perf/
adversarial test tiers.

## 6. Assessment-doc framing corrections (adopt)
- Target **90%+ working MVP**, not "100% built" (pursue completeness; *report* it as 90%+).
- Self-analysis = reads/improves its own **code** under approval — not "understands its cognition."
- Security framing: "**deterministic routing** + a probabilistic 2nd layer, both feeding a **human
  gate**." The human gate is the guarantee; don't oversell the classifier.

## 7. RAM upgrade (2026-06-07): 8 → 16 GB
Unlocks local mid-size models (`qwen2.5-coder:7b`, `llama3.1:8b`) — the Assessment doc's hard
requirement for trustworthy reflection/self-analysis (3B is too weak). Bedrock is now optional, not
mandatory. Self-analysis readiness (was 5/10: "needs tests + a stronger model") — both now satisfied.

## 8. Recommended build order
**Tier 1 — integrate what exists (highest ROI):**
1. Wire the **Verifier** into the live loop (execute→verify→reflect). ← prereq for self-improvement.
   *(ultracode prompt drafted 2026-06-07.)*
2. Wire the **Planner + confidence gate** for multi-step goals.

**Tier 2 — fix the cracks:**
3. Relocate the rollback snapshot repo out of tracked `training_ground/` (into gitignored `data/`).
4. Isolate tests from live `DATA_DIR` (retire the stub workaround).

**Tier 3 — self-analysis runway:**
5. Static tooling (`coverage.py` + `radon`) + a golden-regression harness; document the frozen core
   in CLAUDE.md; pull a stronger local model (`qwen2.5-coder:7b`).

**Tier 4 — the marquee feature:**
6. Self-Analysis Module — T0/T1 (read-only diagnose) first → T2/T3 → T4 last (frozen-core, RED).

**Tier 5 — blueprint expansion:** Knowledge Graph → Voice → Observability/Docker → chaos/perf.

## 9. Honest completion estimate (2026-06-07)
- Backend P0–P1 core: **≈90%** built + test-backed (up from ~80% on 06-03).
- Live agentic pipeline *integration*: **≈75%** (Planner/Verifier not yet in the loop).
- Full v6 vision (incl. self-analysis + voice + KG + observability): **≈55–60%**.

Not 100% — and reported as such. A strong, test-backed core; the next leverage is integrating it
into one pipeline, then building the self-analysis capability on that foundation.

---
_Refreshed 2026-06-07 by Claude Code. Next action: Tier-1 #1 (wire the Verifier) via ultracode._
