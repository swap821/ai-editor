'use client';

import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

// A wide, soft vertical-gradient band; additive, faint, far behind the being.
const VERT = /* glsl */ `
  varying vec2 vUv;
  void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
`;
const FRAG = /* glsl */ `
  precision highp float;
  varying vec2 vUv;
  uniform vec3 uColor;
  uniform float uOpacity;
  void main() {
    // brightest at the horizon line (vUv.y ~ 0.5), fading up and down.
    float band = exp(-pow((vUv.y - 0.5) / 0.16, 2.0));
    float sides = smoothstep(0.0, 0.35, vUv.x) * smoothstep(1.0, 0.65, vUv.x);
    float a = band * mix(0.5, 1.0, sides) * uOpacity;
    gl_FragColor = vec4(uColor * a, a);
  }
`;

interface HorizonGlowProps {
  color?: string;
  opacity?: number;
}

export default function HorizonGlow({ color = '#3a1f7a', opacity = 0.16 }: HorizonGlowProps) {
  const matRef = useRef<THREE.ShaderMaterial>(null);
  useFrame(() => {
    const dial = (window as unknown as { __GAGOS?: { x?: number; y?: number; z?: number; horizon?: number } }).__GAGOS;
    if (dial?.horizon !== undefined && matRef.current) {
      matRef.current.uniforms.uOpacity.value = dial.horizon;
    }
  });
  return (
    <mesh position={[0, -3.2, -10]} renderOrder={0} frustumCulled={false}>
      <planeGeometry args={[60, 14, 1, 1]} />
      <shaderMaterial
        ref={matRef}
        vertexShader={VERT}
        fragmentShader={FRAG}
        transparent
        depthWrite={false}
        depthTest={false}
        toneMapped={false}
        blending={THREE.AdditiveBlending}
        uniforms={{
          uColor: { value: new THREE.Color(color) },
          uOpacity: { value: opacity },
        }}
      />
    </mesh>
  );
}
