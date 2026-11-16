# Journeys, phase 2: the operator sends, the runner measures

**Status:** agreed by the operator on 2026-11-16 ("Yes, build phase 2"). This is the design; each journey lands in its own PR.

Phase 1 (`tools/gagos_journeys.py`, REC-01 and PERF-01) runs the face with nothing in flight. Most of the face's remaining acceptance points need **real work**: a turn the operator sends, a decision he makes, a receipt the backend writes. A journey must never send, approve or deny for him. So in phase 2 the runner only **watches**.

## The rule that does not move

| The operator does | The runner does |
| --- | --- |
| signs in, in the journey window (`open`) | never types a credential; keeps only "signed in: yes/no" |
| types the request and presses Enter | never presses Enter, never sends |
| clicks Approve, Deny or Stop | never clicks them, never fakes the gesture |
| decides when he is done | stops at the turn's terminal event, or at a time limit, and says which |

The runner refuses these actions in code already (phase 1: `JourneyRefused` on Approve/Allow/Grant/Accept, on Enter, on non-letter keys). Phase 2 adds no way around that.

## What the runner records, and what it never records

**Recorded:**
- **Correlation:**
  - the turn's `turn_id`;
  - the browser's `POST /api/generate` request and its SSE frame types (`text_chunk`, `human_required`, `code`, `done`, `error`), with their times;
  - the mirror stream's canonical events (`turn.started`, `turn.completed`, `turn.failed`, approvals, verifications), each with its numeric event ID and the `turn_id` in it.
- **What the face showed:**
  - the decision card appearing;
  - which control his click hit (Approve / Deny / Stop, by its label);
  - the receipt's kind (completed, verified, unverified, failed);
  - the body's named state in the DOM and whether the 3D body drew (phase 1's WebGL count);
  - where keyboard focus went.
- **The frame and input distributions** of phase 1, during the work.

**Never recorded:**
- the text he types or the model's words (frames are kept by type and size only);
- his operator id or any token or cookie;
- file contents.

The evidence record says so in its boundary, as phase 1's does.

## The journeys, one per criterion

| Journey | Criterion (points) | He does | The runner proves |
| --- | --- | --- | --- |
| `ask-01` | UX-01 (4), INT-02 (3) | asks for one small task and waits | one correlated run: his send → `turn.started` (event N) → work → decision/receipt → `turn.completed`, all one `turn_id`; the draft cleared only after admission; the body back at rest |
| `decide-01` | INT-04 (4) | asks for a change that needs approval; then Approve, Deny (second run) or Stop | the card appeared; his click alone moved it; the server's event follows his choice; after Deny or Stop, the held file is unchanged (read back through the backend) |
| `receipt-01` | INT-05 (3) | asks for work with a check, then work without one | "completed", "verified", "unverified" and "failed" never share a receipt; each matches the backend's verification event |
| `recover-01` | REC-01 (3), INT-06 (2) | starts a turn and waits | during the work the runner forces a WebGL loss and a network drop; the draft, the pending decision and the receipt survive; the view recovers once; exactly one `turn_id` and one backend task exist afterwards |
| `body-01` | BODY-01 (5) | runs `ask-01`, `decide-01` and a Stop | at each named state (working, approval, stopped, done, stale), the DOM's state and the 3D body's agree (the face's semantic attributes against the body's projection) |
| `keys-01` | A11Y-01 (4) | does `decide-01` with the keyboard only | no pointer event in the window; focus is visible at every step and comes back after each dialog; Stop and the receipt reachable by keys |
| `focus-01` | UX-02 (5), UX-03 (3) | two requests, switching between them, resizing, closing and reopening a workspace | identity, scroll and focus survive; history stays truthful; nothing steals focus |

## How it runs

```powershell
.\.venv\Scripts\python.exe tools\gagos_journeys.py open           # sign in, once
.\.venv\Scripts\python.exe tools\gagos_journeys.py watch ask-01   # then do the steps it prints
```

- **`watch <id>`** prints the steps for him and attaches to the open journey window, never a new one. It installs its observers, then waits up to 15 minutes for his send.
- **When it stops:** at the turn's terminal event or the time limit, writing the evidence record either way. A run whose turn never ended is recorded as such, never as a pass.
- **Where it runs:** the face as served (`localhost:5173`) or the built bundle. The record names the tree, the commit, the GPU and the window, as PERF-01's does.

## Points

A journey's pass earns its criterion's points only with:
- the operator signed in;
- a headed window on the named desktop;
- the build that ships;
- the record committed;
- for BODY-01 and the UX criteria, his visual sign-off as well.

A failed run is kept, and its finding becomes a goal or a fix.

## Order

1. **`ask-01`**, which builds the `watch` mechanics everyone else uses: attach, correlate, frame types, waiting.
2. **`decide-01`** and **`recover-01`**: the authority and recovery criteria.
3. **`receipt-01`** and **`keys-01`**.
4. **`body-01`** and **`focus-01`**: they need his visual sign-off.
