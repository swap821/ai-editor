import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { CognitionUniforms } from '../../components/canvas/SuperbrainScene.LEGACY';
import { buildFireflyGeometry } from './ConductionPaths';
import './RoutingShader'; // ensures RoutingMaterial is registered

const FIREFLY_COUNT = 320;

export default function SignalParticles({
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
  const materialRef = useRef<any>(null);

  const fireflyGeometry = useMemo(() => {
    return buildFireflyGeometry(source, count);
  }, [source, count]);

  useEffect(() => {
    return () => {
      fireflyGeometry.dispose();
    };
  }, [fireflyGeometry]);

  useFrame((state, delta) => {
    const material = materialRef.current;
    if (!material) return;
    
    // Update simple uniform props
    material.uPixelRatio = state.viewport.dpr;
    material.uTime = uniforms.uTime.value;
    material.uWaveOrigins = uniforms.uWaveOrigins.value;
    material.uWaveTimes = uniforms.uWaveTimes.value;
    material.uPostureColor = uniforms.uPosture.value;
    material.uPostureTint = uniforms.uPostureTint.value;
    
    // Dampen activity
    material.uActivity = THREE.MathUtils.damp(
      material.uActivity,
      THREE.MathUtils.clamp(activity, 0, 1),
      4,
      delta,
    );
  });

  return (
    <points geometry={fireflyGeometry} frustumCulled={false} renderOrder={3}>
      <routingMaterial
        ref={materialRef}
        transparent
        depthWrite={false}
        depthTest
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
    </points>
  );
}
