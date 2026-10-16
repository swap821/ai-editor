import { deriveLivingOrchestration } from './livingOrchestrator';
import { SEGMENT_ANCHORS } from './spineAnatomy';
import type { AttentionTransfer, MaterializedTabRecord, WorkspacePanel } from './tabStore';

export const BRAIN_ATTENTION_POSTURE_DURATION_MS = 920;

/** Local measured presentation, not a task, capability or authority state. */
export interface WorkPlaneAttentionTarget {
  targetId: string;
  lateral: number;
  vertical: number;
}

export interface BrainAttentionPostureInput {
  tabs: MaterializedTabRecord[];
  focusId: string | null;
  attention?: AttentionTransfer | null;
  panels?: readonly WorkspacePanel[];
  nowMs: number;
  /** Local input engagement, independent of retained workspace focus. */
  inputAttentionActive?: boolean;
  /** Undefined preserves standalone authored staging; null means the product
   * plane is unavailable. Never aim at a different record's measured plane. */
  planeTarget?: WorkPlaneAttentionTarget | null;
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
  panels,
  nowMs,
  inputAttentionActive = false,
  planeTarget,
}: BrainAttentionPostureInput): BrainAttentionPosture {
  // The intake is central, not another task/surface identity. Use the existing
  // resting attention amplitude without a timed transfer or model-work signal.
  if (inputAttentionActive) return {
    ...NEUTRAL_POSTURE,
    active: true,
    intensity: 0.32,
    pitch: -0.0186,
    offsetY: -0.0112,
    scaleBoost: 0.0058,
  };
  const orchestration = deriveLivingOrchestration({ tabs, focusId, attention });
  const focusedPanel = panels?.find(panel => panel.open && panel.id === focusId);
  const transfer = orchestration.attention;
  const transferAge = transfer ? nowMs - transfer.startedAt : Number.POSITIVE_INFINITY;
  const transferFresh = transferAge >= 0 && transferAge <= BRAIN_ATTENTION_POSTURE_DURATION_MS;
  const targetId = focusedPanel?.id ?? (transferFresh ? transfer?.toId : orchestration.focusId);
  if (!targetId) {
    return NEUTRAL_POSTURE;
  }

  const targetTab = tabs.find((tab) => tab.id === targetId);
  // DOM focus owns attention even when recovery History has no free anchor.
  // Never borrow a background result's geometry or manufacture a panel seat.
  const panelSeat = focusedPanel?.seatIndex;
  const panelAnchor = typeof panelSeat === 'number' && Number.isInteger(panelSeat)
    && panelSeat >= 0 && panelSeat < SEGMENT_ANCHORS.length ? SEGMENT_ANCHORS[panelSeat] : null;
  if (focusedPanel ? !panelAnchor : !targetTab || targetTab.lifecycle === 'retracting' || targetTab.kind === 'input') {
    return NEUTRAL_POSTURE;
  }
  if (planeTarget !== undefined && (!planeTarget || planeTarget.targetId !== targetId
    || !Number.isFinite(planeTarget.lateral) || !Number.isFinite(planeTarget.vertical))) return NEUTRAL_POSTURE;

  const transferStrength = !focusedPanel && transferFresh && transfer ? pulseEnvelope(transfer.startedAt, nowMs) : 0;
  const intensity = clamp(0.32 + transferStrength * 0.68, 0, 1);
  const lateral = planeTarget ? clamp(planeTarget.lateral, -1, 1)
    : panelAnchor ? 0 : clamp((targetTab!.targetLocal[0] || targetTab!.originLocal[0]) / 1.45, -1, 1);
  const vertebraDepth = clamp((Math.abs(panelAnchor?.y ?? targetTab!.originLocal[1]) - 0.9) / 2.1, 0, 1);
  const downwardAim = planeTarget ? clamp(planeTarget.vertical, -1, 1) : 0.42 + vertebraDepth * 0.58;

  return {
    active: true,
    targetId,
    intensity: round4(intensity),
    yaw: round4(lateral * 0.052 * intensity),
    pitch: round4(-downwardAim * 0.058 * intensity),
    roll: round4(-lateral * 0.034 * intensity),
    offsetX: round4(lateral * 0.045 * intensity),
    offsetY: round4(-downwardAim * 0.035 * intensity),
    scaleBoost: round4(0.018 * intensity),
  };
}
