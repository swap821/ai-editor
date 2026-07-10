import { Text } from '@react-three/drei';
import { useState } from 'react';
import * as THREE from 'three';

/**
 * The orbiting APPROVE/REJECT sphere shown on an approval surface.
 * Extracted from MaterializedTab.tsx (structure audit, 2026-07-10) — fully
 * self-contained, no dependency on the main file's shared helpers.
 */
export function ApprovalActionButton({
  label,
  position,
  fill,
  outline,
  disabled,
  onActivate,
}: {
  label: string;
  position: [number, number, number];
  fill: string;
  outline: string;
  disabled: boolean;
  onActivate: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <group
      position={position}
      scale={hovered && !disabled ? 1.04 : 1}
      onPointerOver={(event) => {
        event.stopPropagation();
        if (!disabled) setHovered(true);
      }}
      onPointerOut={(event) => {
        event.stopPropagation();
        setHovered(false);
      }}
      onClick={(event) => {
        event.stopPropagation();
        if (!disabled) onActivate();
      }}
    >
      <mesh renderOrder={11}>
        <sphereGeometry args={[0.082, 22, 16]} />
        <meshStandardMaterial
          color={fill}
          emissive={fill}
          emissiveIntensity={disabled ? 0.05 : hovered ? 0.85 : 0.46}
          roughness={0.24}
          metalness={0.06}
          transparent
          opacity={disabled ? 0.24 : hovered ? 0.98 : 0.86}
        />
      </mesh>
      <mesh rotation={[Math.PI / 2, 0, 0]} renderOrder={12}>
        <torusGeometry args={[0.122, 0.006, 10, 40]} />
        <meshBasicMaterial
          color={outline}
          transparent
          opacity={disabled ? 0.14 : hovered ? 0.7 : 0.42}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      <Text
        position={[0, 0, 0.1]}
        color="#f9fbff"
        fontSize={0.028}
        maxWidth={0.2}
        anchorX="center"
        anchorY="middle"
        outlineWidth={0.003}
        outlineColor="#04070c"
        renderOrder={13}
      >
        {label}
      </Text>
    </group>
  );
}
