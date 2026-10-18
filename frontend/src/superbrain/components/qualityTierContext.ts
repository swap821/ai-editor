import { createContext, useContext } from 'react';
import type { QualityTier } from './QualityTierProvider';
import { autoQualityProfile, type AutoQualityProfile, type FrameLoadSignal, type QualityPreference } from '../lib/renderQualityPolicy';

interface QualityTierContextValue {
  /** Operator-selected structural detail (including point counts). */
  tier: QualityTier;
  /** Same selected detail; runtime resolution relief is a separate owner. */
  perfTier: QualityTier;
  /** Validated preference, persisted only after an explicit change. */
  baseTier: QualityTier;
  /** Legacy cognition-bus flag, NOT verified backend activity. */
  generating: boolean;
  /** Explicit override; remains usable if storage is unavailable. */
  setTier: (tier: QualityPreference) => void;
  preference: QualityPreference;
  autoProfile: AutoQualityProfile;
  autoRevision: number;
  beginAutoCalibration: (at: number) => void;
  setAutoSamplingActive: (active: boolean, at: number) => void;
  reportAutoWindow: (signal: FrameLoadSignal, revision: number, at: number, densityAllowed: boolean) => void;
}

const DEFAULT_QUALITY_TIER_CONTEXT: QualityTierContextValue = {
  tier: 'high', perfTier: 'high', baseTier: 'high', generating: false, setTier: () => {},
  preference: 'high', autoProfile: autoQualityProfile(0), autoRevision: 0,
  beginAutoCalibration: () => {}, setAutoSamplingActive: () => {}, reportAutoWindow: () => {},
};

// One context, shared by the existing provider and the installed Canvas bridge.
// No component exports here: context helpers must not invalidate Fast Refresh.
export const QualityTierContext = createContext(DEFAULT_QUALITY_TIER_CONTEXT);

/** An absent owner must not advertise an interactive, silently no-op control. */
export function useQualityTierOwner() {
  const value = useContext(QualityTierContext);
  return value === DEFAULT_QUALITY_TIER_CONTEXT ? null : value;
}
