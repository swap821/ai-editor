import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { ErrorBoundary } from './components/ErrorBoundary.jsx'

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

// W5-1 TOP-LEVEL ERROR BOUNDARY (product-safe seam): the superbrain shells live
// in the PORT-MANAGED tree (overwritten byte-for-byte by `npm run port`), so the
// boundary that protects them is mounted HERE — main.jsx is a product-authored
// file that is NEVER touched by the port. Wrapping at the mount point (a DOM
// parent of the lazy shell, outside its Suspense subtree) catches a render fault
// anywhere in the superbrain subtree — the 3D canvas, the workbench organs mount,
// and ForgePorts — and shows the honest fallback instead of white-screening the
// whole app, with no edit to any generated file. The classic <App/> already
// self-wraps at its own top level; this is its additional outermost net.
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary name="App">
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
    </ErrorBoundary>
  </StrictMode>,
)
