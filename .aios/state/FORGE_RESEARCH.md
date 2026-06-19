# THE FORGE — Synthesis Build Plan (P8 of the Working-Brain Canon)

**Author:** Chief Architect synthesis (2026-06-15)
**Inputs:** 4 research lenses + adversarial CORRECTIONS LEDGER (authoritative) + first-hand re-verification against the live tree.
**Roadmap anchor:** `C:\Users\kumar\ai-editor\.aios\state\WORKING_BRAIN_CANON_RESEARCH.md` (P8 = The Forge = the big-substance lens).
**Thesis (operator, 2026-06-15):** the brain goes from demo to an actual working virtual-computer brain — "it's about the WHOLE CANON also and its TOOLS." THE FORGE is "its tools": the brain's real workspace where its agentic tool-use (edit/create/exec/verify) becomes REAL file changes, docked into the superbrain by its nervous system.
**Vision update (operator, 2026-06-15):** the homepage is the BRAIN ALONE, calm, voyaging. On a directive the brain WAKES and the VS-Code-style IDE (editor/preview/terminal) AUTOMATICALLY MATERIALIZES at the existing frozen nerve tips — a living organism extending its nerves to operate the workspace. The forge is STATEFUL + SUMMONED: an IDLE state (brain only) and a WORKING state (brain + materialized IDE + extended nerves), with an ALIVE transition between them.

**Hard rule for this document:** no code edits, no build runs. Everything below is DESCRIBED, not written. Every load-bearing claim is cited file:line and was re-verified first-hand.

---

## 1. VERIFICATION LEDGER (what is TRUE, with file:line; what the lenses got wrong)

### 1.1 The real tool surface — re-verified first-hand

`aios/agents/tool_agent.py` TOOL_SPECS contains **9 entries**, re-confirmed at these exact lines:
`read_file`:161, `read_directory`:181, `execute_terminal`:201, `edit_file`:222, `create_file`:258, `verify`:288, `plan`:316, `self_analyze`:338, `propose_fixes`:363.

- The "8 tools" framing in the prompt is the conceptual grouping that treats `self_analyze`+`propose_fixes` as one read-only self-analysis unit. **Per CORRECTION 5, do NOT write "exactly 8 entries in TOOL_SPECS" — there are 9 dispatched names.** Both framings are defensible; this plan uses "9 dispatched tools / 8 capability groups."
- Zones (from the prompt + tool_agent docstrings, re-verified by name): `read_file`/`read_directory` GREEN; `execute_terminal` GREEN/YELLOW/RED-gated; `edit_file`/`create_file` YELLOW (force auto-verify after); `verify` GREEN; `plan` GREEN advisory; `self_analyze` T0/T1 read-only; `propose_fixes` T2 read-only.
- **NO `web_search`/`fetch_url` tool exists.** Re-confirmed: the `/read|search|list|web|fetch|grep|inspect/` regex at `SuperbrainScene.tsx:492` is a label-classifier arm that maps such labels to the ARCHIVE hub — it is DEAD code for `web|fetch` because no such tool emits those labels (CORRECTION 6 confirmed). Any forge surface referencing web fetch is fabricated.
- Output caps re-verified in `tool_agent.py`: `_TOOL_RESULT_LIMIT = 4000` (line 139, model-facing convo context) and `_PREVIEW_LIMIT = 400` (line 143, the SSE-facing `output`/`reason` slice). Auto-verify verdicts carry id `autoverify-{index}` (lines 1008, 1027, 1031). **Per CORRECTION 7, a forge terminal that needs full untruncated output must use `POST /api/terminal`, not the SSE `tool_result` frame (capped at 400 chars).**

### 1.2 The real workspace/SSE endpoints — re-verified first-hand in `aios/api/main.py`

| Endpoint | Line | What it gives the forge |
|---|---|---|
| `GET /api/v1/development/workspace` | 800 | The on-disk truth: `training_ground/` text files, newest-first, ≤16 files, ≤200KB each, `{root, files:[{path,content}]}`. No path param, no traversal. This is the forge editor's idle data source. |
| `GET /api/v1/development/autonomy` | 844 | Earned-autonomy ledger (graduated/revoked classes + threshold + master switch). |
| `POST /api/v1/development/autonomy/revoke` | 854 | Operator force-revoke of an earned signature. |
| `GET /api/v1/development/trails` | 790 | Pheromone/trail map (strength, freshness, quarantine) — trail-delta after a verified write. |
| `GET /api/v1/development/metrics` | 773 | Verified success rate, coverage, blocked actions, intervention rate. |
| `GET /api/v1/audit/verify` | 899 | `{valid, total_entries}` — audit-chain health. |
| `POST /api/v1/approval/req` | 965 | Resolve a pending approval (the approval panel already uses it). |
| `POST /api/terminal` | 2302 | Direct UI-terminal: full gateway gating — RED `[BLOCKED]`, YELLOW issues a server token + `requiresApproval`, GREEN runs in the scope-locked sandbox and returns `{output, isError}` (re-read lines 2315-2338). Returns FULL output, not the 400-char SSE slice. |
| `POST /api/generate` | (SSE) | The agentic stream the forge already rides (tool_call / tool_result / human_required / code / earned_autonomy / done). Re-verified the `code` frame discard below. |

### 1.3 What classic-editor pieces actually exist to reuse — re-verified first-hand

The product frontend `C:\Users\kumar\ai-editor\frontend\src` is REAL and present (an earlier relative-path glob mis-fired; first-hand `find` confirms the full tree). Confirmed reusable, production-grade:

- `frontend/src/components/CodeCanvas.jsx` — Monaco editor (`@monaco-editor/react`); already wraps value/onChange/language. Product-tree only.
- `frontend/src/components/LivePreview.jsx` — sandboxed CSP iframe for html/css/js. Product-tree only.
- `frontend/src/components/DiffView.jsx` — unified-diff renderer (+green/−red/@@blue). Used by the classic `<App/>`; **NOT imported by ForgePorts** (re-confirmed: `Grep DiffView` over `ForgePorts.jsx` → no matches).
- `frontend/src/superbrain/components/ui/ApprovalPanel.tsx` — the decision surface (AUTHORIZE/REJECT), mounted by the HUD.
- `frontend/src/workbench/approval/ApprovalSafetyNet.jsx` — belt-and-suspenders that re-surfaces a missed approval. Mounted in BOTH `SuperbrainApp.jsx:30` and `SuperbrainShell.jsx:91`.

### 1.4 The forge that ALREADY EXISTS in the product (the lenses are correct here)

`frontend/src/workbench/ForgePorts.jsx` (255 lines, re-read in full) is a REAL, substantially-built forge:

- Two in-canvas `<Html>` ports: `PORT_EDITOR = [-4.8, -1.7, 0]` (line 22) and `PORT_PREVIEW = [4.8, -1.5, 0]` (line 23).
- These coordinates **exactly match the canon frozen nerve tips** re-verified in `frontend/src/superbrain/components/canvas/NervousSystem.tsx` (and the lab copy): `leftTargetX=-4.8` (line 257), `rightTargetX=4.8` (line 258), with the left bundle terminating at y=-1.7 (line 340) and the right at y=-1.5 (line 357). The forge plugs into the frozen tips — it does not move them.
- Editor port: Monaco via `CodeCanvas`; reads `GET /api/v1/development/workspace` (line 109); bounded burst re-poll [350,1500,3500]ms on `synthesis|knowledge-acquired|approval-resolved|agent-dispatch` (lines 140-162); honest loading/OFFLINE banners (lines 193-202); manual ⟳ refresh; tab bar; flares on write events.
- Approval-on-diff: on `approval-required` it reads `getPendingApproval()`; for `kind==='create'` it loads `p.content` into the editor with a PENDING banner (lines 86-93).
- Preview port: `LivePreview` sandboxed iframe sharing the same `files` map; flares on knowledge/verify events.

Wiring: `SuperbrainShell.jsx:46` mounts `<WorkspaceCanvas>{manufacturing ? <ForgePorts/> : null}</WorkspaceCanvas>` — the forge is mounted today, gated behind a `mode` toggle (default `'home'`, line 28; "Enter workbench" button, line 69).

### 1.5 The routing truth — re-verified first-hand in `main.jsx`

| Route | Component | WorkspaceCanvas children | Forge today |
|---|---|---|---|
| Lab `page.tsx` (default) | bare `WorkspaceCanvas` | NONE | EMPTY (comment-only slot at `WorkspaceCanvas.tsx:217-220`) |
| Product `?ui=home` / `?ui=superbrain` | `SuperbrainApp.jsx:17` | NONE | EMPTY (forge slot unfilled) |
| Product `/` (default) or `?ui=shell` | `SuperbrainShell` in home mode | NONE | EMPTY until toggled |
| Product `/` in manufacture mode | `SuperbrainShell.jsx:46` | `<ForgePorts/>` | FILLED — Monaco + workspace + LivePreview + CommandLine |

**Nuance the lenses under-stated:** `SuperbrainApp` (the `?ui=home`/`?ui=superbrain` route) is NOT byte-identical to the lab — it additionally mounts `OrgansDock` (line 23) and `ApprovalSafetyNet` (line 30). It IS identical in the one way that matters here: `WorkspaceCanvas` gets NO children (line 17), so the forge slot is empty there. The operator's thesis ("home/?ui=superbrain passes NO children — the forge ports are unfilled") is CONFIRMED TRUE for `SuperbrainApp` and the lab; the default `/` route already has the forge behind the mode toggle.

### 1.6 The two confirmed adapter/UI GAPS (both re-verified first-hand)

- **GAP A — the `code` SSE frame discards the code string.** `aiosAdapter.ts:273` (`case 'code'`) reads `frame.data.code` only to count lines for the `detail` string, then drops it. Re-confirmed in BOTH the lab adapter (`GAG demo/.../src/lib/aiosAdapter.ts:273`) and the product adapter (`frontend/src/superbrain/lib/aiosAdapter.ts:273`). No `lastEmittedCode`/`lastCodeFrame` module var, no `getLastEmittedCode()`/`getLastCodeFrame()` getter exists (Grep → none). CORRECTION 4 confirmed exact.
- **GAP B — no DiffView in ForgePorts for EDIT approvals.** `ForgePorts.jsx:87-92`: on `approval-required` it calls `setPending(p)` for both create and edit, but only `if (p.kind === 'create' && p.filepath)` loads content into the editor (lines 89-93). For `kind==='edit'` the PENDING banner shows (lines 215-219) but the unified diff in `pendingApproval.diff` is NEVER rendered — `DiffView` is not imported. CORRECTION 3 / B8 confirmed exact. The diff IS available: `PendingApproval.diff` carries the unified diff for edits (`aiosAdapter.ts:160-161`, "Unified diff for writes; empty for command approvals").

### 1.7 Coordinate / security corrections the synthesis MUST obey (from the ledger)

- **CORRECTION 1 (CRITICAL):** the spinal forge-port coordinate `(0,-2.6,1.5)` cited by lenses 3/4 is FABRICATED. `NervousSystem.tsx` has `spinalDrop = (0,-1.2,-0.4)` (line 327), an intermediate control point, NOT a port. The CommandLine is a CSS-positioned DOM element in the `sb-dock-bar` div (`SuperbrainShell.jsx:52-63`), NOT an in-canvas `<Html position={...}>` anchor. **Any third "spinal port" in the plan must be DOM/CSS-positioned, not an R3F `<Html>` at a fabricated 3D coordinate.**
- **CORRECTION 2:** several NervousSystem line citations in lenses 1/4 are ~20-25 lines off (and the y-values were slightly mis-stated). Authoritative values, re-verified: `leftTargetX=-4.8` (257), `rightTargetX=4.8` (258), left tip y=-1.7 (340), right tip y=-1.5 (357), `spinalDrop=(0,-1.2,-0.4)` (327). **Use VALUES, not the lens line numbers.**
- **CORRECTIONS 8 / C1 / C2 / C3 (security):** voice is directive-only and can NEVER redeem an approval (`/api/v1/chat` runs `tools=None`); RED is always blocked (`tool_agent.py` docstring; gateway deterministic); raw `approved_*` without a server token is rejected (`main.py:1719-1722`). No forge surface may add an approval button reachable from the voice organ, and no "voice trigger" may route through the approval path.
- **C4/C5/C7:** ForgePorts uses `<Html>` only — no GLB/texture access (CLEAN); the port coordinates match the frozen tips and are not recomputed (CLEAN); the `npm run port` clobber boundary is safe — `ForgePorts.jsx`, `forge.css`, `manufacturing.css`, `SuperbrainShell.jsx`, `main.jsx` live OUTSIDE the port manifest (which overwrites only the `superbrain/*` tree).

---

## 2. THE STATE — what the forge is today, and the precise gap

**The slot:** `WorkspaceCanvas.tsx:220` renders `{children}` inside `<Canvas>`→`<Suspense>` (re-read lines 206-221). It renders nothing when no children pass. The lab `page.tsx` and product `SuperbrainApp` pass none → empty. The product `SuperbrainShell` passes `<ForgePorts/>` only in manufacture mode.

**What is REAL today (product, manufacture mode only):** a two-port forge — Monaco editor at the left frozen tip showing real `training_ground/` files + pending CREATE content; a sandboxed LivePreview at the right frozen tip; a CommandLine at the bottom-center DOM dock; honest loading/offline states; burst re-poll that catches earned-autonomy writes; the approval pause surfaced via the HUD's ApprovalPanel + the safety net.

**The precise gap to a real, usable, SUMMONED workspace (in importance order):**

1. **No idle→working summon choreography.** Today the forge is a hard mode TOGGLE (a button press flips `mode`), not a directive-triggered MATERIALIZE. The vision wants: brain alone at rest → operator gives a directive → brain wakes → IDE blooms at the nerve tips with an alive transition → returns to calm when work settles. None of that state machine or transition exists.
2. **No terminal port.** `execute_terminal`/`verify` output has no spatial home in the forge. It only appears as text in the HUD cognition feed. (Reuse target: the classic `<App/>` terminal pattern + `POST /api/terminal` for full output.)
3. **No verify-verdict surface.** PASS/FAIL + trail-delta + autonomy status has no anchored panel; verdicts only flash as `VERIFICATION GREEN/RED` cognition labels.
4. **EDIT approvals show no diff (GAP B).** The diff is in `pendingApproval.diff` but ForgePorts never renders it. This is the single most visible correctness gap in the existing forge.
5. **The `code` SSE frame is discarded (GAP A).** Advisory code the brain emits without writing a file is lost to the forge; only files it actually WROTE appear (via the workspace poll).
6. **The lab has zero forge.** If P8 is built lab-first, the lab needs its own (Monaco-free) forge wiring; `page.tsx` passes no children today.
7. **Nerve richness vs the "alive organism" target.** The canon has 3 bundles to 3 tips. The vision references a dense branching peripheral nerve TREE. Today's nerves are frozen and additive-only; richer branching is a separate, FIDELITY-gated visual front (see Risks).

---

## 3. THE DESIGN — the forge as a SUMMONED, nerve-connected IDE docked into the superbrain

### 3.1 The state machine: IDLE → WAKING → WORKING → SETTLING → IDLE

The forge becomes STATEFUL. The brain is always one persistent `WorkspaceCanvas` (never remounted — that would recompile the GLB/shaders). The forge is a child that materializes/dematerializes inside it. Proposed states (described, not coded):

- **IDLE** — homepage. Brain alone, voyaging, full canvas. No forge children rendered (`{children}` is null, byte-identical to canon home). This is the calm default.
- **WAKING** — a real directive lands (the operator types into the command bar / sends a directive → `streamTurn`). The FIRST real signal of intent — the `step(tool_call)` `agent-dispatch` bus event, or the directive submit itself — flips the forge to materializing. The nerve tips brighten; the IDE ports fade/scale in AT the frozen tip coordinates (left editor, right preview) with a short alive transition. Critically: the ports bloom AT the tips, so the existing frozen nerves already reach exactly where the workspace appears — the nerves do NOT chase a moving target (honors the frozen-tips constraint, CORRECTION 1).
- **WORKING** — the IDE is materialized and live. Tool-use streams into it: tool_call surges the nerve toward the port it changes; create/edit pauses for approval with the diff/content shown in the editor port; verify lands a verdict in the right port; earned-autonomy writes appear via the workspace re-poll. The brain keeps voyaging behind the ports.
- **SETTLING** — on `done` with no follow-on activity for a grace window, the forge can either persist (operator is mid-session) or gently recede. Design choice for the operator (open question Q1): auto-recede to IDLE after inactivity, or stay until dismissed. Honest default: STAY until the operator dismisses, so a finished run's artifacts remain readable; only the "alive glow" settles.

The existing `mode` toggle ("Enter workbench"/"Voyage") is KEPT as the manual override (operator can summon/dismiss the forge by hand), but the new path is DIRECTIVE-TRIGGERED materialize. The transition is the hardest, highest-value work — it must be additive (CSS/transform on the `<Html>` DOM islands + a nerve-tip brightness ease), never a canvas remount, never a shader change.

### 3.2 The materialize trigger — data-true, from real tool-use

The trigger MUST be a real signal, never a fake timer:
- Directive submitted → the command bar already calls the adapter's directive path; the forge subscribes to the cognition bus and flips to WAKING on the first `agent-dispatch`/tool_call event of the turn (the same event `ForgePorts.jsx:39 isWriteEvt` already detects).
- This means the IDE materializes because the brain is ACTUALLY about to operate a tool — the bloom is evidence of real intent, not decoration.
- RED is invisible here (CORRECTION 2/C2): a blocked action emits `tool_blocked`→`agent-dispatch BLOCKED`; the forge may still materialize (the brain TRIED to act) but shows no content for the blocked action — there is nothing to show, and that honesty is the security UX.

### 3.3 The editor port (left frozen tip, -4.8,-1.7,0) — REUSE + close GAP B

Keep the existing `CodeCanvas`/Monaco editor port. Priority of what it shows:
1. `pendingApproval.kind==='create'` → `pendingApproval.content` with the PENDING banner (already built, `ForgePorts.jsx:89-93`).
2. **`pendingApproval.kind==='edit'` → render `DiffView` (from `frontend/src/components/DiffView.jsx`) with `pendingApproval.diff`** — this CLOSES GAP B. Reuse the existing component (no rebuild). The PENDING banner already shows; add the diff body.
3. Idle/between turns → real `training_ground/` files from `GET /api/v1/development/workspace` (already built).
4. **Optionally (GAP A)** → the brain's last advisory `code` frame, clearly labeled "ADVISORY · not written," from a new `getLastEmittedCode()` getter. Lower priority than the workspace truth (which shows what was actually written).
5. Honest dormancy: keep the existing loading/OFFLINE banners; never invent content.

### 3.4 The preview/verdict port (right frozen tip, +4.8,-1.5,0) — REUSE + add verdict

Keep `LivePreview` for html/css/js. ADD a verdict mode for non-web work (Python/text — which is what `training_ground/` mostly is):
- Show the latest `[VERIFY PASS]`/`[VERIFY FAIL]` from a `tool_result` whose id starts `autoverify-` (the AUTHORITATIVE evidence, `tool_agent.py:1008/1027/1031`).
- Show the trail-strength delta (`GET /api/v1/development/trails`) and the autonomy status (`GET /api/v1/development/autonomy`) for the just-acted class — adapter getters already exist for both.
- Honest dormancy: "no verdict yet" until a real verify lands; never fabricate PASS (C2-adjacent honesty rule).

### 3.5 The terminal port — NEW, DOM-positioned (NOT a fabricated 3D coordinate)

Per CORRECTION 1, the spinal/command region is a CSS DOM dock (`sb-dock-bar`), not an `<Html>` 3D anchor. The terminal is therefore a DOM panel near the command bar (bottom band), not a third in-canvas `<Html>` port at a fabricated `(0,-2.6,1.5)`.
- Read mode (agent-driven): filter the cognition stream for `tool_result` where `tool ∈ {execute_terminal, verify}` and append to a scrolling log. Note the SSE `output` is capped at `_PREVIEW_LIMIT=400` (line 143) — enough for verdict lines, not full shell dumps.
- Command mode (operator-typed, optional): drive `POST /api/terminal` (line 2302) for FULL untruncated output, with the SAME gateway gating (RED `[BLOCKED]`, YELLOW issues a server token, GREEN runs). Reuse the classic `<App/>` terminal UI pattern (scrolling div + form + token-intercept). This is a separate, operator-typed channel from the agent's tool loop.

### 3.6 Tool-use lighting the lattice/nerves (tie to the data-true firing already built)

The signal chain already exists and must be honored, not duplicated:
- `step(tool_call)` → `agent-dispatch` (intensity 0.8) → nerve surge + flow direction toward the acted port (`ForgePorts.jsx:39` already flares the editor; `:40` flares the preview on knowledge/verify).
- `human_required` → `approval-required` → cortex amber, nerve packets freeze (the supervised pause made visible), the editor port opens the proposed content/diff.
- `step(tool_result, verify)` → `knowledge-acquired VERIFICATION GREEN/RED` → right port verdict + flare.
- `earned_autonomy` → `knowledge-acquired AUTONOMOUS ACTION` (no pause) → the workspace re-poll loads the written file; the lattice flashes the trust grant.
- The forge ADDS spatial context around these existing signals; it does not take decisions. The ApprovalPanel remains the SOLE authorization surface.

### 3.7 Security pause visible + honored (non-negotiable)

- The pause is shown in three layers (scene amber/frozen packets; editor port PENDING content/diff; HUD ApprovalPanel AUTHORIZE/REJECT). The forge is contextual; the panel decides.
- Voice cannot authorize (architecture-enforced). No forge/approval button is reachable from the voice organ (CORRECTION 8).
- RED never reaches the forge (gateway blocks it before any SSE content); the only signal is a dimmed `BLOCKED` label.
- Operator force-revoke (`POST /api/v1/development/autonomy/revoke`) can be exposed on the verdict port so "human authority over the bridge stays absolute."

### 3.8 Reuse map (don't rebuild what exists)

REUSE as-is: `CodeCanvas` (Monaco), `LivePreview`, `DiffView`, `ApprovalPanel`, `ApprovalSafetyNet`, `CommandLine`, the existing `ForgePorts` shell, the adapter's `subscribePendingApproval`/`approvePendingApproval`/`rejectPendingApproval` (lines 191/445/463), `getKnownTrails`/`getAutonomy` getters, and the workspace fetch. NEW work is the state machine + transition, the EDIT-diff wire, the terminal/verdict surfaces, and the two small adapter additions (GAP A getter; optional terminal filtering).

---

## 4. PHASED BUILD PLAN (importance-ranked)

Each phase: capability · real data shown · lab-first vs canon · FIDELITY/security gates · riskiest/blind steps. Backend/adapter changes are flagged as their own steps.

### PHASE 0 — Close the correctness gaps in the EXISTING forge (highest value, lowest risk)
- **0a — Wire `DiffView` for EDIT approvals (GAP B).** Capability: the editor port renders `pendingApproval.diff` when `kind==='edit'` (today it shows only a banner). Real data: the actual unified diff the brain proposed. Reuse `frontend/src/components/DiffView.jsx`. Product-side (ForgePorts is product-authored). FIDELITY: `<Html>` DOM only, no canvas change. Security: read-only display; the ApprovalPanel still decides. Risk: LOW. Blind step: confirm DiffView renders legibly inside the constrained `<Html>` width (forge.css).
- **0b — (Adapter) store the `code` frame (GAP A).** Backend? No — adapter only. Add a `lastEmittedCode` module var in `case 'code'` (adapter line 273) + a `getLastEmittedCode()` getter, SAME idiom as `pendingApproval`. Do it in the LAB adapter first (canon source), then it ports. Capability: the editor can show advisory code labeled "not written." FIDELITY/security: additive, no behavior change. Risk: LOW. Blind step: the product adapter is port-managed; the change must originate in the lab adapter so `npm run port` carries it.

### PHASE 1 — The SUMMON state machine + alive transition (the marquee, highest-value/hardest)
- Capability: IDLE (brain alone) → directive → WAKING → WORKING (IDE materialized at the tips) → SETTLING. Real data trigger: the first real `agent-dispatch`/tool_call of the turn (not a timer). Real data shown: the materialized forge then shows real workspace/diff/verdict as in P0/P2/P3.
- Lab-first: build the state machine + a Monaco-free `<pre>`-based lab forge so the choreography is provable in the lab without adding Monaco to the lab (port-manifest constraint). Then the product `ForgePorts` (Monaco) inherits the same state contract.
- FIDELITY gates: NEVER remount `WorkspaceCanvas` (GLB/shader recompile). The transition is CSS/transform on the `<Html>` DOM islands + an additive nerve-tip brightness ease — no change to `SCENE_UNIFORMS`, no new uniform, no blending/depth change, frozen tips untouched. Before/after screenshots in HIS browser for the transition (FIDELITY law). Lab-first; canon parity proven before product.
- Security: the materialize trigger must be a real tool/directive event; it must NOT route through or short-circuit the approval path (CORRECTION 8). The pause/RED behavior is unchanged.
- Riskiest/blind steps: (1) the transition feel — an alive bloom vs a jarring pop is the whole value, and the final call is the operator's browser; (2) keeping the brain's voyage perfectly intact during materialize (no frame hitch on the 16GB box); (3) deciding SETTLING behavior (Q1).

### PHASE 2 — The terminal surface (DOM dock, not a 3D port)
- Capability: a scrolling terminal in the bottom band showing real `execute_terminal`/`verify` output; optional operator-typed command mode via `POST /api/terminal`.
- Real data: `tool_result` frames (≤400 chars, SSE) for the agent log; full output from `POST /api/terminal` (line 2302) for typed commands. Reuse the classic `<App/>` terminal pattern.
- Lab-first: a styled log in the lab (no new deps); product reuses the same.
- FIDELITY: DOM panel near the command dock — NOT a fabricated `(0,-2.6,1.5)` `<Html>` port (CORRECTION 1). Security: typed commands go through the same gateway (RED blocked, YELLOW token, GREEN run) — re-verified at `main.py:2315-2338`; the typed channel must use the server-issued token, never raw `approved_*` (C3).
- Riskiest/blind step: not visually colliding with the command bar / not crowding the brain at <900px (hide on small screens).

### PHASE 3 — The verdict/preview port enrichment
- Capability: the right port shows PASS/FAIL (autoverify-* verdict), trail-delta, autonomy status, and the operator force-revoke button.
- Real data: `tool_result` autoverify verdicts; `GET /api/v1/development/trails` (790); `GET /api/v1/development/autonomy` (844); `POST /api/v1/development/autonomy/revoke` (854). Adapter getters mostly exist.
- Lab-first feasible; product reuse. FIDELITY: `<Html>` DOM only. Security: revoke is operator-only and honored server-side; never fabricate PASS.
- Riskiest/blind step: honest dormancy — "no verdict yet" must never read as a failure.

### PHASE 4 — Optional backend surface (only if a need is proven)
- **4a — Full untruncated agent terminal output:** the SSE `output` is capped at 400 (line 143). If the operator wants full agent-loop output in the read-only terminal (not just typed commands), this is a BACKEND change (raise/added-field for full output) — flagged as its own step. Mitigation today: `POST /api/terminal` already returns full output for the typed channel, so 4a may be unnecessary.
- **4b — Workspace change push:** the workspace endpoint is poll-only; there is no push. The burst re-poll is sufficient for MVP. A file-watcher SSE is a BACKEND change, deferred.
- **4c — Diff/audit history:** no per-session diff history endpoint exists (`/api/v1/audit/verify` returns only counts). A `GET /api/v1/audit/entries` would be a BACKEND change, deferred.

### PHASE 5 — Richer "alive" nerve branching (FIDELITY-heaviest, deferred)
- Capability: the dense branching peripheral-nerve-tree aesthetic from the vision (richer than 3 bundles). Real data: drives off the same tool-use stream. This is a VISUAL elevation, not a forge-data feature.
- FIDELITY: this is the most sacred area — the nerves and frozen tips are canon. Any branching must be ADDITIVE, must keep the existing tips frozen, must keep the GLB/textures untouched, and requires canon-tag + goldens + before/after in HIS browser BEFORE any work (FIDELITY laws). Lab-first, perf-budgeted (added tubes cost GPU). Deferred until P1-P3 land. Riskiest of all — defer until the substance is real.

---

## 5. RISKS + MITIGATIONS

- **Security gateway bypass.** Mitigation: the forge takes NO decisions; AUTHORIZE/REJECT stays in ApprovalPanel via server tokens (`approvePendingApproval`/`rejectPendingApproval`, lines 445/463); typed terminal uses `POST /api/terminal`'s server token; raw `approved_*` is server-rejected (C3); voice can't authorize (C1/CORRECTION 8); RED never surfaces content (C2).
- **Monaco perf / self-host (16GB box).** Monaco is product-tree only and already lazy (the whole shell is `lazy()` in `main.jsx:20`). `<Html>` is DOM, off the GPU hot path. The lab forge stays Monaco-free (`<pre>`/`DiffView`). The W5 self-host-Monaco todo (offline workers) is a separate hardening item, not a forge blocker — keep it tracked.
- **Frozen nerve tips.** The IDE materializes AT the frozen tips (-4.8/-1.5..-1.7); the nerves don't chase a moving target. No coordinate is recomputed (C5). The fabricated `(0,-2.6,1.5)` spinal port is rejected — the terminal is a DOM dock (CORRECTION 1).
- **Voyage intact during materialize.** Mitigation: never remount `WorkspaceCanvas`; transition only the `<Html>` DOM islands + an additive tip-brightness ease; no `SCENE_UNIFORMS`/shader/blending change; before/after in HIS browser; lab-first parity.
- **Port-clobber.** ForgePorts/forge.css/manufacturing.css/SuperbrainShell/main.jsx are product-authored and survive `npm run port`; the adapter (GAP A getter) must be changed in the LAB adapter so it ports correctly (C7).
- **Honest dormancy.** Every port must show a truthful empty/offline/no-verdict state and never invent content or replay stale content as current.

---

## 6. TOP RECOMMENDATION + OPEN QUESTIONS

**TOP RECOMMENDATION — build PHASE 0 first, then PHASE 1.**
P0 (wire `DiffView` for EDIT approvals + store the `code` frame) is the highest value-to-risk move: it closes the two confirmed correctness gaps in the forge that ALREADY exists, makes the brain's real edits fully visible (today an EDIT shows only a banner, not its diff), is pure reuse + one tiny lab-adapter getter, touches no canon shader/GLB, and honors every security rule. It makes the existing forge truthfully complete. THEN P1 (the directive-triggered summon state machine + alive transition) delivers the operator's marquee vision — brain-alone → wakes → IDE blooms at the frozen tips — built lab-first with screenshots in his browser. P0 makes the forge correct; P1 makes it the living, summoned workspace.

**OPEN QUESTIONS FOR THE OPERATOR**
1. **SETTLING behavior:** after a run finishes (`done` + grace window), should the IDE auto-recede to brain-alone, or persist until dismissed? (Default proposed: persist; only the alive glow settles — so artifacts stay readable.)
2. **Keep the manual toggle?** Should "Enter workbench"/"Voyage" remain as a manual override alongside the new directive-triggered materialize, or be removed in favor of pure summon?
3. **Lab vs product for P1:** build the summon choreography lab-first (Monaco-free `<pre>` forge to prove the state machine), then port to the Monaco product forge — confirm this is the desired path given the lab currently has zero forge.
4. **Terminal command mode:** do you want an operator-TYPED command channel (`POST /api/terminal`, full output) in the forge, or read-only agent-driven terminal output only (the safer, fewer-surfaces option)?
5. **Advisory code (GAP A):** when the brain emits a `code` block it did NOT write to disk, show it in the editor labeled "ADVISORY · not written," or keep the editor strictly to on-disk/pending files only?
6. **Phase 5 nerve branching:** is the richer "alive nerve tree" in scope now, or explicitly deferred until P0-P3 substance lands (recommended)?

**Final aesthetic call:** every transition, bloom, glow, and layout decision in this plan is subject to the operator's verdict in HIS browser. Lab-first, canon-tag + goldens + before/after screenshots gate every visual change; the final aesthetic call is always his browser.
