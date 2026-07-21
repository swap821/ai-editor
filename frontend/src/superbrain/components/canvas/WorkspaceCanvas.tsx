'use client';
import { subscribeCognition } from '@/lib/cognitionBus';

import { Suspense, useCallback, useState, useRef, useEffect, type ReactNode } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { POST_FX, CAMERA } from '@/lib/constants';
import { WebGLErrorBoundary } from './WebGLErrorBoundary';
import { FallbackScene } from './FallbackScene';
import CortexEngine from '../../core/CortexEngine';
import { type BrainSurface, type SkyMode } from './SuperbrainScene.LEGACY';
import type { CognitiveMode } from '@/components/ui/SuperbrainHUD';
import {
  QualityTierProvider,
  useQualityTier,
  type QualityTier,
} from '@/components/QualityTierProvider';
import TierGovernor from './TierGovernor';
import { TIER_DPR } from '@/lib/perfBudget';
import { startAiosPolling } from '@/lib/aiosAdapter';

import {
  notifyDirective,
  tickLifecycle,
} from '@/lib/lifecycleStateMachine';

/** Boot handoff: fire `gagos:ready` ONCE the scene is actually rendering (the
 *  first frame after Suspense resolves = shaders warming, GLB landed), so the
 *  index.html boot loader dismisses precisely when the being is up — not on a
 *  guessed timer that fires before the heavy 3D is ready. One extra rAF so the
 *  frame has painted before the crossfade. Pure additive signal: no render. */
function ReadySignal() {
  const fired = useRef(false);
  useFrame(() => {
    if (fired.current) return;
    fired.current = true;
    if (typeof window !== 'undefined') {
      window.requestAnimationFrame(() => window.dispatchEvent(new Event('gagos:ready')));
    }
  });
  return null;
}

export default function WorkspaceCanvas({ children, booted = false }: { children?: ReactNode; booted?: boolean }) {
  return (
    <QualityTierProvider>
      <WorkspaceInner booted={booted}>{children}</WorkspaceInner>
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

function isWebGLAvailable(): boolean {
  try {
    const canvas = document.createElement('canvas');
    return !!(canvas.getContext('webgl2') || canvas.getContext('webgl'));
  } catch {
    return false;
  }
}

function WorkspaceInner({ children, booted }: { children?: ReactNode; booted: boolean }) {
  const [webglAvailable] = useState(() => isWebGLAvailable());
  const { tier, perfTier } = useQualityTier();
  const mode: CognitiveMode = 'orchestrate';
  const activity = 0.72;
  // GPU context-loss resilience: a lost context first gets a grace window to
  // restore in place (preventDefault opts in); if it never comes back, bumping
  // this key remounts the Canvas — a black dead screen is never acceptable on
  // a machine where Ollama can evict the GPU at any moment.
  const [glEpoch, setGlEpoch] = useState(0);
  const restoreTimerRef = useRef<number | null>(null);
  // The operator's sovereign sky/surface choices still load from storage so
  // the being renders the chosen look; the topbar that wrote them lived in the
  // removed 2D HUD, so there are no setters here.
  const skyMode: SkyMode = readStoredSky() ?? 'voyage';
  const surface: BrainSurface = readStoredSurface() ?? 'web';

  useEffect(() => {
    return () => {
      if (restoreTimerRef.current) {
        window.clearTimeout(restoreTimerRef.current);
      }
    };
  }, []);

  const handleCreated = useCallback(({ gl }: { gl: THREE.WebGLRenderer }) => {
    // WebGPURenderer (the ?gpu=webgpu spike) has no `.capabilities` — guard so the
    // WebGL2 probe never throws and aborts the whole scene mount under WebGPU.
    if (gl.capabilities && !gl.capabilities.isWebGL2) {
      console.warn('WebGL 2 is not available. Falling back to lower quality rendering or failing.');
    }
    // Listeners live and die with this canvas element; a remount re-attaches
    // them via this same onCreated.
    const el = gl.domElement;
    el.addEventListener('webglcontextlost', (event) => {
      event.preventDefault(); // opt in to in-place restoration
      
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
      
    });
  }, []);

  // Once booted, the organism listens to GAGOS: trail/metric polling
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

  if (!webglAvailable) {
    return (
      <div className={`superbrain-experience ${booted ? 'is-booted' : 'is-booting'}`}>
        <div className="scene-layer" aria-hidden="true">
          <FallbackScene posture="idle" />
        </div>
        {children}
      </div>
    );
  }

  return (
      <div className={`superbrain-experience ${booted ? 'is-booted' : 'is-booting'}`}>
        <div className="scene-layer" aria-hidden="true">
        <WebGLErrorBoundary>
          <Canvas
            key={glEpoch}
            tabIndex={-1}
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
            {/* operator call (2026-06-23): pure-black void — was the blue-black
                #010307; the brain's own bloom/aura is additive WebGL light and
                is unaffected, only the empty space goes true black. */}
            <color attach="background" args={['#000000']} />
            <fog attach="fog" args={['#000000', 50, 150]} />
            <TierGovernor />
            <Suspense fallback={null}>
              <CortexEngine mode={mode} activity={activity} tier={tier} sky={skyMode} surface={surface} />
              <ReadySignal />
              {/* Product-side forge ports (editor/preview) mount here, INSIDE the
                  one canvas, so the canon nerves plug into them. Renders nothing
                  when no children are passed (home/?ui=superbrain unchanged). */}
              {children}
            </Suspense>
          </Canvas>
        </WebGLErrorBoundary>
      </div>
      </div>
  );
}
