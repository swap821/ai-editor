'use client';

/**
 * One operator-owned visual-detail preference for DOM and scene consumers.
 * Fresh sessions default to measured Auto; validated manual choices survive.
 * Auto keeps structural/color identity high while separate optional cost
 * levers adapt at runtime. The governor cannot persist this preference or
 * measured stages. No hardware verdict is implied.
 * The legacy cognition flag is advisory only and never dims either tier.
 */

import React, {
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { subscribeCognition } from '@/lib/cognitionBus';
import { QualityTierContext, useQualityTierOwner } from './qualityTierContext';
import { advanceAutoQuality, autoQualityProfile, initialAutoQuality, isQualityPreference,
  setAutoSampling, startAutoQuality, type AutoQualityRuntime, type FrameLoadSignal,
  type QualityPreference } from '../lib/renderQualityPolicy';

export type QualityTier = 'low' | 'medium' | 'high';

/** Validated explicit v3 choices migrate; v4 adds the explicit Auto option.
 * Measured stages are never stored. Earlier machine-verdict keys are removed. */
const STORAGE_KEY = 'gag-quality-tier-v3';
const PREFERENCE_KEY = 'gag-quality-tier-v4';
const LEGACY_STORAGE_KEYS = ['gag-quality-tier', 'gag-quality-tier-v2'];
const TIERS: readonly QualityTier[] = ['low', 'medium', 'high'];

export function isQualityTier(value: unknown): value is QualityTier {
  return typeof value === 'string' && (TIERS as readonly string[]).includes(value);
}

/** One step down; 'low' is the floor. */
export function demoteTier(tier: QualityTier): QualityTier {
  return tier === 'high' ? 'medium' : 'low';
}

/** Legacy pure helper; the provider does NOT dim its returned tiers. */
export function effectiveTier(base: QualityTier, generating: boolean): QualityTier {
  return generating ? demoteTier(base) : base;
}

function readStoredPreference(): QualityPreference | null {
  if (typeof window === 'undefined') return null;
  try {
    for (const legacy of LEGACY_STORAGE_KEYS) {
      window.localStorage.removeItem(legacy);
    }
    const preference = window.localStorage.getItem(PREFERENCE_KEY);
    if (isQualityPreference(preference)) return preference;
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return isQualityTier(stored) ? stored : null;
  } catch {
    return null;
  }
}

export function useQualityTier() {
  return useContext(QualityTierContext);
}

/** Standalone lab canvases own a preference; product canvases inherit theirs. */
export function QualityTierBoundary({ children }: { children: React.ReactNode }) {
  const owner = useQualityTierOwner();
  return owner ? <>{children}</> : <QualityTierProvider>{children}</QualityTierProvider>;
}

export function QualityTierProvider({
  children,
  defaultTier,
  restorePreference = true,
}: {
  children: React.ReactNode;
  defaultTier?: QualityTier;
  /** Isolated renderer fixtures choose their own labelled profile, not the
   * product's saved preference. Normal product/standalone owners restore it. */
  restorePreference?: boolean;
}) {
  const [preference, setPreference] = useState<QualityPreference>(
    () => (restorePreference ? readStoredPreference() : null) ?? defaultTier ?? 'auto',
  );
  const preferenceRef = useRef(preference);
  const runtimeRef = useRef(initialAutoQuality());
  const [runtime, setRuntime] = useState(runtimeRef.current);
  const [generating, setGenerating] = useState(false);
  const commitRuntime = useCallback((next: AutoQualityRuntime) => {
    const previous = runtimeRef.current;
    runtimeRef.current = next;
    if (next.stage !== previous.stage || next.revision !== previous.revision) setRuntime(next);
  }, []);
  const beginAutoCalibration = useCallback((at: number) => {
    if (preferenceRef.current === 'auto') commitRuntime(startAutoQuality(runtimeRef.current, at));
  }, [commitRuntime]);
  const setAutoSamplingActive = useCallback((active: boolean, at: number) => {
    if (preferenceRef.current === 'auto') commitRuntime(setAutoSampling(runtimeRef.current, active, at));
  }, [commitRuntime]);
  const reportAutoWindow = useCallback((signal: FrameLoadSignal, revision: number, at: number, densityAllowed: boolean) => {
    if (preferenceRef.current === 'auto') commitRuntime(advanceAutoQuality(runtimeRef.current, signal, revision, at, densityAllowed));
  }, [commitRuntime]);

  const setTier = useCallback((tier: QualityPreference) => {
    if (!isQualityPreference(tier)) return;
    // Reaffirming the current choice is still an explicit preference write,
    // not a new cost profile. Keep its useful-frame calibration and sampling.
    if (preferenceRef.current !== tier) {
      preferenceRef.current = tier;
      setPreference(tier);
      commitRuntime(initialAutoQuality(runtimeRef.current.revision + 1));
    }
    try {
      window.localStorage.setItem(PREFERENCE_KEY, tier);
      if (tier !== 'auto') window.localStorage.setItem(STORAGE_KEY, tier);
    } catch {
      // Private mode etc. — the session still gets the right tier.
    }
  }, [commitRuntime]);

  // Legacy advisory signal only: no tier mutation or current-backend claim.
  useEffect(() => {
    return subscribeCognition((event) => {
      if (event.type === 'directive') setGenerating(true);
      else if (event.type === 'synthesis' || event.type === 'approval-required') {
        setGenerating(false);
      }
    });
  }, []);

  const value = useMemo(
    () => ({
      // Auto keeps regional anatomy and the complete color/texture chain.
      // Only separate optional levers adapt; manual profiles are unchanged.
      tier: preference === 'auto' ? 'high' as const : preference,
      perfTier: preference === 'auto' ? 'high' as const : preference,
      baseTier: preference === 'auto' ? 'high' as const : preference,
      preference,
      autoProfile: autoQualityProfile(runtime.stage),
      autoRevision: runtime.revision,
      beginAutoCalibration, setAutoSamplingActive, reportAutoWindow,
      generating,
      setTier,
    }),
    [preference, runtime.stage, runtime.revision, generating, setTier,
      beginAutoCalibration, setAutoSamplingActive, reportAutoWindow],
  );

  return (
    <QualityTierContext.Provider value={value}>
      {children}
    </QualityTierContext.Provider>
  );
}
