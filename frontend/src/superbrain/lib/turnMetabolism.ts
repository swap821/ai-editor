import { useEffect, useState } from 'react';
import { useMirrorStore } from './mirrorStore';
import { postureHex, type BodyPostureKey } from './bodyPosture';

export type TurnMetabolismPhase = 'rest' | 'thinking' | 'working' | 'approval' | 'error' | 'settling';

export interface TurnMetabolismSnapshot {
  phase: TurnMetabolismPhase;
  intensity: number;
  surfaceExcitation: number;
  rootExcitation: number;
  breathGain: number;
  tint: string;
  held: boolean;
  changedAt: number;
}

const PHASE_POSTURE: Record<TurnMetabolismPhase, BodyPostureKey> = {
  rest: 'rest',
  thinking: 'think',
  working: 'stream',
  approval: 'hold',
  error: 'error',
  settling: 'complete',
};

const PHASE_TINT: Record<TurnMetabolismPhase, string> = {
  rest: postureHex(PHASE_POSTURE.rest),
  thinking: postureHex(PHASE_POSTURE.thinking),
  working: postureHex(PHASE_POSTURE.working),
  approval: postureHex(PHASE_POSTURE.approval),
  error: postureHex(PHASE_POSTURE.error),
  settling: postureHex(PHASE_POSTURE.settling),
};

export const REST_TURN_METABOLISM: TurnMetabolismSnapshot = {
  phase: 'rest',
  intensity: 0,
  surfaceExcitation: 0,
  rootExcitation: 0,
  breathGain: 0,
  tint: PHASE_TINT.rest,
  held: false,
  changedAt: 0,
};

function round4(value: number): number {
  return Math.round(value * 10000) / 10000;
}

export function deriveTurnMetabolismSnapshot(phase: string): TurnMetabolismSnapshot {
  const normalizedPhase: TurnMetabolismPhase = (['thinking', 'working', 'approval', 'error', 'settling'].includes(phase) ? phase : (phase === 'active' ? 'working' : 'rest')) as TurnMetabolismPhase;
  
  const profile = {
    rest: { surface: 0, root: 0, breath: 0, intensity: 0 },
    thinking: { surface: 0.24, root: 0.2, breath: 0.12, intensity: 0.4 },
    working: { surface: 0.55, root: 0.7, breath: 0.32, intensity: 0.8 },
    approval: { surface: 0.68, root: 0.78, breath: -0.18, intensity: 1.0 },
    error: { surface: 0.72, root: 0.56, breath: 0.22, intensity: 0.9 },
    settling: { surface: 0.2, root: 0.16, breath: 0.08, intensity: 0.3 },
  }[normalizedPhase];

  return {
    phase: normalizedPhase,
    intensity: profile.intensity,
    surfaceExcitation: round4(profile.surface * profile.intensity),
    rootExcitation: round4(profile.root * profile.intensity),
    breathGain: round4(profile.breath * profile.intensity),
    tint: PHASE_TINT[normalizedPhase],
    held: normalizedPhase === 'approval',
    changedAt: Date.now(),
  };
}

export function getTurnMetabolismSnapshot(): TurnMetabolismSnapshot {
  const phase = useMirrorStore.getState().phase;
  return deriveTurnMetabolismSnapshot(phase);
}

type MetabolismListener = (snapshot: TurnMetabolismSnapshot) => void;

export function subscribeTurnMetabolism(listener: MetabolismListener): () => void {
  return useMirrorStore.subscribe(
    (state) => state.phase,
    (phase) => {
      listener(deriveTurnMetabolismSnapshot(phase));
    }
  );
}

export function useTurnMetabolism(): TurnMetabolismSnapshot {
  const phase = useMirrorStore((s) => s.phase);
  return deriveTurnMetabolismSnapshot(phase);
}
