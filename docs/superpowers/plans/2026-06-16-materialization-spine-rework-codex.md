# P3 REWORK — Surfaces belong to the SPINE (live 3D chat box + vertebra-seated tabs) — Codex Build Spec

**Date:** 2026-06-16 · **Owner:** operator · **Planner/Reviewer:** Claude · **Writer:** Codex
**Base:** current `feat/living-being-p1` working tree (P3.1 landed `1b925a7`, P3.2 uncommitted — **this reworks both**)
**Coordination task:** `materialization-spine-rework-codex`

## 0. Why this rework (operator verdict — heed it)

The P3.1/P3.2 approach was **rejected**: surfaces sprouted from a **stray cortex nerve** as **flat translucent Html panels** that floated over and *obscured* the being. That **ignored the whole reason we built the spinal cord + vertebrae** — they ARE the tab-seats / the conductor. Fix the **origin** (spine/vertebrae, not a cortex nerve) and the **form** (the chat box must be a real **3D box**, not flat chrome). Surfaces must read as **grown from the being's own anatomy** and must **not cover the spine**.

Operator's exact words: *"chatbox is a live 3D box which shows what I am typing; and work tab should slide out from a vertebra of the spine."*

## 1. Chat / input → a LIVE 3D BOX at the brainstem intake (PURE 3D, no Html)

- **Form:** a genuine **3D box** — a small slab/console with real depth and a **luminous emissive frame in the being's palette** (reuse the nerve/brain palette + a soft glow), rendered as **three.js geometry**. **NOT** a `<Html>` translucent `<div>`. The chat box shows only text, so it needs **zero DOM** — build it from a box/rounded-rect mesh + drei `<Text>`.
- **Live text:** the user's current draft (mirror the hidden-input value from `BrainstemIntake`) rendered as **3D `<Text>`** on the box face — **large, bright, clearly legible** (this is the operator's core complaint: he must clearly see what he types). Caret optional.
- **Origin/anchor:** it **emerges from the brainstem intake** (`INTAKE_LOCAL ≈ (0,-1.08,-0.42)` — where you speak into the being), growing/scaling in when typing starts. **Not** a cortex nerve. Place it so it **does not cover the cord/spine** (offset forward/beside the intake).
- **Lifecycle:** updates per keystroke (live); on **Enter** → the text releases **up the cord** (the existing P2 `question` rise) and the box dissolves; **Esc**/empty → dissolves.
- This is `kind:'input'` → **pure-3D render path** (box mesh + `<Text>`), no `<Html>`.

## 2. Work / content tab → SLIDES OUT FROM A VERTEBRA of the spine

- **Origin/anchor:** on a work intent (`sendDirective` → `CODE EMITTED`), the content tab materializes by **sliding/extending OUT FROM A VERTEBRA** — use the exported **`SEGMENT_ANCHORS`** (from `NervousSystem.tsx`; the materialization layer is already mounted inside the brain group, so these anchors are in-frame). Pick the next free anchor (P3: one tab → one vertebra; multi-tab seating across vertebrae is P4).
- **Motion:** the slab **emerges from the vertebra** (slide/unfold laterally + forward from that spine segment) and stays **tethered to that vertebra** (a short feed along the spine, not a cortex umbilical). It must read as "the spine produced this," and must **not occlude the cord** (extend outward/forward, leave the spine visible).
- **Content:** real `CodeCanvas` via `<Html transform occlude>` is fine here (a real editor needs DOM) — but the **surface is seated at the vertebra** and framed/lit as part of the being. Keep it lazy.
- `kind:'content'`.

## 3. Approval → a surface from a VERTEBRA (the being asking permission)

- When a directive pauses (`subscribeApproval`), the approval surface **slides from a vertebra** (the seat where the work will go), showing the capability + diff + the existing **3D Approve/Reject click-targets** (keep those — they were correct). Approve → `approvePendingApproval()` → directive resumes → the content tab seats at the vertebra. Origin = spine/vertebra, not cortex nerve.

## 4. What changes vs the current code (rework, not rewrite)

- **Keep & reuse:** `tabStore` (`kind` union, `useSyncExternalStore`), the 3D Approve/Reject controls, `intentRouting`, the `CODE EMITTED`/`subscribeApproval` triggers, the P2 conversation flow.
- **Change in `MaterializedTab`/`MaterializationLayer`:**
  - **Origin:** from a **vertebra `SEGMENT_ANCHORS[i]`** (content/approval) or the **brainstem intake** (input) — remove the cortex-point nerve-reach origin.
  - **Motion:** **slide-out-from-vertebra** (content/approval) / **grow-from-intake** (input) — replace the cortex "nerve reach."
  - **Form for `kind:'input'`:** pure-3D box + `<Text>` (drop `<Html>` for input).
  - **Don't occlude the spine:** offset surfaces outward; keep the cord/vertebrae visible.

## 5. Constraints / gates (unchanged + reinforced)

- **All-3D:** chat box = pure 3D; Approve/Reject = 3D meshes; content tab = `<Html transform>` (the only DOM, the content bridge) seated on the spine. **No flat translucent chrome floating over the being. Nothing that covers the spine.**
- **Cortex/brain byte-identical.** **No new npm dep.** Reuse the one primitive (`kind`). No P1/P2 regressions.
- **Gates green:** `npm run typecheck` + `npm test` (TDD new pure logic — vertebra-seat selection, input-box state). Commit files (no untracked).
- **Final look = operator's browser.** I (Claude) will this time judge whether each surface **belongs to the being, uses the spine, is clearly readable, and doesn't cover the spine** — not just "it renders."

## 6. Verification (operator's browser — the real gate)
1. **Type** → a luminous **3D box** appears at the brainstem showing your text **big + bright**; Enter → text rises up the cord, box dissolves. The cord stays visible.
2. **Work intent (+approve)** → a tab **slides out from a vertebra**, code inside, the spine feeding it; the spine is not covered.
3. Brain at REST identical; conversation intact; 60fps; no flat chrome anywhere.

## 7. Handoff
- Task `materialization-spine-rework-codex`. Claim the lease, rework **§1 input box → §2 work tab → §3 approval** (operator-gated between), gates green, hand to Claude. Don't invent — `// CLAUDE?:` + flag. Commit files.
