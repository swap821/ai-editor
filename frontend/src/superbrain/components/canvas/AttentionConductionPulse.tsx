import { useFrame } from '@react-three/fiber';
import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { deriveAttentionConductionPath, type AttentionConductionPath } from '@/lib/attentionConduction';
import type { AttentionTransfer, MaterializedTabRecord } from '@/lib/tabStore';

function clamp01(value: number): number {
  return THREE.MathUtils.clamp(value, 0, 1);
}

function nowMs(): number {
  return typeof performance !== 'undefined' && typeof performance.now === 'function' ? performance.now() : Date.now();
}

function AttentionConductionPulseMesh({
  path,
  reducedMotion,
}: {
  path: AttentionConductionPath;
  reducedMotion: boolean;
}) {
  const tubeMaterialRef = useRef<THREE.MeshBasicMaterial>(null);
  const beadMaterialRef = useRef<THREE.MeshBasicMaterial>(null);
  const haloMaterialRef = useRef<THREE.MeshBasicMaterial>(null);
  const beadRef = useRef<THREE.Mesh>(null);
  const haloRef = useRef<THREE.Mesh>(null);

  const curve = useMemo(
    () =>
      new THREE.CatmullRomCurve3([
        new THREE.Vector3(...path.start),
        new THREE.Vector3(...path.midA),
        new THREE.Vector3(...path.midB),
        new THREE.Vector3(...path.end),
      ]),
    [path.end, path.midA, path.midB, path.start],
  );
  const tubeGeometry = useMemo(() => new THREE.TubeGeometry(curve, 42, 0.008, 8, false), [curve]);

  useEffect(() => {
    return () => {
      tubeGeometry.dispose();
    };
  }, [tubeGeometry]);

  useFrame(() => {
    const elapsed = Math.max(0, nowMs() - path.startedAt);
    const progress = reducedMotion ? 1 : clamp01(elapsed / path.durationMs);
    const visible = reducedMotion
      ? elapsed <= 280
        ? 0.22
        : 0
      : elapsed <= path.durationMs
        ? Math.sin(Math.PI * progress)
        : 0;
    const point = curve.getPointAt(progress);

    if (beadRef.current) {
      beadRef.current.position.copy(point);
      beadRef.current.scale.setScalar(0.55 + visible * 1.35);
    }
    if (haloRef.current) {
      haloRef.current.position.copy(point);
      haloRef.current.scale.setScalar(0.9 + visible * 2.1);
    }
    if (tubeMaterialRef.current) {
      tubeMaterialRef.current.opacity = visible * 0.42;
    }
    if (beadMaterialRef.current) {
      beadMaterialRef.current.opacity = visible * 0.95;
    }
    if (haloMaterialRef.current) {
      haloMaterialRef.current.opacity = visible * 0.22;
    }
  });

  return (
    <group>
      <mesh geometry={tubeGeometry} renderOrder={16} frustumCulled={false}>
        <meshBasicMaterial
          ref={tubeMaterialRef}
          color="#83f6ff"
          transparent
          opacity={0}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      <mesh ref={haloRef} renderOrder={17} frustumCulled={false}>
        <sphereGeometry args={[0.038, 18, 14]} />
        <meshBasicMaterial
          ref={haloMaterialRef}
          color="#77edff"
          transparent
          opacity={0}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      <mesh ref={beadRef} renderOrder={18} frustumCulled={false}>
        <sphereGeometry args={[0.021, 18, 14]} />
        <meshBasicMaterial
          ref={beadMaterialRef}
          color="#ffd89b"
          transparent
          opacity={0}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}

export default function AttentionConductionPulse({
  tabs,
  attention,
  reducedMotion,
}: {
  tabs: readonly MaterializedTabRecord[];
  attention: AttentionTransfer | null;
  reducedMotion: boolean;
}) {
  const path = deriveAttentionConductionPath(tabs, attention);
  if (!path) return null;
  return <AttentionConductionPulseMesh key={`${path.fromId}-${path.toId}-${path.startedAt}`} path={path} reducedMotion={reducedMotion} />;
}
