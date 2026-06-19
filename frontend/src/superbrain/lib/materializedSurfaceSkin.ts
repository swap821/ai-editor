import type { MaterializedTabKind } from './tabStore';
import type { OutcomeImprintSnapshot } from './outcomeImprint';
import type { TurnMetabolismSnapshot } from './turnMetabolism';

export interface MaterializedSurfaceSkinInput {
  kind: MaterializedTabKind;
  focused: boolean;
  waitingIndex?: number;
  metabolism?: TurnMetabolismSnapshot | null;
  outcome?: OutcomeImprintSnapshot | null;
}

export interface MaterializedSurfaceSkin {
  bodyBaseOpacity: number;
  bodyLiveOpacity: number;
  frameBaseOpacity: number;
  frameLiveOpacity: number;
  plateOpacity: number;
  headerBandOpacity: number;
  membraneOpacity: number;
  veinOpacity: number;
  nodeOpacity: number;
  emissiveIntensity: number;
  actionOpacity: number;
}

const BASE_SKIN: Record<MaterializedTabKind, MaterializedSurfaceSkin> = {
  content: {
    bodyBaseOpacity: 0.08,
    bodyLiveOpacity: 0.64,
    frameBaseOpacity: 0.04,
    frameLiveOpacity: 0.18,
    plateOpacity: 0.58,
    headerBandOpacity: 0.14,
    membraneOpacity: 0.055,
    veinOpacity: 0.1,
    nodeOpacity: 0.28,
    emissiveIntensity: 0.15,
    actionOpacity: 0.72,
  },
  input: {
    bodyBaseOpacity: 0.18,
    bodyLiveOpacity: 0.82,
    frameBaseOpacity: 0.08,
    frameLiveOpacity: 0.24,
    plateOpacity: 0.82,
    headerBandOpacity: 0,
    membraneOpacity: 0.12,
    veinOpacity: 0.2,
    nodeOpacity: 0.4,
    emissiveIntensity: 0.24,
    actionOpacity: 1,
  },
  approval: {
    bodyBaseOpacity: 0.07,
    bodyLiveOpacity: 0.66,
    frameBaseOpacity: 0.035,
    frameLiveOpacity: 0.14,
    plateOpacity: 0.62,
    headerBandOpacity: 0,
    membraneOpacity: 0.025,
    veinOpacity: 0.045,
    nodeOpacity: 0.18,
    emissiveIntensity: 0.075,
    actionOpacity: 0.78,
  },
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function workspaceAttentionScale(input: MaterializedSurfaceSkinInput): number {
  if (input.kind === 'input') return 1;
  if (input.focused) return 1;
  const index = Math.max(0, input.waitingIndex ?? 0);
  return clamp(0.58 - index * 0.075, 0.34, 0.58);
}

function scale(value: number, amount: number): number {
  return Number((value * amount).toFixed(4));
}

function scaleOpacity(value: number, amount: number, max = 0.96): number {
  return Number(clamp(value * amount, 0, max).toFixed(4));
}

function metabolismScale(input: MaterializedSurfaceSkinInput): number {
  const metabolism = input.metabolism;
  if (!metabolism || metabolism.phase === 'rest') return 1;
  const focusWeight = input.kind === 'input' ? 0.42 : input.focused ? 1 : 0.36;
  const kindWeight =
    metabolism.phase === 'approval' && input.kind === 'approval'
      ? 1.18
      : metabolism.phase === 'error'
        ? 1.1
        : 1;
  return 1 + metabolism.surfaceExcitation * focusWeight * kindWeight;
}

function outcomeScale(input: MaterializedSurfaceSkinInput): number {
  const outcome = input.outcome;
  if (!outcome || outcome.kind === 'none') return 1;
  const focusWeight = input.kind === 'input' ? 0 : input.focused ? 1 : 0.24;
  const scarWeight = outcome.kind === 'scar' ? 1.14 : 1;
  return 1 + outcome.surfaceGlow * focusWeight * scarWeight;
}

export function deriveMaterializedSurfaceSkin(input: MaterializedSurfaceSkinInput): MaterializedSurfaceSkin {
  const base = BASE_SKIN[input.kind];
  const attention = workspaceAttentionScale(input);
  const metabolic = metabolismScale(input);
  const imprint = outcomeScale(input);
  const bodyMetabolic = 1 + (metabolic - 1) * 0.16;
  const frameMetabolic = 1 + (metabolic - 1) * 0.32;
  const plateMetabolic = 1 + (metabolic - 1) * 0.06;
  const signalMetabolic = 1 + (metabolic - 1) * 0.72;
  const bodyImprint = 1 + (imprint - 1) * 0.08;
  const frameImprint = 1 + (imprint - 1) * 0.42;
  const plateImprint = 1 + (imprint - 1) * 0.04;
  const signalImprint = 1 + (imprint - 1) * 0.88;

  return {
    bodyBaseOpacity: scaleOpacity(base.bodyBaseOpacity, attention * bodyMetabolic * bodyImprint),
    bodyLiveOpacity: scaleOpacity(base.bodyLiveOpacity, attention * bodyMetabolic * bodyImprint),
    frameBaseOpacity: scaleOpacity(base.frameBaseOpacity, attention * frameMetabolic * frameImprint),
    frameLiveOpacity: scaleOpacity(base.frameLiveOpacity, attention * frameMetabolic * frameImprint),
    plateOpacity: scaleOpacity(base.plateOpacity, attention * plateMetabolic * plateImprint),
    headerBandOpacity: scaleOpacity(base.headerBandOpacity, attention),
    membraneOpacity: scaleOpacity(base.membraneOpacity, attention * signalMetabolic * signalImprint),
    veinOpacity: scaleOpacity(base.veinOpacity, attention * signalMetabolic * signalImprint),
    nodeOpacity: scaleOpacity(base.nodeOpacity, attention * signalMetabolic * signalImprint),
    emissiveIntensity: scale(
      base.emissiveIntensity,
      attention * (1 + (metabolic - 1) * 0.36) * (1 + (imprint - 1) * 0.28),
    ),
    actionOpacity: scaleOpacity(
      base.actionOpacity,
      attention * (1 + (metabolic - 1) * 0.5) * (1 + (imprint - 1) * 0.32),
      1,
    ),
  };
}
