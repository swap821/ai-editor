'use client';

import { Suspense, useCallback, useState, useRef, useEffect } from 'react';
import { Canvas } from '@react-three/fiber';
import * as THREE from 'three';
import { POST_FX, CAMERA } from '@/lib/constants';
import { WebGLErrorBoundary } from './WebGLErrorBoundary';
import SuperbrainScene from './SuperbrainScene';
import SuperbrainHUD, { type CognitiveMode } from '@/components/ui/SuperbrainHUD';
import BootSequence from '@/components/ui/BootSequence';
import {
  QualityTierProvider,
  useQualityTier,
  type QualityTier,
} from '@/components/QualityTierProvider';
import TierGovernor from './TierGovernor';
import { sendDirective, startAiosPolling } from '@/lib/aiosAdapter';
import { publishCognition } from '@/lib/cognitionBus';

/** Device-pixel-ratio budget per effective tier — the cheapest fill-rate lever. */
const TIER_DPR: Record<QualityTier, [number, number]> = {
  high: [1, 1.5],
  medium: [1, 1.25],
  low: [1, 1],
};

export default function WorkspaceCanvas() {
  return (
    <QualityTierProvider>
      <WorkspaceInner />
    </QualityTierProvider>
  );
}

function WorkspaceInner() {
  const { tier, perfTier } = useQualityTier();
  const [mode, setMode] = useState<CognitiveMode>('orchestrate');
  const [activity, setActivity] = useState(0.72);
  const [lastDirective, setLastDirective] = useState('Mapping the active knowledge horizon');
  // Boot choreography contract: "is-booting" while the kernel boot overlay is
  // up, "is-booted" once it unmounts — HUD entrance animations key off it.
  const [booted, setBooted] = useState(false);
  const timeoutRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  const handleBootComplete = useCallback(() => {
    setBooted(true);
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
            camera={{ position: [0, 0.25, 8.5], fov: CAMERA.fov, near: CAMERA.near, far: CAMERA.far }}
            dpr={TIER_DPR[perfTier]}
            onCreated={({ gl }) => {
              if (!gl.capabilities.isWebGL2) {
                console.warn('WebGL 2 is not available. Falling back to lower quality rendering or failing.');
              }
            }}
            gl={{
              antialias: true,
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
              <SuperbrainScene mode={mode} activity={activity} tier={tier} />
              <SuperbrainHUD
                mode={mode}
                activity={activity}
                lastDirective={lastDirective}
                onModeChange={handleModeChange}
                onDirective={handleDirective}
              />
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
