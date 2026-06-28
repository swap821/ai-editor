# GAGOS — Final Build Roadmap (Repo-Grounded)
### For the AI Builder Council · `swap821/ai-editor`

**Provenance.** This roadmap was written after reading the actual modules listed in §1, not the directory tree. Where a claim comes from the maintainer's own `SYSTEM_AUDIT_2026-06-21.md` rather than a fresh line-by-line read, it is marked *(audit)*. The earlier `GAGOS_SPINE` document is **superseded** by this one — two of its carve-outs ("be skeptical of the swarm", "evolution is ambient") were withdrawn after deeper reading and must not be carried forward.

**The one sentence the council should hold.** This is already a governed runtime that **acts**, **learns**, and **renders its own governance as anatomy** — unified by a single invariant: *the model proposes; verification and human approval dispose; nothing untrusted gains authority or calibrates the future.* The remaining work is **not architecture**. It is hardening the one signal everything trusts, flipping one default, sealing the substrate, and building the front door.

---

## 0. The North Star (do not lose this)

The one genuinely novel claim — nothing comparable found in the 2026 governance-agent landscape — is **governance rendered as anatomy**. Every other governance-first system keeps the policy engine as invisible backend with a dashboard bolted on. Here the policy engine *is* the organism's body: the human-approval gate is a first-class lifecycle phase (`approval_hold`), a task awaiting approval is a `held` vertebra, a verified outcome imprints on the spinal nerve roots — all via pure `derive*` functions (governed state → anatomical signal), each unit-tested.

This is the differentiator. Every phase below must protect it. The acceptance test for the whole thesis is **The One Law** (§7).

---

## 1. Ground Truth — what already exists (so the council does not rebuild it)

**Verified by reading the code:**

| Capability | Where | State |
|---|---|---|
| Fail-closed gateway, zones GREEN/YELLOW/RED | `aios/security/gateway.py` | real |
| Scope-locked, audited executor (`shell=False`, env-sanitized) + opt-in `DockerRunner` | `aios/core/executor.py` | real — **host-by-default** |
| Tamper-evident audit ledger | `aios/security/audit_logger.py` | real — holes *(audit)* |
| Supervised tool loop (H2/H3 hardened: strict tiered parsing, loop detection, force-verify-after-write) | `aios/agents/tool_agent.py` | real |
| Stigmergic swarm (castes DECOMPOSER/SCOUT/WORKER/SYNTHESIZER/QUORUM/CLOUD_BROKER; tool subsets enforced at dispatch; YELLOW pauses whole colony) | `aios/agents/swarm.py` | real |
| File-conflict subsystem (OS advisory locks, overlap detection, 3-way merge, fail-closed escalation) | `aios/agents/swarm_conflict.py` | real |
| Non-authoritative alignment frame (model proposes interpretation; cannot approve/zone/count as evidence) | `aios/core/alignment.py` | real |
| Self-analysis T0→T1→T2 (index → deterministic diagnose → propose-diff; no-self-approval; protected core excluded) | `aios/agents/self_analysis_agent.py` | real |
| **Self-apply T3a** (snapshot → `git apply --check` → audit-before-write → confined apply → integrity check → gated verify → **auto-rollback**); no apply *tool* exists (structural no-self-approval); wired to `POST /api/v1/self-analysis/proposals/{id}/apply` | `aios/core/self_apply.py` | real |
| Verification-gated learning loop — skills (promote/demote), mistakes (causal post-mortems → planner confidence), development (verified success rates per task + per model), consolidation (only verified + human-approved facts), swarm patterns (verified decomposition reuse) | `aios/memory/*`, `aios/agents/swarm_patterns.py` | real |
| Organism frontend bound to live backend events; governance projected to anatomy via pure derive functions | `frontend/src/superbrain/**` (~150 files, co-located tests) | most mature layer |

**The one deliberate, correct hold-back:** editing the RED frozen security core (`aios/security/*`) is refused outright (T4). *Keep this refusal. It is the correct place to stop.*

**Genuinely greenfield (does not exist):** `aios/runtime/`, `aios/council/`, `aios/policy/`. No `MissionContract`, `RunLedger`, `KingReport`, `CouncilOrchestrator`, no `/api/v1/council/missions`. **This is the only net-new architectural surface — and §5 argues it should be thin, not a service mesh.**

---

## 2. Why the priorities are what they are (rationale for the architect)

1. **The verifier is the keystone, and the learning loop is already live on it.** Everything downstream — what becomes a `verified` skill, a reusable pattern, a planner-confidence bump — trusts the verification signal. But verification strength is **not uniform**: a sibling-pytest verify is strong; an "exit code 0" on an arbitrary command is weak. The system is a court that believes only evidence — but the strength of "evidence" varies by case, and it **files every verdict as precedent**. A weak green doesn't just ship one questionable change; it gets cited in the next case. This compounds *today, every run*. It is the highest-leverage fix, ahead of everything else.
2. **The system both self-modifies and learns, so a host-mode execution mistake can imprint, not just run.** That makes container-by-default a safety fix, not a polish item — and a precondition for the public word "sovereign."
3. **The constitutional layer's job is mostly already done, distributed across §1.** Gated action, verified-only learning, no-self-approval, audit trail, approval-as-organism-state already exist. So the new layer is a thin formalization that *names and surfaces* what's there — not a parallel governance system. Building it as 8 microservices would be the project's characteristic failure mode (over-building the safe parts).

---

## 3. The Sequenced Build

Each phase: **Goal · Why · Tasks · Done-when (acceptance) · Suggested owner.**
Council roles — **Architect** (Kimi): schemas, taxonomies, guarding the thesis. **Implementer** (Claude Code): wiring and code. **Verifier** (Codex): adversarial tests that try to break each acceptance criterion.

### Phase 0 — Foundation Lock + Honesty Pass
- **Goal.** Freeze what works; close the branding/behavior gap.
- **Why.** The maintainer's own audit names the real risk as a *brilliant workshop presented as a product* (122 docs vs 142 code files). Ship honesty before features.
- **Tasks.**
  - Lock the RED core (`aios/security/*`) as immutable to all automated paths; assert the existing refusal in a test.
  - Write `HONEST_STATE.md`: current *actual* guarantees vs aspirations, in one table. "Sovereign" / "blockchain-grade" / "OS" claims get a plain-language footnote until the phase that earns them lands.
  - Green the existing suite in CI (see Phase 4) before any change is merged.
- **Done-when.** Council signs off on `HONEST_STATE.md`; RED-core immutability has a passing adversarial test; existing tests pass on a clean checkout.
- **Owner.** Architect drafts, Verifier checks claims against code.

### Phase 1 — Verification Integrity (the keystone)
- **Goal.** Make "verified" mean the same strength everywhere it's trusted.
- **Why.** §2.1. The learning loop is already imprinting on a non-uniform signal.
- **Tasks.**
  - Define a **verification-strength taxonomy** (e.g. `STRONG` = sibling test suite asserting behavior; `MEDIUM` = targeted assertion/typecheck; `WEAK` = exit-code-only; `NONE` = unverifiable).
  - Gate promotion on strength: **no skill, pattern, mistake-lesson, or planner-confidence promotion from below a threshold.** `WEAK`/`NONE` outcomes may be recorded but are **ineligible to calibrate the future**.
  - Stamp every `development`/`skills`/`swarm_patterns`/`mistake` record with the strength of the verification that produced it.
  - Surface strength in the organism (a strong verdict imprints brightly; a weak one is visibly faint — keep it anatomical, §7).
- **Done-when.** A test proves a `WEAK` green **cannot** create a `verified` skill/pattern or bump confidence; every promotable record carries a strength field; the UI imprint differs by strength.
- **Owner.** Architect designs the taxonomy; Implementer wires the gates; **Verifier owns this phase's test suite** — the skeptic who tries to make a hollow green imprint and must fail.

### Phase 2 — Execution Boundary (precondition for "sovereign")
- **Goal.** Container-by-default; host mode becomes a loud, explicit opt-out.
- **Why.** §2.2. `executor.py` says it plainly: host mode runs approved commands as the backend OS user — *"not an OS/container isolation boundary."* `DockerRunner` already exists; flip the default.
- **Tasks.**
  - Make `DockerRunner` the default execution backend; host mode requires an explicit flag + a logged warning.
  - Route **self-apply** (`T3a`) only through the container boundary.
  - Document the container as the supported path; host mode labeled "development only."
- **Done-when.** Default run path uses the container; a test proves an approved arbitrary command cannot touch the host outside the boundary by default; self-apply refuses to run in bare host mode.
- **Owner.** Implementer builds; Verifier writes the escape-attempt tests.

### Phase 3 — Substrate Hardening *(parallel with 2/4)*
- **Goal.** Make the ledger and redaction actually trustworthy — they are what the entire governance-and-learning story rests on.
- **Why.** *(audit)* — ledger collision / missing field delimiter / undetectable tail-truncation; secret-scanner misses PEM blocks, URL-embedded creds, bare keys, short hex.
- **Tasks.**
  - Ledger: add an unambiguous field delimiter to the hash preimage; make the chain collision-resistant; add tail-truncation detection (e.g. signed length/terminal marker).
  - Scanner: add detectors for PEM, `scheme://user:pass@`, bare-key, and short-hex secret classes; verify nothing in those classes reaches the ledger in cleartext.
- **Done-when.** Adversarial tests pass for (a) ledger tamper and silent truncation, (b) each secret class attempting to reach the ledger.
- **Owner.** Verifier specifies the attacks; Implementer fixes.

### Phase 4 — The Front Door *(parallel with 2/3)*
- **Goal.** A cold start that shows the living thing, and CI.
- **Why.** The most beautiful artifact in the repo opens on a blank first frame; there is no CI *(audit)*.
- **Tasks.**
  - First-frame **living loading state** (the organism arriving/booting — reuse `booting`/`arrival` phases), never a blank canvas.
  - A 60-second onboarding path that answers "what is this and what can I safely do."
  - CI pipeline: run the suite on push; block merge on red.
- **Done-when.** Cold start renders the organism within the first frame; CI gates merges; a new user reaches a first safe action without reading source.
- **Owner.** Implementer + a frontend pass.

### Phase 5 — Constitutional Formalization (thin — wrap, don't rewrite)
- **Goal.** Name and surface the governance that already exists; don't duplicate it.
- **Why.** §2.3. The capabilities exist; what's missing is a formal *contract → record → report* spine sliding **under** the existing `/api/generate` stream.
- **Tasks.**
  - **`MissionContract`** (the real design work — Architect): a schema declaring, per run, what it may touch (paths/zones/tools) and its **acceptance test**. This is the "law" — get it right; everything else references it.
  - **`RunLedger`**: formalize the *existing* audit ledger as the per-mission record. Do not build a second ledger.
  - **`KingReport`**: a synthesis the existing `development`/audit/verify data already supports — what was attempted, what verified (at what strength, per Phase 1), what was approved by whom.
  - **`CouncilOrchestrator`**: **plain functions** that compose the existing castes/agents under a contract. *Not services, not a message bus.*
- **Done-when.** A mission runs end-to-end — contract → gated action → ledger → report — with **zero new microservices**, and every governance state it produces renders as an organ (The One Law, §7).
- **Owner.** Architect designs the contract schema; Implementer writes the functions; Verifier asserts the invariants (contract bounds are enforced, not advisory).

### Phase 6 — Demonstrate the closed self-evolution loop
- **Goal.** One replayable, end-to-end, human-gated self-improvement.
- **Why.** The pieces exist (analyze → propose → apply → verify → rollback). The deliverable is *proving the whole closes*, visibly.
- **Tasks.**
  - Drive a full gated self-improvement on a **non-core** module: T1 finding → T2 proposal → human approval → T3a apply → STRONG verify → verified lesson imprinted → organism shows `approval_hold` then the outcome imprint.
  - Record it so a skeptic can replay it.
- **Done-when.** A recorded run a third party can reproduce, ending in a `verified` (STRONG) lesson and a clean ledger entry, with the rollback path proven by a deliberately-failing variant.
- **Owner.** All three.

---

## 4. Anti-Goals (the failure modes to refuse)

- **Do not daemonize the castes into 8 microservices.** `CouncilOrchestrator` = functions over the existing agents.
- **Do not build a second governance system.** Governance exists (§1); formalize and surface it, never duplicate it.
- **Do not let any governance function ship as a headless backend + bolted-on panel.** That breaks the thesis (§7).
- **Do not promote any outcome to `verified`/skill/pattern/confidence from a below-threshold verification** (Phase 1).
- **Do not publish the word "sovereign" until Phases 1–2 land.**
- **Do not give the cloud authority.** Cloud reasons; it never approves. The alignment frame already enforces non-authority — preserve it.
- **Do not expand self-modification scope toward the RED core.** T4 stays refused.

---

## 5. The One Law (acceptance criterion for the whole thesis)

> **Every visible element is an organ of the being, or is grown from one. Every governance function projects to anatomy through a pure `derive` function. If a faculty ships as headless backend with a bolted-on dashboard panel, the unification is fake — and the PR is rejected.**

This is falsifiable on purpose. It is how the council keeps "governance rendered as anatomy" from quietly degrading into "yet another backend with a 3D skin." Apply it to every phase that adds a governed function (1, 5, 6 especially).

---

## 6. Suggested Council Division of Labor

- **Architect (Kimi):** the `MissionContract` schema; the verification-strength taxonomy; guardian of The One Law and the non-authority property.
- **Implementer (Claude Code):** container default; ledger/scanner fixes; the front door; the orchestrator-as-functions; the anatomical wiring of new governed states.
- **Verifier (Codex):** owns the adversarial test suite for every "Done-when"; specifically owns Phase 1 — the one who must try, and fail, to make a hollow green imprint.

---

## 7. One-Paragraph Brief (if the council reads nothing else)

The repo is further along than its own roadmap assumed: it already acts under a fail-closed gate, modifies its own non-core source through a reversible audited apply with structural no-self-approval, learns only from verified outcomes, and renders the approval gate as a phase of a living body. It correctly refuses exactly one thing — editing its own security core. So the build is not "add architecture." It is, in order: **(1)** make "verified" mean one strength everywhere, because the learning loop already imprints on that signal and weak greens compound into hollow competence; **(2)** make the container the default execution boundary, because a self-modifying *and* self-learning system can't run approved commands as the host user; **(3)** seal the ledger and redaction the whole story trusts; **(4)** build a front door; **(5)** formalize the constitutional spine as a thin contract→ledger→report layer of *functions* under the existing stream — not a service mesh; **(6)** prove the self-evolution loop closes, end to end, on camera. The North Star through all of it: governance you can *see*, because it is the body — not a backend with a skin.
