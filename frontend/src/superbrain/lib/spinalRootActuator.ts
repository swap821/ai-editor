import type { MaterializedTabKind, TabLifecycle } from './tabStore';
import type { OutcomeImprintSnapshot } from './outcomeImprint';
import type { TurnMetabolismSnapshot } from './turnMetabolism';

export type SpinalRootRole =
  | 'resting'
  | 'sensing'
  | 'gripping'
  | 'conducting'
  | 'holding'
  | 'error'
  | 'reabsorbing';

export type SpinalRootFlow = 'none' | 'outbound' | 'return' | 'bidirectional';

export interface SpinalRootActuatorInput {
  kind: MaterializedTabKind;
  lifecycle?: TabLifecycle;
  focused: boolean;
  waitingIndex?: number;
  metabolism?: TurnMetabolismSnapshot | null;
  outcome?: OutcomeImprintSnapshot | null;
}

export interface SpinalRootActuator {
  role: SpinalRootRole;
  flow: SpinalRootFlow;
  tension: number;
  stiffness: number;
  opacityGain: number;
  radiusGain: number;
  nodeGain: number;
  clampScale: number;
  beadSpeed: number;
  pulseRate: number;
  tint: string;
  secondaryTint: string;
  textureMix: number;
}

const REST_ACTUATOR: SpinalRootActuator = {
  role: 'resting',
  flow: 'none',
  tension: 0,
  stiffness: 0,
  opacityGain: 0,
  radiusGain: 0,
  nodeGain: 0,
  clampScale: 0.62,
  beadSpeed: 0,
  pulseRate: 0.9,
  tint: '#79ebff',
  secondaryTint: '#c6b8ff',
  textureMix: 0.24,
};

const ROLE_PROFILE: Record<
  Exclude<SpinalRootRole, 'resting'>,
  Omit<SpinalRootActuator, 'role'>
> = {
  sensing: {
    flow: 'bidirectional',
    tension: 0.26,
    stiffness: 0.22,
    opacityGain: 0.74,
    radiusGain: 0.74,
    nodeGain: 0.72,
    clampScale: 0.76,
    beadSpeed: 0.12,
    pulseRate: 1.1,
    tint: '#79ebff',
    secondaryTint: '#b9b6ff',
    textureMix: 0.32,
  },
  gripping: {
    flow: 'bidirectional',
    tension: 0.56,
    stiffness: 0.58,
    opacityGain: 1,
    radiusGain: 1,
    nodeGain: 1,
    clampScale: 1.02,
    beadSpeed: 0.18,
    pulseRate: 1.6,
    tint: '#8dffd1',
    secondaryTint: '#b9b6ff',
    textureMix: 0.42,
  },
  conducting: {
    flow: 'outbound',
    tension: 0.78,
    stiffness: 0.72,
    opacityGain: 1.28,
    radiusGain: 1.18,
    nodeGain: 1.18,
    clampScale: 1.15,
    beadSpeed: 0.34,
    pulseRate: 3.4,
    tint: '#9affee',
    secondaryTint: '#d5c6ff',
    textureMix: 0.52,
  },
  holding: {
    flow: 'bidirectional',
    tension: 0.9,
    stiffness: 1,
    opacityGain: 1.2,
    radiusGain: 1.12,
    nodeGain: 1.28,
    clampScale: 1.26,
    beadSpeed: 0.07,
    pulseRate: 0.92,
    tint: '#ffb06e',
    secondaryTint: '#c6b8ff',
    textureMix: 0.38,
  },
  error: {
    flow: 'return',
    tension: 0.84,
    stiffness: 0.82,
    opacityGain: 1.34,
    radiusGain: 1.1,
    nodeGain: 1.22,
    clampScale: 1.1,
    beadSpeed: 0.3,
    pulseRate: 5.8,
    tint: '#ff5f7a',
    secondaryTint: '#b9b6ff',
    textureMix: 0.44,
  },
  reabsorbing: {
    flow: 'return',
    tension: 0.64,
    stiffness: 0.48,
    opacityGain: 1.08,
    radiusGain: 0.96,
    nodeGain: 1.04,
    clampScale: 0.9,
    beadSpeed: 0.26,
    pulseRate: 2.2,
    tint: '#a9fff3',
    secondaryTint: '#c6b8ff',
    textureMix: 0.46,
  },
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function round4(value: number): number {
  return Math.round(value * 10000) / 10000;
}

function roleFor(input: SpinalRootActuatorInput): SpinalRootRole {
  if (input.kind === 'input') return 'resting';
  if (input.lifecycle === 'retracting') return 'reabsorbing';

  const metabolism = input.metabolism;
  const outcome = input.outcome;
  const focused = input.focused;

  if (focused && (outcome?.kind === 'scar' || metabolism?.phase === 'error')) return 'error';
  if (input.kind === 'approval' && focused) return 'holding';
  if (focused && (metabolism?.phase === 'working' || metabolism?.phase === 'thinking')) return 'conducting';
  if (focused) return 'gripping';

  return 'sensing';
}

function intensityFor(input: SpinalRootActuatorInput, role: SpinalRootRole): number {
  if (role === 'resting') return 0;
  if (role === 'holding') return input.metabolism?.phase === 'approval' ? 1 : 0.86;
  if (role === 'error') return Math.max(input.metabolism?.intensity ?? 0, input.outcome?.intensity ?? 0, 0.74);
  if (role === 'reabsorbing') return 0.78;
  if (role === 'conducting') return clamp(input.metabolism?.intensity ?? 0.72, 0.5, 1);
  if (role === 'gripping') return 0.72;

  const index = Math.max(0, input.waitingIndex ?? 0);
  return clamp(0.52 - index * 0.08, 0.28, 0.52);
}

export function deriveSpinalRootActuator(input: SpinalRootActuatorInput): SpinalRootActuator {
  const role = roleFor(input);
  if (role === 'resting') return REST_ACTUATOR;

  const profile = ROLE_PROFILE[role];
  const intensity = intensityFor(input, role);
  const live = input.focused ? intensity : intensity * 0.78;

  return {
    role,
    flow: profile.flow,
    tension: round4(clamp(profile.tension * (0.58 + live * 0.42), 0, 1)),
    stiffness: round4(clamp(profile.stiffness * (0.62 + live * 0.38), 0, 1)),
    opacityGain: round4(clamp(profile.opacityGain * (0.68 + live * 0.32), 0, 1.45)),
    radiusGain: round4(clamp(profile.radiusGain * (0.76 + live * 0.24), 0, 1.28)),
    nodeGain: round4(clamp(profile.nodeGain * (0.72 + live * 0.28), 0, 1.36)),
    clampScale: round4(clamp(profile.clampScale * (0.86 + live * 0.18), 0.46, 1.42)),
    beadSpeed: round4(profile.beadSpeed * (0.72 + live * 0.34)),
    pulseRate: profile.pulseRate,
    tint: profile.tint,
    secondaryTint: profile.secondaryTint,
    textureMix: round4(clamp(profile.textureMix * (0.78 + live * 0.22), 0, 0.64)),
  };
}
