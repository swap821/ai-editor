import * as THREE from 'three';
import { MeshSurfaceSampler } from 'three/examples/jsm/math/MeshSurfaceSampler.js';

const TAU = Math.PI * 2;
const NORMAL_LIFT = 0.004;

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

/** The d.ts for MeshSurfaceSampler lags the runtime: expose the seedable bits. */
type SeedableSampler = MeshSurfaceSampler & { randomFunction: () => number };

export function buildFireflyGeometry(source: THREE.Object3D, count: number): THREE.BufferGeometry {
  // The clone root is never added to the scene, so matrixWorld is
  // brain-group-local space — the same space as the wave origins.
  source.updateMatrixWorld(true);

  // Unique sampling surfaces (clone(true) shares geometry between layers).
  const seen = new Set<THREE.BufferGeometry>();
  const meshes: THREE.Mesh[] = [];
  source.traverse((object) => {
    if (!(object instanceof THREE.Mesh)) return;
    if (seen.has(object.geometry)) return;
    seen.add(object.geometry);
    meshes.push(object);
  });

  const random = createSeededRandom(0x53594e41);
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const phases = new Float32Array(count);
  const speeds = new Float32Array(count);
  const sizes = new Float32Array(count);

  const position = new THREE.Vector3();
  const normal = new THREE.Vector3();
  const color = new THREE.Color();
  const normalMatrix = new THREE.Matrix3();

  const triangleCount = (mesh: THREE.Mesh) => {
    const index = mesh.geometry.getIndex();
    return (index ? index.count : mesh.geometry.getAttribute('position').count) / 3;
  };
  const triangleTotal = meshes.reduce((sum, mesh) => sum + triangleCount(mesh), 0);

  let trianglesSeen = 0;
  let writeIndex = 0;
  meshes.forEach((mesh, meshIndex) => {
    trianglesSeen += triangleCount(mesh);
    const targetCount = meshIndex === meshes.length - 1
      ? count
      : Math.round(count * (trianglesSeen / Math.max(triangleTotal, 1)));

    // Deterministic placement: the sampler draws from the seeded PRNG.
    const sampler = new MeshSurfaceSampler(mesh) as SeedableSampler;
    sampler.randomFunction = random;
    sampler.build();
    normalMatrix.getNormalMatrix(mesh.matrixWorld);

    for (; writeIndex < targetCount; writeIndex++) {
      // Position + smooth normal + interpolated region vertex color.
      sampler.sample(position, normal, color);
      position.applyMatrix4(mesh.matrixWorld);
      normal.applyMatrix3(normalMatrix).normalize();
      position.addScaledVector(normal, NORMAL_LIFT);

      positions[writeIndex * 3] = position.x;
      positions[writeIndex * 3 + 1] = position.y;
      positions[writeIndex * 3 + 2] = position.z;
      colors[writeIndex * 3] = color.r;
      colors[writeIndex * 3 + 1] = color.g;
      colors[writeIndex * 3 + 2] = color.b;
      phases[writeIndex] = random() * TAU;
      speeds[writeIndex] = 0.55 + random() * 1.0;
      sizes[writeIndex] = 0.7 + random() * 0.6;
    }
  });

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('aColor', new THREE.BufferAttribute(colors, 3));
  geometry.setAttribute('aPhase', new THREE.BufferAttribute(phases, 1));
  geometry.setAttribute('aSpeed', new THREE.BufferAttribute(speeds, 1));
  geometry.setAttribute('aSize', new THREE.BufferAttribute(sizes, 1));
  return geometry;
}
