'use client';

import { Suspense, useCallback, useState, useRef, useEffect, type ReactNode } from 'react';
import { Canvas } from '@react-three/fiber';
import * as THREE from 'three';
import { POST_FX, CAMERA } from '@/lib/constants';
import { WebGLErrorBoundary } from './WebGLErrorBoundary';
import SuperbrainScene, { type BrainSurface, type SkyMode } from './SuperbrainScene';
import SuperbrainHUD, { type CognitiveMode } from '@/components/ui/SuperbrainHUD';
import BootSequence from '@/components/ui/BootSequence';
import {
  QualityTierProvider,
  useQualityTier,
  type QualityTier,
} from '@/components/QualityTierProvider';
import TierGovernor from './TierGovernor';
import { sendDirective, startAiosPolling } from '@/lib/aiosAdapter';
import { publishCognition, subscribeCognition } from '@/lib/cognitionBus';
import { notifyDirective, tickLifecycle } from '@/lib/lifecycleStateMachine';

/** Device-pixel-ratio budget per effective tier — the cheapest fill-rate lever. */
const TIER_DPR: Record<QualityTier, [number, number]> = {
  high: [1, 1.5],
  medium: [1, 1.25],
  low: [1, 1],
};

export default function WorkspaceCanvas({ children }: { children?: ReactNode }) {
  return (
    <QualityTierProvider>
      <WorkspaceInner>{children}</WorkspaceInner>
    </QualityTierProvider>
  );
}

/** Chrome restores a lost-but-recoverable context well under a second; past
 *  this grace the context is gone for good and only a remount brings the
 *  organism back. */
const CONTEXT_RESTORE_GRACE_MS = 4000;

/** Like the fidelity tier: only the operator's own click is ever stored.
 *  Voyage (his original moving field, canon) is the default. */
const SKY_STORAGE_KEY = 'gag-sky-mode-v1';

function readStoredSky(): SkyMode | null {
  if (typeof window === 'undefined') return null;
  try {
    const stored = window.localStorage.getItem(SKY_STORAGE_KEY);
    return stored === 'voyage' || stored === 'layered' ? stored : null;
  } catch {
    return null;
  }
}

/** Same sovereignty contract for the cortex surface; canon web is default. */
const SURFACE_STORAGE_KEY = 'gag-brain-surface-v1';

function readStoredSurface(): BrainSurface | null {
  if (typeof window === 'undefined') return null;
  try {
    const stored = window.localStorage.getItem(SURFACE_STORAGE_KEY);
    return stored === 'web' || stored === 'organ' ? stored : null;
  } catch {
    return null;
  }
}

function WorkspaceInner({ children }: { children?: ReactNode }) {
  const { tier, perfTier } = useQualityTier();
  const [mode, setMode] = useState<CognitiveMode>('orchestrate');
  const [activity, setActivity] = useState(0.72);
  const [lastDirective, setLastDirective] = useState('Mapping the active knowledge horizon');
  // Boot choreography contract: "is-booting" while the kernel boot overlay is
  // up, "is-booted" once it unmounts — HUD entrance animations key off it.
  const [booted, setBooted] = useState(false);
  const timeoutRef = useRef<number | null>(null);
  // GPU context-loss resilience: a lost context first gets a grace window to
  // restore in place (preventDefault opts in); if it never comes back, bumping
  // this key remounts the Canvas — a black dead screen is never acceptable on
  // a machine where Ollama can evict the GPU at any moment.
  const [glEpoch, setGlEpoch] = useState(0);
  const restoreTimerRef = useRef<number | null>(null);
  const [skyMode, setSkyMode] = useState<SkyMode>(() => readStoredSky() ?? 'voyage');

  const handleSkyModeChange = useCallback((next: SkyMode) => {
    setSkyMode(next);
    try {
      window.localStorage.setItem(SKY_STORAGE_KEY, next);
    } catch {
      // Private mode etc. — the session still gets the chosen sky.
    }
  }, []);

  const [surface, setSurface] = useState<BrainSurface>(() => readStoredSurface() ?? 'web');

  const handleSurfaceChange = useCallback((next: BrainSurface) => {
    setSurface(next);
    try {
      window.localStorage.setItem(SURFACE_STORAGE_KEY, next);
    } catch {
      // Private mode etc. — the session still gets the chosen surface.
    }
  }, []);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current);
      }
      if (restoreTimerRef.current) {
        window.clearTimeout(restoreTimerRef.current);
      }
    };
  }, []);

  const handleBootComplete = useCallback(() => {
    setBooted(true);
  }, []);

  const handleCreated = useCallback(({ gl }: { gl: THREE.WebGLRenderer }) => {
    if (!gl.capabilities.isWebGL2) {
      console.warn('WebGL 2 is not available. Falling back to lower quality rendering or failing.');
    }
    // Listeners live and die with this canvas element; a remount re-attaches
    // them via this same onCreated.
    const el = gl.domElement;
    el.addEventListener('webglcontextlost', (event) => {
      event.preventDefault(); // opt in to in-place restoration
      publishCognition({
        type: 'synthesis',
        label: 'RENDERER INTERRUPTED',
        detail: 'GPU context lost — holding for in-place restore',
        intensity: 0.4,
        source: 'renderer',
      });
      if (restoreTimerRef.current) window.clearTimeout(restoreTimerRef.current);
      restoreTimerRef.current = window.setTimeout(() => {
        restoreTimerRef.current = null;
        setGlEpoch((epoch) => epoch + 1);
      }, CONTEXT_RESTORE_GRACE_MS);
    });
    el.addEventListener('webglcontextrestored', () => {
      if (restoreTimerRef.current) {
        window.clearTimeout(restoreTimerRef.current);
        restoreTimerRef.current = null;
      }
      publishCognition({
        type: 'synthesis',
        label: 'RENDERER RECOVERED',
        detail: 'GPU context restored in place',
        intensity: 0.3,
        source: 'renderer',
      });
    });
  }, []);

  // Once booted, the organism listens to the REAL AI-OS: trail/metric polling
  // feeds the intake channels and fires knowledge events when actual skill
  // trails are reinforced. Honest fallback: offline, the demo imagination
  // carries on and the bus says so.
  useEffect(() => {
    if (!booted) return;
    return startAiosPolling();
  }, [booted]);

  // Dev-only escape hatch: probes and look-dev sessions can drive the
  // nervous system directly (e.g. trigger the approval hold on demand).
  useEffect(() => {
    if (process.env.NODE_ENV === 'production') return;
    const host = window as unknown as Record<string, unknown>;
    host.__gagCognition = publishCognition;
    return () => {
      delete host.__gagCognition;
    };
  }, []);

  // THE SIGNAL bridge: a user directive (typed or voice) wakes the being.
  // A light heartbeat advances the posture machine's decay timers. The scene
  // subscribes to the machine directly; this component only feeds it.
  useEffect(() => {
    const unsub = subscribeCognition((event) => {
      if (event.type === 'directive') notifyDirective();
    });
    const heartbeat = window.setInterval(() => tickLifecycle(), 50);
    return () => {
      unsub();
      window.clearInterval(heartbeat);
    };
  }, []);

  const handleDirective = useCallback((directive: string) => {
    setMode('synthesize');
    setActivity(1);
    setLastDirective(directive);
    if (timeoutRef.current) window.clearTimeout(timeoutRef.current);

    // The directive drives a REAL supervised turn; the stream's lifecycle —
    // not a canned timer — decides when the organism settles.
    void sendDirective(directive).then((result) => {
      if (result.paused) {
        // The supervised mind is holding its breath for its operator.
        setLastDirective('Awaiting operator approval');
        setActivity(0.9);
        return;
      }
      timeoutRef.current = window.setTimeout(() => {
        setMode('orchestrate');
        setActivity(0.72);
      }, 800);
    });
  }, []);

  const handleModeChange = useCallback((nextMode: CognitiveMode) => {
    setMode(nextMode);
    setActivity(nextMode === 'observe' ? 0.42 : nextMode === 'synthesize' ? 1 : 0.72);
  }, []);

  return (
      <main className={`superbrain-experience ${booted ? 'is-booted' : 'is-booting'}`}>
        <div className="scene-layer" aria-hidden="true">
        <WebGLErrorBoundary>
          <Canvas
            key={glEpoch}
            camera={{ position: [0, 0.25, 8.5], fov: CAMERA.fov, near: CAMERA.near, far: CAMERA.far }}
            dpr={TIER_DPR[perfTier]}
            onCreated={handleCreated}
            gl={{
              // The composer owns AA (4x MSAA on its input buffer at high
              // tier — PostFX.tsx): the canvas backbuffer only ever shows
              // the final fullscreen quad, so its own MSAA bought nothing.
              antialias: false,
              alpha: false,
              powerPreference: 'high-performance',
              // EffectComposer forces renderer.toneMapping = NoToneMapping, so
              // tone mapping happens in PostFX (AgX effect). The prop below is
              // inert while the composer is mounted; toneMappingExposure IS
              // consumed by AgX (three uploads it to every program).
              toneMapping: THREE.ACESFilmicToneMapping,
              toneMappingExposure: POST_FX.toneMappingExposure,
            }}
          >
            <color attach="background" args={['#010307']} />
            <fog attach="fog" args={['#010307', 50, 150]} />
            <TierGovernor />
            <Suspense fallback={null}>
              <SuperbrainScene mode={mode} activity={activity} tier={tier} sky={skyMode} surface={surface} />
              <SuperbrainHUD
                mode={mode}
                activity={activity}
                lastDirective={lastDirective}
                onModeChange={handleModeChange}
                onDirective={handleDirective}
                skyMode={skyMode}
                onSkyModeChange={handleSkyModeChange}
                surface={surface}
                onSurfaceChange={handleSurfaceChange}
              />
              {/* Product-side forge ports (editor/preview) mount here, INSIDE the
                  one canvas, so the canon nerves plug into them. Renders nothing
                  when no children are passed (home/?ui=superbrain unchanged). */}
              {children}
            </Suspense>
          </Canvas>
        </WebGLErrorBoundary>
      </div>

      <div className="atmosphere-layer" aria-hidden="true" />
      <div className="grid-layer" aria-hidden="true" />
      <div id="hud-portal-root" />

        {/* Kernel boot overlay — the Canvas mounts underneath so the GLB and
            shaders compile during boot. Fully unmounts on completion and never
            re-mounts (booted is never reset). */}
        {!booted && <BootSequence onComplete={handleBootComplete} />}
      </main>
  );
}
