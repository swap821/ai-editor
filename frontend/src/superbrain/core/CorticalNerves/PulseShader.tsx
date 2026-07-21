import * as THREE from 'three';
import { shaderMaterial } from '@react-three/drei';
import { extend } from '@react-three/fiber';

export const PulseMaterial = shaderMaterial(
  {
    uTime: 0,
  },
  // vertex shader
  `
    attribute float aActive;
    varying vec3 vColor;
    
    void main() {
      vColor = instanceColor;
      if (aActive < 0.5) {
        vColor *= 0.2; // Dim when inactive
      }
      
      float targetScale = aActive > 0.5 ? 1.5 : 0.5;
      if (aActive > 0.5) {
         // Pulse scale animation matching the original CPU logic
         float pulse = 1.0 + sin(uTime * 6.0 + float(gl_InstanceID)) * 0.3;
         targetScale *= pulse;
      }
      
      vec3 pos = position * targetScale;
      // standard instanced mesh position calculation
      vec4 mvPosition = instanceMatrix * vec4(pos, 1.0);
      gl_Position = projectionMatrix * modelViewMatrix * mvPosition;
    }
  `,
  // fragment shader
  `
    varying vec3 vColor;
    void main() {
      gl_FragColor = vec4(vColor, 0.9);
    }
  `
);

extend({ PulseMaterial });

declare module '@react-three/fiber' {
  interface ThreeElements {
    pulseMaterial: any;
  }
}
