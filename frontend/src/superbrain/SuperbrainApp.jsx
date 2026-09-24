/** One operational shell, one conversation owner, and the preserved connected organism. */
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import BootSequence from '@/components/ui/BootSequence';
import GagosChrome from '../workbench/GagosChrome';
import SuperbrainReactiveEffects from '../workbench/SuperbrainReactiveEffects';
import { LivingWorkspaceShell } from '../livingMirror/LivingWorkspaceShell';
import { readExperienceMode, writeExperienceMode } from '../livingMirror/experienceMode';
import { useBeingPresentation } from '../livingMirror/being/useBeingPresentation';
import { beingStatusText } from '../livingMirror/being/presentationFromStores';
import { createContextRecoveryTracker } from '../livingMirror/observability/contextRecovery';
import { createMirrorReconnectTracker, recordFrontendMetric, startFrameTimeSampler } from '../livingMirror/observability/frontendMetrics';
import { RendererFallbackNotice } from '../livingMirror/RendererFallbackNotice';
import { RendererFailureBoundary } from '../livingMirror/RendererFailureBoundary';
import {
  rendererFallbackVisible,
  setRendererFallbackPresentation,
  useRendererFallbackPresentation,
} from '../livingMirror/rendererFallbackPresentation';
import { startMirrorClient, stopMirrorClient } from './lib/aiosMirror';
import { useTabStore } from './lib/tabStore';
import { useMirrorStore } from './lib/mirrorStore';
import './superbrain.css';

const WorkspaceCanvas = lazy(() => import('@/components/canvas/WorkspaceCanvas'));

export default function SuperbrainApp() {
  const [booted, setBooted] = useState(false);
  const [experienceMode, setExperienceMode] = useState(() => readExperienceMode());
  const [canvasContextLost, setCanvasContextLost] = useState(false);
  const [rendererRestartKey, setRendererRestartKey] = useState(0);
  const snapshot = useTabStore();
  const being = useBeingPresentation();
  const rendererFallback = useRendererFallbackPresentation();
  const measuredAttentionRef = useRef(null);
  const canvasContextLostRef = useRef(false);
  const working = snapshot.panels?.some((p) => p.id === snapshot.focusId && p.open)
    || snapshot.tabs.some((t) => t.id === snapshot.focusId && t.kind === 'content' && t.lifecycle !== 'retracting');
  const handleBootComplete = useCallback(() => setBooted(true), []);
  const handleExperienceModeChange = useCallback((nextMode) => {
    writeExperienceMode(nextMode);
    setExperienceMode(nextMode);
  }, []);
  const handleRendererRetry = useCallback(() => {
    if (canvasContextLostRef.current) {
      // A lost context can make the managed post-processing boundary fail
      // before the browser emits restoration. Unmount the old canvas before
      // remounting a fresh one; the shell remains usable throughout.
      canvasContextLostRef.current = false;
      setCanvasContextLost(false);
      setRendererRestartKey((key) => key + 1);
      setRendererFallbackPresentation(false);
      return;
    }
    const managedRetry = document.querySelector('.webgl-fallback button');
    if (managedRetry instanceof HTMLButtonElement) {
      managedRetry.click();
      return;
    }
    // The no-WebGL path cannot remount a renderer that the browser rejected;
    // a reload is the only honest retry boundary after the user restores
    // graphics support or changes the browser environment.
    window.location.reload();
  }, []);
  useEffect(() => {
    const startedAt = performance.now();
    let inputReady = false;
    let frame = 0;
    const findInput = () => {
      if (inputReady) return;
      const input = document.querySelector('[aria-label="Talk to GAGOS"]');
      if (input) {
        inputReady = true;
        recordFrontendMetric('boot-to-input-ready', performance.now() - startedAt);
        return;
      }
      frame = window.requestAnimationFrame(findInput);
    };
    frame = window.requestAnimationFrame(findInput);
    const organismReady = () => recordFrontendMetric('3d-initialization', performance.now() - startedAt);
    window.addEventListener('gagos:ready', organismReady, { once: true });
    const stopFrameSampler = startFrameTimeSampler();
    const trackMirrorReconnect = createMirrorReconnectTracker();
    const unsubscribeMirror = useMirrorStore.subscribe((state, previous) => {
      trackMirrorReconnect(state, previous);
    });
    const contextTracker = createContextRecoveryTracker();
    let boundCanvas = null;
    const syncRendererFallback = () => {
      setRendererFallbackPresentation(canvasContextLostRef.current || rendererFallbackVisible());
    };
    const handleCanvasContextLost = () => {
      canvasContextLostRef.current = true;
      setCanvasContextLost(true);
      contextTracker.handleLost();
      syncRendererFallback();
    };
    const handleCanvasContextRestored = () => {
      canvasContextLostRef.current = false;
      setCanvasContextLost(false);
      contextTracker.handleRestored();
      syncRendererFallback();
    };
    const bindCanvas = () => {
      const canvas = document.querySelector('.scene-layer canvas');
      if (!(canvas instanceof HTMLCanvasElement) || canvas === boundCanvas) return;
      if (boundCanvas) {
        boundCanvas.removeEventListener('webglcontextlost', handleCanvasContextLost);
        boundCanvas.removeEventListener('webglcontextrestored', handleCanvasContextRestored);
      }
      boundCanvas = canvas;
      boundCanvas.addEventListener('webglcontextlost', handleCanvasContextLost);
      boundCanvas.addEventListener('webglcontextrestored', handleCanvasContextRestored);
    };
    syncRendererFallback();
    bindCanvas();
    const canvasObserver = typeof MutationObserver === 'function'
      ? new MutationObserver(() => {
        syncRendererFallback();
        bindCanvas();
      })
      : null;
    canvasObserver?.observe(document.body, { childList: true, subtree: true });
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('gagos:ready', organismReady);
      stopFrameSampler();
      unsubscribeMirror();
      canvasObserver?.disconnect();
      if (boundCanvas) {
        boundCanvas.removeEventListener('webglcontextlost', handleCanvasContextLost);
        boundCanvas.removeEventListener('webglcontextrestored', handleCanvasContextRestored);
      }
      canvasContextLostRef.current = false;
      setRendererFallbackPresentation(false);
    };
  }, []);
  useEffect(() => {
    const attention = snapshot.attention;
    if (!working || !attention || measuredAttentionRef.current === attention.startedAt) return;
    measuredAttentionRef.current = attention.startedAt;
    recordFrontendMetric('workspace-materialization', Math.max(0, performance.now() - attention.startedAt));
  }, [snapshot.attention, working]);
  useEffect(() => { void startMirrorClient(); return stopMirrorClient; }, []);
  return <div
    className="lm-app"
    data-working={working ? 'true' : 'false'}
    data-experience-mode={experienceMode}
    data-being-phase={being.phase}
    data-being-task-state={being.taskState}
    data-being-coherence={being.coherence}
    data-being-motion={being.motion}
    data-being-attention={being.attention}
  >
    <div className="lm-being-status" role="status" aria-live="polite" aria-atomic="true">{beingStatusText(being)}</div>
    <BootSequence onComplete={handleBootComplete} />
    <RendererFallbackNotice visible={rendererFallback} onRetry={handleRendererRetry} />
    <div className="lm-scene">{canvasContextLost ? null : (
      <RendererFailureBoundary onRetry={handleRendererRetry}>
        <Suspense fallback={<p className="lm-scene-loading">Loading the organism. Operational controls remain available.</p>}>
          <WorkspaceCanvas key={rendererRestartKey} booted={booted}><SuperbrainReactiveEffects /></WorkspaceCanvas>
        </Suspense>
      </RendererFailureBoundary>
    )}</div>
    <main aria-label="GAGOS conversation"><GagosChrome integrated experienceMode={experienceMode} onExperienceModeChange={handleExperienceModeChange} /></main>
    <LivingWorkspaceShell experienceMode={experienceMode} />
  </div>;
}
