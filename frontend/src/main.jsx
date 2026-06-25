import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { ErrorBoundary } from './components/ErrorBoundary.jsx'
import './superbrain/lib/monacoConfig'

// GAGOS — THE VOYAGING MIND is the one and only frontend (operator's decision,
// 2026-06-21): the points-being lives at the clean root URL. No ?ui flags, no
// classic IDE, no manufacturing shell — one mind, one URL.
//
// The superbrain tree is PORT-MANAGED (overwritten byte-for-byte by `npm run
// port`), so the error boundary that protects it is mounted HERE in this
// product-authored file — a DOM parent of the lazy shell, outside its Suspense
// subtree — catching a render fault anywhere in the superbrain subtree without
// editing any generated file.
const SuperbrainApp = lazy(() => import('./superbrain/SuperbrainApp.jsx'))

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary name="App">
      <Suspense fallback={null}>
        <SuperbrainApp />
      </Suspense>
    </ErrorBoundary>
  </StrictMode>,
)
