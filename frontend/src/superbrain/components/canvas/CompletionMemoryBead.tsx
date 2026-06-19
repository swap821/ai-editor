import { useFrame } from '@react-three/fiber';
import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import type { CompletionReflexSnapshot } from '@/lib/completionReflex';

const TRAIL_COUNT = 3;

function clamp01(value: number): number {
  return THREE.MathUtils.clamp(value, 0, 1);
}

export default function CompletionMemoryBead({
  reflex,
  reducedMotion,
}: {
  reflex: CompletionReflexSnapshot;
  reducedMotion: boolean;
}) {
  const beadRef = useRef<THREE.Mesh>(null);
  const haloRef = useRef<THREE.Mesh>(null);
  const pathRef = useRef<THREE.Mesh>(null);
  const trailRefs = useRef<THREE.Mesh[]>([]);
  const color = useMemo(() => new THREE.Color(reflex.tint), [reflex.tint]);

  const curve = useMemo(() => {
    if (!reflex.targetOriginLocal || !reflex.targetTargetLocal) return null;

    const source = new THREE.Vector3(...reflex.targetTargetLocal);
    const sink = new THREE.Vector3(...reflex.targetOriginLocal);
    const delta = sink.clone().sub(source);
    const midA = source.clone().add(delta.clone().multiplyScalar(0.34)).add(new THREE.Vector3(-0.03, 0.035, 0.05));
    const midB = source.clone().add(delta.clone().multiplyScalar(0.7)).add(new THREE.Vector3(0.02, 0.018, 0.035));
    return new THREE.CatmullRomCurve3([source, midA, midB, sink]);
  }, [reflex.targetOriginLocal, reflex.targetTargetLocal]);

  const pathGeometry = useMemo(() => {
    if (!curve) return null;
    return new THREE.TubeGeometry(curve, 36, 0.0032, 6, false);
  }, [curve]);

  useEffect(() => {
    return () => {
      pathGeometry?.dispose();
    };
  }, [pathGeometry]);

  useFrame((state) => {
    if (!curve) return;

    const pulse = reducedMotion ? 0.82 : 0.72 + 0.28 * (0.5 + 0.5 * Math.sin(state.clock.elapsedTime * 5.4));
    const progress = reducedMotion ? Math.max(reflex.beadProgress, 0.96) : reflex.beadProgress;
    const pathT = clamp01(0.04 + progress * 0.9);
    const opacity = clamp01(reflex.memoryOpacity * pulse);

    if (beadRef.current) {
      beadRef.current.position.copy(curve.getPointAt(pathT));
      beadRef.current.scale.setScalar(0.72 + reflex.intensity * 0.55 + opacity * 0.34);
      const mat = beadRef.current.material as THREE.MeshBasicMaterial;
      mat.color.copy(color);
      mat.opacity = Math.min(0.98, opacity);
    }

    if (haloRef.current) {
      haloRef.current.position.copy(curve.getPointAt(pathT));
      haloRef.current.rotation.z = state.clock.elapsedTime * 0.35;
      haloRef.current.scale.setScalar(0.92 + reflex.intensity * 0.85);
      const mat = haloRef.current.material as THREE.MeshBasicMaterial;
      mat.color.copy(color);
      mat.opacity = Math.min(0.42, opacity * 0.36);
    }

    if (pathRef.current) {
      const geometry = pathRef.current.geometry;
      const drawCount = geometry.getIndex()?.count ?? geometry.getAttribute('position').count;
      geometry.setDrawRange(0, Math.max(2, Math.floor(drawCount * Math.max(pathT, 0.08))));
      const mat = pathRef.current.material as THREE.MeshBasicMaterial;
      mat.color.copy(color);
      mat.opacity = Math.min(0.22, opacity * 0.2);
    }

    trailRefs.current.forEach((trail, index) => {
      if (!trail) return;
      const trailT = clamp01(pathT - 0.065 * (index + 1));
      trail.position.copy(curve.getPointAt(trailT));
      trail.scale.setScalar(0.3 + Math.max(0, opacity - index * 0.16) * 0.42);
      const mat = trail.material as THREE.MeshBasicMaterial;
      mat.color.copy(color);
      mat.opacity = Math.min(0.46, Math.max(0, opacity - index * 0.14));
    });
  });

  if (reflex.state === 'idle' || reflex.state === 'held' || !pathGeometry || !curve) return null;

  return (
    <group renderOrder={14}>
      <mesh ref={pathRef} geometry={pathGeometry} frustumCulled={false} renderOrder={13}>
        <meshBasicMaterial
          color={color}
          transparent
          opacity={0}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      {Array.from({ length: TRAIL_COUNT }, (_, index) => (
        <mesh
          key={`completion-memory-trail-${reflex.sequence}-${index}`}
          ref={(mesh) => {
            if (mesh) trailRefs.current[index] = mesh;
          }}
          renderOrder={14}
        >
          <sphereGeometry args={[0.017, 12, 10]} />
          <meshBasicMaterial
            color={color}
            transparent
            opacity={0}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      ))}
      <mesh ref={beadRef} renderOrder={15}>
        <sphereGeometry args={[0.026, 18, 14]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={0}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      <mesh ref={haloRef} renderOrder={14}>
        <torusGeometry args={[0.038, 0.0035, 6, 28]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={0}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          side={THREE.DoubleSide}
        />
      </mesh>
    </group>
  );
}
