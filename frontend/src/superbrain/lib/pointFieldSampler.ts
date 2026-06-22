// frontend/src/superbrain/lib/pointFieldSampler.ts
import * as THREE from 'three';
import { MeshSurfaceSampler } from 'three/examples/jsm/math/MeshSurfaceSampler.js';

const TAU = Math.PI * 2;

/** One sampling source: a processed (region-colored) clone + its budget share +
 *  the world-Y range used to normalize aBand (0 at axisMin → 1 at axisMax). */
export interface PointFieldSource {
  object: THREE.Object3D;
  /** fraction of the total budget for this source (the array should sum ~1). */
  share: number;
  /** group-local Y that maps to aBand=0 (e.g. cloud top). */
  axisMin: number;
  /** group-local Y that maps to aBand=1 (e.g. root base). */
  axisMax: number;
}

export interface PointFieldData {
  positions: Float32Array; // itemSize 3 (aBase, world-transformed + jitter)
  colors: Float32Array;    // itemSize 3 (region RGB, linear-sRGB)
  normals: Float32Array;   // itemSize 3 (surface normal)
  sizes: Float32Array;     // itemSize 1 (~[0.6,1.4])
  phases: Float32Array;    // itemSize 1 (0..2π)
  speeds: Float32Array;    // itemSize 1 (~[0.6,1.4])
  scatter: Float32Array;   // itemSize 3 (unit dir, arrival/dissolve)
  births: Float32Array;    // itemSize 1 (0..1 stagger)
  bands: Float32Array;     // itemSize 1 (normalized body-axis coord)
  count: number;
}

/** Project-standard mulberry32 (matches CorticalSignals/NodeLattice). */
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

/** Tiny hand-drawn jitter so points don't read as mechanically scanned (% of model scale). */
const JITTER = 0.012;

type SeedableSampler = MeshSurfaceSampler & { randomFunction: () => number };

/**
 * Sample one or more region-colored source clones into a single set of baked
 * point-field attribute arrays. Pure: deterministic given (sources, count, seed).
 */
export function samplePointField(
  sources: PointFieldSource[],
  totalCount: number,
  seed: number,
): PointFieldData {
  const positions = new Float32Array(totalCount * 3);
  const colors = new Float32Array(totalCount * 3);
  const normals = new Float32Array(totalCount * 3);
  const sizes = new Float32Array(totalCount);
  const phases = new Float32Array(totalCount);
  const speeds = new Float32Array(totalCount);
  const scatter = new Float32Array(totalCount * 3);
  const births = new Float32Array(totalCount);
  const bands = new Float32Array(totalCount);

  const random = createSeededRandom(seed);
  const position = new THREE.Vector3();
  const normal = new THREE.Vector3();
  const color = new THREE.Color();
  const dir = new THREE.Vector3();
  const normalMatrix = new THREE.Matrix3();

  const triangleCount = (mesh: THREE.Mesh) => {
    const index = mesh.geometry.getIndex();
    return (index ? index.count : mesh.geometry.getAttribute('position').count) / 3;
  };

  let writeIndex = 0;
  const shareTotal = sources.reduce((s, src) => s + src.share, 0) || 1;

  sources.forEach((src, srcIndex) => {
    src.object.updateMatrixWorld(true);
    const isLastSource = srcIndex === sources.length - 1;
    // budget for this source (last source absorbs rounding so the array fills)
    const srcTarget = isLastSource
      ? totalCount
      : writeIndex + Math.round((totalCount * src.share) / shareTotal);

    const seen = new Set<THREE.BufferGeometry>();
    const meshes: THREE.Mesh[] = [];
    src.object.traverse((object) => {
      if (!(object instanceof THREE.Mesh)) return;
      if (seen.has(object.geometry)) return;
      seen.add(object.geometry);
      meshes.push(object);
    });
    if (meshes.length === 0) return;

    const triTotal = meshes.reduce((sum, m) => sum + triangleCount(m), 0) || 1;
    const axisRange = src.axisMax - src.axisMin || 1;

    let triSeen = 0;
    const srcStart = writeIndex;
    meshes.forEach((mesh, meshIndex) => {
      triSeen += triangleCount(mesh);
      const meshTarget = meshIndex === meshes.length - 1
        ? srcTarget
        : Math.min(srcTarget, srcStart + Math.round((srcTarget - srcStart) * (triSeen / triTotal)));
      const target = meshTarget;

      const hasColor = !!mesh.geometry.getAttribute('color');
      const sampler = new MeshSurfaceSampler(mesh) as SeedableSampler;
      sampler.randomFunction = random;
      sampler.build();
      normalMatrix.getNormalMatrix(mesh.matrixWorld);

      for (; writeIndex < target && writeIndex < totalCount; writeIndex++) {
        sampler.sample(position, normal, hasColor ? color : undefined);
        position.applyMatrix4(mesh.matrixWorld);
        normal.applyMatrix3(normalMatrix).normalize();

        // hand-drawn jitter
        position.x += (random() - 0.5) * JITTER;
        position.y += (random() - 0.5) * JITTER;
        position.z += (random() - 0.5) * JITTER;

        positions[writeIndex * 3] = position.x;
        positions[writeIndex * 3 + 1] = position.y;
        positions[writeIndex * 3 + 2] = position.z;

        colors[writeIndex * 3] = hasColor ? color.r : 0.6;
        colors[writeIndex * 3 + 1] = hasColor ? color.g : 0.5;
        colors[writeIndex * 3 + 2] = hasColor ? color.b : 0.95;

        normals[writeIndex * 3] = normal.x;
        normals[writeIndex * 3 + 1] = normal.y;
        normals[writeIndex * 3 + 2] = normal.z;

        sizes[writeIndex] = 0.6 + random() * 0.8;
        phases[writeIndex] = random() * TAU;
        speeds[writeIndex] = 0.6 + random() * 0.8;
        births[writeIndex] = random();

        // random unit scatter dir
        dir.set(random() * 2 - 1, random() * 2 - 1, random() * 2 - 1);
        if (dir.lengthSq() < 1e-6) dir.set(0, 1, 0);
        dir.normalize();
        scatter[writeIndex * 3] = dir.x;
        scatter[writeIndex * 3 + 1] = dir.y;
        scatter[writeIndex * 3 + 2] = dir.z;

        // body-axis band: 0 at axisMin → 1 at axisMax, clamped
        bands[writeIndex] = THREE.MathUtils.clamp((position.y - src.axisMin) / axisRange, 0, 1);
      }
    });
  });

  return { positions, colors, normals, sizes, phases, speeds, scatter, births, bands, count: totalCount };
}
