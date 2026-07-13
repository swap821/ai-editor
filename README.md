<div align="center">

# G A G O S

## A Sovereign Intelligence Operating System

**Governed Agentic Guided Operating System**

<br>

> Most AI projects ask: *“How much autonomy can we give the model?”*  
> **GAGOS asks a harder question:** *“When models become powerful, where does authority live?”*

**The model is never trusted. The system must earn trust. The human remains sovereign.**

</div>

---

## Table of Contents

- [What This Is Not](#what-this-is-not)
- [The Organism](#the-organism)
- [A Mission Has a Pulse](#a-mission-has-a-pulse)
- [Why GAGOS Is Unusual](#why-gagos-is-unusual)
- [Constitutional Laws](#constitutional-laws)
- [The Eight Organs](#the-eight-organs)
- [Current Reality](#current-reality)
- [Defensive Design](#defensive-design)
- [Repository Anatomy](#repository-anatomy)
- [Quick Start](#quick-start)
- [Verification](#verification)
- [Configuration Posture](#configuration-posture)
- [What GAGOS Refuses to Become](#what-gagos-refuses-to-become)
- [Research Questions](#research-questions)
- [Development Philosophy](#development-philosophy)
- [Contributing](#contributing)
- [A Note from the Builder](#a-note-from-the-builder)

---

## What This Is Not

A normal AI assistant receives a prompt, calls a model, and returns an answer.

**GAGOS is exploring something fundamentally different:**

A local-first intelligence control plane in which permanent cognitive organs deliberate, temporary workers execute bounded missions, every important action passes through deterministic governance, evidence flows back upward, verified experience becomes memory, and the interface reflects what the system is actually doing.

**The language models are not the operating system.** They are replaceable sources of intelligence living *inside* the operating system.

GAGOS is the layer that decides:

- Which intelligence may participate.
- What context it may see.
- What tools it may request.
- Where it may operate.
- Which actions require approval.
- What must be verified.
- What may become memory.
- What must be rolled back.
- What the human is shown as truth.

---

## The Organism

```
┌─────────────────────────────────────────────────────────────────────┐
│  👑 HUMAN SOVEREIGN                                                │
│  Goal · Taste · Approval · Veto                                     │
│                          ↓                                          │
│  SOVEREIGN KERNEL                                                   │
│  Identity · Policy · Scope · Budgets · Capabilities                 │
│              ↓                    ↓                    ↓            │
│  QUEEN COUNCIL              MEMORY & LEARNING        CORTEX         │
│  Permanent cognitive organs  Episodes · Facts ·      Nervous System │
│                              Skills · Mistakes ·                    │
│                              Trails · Provenance                    │
│              ↓                                                      │
│  WORKER FOUNDRY                                                     │
│  Creates bounded temporary intelligence                             │
│              ↓                                                      │
│  ┌──────────┬──────────┬──────────┐                                 │
│  │ Builder  │ Scout    │ Test /   │                                 │
│  │ Worker   │ Worker   │ Research │                                 │
│  └────┬─────┴────┬─────┴────┬────┘                                 │
│       ↓          ↓          ↓                                      │
│  ISOLATED EXECUTION PLANE                                           │
│  Workspace · Tool limits · Resource limits · No implicit authority  │
│                          ↓                                          │
│  PROOF & RECOVERY                                                   │
│  Evidence · Verification · Promotion · Rollback                     │
│                          ↓                                          │
│  LIVING MIRROR                                                      │
│  A truthful visual self-portrait                                    │
│                          ↓                                          │
│  👑 HUMAN SOVEREIGN (loop closed)                                   │
└─────────────────────────────────────────────────────────────────────┘
```

### The Metaphor Is Not Decoration

The biological and sovereign language maps to concrete engineering responsibilities.

| GAGOS Concept | Engineering Meaning |
|---------------|---------------------|
| **Human Sovereign / King** | The authenticated human with final approval, veto and shutdown authority |
| **Sovereign Kernel** | Deterministic identity, policy, scope, capability and budget enforcement |
| **Queen Council** | Permanent specialist reasoning organs that deliberate but do not execute unrestricted actions |
| **Temporary Workers** | Mission-bound processes or agents created for specific work and dissolved afterward |
| **Cortex** | Durable observation and event infrastructure connecting the organism |
| **Memory** | Provenance-aware episodic, semantic, factual, procedural and reflective stores |
| **Pheromone Trails** | Decaying advisory signals learned from verified outcomes—not permissions |
| **Living Mirror** | A 3D and 2D frontend whose operational state comes from backend truth |
| **Immune System** | Read-only detection of unsafe patterns, drift, bypasses and internal degradation |
| **Proof Organs** | Verification, evidence strength, audit, checkpoints and rollback |

---

## A Mission Has a Pulse

Imagine telling GAGOS:

> *“Inspect this project, find the cause of the failing frontend test, repair it without touching the backend, verify the fix and explain what was learned.”*

A mature GAGOS mission unfolds like this:

```
01  The human declares the goal
          ↓
02  Project knowledge and relevant memory are recalled
          ↓
03  The Queen Council identifies scope, uncertainty and risk
          ↓
04  A bounded mission contract is created
          ↓
05  The human approves the exact authority being requested
          ↓
06  Temporary workers are born inside an isolated workspace
          ↓
07  The workers inspect, edit, test and return evidence
          ↓
08  The Testing Queen challenges the result
          ↓
09  Verified work is promoted—or automatically rejected and rolled back
          ↓
10  Proven experience becomes reusable memory
          ↓
11  Workers dissolve
          ↓
12  The living interface visibly returns to rest
```

**The intended result is not merely:** *“AI changed a file.”*

**It is:**

> A specific principal performed a specific action inside a specific mission and scope, under a specific policy, using a specific capability, inside a known environment, produced inspectable evidence, passed a declared verification standard, and remained reversible by the human.

---

## Why GAGOS Is Unusual

### 1. Intelligence and Authority Are Separated

Models may **propose, reason, plan, critique, generate candidate changes, and interpret evidence.**

Models may **not define their own permissions.**

A persuasive model response is not an authorization token.

### 2. The Council Is Permanent; Workers Are Temporary

Most agent systems create a flat crowd of agents and let them negotiate.

**GAGOS separates two kinds of intelligence:**

| Permanent Organs | Temporary Workers |
|------------------|-------------------|
| The Queen Council maintains stable responsibilities: planning, memory, security, testing, reflection. | Workers are born for a mission, receive limited scope and tools, return evidence and dissolve. |
| Queens produce verdicts, constraints and evidence. | This limits long-lived privilege and prevents every specialist from becoming another permanent autonomous process. |
| They do not receive unlimited execution authority. | |

### 3. Memory Must Be Earned

GAGOS does not treat repetition as truth.

A statement, model output, project scan or worker result may begin as:

```
observation → candidate → proposal
```

It should become trusted memory only through **evidence, verification or explicit human approval.**

Memories retain **provenance, confidence, contradiction and supersession history.**

### 4. Verification Has Strength

A successful process exit is not always proof.

GAGOS distinguishes weak signals from behavior-confirming evidence. Downstream learning is limited by the weakest authoritative evidence in the chain.

> A passing test for one file should never erase an unresolved failure in another target.

### 5. The Frontend Is Meant to Be the System's Body

The interface is not supposed to animate fictional intelligence.

Worker births, approvals, verification failures, model routing, memory formation and system degradation should originate from **real operational events.**

Ambient motion can make the organism feel alive. It must not make false operational claims.

### 6. Local and Cloud Intelligence Coexist Under Policy

GAGOS can use local inference and configured cloud providers, but provider availability alone does not grant permission to send data externally.

Routing decisions account for:

- Task type
- Privacy classification
- Local capability
- Cost
- Latency
- Model health
- Operator policy
- Mission constraints

**Cloud intelligence is an optional cognitive resource—not the owner of the system.**

---

## Constitutional Laws

These are not branding statements. They are **architectural invariants.**

| Law | Statement |
|-----|-----------|
| **I** | The Human Sovereign is the final authority. |
| **II** | A model may propose an action but may never authorize itself. |
| **III** | RED actions remain blocked. Approval does not magically make them safe. |
| **IV** | Every side effect must have an attributable principal and mission. |
| **V** | Authority must be narrow, exact, expiring and revocable. |
| **VI** | Untrusted work must not execute directly inside the control plane. |
| **VII** | Unknown state must be shown as unknown—not invented. |
| **VIII** | Evidence must exist before successful experience becomes trusted memory. |
| **IX** | The Cortex carries observations, never permission. |
| **X** | Every important mutation must remain auditable and recoverable. |

---

## The Eight Organs

### Ⅰ. Sovereign Kernel

The trusted control spine.

- Operator identity
- Session posture
- Deterministic risk classification
- Scope enforcement
- Approval capabilities
- Tool permissions
- Resource budgets
- Data-classification policy
- Emergency shutdown
- Autonomy limits

### Ⅱ. Queen Council

Permanent specialist cognition.

Current and emerging Queen responsibilities include:

- Planning
- Memory
- Security
- Testing
- Routing
- Reflection
- Critique
- Project understanding

Queens produce verdicts, constraints and evidence. They do not receive unlimited execution authority.

### Ⅲ. Worker Foundry

Creates temporary intelligence for bounded missions.

Worker forms may include:

- Builder
- Scout
- Forager
- Soldier
- Nurse
- Researcher
- Inspector
- Test worker
- Role-pass worker
- Swarm strategy

The caste metaphor describes **constrained behavior profiles**—not decorative agent names.

### Ⅳ. Execution Plane

The boundary between proposed intelligence and real-world effects.

- Structured commands instead of ambient shell access
- Isolated workspaces
- Explicit file scope
- Resource limits
- No network by default
- Secret isolation
- Staged changes
- Bounded output
- Process-tree termination
- No silent host fallback

### Ⅴ. Cortex Nervous System

Durable signals connecting the organism.

The Cortex records what happened:

- A turn began
- A plan formed
- Memory was recalled
- A worker started
- An action was blocked
- Human approval became necessary
- Verification passed or failed
- A worker dissolved

**The Cortex must never decide what is permitted.**

### Ⅵ. Memory and Learning

GAGOS explores several complementary forms of memory:

- Working memory
- Conversation state
- Episodic memory
- Semantic retrieval
- Verified facts
- Procedural skills
- Mistake memory
- Developmental curriculum
- Swarm patterns
- Council memory
- Narrative self-model
- Pheromone trails

Different memories answer different questions. They should not be collapsed into one giant vector search.

### Ⅶ. Proof and Recovery

The system must be able to explain why it trusts an outcome.

- Verification plans
- Evidence records
- Evidence-strength classification
- Target-specific results
- Audit chains
- Snapshots
- Promotion gates
- Post-promotion checks
- Rollback

### Ⅷ. Living Mirror

The frontend is the organism's self-portrait.

Built with **React, Vite, React Three Fiber, Three.js, Monaco** and a hybrid 3D/DOM workbench, it brings together:

- Conversation
- Council deliberation
- Project files
- Code editing
- Terminal activity
- Memory inspection
- Worker and swarm state
- Governance
- Verification
- System health

The visual system is ambitious by design: the AI-OS should not look like another rectangle with a chat box.

---

## Current Reality

GAGOS is an **alpha research prototype** under active architectural convergence. It is not production-ready.

The repository already contains unusually deep working substrates, but not every subsystem has yet converged into one production-grade causal spine.

| Area | Current Reality |
|------|-----------------|
| Deterministic security gateway | ✅ Implemented |
| GREEN / YELLOW / RED classification | ✅ Implemented |
| Human approval flows | ✅ Implemented, still undergoing authority hardening |
| Queen Council | ✅ Implemented as a real backend runtime |
| Mission contracts and verdicts | ✅ Implemented, evolving toward a unified contract |
| Temporary workers | ✅ Implemented, isolation architecture still converging |
| Verification-strength model | ✅ Implemented |
| Audit and rollback concepts | ✅ Implemented |
| Hybrid memory and retrieval | ✅ Implemented |
| Local and cloud model routing | ✅ Implemented behind configuration and policy |
| CRAG and project knowledge | ✅ Implemented |
| Pheromone and skill learning | ✅ Implemented as advisory learning |
| Cortex event substrate | ✅ Implemented, delivery/read-model mechanics evolving |
| Living 3D frontend | ✅ Implemented |
| Truthful backend mirror | ⚠️ Partially implemented and actively hardened |
| Single canonical action authority | 🔄 In convergence |
| Full production worker cage | 🔄 In convergence |
| Production packaging | ❌ Not complete |
| Unrestricted autonomy | 🚫 Intentionally not supported |

**Honesty matters more than an impressive feature count.**

A subsystem is not considered complete merely because:

- A class exists
- A configuration flag exists
- A test imports it
- A UI component renders
- A document describes it

It must be **reachable, enforced, observable and verified** through the real product path.

---

## Defensive Design

### Security Cage

The deterministic security layer classifies operations and blocks unsafe behavior before execution.

- Scope roots
- Protected foundation files
- Secret scanning
- Prompt-injection checks
- Command classification
- Rate limiting
- Human approval
- Container-backed execution paths
- Fail-closed behavior

### Vulture

The Vulture is the beginning of an internal immune system.

Its role is to detect and surface evidence of:

- Security bypasses
- Approval bypasses
- Unsafe self-modification
- Secret-material handling
- Trusted-memory activation without proof
- Internal architectural rot

It is deliberately **read-only**. Detection does not equal autonomous deletion.

### Ecosystem Scanner

The ecosystem layer inspects local dependency and project evidence. Its purpose is to help the organism understand the environment surrounding it without silently widening network access or mutating the project.

### Audit

Important decisions and actions are intended to remain attributable and tamper-evident.

The long-term goal is not simply to record logs. It is to reconstruct causality:

```
Human directive
  → Council decision
    → Mission contract
      → Capability
        → Worker action
          → Evidence
            → Verification
              → Promotion or rollback
                → Memory consequence
```

---

## Repository Anatomy

```
ai-editor/
│
├── aios/
│   ├── api/                 # FastAPI surface and route adapters
│   ├── agents/              # Tool agents, role passes, swarms, reflection
│   ├── council/             # Queen Council and deliberative organs
│   ├── cognition/           # Project and structural understanding
│   ├── core/                # Routing, execution, verification, autonomy
│   ├── interfaces/          # External boundaries such as HTTP policy
│   ├── learning/            # Meta-learning and developmental systems
│   ├── maintenance/         # Vulture, ecosystem and sanitation evidence
│   ├── memory/              # Episodic, semantic, factual and skill memory
│   ├── policy/              # Constitution and governance vocabulary
│   ├── runtime/             # Missions, workers, Cortex, ledgers and snapshots
│   └── security/            # Deterministic security spine
│
├── frontend/
│   └── src/
│       ├── components/      # Interface and canvas organs
│       ├── superbrain/      # Living 3D organism and nervous reactions
│       └── workbench/       # Conversation, code, files and governance
│
├── tests/                   # Unit, integration and adversarial evidence
├── tools/                   # Audits, probes and verification utilities
├── docs/                    # Architecture, ADRs, plans and research notes
├── .aios/                   # Builder continuity, state and project memory
└── docker-compose.yml       # Local runtime and observability stack
```

---

## Quick Start

### Requirements

- Python 3.11 or newer
- Node.js 20 or newer
- Git
- Optional: Docker Desktop
- Optional: Ollama for local inference

### 1. Clone

```bash
git clone https://github.com/swap821/ai-editor.git
cd ai-editor
```

### 2. Create the Python Environment

**Windows PowerShell**

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

**Linux or macOS**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

### 3. Optional: Local Model

```bash
ollama pull qwen2.5-coder:7b
```

Configure the chosen model through the environment rather than assuming the example is the repository default.

### 4. Start the Control Plane

```bash
python -m aios
```

The default local API address is: `http://127.0.0.1:8000`

### 5. Start the Living Frontend

Open another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open the local URL printed by Vite.

---

## Verification

The repository treats **test evidence as more important than README claims.**

### Backend

```bash
python tools/thesis_audit.py
python -m pytest -q
python -m pytest -q \
  --cov=aios \
  --cov-report=term-missing \
  --cov-report=xml \
  --cov-fail-under=85
```

### Frontend

```bash
cd frontend
npm run typecheck
npm run lint
npm run test:coverage
npm run build
```

> **Verification rule:** Do not copy old pass counts into reports. Run the commands and report the current result.

---

## Configuration Posture

The complete source of truth is `aios/config.py`.

`AIOS_SWARM_CLOUD_BURST` is a separate worker-swarm egress control; it does
not change the router task-class allowlist. Keep it set to `0` for local-only
swarm execution, and remember that provider policy and the security cage still
apply.

Common configuration areas include:

```python
# Explicit project scope
AIOS_SCOPE_ROOTS=training_ground;lab

# Local inference
AIOS_LLM_MODEL=qwen2.5-coder:7b
OLLAMA_HOST=http://127.0.0.1:11434

# Cloud eligibility
AIOS_ROUTER_CLOUD_TASKS=reasoning,coding

# Hard local-only override
AIOS_ROUTER_CLOUD_TASKS=""

# Worker limits
AIOS_SWARM_MAX_WORKERS=4
AIOS_COUNCIL_MAX_CONCURRENT_WORKERS=4

# Execution boundary
AIOS_APPROVED_EXECUTION_BACKEND=container

# API edge
AIOS_API_HOST=127.0.0.1
AIOS_API_PORT=8000
```

> **Do not place real credentials inside the repository.**  
> Do not infer a safety guarantee from one environment variable alone. Runtime validation and policy enforcement must agree.

---

## What GAGOS Refuses to Become

GAGOS is **not**:

- ❌ An operating-system kernel replacement
- ❌ An LLM with unrestricted terminal access
- ❌ A wrapper around a single model provider
- ❌ A theatrical multi-agent chat room
- ❌ A system where every agent is permanent
- ❌ A dashboard that fabricates activity
- ❌ A memory store that treats generated text as truth
- ❌ A self-modifying system that can weaken its own constitution
- ❌ A promise that autonomy is safe merely because a human clicked "approve"
- ❌ Production-ready today

**The intended destination is:**

> Supervised, explainable, permissioned, evidence-backed and recoverable autonomy for one developer.

---

## Research Questions

GAGOS is also an engineering research project. It asks:

1. Can permanent cognitive organs and temporary workers outperform a flat agent swarm?
2. Can autonomy be earned per action class rather than granted globally?
3. Can verification strength prevent weak successes from poisoning memory?
4. Can a local system combine multiple models without letting any provider become authority?
5. Can an AI interface feel alive while remaining constitutionally truthful?
6. Can biological concepts such as pheromones, immune response, consolidation and development become useful computational mechanisms rather than metaphors?
7. Can one developer build a safe miniature intelligence institution instead of another assistant?

The project does not pretend these questions are solved. It turns them into **code, tests and falsifiable architecture.**

---

## Development Philosophy

> **Build the system that supervises intelligence, not the illusion that intelligence supervises itself.**

Changes should preserve these priorities:

1. **Authority** before autonomy
2. **Isolation** before execution
3. **Evidence** before memory
4. **Verification** before promotion
5. **Recovery** before mutation
6. **Truth** before animation
7. **Coherence** before feature count

A new subsystem should not be accepted merely because it is interesting. It must have:

- A defined organ
- A production constructor
- A real caller
- An authority classification
- A state owner
- Tests
- Observability
- Failure behavior
- A reason it cannot be implemented by an existing subsystem

---

## Contributing

GAGOS welcomes careful engineering, adversarial review and architectural criticism.

**High-value contributions include:**

- Finding authority bypasses
- Improving worker isolation
- Strengthening verification
- Detecting fabricated or stale frontend state
- Simplifying duplicated runtime paths
- Improving cross-platform behavior
- Adding side-effect assertions to security tests
- Improving accessibility and reduced-motion support
- Making memory provenance clearer
- Proving that a dormant subsystem is either useful or dead

### Before Opening a Pull Request

```bash
python -m pytest -q --cov=aios --cov-fail-under=85
cd frontend
npm run typecheck
npm run lint
npm run test:coverage
npm run build
```

> **Never weaken a security invariant to make a test green.**

---

## A Note from the Builder

GAGOS began with a simple discomfort:

> Giving a powerful language model more tools does not automatically create a trustworthy system.

The interesting engineering problem is not only making AI more capable. It is building the structures around intelligence that make capability:

- **Bounded**
- **Inspectable**
- **Correctable**
- **Reversible**
- **Accountable to a human**

This repository is being built as a serious single-developer prototype—not because one developer can recreate an enterprise AI platform, but because the central ideas can be demonstrated at human scale.

A sovereign intelligence system does not begin by asking the model to rule.

**It begins by designing a constitution the model cannot quietly escape.**

---

<div align="center">

## GAGOS

Many models may think.  
Temporary workers may act.  
Evidence must return.  
The system must remember honestly.  
The human remains sovereign.

---

**Built by Kumar Swapnil**

[Explore the architecture](https://github.com/swap821/ai-editor) · 
[Inspect the control plane](https://github.com/swap821/ai-editor/tree/master/aios) · 
[Enter the living interface](https://github.com/swap821/ai-editor/tree/master/frontend) · 
[Read the tests](https://github.com/swap821/ai-editor/tree/master/tests)

Licensed under the [Apache License 2.0](LICENSE).

</div>
