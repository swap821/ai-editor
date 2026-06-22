'use client';

// ReabsorptionParticles — poster phase 7 "energy returns up the spine".
// When a work slab is reabsorbing, its substance dissolves into motes that
// stream UP from its vertebra along the spine and back into the brain, then fade
// — "work completes → tab dissolves into particles → energy up the spine → rest".
// Rendered (in MaterializationLayer / groupRef space) per retracting tab; CPU-
// animated (≤80 motes, cheap) so it needs no shader plumbing.

import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

const COUNT = 72;

function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v));
}

function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = clamp01((x - edge0) / (edge1 - edge0));
  return t * t * (3 - 2 * t);
}

export default function ReabsorptionParticles({
  origin,
  target,
  startedAt,
  durationMs = 1300,
  color = '#5ef0b0',
  reducedMotion = false,
}: {
  /** where the slab feeds the spine (the tab's fused vertebra anchor). */
  origin: [number, number, number];
  /** the brain the motes return into (groupRef-local). */
  target: [number, number, number];
  startedAt: number;
  durationMs?: number;
  color?: string;
  /** a11y: skip the up-spine travel (fade dissolve in place — no vestibular sweep). */
  reducedMotion?: boolean;
}) {
  const pointsRef = useRef<THREE.Points>(null);

  // Per-mote scatter (xyz around the origin) + birth stagger.
  const seeds = useMemo(() => {
    const s = new Float32Array(COUNT * 4);
    for (let i = 0; i < COUNT; i++) {
      s[i * 4] = (Math.random() - 0.5) * 2;
      s[i * 4 + 1] = (Math.random() - 0.5) * 2;
      s[i * 4 + 2] = (Math.random() - 0.5) * 2;
      s[i * 4 + 3] = Math.random() * 0.45; // birth 0..0.45
    }
    return s;
  }, []);

  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(COUNT * 3), 3));
    return g;
  }, []);

  // SPINE-CURVE ROUTE (poster phase 7): the motes don't cut a straight diagonal —
  // they puff off the vertebra, converge to the spine centerline, then ride UP it
  // into the brain. A CatmullRom through 4 control points draws that curved route;
  // getPointAt(e) gives an arc-length-even position so the rise reads steady.
  // Depend on the VALUES (not the array refs) so a new [..] literal per render
  // doesn't rebuild the curve every frame.
  const [ox, oy, oz] = origin;
  const [tx, ty, tz] = target;
  const curve = useMemo(
    () =>
      new THREE.CatmullRomCurve3([
        new THREE.Vector3(ox, oy, oz), // the dissolving slab's vertebra
        new THREE.Vector3(tx + (ox - tx) * 0.5, oy + (ty - oy) * 0.18, tz + (oz - tz) * 0.5), // pull toward the spine
        new THREE.Vector3(tx, oy + (ty - oy) * 0.58, tz), // on the spine centerline, risen partway
        new THREE.Vector3(tx, ty, tz), // home into the brain
      ]),
    [ox, oy, oz, tx, ty, tz],
  );

  const scratch = useMemo(() => new THREE.Vector3(), []);

  useFrame(() => {
    const pts = pointsRef.current;
    if (!pts) return;
    const t = clamp01((performance.now() - startedAt) / durationMs);
    const pos = geometry.attributes.position.array as Float32Array;
    for (let i = 0; i < COUNT; i++) {
      const birth = seeds[i * 4 + 3];
      const lt = clamp01((t - birth) / (1 - birth));
      // STAGED BEATS: (1) DISSOLVE — the slab breaks apart, motes puff outward off
      // the vertebra; (2) RISE — they stream up the spine curve into the brain. The
      // beats overlap slightly so it reads as one continuous "energy returns" gesture.
      const dissolve = smoothstep(0, 0.32, lt);
      const rise = reducedMotion ? 0 : smoothstep(0.24, 1, lt);
      const e = 1 - Math.pow(1 - rise, 2); // ease-out along the curve
      curve.getPointAt(clamp01(e), scratch);
      // Scatter puffs out during the dissolve, then shrinks to nothing as the motes
      // converge onto the spine and rise — so the cloud gathers into the cord.
      const scatter = (0.12 + 0.26 * dissolve) * (1 - rise * 0.88);
      pos[i * 3] = scratch.x + seeds[i * 4] * scatter;
      pos[i * 3 + 1] = scratch.y + seeds[i * 4 + 1] * scatter * 0.5;
      pos[i * 3 + 2] = scratch.z + seeds[i * 4 + 2] * scatter;
    }
    geometry.attributes.position.needsUpdate = true;
    const mat = pts.material as THREE.PointsMaterial;
    // bright as they leave, fade as they arrive
    mat.opacity = (1 - Math.pow(t, 2)) * 0.95;
  });

  return (
    <points ref={pointsRef} geometry={geometry} renderOrder={8} frustumCulled={false}>
      <pointsMaterial
        size={0.05}
        color={color}
        transparent
        opacity={0.95}
        sizeAttenuation
        blending={THREE.AdditiveBlending}
        depthWrite={false}
      />
    </points>
  );
}
