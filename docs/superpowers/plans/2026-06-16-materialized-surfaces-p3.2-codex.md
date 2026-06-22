# P3.2 — Materialized Input + Approval Surfaces (everything grows from the nerves) — Codex Build Spec

**Date:** 2026-06-16 · **Owner:** operator · **Planner/Reviewer:** Claude · **Writer:** Codex
**Base (hash-pin):** the P3.1 commit (see handoff message) on `feat/living-being-p1`
**Coordination task:** `materialized-surfaces-p3.2-codex`
**Operator directive:** "whenever a random key is pressed it generates a 3D chat box from its nerves so the user can see what he's typing; and for approval it should generate a 3D approval box, again from the nerves."

---

## 0. The unifying principle (why this is one mechanism, not two hacks)

Per the one law — *everything you see grew out of the being* — the **typing box, the approval box, and the work/code tabs are the SAME primitive: a 3D surface the being materializes from a nerve.** Extend the P3.1 materialization primitive with a **`kind`**: `'input' | 'approval' | 'content'`. Same reach→unfurl→umbilical birth; different fill + lifecycle per kind. Do NOT build separate one-off systems.

## 1. Reuse (base = P3.1)
- `MaterializedTab.tsx` / `MaterializationLayer.tsx` / `tabStore.ts` — the nerve-reach → slab-unfurl → `<Html transform>` primitive. Add a `kind` field to the tab record + a per-kind render branch + per-kind spawn.
- `BrainstemIntake.jsx` — already has the **invisible hidden `<input>`** capturing keystrokes (the `'Brainstem typing fallback'`), the live `draftText`, `submitTurn`, and the `'question'`/reply phases. The input box **mirrors that draft**; keep the hidden input as the capture device (caret/IME), surface its value on the 3D box.
- **Approval API (already complete) in `aiosAdapter.ts`:**
  - `subscribeApproval(listener)` (line ~190) → invoked immediately + on every change with the pending approval (or null). **This is the single source of truth the approval box binds to.**
  - The pending object (line ~151–176): `{ capability, diff (unified diff = the decision surface), file, token, … }`.
  - `approvePendingApproval(): Promise<DirectiveResult>` (line ~447) — approve (publishes `'approval-resolved'`/`'approved'`, resumes the directive → it then emits the `code` frame → a **content** tab materializes).
  - the reject path (line ~463–477, `POST /api/v1/approval/req` `approve:false`, publishes `'rejected'`).
  - `'approval-required'` cognition event already fires on the `human_required` frame (line ~262).

## 2. Build — phased (each is an operator browser-gate)

### P3.2a — Materialized INPUT box (on typing)  [the visible-typing fix]
- **Trigger:** on the FIRST printable keypress of a new draft (the existing global keydown / hidden-input focus path in `BrainstemIntake`) → spawn a `kind:'input'` materialized surface (one at a time) via the tabStore, born from a nerve at the **brainstem/cortex**, unfurling to a readable spot (near the intake / lower-center, camera-facing).
- **Fill:** the **live draft text** (mirror `draftText` / the hidden input value), large + legible + lit, with a soft caret. Render as `<Text>` on a framed slab OR `<Html transform>` showing the value — your call, but it must be **clearly readable** (this replaces the current faint floating ghost text, which the operator can't read well).
- **Lifecycle:** updates live as the user types; on **Enter** → `submitTurn` (existing) fires, the box **retracts/dissolves** as the question rises up the cord (the existing `'question'` flow). On **Esc**/empty → dissolve. Reduced-motion: skip the reach tween, just show/hide.
- Retire/replace the faint draft `<Text>` so there aren't two competing displays.

### P3.2b — Materialized APPROVAL box (on a pause)  [unblocks the materialization demo]
- **Trigger:** `subscribeApproval` fires with a non-null pending approval (a supervised directive paused on `human_required`) → spawn a `kind:'approval'` materialized surface from a nerve (reach from the cortex; this is the being asking permission), center-forward.
- **Fill:** the pending **capability/action** + the **unified `diff`** (the decision surface — show it, scrollable if long) on the slab via `<Html transform>` (reuse a diff/code view; `CodeCanvas` can render the diff text, or a simple pre). Plus two **in-scene 3D controls**: **APPROVE** and **REJECT** (3D click-targets — meshes/Text with `onClick`, NOT DOM buttons).
- **Actions:** APPROVE → `approvePendingApproval()`; REJECT → the reject call. On resolve (`'approval-resolved'`) → the box **dissolves**; if approved, the directive resumes and its `code` frame spawns the **content** tab (P3.1 path) — so the operator sees: work intent → approval box → approve → tab. RED-zone capabilities stay refused per policy (don't offer approve if the server marks it forbidden).
- **One approval at a time**; if another arrives while one is open, queue or replace (simplest: the store holds the current pending — bind to `subscribeApproval`'s single truth).

### P3.2c — (after a+b) live code streaming into the content tab
- The original P3.2: stream the `code`/`text_chunk` into the content slab live (beads pulse on the umbilical per chunk). Additive export on `aiosAdapter` if needed; don't change existing behavior.

## 3. Constraints / gates
- **All-3D:** every surface is born from a nerve and rendered in-scene (`<Html transform>` / 3D `<Text>` / 3D click-targets). The hidden input stays **invisible** (capture only). **No visible 2D DOM chrome, no DOM buttons.**
- **Cortex/brain byte-identical** — materialization is the additive layer; no cortex edits.
- **Reuse the ONE primitive** — `kind` on the tab record; do not fork MaterializedTab into three components (a per-kind render branch is fine; share the reach/unfurl/umbilical).
- **No regressions** — P1 growth, P2 conversation, P3.1 content tab, steady glow, 4-draw-call nerve bundles all intact.
- **No new npm dep** (continue `useSyncExternalStore`).
- **Gates green** before each handoff: `cd frontend && npm run typecheck` + `npm test` (TDD the new pure logic — tabStore `kind` reducers, the input/approval spawn guards). Changed-file lint clean. **Commit your files** (don't leave untracked).
- **Final look = operator's browser** (`:5177`). Hand to Claude per sub-phase.

## 4. Verification (operator's browser)
1. Start typing → a **3D box grows from a nerve** showing your text **clearly** (you can read what you type); Enter → it dissolves as the question rises.
2. A work intent that pauses → a **3D approval box grows from a nerve** with the action/diff + Approve/Reject; **Approve → a content tab materializes** (the full chain finally visible end-to-end); Reject → dissolves.
3. Brain at REST identical; conversation still works; no 2D chrome; 60fps high-tier.

## 5. Handoff protocol
- Task `materialized-surfaces-p3.2-codex`. Claim the lease, build **P3.2a → P3.2b → P3.2c** (operator-gated between a/b/c), gates green, hand to Claude (`agent_coord.py message`). `verdict` rejects on snapshot drift — a `message` is the approval-of-record fallback. Don't invent — `// CLAUDE?:` + flag. Commit new files.
