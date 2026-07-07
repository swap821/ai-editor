# GAGOS

**G**overned · **A**gentic · **G**uided · **O**perating · **S**ystem

> Not an OS replacement — an intelligence layer for the OS that keeps **the human** sovereign over the AI, instead of the other way around.

GAGOS is a local-first, cloud-capable, human-supervised intelligence layer that sits *above* Windows, Linux, or macOS. It connects local project knowledge, LLMs (local and cloud), memory, tools, approvals, verification, and — on the roadmap — open-internet navigation into one governed system. It is not a kernel, a driver layer, or a chatbot wrapper. It is a control plane in which language models act as **untrusted workers inside a trusted system**.

`Phase 2 complete in code, runtime prover 16/19 · core loop proven live · Phase 1 integration 85% · Python/FastAPI backend · React/TypeScript 3D superbrain frontend · fail-closed by default · 2,500+ backend tests · 468 frontend tests · ~92% branch coverage (as of 2026-07-06 — live evidence in .aios/state/AUDIT.md)`

---

## The one belief

**The model is never trusted. The system is trusted. The human is sovereign.**

Be precise about which sovereignty is being claimed, because it's the whole thesis:

- **Sovereignty of authority** — the human sets permissions, approves risk, owns memory, and holds final say — is real and is what GAGOS delivers.
- **Sovereignty of infrastructure** — the system standing alone — is *not* claimed, and pretending otherwise would be dishonest. The moment GAGOS routes to a cloud model, it sends operator data to a third party under that party's terms and can be rate-limited or cut off.

The honest framing: **GAGOS is the landlord of the governance and a tenant of the compute.** It writes the house rules — what runs, what needs approval, what gets remembered — while renting intelligence from models it doesn't own. Sovereignty lives with the operator, not the machine.

---

## What's actually built and verified today

Not aspiration — this is in the repo and under test:

- **Fail-closed security gateway.** Actions are classified before execution (`GREEN` = safe/read-only · `YELLOW` = needs explicit approval · `RED` = blocked). When uncertain, it denies. Prompt-injection shield via vector blocklist.
- **Tamper-evident audit ledger.** An Ed25519-signed hash-chain records important actions, with boot attestation — designed so that altering history breaks the chain.
- **Sandboxed executor with rollback.** Commands and edits run in a constrained executor backed by a rollback engine, so actions are recoverable. File-edit tool with unified diff approval tested live on AWS Bedrock (2026-07-05).
- **Deterministic, operator-owned model router.** Routes across local **Ollama** and **Anthropic / Bedrock / Gemini / OpenAI-compatible** providers behind a failover wrapper. Selection is a transparent heuristic, not an LLM guessing about itself. Cloud routes detected and visualized in the UI (real-time lightning bolts on the superbrain spine).
- **Quarantined memory pipeline.** Facts are *proposed*, then human-*approved*, then *active*, with contradiction detection (L3 entity facts). Auto-extraction reads **only the operator's own statements** — never file contents or model output. FAISS + BM25 hybrid retrieval with decay-weighted freshness.
- **Council Runtime (v0.1).** A deterministic planner producing evidence-derived confidence (not LLM-reported), plus a **King** approval surface the operator signs off on. Full deliberation → proposer → king veto wired into the live loop.
- **Cerebellum.** A playbook layer that caches verified routines for reuse. Stigmergic skill trails (success/failure counts, strength, status) embedded in the live tool-agent loop.
- **Reflection engine.** Structured failure post-mortems → Mistake DB. Lessons learned persist and inform future attempts.
- **Multi-agent orchestration.** Role-pass swarm patterns, worker agents spawned for one job, required to return evidence, then dissolved.
- **Living 3D superbrain frontend.** Real-time visualization of cognition events (knowledge-acquired, verification verdicts, agent dispatch, cloud routing). Honest: goes dormant when there is no data.
- **Verification discipline in the tooling itself.** The suite is green in CI on every commit; live counts and run evidence live in the audit ledger (`.aios/state/AUDIT.md`). The project deliberately reports the *lower, truer* branch-coverage number (~92%) rather than the flattering line number.

---

## What GAGOS is *not*

- a Windows/Linux/macOS replacement, kernel, or driver layer
- a chatbot wrapper or a blind code executor
- an unrestricted autonomous agent, or a system where the AI has final authority
- a production-ready commercial platform

It is a **working governance layer** — experimental, but shipping real workflows. The goal is not to fake autonomy. It is to build autonomy that is supervised, permissioned, auditable, recoverable, and explainable.

---

## Core philosophy

1. **Human sovereignty.** The operator is the final authority. The system can suggest, prepare, search, reason, and take *safe* actions — but important decisions stay with the human.
2. **AI is a worker, not a master.** LLMs are replaceable reasoning engines. Useful, never trusted by default; their output passes through policy, verification, memory rules, and approval.
3. **Trust the system, not the model.** The model may hallucinate; the system protects the user through permissions, security classification, approval, audit logs, source tracking, memory quarantine, and fail-closed defaults.
4. **Memory must be earned.** Raw model output, web content, and project scans do not become trusted memory automatically. They climb a ladder (below).
5. **Experience comes from proof.** Real capability comes from tasks that were attempted, approved, executed, and *verified* — not from a prompt.

---

## Sovereign Colony architecture

GAGOS is organized as a colony under a human sovereign.

**The Operator** — you — holds goals, taste, approval, and control. Final authority, always.

**The Queen Council** — the permanent *organs* of the system. Most are **deterministic and operator-owned** rather than free-running LLM agents; they are instruments and policy, not chatbots:

| Organ | Status | Role | Live in loop? |
|---|---|---|---|
| Memory | ✅ built | proposal → approval → active, with contradiction detection | ✅ yes |
| Security | ✅ built | classifies and gates every action, fail-closed | ✅ yes |
| Planner | ✅ built | deterministic plans with evidence-derived confidence | ⚠️ optional tool + standalone endpoint; the mandatory per-task plan stage is built behind `AIOS_PLAN_STAGE` (default-OFF until the runtime prover is green — fail-closed) |
| Router | ✅ built | picks local/cloud model transparently, with failover | ✅ yes |
| Verifier | ✅ built | runs checks; success means *verified*, not *returned* | ✅ wired in-loop (provenance-gated evidence; strength gates every promotion) |
| Reflection | ✅ built | turns failures into recorded lessons | ✅ yes |
| Cerebellum | ✅ built | stigmergic skill trails, playbook replay | ✅ yes |
| Project Knowledge | ❌ designed | scans repos into a Project Passport *(roadmap)* | — |
| Web Navigation | ❌ designed | controlled, cited internet research *(roadmap)* | — |
| Taste Alignment | ❌ designed | learns how the operator likes things done *(roadmap)* | — |

**The King** — a caution-only ratchet. A human-facing approval surface that can hold or escalate a risky step for the operator to sign off on, but **never silently proceeds**. This is the veto, and it is the most sovereignty-relevant organ in the system.

**Earned autonomy** — the ratchet's honest counterpart, and it must be disclosed plainly: the mechanism ships **enabled by default**, but it grants nothing until earned. A narrow action class may skip its approval pause only after **at least 5 consecutive verifier-backed successes** for that exact class; a single failure resets the streak to zero; the operator can revoke any earned class in one click; every autonomous act still passes the security gateway and lands in the audit ledger; and RED actions can never be earned. Autonomy here is proof-of-work, not a setting.

**Worker agents** — ephemeral. Spawned for one job (inspect a file, write a component, run a test, research a topic), required to **return evidence**, then dissolved. They serve the colony; they don't own it. Only *verified* outcomes are eligible to become memory.

```
┌──────────────────────────────────────────────────────┐
│                    HUMAN OPERATOR                      │
│            Goals · Taste · Approval · Control          │
└───────────────────────────┬──────────────────────────┘
                            │  approves / vetoes (via King)
┌───────────────────────────▼──────────────────────────┐
│                 SOVEREIGN AI-OS LAYER                  │
│      Policy · Memory · Routing · Tools · Proof         │
└───────────────┬───────────────────────┬──────────────┘
                │                       │
   ┌────────────▼───────────┐  ┌────────▼──────────────┐
   │      QUEEN COUNCIL       │  │   TEMPORARY WORKERS    │
   │ (deterministic organs)   │  │ (ephemeral agents)     │
   │ Memory · Security · Plan │  │ Research · Code · Test │
   │ Router · Verify · Reflect│  │ Inspect · Debug        │
   └────────────┬───────────┘  └────────┬──────────────┘
                │       evidence flows up │
   ┌────────────▼────────────────────────▼─────────────┐
   │           LOCAL MACHINE + PROJECT UNIVERSE          │
   │      Files · Terminal · Repos · Notes · Commands    │
   └───────────────────────────┬────────────────────────┘
                              │  (roadmap)
   ┌───────────────────────────▼────────────────────────┐
   │              OPEN INTERNET UNIVERSE                  │
   │        Docs · Research · Sources · APIs             │
   └────────────────────────────────────────────────────┘
```

---

## How knowledge earns trust

Nothing is trusted because an AI said it. Every input climbs the same ladder:

```
Observation → Proposal → Human approval → Verified use → Reusable experience
```

Internet findings are **observations**. Project scans are **proposals**. Model outputs are **suggestions**. Only what is approved, then verified, then repeatedly proven becomes reusable skill.

## How experience is earned

```
Task attempted → Action proposed → Approval (if risky) → Executed
              → Verification → Result recorded → Lesson learned → Workflow improved
```

Capability is not asserted. It is *done, verified, and remembered safely.*

---

## Current Phase: What's shipping vs. what's next

These are the **Product Phases (P0–P6)** — how the product story advances. The runtime roadmap spec tracks its own **Runtime Phases (R0–R10)** on a different axis; the crosswalk between the two lives in [`.aios/state/AUDIT.md`](./.aios/state/AUDIT.md).

### **P0 — Foundation (LOCKED)** ✅

Core control plane, security spine, executor, memory, audit ledger, all functional and under continuous test.

### **P1 — Integration (85% complete)** ⚠️

**Wired and live:**
- Tool agent loop (read, edit, execute) with approval gates.
- Reflection post-mortems from failed tasks.
- Skill trails (stigmergy) learning from verified outcomes.
- Multi-agent orchestration (role-pass, swarm patterns).
- **Verifier integration:** verification runs *inside* the live loop — only trusted verify-tool output counts as evidence (provenance-gated, so a model cannot forge a passing verdict), and verification strength gates every skill and memory promotion, feeding verified outcomes directly into the Cerebellum.

**Built, wired behind a fail-closed flag:**
- **Planner integration:** The deterministic planner exists, passes tests, and produces evidence-derived confidence. The mandatory in-loop plan stage is built and wired into `/api/generate` behind `AIOS_PLAN_STAGE`, held **default-OFF until the runtime prover is green** (fail-closed). It also runs as an optional agent tool and the standalone `/api/v1/plan` endpoint.

### **P2 — Verification & Reflection (complete in code · runtime prover 16/19)** ✅

The full feedback loop exists in code and the learning-loop prover (`tools/learning_loop_prover.py`) now runs it live: task failure → reflection → recall → re-attempt → success → trail promoted → reflex replay → cerebellum compile/replay, plus a deliberately-broken mutation probe. **16/19 checks green with the core loop proven end-to-end**; the 3 remaining are best-effort reflection-LLM variance and a cerebellum matching-soundness redesign (honest breakdown in AUDIT §8). Artifact: `.aios/audit/learning-loop-runs.jsonl`.

### **P3 — Project Knowledge (Roadmap)** ❌

**Project Passport Harvester** — scans a project into purpose, stack, folder map, install/run/build/test commands, env vars, safe vs risky actions, known issues, goals, suggested improvements. This is the crux: everything downstream (taste learning, web navigation, earned autonomy) depends on accurate project understanding.

### **P4 — Sovereign Web Navigator (Roadmap)** ❌

Controlled internet research with cited sources, cross-verification, quarantine, freshness tracking, and re-verification on use.

### **P5 — Human Taste Memory (Roadmap)** ❌

Operator-editable preference memory: tone, explanation depth, naming conventions, design patterns, career goals, feedback patterns.

### **P6 — Public Product (Roadmap)** ❌

Student / Developer / Professional / Creator modes, onboarding, demo videos, case studies.

---

## The ceiling — what GAGOS deliberately can't do

A serious system names its limits:

- It **cannot inspect the models' weights.** It governs their *use*, not their internals.
- It **cannot guarantee correctness** — only *verify against checks it can actually run*. Unverifiable claims stay suggestions.
- Its future web navigation **inherits staleness and poisoning risk.** These are *mitigated* (freshness, quarantine, cross-verification), not *solved*.
- Its taste memory is only ever as good as **the facts the operator approved.**
- It is **not infrastructure-sovereign** while it depends on cloud APIs. Local-first narrows this; it doesn't erase it.

---

## Security principles

Deny dangerous actions by default · require approval for risky operations · keep audit logs · separate observation from memory · separate AI suggestion from trusted fact · never auto-trust model output or web content · keep memory editable and reversible · prefer local execution · **fail closed when uncertain.**

Two distinctions reviewers often miss. First, fail-closed governs **actions**: an uncertain classification denies execution. A contradiction in **knowledge** is handled differently — the fact refuses activation and the system asks the sovereign; that pause is the design working, not a failure mode. Second, local-first governs **egress**: a cloud route requires per-task-class operator opt-in (`AIOS_ROUTER_CLOUD_TASKS`, empty by default = local-only), and anything that does leave passes the privacy filter with paths and secrets redacted.

---

## Proof, not claims

A GAGOS workflow, end to end, looks like:

1. Operator issues a directive (goal or task).
2. GAGOS classifies the scope (which actions are GREEN/YELLOW/RED).
3. For YELLOW actions, operator approves. RED actions are refused.
4. Tool agent executes approved actions with memory context.
5. Verification checks run; results recorded.
6. Failures trigger structured reflection; lessons enter the Mistake DB.
7. Successes reinforce skill trails; strength increases.
8. The next time a similar task appears, GAGOS can (a) reflex-recall from memory, (b) replay a learned playbook, or (c) route to the planner for a new plan.
9. Operator can inspect memory, edit facts, reject skills, and audit the entire hash-chained history.

That loop — context, permission, verification, memory, introspection — is the line between a chatbot and a governed AI-OS layer.

---

## Positioning

**One line:** A working AI layer that learns your projects, your style, and your workflow — supervised by you, accountable to you, always.

**Technical:** A local-first, cloud-capable, human-supervised agentic control plane where LLMs act as untrusted workers inside a trusted system of memory, permissions, routing, verification, and auditability.

**Honest:** Phase 2 complete in code, Phase 1 integration underway. Not production-ready. But the core governance layer is real and its full suite is green in CI on every commit (live evidence: `.aios/state/AUDIT.md`).

---

## Getting started

See [`START_HERE.md`](./START_HERE.md) for setup, environment configuration, and backend/frontend launch.

For the architecture deep-dive, see:
- **`.aios/state/PLAN.md`** — Blueprint vs. Reality, system context, what's next.
- **`.aios/state/AUDIT.md`** — Component status, test evidence, integration gaps.
- **`.aios/coordination/README.md`** — How the builder agents coordinate (Claude / Codex / Kimi).
- **`docs/superpowers/specs/2026-06-27-sovereign-ai-os-roadmap.md`** — The runtime roadmap: Runtime Phases R0→R10 to Sovereign AI-OS v1.0, with a 30-day MVP scoped inside it.

For the frontend:
- **`frontend/README.md`** — The 3D superbrain UI, real-time cognition visualization, how it reads from the backend.

---

## Disclaimer

Experimental, working prototype. Not a production security system, enterprise automation platform, or autonomous OS. Review actions before execution. Do not grant unrestricted access to sensitive files, credentials, or destructive commands.

**Human-owned. System-trusted. AI-assisted. Accountable.**
