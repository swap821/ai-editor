# P2-6 perf/assets + manualChunks + self-host Monaco — design spec

**Date:** 2026-06-25  
**Scope:** `RENOVATION_PLAN.md` P2-6 — reduce first-paint payload, stop shipping unused texture bytes, and make Monaco available offline.  
**Constraint:** No change to the cherished 3D being / scene appearance.

---

## Goal

The product's first paint is currently blocked on one undifferentiated 1.35 MB chunk and a 264 KB texture (`specgloss.png`) that no shader samples. Monaco loads its engine from `cdn.jsdelivr.net`, breaking the local-first thesis for the code editor. This slice removes dead bytes, splits the bundle so the 2D chrome can paint earlier, and self-hosts Monaco.

## Current state (from investigation)

- `specgloss.png` exists in `frontend/public/textures/brain/` and is copied by the lab port tool, but `OrganSurface.tsx` only samples `diffuse.png` + `normal.png`.
- `vite.config.js` already uses Vite 8 `codeSplitting.groups` for `vendor-react`, `vendor-three`, `vendor-drei`, `vendor-postprocessing`, `vendor-r3f`, `vendor-monaco`. `motion` is not split out, and the task wants `drei+postprocessing` merged.
- `SuperbrainApp.jsx` imports `WorkspaceCanvas` synchronously, so the heavy 3D chunk blocks the 2D chrome.
- `@monaco-editor/react` is installed, but `monaco-editor` is only a peer (present in `node_modules` but not in `package.json`). No `loader.config` call exists; the wrapper will fall back to jsDelivr when an editor is rendered.

## Approach

### 1. Remove the unused `specgloss.png` texture

- Delete `frontend/public/textures/brain/specgloss.png`.
- Remove `['public/textures/brain/specgloss.png', ...]` from `GAG demo/gag-orchestrator/tools/port-to-frontend.mjs` ASSETS array.
- Run `tools/check_canon_frozen.py --allow-canon` to verify the deletion is intentional and the remaining frozen assets are intact.

**Trade-off:** The texture is canon-frozen. Removing it requires the break-glass flag, but it is unused and has no visual effect. The alternative — keeping it — wastes 264 KB on every deploy.

### 2. Adjust Vite chunk groups

Change `frontend/vite.config.js` `codeSplitting.groups` to:

- `vendor-react` — `react`, `react-dom`, `scheduler`.
- `vendor-drei-postprocessing` — `@react-three/drei` + `postprocessing` + `@react-three/postprocessing`.
- `vendor-motion` — `motion` (framer-motion successor).
- `vendor-monaco` — `@monaco-editor/*` + `monaco-editor`.
- `vendor-three` — `three`.
- `vendor-r3f` — `@react-three/fiber`.

Merging drei and postprocessing reduces the number of parallel fetches and matches the task's desired grouping. Adding `motion` prevents it from bloating the main chunk. Including `monaco-editor` in the monaco group ensures self-hosted Monaco isn't split into an unexpected chunk.

### 3. Lazy-mount the Canvas subtree

In `frontend/src/superbrain/SuperbrainApp.jsx`:

- Convert `import WorkspaceCanvas from '@/components/canvas/WorkspaceCanvas'` to `const WorkspaceCanvas = lazy(() => import('@/components/canvas/WorkspaceCanvas'))`.
- Wrap `<WorkspaceCanvas>` in `<Suspense fallback={null}>`.
- Keep `GagosChrome` synchronous so the 2D command chrome paints before the 3D chunk is parsed.

The existing `index.html` boot overlay covers the initial blank frame, so lazy loading does not introduce a new flash.

### 4. Self-host Monaco

- Add `monaco-editor` to `frontend/package.json` dependencies (pin to the version already present as a peer, `^0.55.1`).
- Create `frontend/src/superbrain/lib/monacoConfig.ts` that imports `loader` from `@monaco-editor/loader`, imports * as monaco from `monaco-editor`, and calls `loader.config({ monaco })`.
- Import `../superbrain/lib/monacoConfig` in `frontend/src/main.jsx` before `createRoot(...).render(...)` so the loader is configured before any editor mounts.

No UI component currently renders Monaco, so this slice only prepares the loader. A future forge/classic-IDE editor will use the local package automatically.

## Files touched

- `frontend/public/textures/brain/specgloss.png` — delete.
- `GAG demo/gag-orchestrator/tools/port-to-frontend.mjs` — remove specgloss from ASSETS.
- `frontend/vite.config.js` — adjust chunk groups.
- `frontend/src/superbrain/SuperbrainApp.jsx` — lazy import WorkspaceCanvas + Suspense.
- `frontend/package.json` — add `monaco-editor`.
- `frontend/src/superbrain/lib/monacoConfig.ts` — new loader config module.
- `frontend/src/main.jsx` — import monacoConfig.

## Testing plan

1. `python tools/check_canon_frozen.py --allow-canon` — confirms specgloss deletion is intentional; remaining canon assets pass.
2. `cd frontend && npm install` — installs `monaco-editor`.
3. `npm run typecheck` — no new errors.
4. `npm test -- --run` — 56 test files, 337 tests pass.
5. `npm run build` — exit 0; inspect `dist/assets/` for the new chunk names.
6. `python tools/check_css_canon.py` — unaffected, should pass.

## Out of scope

- No changes to shader code, materials, or the 3D scene.
- No new Monaco editor UI (the existing collapsed GAGOS UI has no editor surface).
- No backend changes.
