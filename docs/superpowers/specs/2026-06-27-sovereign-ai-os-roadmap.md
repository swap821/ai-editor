Sovereign AI-OS Transformation Roadmap v1.2 — FINAL

AI Editor → Governed Hybrid Sovereign AI Operating Runtime

Official Implementation Specification for AI Council
Council: Claude Code | OpenAI Codex | Moonshot AI Kimi
Repository: swap821/ai-editor
Branch: council-runtime-v01
Locked: 2026-06-27
Primary Environment: Windows laptop, FastAPI backend, Ollama local-first, optional cloud intelligence
Academic Context: BCA capstone / internship-grade standout project
Core Philosophy: AI is not trusted. The system is trusted.

⸻

0. Immutable North-Star

The Council is permanent. The workers are temporary. The King is sovereign. The colony evolves.

This project is not a chatbot.
This project is not a Jarvis clone.
This project is not a normal AI coding assistant.

It is a local-first, hybrid-capable Sovereign AI-OS runtime where:

* The King is the human user and final authority.
* The Queen Council is the permanent governance layer.
* The Mission Contract is the law.
* The Workers are temporary bounded execution units.
* The Testing Queen verifies reality.
* The Run Ledger records evidence.
* The King Report distills truth for approval.
* The Reflection / Pheromone system evolves memory and policy.
* Cloud models may assist reasoning, but they never receive authority.
* No AI agent has absolute power.

The transformation is not greenfield.

It is topology surgery.

Current topology:

Human → ToolAgent → Security Gate → Execute → Raw Output

Target topology:

Human → Council → Mission Contract → Worker → Verify → Run Ledger → King Report → Human

Hybrid sovereignty principle:

Local-first does not mean cloud-never.
It means local authority is never surrendered.
Cloud models may assist reasoning.
They may not bypass Mission Contracts.
They may not access secrets directly.
They may not execute tools directly.
They may not approve themselves.
They may not override the King.

⸻

1. Current Repo Diagnosis

The repository already has strong organs.

aios/security/gateway.py       → deterministic GREEN/YELLOW/RED classifier
aios/core/executor.py          → scope-constrained, audited, shell=False command execution
aios/core/verifier.py          → evidence-based verification
aios/core/approvals.py         → server-issued, expiring, single-use approvals
aios/core/self_apply.py        → snapshot, audit-before-write, verify, rollback pattern
aios/memory/                   → SQLite/FAISS memory and skill memory
aios/agents/tool_agent.py      → current monolithic persistent tool-loop agent
aios/agents/swarm.py           → existing swarm/caste logic
frontend/src/superbrain/       → GAGOS 3D brain UI

The problem is not lack of intelligence.

The problem is lack of constitutional runtime architecture.

The existing modules must be wrapped and governed, not rewritten.

⸻

2. Foundation Lock

Before building the Council Runtime, protect what already works.

Create branch:

git checkout -b council-runtime-v01

Create:

FOUNDATION_LOCK.md

Content:

# Foundation Lock
The existing security gateway, executor, verifier, approvals, audit ledger, and self-apply engine are foundation modules.
Council Runtime v0.1 wraps them. It does not rewrite them.
## Protected Modules
- aios/security/*
- aios/core/executor.py
- aios/core/approvals.py
- aios/core/verifier.py
- aios/core/self_apply.py
Any change to these files requires explicit human approval and a written reason.

Hard rule:

Do not refactor the foundation while building Council Runtime v0.1.

⸻

3. Five Atomic Runtime Schemas

Create:

aios/runtime/contracts.py

Rules:

- All shared runtime schemas live in contracts.py.
- Use Field(default_factory=...) for all lists and dicts.
- No mutable defaults.
- Schemas are frozen for v0.1.
- Breaking changes require version bump.

3.1 MissionContract

from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field
RiskLevel = Literal["GREEN", "YELLOW", "RED"]
WorkerStatus = Literal[
    "completed",
    "failed",
    "timeout",
    "blocked",
    "contract_violation",
    "approval_denied",
    "awaiting_approval",
    "killed",
]
class MissionContract(BaseModel):
    version: str = "v0.1"
    mission_id: str
    parent_mission_id: str | None = None
    goal: str
    worker_type: str
    created_by: str
    priority: int = 0
    risk_level: RiskLevel = "YELLOW"
    requires_approval: bool = True
    workspace_root: str
    snapshot_id: str | None = None
    allowed_files: list[str] = Field(default_factory=list)
    forbidden_files: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    timeout_seconds: int = 600
    max_steps: int = 12
    verification_commands: list[str] = Field(default_factory=list)
    pheromone_context: list[str] = Field(default_factory=list)
    required_output: list[str] = Field(default_factory=lambda: [
        "summary",
        "files_touched",
        "diff",
        "verification_result",
        "risk_after",
        "rollback_id",
    ])
    metadata: dict[str, Any] = Field(default_factory=dict)

3.2 WorkerResult

class WorkerResult(BaseModel):
    mission_id: str
    worker_id: str
    status: WorkerStatus
    summary: str = ""
    files_touched: list[str] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    risk_after: RiskLevel
    rollback_id: str | None = None
    next_recommendation: str = ""
    council_verdicts_applied: list[dict[str, Any]] = Field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    started_at: str
    ended_at: str

3.3 QueenVerdict

class QueenVerdict(BaseModel):
    queen: str
    verdict: Literal["allow", "allow_with_approval", "deny", "defer"]
    risk: RiskLevel
    reason: str
    constraints: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

3.4 RunLedger

class RunLedger(BaseModel):
    mission_id: str
    mission: str
    risk_before: RiskLevel
    risk_after: RiskLevel
    contract: MissionContract
    workers_created: list[str] = Field(default_factory=list)
    files_allowed: list[str] = Field(default_factory=list)
    files_touched: list[str] = Field(default_factory=list)
    blocked_attempts: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    verification: dict[str, Any] = Field(default_factory=dict)
    council_verdicts: list[QueenVerdict] = Field(default_factory=list)
    snapshot_id: str | None = None
    rollback_id: str | None = None
    status: str
    created_at: str
    completed_at: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)

3.5 KingReport

class KingReport(BaseModel):
    mission_id: str
    mission: str
    status: Literal[
        "awaiting_approval",
        "completed",
        "failed",
        "rolled_back",
        "needs_revision",
    ]
    council_summary: dict[str, Any] = Field(default_factory=dict)
    recommendation: Literal[
        "approve",
        "reject",
        "revise",
        "rollback",
        "observe",
    ]
    risk: RiskLevel
    files: list[str] = Field(default_factory=list)
    verification_result: dict[str, Any] = Field(default_factory=dict)
    approval_needed: bool
    rollback_available: bool
    rollback_id: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    human_summary: str

⸻

4. Phase 0 — Schema Lock + Skeleton

Goal

Create the runtime / council / memory / policy skeleton and freeze v0.1 schemas.

Files to create

aios/runtime/__init__.py
aios/runtime/contracts.py
aios/runtime/backends.py
aios/runtime/worker_api.py
aios/runtime/worker_entry.py
aios/runtime/spawner.py
aios/runtime/run_ledger.py
aios/runtime/king_report.py
aios/runtime/snapshots.py
aios/runtime/leases.py
aios/runtime/intelligence_gateway.py
aios/runtime/budget_guard.py
aios/runtime/secret_policy.py
aios/council/__init__.py
aios/council/queen_verdict.py
aios/council/council_orchestrator.py
aios/council/service_definitions.py
aios/council/queens/__init__.py
aios/memory/pheromones.py
aios/policy/constitution.py
aios/policy/policy_evolution.py

Success criteria

This import must work:

from aios.runtime.contracts import (
    MissionContract,
    WorkerResult,
    QueenVerdict,
    RunLedger,
    KingReport,
)

Malformed contracts must fail Pydantic validation.

Valid contracts must pass with Field(default_factory=...) defaults.

⸻

5. Phase 1A — Deterministic Worker Birth

Goal

Prove the worker lifecycle without AI complexity.

No Ollama.
No cloud.
No LLM.

First prove:

MissionContract
→ WorkerSpawner
→ ControlledSubprocessBackend
→ WorkerRuntime API
→ WorkerResult
→ RunLedger
→ KingReport
→ worker death

This is the first heartbeat.

⸻

6. WorkerBackend Abstraction

Create:

aios/runtime/backends.py
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal
from aios.runtime.contracts import MissionContract, WorkerResult
@dataclass
class WorkerHandle:
    worker_id: str
    mission_id: str
    backend: str
    pid: int | None = None
    result_path: str | None = None
    status: Literal[
        "born",
        "running",
        "awaiting_approval",
        "dead",
        "killed",
    ] = "born"
class WorkerBackend(ABC):
    @abstractmethod
    async def spawn(self, contract: MissionContract) -> WorkerHandle:
        ...
    @abstractmethod
    async def reap(self, handle: WorkerHandle) -> WorkerResult:
        ...
    @abstractmethod
    async def kill(self, handle: WorkerHandle, reason: str) -> None:
        ...
class ControlledSubprocessBackend(WorkerBackend):
    """
    v0.1 backend.
    Policy isolation only.
    Not a real OS security sandbox.
    Uses:
    - subprocess
    - shell=False
    - restricted environment
    - timeout
    - WorkerRuntime API
    """

Reason:

WorkerSpawner must be backend-agnostic from day one.
Docker, WSL2, Git Worktree, and future backends must become plugin swaps, not rewrites.

⸻

7. WorkerRuntime API

Create:

aios/runtime/worker_api.py

The worker must not touch files directly.

It must act through:

class WorkerRuntime:
    def read_file(self, path: str) -> str: ...
    def write_file(self, path: str, content: str) -> None: ...
    def run_command(self, command: list[str]) -> dict: ...
    def request_approval(self, action: str, reason: str) -> bool: ...
    def request_plan(self, prompt: str, allow_cloud: bool = False) -> str: ...
    def emit_evidence(self, data: dict) -> None: ...
    def finish(self, result: WorkerResult) -> None: ...

Every method must enforce MissionContract.

Rules:

- path must resolve inside workspace_root
- path must not match forbidden_files
- path must match allowed_files
- tool must be in allowed_tools
- tool must not be in forbidden_tools
- max_steps must be enforced
- all blocked attempts must be recorded
- all writes must be recorded
- all evidence must be saved
- cloud reasoning may return plans, but never execute actions

Important limitation:

WorkerRuntime is a policy layer, not a true OS security boundary.

That is acceptable for v0.1.

True sandboxing comes later.

⸻

8. Deterministic Worker Entry

Create:

aios/runtime/worker_entry.py

First worker must be deterministic.

It should:

1. Load MissionContract from JSON path.
2. Initialize WorkerRuntime.
3. Try to read a forbidden backend path.
4. Confirm WorkerRuntime blocks it.
5. Read allowed Login.jsx.
6. Append harmless comment.
7. Write allowed Login.jsx.
8. Run verification command if allowed.
9. Write WorkerResult.
10. Exit.

First mission:

Goal:
Append a harmless comment to Login.jsx.
Allowed:
frontend/src/pages/Login.jsx
Forbidden:
backend/
.env
aios/security/
package.json
Allowed tools:
read_file
write_file
run_command
Verification:
npm run build

Expected evidence:

Forbidden backend access was blocked.
Only allowed frontend file was touched.
Verification ran.
Worker died.

This proves the law is real.

⸻

9. WorkerSpawner

Create:

aios/runtime/spawner.py

Spawner responsibilities:

1. Validate MissionContract.
2. Create worker_id.
3. Create snapshot_id through SnapshotManager.
4. Seal contract by filling snapshot_id.
5. Select WorkerBackend.
6. Spawn worker.
7. Enforce timeout.
8. Detect approval requests.
9. Reap worker.
10. Validate WorkerResult.
11. Write RunLedger.
12. Generate KingReport.
13. Ensure worker is dead.

Hard separation:

Spawner must not think.
Worker must not govern.
Contract is the law.

⸻

10. Approval Pause Protocol

Use file-based IPC for v0.1 because it is Windows-friendly.

When worker calls:

runtime.request_approval(action, reason)

WorkerRuntime writes:

missions/{mission_id}/approvals/{request_id}.request.json

Then WorkerRuntime waits for:

missions/{mission_id}/approvals/{request_id}.response.json

Spawner watches the approval directory.

When request appears:

1. Spawner updates RunLedger status to awaiting_approval.
2. Backend exposes approval request through API.
3. Minimal UI shows Approve / Reject.
4. King clicks.
5. Backend writes response JSON.
6. WorkerRuntime unblocks.
7. Worker continues or exits approval_denied.

Do not overbuild this in v0.1.

Later replace with SQLite event queue or WebSocket.

⸻

11. Phase 1B — Hybrid Intelligence Worker Birth

Goal

After deterministic worker birth works, add reasoning.

The worker still cannot execute freely.

Cloud/local intelligence can only produce a plan.

Execution still goes through WorkerRuntime.

Cloud can provide intelligence.
Cloud cannot provide authority.

The worker now:

1. Loads MissionContract.
2. Initializes WorkerRuntime.
3. Calls WorkerRuntime.request_plan().
4. WorkerRuntime sends request to IntelligenceGateway.
5. IntelligenceGateway chooses local Ollama or cloud provider.
6. Plan is returned.
7. Worker executes the plan only through WorkerRuntime methods.
8. Forbidden actions are blocked.
9. Worker writes WorkerResult.
10. Worker dies.

Mission:

Improve login page without changing backend logic.

Allowed:

frontend/src/pages/Login.jsx
frontend/src/styles/auth.css

Forbidden:

backend/
.env
aios/security/
package.json

Verification:

npm run build

Success:

Model creates plan.
Runtime enforces law.
Forbidden actions are blocked.
Build passes.
Worker dies.

⸻

12. Intelligence Gateway

Create:

aios/runtime/intelligence_gateway.py

Purpose:

Route reasoning requests to local or cloud models without giving workers direct access to keys, credentials, provider SDKs, or execution authority.

Core rule:

Workers do not call OpenAI / Anthropic / Gemini directly.
Workers ask WorkerRuntime for reasoning.
WorkerRuntime asks IntelligenceGateway.
IntelligenceGateway applies privacy, budget, routing, and fallback rules.

Suggested schemas:

class IntelligenceRequest(BaseModel):
    mission_id: str
    worker_id: str
    purpose: Literal["plan", "summarize", "reflect", "repair"]
    prompt: str
    risk: RiskLevel
    allow_cloud: bool = False
    max_tokens: int = 1500
    timeout_seconds: int = 20
class IntelligenceResponse(BaseModel):
    provider: str
    model: str
    used_cloud: bool
    text: str
    cost_estimate: float | None = None
    fallback_used: bool = False

Routing policy:

GREEN + non-sensitive → cloud allowed if budget allows
YELLOW → cloud only if King/session policy allows
RED → local only or deny
Secrets detected → local only or deny
Source code with sensitive files → local only unless explicitly approved

Fallback policy:

Try preferred provider.
If timeout / error / budget exceeded:
    fallback to local Ollama.
If local also fails:
    mission status = failed.
    KingReport recommendation = revise.

⸻

13. Secret Policy

Create:

aios/runtime/secret_policy.py

Rules:

Cloud API keys never enter worker subprocess environment.
Workers never see OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, AWS keys, tokens, secrets, credentials, or auth values.
Secrets are never written to RunLedger, WorkerResult, KingReport, stdout, stderr, or UI.

Worker sees:

request_plan(...)

Worker never sees:

OPENAI_API_KEY
ANTHROPIC_API_KEY
GEMINI_API_KEY
AWS_ACCESS_KEY
AWS_SECRET_ACCESS_KEY

⸻

14. Budget Guard

Create:

aios/runtime/budget_guard.py

Minimum controls:

daily_cloud_budget
mission_cloud_budget
max_cloud_calls_per_mission
max_tokens_per_request
max_total_tokens_per_mission
deny_when_budget_exceeded

For v0.1, store policy inside MissionContract.metadata:

metadata={
    "model_policy": {
        "mode": "hybrid",
        "allow_cloud": True,
        "max_cloud_calls": 3,
        "max_tokens_total": 6000,
        "fallback": "local_ollama"
    }
}

Hard rule:

Budget exceeded = cloud denied.
Mission falls back to local or fails gracefully.

⸻

15. Phase 2 — Simulated Council Loop

Goal

Wrap existing modules as Queen-like classes.

Queens are stateful wrappers, not long-lived services yet.

Loop:

King
↓
Planner Queen Stub
↓
Security Queen Wrapper
↓
Memory Queen Wrapper
↓
MissionContract
↓
WorkerSpawner
↓
Testing Queen Wrapper
↓
RunLedger
↓
KingReport

Create:

aios/council/queen_verdict.py
aios/council/council_orchestrator.py
aios/council/queens/security.py
aios/council/queens/testing.py
aios/council/queens/planner.py
aios/council/queens/memory.py

Queen mapping:

Security Queen → wrap aios/security/gateway.py
Testing Queen  → wrap aios/core/verifier.py
Memory Queen   → wrap aios/memory/*
Planner Queen  → create MissionContract draft, may use IntelligenceGateway
Tool Queen     → wrap aios/core/executor.py later

KingReport is mandatory here.

If the backend cannot generate a clean KingReport, the Council abstraction is fake.

Success:

One mission completes through CouncilOrchestrator.
Security Queen returns verdict.
Worker runs under MissionContract.
Testing Queen verifies.
RunLedger records truth.
KingReport recommends approve/reject/revise.

⸻

16. Minimal Dashboard Starts in Phase 2

Do not wait until the end.

Create a minimal, ugly, useful React panel.

It must show:

Mission
Risk
Council verdicts
Allowed files
Files touched
Blocked attempts
Verification result
Rollback ID
Approve / Reject
Cloud/local model used
Estimated cost
Fallback used

No 3D polish yet.

GAGOS brain stays, but dashboard becomes the command center.

⸻

17. Phase 3A — Stateful Queen Wrappers

Goal

Every Queen verdict becomes durable and queryable.

Create:

aios/council/council_state.py

Tables:

CREATE TABLE queen_verdicts (
    id INTEGER PRIMARY KEY,
    mission_id TEXT NOT NULL,
    queen_name TEXT NOT NULL,
    verdict TEXT NOT NULL,
    risk TEXT NOT NULL,
    reason TEXT,
    constraints_json TEXT,
    confidence REAL,
    created_at TEXT NOT NULL
);
CREATE TABLE council_events (
    id INTEGER PRIMARY KEY,
    mission_id TEXT,
    queen_name TEXT,
    event_type TEXT,
    payload_json TEXT,
    risk TEXT,
    snapshot_id TEXT,
    created_at TEXT NOT NULL
);

Success:

All Queen verdicts are persisted.
Mission deliberation can be replayed.
Council events include snapshot_id.

⸻

18. Phase 3B — Runtime Queen Services

Goal

Queens become long-lived runtime services.

Each Queen gets:

name
responsibility
input schema
QueenVerdict output
state
message inbox
failure behavior

Service registry:

QUEEN_SERVICES = {
    "planner": PlannerQueenService,
    "security": SecurityQueenService,
    "memory": MemoryQueenService,
    "testing": TestingQueenService,
    "reflection": ReflectionQueenService,
    "worker_factory": WorkerFactoryQueenService,
    "health": HealthQueenService,
    "report": ReportQueenService,
}

Success:

CouncilOrchestrator is top-level authority.
ToolAgent is no longer the brain.
Queens deliberate before worker spawn.

ToolAgent may survive as a worker implementation detail.

It cannot remain the sovereign brain.

⸻

19. Phase 4 — Pheromone Memory

Create:

aios/memory/pheromones.py

PheromoneTrail fields:

pheromone_id
parent_pheromone_id
mission_signature
goal_pattern
worker_type
allowed_files_pattern
tool_sequence
outcome
confidence
risk
reuse_when
avoid_when
success_count
failure_count
last_used_at
decay_score
created_at
updated_at
evidence_mission_ids

Before worker spawn:

Memory Queen retrieves similar successful trails.
Memory Queen retrieves similar failed trails.
reuse_when and avoid_when are injected into MissionContract.pheromone_context.
Old trails decay.
Repeated failures weaken trails.
Verified successes strengthen trails.

Success:

A second similar mission behaves better because the first verified trail is injected.

⸻

20. Phase 5 — Live Pheromone Surface + Git Worktree Swarm

Git Worktrees belong here, not Phase 9.

They solve parallel worker workspace conflicts.

Create:

aios/runtime/live_surface.py

LiveSurface:

id
mission_id
worker_id
kind
payload
strength
expires_at
created_at

Example:

Worker A discovers file locked.
Worker A deposits live pheromone.
Worker B senses it and avoids same path.

Add Git Worktree support:

UI Worker   → worktree A
Test Worker → worktree B
Docs Worker → worktree C

Success:

Multiple workers coordinate indirectly through live surface.
Parallel workers do not overwrite each other.

⸻

21. Phase 6 — Universal Healing

Generalize the proven self_apply.py pattern.

Create:

aios/runtime/rollback_registry.py
aios/runtime/snapshots.py

Rules:

Every mutation has snapshot_id.
Every mission has rollback_id.
Verification failure triggers retry or rollback proposal.
Rollback preserves history.
No destructive git reset/rebase as final recovery path.

Rollback modes:

Before King approval:
discard worktree or restore snapshot.
After King approval:
restore old file state and create rollback commit.

Success:

Every approved mission can be undone.
Rollback is shown in KingReport.

⸻

22. Phase 7 — Policy Evolution

Create:

aios/policy/constitution.py
aios/policy/policy_evolution.py

The colony can propose new laws, but only the King approves them.

PolicyProposal:

proposal_id
reason
evidence_mission_ids
current_rule
proposed_rule
risk
created_by
requires_king_approval
status

Example:

After repeated UI missions try package.json:
Reflection Queen proposes package.json forbidden for UI workers.
After repeated frontend missions try backend/:
Reflection Queen proposes backend/ forbidden for frontend_ui_worker.

Success:

Reflection Queen proposes rule.
King approves/rejects.
Future MissionContracts include approved rule.

⸻

23. Phase 8 — Mature Sovereignty Dashboard

Backend endpoints:

GET  /api/v1/council/missions
GET  /api/v1/council/missions/{id}
GET  /api/v1/council/reports/{id}
POST /api/v1/council/approve
POST /api/v1/council/reject
POST /api/v1/council/rollback
GET  /api/v1/colony/health

UI panels:

Pending Missions
Council Verdicts
Mission Contract
Worker Status
Blocked Attempts
Verification Evidence
Rollback Path
Pheromone Updates
King Decision
Model Routing
Cloud Budget
Fallback Status

GAGOS 3D brain becomes runtime visualization:

Green pulse  → verification passed
Yellow pulse → awaiting approval
Red pulse    → blocked action
Blue trail   → pheromone update
Purple pulse → cloud reasoning used
Worker mote  → active worker

⸻

24. Phase 9 — Hardened Isolation

Do not block earlier phases on this.

Backend levels:

v0.1 → ControlledSubprocessBackend
v0.5 → GitWorktreeBackend
v0.9 → DockerBackend
v1.1 → WSL2/Linux/MicroVM backend

DockerBackend should support:

no network
read-only root
single scoped read-write mount
dropped capabilities
no-new-privileges
PID/memory/CPU limits
non-root user
tmpfs /tmp

Success:

Worker backend can be changed without changing MissionContract, WorkerResult, RunLedger, or KingReport.

⸻

25. Phase 10 — Sovereign AI-OS v1.0

v1.0 means:

King gives real project goal.
Council deliberates.
MissionContract is created.
Temporary workers are spawned.
Workers act only through contract.
Security blocks illegal actions.
Testing Queen verifies reality.
Reflection updates pheromones.
Rollback is available for every mutation.
Policy evolves with King approval.
Cloud can assist intelligence, but never authority.
King receives clean report.
Everything is logged.
No agent has absolute power.

This is the working AI-OS of the current vision.

Not AGI.
Not Jarvis.
Not enterprise fantasy.

A governed, verifiable, reversible, memory-evolving local AI-OS runtime.

⸻

26. 30-Day MVP Scope

The full roadmap remains v1.0.

The 30-day sprint is smaller.

In 30-day scope

Phase 0       → Foundation Lock + schemas
Phase 1A      → Deterministic Worker Birth
Phase 1B      → Hybrid Intelligence Worker Birth
Phase 2       → Simulated Council wrappers
Phase 3A-lite → SQLite verdict / event logs
Dashboard-lite → KingReport panel with approve/reject

Not in 30-day scope

Runtime Queen services
Git Worktree swarm
Live pheromone surface
Universal healing
Policy evolution
Docker backend
Mature GAGOS integration

These are future / advanced / v1.0 scope.

⸻

27. Revised 30-Day Build Plan

Days 1–2: Phase 0

Create branch
FOUNDATION_LOCK.md
contracts.py
stubs
schema tests

Days 3–6: Phase 1A

WorkerBackend ABC
ControlledSubprocessBackend
WorkerRuntime API
deterministic worker_entry
RunLedger
KingReport
forbidden backend access test

Days 7–10: Phase 1B Hybrid

IntelligenceGateway
local Ollama route
optional cloud route
SecretPolicy
BudgetGuard
fallback to local route
cloud output treated as plan only

Days 11–15: Phase 2

PlannerQueen wrapper
SecurityQueen wrapper
TestingQueen wrapper
MemoryQueen basic wrapper
CouncilOrchestrator
full loop

Days 16–18: Phase 3A-lite

queen_verdicts table
council_events table
snapshot_id in event logs
mission replay support

Days 19–23: Dashboard-lite

KingReport endpoint
Pending mission panel
Approve / Reject
Risk
Files touched
Blocked attempts
Verification result
Cloud/local model used
Estimated cost
Fallback used

Days 24–30: Proof + polish

demo mission
tests
Windows subprocess cleanup
documentation
3–5 minute demo script
capstone explanation

⸻

28. No-Distraction Build Order

1. Create council-runtime-v01 branch
2. Write FOUNDATION_LOCK.md
3. Add aios/runtime/contracts.py
4. Add aios/runtime/backends.py
5. Add aios/runtime/worker_api.py
6. Add deterministic aios/runtime/worker_entry.py
7. Add aios/runtime/spawner.py
8. Add aios/runtime/snapshots.py
9. Add aios/runtime/run_ledger.py
10. Add aios/runtime/king_report.py
11. Run first deterministic mission
12. Add deliberate forbidden-access test
13. Add IntelligenceGateway
14. Add SecretPolicy
15. Add BudgetGuard
16. Add hybrid worker mode
17. Run first hybrid mission
18. Add council Queen wrappers
19. Add CouncilOrchestrator
20. Add KingReport endpoint
21. Add minimal dashboard
22. Run first full sovereign loop
23. Add council SQLite verdict/event logs
24. Add Memory Queen pheromone retrieval
25. Add Reflection Queen update
26. Add live pheromone surface
27. Add Git Worktree backend
28. Add universal rollback registry
29. Add policy evolution
30. Add mature dashboard
31. Add Docker backend
32. Connect GAGOS brain to runtime events
33. Release v1.0 candidate

⸻

29. 30-Day Proof

By Day 30, the system must demonstrate:

Improve the login page without changing backend logic.

The proof must show:

1. Planner Queen creates MissionContract.
2. Security Queen classifies risk.
3. Worker is born.
4. Worker requests a plan through IntelligenceGateway.
5. Local or cloud model returns a plan.
6. Worker attempts backend access.
7. WorkerRuntime blocks backend access.
8. Worker edits only allowed frontend files.
9. Testing Queen verifies build.
10. RunLedger records truth.
11. KingReport summarizes evidence.
12. Dashboard shows approve/reject.
13. Worker dies.
14. King approves from dashboard.

This is not a demo.

This is proof of architecture.

⸻

30. Anti-Patterns

Do not:

rewrite executor
rewrite security gateway
rewrite verifier
make ToolAgent top-level authority
make workers persistent
skip KingReport
auto-approve YELLOW actions
give cloud models execution authority
put API keys in worker subprocess env
log secrets in RunLedger or UI
add Firecracker now
add LangGraph now
add MITM proxy now
add graph database now
add more cloud providers now
add more 3D UI before backend works

ToolAgent can survive as implementation detail.

It cannot remain the sovereign brain.

⸻

31. Council Role Assignment

Kimi

Role:

Architect / critic / topology guard

Responsibilities:

review architecture
detect overengineering
detect topology mistakes
protect north-star
review roadmap drift

Kimi must not write huge code blindly.

Claude Code

Role:

primary implementation worker

Responsibilities:

create files
write code
run tests
follow build order
avoid protected modules
produce diffs
stop on risky actions

Claude Code must not rewrite foundation modules.

Codex

Role:

verifier / reviewer / test hardener

Responsibilities:

review generated code
add tests
find edge cases
verify contract enforcement
check Windows compatibility
check subprocess cleanup
check secret leakage
check cloud budget guard

Codex must focus on correctness, not new features.

Human King

Role:

sovereign authority

Responsibilities:

approve YELLOW actions
reject risky rewrites
choose when to merge
approve cloud usage policy
approve policy changes
protect project scope

The King is final authority.

⸻

32. Final Implementation Command to Council

All builder agents must follow this:

Do not redesign the project.
Do not rewrite foundation modules.
Do not add new features outside the roadmap.
Implement Council Runtime v0.1 first.
The first deliverable is Controlled Worker Birth:
MissionContract
→ WorkerBackend
→ WorkerRuntime API
→ deterministic worker
→ WorkerResult
→ RunLedger
→ KingReport
→ worker death
Only after deterministic worker birth passes, add Hybrid Intelligence Worker Birth.
Cloud/local models may assist reasoning.
They may not execute actions.
They may not bypass MissionContract.
They may not approve themselves.
They may not access secrets.
They may not override the King.
Only after hybrid worker birth passes, build simulated council wrappers.

⸻

33. First Command for Claude Code

Give this exact command first:

Create branch council-runtime-v01.
Implement Phase 0 only.
Create:
1. FOUNDATION_LOCK.md
2. aios/runtime/contracts.py
3. empty stubs for runtime/council/memory/policy files listed in the roadmap
Rules:
- Do not modify aios/security/*
- Do not modify aios/core/executor.py
- Do not modify aios/core/approvals.py
- Do not modify aios/core/verifier.py
- Do not modify aios/core/self_apply.py
- Do not modify ToolAgent yet
- Do not implement WorkerSpawner yet
- Do not add Ollama yet
- Do not add cloud integration yet
- Do not add UI yet
After contracts import successfully and basic Pydantic validation tests pass, stop and report.

⸻

34. First Command for Codex

Give this after Claude completes Phase 0:

Review Phase 0 implementation.
Check:
1. Protected modules were not modified.
2. contracts.py has no mutable defaults.
3. MissionContract, WorkerResult, QueenVerdict, RunLedger, KingReport import correctly.
4. Invalid contracts fail validation.
5. Stubs do not contain hidden implementation beyond Phase 0.
6. Windows compatibility is not broken.
7. No secrets, API keys, or credentials are introduced.
8. No unnecessary dependencies are added.
Do not add new features.
Only review and add minimal tests if needed.

⸻

35. Final Truth

You are not missing intelligence.
You are missing the constitutional runtime layer.

The transformation is:

security-gated AI agent
↓
governed hybrid sovereign AI operating runtime

The first worker birth is the first heartbeat of the AI-OS.

The Council is permanent.
The workers are temporary.
The King is sovereign.
The colony evolves.

Build the first heartbeat.