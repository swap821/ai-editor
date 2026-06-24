# CAPABILITY HARMONY MAP

> Living source-of-truth: how well the **product frontend** surfaces the **backend's real capabilities**. Audience: the operator + future coding agents.
> **Verified** against source on 2026-06-14: SSE parsers (`App.jsx` `processEvent`, `superbrain/lib/aiosAdapter.ts`), the 34 REST routes in `aios/api/main.py`, and the 9 SSE wire names. Endpoint callers grep-confirmed in `frontend/src`.
>
> **Context (2026-06-14):** the backend is live-verified and working. This map drives the **frontend renovation** to 100% backend harmony. The operator's CORE DESIGN (the voyaging-superbrain soul, the canon scene/brain/GLB assets, the sovereignty row, the aesthetic tokens) is **FROZEN, inviolable law** — renovation is additive and conforms to it; it never redesigns it. See [[frontend-harmony-direction]] and [[fidelity-is-sacred-ui-laws]].
>
> **Renovation status (Waves 0–9, branch `feat/frontend-renovation`):** the additive `OrgansDock` shipped with **10 read-only organs** + the `ApprovalSafetyNet`, lifting the rows below out of ABSENT/PARTIAL. The status columns now read **as-shipped**; act/control endpoints are marked **DEFERRED-AND-DOCUMENTED** (observe-before-operate), never silently dropped. See the *Renovation IA note* near the bottom.

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

## ✅ Resolved: approval surface single-source-of-truth (P0-3, 2026-06-24)

> Original defect description retained below for history. The actionable `<ApprovalPanel>` now binds to the adapter's persisted pending-approval truth via `subscribePendingApproval()` (`SuperbrainHUD.tsx:574-590`), which fires immediately on subscribe and on every change. `approvalHold` and the AUTHORIZE/REJECT panel are therefore driven by the same state; a missed transient `approval-required` bus event can no longer strand a pause. Covered by `frontend/src/superbrain/lib/aiosAdapter.approval.test.ts`.

**Original (2026-06-14) defect — superseded:**
> A live run that pauses on a YELLOW write can leave the operator **stuck**: the hold *text* ("Awaiting operator approval") is set by the parent `WorkspaceCanvas.tsx:184` from `result.paused`, while the actionable `<ApprovalPanel>` (`SuperbrainHUD.tsx:1039`) is gated on the HUD's *local* `pendingApproval`, populated **only** by the transient `approval-required` bus event (`:768`) + a null mount-seed (`:578`). The adapter's `pendingApproval` (and the server token) persist and stay valid (`aiosAdapter.ts:250`), but if the bus event doesn't reconcile into HUD state, the panel never renders → no AUTHORIZE/REJECT → the run hangs. **Fix:** drive the panel from the persisted adapter truth reconciled by the same `result.paused` signal that sets the text (single source of truth). Renovation P0.

---

## Cognition & Routing

| Capability | Backend (event/endpoint) | Frontend status | Proposed surface (FIDELITY-additive) | Priority |
|---|---|---|---|---|
| Active brain / per-turn route | `route` (SSE) | **SURFACED** — HUD sovereignty-row BRAIN badge + privacy dot (superbrain); classic title-bar pill | Keep. Optional: failover flash on the BRAIN PORT when route re-announces mid-loop | — |
| Live tool-loop steps | `step` (SSE: tool_call/result/blocked) | **SURFACED** — AGENT MESH cards + TERMINAL LOG + objective sub-steps | Keep | — |
| Streamed answer text | `text_chunk` (SSE) | **SURFACED** (Wave 5, P0) — Conversation organ renders the verbatim last reply from L2 episodic memory (full, code fences as blocks); unread-answer dot; default `converse` tab | Keep | — |
| Generated code artifact | `code` (SSE) | **SURFACED** — covered without a separate organ: the Conversation organ renders fenced code blocks verbatim, and the ForgePorts shell workspace surfaces real on-disk written files (read-only) | Keep — CODE PORT folded into Conversation + ForgePorts | — |
| Fatal turn fault | `error` (SSE) | **SURFACED** — superbrain "COGNITION FAULT"; classic error bubble | Keep | — |
| Turn complete | `done` (SSE) | **SURFACED** — superbrain "SYNTHESIS COMPLETE"; classic settles message | Keep | INFRA |
| Run the agentic turn | `POST /api/generate` | **SURFACED** — primary driver of both faces | Keep | INFRA |
| Swarm / role-pass caste narration | `step` w/ `role` tag | **SURFACED** — superbrain caste narration on the mesh | Keep; consider per-caste mesh lanes | P2 |

## Memory

| Capability | Backend (event/endpoint) | Frontend status | Proposed surface | Priority |
|---|---|---|---|---|
| Synthesized recall pre-steps | `step` (id `memory-recall`/`lesson-recall`/`skill-recall`) | **PARTIAL** — generic steps; not distinguished as *recall* | Flag recall steps in the KNOWLEDGE INTAKE Memory row ("recalled N lessons/facts") | P2 |
| Hybrid semantic search (L3) | `POST /api/v1/memory/search` | **SURFACED** (Wave 2) — Memory organ: type a query → scored star-rows w/ provenance; honest "No memories matched" empty | Keep | — |
| Consolidate verified lessons/facts | `POST /api/v1/memory/consolidate` | **ABSENT** — *DEFERRED-AND-DOCUMENTED* (observe-before-operate: an act/control, not an observer) | Operator action on the Memory PORT ("consolidate now") | P2 |
| Promote approved fact | `POST /api/v1/memory/facts` | **ABSENT** — *DEFERRED-AND-DOCUMENTED* (act/control) | Fact-commit console (shows 409 contradiction) | P2 |
| Reconcile contradictory fact | `POST /api/v1/memory/facts/reconcile` | **ABSENT** — *DEFERRED-AND-DOCUMENTED* (act/control) | Contradiction-resolution card when `/facts` returns 409 | P2 |

## Learning & Stigmergy

| Capability | Backend (event/endpoint) | Frontend status | Proposed surface | Priority |
|---|---|---|---|---|
| Pheromone / skill-trail map | `GET /api/v1/development/trails` | **SURFACED** — KNOWLEDGE INTAKE rows + sparklines (poll 20s) | Keep | — |
| Development metrics | `GET /api/v1/development/metrics` | **SURFACED** — intake rows + AGENT MESH avg + objective % | Keep | — |
| Procedural skills list | `GET /api/v1/development/skills` | **SURFACED** (Wave 2) — Skills organ: verified workflows + success rate (via adapter `getKnownTrails()` poll); honest empty | Keep | — |
| Curriculum tasks + evidence | `GET /api/v1/development/curriculum` | **SURFACED** (Wave 1) — Growth organ: read-only skill→level→task ladder, held-out pills; honest empty | Keep | — |
| Define a curriculum task | `POST /api/v1/development/curriculum` | **ABSENT** — *DEFERRED-AND-DOCUMENTED* (act/control) | Define-only form on the Curriculum PORT | P2 |

## Self-improvement

| Capability | Backend (event/endpoint) | Frontend status | Proposed surface | Priority |
|---|---|---|---|---|
| Earned-autonomy autonomous write | `earned_autonomy` (SSE) | **SURFACED** — "AUTONOMY ⚡N" badge + terminal lines | Keep | — |
| Earned-autonomy ledger | `GET /api/v1/development/autonomy` | **SURFACED** (Wave 1, P0) — Autonomy organ: earned/probation/revoked rows + `min_successes` threshold + failure_count/timestamps; honest "no earned classes" (feature ships OFF) | Keep | — |
| Operator force-revoke autonomy | `POST /api/v1/development/autonomy/revoke` | **ABSENT** — *DEFERRED-AND-DOCUMENTED* (act/control; observer shipped first) | "Pull back to YELLOW" on each granted signature | P2 |
| Self-analysis proposals list | `GET /api/v1/self-analysis/proposals` | **SURFACED** (Wave 2, observe-only) — Proposals organ in the product HUD: self-analysis fixes w/ diff; honest empty | Keep | — |
| Apply / reject proposal | `POST /api/v1/self-analysis/proposals/{id}/{apply,reject}` | **PARTIAL** — classic-only — *DEFERRED-AND-DOCUMENTED* in the product face (act/control; Proposals organ is observe-only) | Apply/Reject on the Proposals PORT | P2 |
| Reflect on a failure → lesson | `POST /api/v1/reflect` | **ABSENT** (in-loop reflect arrives via `step`) | Optional; low value vs auto-loop | P2 |

## Reasoning & Alignment

| Capability | Backend (event/endpoint) | Frontend status | Proposed surface | Priority |
|---|---|---|---|---|
| Per-turn alignment frame | `alignment` (SSE) | **SURFACED** (Wave 9) — Intent organ: interpreted intent (+ gloss), confidence meter, goal/desired_outcome, ASSUMPTIONS/UNKNOWNS/CONSTRAINTS/DECISIONS, next_action, `CORRECTED` badge; reads the latest `UnderstandingFrame.as_dict()` from `/conversation/session` (`limit:1`) | Keep | — |
| Clarifying question (ambiguity=ask) | `alignment.communication.ambiguity_action` | **SURFACED** (Wave 9) — Intent organ raises the policy-owned `clarifying_question` in a loud truth-state banner above the frame | Keep | — |
| Session restore | `POST /api/v1/conversation/session` | **SURFACED** (Wave 5/9) — Conversation + Intent organs both read this endpoint with the shared session-id resolver | Keep | — |
| Submit / clear corrections | `POST /api/v1/conversation/correction{,/clear}` | **PARTIAL** — classic only — *DEFERRED-AND-DOCUMENTED* in the product face (act/control; Intent organ shows `correction.active` as `CORRECTED` read-only) | Correction controls on the INTENT PORT (advisory) | P2 |
| Alignment evaluation feed | `GET /api/v1/alignment/evaluation` | **PARTIAL** — classic only — *DEFERRED-AND-DOCUMENTED* | Diagnostic readout on the INTENT PORT | P2 |
| Record alignment feedback | `POST /api/v1/alignment/feedback` | **PARTIAL** — classic only — *DEFERRED-AND-DOCUMENTED* (act/control) | Feedback control tied to `evaluation.observation_id` | P2 |
| Plan decomposition | `POST /api/v1/plan` | **SURFACED** (Wave 3) — Plan organ: confidence-gated step tree + AUTO/HUMAN verdict; idle until a goal is submitted | Keep | — |

## Security & Trust

| Capability | Backend (event/endpoint) | Frontend status | Proposed surface | Priority |
|---|---|---|---|---|
| YELLOW approval pause + diff | `human_required` (SSE) | **SURFACED + HARDENED** (Wave 6, P0) — canon ApprovalPanel on the healthy path, plus a deferred ApprovalSafetyNet (z-62, both faces) that surfaces a RESOLVE control if the `approval-required` bus event is missed → no more stuck runs | Keep | — |
| Resolve approval | `POST /api/v1/approval/req` | **SURFACED** — reject path; approve replays `/api/generate` | Keep | INFRA |
| Audit hash-chain integrity | `GET /api/v1/audit/verify` | **SURFACED** — SHIELD flips red "TAMPER" (sampled) | Keep | — |
| Deterministic zone classify | `POST /api/v1/security/classify` | **SURFACED** (Wave 3) — Zone Probe organ: type a command → GREEN/YELLOW/RED + reason; idle until probed | Keep | — |
| Classify+gate+run a command | `POST /api/v1/execute` | **ABSENT** (`/api/terminal` covers the classic path) | INFRA | INFRA |
| Terminal / Git execution | `POST /api/terminal` | **PARTIAL** — classic only — *DEFERRED-AND-DOCUMENTED* (act/control; observe-first) | Optional CONSOLE PORT | P2 |
| Sandbox rollback | `POST /api/v1/rollback` | **ABSENT** — *DEFERRED-AND-DOCUMENTED* (act/control) | Operator "restore snapshot" on the Forge PORT | P2 |
| Liveness probe | `GET /health` | **SURFACED** — BootSequence kernel version | Keep | INFRA |

## Forge & Workspace

| Capability | Backend (event/endpoint) | Frontend status | Proposed surface | Priority |
|---|---|---|---|---|
| Real on-disk training_ground files | `GET /api/v1/development/workspace` | **SURFACED** — the ForgePorts shell workspace (Monaco EDITOR + PREVIEW) renders the mind's REAL written files read-only; this is also where the `code` artifact lands (no separate CODE organ). Still `?ui=shell`-scoped; default-home surfacing is the open follow-up | Keep (shell) | P1 (default-home) |

## Models

| Capability | Backend (event/endpoint) | Frontend status | Proposed surface | Priority |
|---|---|---|---|---|
| Local (Ollama) availability | `GET /api/v1/models/local` | **SURFACED** (Wave 3) — Models organ: per-provider readiness; honest "No brains ready" empty | Keep | — |
| Bedrock models | `GET /api/v1/models/bedrock` | **SURFACED** (Wave 3) — Models organ readiness row | Keep | — |
| Gemini (Vertex) models | `GET /api/v1/models/gemini` | **SURFACED** (Wave 3) — Models organ readiness row (was ABSENT) | Keep | — |
| Auto per-task selection | `GET /api/v1/models/auto` | **SURFACED** (Wave 3) — Models organ `by_task` readout | Keep | — |

---

## Infra-only (no hero UI)
- `POST /api/generate` — the turn driver; observed via its SSE frames.
- `done` (SSE) — terminal frame; drives stream-stop + persistence.
- `POST /api/v1/approval/req` — capability resolver; the approval card is the surface.
- `GET /health` — boot liveness (BootSequence).
- `POST /api/v1/execute` — single-command gate/run; redundant with `/api/terminal`.

## Renovation IA note (what actually shipped, Waves 0–9)

The renovation shipped as **ONE additive `OrgansDock`** — a collapsed top-right **▣ ORGANS** tab that opens a glass panel with **10 grouped organs** (Conversation · Autonomy · Proposals · Growth · Skills · Memory · Plan · Intent · Zone Probe · Models), self-portaled to `document.body` at **z-55** — plus the **`ApprovalSafetyNet`** (z-62) mounted on **both faces**. This is a deliberately **canon-safer** choice than the blueprint's in-scene nerve-tab-stacks: the canon idle frame (brain, voyage, scene, sovereignty row) is **unchanged** except for the small dormant **▣ ORGANS** tab. Observe-before-operate held throughout — every organ is a read-only observer; act/control endpoints (revoke, apply/reject, consolidate/facts/reconcile, corrections/feedback, terminal/rollback) are **DEFERRED-AND-DOCUMENTED**, not silently dropped. **CODE** has no dedicated organ: it is covered by the Conversation organ's fenced-code rendering + the ForgePorts shell workspace (real on-disk files). The two lab-relabel items (#12/#13) remain DEFERRED-AND-DOCUMENTED.

## Recommended first surfaces — SHIPPED (Waves 0–9)
All four originally-recommended P0/P1 surfaces landed:
1. ✅ **Harden the approval surface (P0)** — Wave 6 `ApprovalSafetyNet`; stuck-run desync fixed.
2. ✅ **Conversation/Answer (P0, `text_chunk`)** — Wave 5; verbatim reply from L2 episodic memory, default `converse` tab.
3. ✅ **Autonomy Ledger (P0, `/development/autonomy`)** — Wave 1; ⚡N black box → auditable observability.
4. ✅ **Curriculum / Growth (P1, `/development/curriculum`)** — Wave 1; live brain-growth evidence visible.

**Open follow-ups (next fronts):** the act/control DEFERRED-AND-DOCUMENTED rows above (observe-before-operate, when wanted), and surfacing the ForgePorts workspace on the **default home** (currently `?ui=shell`-scoped).

Key source paths: `aios/api/main.py` (SSE + 34 routes), `frontend/src/App.jsx` (classic parser; `code` no-op line 763), `frontend/src/superbrain/lib/aiosAdapter.ts` (product SSE/REST/poll), `frontend/src/superbrain/components/ui/SuperbrainHUD.tsx` (primary product render surface).
