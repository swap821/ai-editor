import { deriveSpinalRootActuator, type SpinalRootActuator, type SpinalRootFlow, type SpinalRootRole } from './spinalRootActuator';
import type { MaterializedTabKind, TabLifecycle } from './tabStore';
import type { OutcomeImprintSnapshot } from './outcomeImprint';
import type { TurnMetabolismSnapshot } from './turnMetabolism';

export type Vec3Tuple = [number, number, number];

export interface VertebraConductorRootInput {
  kind: MaterializedTabKind;
  lifecycle?: TabLifecycle;
  focused: boolean;
  originLocal: Vec3Tuple;
  targetLocal: Vec3Tuple;
  surfaceWidth: number;
  surfaceHeight: number;
  waitingIndex?: number;
  metabolism?: TurnMetabolismSnapshot | null;
  outcome?: OutcomeImprintSnapshot | null;
}

export interface VertebraConductorRoot {
  id: string;
  pair: 'upper' | 'lower';
  role: SpinalRootRole;
  flow: SpinalRootFlow;
  start: Vec3Tuple;
  midA: Vec3Tuple;
  midB: Vec3Tuple;
  end: Vec3Tuple;
  radius: number;
  opacity: number;
  tension: number;
  stiffness: number;
  clampScale: number;
  tint: string;
  secondaryTint: string;
  textureMix: number;
  beadSpeed: number;
  beadOffset: number;
}

export interface VertebraConductorRoots {
  roots: VertebraConductorRoot[];
  rootNode: Vec3Tuple | null;
  gripNodes: Vec3Tuple[];
  nodeOpacity: number;
  actuator: SpinalRootActuator;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function sideTowardSurface(originX: number, targetX: number): number {
  return targetX >= originX ? 1 : -1;
}

function attentionScale(input: VertebraConductorRootInput): number {
  if (input.kind === 'input') return 0;
  if (input.focused) return 0.52;
  const index = Math.max(0, input.waitingIndex ?? 0);
  return clamp(0.16 - index * 0.025, 0.08, 0.16);
}

function metabolismScale(input: VertebraConductorRootInput): number {
  const metabolism = input.metabolism;
  if (!metabolism || metabolism.phase === 'rest') return 1;
  const focusWeight = input.focused ? 1 : 0.38;
  const approvalWeight = metabolism.phase === 'approval' && input.kind === 'approval' ? 1.18 : 1;
  return 1 + metabolism.rootExcitation * focusWeight * approvalWeight;
}

function outcomeScale(input: VertebraConductorRootInput): number {
  const outcome = input.outcome;
  if (!outcome || outcome.kind === 'none') return 1;
  const focusWeight = input.focused ? 1 : 0.28;
  const scarWeight = outcome.kind === 'scar' ? 1.16 : 1;
  return 1 + outcome.rootGlow * focusWeight * scarWeight;
}

function tuple(x: number, y: number, z: number): Vec3Tuple {
  return [Number(x.toFixed(4)), Number(y.toFixed(4)), Number(z.toFixed(4))];
}

export function deriveVertebraConductorRoots(input: VertebraConductorRootInput): VertebraConductorRoots {
  const actuator = deriveSpinalRootActuator(input);
  const attention = attentionScale(input);
  if (attention <= 0) {
    return { roots: [], rootNode: null, gripNodes: [], nodeOpacity: 0, actuator };
  }

  const [originX, originY, originZ] = input.originLocal;
  const [targetX, targetY, targetZ] = input.targetLocal;
  const side = sideTowardSurface(originX, targetX);
  const edgeX = targetX - side * input.surfaceWidth * 0.5;
  const focusReach = input.focused ? 1 : 0.4;
  const metabolic = metabolismScale(input);
  const imprint = outcomeScale(input);
  const liveScale = clamp(metabolic * imprint, 0, 1.9);
  const endZ = targetZ + (input.focused ? 0.012 : -0.04) + actuator.tension * 0.01;
  const clampPull = actuator.stiffness * (input.focused ? 0.028 : 0.012);
  const fan = [
    { id: 'upper-primary', pair: 'upper' as const, y: input.surfaceHeight * 0.34, z: 0.02, beadOffset: 0.02 },
    { id: 'upper-secondary', pair: 'upper' as const, y: input.surfaceHeight * 0.16, z: -0.018, beadOffset: 0.26 },
    { id: 'lower-secondary', pair: 'lower' as const, y: -input.surfaceHeight * 0.16, z: -0.012, beadOffset: 0.5 },
    { id: 'lower-primary', pair: 'lower' as const, y: -input.surfaceHeight * 0.34, z: 0.018, beadOffset: 0.74 },
  ];

  const roots = fan.map((root, index) => {
    const end = tuple(edgeX - side * clampPull, targetY + root.y, endZ + root.z);
    return {
      id: root.id,
      pair: root.pair,
      role: actuator.role,
      flow: actuator.flow,
      start: tuple(originX + side * 0.006 * (index - 1.5), originY + root.y * 0.045, originZ + root.z * 0.22),
      midA: tuple(
        originX + side * (0.11 + 0.045 * focusReach + actuator.tension * 0.026),
        originY + root.y * (0.12 - actuator.stiffness * 0.018),
        originZ + 0.044 + root.z * 0.2,
      ),
      midB: tuple(
        edgeX - side * (0.07 + 0.04 * focusReach + actuator.stiffness * 0.018),
        targetY + root.y * (0.74 + actuator.tension * 0.04),
        endZ + root.z * 0.7,
      ),
      end,
      radius: Number(
        ((0.0012 + attention * (input.focused ? 0.0018 : 0.0007)) * liveScale * actuator.radiusGain).toFixed(4),
      ),
      opacity: Number(
        clamp((0.018 + attention * (input.focused ? 0.14 : 0.06)) * liveScale * actuator.opacityGain, 0, 0.34).toFixed(4),
      ),
      tension: actuator.tension,
      stiffness: actuator.stiffness,
      clampScale: actuator.clampScale,
      tint: actuator.tint,
      secondaryTint: actuator.secondaryTint,
      textureMix: actuator.textureMix,
      beadSpeed: actuator.beadSpeed,
      beadOffset: root.beadOffset,
    };
  });

  return {
    roots,
    rootNode: tuple(originX, originY, originZ + 0.018),
    gripNodes: roots.map((root) => root.end),
    nodeOpacity: Number(
      clamp((0.05 + attention * (input.focused ? 0.18 : 0.07)) * liveScale * actuator.nodeGain, 0, 0.36).toFixed(4),
    ),
    actuator,
  };
}
