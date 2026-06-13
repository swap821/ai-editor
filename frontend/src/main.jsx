import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// THE SUPERBRAIN IS THE OFFICIAL FRONTEND (operator's decision, 2026-06-12):
// the experience built in his visual lab is the face of the AI-OS. The
// classic editor remains reachable behind ?ui=classic. Lazy on every side:
// each UI's stack loads only when it is the one being mounted.
//
// ?ui=shell mounts the Phase 2 integration shell (superbrain-as-lead with a
// home form + a manufacturing form) WHILE it is in development — so the canon
// default (no flag) and the classic IDE (?ui=classic) stay byte-untouched and
// parity can be reviewed in the operator's browser before it becomes default.
const SuperbrainApp = lazy(() => import('./superbrain/SuperbrainApp.jsx'))
const SuperbrainShell = lazy(() => import('./superbrain/SuperbrainShell.jsx'))
const ui = new URLSearchParams(window.location.search).get('ui')

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {ui === 'classic' ? (
      <App />
    ) : ui === 'shell' ? (
      <Suspense fallback={null}>
        <SuperbrainShell />
      </Suspense>
    ) : (
      <Suspense fallback={null}>
        <SuperbrainApp />
      </Suspense>
    )}
  </StrictMode>,
)
