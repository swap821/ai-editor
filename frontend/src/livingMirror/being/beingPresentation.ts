import type { CortexMirrorState } from '../../superbrain/lib/mirrorStore';
import type { BeingSignal } from './semanticSignals';

export type BeingPhase =
  | 'booting'
  | 'ready'
  | 'listening'
  | 'understanding'
  | 'planning'
  | 'awaiting-human'
  | 'acting'
  | 'verifying'
  | 'learning'
  | 'reflex'
  | 'recovering'
  | 'degraded'
  | 'stale'
  | 'stopped';

export type ActiveTurn = 'idle' | 'listening' | 'understanding' | 'planning' | 'acting' | 'checking' | 'reflex' | 'recovering';
export type ContinuityState = 'fresh' | 'snapshot' | 'stale' | 'unknown' | 'stopped';
export type VerificationState = 'none' | 'pending' | 'passed' | 'failed' | 'unverified';
export type QualityTier = 'high' | 'balanced' | 'low';

export interface BeingPresentationInput {
  mirrorSnapshot: Pick<CortexMirrorState, 'status' | 'projection' | 'snapshotRequired' | 'snapshotReceivedAt' | 'activeWorkers'>;
  connectionState: CortexMirrorState['connection'];
  activeTurn: ActiveTurn;
  pendingApproval: boolean;
  emergencyStop: boolean;
  recentSemanticSignals: readonly BeingSignal[];
  reducedMotion: boolean;
  qualityTier: QualityTier;
  verificationState?: VerificationState;
}

export interface BeingPresentation {
  phase: BeingPhase;
  energy: number;
  coherence: number;
  attentionDirection: 'inward' | 'toward-human' | 'outward' | 'settling' | 'still';
  workerCount: number;
  verificationState: VerificationState;
  continuityState: ContinuityState;
  semanticSignals: BeingSignal[];
  motionIntensity: number;
}

const clamp = (value: number): number => Math.max(0, Math.min(1, value));

function continuityOf(input: BeingPresentationInput): ContinuityState {
  if (input.emergencyStop) return 'stopped';
  if (input.mirrorSnapshot.snapshotRequired || input.mirrorSnapshot.status === 'stale' || input.mirrorSnapshot.projection === 'stale') return 'stale';
  if (input.mirrorSnapshot.projection === 'fresh' && input.connectionState === 'connected') return 'fresh';
  if (input.mirrorSnapshot.projection === 'snapshot') return 'snapshot';
  return 'unknown';
}

function phaseOf(input: BeingPresentationInput, continuity: ContinuityState, verification: VerificationState): BeingPhase {
  const latestSignal = input.recentSemanticSignals[input.recentSemanticSignals.length - 1];
  if (input.emergencyStop) return 'stopped';
  if (continuity === 'stale') return 'stale';
  if (input.connectionState === 'disconnected' && !input.mirrorSnapshot.snapshotReceivedAt) return 'degraded';
  if (input.pendingApproval) return 'awaiting-human';
  if (input.activeTurn === 'reflex' || latestSignal === 'reflex-reused') return 'reflex';
  if (input.activeTurn === 'checking' || verification === 'pending') return 'verifying';
  if (input.activeTurn === 'recovering' || latestSignal === 'verification-fail') return 'recovering';
  if (input.activeTurn === 'listening') return 'listening';
  if (input.activeTurn === 'understanding') return 'understanding';
  if (input.activeTurn === 'planning') return 'planning';
  if (input.activeTurn === 'acting' || input.mirrorSnapshot.activeWorkers.length > 0) return 'acting';
  if (input.mirrorSnapshot.projection === 'unknown' || input.mirrorSnapshot.projection === 'synchronizing') return 'booting';
  if (latestSignal === 'memory-promoted' || latestSignal === 'curriculum-mastered') return 'learning';
  return 'ready';
}

function energyOf(phase: BeingPhase, reducedMotion: boolean, qualityTier: QualityTier): number {
  const base: Record<BeingPhase, number> = {
    booting: 0.25, ready: 0.12, listening: 0.35, understanding: 0.5, planning: 0.62,
    'awaiting-human': 0.72, acting: 0.85, verifying: 0.5, learning: 0.7, reflex: 0.9,
    recovering: 0.42, degraded: 0.18, stale: 0.2, stopped: 0,
  };
  const qualityScale = qualityTier === 'low' ? 0.72 : qualityTier === 'balanced' ? 0.9 : 1;
  return clamp(base[phase] * qualityScale * (reducedMotion ? 0.5 : 1));
}

export function deriveBeingPresentation(input: BeingPresentationInput): BeingPresentation {
  const continuityState = continuityOf(input);
  const verificationState = input.verificationState ?? 'none';
  const phase = phaseOf(input, continuityState, verificationState);
  const coherence = continuityState === 'fresh' ? 1 : continuityState === 'snapshot' ? 0.78 : continuityState === 'stale' ? 0.38 : continuityState === 'stopped' ? 0.82 : 0.55;
  const attentionDirection = phase === 'awaiting-human' || phase === 'listening'
    ? 'toward-human'
    : phase === 'acting' || phase === 'learning' || phase === 'reflex'
      ? 'outward'
      : phase === 'verifying' || phase === 'recovering'
        ? 'settling'
        : phase === 'understanding' || phase === 'planning'
          ? 'inward'
          : 'still';
  const motionIntensity = phase === 'stopped' || input.reducedMotion ? 0 : input.qualityTier === 'low' ? 0.6 : 1;
  return {
    phase,
    energy: energyOf(phase, input.reducedMotion, input.qualityTier),
    coherence,
    attentionDirection,
    workerCount: input.mirrorSnapshot.activeWorkers.length,
    verificationState,
    continuityState,
    semanticSignals: [...input.recentSemanticSignals],
    motionIntensity,
  };
}
