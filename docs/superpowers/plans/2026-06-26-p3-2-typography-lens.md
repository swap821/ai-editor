# P3-2 Typography Lens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the remaining Fable typography findings in the GAG lab so the HUD's type system is consistent, legible, and truthful.

**Architecture:** Two-file CSS/label touch-up. `globals.css` receives token, feature-settings, weight, tracking, and size normalizations. `SuperbrainHUD.tsx` receives one string change for the secure-button default label. No new modules, no tests (CSS-only lens; existing lab suite is the regression guard).

**Tech Stack:** TypeScript/React (lab), CSS, Vitest (existing suite), Git.

---

## File mapping

| File | Responsibility |
|---|---|
| `GAG demo/gag-orchestrator/src/app/globals.css` | Token fixes, OpenType feature scoping, type-scale normalization, weight unification. |
| `GAG demo/gag-orchestrator/src/components/ui/SuperbrainHUD.tsx` | Secure-button visible label string. |

---

## Task 1: Scope the `case` OpenType feature to caps roles

**Files:**
- Modify: `GAG demo/gag-orchestrator/src/app/globals.css` (root `html` rule and new grouped rule)

- [ ] **Step 1: Remove global `case` feature from `html`**

In `GAG demo/gag-orchestrator/src/app/globals.css`, change:

```css
html {
  font-feature-settings: "case" 1, "cv05" 1;
}
```

to:

```css
html {
  font-feature-settings: "cv05" 1;
}
```

- [ ] **Step 2: Add caps-role rule with both `case` and `cv05`**

Append this grouped rule immediately after the `html` rule (or near the other feature-settings rules):

```css
/* Caps roles need cap-height punctuation; cv05 is re-declared because
   font-feature-settings replaces rather than merges. */
.system-summary,
.eyebrow,
.build-tag,
.core-sub,
.command-field label,
.source-name strong,
.approval-title {
  font-feature-settings: "case" 1, "cv05" 1;
}
```

- [ ] **Step 3: Verify the edit with grep**

Run:

```bash
cd "GAG demo/gag-orchestrator" && grep -n 'font-feature-settings' src/app/globals.css
```

Expected output shows exactly two rules: the `html` rule with `"cv05" 1` and the caps-role grouped rule with `"case" 1, "cv05" 1`.

- [ ] **Step 4: Commit**

```bash
cd "GAG demo/gag-orchestrator" && \
git add src/app/globals.css && \
git commit -m "fix(typography): scope case feature to caps roles only"
```

---

## Task 2: Raise `--text-3` alpha and pin-graph em opacity

**Files:**
- Modify: `GAG demo/gag-orchestrator/src/app/globals.css`

- [ ] **Step 1: Raise `--text-3` alpha from 0.38 to 0.48**

In `GAG demo/gag-orchestrator/src/app/globals.css`, change:

```css
  --text-3: rgba(120, 130, 150, 0.38);
```

to:

```css
  --text-3: rgba(120, 130, 150, 0.48);
```

- [ ] **Step 2: Raise `.region-pin-graph em` opacity from 0.6 to 0.8**

Locate `.region-pin-graph em` and change:

```css
.region-pin-graph em {
  font-style: normal;
  font-size: 9px;
  opacity: 0.6;
}
```

to:

```css
.region-pin-graph em {
  font-style: normal;
  font-size: 9px;
  opacity: 0.8;
}
```

- [ ] **Step 3: Verify with grep**

Run:

```bash
cd "GAG demo/gag-orchestrator" && grep -n 'text-3:' src/app/globals.css && grep -n 'region-pin-graph em' -A 3 src/app/globals.css
```

Expected: `--text-3: rgba(120, 130, 150, 0.48);` and `opacity: 0.8;`.

- [ ] **Step 4: Commit**

```bash
cd "GAG demo/gag-orchestrator" && \
git add src/app/globals.css && \
git commit -m "fix(typography): raise text-3 legibility and pin-graph em opacity"
```

---

## Task 3: Normalize approval-panel type scale

**Files:**
- Modify: `GAG demo/gag-orchestrator/src/app/globals.css`

- [ ] **Step 1: Normalize `.approval-title` tracking**

Change:

```css
.approval-title {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.22em;
  color: #ffb454;
}
```

to:

```css
.approval-title {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.12em;
  color: #ffb454;
}
```

- [ ] **Step 2: Normalize `.approval-summary` size**

Change:

```css
.approval-summary {
  font-size: 12.5px;
  color: var(--text-1);
}
```

to:

```css
.approval-summary {
  font-size: 13px;
  color: var(--text-1);
}
```

- [ ] **Step 3: Normalize `.approval-actions button` size and tracking**

Change:

```css
.approval-actions button {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.18em;
  padding: 7px 16px;
  border-radius: 6px;
  cursor: pointer;
  transition: opacity 200ms var(--ease-out-quart), transform 120ms var(--ease-out-quart),
    background 200ms var(--ease-out-quart), border-color 200ms var(--ease-out-quart),
    color 200ms var(--ease-out-quart);
}
```

to:

```css
.approval-actions button {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.12em;
  padding: 7px 16px;
  border-radius: 6px;
  cursor: pointer;
  transition: opacity 200ms var(--ease-out-quart), transform 120ms var(--ease-out-quart),
    background 200ms var(--ease-out-quart), border-color 200ms var(--ease-out-quart),
    color 200ms var(--ease-out-quart);
}
```

- [ ] **Step 4: Verify off-token values are gone**

Run:

```bash
cd "GAG demo/gag-orchestrator" && grep -n '0.22em\|12.5px\|10.5px\|0.18em' src/app/globals.css
```

Expected: no matches in the approval-panel region (or anywhere if these were the only uses).

- [ ] **Step 5: Commit**

```bash
cd "GAG demo/gag-orchestrator" && \
git add src/app/globals.css && \
git commit -m "fix(typography): normalize approval-panel type scale to token grid"
```

---

## Task 4: Unify secure-button case discipline

**Files:**
- Modify: `GAG demo/gag-orchestrator/src/components/ui/SuperbrainHUD.tsx`
- Modify: `GAG demo/gag-orchestrator/src/app/globals.css`

- [ ] **Step 1: Change visible shield label to all-caps**

In `GAG demo/gag-orchestrator/src/components/ui/SuperbrainHUD.tsx`, locate the secure-button children and change:

```tsx
{telemetry?.chainValid === false
  ? 'TAMPER'
  : approvalHold
    ? 'HOLD'
    : 'Supervised'}
```

to:

```tsx
{telemetry?.chainValid === false
  ? 'TAMPER'
  : approvalHold
    ? 'HOLD'
    : 'SUPERVISED'}
```

Leave the `title` tooltip and the `sr-only role="status"` span in sentence case — only the visible label changes.

- [ ] **Step 2: Add letter-spacing to `.secure-button`**

In `GAG demo/gag-orchestrator/src/app/globals.css`, change:

```css
.secure-button {
  justify-self: end;
  gap: 8px;
  padding: 8px 14px;
  border: 1px solid var(--hairline);
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.02);
  color: var(--text-2);
  font-size: 11px;
  cursor: pointer;
  transition: border-color 200ms var(--ease-out-quart), color 200ms var(--ease-out-quart),
    box-shadow 200ms var(--ease-out-quart), transform 200ms var(--ease-out-quart);
}
```

to:

```css
.secure-button {
  justify-self: end;
  gap: 8px;
  padding: 8px 14px;
  border: 1px solid var(--hairline);
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.02);
  color: var(--text-2);
  font-size: 11px;
  letter-spacing: 0.08em;
  cursor: pointer;
  transition: border-color 200ms var(--ease-out-quart), color 200ms var(--ease-out-quart),
    box-shadow 200ms var(--ease-out-quart), transform 200ms var(--ease-out-quart);
}
```

- [ ] **Step 3: Verify**

Run:

```bash
cd "GAG demo/gag-orchestrator" && grep -n "'Supervised'" src/components/ui/SuperbrainHUD.tsx && grep -n 'letter-spacing: 0.08em' -B 2 src/app/globals.css
```

Expected: no output for `'Supervised'` (the all-caps label should be `'SUPERVISED'`); the CSS grep shows `letter-spacing: 0.08em;` on `.secure-button`.

- [ ] **Step 4: Commit**

```bash
cd "GAG demo/gag-orchestrator" && \
git add src/components/ui/SuperbrainHUD.tsx src/app/globals.css && \
git commit -m "fix(typography): unify secure-button case and tracking"
```

---

## Task 5: Unify section-label weight to 510

**Files:**
- Modify: `GAG demo/gag-orchestrator/src/app/globals.css`

- [ ] **Step 1: Add weight 510 to `.objective-head`**

Locate `.objective-head` and change:

```css
.objective-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.12em;
  color: var(--text-2);
}
```

to:

```css
.objective-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 510;
  letter-spacing: 0.12em;
  color: var(--text-2);
}
```

- [ ] **Step 2: Add weight 510 to `.agent-heading span`**

Locate `.agent-heading span` and change:

```css
.agent-heading span {
  color: var(--text-2);
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.12em;
}
```

to:

```css
.agent-heading span {
  color: var(--text-2);
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 510;
  letter-spacing: 0.12em;
}
```

- [ ] **Step 3: Add weight 510 to `.terminal-log span`**

Locate `.terminal-log span` and change:

```css
.terminal-log span {
  margin-bottom: 3px;
  color: var(--text-3);
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.12em;
}
```

to:

```css
.terminal-log span {
  margin-bottom: 3px;
  color: var(--text-3);
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 510;
  letter-spacing: 0.12em;
}
```

- [ ] **Step 4: Verify**

Run:

```bash
cd "GAG demo/gag-orchestrator" && grep -n 'font-weight: 510' src/app/globals.css | head -n 10
```

Expected: `.eyebrow`, `.objective-head`, `.agent-heading span`, and `.terminal-log span` all show `font-weight: 510`.

- [ ] **Step 5: Commit**

```bash
cd "GAG demo/gag-orchestrator" && \
git add src/app/globals.css && \
git commit -m "fix(typography): unify section-label weights to 510"
```

---

## Task 6: Run lab verification gates

**Files:**
- All lab tests and golden images.

- [ ] **Step 1: Run the full lab test suite**

```bash
cd "GAG demo/gag-orchestrator" && npm test
```

Expected: all existing tests pass (baseline before this lens: 387 passed). No new failures.

- [ ] **Step 2: Verify goldens are untouched**

```bash
cd "GAG demo/gag-orchestrator" && git status --short goldens/
```

Expected: empty output (no golden changes).

- [ ] **Step 3: Run lint on the touched JSX file**

```bash
cd "GAG demo/gag-orchestrator" && npx eslint src/components/ui/SuperbrainHUD.tsx
```

Expected: exit 0. The lab has no CSS linter; CSS correctness is covered by the test suite and golden comparison. Note that the lab's full `npm run lint` may still fail on pre-existing issues elsewhere.

- [ ] **Step 4: Final lens commit**

If all gates pass, create a single aggregate commit (or keep the per-task commits — both are acceptable; the previous lenses used a single final commit):

```bash
cd "GAG demo/gag-orchestrator" && \
git add -A && \
git commit -m "fix(typography): complete P3-2 Typography Lens

- Scope case OpenType feature to caps roles.
- Raise --text-3 alpha and region-pin-graph em opacity.
- Normalize approval-panel sizes/trackings to token grid.
- Unify secure-button to SUPERVISED with caps tracking.
- Unify section-label weights to 510.
- Lab tests pass; goldens unchanged; lint clean on touched files."
```

---

## Task 7: Update builder coordination and RESUME

**Files:**
- Modify: `.aios/state/RESUME.md`
- Use: `python agent_coord.py`

- [ ] **Step 1: Update RESUME.md**

In `.aios/state/RESUME.md`, update the P3-2 Typography Lens section to record implementation completion and test counts. Move the section under a completed heading if appropriate. Update the single next action to the next RENOVATION_PLAN item or to operator review/port decision.

- [ ] **Step 2: Commit RESUME update**

```bash
git add .aios/state/RESUME.md && \
git commit -m "docs(resume): P3-2 typography lens implemented in lab"
```

- [ ] **Step 3: Release builder lease and hand off for review**

```bash
python agent_coord.py handoff p3-2-typography-lens --agent kimi --to claude --reason "P3-2 Typography Lens implemented in GAG lab; awaiting review."
```

---

## Self-review checklist

- [ ] Spec coverage: every remaining typography finding has a task above.
- [ ] Placeholder scan: no "TBD", "TODO", or "implement later".
- [ ] Exact file paths: all paths use `GAG demo/gag-orchestrator/...` and `.aios/state/RESUME.md`.
- [ ] The `Supervised` label change does not alter the tooltip or screen-reader span.
- [ ] The global `case` feature is removed and re-added only to caps roles.

## Execution choice

Plan complete and saved to `docs/superpowers/plans/2026-06-26-p3-2-typography-lens.md`.

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.
