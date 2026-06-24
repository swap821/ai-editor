# SWARM_FUSE_WOW_SPEC — Frontend/Backend Fusion + First-Viewer Wow

**Status:** design doc — ready for implementation when the operator gives the next go.  
**Scope:** make the GAGOS 3D being a live, readable surface for the ant-colony swarm, and give a first-time viewer an immediate "this thing is alive" moment.

---

## 1. Backend: expose swarm intent as first-class SSE frames

The swarm already emits `tool_result` events tagged with `role`. The API consumes them as generic `step` frames. Add a small set of semantically typed frames so the UI can animate without parsing role strings.

### New SSE frame types

| Frame | Fields | When emitted |
|-------|--------|--------------|
| `swarm_plan` | `plan: string[]` | After decomposition/pattern recall (already emitted; UI should consume it). |
| `caste_start` | `caste: "scout"\|"decomposer"\|"cloud_broker"\|"worker-N"\|"quorum-N"\|"synthesizer"`, `index?: number` | At the first event of a caste leg. |
| `caste_end` | `caste`, `outcome: "ok"\|"paused"\|"blocked"` | When a leg ends or pauses. |
| `cloud_route` | `subtask_index: number`, `provider: "bedrock"\|"gemini"\|"ollama"` | When a worker is routed through the cloud factory. |

### Minimal change

In `aios/agents/swarm.py`, prefix each caste's first event with a typed frame:

```python
yield {"type": "caste_start", "role": "swarm", "caste": role, "index": index}
```

In `aios/api/main.py`, map `caste_start` / `caste_end` / `cloud_route` to `_sse(...)` so the front-end receives them. These frames carry no new authority; they are purely observational.

---

## 2. Frontend: GAGOS as a live swarm dashboard

### 2.1 Swarm HUD overlay

A thin, semi-transparent overlay inside `GagosChrome` (not blocking the canvas) that appears only during `req.swarm` turns:

- **Plan strip:** small numbered pills across the top, one per subtask. Filled = completed, pulsing = active, amber = cloud-burst.
- **Caste indicator:** a glyph beside the active-brain badge that names the current caste (`SCOUT`, `WORKER-2`, `QUORUM`, `SYNTH`).
- **Live count:** `N workers • M cloud • quorum on/off`.

Implementation: new component `frontend/src/workbench/SwarmHUD.jsx`, subscribed to the same SSE stream via the existing adapter.

### 2.2 Browse approval card

The `human_required` handler in `aiosAdapter.ts` today expects `command` / `edit` / `creation`. Add a `browse` branch:

- Surface a `BrowseApprovalCard` with:
  - large domain name,
  - URL truncated with ellipsis,
  - shield icon + "This fetches a public page and sends it to the model",
  - Approve / Deny buttons.
- On approve, the token is added to `approvalTokens`; the replay turn runs `browse` pre-approved.

### 2.3 Cloud-burst route badge

Extend the existing `route` frame logic so a `cloud_route` frame switches the active-brain badge to a cloud icon + provider name (Bedrock/Gemini) for the duration of that worker leg.

---

## 3. First-viewer "wow" polish

### 3.1 Awakening sequence (first mount only)

When `GagosChrome` mounts with no conversation history, run a 3–4 second ambient intro:

1. Canvas fades in from black.
2. Brain coheres from a particle field into the GLB mesh.
3. Spine lights travel from base to crown.
4. The input placeholder types itself: "What shall we build?"

Use existing animation systems (`livingOrchestrator`, `organismLifecycle`); no new heavy dependencies.

### 3.2 Idle breathing

When not busy, the being gently breathes: slow scale/rotation micro-motion, occasional faint nerve pulse. This makes the page feel alive before the user types.

### 3.3 Intent preview while typing

As the user types, send a lightweight `POST /api/v1/intent_preview` (or reuse the existing lightweight classification) and subtly tint the input border/aura toward the predicted mode:

- code → cyan,
- browse → blue,
- swarm → purple,
- chat → neutral.

This is cosmetic and low-frequency (debounced 300 ms).

### 3.4 Verify celebration / failure

When a `verify` tool result arrives:

- PASS: a short aurora pulse travels up the spine; the active brain badge glows green for 1 s.
- FAIL: a controlled red shimmer + the caste HUD shows a compact reflection note.

---

## 4. Onboarding (first run)

If `localStorage.getItem("gagos-onboarded")` is absent, show a 3-step translucent coach:

1. "Type a goal — I will split it into a swarm plan."
2. "Watch the numbered plan appear; each dot is an independent worker."
3. "I pause for your approval on writes, commands, and web fetches."

Dismiss sets the flag; no forced tutorial after that.

---

## 5. Implementation order (recommended)

1. **Backend typed frames** — DONE (`caste_start` / `caste_end` emitted from the
   swarm and forwarded by `/api/generate`). `cloud_route` remains to be added when
   the cloud factory carries provider metadata.
2. **Browse approval card** — closes a real functional gap from the new tool.
3. **Swarm HUD overlay** — high visibility, moderate risk; keep it read-only.
4. **Awakening + idle breathing** — pure polish; gate behind a feature flag if needed.
5. **Intent preview + verify celebration** — nice-to-have; can ship separately.
6. **Onboarding coach** — last, after the new visuals are stable.

---

## 6. Guardrails

- No changes to `aios/security/*`.
- All new frames are observational; authority stays in existing approval flows.
- Cloud-burst and browse remain YELLOW; the UI must not auto-approve.
- Keep first-load animation respectful of `prefers-reduced-motion`.

---

## 7. Acceptance

- `npm test -- --run` stays 299 passed.
- `vite build` green.
- `python -m pytest -q` stays green.
- A first-time user sees motion, understands the being is reactive, and can approve a browse URL without reading docs.
