# GAGOS

**G**overned · **A**gentic · **G**uided · **O**perating · **S**ystem

> Not an OS replacement — an intelligence layer for the OS that keeps **the human** sovereign over the AI, instead of the other way around.

GAGOS is a local-first, cloud-capable, human-supervised intelligence layer that sits *above* Windows, Linux, or macOS. It connects local project knowledge, LLMs (local and cloud), memory, tools, approvals, verification, and — on the roadmap — open-internet navigation into one governed system. It is not a kernel, a driver layer, or a chatbot wrapper. It is a control plane in which language models act as **untrusted workers inside a trusted system**.

`alpha` · Python/FastAPI backend · React/TypeScript frontend · fail-closed by default · green test suite at ~92% *branch* coverage

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

- **Fail-closed security gateway.** Actions are classified before execution (`GREEN` = safe/read-only · `YELLOW` = needs explicit approval · `RED` = blocked). When uncertain, it denies.
- **Tamper-evident audit ledger.** An Ed25519-signed hash-chain records important actions, with boot attestation — designed so that altering history breaks the chain.
- **Sandboxed executor with rollback.** Commands and edits run in a constrained executor backed by a rollback engine, so actions are recoverable.
- **Deterministic, operator-owned model router.** Routes across local **Ollama** and **Anthropic / Bedrock / Gemini / OpenAI-compatible** providers behind a failover wrapper. Selection is a transparent heuristic, not an LLM guessing about itself.
- **Quarantined memory pipeline.** Facts are *proposed*, then human-*approved*, then *active*, with contradiction detection. Auto-extraction reads **only the operator's own statements** — never file contents or model output, both of which are memory-poisoning surfaces. FAISS-backed retrieval underneath.
- **Council Runtime (v0.1).** A deterministic planner producing evidence-derived confidence (not LLM-reported), plus a **King** approval surface the operator signs off on.
- **Cerebellum.** A playbook layer that caches verified routines for reuse.
- **Verification discipline in the tooling itself.** The suite is green, and the project deliberately reports the *lower, truer* branch-coverage number (~92%) rather than the flattering line number. `prove_sovereignty.py` gates core invariants.

---

## What GAGOS is *not*

- a Windows/Linux/macOS replacement, kernel, or driver layer
- a chatbot wrapper or a blind code executor
- an unrestricted autonomous agent, or a system where the AI has final authority
- a production-ready commercial platform

It is an **alpha-stage prototype** exploring what a human-owned AI operating layer can become — experimental, but intentionally serious. The goal is not to fake autonomy. It is to build autonomy that is supervised, permissioned, auditable, recoverable, and explainable.

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

| Organ | Status | Role |
|---|---|---|
| Memory | built | proposal → approval → active, with contradiction detection |
| Security | built | classifies and gates every action, fail-closed |
| Planner | built | deterministic plans with evidence-derived confidence |
| Router | built | picks local/cloud model transparently, with failover |
| Verifier | built | runs checks; success means *verified*, not *returned* |
| Reflection | built | turns failures into recorded lessons |
| Project Knowledge | designed | scans repos into a Project Passport *(roadmap)* |
| Web Navigation | designed | controlled, cited internet research *(roadmap)* |
| Taste Alignment | designed | learns how the operator likes things done *(roadmap)* |

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

## Feature map: built vs designed

**Built** — security gateway · audit ledger · sandboxed executor + rollback · multi-provider router · quarantined memory + FAISS retrieval · Council Runtime v0.1 · cerebellum playbooks.

**Designed (roadmap):**

- **Project Knowledge Harvester** — scans an existing project into a **Project Passport** (purpose, stack, folder map, install/run/build/test commands, env vars, safe vs risky actions, known issues, goals, suggested improvements). This is GAGOS's *local perception* — closer to literacy than to a live camera: it studies a project deliberately rather than watching it in real time. Scans enter memory as proposals, never as trusted facts.
- **Sovereign Web Navigator** — the system's *external navigation*, not its eyes. Search → source-backed claim → cross-verified claim (corrective-RAG style) → human-approved memory. Critically, the open web is **non-stationary and adversarial**: a learned route can rot or be poisoned overnight, so cached web routes carry an expiry and re-verify. The web may *inform* the system; it must never *poison* it.
- **Human Taste Memory** — preferred tone, explanation depth, design and coding style, naming conventions, career goals, feedback patterns. Purpose is alignment, not manipulation: adapt AI to the human, not the human to the AI.
- **Verified Experience & Skill Replay** — repeated, verified workflows become reusable skills, so the next similar task runs faster and safer.
- **Living-being interface** — a real-time, embodied AI-OS visualization (event stream, approval UI, memory/project dashboard) rather than a static console.

---

## The ceiling — what GAGOS deliberately can't do

A serious system names its limits:

- It **cannot inspect the models' weights.** It governs their *use*, not their internals.
- It **cannot guarantee correctness** — only *verify against checks it can actually run*. Unverifiable claims stay suggestions.
- Its future web navigation **inherits staleness and poisoning risk.** These are *mitigated* (freshness, quarantine, cross-verification), not *solved*.
- Its taste memory is only ever as good as **the facts the operator approved.**
- It is **not infrastructure-sovereign** while it depends on cloud APIs. Local-first narrows this; it doesn't erase it.

---

## Roadmap

1. **Foundation** *(current)* — backend, frontend, control loop, tool execution, approval gates, memory proposal/approval, routing.
2. **Project Awareness** — Harvester, Project Passport, safe-command detection, project-scoped memory.
3. **Verified Experience** — verification logs, outcome tracking, skill attempts, workflow replay.
4. **Human Taste Layer** — editable preference memory, tone/style/convention learning, feedback loop.
5. **Sovereign Web Navigator** — cited web search, trust ranking, quarantine, internet-to-project reasoning.
6. **Public Product** — Student / Developer / Professional / Creator modes, onboarding, demo videos, case studies.

---

## Security principles

Deny dangerous actions by default · require approval for risky operations · keep audit logs · separate observation from memory · separate AI suggestion from trusted fact · never auto-trust model output or web content · keep memory editable and reversible · prefer local execution · **fail closed when uncertain.**

---

## Proof, not claims

A GAGOS demo is judged by a real workflow, end to end:

1. Operator selects an existing project.
2. GAGOS scans it → builds a Project Passport.
3. It identifies weak areas and proposes improvements.
4. Operator approves any risky edits.
5. GAGOS applies changes → runs verification → reports evidence.
6. Approved lessons are saved; the workflow is reused, faster and safer, next time.

That loop — context, permission, verification, memory — is the line between a chatbot and a governed AI-OS layer.

---

## Positioning

**One line:** An AI layer that learns your projects, your style, and your workflow — and keeps *you* in control.

**Technical:** A local-first, cloud-capable, human-supervised agentic control plane where LLMs act as untrusted workers inside a trusted system of memory, permissions, routing, verification, and auditability.

---

## Disclaimer

Experimental, alpha-stage prototype. Not a production security system, enterprise automation platform, or autonomous OS. Review actions before execution. Do not grant unrestricted access to sensitive files, credentials, or destructive commands.

**Human-owned. System-trusted. AI-assisted.**
