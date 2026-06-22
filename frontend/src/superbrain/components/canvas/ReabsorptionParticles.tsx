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

export default function ReabsorptionParticles({
  origin,
  target,
  startedAt,
  durationMs = 1300,
  color = '#5ef0b0',
}: {
  /** where the slab feeds the spine (the tab's fused vertebra anchor). */
  origin: [number, number, number];
  /** the brain the motes return into (groupRef-local). */
  target: [number, number, number];
  startedAt: number;
  durationMs?: number;
  color?: string;
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

  useFrame(() => {
    const pts = pointsRef.current;
    if (!pts) return;
    const t = clamp01((performance.now() - startedAt) / durationMs);
    const pos = geometry.attributes.position.array as Float32Array;
    for (let i = 0; i < COUNT; i++) {
      const birth = seeds[i * 4 + 3];
      const lt = clamp01((t - birth) / (1 - birth));
      const e = 1 - Math.pow(1 - lt, 2); // ease-out rise
      // start: scattered around the vertebra (the dissolving slab feeds here);
      // a slight outward puff before being drawn up the spine into the brain.
      const sx = origin[0] + seeds[i * 4] * 0.34;
      const sy = origin[1] + seeds[i * 4 + 1] * 0.14;
      const sz = origin[2] + seeds[i * 4 + 2] * 0.34;
      // gentle sideways converge as they rise (curl toward the spine centerline)
      const conv = 1 - e * 0.6;
      pos[i * 3] = (sx + (target[0] - sx) * e) * (e < 0.001 ? 1 : conv) + target[0] * (1 - conv);
      pos[i * 3 + 1] = sy + (target[1] - sy) * e;
      pos[i * 3 + 2] = (sz + (target[2] - sz) * e) * (e < 0.001 ? 1 : conv) + target[2] * (1 - conv);
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
