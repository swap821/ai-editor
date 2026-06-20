'use client';

import { useEffect, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { samplePointField, type PointFieldSource, type PointFieldData } from '@/lib/pointFieldSampler';
import { buildSpinePoints, BODY_AXIS_MIN, BODY_AXIS_MAX } from '@/lib/spinePointField';
import { createPointFieldMaterial } from '@/lib/pointFieldMaterial';
import { lifecycleTargets } from '@/lib/pointFieldLifecycle';
import { getOrganismPhase } from '@/lib/organismPhaseBus';
import type { CognitionUniforms } from './SuperbrainScene';

/**
 * The being's flesh as an additive point cloud (poster substrate). Two kinds,
 * each mounted in its OWN coordinate space:
 *   'brain' — sampled from the GLB clone, mounted INSIDE the brain group (rides
 *             the brain's scale/position/Float bob), region-colored.
 *   'spine' — the cord/vertebrae/roots, authored in SCENE space, mounted inside
 *             the same Float as the brain (so they bob as one body) but NOT inside
 *             the brain's rotating group, or the brain transform would squash it;
 *             colored from the brain's palette so it reads as one continuous body.
 */
export default function BrainPointField({
  source,
  uniforms,
  count = 60000,
  kind = 'brain',
  baseSize = 3,
}: {
  /** processed brain clone (region-colored) — required for kind='brain'. */
  source?: THREE.Object3D;
  uniforms: CognitionUniforms;
  count?: number;
  kind?: 'brain' | 'spine';
  /** base point size in CSS px (the spine reads better a touch larger). */
  baseSize?: number;
}) {
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const gl = useThree((s) => s.gl);

  const geometry = useMemo(() => {
    let data: PointFieldData;
    if (kind === 'spine') {
      // The spine is colored from the brain's own region palette inside the
      // generator (one body — the brain's flesh extruded down the cord).
      data = buildSpinePoints(count, 0x5350494e);
    } else {
      // aBand spans the FULL body axis so the flow band sweeps brain↔roots together.
      data = samplePointField(
        [{ object: source!, share: 1, axisMin: BODY_AXIS_MIN, axisMax: BODY_AXIS_MAX } as PointFieldSource],
        count,
        0x50494e54,
      );
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(data.positions, 3));
    g.setAttribute('aColor', new THREE.BufferAttribute(data.colors, 3));
    g.setAttribute('aNormal', new THREE.BufferAttribute(data.normals, 3));
    g.setAttribute('aSize', new THREE.BufferAttribute(data.sizes, 1));
    g.setAttribute('aPhase', new THREE.BufferAttribute(data.phases, 1));
    g.setAttribute('aSpeed', new THREE.BufferAttribute(data.speeds, 1));
    g.setAttribute('aScatter', new THREE.BufferAttribute(data.scatter, 3));
    g.setAttribute('aBirth', new THREE.BufferAttribute(data.births, 1));
    g.setAttribute('aBand', new THREE.BufferAttribute(data.bands, 1));
    return g;
  }, [source, count, kind]);

  const material = useMemo(
    () => {
      const m = createPointFieldMaterial({
        uTime: uniforms.uTime,
        uPostureColor: uniforms.uPosture,
        uPostureTint: uniforms.uPostureTint,
      });
      m.uniforms.uSize.value = baseSize;
      return m;
    },
    [uniforms, baseSize],
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
    if (kind !== 'brain') return; // one dial owner (the brain material)
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
  }, [material, kind]);

  useFrame((_state, delta) => {
    // uTime is the shared leaf (advanced by the scene); keep uPixelRatio fresh.
    setDpr();
    const u = material.uniforms;
    // Drive breathe / flow / arrival-inrush / reabsorption from the live organism
    // phase (the lifecycle gesture engine). All motion runs in the vertex shader;
    // here we only damp a few scalar uniforms via ref (zero per-point CPU).
    const t = lifecycleTargets(getOrganismPhase());
    if (reduce) {
      // reduced motion: snap to the settled state (no inrush/dissolve translation).
      u.uGrow.value = t.grow;
      u.uArrival.value = t.arrival;
      u.uReabsorb.value = t.reabsorb;
      u.uFlowSpeed.value = 0.05 + t.flow * 0.2;
    } else {
      u.uGrow.value = THREE.MathUtils.damp(u.uGrow.value, t.grow, 2, delta);
      u.uArrival.value = THREE.MathUtils.damp(u.uArrival.value, t.arrival, 1.6, delta);
      u.uReabsorb.value = THREE.MathUtils.damp(u.uReabsorb.value, t.reabsorb, 1.6, delta);
      u.uFlowSpeed.value = THREE.MathUtils.damp(u.uFlowSpeed.value, 0.05 + t.flow * 0.2, 3, delta);
    }
  });

  return (
    <points geometry={geometry} frustumCulled={false} renderOrder={3}>
      <primitive object={material} ref={materialRef} attach="material" />
    </points>
  );
}
