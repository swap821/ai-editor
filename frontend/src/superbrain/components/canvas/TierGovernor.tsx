'use client';

/**
 * TierGovernor — the 60fps relief valve + the structural-tier advisory.
 *
 * Lives inside the Canvas so drei's PerformanceMonitor watches the real render
 * loop. Two responsibilities, both honoring FIDELITY-IS-SACRED (palette/textures
 * and GEOMETRY are never auto-changed):
 *
 *   1. RELIEF VALVE (P2.3) — when the frame rate sags, RESOLUTION gives to recover
 *      it. The monitor's 0..1 factor maps (dprForFactor) into the tier's DPR range
 *      and we setDpr() it live. Only device-pixel-ratio (sharpness) flexes;
 *      geometry / particle-counts / hue / palette are untouched, and nothing is
 *      persisted — a pure runtime breath that self-restores when smooth. THIS is
 *      what makes the "must run at 60fps" guarantee real.
 *
 *   2. ADVISORY (kept) — if the frame rate is STILL low after resolution has
 *      bottomed out, the governor may WHISPER in the terminal that the operator
 *      can drop the structural tier. It never acts; only his FIDELITY click ever
 *      changes / persists the structural tier.
 */

import { useEffect, useRef, useState, type MutableRefObject } from 'react';
import { useThree, useFrame } from '@react-three/fiber';
import { PerformanceMonitor } from '@react-three/drei';

import { useQualityTier } from '@/components/QualityTierProvider';
import { dprForFactor, PERF_BOUNDS, DPR_WARMUP_MS, ADVISORY_WARMUP_MS } from '@/lib/perfBudget';
import { FeatureGate } from '../../core/Performance/FeatureGate';

/** At most one advisory per this window — advice, not nagging. */
const ADVISORY_COOLDOWN_MS = 120_000;

export default function TierGovernor() {
  const { baseTier, perfTier, generating } = useQualityTier();
  const setDpr = useThree((s) => s.setDpr);
  // DPR relief arms early (reversible); the advisory waits the full warmup.
  const [armed, setArmed] = useState(false);
  const fullyWarmedRef = useRef(false);
  const lastAdvisoryRef = useRef(0);
  // Live perf snapshot for the operator's profiling: window.__getPerf().
  const perfRef = useRef({ fps: 0, factor: 1, dpr: dprForFactor(perfTier, 1), tier: perfTier });

  useEffect(() => {
    const a = window.setTimeout(() => setArmed(true), DPR_WARMUP_MS);
    const b = window.setTimeout(() => {
      fullyWarmedRef.current = true;
    }, ADVISORY_WARMUP_MS);
    return () => {
      window.clearTimeout(a);
      window.clearTimeout(b);
    };
  }, []);

  // Dev-only profiling hook: read the live FPS / relief factor / applied DPR.
  // SECURITY (H4): double-gated with hostname check.
  useEffect(() => {
    if (typeof window === 'undefined' || process.env.NODE_ENV === 'production' || window.location.hostname !== 'localhost') return undefined;
    const host = window as typeof window & { __getPerf?: () => typeof perfRef.current };
    host.__getPerf = () => perfRef.current;
    return () => {
      delete host.__getPerf;
    };
  }, []);

  return (
    <>
      {/* Always-on probe so __getPerf() reports live FPS + the applied DPR even
          when the relief factor is steady (drei onChange only fires on change). */}
      <PerfProbe perfRef={perfRef} />
      {armed && (
        <PerformanceMonitor
          bounds={() => PERF_BOUNDS}
          flipflops={3}
      // Start optimistic (full sharpness); shed resolution only if FPS sags.
      factor={1}
          onChange={({ fps, factor }) => {
            // RELIEF VALVE: resolution gives to hold the framerate. A hidden tab
            // throttles RAF to ~0 fps (not a real sag) — never react to that.
            if (FeatureGate.isSleeping) return;
            const dpr = dprForFactor(perfTier, factor);
            setDpr(dpr);
            perfRef.current = { ...perfRef.current, fps, factor, dpr, tier: perfTier };
          }}
          onDecline={() => {
            // Resolution couldn't save it. Dips while the model generates or the
            // tab is hidden are expected; a machine already on 'low' has nothing
            // left to advise; and boot jank must never count (fullyWarmed gate).
            if (!fullyWarmedRef.current || generating || FeatureGate.isSleeping || baseTier === 'low') return;
            const now = Date.now();
            if (now - lastAdvisoryRef.current < ADVISORY_COOLDOWN_MS) return;
            lastAdvisoryRef.current = now;
            
          }}
        />
      )}
    </>
  );
}

/** Per-frame FPS + applied-DPR sampler → perfRef (read via window.__getPerf()).
 *  Rolls a ~0.5s window so the operator's profiling has a steady live number. */
function PerfProbe({ perfRef }: { perfRef: MutableRefObject<{ fps: number; factor: number; dpr: number; tier: string }> }) {
  const gl = useThree((s) => s.gl);
  const acc = useRef({ frames: 0, t: 0 });
  useFrame((_s, delta) => {
    const a = acc.current;
    a.frames += 1;
    a.t += delta;
    if (a.t >= 0.5) {
      perfRef.current = { ...perfRef.current, fps: Math.round(a.frames / a.t), dpr: gl.getPixelRatio() };
      a.frames = 0;
      a.t = 0;
    }
  });
  return null;
}
