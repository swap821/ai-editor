import * as THREE from 'three';

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

// ── Body scene frame ────────────────────────────────────────────────────────
// Product-owned scene effects are siblings of the animated brain group. Publish
// its complete world matrix so their group-local paths inherit the same voyage,
// orbit and scale instead of drifting away from the visible body.
let bodyGroupWorldMatrix: THREE.Matrix4 | null = null;
let bodyGroupSource: THREE.Object3D | null = null;

export function setBodyGroupWorldMatrix(matrix: THREE.Matrix4, source: THREE.Object3D | null = null): void {
  if (!bodyGroupWorldMatrix) bodyGroupWorldMatrix = new THREE.Matrix4();
  bodyGroupWorldMatrix.copy(matrix);
  bodyGroupSource = source;
}

/** Release only this renderer's body; a late old-root cleanup cannot clear a replacement. */
export function clearBodyGroupWorldMatrix(source: THREE.Object3D): void {
  if (bodyGroupSource !== source) return;
  bodyGroupSource = null;
  bodyGroupWorldMatrix = null;
}

/** Resolve the mounted body's current ancestor pose into caller-owned storage.
 * Float updates after its child callbacks; a copied child-frame matrix lags it.
 * Matrix-only publishers retain their independent snapshot-copy contract. */
export function copyBodyGroupWorldMatrix(target: THREE.Matrix4): boolean {
  if (bodyGroupSource) {
    bodyGroupSource.updateWorldMatrix(true, false);
    target.copy(bodyGroupSource.matrixWorld);
    return true;
  }
  if (!bodyGroupWorldMatrix) return false;
  target.copy(bodyGroupWorldMatrix);
  return true;
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

// Presentation geometry, owned by the mounted point field. Keep the actual
// source transform (including dock, voyage and ancestors), not another pose.
let cortexShapeSource: THREE.Object3D | null = null;
let cortexShapeBounds: THREE.Box3 | null = null;
let bodyShapeBounds: THREE.Box3 | null = null;

export function setCortexShape(source: THREE.Object3D, bounds: THREE.Box3, bodyBounds = bounds): void {
  cortexShapeSource = source;
  cortexShapeBounds = bounds.clone();
  bodyShapeBounds = bodyBounds.clone();
}

export function clearCortexShape(source: THREE.Object3D): void {
  if (cortexShapeSource !== source) return;
  cortexShapeSource = null;
  cortexShapeBounds = null;
  bodyShapeBounds = null;
}

/** The intake junction has raw body-axis band zero. Read the mounted field's
 * actual shader withdrawal, not a second phase target or damping clock. Shape
 * ownership already protects this read from late replacement-root cleanup.
 * Legacy/no-field consumers keep their authored presentation. */
export function getCaudaIntakePresence(): number {
  const material = (cortexShapeSource as THREE.Points | null)?.material;
  if (!material || Array.isArray(material) || !(material instanceof THREE.ShaderMaterial)) return 1;
  const withdrawal = material.uniforms.uSprayHide?.value;
  if (typeof withdrawal !== 'number' || !Number.isFinite(withdrawal)) return 0;
  return 1 - THREE.MathUtils.clamp(withdrawal, 0, 1);
}

function copyShapeWorldBounds(target: THREE.Box3, bounds: THREE.Box3 | null): boolean {
  if (!cortexShapeSource || !bounds) return false;
  cortexShapeSource.updateWorldMatrix(true, false);
  target.copy(bounds).applyMatrix4(cortexShapeSource.matrixWorld);
  return !target.isEmpty()
    && Number.isFinite(target.min.x) && Number.isFinite(target.min.y) && Number.isFinite(target.min.z)
    && Number.isFinite(target.max.x) && Number.isFinite(target.max.y) && Number.isFinite(target.max.z);
}

/** Copy the current protected head envelope into caller-owned storage. */
export function copyCortexWorldBounds(target: THREE.Box3): boolean {
  return copyShapeWorldBounds(target, cortexShapeBounds);
}

/** Keep the fused envelope oriented until projection. A world-axis box around
 * a tall rotated cord invents occupied screen space outside the painted body. */
export function copyBodyShapeWorldFrame(bounds: THREE.Box3, world: THREE.Matrix4): boolean {
  if (!cortexShapeSource || !bodyShapeBounds || bodyShapeBounds.isEmpty()) return false;
  cortexShapeSource.updateWorldMatrix(true, false);
  bounds.copy(bodyShapeBounds);
  world.copy(cortexShapeSource.matrixWorld);
  return Number.isFinite(bounds.min.x + bounds.min.y + bounds.min.z + bounds.max.x + bounds.max.y + bounds.max.z)
    && world.elements.every(Number.isFinite);
}

export function __resetSpineFusionForTests(): void {
  fusion = IDENTITY;
  brainDockScale = 1;
  cortexAnchor = [0, 0.1, 0];
  bodyGroupWorldMatrix = null;
  bodyGroupSource = null;
  cortexShapeSource = null;
  cortexShapeBounds = null;
  bodyShapeBounds = null;
}
