# GAGOS

**G**overned · **A**gentic · **G**uided · **O**perating · **S**ystem

> Not an OS replacement — an intelligence layer for the OS that keeps **the human** sovereign over the AI, instead of the other way around.

GAGOS is a local-first, cloud-capable, human-supervised intelligence layer that sits *above* Windows, Linux, or macOS. It connects local project knowledge, LLMs (local and cloud), memory, tools, approvals, verification, and — on the roadmap — open-internet navigation into one governed system. It is not a kernel, a driver layer, or a chatbot wrapper. It is a control plane in which language models act as **untrusted workers inside a trusted system**.

`phase 2 complete · Phase 1 integration 70% · Python/FastAPI backend · React/TypeScript 3D superbrain frontend · fail-closed by default · 654 backend tests + 326 frontend tests passing · ~92% branch coverage`

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
- **Sandboxed executor with rollback.** Commands and edits run in a constrained executor backed by a rollback engine, so actions are recoverable. File-edit tool with unified diff approval tested live on AWS Bedrock (2026-07-07).
- **Deterministic, operator-owned model router.** Routes across local **Ollama** and **Anthropic / Bedrock / Gemini / OpenAI-compatible** providers behind a failover wrapper. Selection is a transparent heuristic, not an LLM guessing about itself. Cloud routes detected and visualized in the UI (real-time lightning bolts on the superbrain spine).
- **Quarantined memory pipeline.** Facts are *proposed*, then human-*approved*, then *active*, with contradiction detection (L3 entity facts). Auto-extraction reads **only the operator's own statements** — never file contents or model output. FAISS + BM25 hybrid retrieval with decay-weighted freshness.
- **Council Runtime (v0.1).** A deterministic planner producing evidence-derived confidence (not LLM-reported), plus a **King** approval surface the operator signs off on. Full deliberation → proposer → king veto wired into the live loop.
- **Cerebellum.** A playbook layer that caches verified routines for reuse. Stigmergic skill trails (success/failure counts, strength, status) embedded in the live tool-agent loop.
- **Reflection engine.** Structured failure post-mortems → Mistake DB. Lessons learned persist and inform future attempts.
- **Multi-agent orchestration.** Role-pass swarm patterns, worker agents spawned for one job, required to return evidence, then dissolved.
- **Living 3D superbrain frontend.** Real-time visualization of cognition events (knowledge-acquired, verification verdicts, agent dispatch, cloud routing). Honest: goes dormant when there is no data.
- **Verification discipline in the tooling itself.** The suite is green: 654 backend tests + 326 frontend tests. The project deliberately reports the *lower, truer* branch-coverage number (~92%) rather than the flattering line number.

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
| Planner | ✅ built | deterministic plans with evidence-derived confidence | ⚠️ wired, not fully integrated |
| Router | ✅ built | picks local/cloud model transparently, with failover | ✅ yes |
| Verifier | ✅ built | runs checks; success means *verified*, not *returned* | ⚠️ ready, not wired |
| Reflection | ✅ built | turns failures into recorded lessons | ✅ yes |
| Cerebellum | ✅ built | stigmergic skill trails, playbook replay | ✅ yes |
| Project Knowledge | ❌ designed | scans repos into a Project Passport *(roadmap)* | — |
| Web Navigation | ❌ designed | controlled, cited internet research *(roadmap)* | — |
| Taste Alignment | ❌ designed | learns how the operator likes things done *(roadmap)* | — |

**The King** — a caution-only ratchet. A human-facing approval surface that can hold or escalate a risky step for the operator to sign off on, but **never silently proceeds**. This is the veto, and it is the most sovereignty-relevant organ in the system.

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

### **Phase 0 — Foundation (LOCKED)** ✅

Core control plane, security spine, executor, memory, audit ledger, all functional and under continuous test.

### **Phase 1 — Integration (70% complete)** ⚠️

**Wired and live:**
- Tool agent loop (read, edit, execute) with approval gates.
- Reflection post-mortems from failed tasks.
- Skill trails (stigmergy) learning from verified outcomes.
- Multi-agent orchestration (role-pass, swarm patterns).

**Built but not yet wired:**
- **Planner integration:** The deterministic planner component exists and passes tests. It produces evidence-derived confidence scores. Next step: wire it into the main `/api/v1/generate` orchestration so every task runs with a structured plan stage before execution.
- **Verifier integration:** The verification engine is complete (stage 8) and has its own endpoint (`/api/v1/verify`). Next step: integrate verdict verdicts into the tool-agent loop so verified outcomes feed directly into the Cerebellum.

### **Phase 2 — Verification & Reflection (90% complete)** ✅

The full feedback loop exists in code. Missing: an end-to-end demo showing task failure → reflection → system recall → re-attempt → success → trail promoted → reflex replay. (This is a demo burden, not a code burden.)

### **Phase 3 — Project Knowledge (Roadmap)** ❌

**Project Passport Harvester** — scans a project into purpose, stack, folder map, install/run/build/test commands, env vars, safe vs risky actions, known issues, goals, suggested improvements. This is the crux: everything downstream (taste learning, web navigation, earned autonomy) depends on accurate project understanding.

### **Phase 4 — Sovereign Web Navigator (Roadmap)** ❌

Controlled internet research with cited sources, cross-verification, quarantine, freshness tracking, and re-verification on use.

### **Phase 5 — Human Taste Memory (Roadmap)** ❌

Operator-editable preference memory: tone, explanation depth, naming conventions, design patterns, career goals, feedback patterns.

### **Phase 6 — Public Product (Roadmap)** ❌

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

**Honest:** Phase 2 complete, Phase 1 integration underway. Not production-ready. But the core governance layer is real and passes 650+ tests.

---

## Getting started

See [`START_HERE.md`](./START_HERE.md) for setup, environment configuration, and backend/frontend launch.

For the architecture deep-dive, see:
- **`.aios/state/PLAN.md`** — Blueprint vs. Reality, system context, what's next.
- **`.aios/state/AUDIT.md`** — Component status, test evidence, integration gaps.
- **`.aios/coordination/README.md`** — How the builder agents coordinate (Claude / Codex / Kimi).
- **`docs/superpowers/specs/2026-06-27-sovereign-ai-os-roadmap.md`** — Current 24-week Phase 1→v1.0 execution plan.

For the frontend:
- **`frontend/README.md`** — The 3D superbrain UI, real-time cognition visualization, how it reads from the backend.

---

## Disclaimer

Experimental, working prototype. Not a production security system, enterprise automation platform, or autonomous OS. Review actions before execution. Do not grant unrestricted access to sensitive files, credentials, or destructive commands.

**Human-owned. System-trusted. AI-assisted. Accountable.**
