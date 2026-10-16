import type { QualityTier } from '../components/QualityTierProvider';

export type QualityPreference = QualityTier | 'auto';
export type FrameLoadSignal = 'slow' | 'healthy';
export type AutoQualityStage = 0 | 1 | 2 | 3 | 4 | 5 | 6;
export interface AutoQualityProfile {
  stage: AutoQualityStage;
  multisampling: 0 | 4;
  skyTier: QualityTier;
  densityTier: QualityTier;
  dpr: [number, number];
}

// Approved cost order. Color/texture grading and regional anatomy are NOT
// budget levers. These runtime profiles are not device-speed measurements.
const PROFILES: readonly AutoQualityProfile[] = [
  { stage: 0, multisampling: 4, skyTier: 'high', densityTier: 'high', dpr: [1, 1.5] },
  { stage: 1, multisampling: 0, skyTier: 'high', densityTier: 'high', dpr: [1, 1.5] },
  { stage: 2, multisampling: 0, skyTier: 'low', densityTier: 'high', dpr: [1, 1.5] },
  { stage: 3, multisampling: 0, skyTier: 'low', densityTier: 'high', dpr: [1, 1.25] },
  { stage: 4, multisampling: 0, skyTier: 'low', densityTier: 'high', dpr: [1, 1] },
  { stage: 5, multisampling: 0, skyTier: 'low', densityTier: 'medium', dpr: [1, 1] },
  { stage: 6, multisampling: 0, skyTier: 'low', densityTier: 'low', dpr: [1, 1] },
];
const WARMUP_MS = 20_000;
const SETTLE_MS = 4_000;
const RECOVERY_MS = 10_000;
const HEALTHY_ADJACENCY_MS = 4_000; // Healthy monitor windows take ~2.5s.

export function isQualityPreference(value: unknown): value is QualityPreference {
  return value === 'auto' || value === 'high' || value === 'medium' || value === 'low';
}
export function autoQualityProfile(stage: AutoQualityStage): AutoQualityProfile {
  return PROFILES[stage];
}
export interface AutoQualityRuntime {
  stage: AutoQualityStage;
  revision: number;
  sampling: boolean;
  readyAfter: number | null;
  lastChangedAt: number;
  lastSignalAt: number | null;
  lastSignal: FrameLoadSignal | null;
  healthyWindows: number;
}
export function initialAutoQuality(revision = 0): AutoQualityRuntime {
  return { stage: 0, revision, sampling: false, readyAfter: null,
    lastChangedAt: 0, lastSignalAt: null, lastSignal: null, healthyWindows: 0 };
}
export function startAutoQuality(state: AutoQualityRuntime, at: number): AutoQualityRuntime {
  if (!Number.isFinite(at) || at < 0) return state;
  return { ...initialAutoQuality(state.revision + 1), sampling: state.sampling,
    readyAfter: at + WARMUP_MS, lastChangedAt: at };
}
export function setAutoSampling(state: AutoQualityRuntime, active: boolean, at: number): AutoQualityRuntime {
  if (state.sampling === active || !Number.isFinite(at) || at < 0) return state;
  return { ...state, sampling: active, revision: state.revision + 1,
    readyAfter: active && state.readyAfter !== null ? Math.max(state.readyAfter, at + SETTLE_MS) : state.readyAfter,
    lastSignalAt: null, lastSignal: null, healthyWindows: 0 };
}
export function advanceAutoQuality(state: AutoQualityRuntime, signal: FrameLoadSignal,
  revision: number, at: number, densityAllowed: boolean): AutoQualityRuntime {
  if (!state.sampling || state.readyAfter === null || revision !== state.revision
    || !Number.isFinite(at) || at < state.readyAfter
    || (state.lastSignalAt !== null && at <= state.lastSignalAt)
    || (signal !== 'slow' && signal !== 'healthy')) return state;
  const healthyWindows = signal === 'healthy'
    ? (state.lastSignal === 'healthy' && state.lastSignalAt !== null
      && at - state.lastSignalAt <= HEALTHY_ADJACENCY_MS ? state.healthyWindows + 1 : 1) : 0;
  const next = { ...state, lastSignalAt: at, lastSignal: signal, healthyWindows };
  let stage = state.stage;
  if (signal === 'slow' && at - state.lastChangedAt >= SETTLE_MS && stage < 6) stage = (stage + 1) as AutoQualityStage;
  if (signal === 'healthy' && healthyWindows >= 2 && at - state.lastChangedAt >= RECOVERY_MS && stage > 0) stage = (stage - 1) as AutoQualityStage;
  if (stage === state.stage || (!densityAllowed && (stage >= 5 || state.stage >= 5))) return next;
  return { ...next, stage, revision: state.revision + 1, lastChangedAt: at,
    lastSignalAt: null, lastSignal: null, healthyWindows: 0 };
}
