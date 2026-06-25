# P2-6 perf/assets + manualChunks + self-host Monaco — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the unused `specgloss.png` texture, split the Vite bundle so the 2D chrome paints earlier, lazy-mount the heavy 3D Canvas subtree, and self-host Monaco for offline use.

**Architecture:** A config-only + small product-wrapper change slice. The 3D scene is lazy-loaded inside `SuperbrainApp` while `GagosChrome` stays eager; Vite chunk groups are tuned to `react / drei+postprocessing / motion`; Monaco's loader is pointed at the local `monaco-editor` package before render.

**Tech Stack:** Vite 8 / Rolldown, React 19, `@monaco-editor/react`, `monaco-editor`.

---

## File map

- Delete: `frontend/public/textures/brain/specgloss.png`
- Modify: `GAG demo/gag-orchestrator/tools/port-to-frontend.mjs` (remove specgloss from ASSETS)
- Modify: `frontend/vite.config.js` (chunk groups)
- Modify: `frontend/src/superbrain/SuperbrainApp.jsx` (lazy WorkspaceCanvas + Suspense)
- Modify: `frontend/package.json` (add `monaco-editor` dependency)
- Create: `frontend/src/superbrain/lib/monacoConfig.ts` (loader config)
- Modify: `frontend/src/main.jsx` (import monacoConfig before render)

---

## Task 1: Remove the unused `specgloss.png` texture

**Files:**
- Delete: `frontend/public/textures/brain/specgloss.png`
- Modify: `GAG demo/gag-orchestrator/tools/port-to-frontend.mjs:44-46`

- [ ] **Step 1: Delete the product copy**

```bash
rm frontend/public/textures/brain/specgloss.png
```

Expected: file no longer exists.

- [ ] **Step 2: Remove specgloss from the port tool ASSETS array**

The file uses CRLF line endings. Match the exact line plus trailing comma:

```js
  ['public/textures/brain/specgloss.png', 'public/textures/brain/specgloss.png'],
```

Edit `GAG demo/gag-orchestrator/tools/port-to-frontend.mjs` to remove that line. The ASSETS array should then read:

```js
const ASSETS = [
  ['public/models/brain.glb', 'public/models/brain.glb'],
  ['public/grain.svg', 'public/grain.svg'],
  // The operator's hand-painted cortex (BRAIN_SURFACE 'organ' samples these
  // product copies — the GLB still ships stripped; his source is untouched).
  ['public/textures/brain/diffuse.png', 'public/textures/brain/diffuse.png'],
  ['public/textures/brain/normal.png', 'public/textures/brain/normal.png'],
];
```

- [ ] **Step 3: Confirm the canon break-glass**

Run: `python tools/check_canon_frozen.py --allow-canon`
Expected: exit 0, no remaining violations (the deletion is intentional).

---

## Task 2: Tune Vite chunk groups

**Files:**
- Modify: `frontend/vite.config.js:55-81`

- [ ] **Step 1: Replace the `codeSplitting.groups` array**

Change the `build.rollupOptions.output.codeSplitting.groups` to:

```js
            groups: [
              // ORDER MATTERS: first matching group wins. three.js core must be
              // matched before drei/r3f so the ~600 KB monolith lands here.
              { name: 'vendor-three', test: /[\\/]node_modules[\\/]three[\\/]/ },
              { name: 'vendor-drei-postprocessing', test: /[\\/]node_modules[\\/](@react-three[\\/]drei|postprocessing|@react-three[\\/]postprocessing)[\\/]/ },
              { name: 'vendor-r3f', test: /[\\/]node_modules[\\/]@react-three[\\/]/ },
              { name: 'vendor-monaco', test: /[\\/]node_modules[\\/](@monaco-editor|monaco-editor)[\\/]/ },
              { name: 'vendor-react', test: /[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/ },
              { name: 'vendor-motion', test: /[\\/]node_modules[\\/]motion[\\/]/ },
            ],
```

- [ ] **Step 2: Build and inspect chunks**

Run: `cd frontend && npm run build`
Expected: exit 0; `dist/assets/` contains `vendor-drei-postprocessing-*.js`, `vendor-motion-*.js`, and `vendor-monaco-*.js`.

---

## Task 3: Lazy-mount the 3D Canvas subtree

**Files:**
- Modify: `frontend/src/superbrain/SuperbrainApp.jsx`

- [ ] **Step 1: Convert WorkspaceCanvas to a lazy import and wrap in Suspense**

Replace the top of the file with:

```jsx
import { lazy, Suspense } from 'react';
import GagosChrome from '../workbench/GagosChrome';
import SuperbrainReactiveEffects from '../workbench/SuperbrainReactiveEffects';
import './superbrain.css';

const WorkspaceCanvas = lazy(() => import('@/components/canvas/WorkspaceCanvas'));

export default function SuperbrainApp() {
  return (
    <div className="font-sans antialiased">
      <Suspense fallback={null}>
        <WorkspaceCanvas>
          <SuperbrainReactiveEffects />
        </WorkspaceCanvas>
      </Suspense>
      <main aria-label="GAGOS">
        <GagosChrome />
      </main>
    </div>
  );
}
```

> `GagosChrome` stays eager so the 2D command chrome paints before the heavy 3D chunk parses. The existing `index.html` boot overlay covers the blank frame.

- [ ] **Step 2: Run product tests**

Run: `cd frontend && npm test -- --run`
Expected: 56 test files, 337+ tests pass. If a test renders `SuperbrainApp` before the lazy chunk resolves, add an `await findByTestId('mock-being')` or wrap with `waitFor`.

---

## Task 4: Self-host Monaco

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/superbrain/lib/monacoConfig.ts`
- Modify: `frontend/src/main.jsx`

- [ ] **Step 1: Add `monaco-editor` to dependencies**

Add to `frontend/package.json` `dependencies`:

```json
    "monaco-editor": "^0.55.1",
```

Run: `cd frontend && npm install`
Expected: `monaco-editor` is listed in `node_modules` and `package-lock.json`.

- [ ] **Step 2: Create the loader config module**

Create `frontend/src/superbrain/lib/monacoConfig.ts`:

```ts
import { loader } from '@monaco-editor/loader';
import * as monaco from 'monaco-editor';

loader.config({ monaco });
```

- [ ] **Step 3: Import the config before render**

In `frontend/src/main.jsx`, add the import before `createRoot(...).render(...)`:

```jsx
import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { ErrorBoundary } from './components/ErrorBoundary.jsx'
import './superbrain/lib/monacoConfig'

const SuperbrainApp = lazy(() => import('./superbrain/SuperbrainApp.jsx'))
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: exit 0.

---

## Task 5: Verify all gates

- [ ] **Step 1: Canon guard (frozen assets)**

Run: `python tools/check_canon_frozen.py --allow-canon`
Expected: exit 0.

- [ ] **Step 2: CSS canon guard**

Run: `python tools/check_css_canon.py`
Expected: exit 0.

- [ ] **Step 3: Full product test suite**

Run: `cd frontend && npm test -- --run`
Expected: 56 test files, 337+ tests pass.

- [ ] **Step 4: Production build**

Run: `cd frontend && npm run build`
Expected: exit 0; no chunk-size warnings.

- [ ] **Step 5: Update continuity docs**

- Add a P2-6 row to `.aios/state/RESUME.md` with the test/build evidence.
- Mark P2-6 done in the TODO list and choose the next backlog item.

---

## Spec coverage check

| Spec requirement | Task covering it |
|------------------|------------------|
| Drop `specgloss.png` from product + port | Task 1 |
| `react / drei+postprocessing / motion` grouping | Task 2 |
| Lazy-mount heavy Canvas | Task 3 |
| Self-host Monaco (`monaco-editor` + loader config) | Task 4 |
| Verify typecheck/tests/build/canon | Task 5 |
