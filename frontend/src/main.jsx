import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// THE SUPERBRAIN INTEGRATION SHELL IS THE OFFICIAL FRONTEND (operator's
// decision, 2026-06-14): the clean root URL (no flag) IS the whole system.
// The shell is superbrain-as-lead — the persistent voyaging brain + the
// renovated HUD, an in-app home <-> workbench toggle (no URL change), the
// read-only governance/learning organs, and the approval safety-net — so
// everything works at one URL. Lazy on every side: each UI's stack loads only
// when it is the one being mounted.
//
//   /              -> the official shell (default; ?ui=shell is a kept alias)
//   ?ui=classic    -> the classic IDE (fallback, byte-untouched)
//   ?ui=home       -> the bare canon superbrain home (SuperbrainApp), kept
//                     reachable for parity review against the frozen brain+space
const SuperbrainApp = lazy(() => import('./superbrain/SuperbrainApp.jsx'))
const SuperbrainShell = lazy(() => import('./superbrain/SuperbrainShell.jsx'))
const ui = new URLSearchParams(window.location.search).get('ui')

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {ui === 'classic' ? (
      <App />
    ) : ui === 'home' || ui === 'superbrain' ? (
      <Suspense fallback={null}>
        <SuperbrainApp />
      </Suspense>
    ) : (
      <Suspense fallback={null}>
        <SuperbrainShell />
      </Suspense>
    )}
  </StrictMode>,
)
