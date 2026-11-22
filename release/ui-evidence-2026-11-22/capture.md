# Face UI live re-capture, 2026-11-22 (organs 20, 48, 49, 51)

Captured on the operator's laptop against his running backend and face, both on
code `cea15a2791bc63d6b7ef56e5ca8b95e4d18f908c` (backend started 2026-11-22T01:07Z;
`data/services/daily.json` records that code). The face is the Vite dev server at
http://localhost:5173/.

## How it was captured (the boundary)

- The browser is GAGOS's own journey Chrome (`tools/gagos_journeys.py open`): a
  real, headed window on the operator's desktop, in GAGOS's journey profile, not
  headless. The operator signed in himself in that window; no credential was typed
  by an agent.
- The page was read through Chrome DevTools on 127.0.0.1 (DOM text only). The agent
  clicked only view controls (Expert / Mirror, Governance, Sovereign State, GAGOS
  tasks); never Approve, Allow, Accept or Revoke.
- The disconnected state was made by emulating the browser tab offline
  (`Network.emulateNetworkConditions`), not by stopping the backend, which kept
  serving GAGOS throughout. To the page this is the backend being unreachable.
- Operator ids are replaced by `operator:<id>`.

## The three states (organs 20 and 48)

== state 1 (signed out) 2026-11-22T03:29:32Z backend code cea15a27
Not signed in
The backend answered: this browser has no operator session. The operational picture needs one.transport connecting; projection unavailable; cursor unavailable
Visual detail
Auto
High detail
Balanced
Economy
Optional detail adapts to frame pacing. Work and con

== state 2 (signed in, connected) 2026-11-22T03:35:59Z backend code cea15a27; after one page reload (see defect note)
Live projection ready
Continuity has been confirmed.transport connected; projection fresh; cursor 3763Snapshot 9:05:54 AM

...
CONSTITUTION & EMERGENCY STOP
OPERATIONAL

Distinct from the v10 section's own "Constitution" field above (an older, separate caste-count view) — this is the typed, digest-verified read-model surface (organs 47/48): every field below is either a real measured value or an honest "unavailable", never guessed.

CONSTITUTION VERSION
1
RATIFIED BY
operator:<id>
SNAPSHOT DIGEST
2653480cfbfe40d5…
FOUNDATION LAWS
6
EMERGENCY STOP
clear
STOP REASON
unavailable

== state 3 (browser network emulated offline; backend kept running) 2026-11-22T03:36:35Z
before: {"status":"Live projection ready\nContinuity has been confirmed.transport connected; projection fresh; cursor 3763Snapshot 9:06:24 AM","signedIn":true,"constitution":"CONSTITUTION & EMERGENCY STOP\nOPERATIONAL","executor":"ISOLATED EXECUTOR\nREACHABLE","badges":[]}
offline +5s: {"status":"offline\nGAGOS is working.","signedIn":true,"constitution":"CONSTITUTION & EMERGENCY STOP\nOPERATIONAL","executor":"ISOLATED EXECUTOR\nREACHABLE","badges":["gagos-pill gagos-pill--offline||offline","gagos-dot gagos-dot--offline||"]}
offline +25.0s: {"status":"offline\nGAGOS is showing a last-known picture; current state is not confirmed.","signedIn":true,"constitution":"CONSTITUTION & EMERGENCY STOP\nOPERATIONAL","executor":"ISOLATED EXECUTOR\nREACHABLE","badges":["gagos-pill gagos-pill--offline||offline","gagos-dot gagos-dot--offline||"]}
restored +15s: {"status":"Live projection ready\nContinuity has been confirmed.transport connected; projection fresh; cursor 3763Snapshot 9:07:09 AM","signedIn":true,"constitution":"CONSTITUTION & EMERGENCY STOP\nOPERATIONAL","executor":"ISOLATED EXECUTOR\nREACHABLE","badges":[]}

== consistency live checks 2026-11-22T03:38-03:42Z (operator sent both turns himself, signed in, journey window)
turn 1 (LOCAL chooser, auto routing, coding): understand+plan on ollama qwen2.5-coder:7b; tool agent ran on provider=plan model=claude-sonnet-5-5 (model_calls 03:40:32Z, ok). The turn was then cancelled locally in the face before it finished ("Generation cancelled locally; backend termination is unconfirmed").
turn 2 (SWARM on, SONNET): decomposer leg worker-009ee8aa11f6 admitted by the Foundry and completed on plan claude-sonnet-5-5 (03:41:43-57Z). Then 4 worker legs (worker-6b86a190c648, -078db874c05f, -f49e3a872e93, -0bf4914188e8) requested/admitted/started within 0.5 s of each other (side by side), and each FAILED within ~0.3 s: "aios/agents/tool_agent.py:_stream_iteration asked plan for a model call through no gateway entrance; it was refused before it left (docs/ONE_GATEWAY.md, AIOS_GATEWAY_ENFORCE)". turn.failed 03:41:58Z. DEFECT: parallel swarm legs lose the gateway entrance.
tasks panel: renders live task rows with statuses (taken, cancelled seen).
defect 2: after sign-in the mirror transport stayed "Transport connecting" (>15 s, zero backend requests in 8 s) until a page reload; after reload "Live projection ready" at once.

## Sovereign State, connected (organs 49 and 51)

The whole panel's text is in `sovereign-state-connected.txt`. Read from it:
CONSTITUTION & EMERGENCY STOP: OPERATIONAL (version 1, 6 foundation laws, stop
clear); PENDING APPROVALS: 0 pending, "never exposes a usable bearer token";
PROVIDER HEALTH: 0 observed this process, no never-called provider shown as
healthy; ISOLATED EXECUTOR: configured yes, reachable yes, runtime docker.

## Found in the same session (not evidence for these organs)

- After signing in, the face's mirror transport stayed "Transport connecting"
  (more than 15 s, no backend request in 8 s) until the page was reloaded.
- The swarm's side-by-side worker legs were refused by the one gateway (PR #721).
