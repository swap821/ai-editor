'use client';

import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { MeshSurfaceSampler } from 'three/examples/jsm/math/MeshSurfaceSampler.js';
import type { CognitionUniforms } from './SuperbrainScene';

/* -------------------------------------------------------------------------- */
/*  Synaptic fireflies — ~320 surface-sampled motes that blink like synapses   */
/*  and fire preferentially where a thought-wave passes. Occlusion is the      */
/*  volume cue: depthTest ON, so motes vanish behind the cortex.               */
/* -------------------------------------------------------------------------- */

const TAU = Math.PI * 2;
const FIREFLY_COUNT = 320;
/** Lift off the cortex by ~0.8% of the local brain radius (≈0.5). */
const NORMAL_LIFT = 0.004;

/* -------------------------------------------------------------------------- */
/*  Shared thought-wave GLSL                                                   */
/*                                                                             */
/*  Consumed by the brain cortex shader (SuperbrainScene) AND the firefly      */
/*  vertex shader, so a wavefront lights the surface and biases the synapses   */
/*  with the SAME uniforms (uWaveOrigins / uWaveTimes, fed by the wave         */
/*  scheduler in SuperbrainScene).                                             */
/* -------------------------------------------------------------------------- */

export const THOUGHT_WAVE_GLSL = /* glsl */ `
  uniform vec3 uWaveOrigins[3];
  uniform float uWaveTimes[3];

  // Expanding spherical wavefront in brain-group-local space. The 3.02 factor
  // converts local distance into the ~world-scale units the 1.4 u/s front
  // speed and 0.8/s decay were tuned for (BRAIN_SCALE). All terms are clamped
  // so dormant slots (startTime << 0) can never produce inf * 0 = NaN.
  float thoughtWave(vec3 p, float t, float sharpness) {
    float w = 0.0;
    for (int i = 0; i < 3; i++) {
      float age = t - uWaveTimes[i];
      float live = step(0.0, age) * (1.0 - smoothstep(5.0, 6.0, age));
      float a = clamp(age, 0.0, 6.0);
      float d = distance(p, uWaveOrigins[i]) * 3.02;
      float front = abs(d - a * 1.4) * sharpness;
      w += live * exp(-front * front) * exp(-a * 0.8);
    }
    return w;
  }
`;

/* -------------------------------------------------------------------------- */
/*  Seeded PRNG (same implementation used across the project)                  */
/* -------------------------------------------------------------------------- */

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

/* -------------------------------------------------------------------------- */
/*  Shaders                                                                    */
/* -------------------------------------------------------------------------- */

const FIREFLY_VERTEX_SHADER = /* glsl */ `
  ${THOUGHT_WAVE_GLSL}

  uniform float uTime;
  uniform float uActivity;
  uniform float uPixelRatio;

  attribute vec3 aColor;
  attribute float aPhase;
  attribute float aSpeed;
  attribute float aSize;

  varying vec3 vColor;
  varying float vAlpha;

  void main() {
    // Sharp synapse spike, not a lava lamp: pow-8 narrows the sine to a blink.
    float flash = pow(0.5 + 0.5 * sin(uTime * aSpeed * 4.0 + aPhase), 8.0);

    // Sentience bias: synapses fire WHERE the thought-wave passes. The
    // proximity lobe is wider (sharpness 3) than the cortex's tight front.
    float prox = clamp(thoughtWave(position, uTime, 3.0) * 1.6, 0.0, 1.0);
    flash *= 0.3 + 0.7 * prox;
    flash *= 0.7 + uActivity * 0.5;

    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    // Large glowing nodes
    gl_PointSize = max(
      aSize * flash * 120.0 * uPixelRatio / max(2.0, -mvPosition.z),
      12.0 * uPixelRatio
    );
    gl_Position = projectionMatrix * mvPosition;

    vColor = aColor;
    vAlpha = flash;
  }
`;

const FIREFLY_FRAGMENT_SHADER = /* glsl */ `
  varying vec3 vColor;
  varying float vAlpha;

  void main() {
    float dist = length(gl_PointCoord - 0.5);
    if (dist > 0.5) discard;
    
    // Soft glowing edge
    float glow = 1.0 - smoothstep(0.0, 0.5, dist);
    // Bright hot core
    float core = 1.0 - smoothstep(0.0, 0.15, dist);
    
    vec3 finalColor = mix(vColor, vec3(1.0), core * 0.6);
    gl_FragColor = vec4(finalColor, vAlpha * glow);
  }
`;

/* -------------------------------------------------------------------------- */
/*  Component                                                                  */
/* -------------------------------------------------------------------------- */

/** The d.ts for MeshSurfaceSampler lags the runtime: expose the seedable bits. */
type SeedableSampler = MeshSurfaceSampler & { randomFunction: () => number };

export default function CorticalSignals({
  activity,
  source,
  uniforms,
  count = FIREFLY_COUNT,
}: {
  activity: number;
  /** Processed brain clone (smooth normals + baked region vertex colors). */
  source: THREE.Object3D;
  uniforms: CognitionUniforms;
  /** Firefly budget — governed by the quality tier. */
  count?: number;
}) {
  const materialRef = useRef<THREE.ShaderMaterial>(null);

  const fireflyGeometry = useMemo(() => {
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
  }, [source, count]);

  // Wave + time uniforms are the SHARED leaf objects from SuperbrainScene —
  // one CPU write per frame drives the cortex, shells and fireflies together.
  const fireflyUniforms = useMemo(
    () => ({
      uTime: uniforms.uTime,
      uWaveOrigins: uniforms.uWaveOrigins,
      uWaveTimes: uniforms.uWaveTimes,
      uActivity: { value: 0 },
      uPixelRatio: { value: 1 },
    }),
    [uniforms],
  );

  useEffect(() => {
    return () => {
      fireflyGeometry.dispose();
    };
  }, [fireflyGeometry]);

  useFrame((state, delta) => {
    const material = materialRef.current;
    if (!material) return;
    material.uniforms.uPixelRatio.value = state.viewport.dpr;
    material.uniforms.uActivity.value = THREE.MathUtils.damp(
      material.uniforms.uActivity.value,
      THREE.MathUtils.clamp(activity, 0, 1),
      4,
      delta,
    );
  });

  return (
    <points geometry={fireflyGeometry} frustumCulled={false} renderOrder={3}>
      <shaderMaterial
        ref={materialRef}
        vertexShader={FIREFLY_VERTEX_SHADER}
        fragmentShader={FIREFLY_FRAGMENT_SHADER}
        uniforms={fireflyUniforms}
        transparent
        depthWrite={false}
        depthTest
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
    </points>
  );
}
