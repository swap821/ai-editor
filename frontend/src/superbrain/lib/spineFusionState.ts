export interface SpineFusion {
  ready: boolean;
  spineScale: number;
  weld: [number, number, number];
}

const IDENTITY: SpineFusion = { ready: false, spineScale: 1, weld: [0, 0, 0] };

let fusion: SpineFusion = IDENTITY;

export function setSpineFusion(spineScale: number, weld: [number, number, number]): void {
  fusion = { ready: true, spineScale, weld: [weld[0], weld[1], weld[2]] };
}

export function getSpineFusion(): SpineFusion {
  return fusion;
}

/** Map a raw spine-anatomy point (SEGMENT_ANCHORS space) into the fused brain-
 *  local space where the visible spine actually lives. Identity until ready. */
export function fuseSpinePoint(p: readonly [number, number, number]): [number, number, number] {
  const f = fusion;
  if (!f.ready) return [p[0], p[1], p[2]];
  return [p[0] * f.spineScale + f.weld[0], p[1] * f.spineScale + f.weld[1], p[2] * f.spineScale + f.weld[2]];
}

/** Shared legacy test reset; the renderer bus delegates to this same owner. */
export function __resetSpineFusionStateForTests(): void { fusion = IDENTITY; }
