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

import { useEffect, useRef, useState } from 'react';
import { PerformanceMonitor } from '@react-three/drei';
import { publishCognition } from '@/lib/cognitionBus';
import { useQualityTier } from '@/components/QualityTierProvider';

/** Boot shader compilation and first-load jank must never count as evidence. */
const WARMUP_MS = 20_000;
/** At most one advisory per this window — advice, not nagging. */
const ADVISORY_COOLDOWN_MS = 120_000;

/**
 * FIDELITY IS SACRED (the operator's law): the governor measures, and when
 * the frame rate genuinely sags it may WHISPER in the terminal — it never
 * touches the tier. Only the operator's FIDELITY click trades detail for
 * smoothness, and only that click is ever persisted.
 */
export default function TierGovernor() {
  const { baseTier, generating } = useQualityTier();
  const [armed, setArmed] = useState(false);
  const lastAdvisoryRef = useRef(0);

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
        // Dips while the model generates or the tab is hidden are expected;
        // and a machine already on 'low' has nothing left to be advised.
        if (generating || document.hidden || baseTier === 'low') return;
        const now = Date.now();
        if (now - lastAdvisoryRef.current < ADVISORY_COOLDOWN_MS) return;
        lastAdvisoryRef.current = now;
        publishCognition({
          type: 'synthesis',
          label: 'PERFORMANCE ADVISORY',
          detail:
            'frame rate below target — click FIDELITY to trade detail for smoothness (your call, never automatic)',
          intensity: 0.3,
          source: 'governor',
        });
      }}
    />
  );
}
