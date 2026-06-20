'use client';

import { useEffect, useRef, useState } from 'react';
import { Text } from '@react-three/drei';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { subscribeCognition } from '@/lib/cognitionBus';
import {
  getActiveBrain,
  setActiveBrain,
  subscribeActiveBrain,
  formatActiveBrainLine,
} from '@/lib/activeBrain';

// View-space anchor: child of the camera, so this is metres in front of the lens.
// Tuned for the points-mode fov=26 camera; operator fine-tunes via window.__GAGOS.
const ANCHOR = { x: -1.92, y: 1.12, z: -4 };

const NAME_COLOR = new THREE.Color('#cdbbff'); // spectral violet, lifted for legibility
const META_COLOR = new THREE.Color('#7fe9ff'); // spectral cyan
const DOT_COLOR = new THREE.Color('#9b6bff');

interface IdentityReadoutProps {
  name?: string;
  supervised?: boolean;
}

export default function IdentityReadout({ name = 'GAGOS', supervised = true }: IdentityReadoutProps) {
  const groupRef = useRef<THREE.Group>(null);
  const [modelLine, setModelLine] = useState(() => formatActiveBrainLine(getActiveBrain()));
  const speakingRef = useRef(0); // 0..1, decays; dims the cluster while speaking

  useEffect(() => subscribeActiveBrain(() => setModelLine(formatActiveBrainLine(getActiveBrain()))), []);

  useEffect(
    () =>
      subscribeCognition((event) => {
        if (event.type === 'route' && event.data) {
          setActiveBrain({
            provider: event.data.provider as string | undefined,
            model: event.data.model as string | undefined,
            privacy: event.data.privacy as string | undefined,
          });
        }
        if (event.type === 'voice-speaking') speakingRef.current = 1;
      }),
    [],
  );

  useFrame((_s, delta) => {
    speakingRef.current = Math.max(0, speakingRef.current - delta * 0.6);
    const dial = (window as unknown as { __GAGOS?: { x?: number; y?: number; z?: number; horizon?: number } }).__GAGOS;
    if (dial && groupRef.current) {
      groupRef.current.position.set(dial.x ?? ANCHOR.x, dial.y ?? ANCHOR.y, dial.z ?? ANCHOR.z);
    }
    if (groupRef.current) {
      // dim ~35% while speaking so it never competes with the reply slab.
      const dim = 1 - speakingRef.current * 0.35;
      groupRef.current.traverse((o: THREE.Object3D) => {
        const mesh = o as THREE.Mesh;
        if (mesh.material && !Array.isArray(mesh.material) && 'opacity' in mesh.material) {
          (mesh.material as THREE.Material & { opacity: number }).opacity = dim;
        }
      });
    }
  });

  return (
    <group ref={groupRef} position={[ANCHOR.x, ANCHOR.y, ANCHOR.z]}>
      <Text fontSize={0.2} anchorX="left" anchorY="top" color={NAME_COLOR.getStyle()}
            outlineWidth={0.006} outlineColor="#05010f" letterSpacing={0.18}
            material-toneMapped={false} material-transparent>
        {name}
      </Text>
      <group position={[0, -0.28, 0]}>
        <mesh position={[0.05, 0, 0]}>
          <circleGeometry args={[0.028, 16]} />
          <meshBasicMaterial color={DOT_COLOR} toneMapped={false} transparent />
        </mesh>
        <Text position={[0.14, 0.02, 0]} fontSize={0.085} anchorX="left" anchorY="top"
              color={META_COLOR.getStyle()} outlineWidth={0.004} outlineColor="#031016"
              material-toneMapped={false} material-transparent>
          {modelLine}
        </Text>
      </group>
      {supervised ? (
        <Text position={[0, -0.46, 0]} fontSize={0.07} anchorX="left" anchorY="top"
              color="#8aa0b8" outlineWidth={0.003} outlineColor="#02080d"
              letterSpacing={0.08} material-toneMapped={false} material-transparent>
          supervised
        </Text>
      ) : null}
    </group>
  );
}
