// frontend/src/superbrain/lib/pointFieldMaterial.ts
import * as THREE from 'three';

export interface PointFieldUniformOverrides {
  uTime?: { value: number };
  uPostureColor?: { value: THREE.Color };
  uPostureTint?: { value: number };
}

const VERTEX = /* glsl */ `
  uniform float uScale;     // drawingBufferHeight * 0.5 (recompute on resize/DPR)
  uniform float uSize;
  uniform float uAttenK;    // 0 = flat poster, ~0.25 = weak depth
  attribute float aSize;
  attribute vec3 aColor;
  varying vec3 vColor;
  void main() {
    vColor = aColor;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    float atten = mix(1.0, uScale / -mv.z, uAttenK);
    gl_PointSize = min(uSize * aSize * atten, 64.0);
    gl_Position = projectionMatrix * mv;
  }
`;

// P0 fragment: simple soft round dot (premultiplied). P1 replaces this.
const FRAGMENT = /* glsl */ `
  precision mediump float;
  varying vec3 vColor;
  uniform vec3 uPostureColor;
  uniform float uPostureTint;
  uniform float uGlowMul;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    float i = pow(1.0 - clamp(d / 0.5, 0.0, 1.0), 2.5);
    if (i <= 0.003) discard;
    vec3 c = mix(vColor, vColor * uPostureColor, clamp(uPostureTint, 0.0, 0.8)) * uGlowMul;
    gl_FragColor = vec4(c * i, i);
  }
`;

export function createPointFieldMaterial(overrides: PointFieldUniformOverrides = {}): THREE.ShaderMaterial {
  const material = new THREE.ShaderMaterial({
    vertexShader: VERTEX,
    fragmentShader: FRAGMENT,
    uniforms: {
      uTime: overrides.uTime ?? { value: 0 },
      uScale: { value: 540 },
      uSize: { value: 9 },
      uAttenK: { value: 0.25 },
      uFogDensity: { value: 0.0 },
      uGlowMul: { value: 1.0 },     // P0 plain; P1 raises >1 for bloom
      uGrow: { value: 0 },
      uFlow: { value: 0.16 },
      uFlowSpeed: { value: 0.16 },
      uCurlAmp: { value: 0 },
      uArrival: { value: 0 },
      uReabsorb: { value: 0 },
      uPostureColor: overrides.uPostureColor ?? { value: new THREE.Color(150 / 255, 120 / 255, 255 / 255) },
      uPostureTint: overrides.uPostureTint ?? { value: 0 },
    },
    transparent: true,
    depthWrite: false,
    depthTest: true,
    toneMapped: false,
    blending: THREE.CustomBlending,
    blendEquation: THREE.AddEquation,
    blendSrc: THREE.OneFactor,
    blendDst: THREE.OneFactor,
    premultipliedAlpha: true,
  });
  material.customProgramCacheKey = () => 'pointfield_v1';
  return material;
}
