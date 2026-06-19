import { deriveLivingOrchestration } from './livingOrchestrator';
import type { AttentionTransfer, MaterializedTabRecord } from './tabStore';

export const BRAIN_ATTENTION_POSTURE_DURATION_MS = 920;

export interface BrainAttentionPostureInput {
  tabs: MaterializedTabRecord[];
  focusId: string | null;
  attention?: AttentionTransfer | null;
  nowMs: number;
}

export interface BrainAttentionPosture {
  active: boolean;
  targetId: string | null;
  intensity: number;
  yaw: number;
  pitch: number;
  roll: number;
  offsetX: number;
  offsetY: number;
  scaleBoost: number;
}

const NEUTRAL_POSTURE: BrainAttentionPosture = {
  active: false,
  targetId: null,
  intensity: 0,
  yaw: 0,
  pitch: 0,
  roll: 0,
  offsetX: 0,
  offsetY: 0,
  scaleBoost: 0,
};

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

const round4 = (value: number) => Math.round(value * 10000) / 10000;

const pulseEnvelope = (startedAt: number, nowMs: number) => {
  const progress = clamp((nowMs - startedAt) / BRAIN_ATTENTION_POSTURE_DURATION_MS, 0, 1);
  if (progress <= 0 || progress >= 1) {
    return 0;
  }
  return Math.sin(progress * Math.PI);
};

export function deriveBrainAttentionPosture({
  tabs,
  focusId,
  attention,
  nowMs,
}: BrainAttentionPostureInput): BrainAttentionPosture {
  const orchestration = deriveLivingOrchestration({ tabs, focusId, attention });
  const transfer = orchestration.attention;
  const transferAge = transfer ? nowMs - transfer.startedAt : Number.POSITIVE_INFINITY;
  const transferFresh = transferAge >= 0 && transferAge <= BRAIN_ATTENTION_POSTURE_DURATION_MS;
  const targetId = transferFresh ? transfer?.toId : orchestration.focusId;
  if (!targetId) {
    return NEUTRAL_POSTURE;
  }

  const targetTab = tabs.find((tab) => tab.id === targetId);
  if (!targetTab || targetTab.lifecycle === 'retracting' || targetTab.kind === 'input') {
    return NEUTRAL_POSTURE;
  }

  const transferStrength = transferFresh && transfer ? pulseEnvelope(transfer.startedAt, nowMs) : 0;
  const intensity = clamp(0.32 + transferStrength * 0.68, 0, 1);
  const lateral = clamp((targetTab.targetLocal[0] || targetTab.originLocal[0]) / 1.45, -1, 1);
  const vertebraDepth = clamp((Math.abs(targetTab.originLocal[1]) - 0.9) / 2.1, 0, 1);
  const downwardAim = 0.42 + vertebraDepth * 0.58;

  return {
    active: true,
    targetId: targetTab.id,
    intensity: round4(intensity),
    yaw: round4(lateral * 0.052 * intensity),
    pitch: round4(-downwardAim * 0.058 * intensity),
    roll: round4(-lateral * 0.034 * intensity),
    offsetX: round4(lateral * 0.045 * intensity),
    offsetY: round4(-downwardAim * 0.035 * intensity),
    scaleBoost: round4(0.018 * intensity),
  };
}
