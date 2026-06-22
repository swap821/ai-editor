# ai-editor frontend — GAGOS, the points-being

The React + Vite single-page app that is the **face of the AI-OS**. Since the
2026-06-21 single-frontend collapse it mounts ONE UI (`src/main.jsx` → `SuperbrainApp`):

| URL | Mounts |
|-----|--------|
| `localhost:5173/` (no params) | **GAGOS — the voyaging mind**: the 3D point-field brain + spine + roots (`WorkspaceCanvas`) and the 2D chrome (`workbench/GagosChrome`), streaming supervised turns that materialize luminous 3D work surfaces on the being's spine. |

(The classic IDE `App.jsx`, the `SuperbrainShell`, the `OrgansDock`, and all `?ui=` routes were deleted in the collapse — git history preserves them.)

Both faces stream the **same supervised turn** over SSE from the backend, share one
session, and bind through one data spine (`src/superbrain/lib/aiosAdapter.ts` →
`cognitionBus`). The UI is a real-data read-out of the backend cage: it goes honestly
dormant when there is no data (no fabricated activity).

## Run

```bash
npm install
npm run dev        # http://localhost:5173/   (needs the backend on :8000)
npm run build      # production build
npm test           # vitest
npm run showcase   # prod build + preview (the FIDELITY reference viewing condition, :4173)
```

The backend must be running for live data: from the repo root, `python -m aios`
(binds `AIOS_API_HOST`/`AIOS_API_PORT`, default `127.0.0.1:8000`). See the repo
`START_HERE.md`.

## The lab → product port (3D superbrain)

Everything under `src/superbrain/` is **generated**, not hand-edited here: the source of
truth is the gitignored lab (`GAG demo/gag-orchestrator/`), synced by `npm run port`
(byte-faithful copy of the canon scene + HUD + `superbrain.css` regenerated from the lab
`globals.css`). Edit the 3D scene/HUD in the LAB, then port. The product-only seams you
*do* edit directly: `src/superbrain/SuperbrainApp.jsx` / `SuperbrainShell.jsx`, and
everything under `src/workbench/` + `src/components/`.

The 3D brain + cosmic space are the operator's cherished core — **enhance, never replace**
(canon tag + goldens + before/after screenshots before any visual change).
