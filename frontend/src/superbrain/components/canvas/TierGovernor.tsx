'use client';

/**
 * TierGovernor — the 60fps relief valve + the structural-tier advisory.
 *
 * Installed monitor samples the real render loop. Original approved Auto
 * policy relieves optional MSAA, distant decoration, resolution, then fused
 * point density; regional anatomy/color/texture/critical DOM never demote.
 * Useful-frame warmup, fresh revision windows and asymmetric recovery avoid
 * boot-hitch verdicts/hunting. Manual profiles retain their bounded DPR-only
 * relief. No stage is persisted and no arbitrary-device 60fps claim is made.
 */

import { useEffect, useLayoutEffect, useRef, useState, type MutableRefObject } from 'react';
import { useThree, useFrame } from '@react-three/fiber';
import { PerformanceMonitor } from '@react-three/drei';

import { useQualityTier } from '@/components/QualityTierProvider';
import { dprForFactor, PERF_BOUNDS, DPR_WARMUP_MS, ADVISORY_WARMUP_MS } from '@/lib/perfBudget';
import { FeatureGate, useFeatureGate } from '../../core/Performance/FeatureGate';

/** At most one advisory per this window — advice, not nagging. */
const ADVISORY_COOLDOWN_MS = 120_000;
interface PerfSnapshot {
  fps: number | null; factor: number; dpr: number; tier: string;
  preference: string; autoStage: number | null;
}

export default function TierGovernor({ densityChangesAllowed = true }: { densityChangesAllowed?: boolean }) {
  const quality = useQualityTier();
  const { baseTier, perfTier, generating, preference, autoProfile, autoRevision,
    beginAutoCalibration, setAutoSamplingActive, reportAutoWindow } = quality;
  const automatic = preference === 'auto';
  const setDpr = useThree((s) => s.setDpr);
  const get = useThree((s) => s.get);
  const frameLoop = useThree((s) => s.frameloop);
  const sleeping = useFeatureGate();
  const usefulFrameSeen = useRef(false);
  const currentAutomatic = useRef(automatic);
  currentAutomatic.current = automatic;
  useLayoutEffect(() => {
    const canvas = get().gl.domElement;
    const ready = (event: Event) => {
      if (!(event instanceof CustomEvent) || event.detail?.canvas !== canvas) return;
      usefulFrameSeen.current = true;
      if (currentAutomatic.current) beginAutoCalibration(performance.now());
    };
    window.addEventListener('gagos:ready', ready);
    return () => window.removeEventListener('gagos:ready', ready);
  }, [get, beginAutoCalibration]);
  useEffect(() => {
    if (automatic && usefulFrameSeen.current) beginAutoCalibration(performance.now());
  }, [automatic, beginAutoCalibration]);
  useEffect(() => {
    if (!automatic) return;
    setAutoSamplingActive(frameLoop === 'always' && !sleeping, performance.now());
    return () => setAutoSamplingActive(false, performance.now());
  }, [automatic, frameLoop, sleeping, setAutoSamplingActive]);
  useEffect(() => {
    if (automatic) setDpr(autoProfile.dpr);
  }, [automatic, autoProfile, setDpr]);
  // DPR relief arms early (reversible); the advisory waits the full warmup.
  const [armed, setArmed] = useState(false);
  const fullyWarmedRef = useRef(false);
  const lastAdvisoryRef = useRef(0);
  // Live perf snapshot for the operator's profiling: window.__getPerf().
  const perfRef = useRef<PerfSnapshot>({
    fps: null, factor: 1, dpr: dprForFactor(perfTier, 1), tier: perfTier,
    preference, autoStage: automatic ? autoProfile.stage : null,
  });
  useEffect(() => {
    // A changed cost profile, demand or hidden frames have no fresh pacing
    // sample. Keep actual applied DPR, label the selected tier immediately,
    // and seed a new tier's monitor without inheriting its previous verdict.
    const previous = perfRef.current;
    perfRef.current = { ...previous, fps: null, tier: perfTier,
      dpr: get().gl.getPixelRatio(), factor: previous.tier === perfTier ? previous.factor : 1,
      preference, autoStage: automatic ? autoProfile.stage : null };
  }, [frameLoop, perfTier, get, preference, automatic, autoProfile.stage, autoRevision, sleeping]);

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
      {/* Mount a fresh sampling window on Resume; intentional demand gaps
          must not contaminate either the probe or drei's relief history. */}
      {!sleeping && frameLoop === 'always' && <PerfProbe key={`probe:${perfTier}:${automatic ? autoRevision : 'manual'}`} perfRef={perfRef} />}
      {armed && !sleeping && frameLoop === 'always' && (
        <PerformanceMonitor
          key={`monitor:${perfTier}:${automatic ? autoRevision : 'manual'}`}
          bounds={() => PERF_BOUNDS}
          // The installed monitor counts EVERY above/below-budget window as a
          // flip, even healthy windows at factor1. A finite lifetime quota would
          // disable later load relief permanently. Keep sampling while active;
          // existing window/threshold/step hysteresis and DPR bounds limit change.
          flipflops={Infinity}
          // Start optimistic (full sharpness); shed resolution only if FPS sags.
          factor={1}
          onChange={({ fps, factor }) => {
            // RELIEF VALVE: resolution gives to hold the framerate. A hidden tab
            // throttles RAF to ~0 fps (not a real sag) — never react to that.
            if (FeatureGate.isSleeping || get().frameloop !== 'always') return;
            const dpr = automatic ? get().gl.getPixelRatio() : dprForFactor(perfTier, factor);
            if (!automatic) setDpr(dpr);
            perfRef.current = { ...perfRef.current, fps, factor, dpr, tier: perfTier };
          }}
          onIncline={() => {
            if (!automatic || FeatureGate.isSleeping || get().frameloop !== 'always'
              || get().gl.getContext().isContextLost()) return;
            reportAutoWindow('healthy', autoRevision, performance.now(), densityChangesAllowed);
          }}
          onDecline={() => {
            if (automatic) {
              if (FeatureGate.isSleeping || get().frameloop !== 'always'
                || get().gl.getContext().isContextLost()) return;
              reportAutoWindow('slow', autoRevision, performance.now(), densityChangesAllowed);
              return;
            }
            // Resolution couldn't save it. Dips while the model generates or the
            // tab is hidden are expected; a machine already on 'low' has nothing
            // left to advise; and boot jank must never count (fullyWarmed gate).
            if (!fullyWarmedRef.current || generating || FeatureGate.isSleeping
              || get().frameloop !== 'always' || baseTier === 'low') return;
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
function PerfProbe({ perfRef }: { perfRef: MutableRefObject<PerfSnapshot> }) {
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
