'use client';

/**
 * TierGovernor — turns measured frame rate into quality-tier evidence.
 *
 * Lives inside the Canvas so drei's PerformanceMonitor can watch the real
 * render loop. Demote-only by design: a decline is proof this machine cannot
 * sustain the current tier (the verdict persists via the provider), while
 * auto-promotion would flip-flop the look every time the scene idles. The
 * operator can always promote manually through setTier.
 */

import { useEffect, useState } from 'react';
import { PerformanceMonitor } from '@react-three/drei';
import { demoteTier, useQualityTier } from '@/components/QualityTierProvider';

/** Boot shader compilation and first-load jank must never count as evidence. */
const WARMUP_MS = 20_000;

export default function TierGovernor() {
  const { baseTier, generating, setTier } = useQualityTier();
  const [armed, setArmed] = useState(false);

  useEffect(() => {
    const handle = window.setTimeout(() => setArmed(true), WARMUP_MS);
    return () => window.clearTimeout(handle);
  }, []);

  if (!armed) return null;
  return (
    <PerformanceMonitor
      bounds={() => [40, 57]}
      flipflops={3}
      onDecline={() => {
        // Frame dips while the local model is generating, or while the tab is
        // hidden, are EXPECTED — they are not evidence about the machine.
        if (generating || document.hidden) return;
        if (baseTier !== 'low') setTier(demoteTier(baseTier));
      }}
      onFallback={() => {
        if (generating || document.hidden) return;
        setTier('low');
      }}
    />
  );
}
