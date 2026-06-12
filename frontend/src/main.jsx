import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// The superbrain experience (extracted from the operator's visual lab) mounts
// behind an explicit flag; the classic frontend stays the default. Lazy: the
// 3D stack and its CSS load only when summoned.
const SuperbrainApp = lazy(() => import('./superbrain/SuperbrainApp.jsx'))
const wantsSuperbrain =
  new URLSearchParams(window.location.search).get('ui') === 'superbrain'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {wantsSuperbrain ? (
      <Suspense fallback={null}>
        <SuperbrainApp />
      </Suspense>
    ) : (
      <App />
    )}
  </StrictMode>,
)
