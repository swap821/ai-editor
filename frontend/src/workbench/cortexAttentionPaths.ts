export type CortexPathPoint = [number, number, number];
export type CortexCurrentPath = [CortexPathPoint, CortexPathPoint, CortexPathPoint];

// The input current meets the spine's visible centerline at the intake height.
// Materialized-surface anchors retain their rearward z offset; applying the
// body's yaw to that surface offset displaces a central composer cue sideways.
export const CORTEX_COMPOSER_INTAKE_LOCAL = [0, -1.08, 0] as const;

export interface CortexCurrentPathInput {
  origin: readonly [number, number, number];
  target: readonly [number, number, number] | null;
  activity: number;
  convergence: number;
  count: number;
  /** Use one unambiguous path that physically lands on a local interaction anchor. */
  contactTarget?: boolean;
}

export interface CortexAttentionSpring {
  readonly positions: Float64Array;
  readonly velocities: Float64Array;
  readonly targets: Float64Array;
}

export interface CortexAttentionPulseState {
  active: boolean;
  elapsedSeconds: number;
  progress: number;
  direction: 'hidden' | 'inbound' | 'settled' | 'outbound';
}

export const CORTEX_ATTENTION_PULSE_DURATION_SECONDS = 0.72;

const ATTENTION_SPRING_FREQUENCY = 24;
const POSITION_SETTLE_EPSILON = 0.0001;
const VELOCITY_SETTLE_EPSILON = 0.001;

export function createCortexAttentionPulseState(): CortexAttentionPulseState {
  return { active: false, elapsedSeconds: 0, progress: 0, direction: 'hidden' };
}

/** Transit once on each draft edge; reversals continue from the current position. */
export function retargetCortexAttentionPulse(
  pulse: CortexAttentionPulseState,
  active: boolean,
  reducedMotion = false,
): void {
  if (pulse.active === active) {
    if (active && reducedMotion) {
      pulse.progress = 1;
      pulse.elapsedSeconds = CORTEX_ATTENTION_PULSE_DURATION_SECONDS;
      pulse.direction = 'settled';
    }
    return;
  }

  pulse.active = active;
  if (reducedMotion) {
    pulse.progress = active ? 1 : 0;
    pulse.elapsedSeconds = pulse.progress * CORTEX_ATTENTION_PULSE_DURATION_SECONDS;
    pulse.direction = active ? 'settled' : 'hidden';
    return;
  }

  pulse.direction = active ? 'inbound' : 'outbound';
}

/** Returns cortex→intake progress until the draft settles or the returning bead vanishes. */
export function advanceCortexAttentionPulse(
  pulse: CortexAttentionPulseState,
  deltaSeconds: number,
  reducedMotion = false,
): number | null {
  if (reducedMotion) {
    pulse.progress = pulse.active ? 1 : 0;
    pulse.elapsedSeconds = pulse.progress * CORTEX_ATTENTION_PULSE_DURATION_SECONDS;
    pulse.direction = pulse.active ? 'settled' : 'hidden';
    return pulse.active ? 1 : null;
  }
  if (pulse.direction === 'hidden') return null;
  if (pulse.direction === 'settled') return 1;

  const delta = Number.isFinite(deltaSeconds) ? Math.max(0, Math.min(deltaSeconds, 0.25)) : 0;
  const progressDelta = delta / CORTEX_ATTENTION_PULSE_DURATION_SECONDS;
  if (pulse.direction === 'inbound') {
    pulse.progress = Math.min(1, pulse.progress + progressDelta);
    if (pulse.progress === 1) pulse.direction = 'settled';
  } else {
    pulse.progress = Math.max(0, pulse.progress - progressDelta);
    if (pulse.progress === 0) {
      pulse.direction = 'hidden';
      pulse.elapsedSeconds = 0;
      return null;
    }
  }
  pulse.elapsedSeconds = pulse.progress * CORTEX_ATTENTION_PULSE_DURATION_SECONDS;
  return pulse.progress;
}

function flattenPaths(paths: readonly CortexCurrentPath[]): Float64Array {
  const values = new Float64Array(paths.length * 9);
  let offset = 0;
  for (const path of paths) {
    for (const point of path) {
      values[offset] = point[0];
      values[offset + 1] = point[1];
      values[offset + 2] = point[2];
      offset += 3;
    }
  }
  return values;
}

/** Create reusable numeric buffers for frame-by-frame attention retargeting. */
export function createCortexAttentionSpring(paths: readonly CortexCurrentPath[]): CortexAttentionSpring {
  const positions = flattenPaths(paths);
  return {
    positions,
    velocities: new Float64Array(positions.length),
    targets: new Float64Array(positions),
  };
}

/**
 * Retarget from the current position and velocity, so rapid focus changes
 * interrupt naturally instead of restarting or queuing a transition.
 */
export function retargetCortexAttentionSpring(
  spring: CortexAttentionSpring,
  paths: readonly CortexCurrentPath[],
  reducedMotion = false,
): void {
  const nextTargets = flattenPaths(paths);
  if (nextTargets.length !== spring.targets.length) {
    throw new RangeError('Cortical attention paths must retain their bounded point count');
  }

  spring.targets.set(nextTargets);
  if (!reducedMotion) return;

  spring.positions.set(nextTargets);
  spring.velocities.fill(0);
}

/** Advance an exact critically-damped spring; returns whether geometry moved. */
export function advanceCortexAttentionSpring(spring: CortexAttentionSpring, deltaSeconds: number): boolean {
  const delta = Number.isFinite(deltaSeconds) ? Math.max(0, Math.min(deltaSeconds, 0.25)) : 0;
  if (delta === 0) return false;

  const frequency = ATTENTION_SPRING_FREQUENCY;
  const decay = Math.exp(-frequency * delta);
  let moved = false;

  for (let index = 0; index < spring.positions.length; index += 1) {
    const position = spring.positions[index];
    const velocity = spring.velocities[index];
    const displacement = position - spring.targets[index];
    const combined = velocity + frequency * displacement;
    const nextDisplacement = (displacement + combined * delta) * decay;
    const nextVelocity = (velocity - frequency * combined * delta) * decay;

    if (Math.abs(nextDisplacement) < POSITION_SETTLE_EPSILON
      && Math.abs(nextVelocity) < VELOCITY_SETTLE_EPSILON) {
      spring.positions[index] = spring.targets[index];
      spring.velocities[index] = 0;
      moved ||= Math.abs(displacement) > 0 || Math.abs(velocity) > 0;
      continue;
    }

    spring.positions[index] = spring.targets[index] + nextDisplacement;
    spring.velocities[index] = nextVelocity;
    moved ||= nextDisplacement !== displacement || nextVelocity !== velocity;
  }

  return moved;
}

const LEGACY_AXES: readonly (readonly [number, number, number])[] = [
  [1, 0.38, 0.24],
  [-0.72, 0.56, 0.18],
  [0.18, -0.68, 0.52],
];

function clampUnit(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function normalize(vector: readonly number[]): [number, number, number] {
  const length = Math.hypot(vector[0], vector[1], vector[2]);
  if (length < 1e-8) return [0, 0, 0];
  return [vector[0] / length, vector[1] / length, vector[2] / length];
}

function addScaled(
  origin: readonly [number, number, number],
  direction: readonly [number, number, number],
  distance: number,
  lateral: readonly [number, number, number],
  lateralScale: number,
): CortexPathPoint {
  return [
    origin[0] + direction[0] * distance + lateral[0] * lateralScale,
    origin[1] + direction[1] * distance + lateral[1] * lateralScale,
    origin[2] + direction[2] * distance + lateral[2] * lateralScale,
  ];
}

/**
 * Gives the cortical current a stable visual bearing toward the focused
 * anatomical seat. Without a workspace target, the existing calm field is
 * preserved exactly. This is a render-only cue; it carries no task authority.
 */
export function deriveCortexAttentionPaths(input: CortexCurrentPathInput): CortexCurrentPath[] {
  const count = input.contactTarget ? 1 : Math.max(1, Math.min(LEGACY_AXES.length, Math.trunc(input.count)));
  const activity = clampUnit(input.activity);
  const convergence = clampUnit(input.convergence);
  const reach = 0.18 + activity * 0.2;
  const targetVector: CortexPathPoint | null = input.target
    ? [input.target[0] - input.origin[0], input.target[1] - input.origin[1], input.target[2] - input.origin[2]]
    : null;
  const targetLength = targetVector ? Math.hypot(...targetVector) : 0;

  if (!targetVector || targetLength < 1e-8) {
    return LEGACY_AXES.slice(0, count).map((axis, index) => {
      const settle = reach * (1 - convergence) * (0.78 + index * 0.06);
      return [
        addScaled(input.origin, axis, 0.08, [0, 0, 0], 0),
        addScaled(input.origin, axis, reach, [0, 0, 0], 0),
        addScaled(input.origin, axis, settle, [0, 0, 0], 0),
      ];
    });
  }

  const direction = normalize(targetVector);
  const reference: CortexPathPoint = Math.abs(direction[1]) > 0.92 ? [1, 0, 0] : [0, 1, 0];
  const side = normalize([
    direction[1] * reference[2] - direction[2] * reference[1],
    direction[2] * reference[0] - direction[0] * reference[2],
    direction[0] * reference[1] - direction[1] * reference[0],
  ]);
  const offsets = count === 3 ? [-1, 0, 1] : count === 2 ? [-0.5, 0.5] : [0];
  const targetedReach = input.contactTarget
    ? targetLength
    : Math.min(0.78, targetLength * (0.54 + activity * 0.04));

  return offsets.map((offset, index) => {
    const fan = offset * 0.045;
    const settle = input.contactTarget
      ? targetedReach
      : targetedReach * (1 - convergence * 0.28) * (0.98 + index * 0.01);
    return [
      addScaled(input.origin, direction, Math.min(0.08, targetedReach * 0.16), side, fan * 0.35),
      addScaled(input.origin, direction, targetedReach * 0.62, side, fan),
      addScaled(input.origin, direction, settle, side, input.contactTarget ? 0 : fan * (1 - convergence)),
    ];
  });
}
