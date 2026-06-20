'use client';

import { useEffect, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { samplePointField, type PointFieldSource } from '@/lib/pointFieldSampler';
import { createPointFieldMaterial } from '@/lib/pointFieldMaterial';
import type { CognitionUniforms } from './SuperbrainScene';

/** The being's flesh as a single additive point cloud (poster substrate). */
export default function BrainPointField({
  source,
  uniforms,
  count = 60000,
}: {
  /** processed brain clone (region-colored), same prop CorticalSignals takes. */
  source: THREE.Object3D;
  uniforms: CognitionUniforms;
  count?: number;
}) {
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const gl = useThree((s) => s.gl);

  const geometry = useMemo(() => {
    // brain.glb occupies group-local y ≈ -0.222 .. +0.633; band normalizes over it.
    const sources: PointFieldSource[] = [{ object: source, share: 1, axisMin: -0.6, axisMax: 0.7 }];
    const d = samplePointField(sources, count, 0x50494e54);
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(d.positions, 3));
    g.setAttribute('aColor', new THREE.BufferAttribute(d.colors, 3));
    g.setAttribute('aNormal', new THREE.BufferAttribute(d.normals, 3));
    g.setAttribute('aSize', new THREE.BufferAttribute(d.sizes, 1));
    g.setAttribute('aPhase', new THREE.BufferAttribute(d.phases, 1));
    g.setAttribute('aSpeed', new THREE.BufferAttribute(d.speeds, 1));
    g.setAttribute('aScatter', new THREE.BufferAttribute(d.scatter, 3));
    g.setAttribute('aBirth', new THREE.BufferAttribute(d.births, 1));
    g.setAttribute('aBand', new THREE.BufferAttribute(d.bands, 1));
    return g;
  }, [source, count]);

  const material = useMemo(
    () => createPointFieldMaterial({
      uTime: uniforms.uTime,
      uPostureColor: uniforms.uPosture,
      uPostureTint: uniforms.uPostureTint,
    }),
    [uniforms],
  );

  // Keep the on-screen point size DPR-correct: write the renderer's pixel ratio
  // into uPixelRatio (the vertex multiplies by it). Re-applied on resize/DPR change.
  const setDpr = () => {
    material.uniforms.uPixelRatio.value = gl.getPixelRatio();
  };
  useEffect(() => {
    setDpr();
    window.addEventListener('resize', setDpr);
    return () => {
      window.removeEventListener('resize', setDpr);
      geometry.dispose();
      material.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometry, material, gl]);

  // Honor reduced-motion: freeze the breathe/flow gains (the lit field stays
  // fully visible — we never blank it; large translations are the trigger).
  const reduce = useMemo(
    () =>
      typeof window !== 'undefined' &&
      !!window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  );

  // Dev-only live tuning dials: e.g. window.__POINTFIELD.uSize = 4,
  // window.__POINTFIELD.uGlowMul = 1.4, window.__POINTFIELD.uAttenK = 0.1.
  useEffect(() => {
    if (typeof window === 'undefined' || process.env.NODE_ENV === 'production') return;
    (window as unknown as { __POINTFIELD?: unknown }).__POINTFIELD = new Proxy(
      {},
      {
        get: (_t, key: string) => material.uniforms[key]?.value,
        set: (_t, key: string, value: number) => {
          if (material.uniforms[key]) material.uniforms[key].value = value;
          return true;
        },
      },
    );
  }, [material]);

  useFrame(() => {
    // uTime is the shared leaf (advanced by the scene); keep uPixelRatio fresh
    // and drive the breathe/flow gains. All motion runs in the vertex shader.
    setDpr();
    const u = material.uniforms;
    u.uGrow.value = reduce ? 0 : 1;
    u.uFlowSpeed.value = 0.05 + (uniforms.uFlow.value ?? 0.16) * 0.18;
  });

  return (
    <points geometry={geometry} frustumCulled={false} renderOrder={3}>
      <primitive object={material} ref={materialRef} attach="material" />
    </points>
  );
}
