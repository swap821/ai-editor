# GAGOS - Sovereign AI-OS

**G**overned **A**gentic **G**uided **O**perating **S**ystem

> Not an OS replacement. GAGOS is an intelligence layer above the OS that keeps
> the human operator sovereign while language models work inside deterministic
> policy, approval, memory, routing, audit, and verification boundaries.

GAGOS is a local-first, cloud-capable, human-supervised control plane for
agentic work. It connects local project knowledge, local and policy-permitted
cloud LLMs, memory, tools, approvals, verification, and a 3D sovereignty UI. It
is experimental, not production-ready, and its main design law is blunt:

**The model is never trusted. The system is trusted. The human is sovereign.**

## What Is Real Today

This section is intentionally operational. If a claim here drifts from config or
tests, `python tools/thesis_audit.py` should catch it.

| Organ | Status | Truth |
| --- | --- | --- |
| Security Cage | Built | `aios/security/gateway.py` classifies actions as GREEN/YELLOW/RED. RED is blocked, YELLOW requires approval unless exact-class earned autonomy applies, and unknown fails closed. |
| Constitution | Built seed | `aios/policy/constitution.py` and `constitution_enforcer.py` expose executable policy vocabulary over existing gateway, router, budget, caste, and frozen-core rules. They add caution or blocks; they do not override stronger authorities. |
| Audit + Rollback | Built | Critical actions are audited; write paths use snapshots, confinement, verification, and rollback support through the existing spine. |
| Router | Built | `Auto` can route across local Ollama and configured cloud providers, but only through deterministic policy. The current cloud-task default is `reasoning,coding`; set `AIOS_ROUTER_CLOUD_TASKS=""` to force local-only routing. `AIOS_SWARM_CLOUD_BURST` is a separate egress control for swarm cloud bursts. |
| Memory | Built | Facts are proposed, approved, then active. Project scans and model output are evidence/proposals, not trusted memory. |
| Project Knowledge | Built seed | Project Passport scans repos locally into purpose, stack, folder map, key commands, env vars, risks, issues, goals, and suggestions. Deeper symbol RepoMap/PageRank is roadmap. |
| Pheromones | Built | Typed, decaying, auditable hints influence planning/worker context but never override security, verification, or human approval. |
| Caste Workers | Built | Forager, Builder, Scout, Soldier, and Nurse profiles clamp tools, scope, timeout, and evidence expectations over the existing worker runtime. Workers are ephemeral. |
| Royal Decree | Built seed | Complex work can get scout-first advisory plans before execution. The decree is evidence, not authority. |
| Resource + Hibernation | Built seed | Resource mode can block expensive/cloud operations. Hibernation is local-only maintenance evidence: no writes, cloud calls, self-modification, git push, or credential access. |
| Vulture / Immune System | Built read-only seed | `aios/maintenance/vulture_sanitation.py` detects security-bypass, approval-bypass, trusted-memory activation, unsafe self-modification, and secret-material patterns as redacted quarantine proposals. It does not delete, mutate memory, mutate policy, or touch frozen core. |
| Ecosystem Scanner | Roadmap | Phase 3 target: local-only dependency/config/git/API-text scanner staged under `aios/maintenance/*` first. A security-core promotion requires separate Section VIII approval. |
| Sovereign UI | Built seed | `frontend/src/workbench/SovereignStatePanel.jsx` shows backend-backed RepoMap, resource, hibernation, pheromone, caste, autonomy, and proposal indicators. No fake liveness claims. |

## What GAGOS Is Not

- Not a Windows, Linux, or macOS replacement.
- Not a blind code executor.
- Not an unrestricted autonomous agent.
- Not a system where an LLM has final authority.
- Not production-ready.

The goal is supervised autonomy: permissioned, auditable, recoverable, and
explainable.

## Sovereign Architecture

```text
Human Operator
  -> approval / veto via King
Sovereign AI-OS Layer
  -> policy / memory / routing / tools / proof
Queen Council + Temporary Workers
  -> evidence flows up
Local Machine + Project Universe
  -> roadmap
Open Internet Universe
```

The durable pattern is:

1. Scout first for complex work.
2. Produce structured plan/evidence.
3. Review through deterministic policy and council surfaces.
4. Generate narrow worker contracts.
5. Execute only through approved existing paths.
6. Verify.
7. Report back to the King/operator.

Plans, pheromones, RepoMap/Project Passport output, vulture findings, and
council memory are advisory. They may suggest caution or review. They may not
override the gateway, verifier, budget guard, scope lock, audit policy, or human
approval.

## The Three Defensive Pillars

| Pillar | Current state | Rule |
| --- | --- | --- |
| Cage | Real and frozen | Prevent unsafe action before execution. Do not weaken `aios/security/*`. |
| Vulture | Read-only evidence seed | Detect internal rot and propose quarantine. No autonomous purge or mutation. |
| Ecosystem | Next phase | Inspect local environment evidence without network calls or secret exposure. |

The future vulture authority, if promoted into `aios/security/*`, is frozen-core
work and requires the full Section VIII flow: observe, analyze, propose, test,
verify, human review, approve, deploy. The current v10 Phase 2 implementation is
deliberately outside frozen core under `aios/maintenance/*`.

## Safety Invariants

- RED actions never auto-run.
- YELLOW actions require human approval unless exact-class, verifier-backed,
  revocable earned autonomy applies.
- Earned autonomy is enabled by default but grants nothing until earned; RED is
  never earnable.
- Scope roots must not silently widen to the user home directory.
- Secrets must not be read, logged, stored, or exposed.
- Cloud routing is policy-gated. The config default permits task classes
  `reasoning,coding`, but a provider must be configured before data can leave
  the machine. Use `AIOS_ROUTER_CLOUD_TASKS=""` for a hard local-only override.
- `AIOS_SWARM_CLOUD_BURST` controls swarm cloud bursts separately from the
  router task-class allowlist.
- Scaffold code is blueprint material only; stubs that allow/pass by default
  must not be copied into production.
- README prose is documentation, not authority. The runtime constitution,
  gateway, router, verifier, budget guard, and audit ledger decide.

## Quick Start

Windows PowerShell:

```powershell
git clone https://github.com/swap821/ai-editor.git
cd ai-editor

py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -U pip
.venv\Scripts\python -m pip install -e ".[test]"

# Optional local model setup
ollama pull qwen2.5-coder:7b

# Run backend on 127.0.0.1:8000 by default
.venv\Scripts\python -m aios

# In another shell
cd frontend
npm install
npm run dev
```

Portable backend command:

```bash
python -m aios
```

## Verification

```powershell
python tools\thesis_audit.py
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m pytest -q --cov=aios --cov-report=term-missing --cov-report=xml --cov-fail-under=85
```

Frontend checks, when UI files change:

```powershell
cd frontend
npm test
npm run build
```

Use live command output, not hardcoded pass counts, when reporting status.

## Configuration Notes

Key environment variables live in `aios/config.py`.

```bash
# Scope and approval posture
AIOS_SCOPE_ROOTS=training_ground;lab
AIOS_EARNED_AUTONOMY=true
AIOS_EARNED_AUTONOMY_MIN_SUCCESSES=5

# Planning and workers
AIOS_PLAN_STAGE=true
AIOS_SWARM_MAX_WORKERS=4

# Router and cloud egress
AIOS_ROUTER_CLOUD_TASKS=reasoning,coding
AIOS_ROUTER_CLOUD_TASKS=""
AIOS_ROUTER_PREFER_LOCAL=true
AIOS_ROUTER_MAX_COST=high
AIOS_SWARM_CLOUD_BURST=0

# Resource ecology
AIOS_RESOURCE_MODE=normal
```

Do not infer defaults from this snippet alone; `aios/config.py` is the source of
truth and `tools/thesis_audit.py` guards the most safety-sensitive claims.

## v10 Integration State

The uploaded v10 scaffold is an architectural contract, not production code.
Current integration status:

| Phase | State | Files |
| --- | --- | --- |
| Phase 0 - Truth/Safety Guard | Complete locally | `tools/thesis_audit.py`, `tests/test_thesis_audit.py`, docs |
| Phase 1 - Constitution Facade | Complete locally | `aios/policy/constitution.py`, `aios/policy/constitution_enforcer.py`, `tests/test_constitution.py` |
| Phase 2 - Vulture Read-Only Seed | Complete locally | `aios/maintenance/vulture_sanitation.py`, `tests/test_vulture_sanitation.py` |
| Phase 3 - Ecosystem Scanner | Recommended next | local-only `aios/maintenance/ecosystem_scanner.py` |
| Phase 4 - Signal Ganglia + Council Memory | Planned | typed gradients and durable deliberation evidence |
| Phase 5 - Symbol RepoMap | Planned | stdlib-first symbol graph over Project Passport |
| Phase 6 - Meta Loop | Planned | proposal-only self-assessment |
| Phase 7 - UI Truth Surface | Planned | backend-backed indicators only |

See `.aios/state/V10_INTEGRATION_AUDIT.md` and
`.aios/state/V10_INTEGRATION_PLAN.md` for the detailed contract, risks, and
exit gates.

## Honesty Law

1. Every load-bearing claim should be testable.
2. Prior chat is unverified until grounded in disk state.
3. Memory must be earned through approval and evidence.
4. Project scans are proposals, not trusted memory.
5. Cloud calls require explicit policy allowance and configured providers.
6. Autonomous writes require scope checks, audit, approval where required,
   verification, and rollback support.
7. Security and verification are stronger than planning, pheromones, council
   memory, or scaffold ambition.

## License

Apache-2.0. See [LICENSE](LICENSE).

