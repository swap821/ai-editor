# CAPABILITY HARMONY MAP

> Living source-of-truth: how well the **product frontend** surfaces the **backend's real capabilities**. Audience: the operator + future coding agents.
> **Verified** against source on 2026-06-14: SSE parsers (`App.jsx` `processEvent`, `superbrain/lib/aiosAdapter.ts`), the 34 REST routes in `aios/api/main.py`, and the 9 SSE wire names. Endpoint callers grep-confirmed in `frontend/src`.
>
> **Context (2026-06-14):** the backend is live-verified and working; the product frontend is still largely the "demo" scaffold built before the operator's canon design was finalized. This map drives the **frontend renovation** to 100% backend harmony. The operator's CORE DESIGN (the voyaging-superbrain soul, the canon scene/brain/GLB assets, the sovereignty row, the aesthetic tokens) is **FROZEN, inviolable law** — renovation is additive and conforms to it; it never redesigns it. See [[frontend-harmony-direction]] and [[fidelity-is-sacred-ui-laws]].

**Status legend**
- **SURFACED** — visibly rendered to the operator.
- **PARTIAL** — some signal reaches the UI but it is lossy/incomplete (truncated, narration-only, classic-only, or buried).
- **ABSENT** — backend capability exists, no UI calls or shows it.
- **INFRA** — infrastructure / replay / liveness; no hero UI needed.

**Guiding principles**
- **Additive ports only** — new surfaces are new PORTs in the superbrain nervous system; never redesign or degrade existing canon.
- **Observability before operability** — *read/show* a capability before adding *act/control* UI for it. Earlier P0s are observers, not buttons.
- **FIDELITY is sacred** — parity proven in HIS browser, his assets untouched, before/after screenshots, canon tag + goldens before visual work.
- **Lab-first** — build in the superbrain lab (`GAG demo/gag-orchestrator`), port via tripwired `npm run port`; product `src/superbrain/*` is byte-identical-to-lab.

Status reflects the **product (superbrain) default face** first; classic-only coverage is called out because classic is the legacy/fallback face.

---

## ⚠ Known robustness defect (P0, 2026-06-14) — approval surface desync

A live run that pauses on a YELLOW write can leave the operator **stuck**: the hold *text* ("Awaiting operator approval") is set by the parent `WorkspaceCanvas.tsx:184` from `result.paused`, while the actionable `<ApprovalPanel>` (`SuperbrainHUD.tsx:1039`) is gated on the HUD's *local* `pendingApproval`, populated **only** by the transient `approval-required` bus event (`:768`) + a null mount-seed (`:578`). The adapter's `pendingApproval` (and the server token) persist and stay valid (`aiosAdapter.ts:250`), but if the bus event doesn't reconcile into HUD state, the panel never renders → no AUTHORIZE/REJECT → the run hangs. **Fix:** drive the panel from the persisted adapter truth reconciled by the same `result.paused` signal that sets the text (single source of truth). Renovation P0.

---

## Cognition & Routing

| Capability | Backend (event/endpoint) | Frontend status | Proposed surface (FIDELITY-additive) | Priority |
|---|---|---|---|---|
| Active brain / per-turn route | `route` (SSE) | **SURFACED** — HUD sovereignty-row BRAIN badge + privacy dot (superbrain); classic title-bar pill | Keep. Optional: failover flash on the BRAIN PORT when route re-announces mid-loop | — |
| Live tool-loop steps | `step` (SSE: tool_call/result/blocked) | **SURFACED** — AGENT MESH cards + TERMINAL LOG + objective sub-steps | Keep | — |
| Streamed answer text | `text_chunk` (SSE) | **PARTIAL** — superbrain drops the verbatim answer (only a truncated SYNTHESIS COMPLETE preview); full bubble is classic-only | **ANSWER PORT**: a dockable console rendering the verbatim streamed reply | **P0** |
| Generated code artifact | `code` (SSE) | **PARTIAL** — both faces discard the body (classic no-ops line 763; superbrain emits only "CODE EMITTED") | **CODE PORT**: render the fenced block in a read-only ForgePorts EDITOR pane (never overwrites the operator's file) | **P1** |
| Fatal turn fault | `error` (SSE) | **SURFACED** — superbrain "COGNITION FAULT"; classic error bubble | Keep | — |
| Turn complete | `done` (SSE) | **SURFACED** — superbrain "SYNTHESIS COMPLETE"; classic settles message | Keep | INFRA |
| Run the agentic turn | `POST /api/generate` | **SURFACED** — primary driver of both faces | Keep | INFRA |
| Swarm / role-pass caste narration | `step` w/ `role` tag | **SURFACED** — superbrain caste narration on the mesh | Keep; consider per-caste mesh lanes | P2 |

## Memory

| Capability | Backend (event/endpoint) | Frontend status | Proposed surface | Priority |
|---|---|---|---|---|
| Synthesized recall pre-steps | `step` (id `memory-recall`/`lesson-recall`/`skill-recall`) | **PARTIAL** — generic steps; not distinguished as *recall* | Flag recall steps in the KNOWLEDGE INTAKE Memory row ("recalled N lessons/facts") | P2 |
| Hybrid semantic search (L3) | `POST /api/v1/memory/search` | **ABSENT** | **MEMORY GALAXY PROBE**: search-into-the-galaxy console; scored hits as star-rows | P1 |
| Consolidate verified lessons/facts | `POST /api/v1/memory/consolidate` | **ABSENT** | Operator action on the Memory PORT ("consolidate now") | P2 |
| Promote approved fact | `POST /api/v1/memory/facts` | **ABSENT** | Fact-commit console (shows 409 contradiction) | P2 |
| Reconcile contradictory fact | `POST /api/v1/memory/facts/reconcile` | **ABSENT** | Contradiction-resolution card when `/facts` returns 409 | P2 |

## Learning & Stigmergy

| Capability | Backend (event/endpoint) | Frontend status | Proposed surface | Priority |
|---|---|---|---|---|
| Pheromone / skill-trail map | `GET /api/v1/development/trails` | **SURFACED** — KNOWLEDGE INTAKE rows + sparklines (poll 20s) | Keep | — |
| Development metrics | `GET /api/v1/development/metrics` | **SURFACED** — intake rows + AGENT MESH avg + objective % | Keep | — |
| Procedural skills list | `GET /api/v1/development/skills` | **ABSENT** | **SKILLS PORT**: "verified workflows" readout (goal pattern, success rate, status) | P1 |
| Curriculum tasks + evidence | `GET /api/v1/development/curriculum` | **ABSENT** | **CURRICULUM PORT**: read-only brain-growth ladder (skill/level/pass-fail, held-out) | P1 |
| Define a curriculum task | `POST /api/v1/development/curriculum` | **ABSENT** | Define-only form on the Curriculum PORT | P2 |

## Self-improvement

| Capability | Backend (event/endpoint) | Frontend status | Proposed surface | Priority |
|---|---|---|---|---|
| Earned-autonomy autonomous write | `earned_autonomy` (SSE) | **SURFACED** — "AUTONOMY ⚡N" badge + terminal lines | Keep | — |
| Earned-autonomy ledger | `GET /api/v1/development/autonomy` | **PARTIAL** — polled for ⚡N count only (`aiosAdapter.ts:653`); per-signature evidence/threshold not shown | **AUTONOMY LEDGER PORT**: graduated/revoked signatures, threshold, master switch | **P0** |
| Operator force-revoke autonomy | `POST /api/v1/development/autonomy/revoke` | **ABSENT** | "Pull back to YELLOW" on each granted signature | P2 |
| Self-analysis proposals list | `GET /api/v1/self-analysis/proposals` | **PARTIAL** — classic-only ProposalsPanel; absent from superbrain | **PROPOSALS PORT** in the product HUD | P1 |
| Apply / reject proposal | `POST /api/v1/self-analysis/proposals/{id}/{apply,reject}` | **PARTIAL** — classic-only | Apply/Reject on the Proposals PORT | P2 |
| Reflect on a failure → lesson | `POST /api/v1/reflect` | **ABSENT** (in-loop reflect arrives via `step`) | Optional; low value vs auto-loop | P2 |

## Reasoning & Alignment

| Capability | Backend (event/endpoint) | Frontend status | Proposed surface | Priority |
|---|---|---|---|---|
| Per-turn alignment frame | `alignment` (SSE) | **PARTIAL** — superbrain reduces to one INTENT line; rich panel classic-only | **INTENT PORT**: interpreted intent, ambiguity_action, clarifying_question | P1 |
| Session restore | `POST /api/v1/conversation/session` | **PARTIAL** — classic-only | Wire superbrain mount to restore continuity | P2 |
| Submit / clear corrections | `POST /api/v1/conversation/correction{,/clear}` | **PARTIAL** — classic only | Correction controls on the INTENT PORT (advisory) | P2 |
| Alignment evaluation feed | `GET /api/v1/alignment/evaluation` | **PARTIAL** — classic only | Diagnostic readout on the INTENT PORT | P2 |
| Record alignment feedback | `POST /api/v1/alignment/feedback` | **PARTIAL** — classic only | Feedback control tied to `evaluation.observation_id` | P2 |
| Plan decomposition | `POST /api/v1/plan` | **ABSENT** (in-loop `plan` via `step`) | **PLAN PORT**: task tree (steps/approved/escalate/requires_human) | P1 |

## Security & Trust

| Capability | Backend (event/endpoint) | Frontend status | Proposed surface | Priority |
|---|---|---|---|---|
| YELLOW approval pause + diff | `human_required` (SSE) | **SURFACED but FRAGILE** — ApprovalPanel + ForgePorts PENDING + SHIELD HOLD (see P0 defect above) | Harden (single source of truth) | **P0** |
| Resolve approval | `POST /api/v1/approval/req` | **SURFACED** — reject path; approve replays `/api/generate` | Keep | INFRA |
| Audit hash-chain integrity | `GET /api/v1/audit/verify` | **SURFACED** — SHIELD flips red "TAMPER" (sampled) | Keep | — |
| Deterministic zone classify | `POST /api/v1/security/classify` | **ABSENT** | **ZONE PROBE PORT**: type a command → GREEN/YELLOW/RED + reason | P1 |
| Classify+gate+run a command | `POST /api/v1/execute` | **ABSENT** (`/api/terminal` covers the classic path) | INFRA | INFRA |
| Terminal / Git execution | `POST /api/terminal` | **PARTIAL** — classic only | Optional CONSOLE PORT | P2 |
| Sandbox rollback | `POST /api/v1/rollback` | **ABSENT** | Operator "restore snapshot" on the Forge PORT | P2 |
| Liveness probe | `GET /health` | **SURFACED** — BootSequence kernel version | Keep | INFRA |

## Forge & Workspace

| Capability | Backend (event/endpoint) | Frontend status | Proposed surface | Priority |
|---|---|---|---|---|
| Real on-disk training_ground files | `GET /api/v1/development/workspace` | **PARTIAL** — Monaco EDITOR + PREVIEW, but `?ui=shell` only | Surface the workspace files PORT in the default product HUD | P1 |

## Models

| Capability | Backend (event/endpoint) | Frontend status | Proposed surface | Priority |
|---|---|---|---|---|
| Local (Ollama) availability | `GET /api/v1/models/local` | **PARTIAL** — classic picker only; superbrain hardcodes `modelId:'auto'` | Read-only model readiness in the BRAIN PORT | P2 |
| Bedrock models | `GET /api/v1/models/bedrock` | **PARTIAL** — classic picker only | BRAIN PORT readiness | P2 |
| Gemini (Vertex) models | `GET /api/v1/models/gemini` | **ABSENT** | BRAIN PORT readiness | P2 |
| Auto per-task selection | `GET /api/v1/models/auto` | **PARTIAL** — classic Auto badge only | `by_task` map under the BRAIN badge | P2 |

---

## Infra-only (no hero UI)
- `POST /api/generate` — the turn driver; observed via its SSE frames.
- `done` (SSE) — terminal frame; drives stream-stop + persistence.
- `POST /api/v1/approval/req` — capability resolver; the approval card is the surface.
- `GET /health` — boot liveness (BootSequence).
- `POST /api/v1/execute` — single-command gate/run; redundant with `/api/terminal`.

## Recommended first surfaces (highest-value observability wins)
1. **Harden the approval surface (P0)** — stop live runs hanging (the defect above). Robustness before new ports.
2. **ANSWER PORT (P0, `text_chunk`)** — the default face drops the assistant's verbatim reply; restoring a real conversational console closes the largest perception gap; no new backend.
3. **AUTONOMY LEDGER PORT (P0, `/development/autonomy`)** — turn the ⚡N black box into auditable observability (graduated classes, threshold, revoke).
4. **CURRICULUM PORT (P1, `/development/curriculum`)** — make the marquee learning loop's live brain-growth evidence visible.

Key source paths: `aios/api/main.py` (SSE + 34 routes), `frontend/src/App.jsx` (classic parser; `code` no-op line 763), `frontend/src/superbrain/lib/aiosAdapter.ts` (product SSE/REST/poll), `frontend/src/superbrain/components/ui/SuperbrainHUD.tsx` (primary product render surface).
