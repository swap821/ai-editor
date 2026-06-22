/**
 * spineFusionBus — publishes the EXACT transform that BrainPointField uses to
 * weld the spine point-cloud into the brain cloud, so other systems (the
 * materialized work slabs) can anchor onto the *visible* fused spine.
 *
 * BrainPointField builds the fused geometry by mapping each raw spine-anatomy
 * point P (SEGMENT_ANCHORS space) into brain-local space:
 *     fused = P * spineScale + weld
 * where spineScale = 1/BRAIN_SCALE and weld = brainstemCentroid - cordTop*spineScale
 * (both computed at runtime from the sampled GLB). It calls setSpineFusion() once
 * the geometry is built; consumers read getSpineFusion()/fuseSpinePoint() to place
 * surfaces on the real vertebrae. Until the field is built, `ready` is false and
 * fuseSpinePoint is identity (callers fall back to raw mesh-spine coords).
 *
 * Module-singleton, SSR-safe (no window/document).
 */
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

// ── Brain dock scale ─────────────────────────────────────────────────────────
// The brain (brainVisualRef) shrinks while orchestrating (SOUL P1). The work slabs
// + their nerves render as a SIBLING of that scaling group, so to anchor a nerve on
// the *visible* (shrunken) vertebra they multiply the fused vertebra by this eased
// dock scale. SuperbrainScene publishes it each frame; 1 = full size (rest).
let brainDockScale = 1;

export function setBrainDockScale(scale: number): void {
  brainDockScale = scale;
}

export function getBrainDockScale(): number {
  return brainDockScale;
}

// ── Cortex anchor ────────────────────────────────────────────────────────────
// The brain-HEAD centroid in cloud-local space (where the point cloud is sampled).
// BrainPointField publishes it once the geometry is built. Reabsorption motes
// (rendered as a SIBLING of the scaled brain-visual group, in brain-group-local
// space) read this and multiply by getBrainDockScale() to land in the *visible*
// (shrunken, voyaging, crowned) cortex — "energy returns up the spine INTO the
// brain". The hardcoded [0,0.1,0] it replaces missed the cortex every frame the
// being scaled/voyaged. Default is that old point so behavior is safe pre-publish.
let cortexAnchor: [number, number, number] = [0, 0.1, 0];

export function setCortexAnchor(anchor: readonly [number, number, number]): void {
  cortexAnchor = [anchor[0], anchor[1], anchor[2]];
}

export function getCortexAnchor(): [number, number, number] {
  return cortexAnchor;
}

export function __resetSpineFusionForTests(): void {
  fusion = IDENTITY;
  brainDockScale = 1;
  cortexAnchor = [0, 0.1, 0];
}
