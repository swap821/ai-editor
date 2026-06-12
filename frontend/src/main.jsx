import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// THE SUPERBRAIN IS THE OFFICIAL FRONTEND (operator's decision, 2026-06-12):
// the experience built in his visual lab is the face of the AI-OS. The
// classic editor remains reachable behind ?ui=classic. Lazy on both sides:
// each UI's stack loads only when it is the one being mounted.
const SuperbrainApp = lazy(() => import('./superbrain/SuperbrainApp.jsx'))
const wantsClassic =
  new URLSearchParams(window.location.search).get('ui') === 'classic'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {wantsClassic ? (
      <App />
    ) : (
      <Suspense fallback={null}>
        <SuperbrainApp />
      </Suspense>
    )}
  </StrictMode>,
)
