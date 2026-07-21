export const PARTICLE_COUNT = 820;
export const INNER_RADIUS = 1.55;
export const OUTER_RADIUS = 4.85;
export const INFALL_PERIOD = 34;
export const SPIN_TURNS = 1.6;
export const TAU = Math.PI * 2;

export const BASE_TILT_X = 0.42;
export const BASE_TILT_Z = -0.14;

// "Knowledge-acquired" feeding pulse: disc brightness multiplies x1.0 -> x1.5
// at full strength, decaying over ~1.2s (exp(-3.6 * 1.2s) ~= 1.3%).
export const PULSE_GAIN = 0.5;
export const PULSE_DECAY_RATE = 3.6;

export interface DiskGeometryData {
  positions: Float32Array;
  angles: Float32Array;
  offsets: Float32Array;
  speeds: Float32Array;
  phases: Float32Array;
  sizes: Float32Array;
  tints: Float32Array;
  jitters: Float32Array;
}

function createSeededRandom(seed: number) {
  let state = seed >>> 0;
  return () => {
    state += 0x6d2b79f5;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function pickTint(roll: number) {
  if (roll < 0.6) return 0;
  if (roll < 0.78) return 3;
  if (roll < 0.9) return 1;
  return 2;
}

export function createDiskData(): DiskGeometryData {
  const random = createSeededRandom(0x41434352);
  const positions = new Float32Array(PARTICLE_COUNT * 3);
  const angles = new Float32Array(PARTICLE_COUNT);
  const offsets = new Float32Array(PARTICLE_COUNT);
  const speeds = new Float32Array(PARTICLE_COUNT);
  const phases = new Float32Array(PARTICLE_COUNT);
  const sizes = new Float32Array(PARTICLE_COUNT);
  const tints = new Float32Array(PARTICLE_COUNT);
  const jitters = new Float32Array(PARTICLE_COUNT);

  for (let index = 0; index < PARTICLE_COUNT; index += 1) {
    angles[index] = random() * TAU;
    offsets[index] = random() + random() - 1;
    speeds[index] = 0.75 + random() * 0.55;
    phases[index] = random();
    sizes[index] = 0.5 + random() * 0.85;
    tints[index] = pickTint(random());
    jitters[index] = random() * 2 - 1;
  }

  return { positions, angles, offsets, speeds, phases, sizes, tints, jitters };
}
