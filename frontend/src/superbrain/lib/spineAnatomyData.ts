/** Shared anatomy coordinates; scene vectors and DOM placement use one source. */
export const CORD_Z = -0.42;
export const SEGMENT_COUNT: number = 12;
export const SEGMENT_TOP_Y = -0.92;
export const SEGMENT_BOTTOM_Y = -2.85;

export const SEGMENT_ANCHOR_COORDINATES: ReadonlyArray<[number, number, number]> = Array.from(
  { length: SEGMENT_COUNT }, (_, i) => {
    const f = SEGMENT_COUNT === 1 ? 0 : i / (SEGMENT_COUNT - 1);
    // Same operation order as Three.MathUtils.lerp; no renderer evaluation.
    const y = (1 - f) * SEGMENT_TOP_Y + f * SEGMENT_BOTTOM_Y;
    const z = CORD_Z + Math.sin(f * Math.PI) * 0.04;
    return [0, y, z];
  },
);
