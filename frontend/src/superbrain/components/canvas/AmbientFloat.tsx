import { useRef, type ReactNode } from 'react';
import { useFrame } from '@react-three/fiber';
import type { Group } from 'three';

/** The body's small ambient bob, with no paused wall time to catch up on.
 * Same amplitudes as the former Drei Float's default range; a stable starting
 * phase replaces its random offset. Functional state updates remain outside
 * this wrapper and the default frame priority does not take over rendering.
 */
export default function AmbientFloat({ children, paused, speed, rotationIntensity, floatIntensity }: {
  children: ReactNode;
  paused: boolean;
  speed: number;
  rotationIntensity: number;
  floatIntensity: number;
}) {
  const group = useRef<Group>(null);
  const phase = useRef(0);
  useFrame((_, delta) => {
    if (paused || speed === 0 || !group.current) return;
    phase.current += delta * speed / 4;
    const sin = Math.sin(phase.current);
    group.current.rotation.set(
      Math.cos(phase.current) / 8 * rotationIntensity,
      sin / 8 * rotationIntensity,
      sin / 20 * rotationIntensity,
    );
    group.current.position.y = sin / 10 * floatIntensity;
    group.current.updateMatrix();
  });
  return <group><group ref={group} matrixAutoUpdate={false}>{children}</group></group>;
}
