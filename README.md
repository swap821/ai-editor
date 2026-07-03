# GAGOS — a supervised AI operating system that earns its own intelligence

> **Think of most AI agent tools as a telephone.** You call an expert (the LLM), relay
> questions back and forth, and hang up. GAGOS is different. It's closer to an **apprentice
> who works under a master craftsman** — supervised on every action, learning from verified
> outcomes, remembering its mistakes, and gradually developing the ability to perform
> practiced tasks entirely on its own. The master (you) always has final authority.
> The apprentice earns autonomy by proving competence, never by claiming it.

---

## What this is

GAGOS is a local-first, supervised AI operating system — a Python backend (`aios/`) and a
WebGL organism frontend (`frontend/`) — that orchestrates LLMs (local Ollama, AWS Bedrock,
Google Gemini) through a security-gated, verification-backed pipeline where:

- **Every action is classified** into GREEN (auto-execute), YELLOW (human approval required),
  or RED (blocked) by a deterministic, fail-closed security gateway. Think of it like airport
  security — the scanner doesn't care who packed the bag; it scans the contents.

- **Every outcome is verified** by running real tests, not by asking the LLM "did it work?"
  A passing test is evidence. A model's narration is not.

- **Every lesson is earned.** A skill becomes "verified" only after ≥3 independently successful
  executions at ≥80% rate. A mistake becomes a lesson only after the fix proves itself on a
  later task. Nothing is trusted because the model said so.

- **The LLM is an untrusted subordinate.** It proposes actions. The security gateway, verifier,
  confidence filter, and human operator *decide*. The model can never approve its own writes,
  override the gateway, or escalate its own permissions.

The frontend renders all of this as a **living organism** — a spectral particle cloud brain,
a spinal cord panel controller, nerve conduction pulses, metabolic cost tracking, and body
posture shifts that show *how* the system is thinking, not just what it outputs. The organism's
body tells the truth about its cognitive state.

## The sovereignty thesis

> **Analogy:** Most AI tools are like a restaurant that closes when the chef (LLM) doesn't
> show up. GAGOS is building a restaurant where the kitchen staff learn the regular menu
> by doing it repeatedly under the chef's supervision. Eventually, the chef can take a day
> off and the regulars still get served. The tasting menu still needs the chef. But the
> signature dishes? The staff have those down cold.

The system earns native intelligence through accumulated verified experience:

- **Cerebellum (Phase S1 — LANDED ✓):** Verified skill arcs compile into deterministic
  playbooks that replay without any LLM call, through the full security gateway. Like muscle
  memory — a pianist who's practiced a piece a thousand times doesn't read the sheet music
  anymore, but still follows the rules of music.

- **Knowledge Graph (Phase S2 — IN PROGRESS):** The system's verified facts form a
  confidence-weighted graph it can traverse to answer questions and make inferences without
  consulting an LLM. Like a doctor's diagnostic intuition — cough + fever + rash → measles?
  → check vaccination history. Graph traversal, not text generation.

- **Native Planner (Phase S3 — SPEC'D):** Known task shapes plan deterministically from
  compiled templates. Like a chess engine's opening book — the first 15 moves are recalled
  instantly; creative play starts when the position leaves the book.

When all three are wired, LLMs become **turbochargers, not the engine**. The system handles
every task shape it's verified before. Novel tasks fall through to the LLM. Cold start (no
experience) behaves identically to today. Sovereignty is earned, never declared.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        OPERATOR (you)                          │
│  Final authority on YELLOW actions · approves/rejects writes   │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                    ORGANISM FRONTEND                            │
│  Brain point field · Spine anatomy · Nerve conduction          │
│  Body posture · Metabolism · Memory galaxy · Boot sequence      │
│  React 19 + Three.js + R3F · Tailwind v4 · Vitest              │
│  SSE ←→ cognitionBus → every visual component                  │
└────────────────────────────┬────────────────────────────────────┘
                             │ SSE
┌────────────────────────────▼────────────────────────────────────┐
│                      FastAPI BACKEND                            │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ CEREBELLUM  │  │  TOOL AGENT  │  │     COUNCIL RUNTIME    │ │
│  │ compiled    │→ │ reason→act→  │  │ Queens (Plan/Security/ │ │
│  │ playbook    │  │ observe loop │  │ Memory/Test/Critique)  │ │
│  │ replay      │  │ + reflection │  │ → King Report          │ │
│  └──────┬──────┘  └──────┬───────┘  └────────────────────────┘ │
│         │                │                                      │
│         ▼                ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              SECURITY GATEWAY (frozen)                    │  │
│  │  3-zone classify → scope lock → secret scan → audit log  │  │
│  │  Fail-closed · Deterministic · LLM-independent            │  │
│  │  Ed25519-signed hash-chained tamper-evident ledger        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    MEMORY SYSTEM                          │  │
│  │  Semantic facts (graph) · Episodic · Mistake · Skills     │  │
│  │  CRAG refinement · BM25+FAISS hybrid · Temporal decay     │  │
│  │  Fact extraction (operator-only) · Curriculum tracking    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                 MULTI-CLOUD ROUTER                        │  │
│  │  Policy (operator-owned) → Rank (evidence-calibrated)     │  │
│  │  → optional LLM picker (constrained to allowed set)       │  │
│  │  Ollama (local) · Bedrock (AWS) · Gemini (Google)         │  │
│  │  LOCAL_FIRST default — nothing leaves the machine          │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick start

### Prerequisites

- Python 3.11+
- Node.js 20+
- (Optional) [Ollama](https://ollama.com) with a tool-calling model
  (`ollama pull qwen2.5-coder:7b`)

### Backend

```bash
git clone https://github.com/swap821/ai-editor.git
cd ai-editor
python -m venv .venv
.venv/bin/pip install -r requirements.txt    # Linux/Mac
# or: .venv\Scripts\pip install -r requirements.txt  # Windows

# Run
.venv/bin/python -m aios
# Binds to 127.0.0.1:8000 by default
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

### Prove it works

```bash
# Scripted end-to-end proof — no LLM required
.venv/bin/python prove_it.py

# Sovereignty proof — cerebellum compiles and replays without LLM
.venv/bin/python prove_cerebellum.py
```

Both scripts print `[PASS]` / `[FAIL]` per step with real evidence. No faked green bars.

---

## The security spine

> **Analogy:** Think of the security spine as a building's fire safety system. Smoke
> detectors (gateway classification), fire doors (scope locks), sprinklers (secret
> scanners), and the fire log (audit trail) all work independently of the building's
> tenants (the LLMs). A new tenant doesn't get to disable the sprinklers. A compiled
> playbook from the cerebellum doesn't get to bypass the gateway. The safety system
> is structural, not behavioral.

The security subsystem is **frozen** — no automated path can modify it. This is enforced
structurally, not by policy.

| Layer | What it does | File |
|-------|-------------|------|
| **Gateway** | Deterministic 3-zone classifier. Empty/unknown/exception → RED (fail-closed). Homoglyph normalization. Shell composition blocking. | `aios/security/gateway.py` |
| **Scope Lock** | Canonicalizes paths, resolves symlinks, refuses traversal outside project root. | `aios/security/scope_lock.py` |
| **Secret Scanner** | Regex + entropy detection. Secrets are redacted *before* hashing or storage. | `aios/security/secret_scanner.py` |
| **Audit Logger** | Ed25519-signed, SHA-256 hash-chained, append-only ledger. Tamper-evident. Key rotation. | `aios/security/audit_logger.py` |
| **Injection Shield** | Regex patterns for prompt injection attempts + optional embedding-similarity layer. | `aios/security/injection_shield.py` |

Adversarial test coverage: `tests/adversarial/` — 7 suites covering command substitution
bypasses, Unicode homoglyphs, shell escape hatches, sandbox escapes, secret detection gaps,
and more.

---

## The organism frontend

> **Analogy:** Most AI UIs are dashboards — arrays of numbers and status indicators, like
> reading a spreadsheet about someone's health. GAGOS's frontend is more like watching
> a living creature — you can tell if it's relaxed, concentrating, struggling, or waiting
> for you, the same way you can read a dog's posture without checking a status panel.

The frontend renders the AI's cognitive state as a biological organism:

| Component | What it represents | Key file |
|-----------|-------------------|----------|
| **Brain Point Field** | 3D spectral particle cloud — churns during LLM reasoning, calms during compiled recall | `BrainPointField.tsx` |
| **Spine Anatomy** | Ordered panel controller — vertebrae are addressable seats for workspace tabs | `spineAnatomy.ts` |
| **Nerve Conduction** | Attention pulses traveling the spine — fast and clean for cerebellum replays, preceded by brain activity for LLM turns | `AttentionConductionPulse.tsx` |
| **Body Posture** | Whole-organism hue shift: purple (thinking), cyan (streaming), orange (holding for approval), green (complete), red (error) | `bodyPosture.ts` |
| **Turn Metabolism** | Metabolic cost tracking — near-zero for compiled replays, high for novel LLM turns | `turnMetabolism.ts` |
| **Phase Weather** | Emotional atmosphere from cognitive state — reflex (fast), narrative (structured), emotion (uncertain) | `phaseWeather.ts` |
| **Lifecycle State Machine** | BOOTING → ARRIVING → REST ↔ ATTENTIVE, with materialization/reabsorption for tab lifecycle | `lifecycleStateMachine.ts` |
| **Memory Galaxy** | Visual representation of stored memories and knowledge beads | `MemoryGalaxy.tsx` |

Every visual component subscribes to the **cognitionBus** (`cognitionBus.ts`) — a module-level
pub/sub that carries typed events from the backend SSE stream. New cognitive capabilities
(cerebellum, knowledge graph) publish new event types on the same bus. The body reacts to
signals it's never seen before because it's already wired to respond to the bus, not to
specific signal types.

---

## The agentic loop

> **Analogy:** Think of the tool agent like a surgical team, not a solo surgeon. The
> surgeon (LLM) proposes the incision. The scrub nurse (gateway) checks the instrument.
> The anesthesiologist (scope lock) confirms the patient is stable. The recorder (audit
> logger) documents every action. The pathologist (verifier) examines the result. If the
> surgeon proposes something dangerous, the team stops the procedure — the surgeon doesn't
> get to overrule the team.

The `ToolAgent` (`aios/agents/tool_agent.py`) runs a bounded reason→act→observe loop:

1. **Cerebellum check** — if a compiled playbook matches, replay it without an LLM call
2. **LLM proposes** a tool call (read, write, execute, verify, plan, analyze)
3. **Gateway classifies** the action: GREEN → execute, YELLOW → pause for human, RED → block
4. **Tool dispatches** through gated handlers with scope locking and secret scanning
5. **Force-verify-after-write** — any landed write immediately triggers the test suite
6. **Reflect on failure** — genuine errors produce structured lessons for the Mistake DB
7. **Loop detection** — repeated identical calls or A→B→A→B oscillation stops the loop

Additional agents: **Reflection Agent** (failure → structured lesson), **Rollback Engine**
(git-snapshot restore on failure), **Self-Analysis Agent** (read-only codebase diagnosis),
**Swarm** (stigmergic multi-agent decomposition with ant-colony patterns).

---

## Multi-cloud routing

> **Analogy:** An F1 team doesn't use the same tire compound for every circuit. Soft tires
> for Monaco (fast, short-lived), hards for Spa (durable, slower). The router is the tire
> strategist — it picks the right model for the task, calibrated by real performance data,
> within boundaries the team principal (operator) sets.

The router (`aios/core/router.py`) selects models across three providers:

1. **Policy gate** (deterministic, operator-owned): which task classes may leave the machine.
   Default: `LOCAL_FIRST` — nothing goes to cloud until the operator opts in.
2. **Evidence-calibrated rank**: capability scores blended with measured per-(provider, model,
   task) verified-success rates from the development tracker.
3. **Optional LLM picker**: a local model can reorder preference within the allowed set.
   It can never escape the policy — its choice is validated against the allowed candidates.

Supported providers: **Ollama** (local, free, private), **AWS Bedrock** (Claude via Converse
API), **Google Gemini** (Vertex AI, lazy-loaded).

---

## Memory system

| Layer | Purpose | Trust level |
|-------|---------|-------------|
| **Working Memory** | RAM-only session context | Ephemeral |
| **Episodic Memory** | Chronological conversation record | Raw, unverified |
| **Semantic Memory** | BM25 + FAISS hybrid retrieval with temporal decay | Verification-gated |
| **Semantic Facts** | (Subject, Predicate, Object) triples with contradiction detection + graph traversal | Human-approved only |
| **Mistake Memory** | Structured failure post-mortems with confidence deltas | Verified on corrective success |
| **Skill Memory** | Procedural workflows with promotion/demotion lifecycle | ≥3 STRONG verifications |
| **CRAG** | Corrective RAG — sentence-level knowledge strips, noise dropped | Deterministic refinement |
| **Development Tracker** | Per-task outcomes with success rates for router calibration | Verification-backed |

**The trust boundary:** facts enter the graph only through operator statements (via
`fact_extraction.py`) or human-approved proposals. LLM-generated claims never enter.
The graph is a catalog of what the system *knows*, not what it *guesses*.

---

## Project stats

| Metric | Value |
|--------|-------|
| Python backend | ~57K lines across 87 modules |
| Frontend (TS/TSX/JSX) | ~34K lines across 110 source files |
| Backend test files | 109 (including 7 adversarial suites) |
| Frontend test files | 69 |
| Total test functions | 1,538 |
| Test:code ratio (backend) | ~1:1 |
| Commits | 710 (solo) |
| Project age | 33 days (June 1 – July 3, 2026) |
| CI | GitHub Actions — pytest 85% coverage gate + pip-audit + npm audit + typecheck + production build |
| Dependencies | Fully pinned in `requirements.txt` |

---

## Observability

Docker Compose stack with Prometheus, Grafana, and Alertmanager:

```bash
AIOS_API_TOKEN=<32-char-token> docker compose up --build
```

- **Prometheus** (`:9090`): request latency, zone classification counts, audit chain health
- **Grafana** (`:3000`): pre-provisioned GAGOS dashboard
- **Alertmanager** (`:9093`): alert routing

---

## Tech stack

**Backend:** Python 3.11 · FastAPI · SQLite (WAL) · sentence-transformers · FAISS ·
GitPython · cryptography (Ed25519) · boto3 (Bedrock) · structlog · Prometheus client

**Frontend:** React 19 · Three.js / React Three Fiber · Tailwind CSS v4 · Monaco Editor ·
Framer Motion · Vitest · TypeScript

**Infrastructure:** Docker · Docker Compose · Prometheus · Grafana · Alertmanager ·
GitHub Actions CI

---

## Repository structure

```
aios/                    # Python backend
  api/main.py            # FastAPI orchestration (SSE streaming)
  agents/                # Tool agent, reflection, rollback, swarm, self-analysis
  core/                  # Router, planner, executor, verifier, cerebellum, confidence
  council/               # Queens (planner/security/memory/testing/critique) + King
  memory/                # Episodic, semantic, facts, skills, mistakes, CRAG, curriculum
  runtime/               # Worker spawner, cortex bus, contracts, backends
  security/              # Gateway, scope lock, secret scanner, audit logger (FROZEN)

frontend/                # Organism UI
  src/superbrain/        # 3D living-being components + lib
    components/canvas/   # BrainPointField, NervousSystem, MemoryGalaxy, etc.
    components/ui/       # SuperbrainHUD, ApprovalPanel, BootSequence
    lib/                 # cognitionBus, bodyPosture, phaseWeather, tabStore, etc.
  src/workbench/         # GagosChrome shell, CouncilDashboard, CommandDock

tests/                   # Backend test suite
  adversarial/           # Security bypass attempt suites
  golden/                # Snapshot-based golden tests
  e2e/                   # End-to-end integration tests

docs/superpowers/specs/  # Design specs (dated, grounded against code)
tools/                   # Health checks, CSS canon guards, calibration
training_ground/         # Sandboxed playground for agent operations
observability/           # Prometheus, Grafana, Alertmanager config
```

---

## Sovereignty roadmap

| Phase | Status | What it delivers |
|-------|--------|-----------------|
| **S1 — Cerebellum** | ✅ Landed | Verified skills compile into deterministic playbooks. LLM-free execution for practiced tasks. |
| **S2 — Knowledge Graph** | 🔨 Building | Confidence-weighted graph traversal over verified facts. Multi-hop inference without LLM. Cross-store ingestion from skills, mistakes, development outcomes. |
| **S3 — Native Planner** | 📋 Spec'd | Known task shapes plan from compiled templates. Falls through to LLM for novel tasks. |
| **S4 — Offline Mode** | 📋 Spec'd | Meaningful operation with all LLMs offline. `prove_sovereignty.py` end-to-end proof. |

Design specs: `docs/superpowers/specs/2026-07-03-sovereignty-engine-design.md`

---

## The One Law

> A task the system has verifiably completed three times before executes entirely without
> an LLM call, through the full security gateway, with human approval on YELLOW steps,
> verified by the same evidence-based verifier that judged the original successes — and the
> organism's body shows the user, visually, that this is native action, not external
> consultation.

If this law holds, the system has earned the word "sovereign." Not declared it. Proved it.

---

## Builder council

This project is developed by a multi-agent builder council coordinated through `AGENTS.md`:

- **Claude Code** — primary implementer
- **OpenAI Codex** — adversarial verifier
- **Kimi Code CLI** — architect

Council protocol: `agent_coord.py` manages leases, handoffs, and hash-pinned reviews.
The human operator has final authority on all decisions. See `AGENTS.md` for the full
coordination protocol.

---

## License

This project is not currently under an open-source license. All rights reserved.
Contact the maintainer for licensing inquiries.

---

<sub>Built solo. 710 commits in 33 days. The hard things are done. The engine is being installed.</sub>
