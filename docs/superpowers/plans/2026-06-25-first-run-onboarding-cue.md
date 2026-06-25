# First-run onboarding cue — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single, dismissible first-run hint to `GagosChrome` that shows a ghost example directive in the input and a pointer to `▣ ORGANS / forge`, without touching the 3D scene.

**Architecture:** A new local-state/read `gagos-onboarding-hint-dismissed` flag drives a conditional placeholder and a chip rendered under the command dock. The hint is shown only after the existing multi-step coach is dismissed, so the two onboarding surfaces never stack on a brand-new operator.

**Tech stack:** React 19, Vite, Vitest, Testing Library, existing `GagosChrome.jsx` / `.css` canon tokens.

---

## File map

- `frontend/src/workbench/GagosChrome.jsx` — add hint state, dismiss handler, placeholder logic, and chip markup.
- `frontend/src/workbench/GagosChrome.css` — add `.gagos-hint` / `.gagos-hint__dismiss` styles using canon colors.
- `frontend/src/workbench/GagosChrome.onboarding.test.tsx` — extend existing onboarding tests with hint presence / dismissal / localStorage behavior.

---

## Constants

```jsx
const EXAMPLE_DIRECTIVE = "Try: 'scaffold a FastAPI /health endpoint'";
const HINT_DISMISSED_KEY = 'gagos-onboarding-hint-dismissed';
```

---

## Task 1: Read the dismissed flag on mount

**Files:**
- Modify: `frontend/src/workbench/GagosChrome.jsx:185-191`

Add a new state + effect alongside the existing `onboarded` effect.

- [ ] **Step 1: Add state and effect**

Add near the existing `onboarded` state:

```jsx
const [hintDismissed, setHintDismissed] = useState(true);
```

Add an effect right after the `onboarded` effect (around line 285):

```jsx
// First-run hint: only prompt once; localStorage failure silently opts out.
useEffect(() => {
  try {
    setHintDismissed(!!window.localStorage.getItem(HINT_DISMISSED_KEY));
  } catch {
    setHintDismissed(true);
  }
}, []);
```

- [ ] **Step 2: Add dismiss callback**

Add near `finishOnboarding`:

```jsx
const dismissHint = useCallback(() => {
  try { window.localStorage.setItem(HINT_DISMISSED_KEY, '1'); } catch { /* storage may be blocked */ }
  setHintDismissed(true);
}, []);
```

---

## Task 2: Drive the input placeholder from the hint flag

**Files:**
- Modify: `frontend/src/workbench/GagosChrome.jsx:703-721`

Compute `showHint` before the return, near the `dock` derivation (around line 602):

```jsx
const showHint = !hintDismissed && onboarded && messages.length === 0 && !busy;
```

> Why `onboarded`? The multi-step coach already occupies the same zero-state moment; showing both would clutter the first run. The single hint appears only after the coach is dismissed (or on reload if the coach was already dismissed).

Change the input `placeholder`:

```jsx
placeholder={listening ? 'listening…' : showHint ? EXAMPLE_DIRECTIVE : 'talk to GAGOS…'}
```

---

## Task 3: Render the dismissible hint chip

**Files:**
- Modify: `frontend/src/workbench/GagosChrome.jsx:774-791`

Replace the existing standalone coach block wrapper with one that also renders the hint row **after** the coach when `showHint` is true.

Current block:

```jsx
{!onboarded && messages.length === 0 && !busy ? (
  <div className="gagos-coach" role="dialog" aria-label="Getting started">
    ...
  </div>
) : null}
```

Wrap it so the hint can share the same bottom-of-chat placement:

```jsx
{messages.length === 0 && !busy ? (
  <>
    {!onboarded ? (
      <div className="gagos-coach" role="dialog" aria-label="Getting started">
        {deriveCoachCards(milestones).map((text, i) => (
          <div key={i} className="gagos-coach__card">
            <p>{text}</p>
          </div>
        ))}
        <div className="gagos-coach__actions">
          <span />
          <button type="button" className="gagos-coach__primary" onClick={finishOnboarding}>
            Got it
          </button>
        </div>
      </div>
    ) : null}
    {showHint ? (
      <div className="gagos-hint" role="note" aria-label="Onboarding hint">
        <span className="gagos-hint__text">▣ ORGANS · forge (Ctrl+`)</span>
        <button
          type="button"
          className="gagos-hint__dismiss"
          onClick={dismissHint}
          aria-label="Dismiss onboarding hint"
          title="Dismiss onboarding hint"
        >
          ×
        </button>
      </div>
    ) : null}
  </>
) : null}
```

---

## Task 4: Style the hint chip with canon tokens

**Files:**
- Modify: `frontend/src/workbench/GagosChrome.css`

Add after the `.gagos-coach` block (around line 785):

```css
/* ── First-run hint chip ─────────────────────────────────────────────────
   Appears after the multi-step coach is dismissed; points the operator at
   ▣ ORGANS and the forge shortcut without touching the 3D being. */
.gagos-hint {
  pointer-events: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
  padding: 8px 10px 8px 14px;
  border-radius: 12px;
  background: rgba(6, 4, 15, 0.55);
  border: 1px solid rgba(123, 245, 251, 0.12);
  backdrop-filter: blur(12px) saturate(140%);
  -webkit-backdrop-filter: blur(12px) saturate(140%);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
  animation: gagos-hint-in 0.45s cubic-bezier(0.16, 1, 0.3, 1) 0.2s backwards;
}
.gagos-hint__text {
  font-size: 12px;
  font-weight: 400;
  letter-spacing: 0.01em;
  color: rgba(190, 202, 226, 0.78);
}
.gagos-hint__dismiss {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  font: inherit;
  font-size: 17px;
  line-height: 1;
  color: rgba(190, 202, 226, 0.7);
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease, transform 0.16s ease;
}
.gagos-hint__dismiss:hover {
  background: rgba(255, 255, 255, 0.12);
  color: rgba(244, 248, 255, 0.95);
}
.gagos-hint__dismiss:active { transform: scale(0.94); }
.gagos-hint__dismiss:focus-visible {
  outline: 2px solid rgba(123, 245, 251, 0.6);
  outline-offset: 2px;
}

@keyframes gagos-hint-in {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

@media (prefers-reduced-motion: reduce) {
  .gagos-hint { animation: none; }
}

@media (max-width: 640px) {
  .gagos-hint { margin-top: 10px; padding: 7px 9px 7px 12px; }
  .gagos-hint__text { font-size: 11.5px; }
}
```

---

## Task 5: Extend onboarding tests

**Files:**
- Modify: `frontend/src/workbench/GagosChrome.onboarding.test.tsx`

Update `beforeEach` to also clear the new key:

```tsx
window.localStorage.removeItem('gagos-onboarded');
window.localStorage.removeItem('gagos-onboarding-hint-dismissed');
```

Add three new test cases:

- [ ] **Step 1: Write the hint-visible test**

```tsx
it('shows the example placeholder and organs hint after the coach is dismissed', async () => {
  // Coach already dismissed -> hint should appear.
  window.localStorage.setItem('gagos-onboarded', '1');
  fetchOnboardingState.mockResolvedValue({
    firstDirective: false,
    firstApproval: false,
    firstVerify: false,
    firstCloudRoute: false,
    firstAutonomy: false,
  });

  const { default: GagosChrome } = await import('./GagosChrome');
  render(<GagosChrome />);

  await waitFor(() => {
    expect(screen.getByPlaceholderText(/Try: 'scaffold a FastAPI \/health endpoint'/i)).toBeInTheDocument();
  });
  expect(screen.getByRole('note', { name: /Onboarding hint/i })).toBeInTheDocument();
  expect(screen.getByText(/▣ ORGANS · forge/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Write the dismiss test**

```tsx
it('hides the hint and writes the dismissal flag when the X is clicked', async () => {
  window.localStorage.setItem('gagos-onboarded', '1');
  fetchOnboardingState.mockResolvedValue({
    firstDirective: false,
    firstApproval: false,
    firstVerify: false,
    firstCloudRoute: false,
    firstAutonomy: false,
  });

  const { default: GagosChrome } = await import('./GagosChrome');
  render(<GagosChrome />);

  await waitFor(() => {
    expect(screen.getByRole('note', { name: /Onboarding hint/i })).toBeInTheDocument();
  });

  await act(async () => {
    screen.getByRole('button', { name: /Dismiss onboarding hint/i }).click();
  });

  await waitFor(() => {
    expect(screen.queryByRole('note', { name: /Onboarding hint/i })).not.toBeInTheDocument();
  });
  expect(window.localStorage.getItem('gagos-onboarding-hint-dismissed')).toBe('1');
});
```

- [ ] **Step 3: Write the already-dismissed test**

```tsx
it('does not show the hint if it was already dismissed', async () => {
  window.localStorage.setItem('gagos-onboarded', '1');
  window.localStorage.setItem('gagos-onboarding-hint-dismissed', '1');
  fetchOnboardingState.mockResolvedValue({
    firstDirective: false,
    firstApproval: false,
    firstVerify: false,
    firstCloudRoute: false,
    firstAutonomy: false,
  });

  const { default: GagosChrome } = await import('./GagosChrome');
  render(<GagosChrome />);

  await waitFor(() => {
    expect(screen.queryByRole('note', { name: /Onboarding hint/i })).not.toBeInTheDocument();
  });
  expect(screen.getByPlaceholderText(/talk to GAGOS/i)).toBeInTheDocument();
});
```

---

## Task 6: Verify the gates

- [ ] **Step 1: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: exit 0, no new errors.

- [ ] **Step 2: Tests**

Run: `cd frontend && npm test -- --run GagosChrome.onboarding`
Expected: all tests pass.

Run: `cd frontend && npm test -- --run`
Expected: 56 test files, 334+ tests pass.

- [ ] **Step 3: Build**

Run: `cd frontend && npm run build`
Expected: exit 0.

- [ ] **Step 4: Canon guard**

Run: `python tools/check_css_canon.py`
Expected: no new off-palette colors in `GagosChrome.css`.

---

## Task 7: Update continuity docs

- [ ] **Step 1: Update `.aios/state/RESUME.md`**

Add a P3-3 row summarizing the change, test counts, and the next action.

- [ ] **Step 2: Update the TODO list**

Mark P3-3 as done and pick the next backlog item (P2-6, P2-3, P2-7, or P3-2).

---

## Spec coverage check

| Spec requirement | Task covering it |
|------------------|------------------|
| Ghost example directive as placeholder | Task 2 |
| `▣ ORGANS · forge` pointer chip | Task 3 |
| Dismissible with X | Tasks 3 + 5 |
| localStorage persistence across restarts | Tasks 1 + 5 |
| No 3D scene changes | File map (only `GagosChrome.jsx`/`.css`) |
| Accessibility (note role, dismiss label, focus ring) | Tasks 3 + 4 |
| Reduced-motion gating | Task 4 |
| Tests for presence/dismissal/hidden | Task 5 |
| Canon color usage | Task 4 + 6 |
