import * as THREE from 'three';

const vertexShader = /* glsl */ `
varying vec3 vHaloNormal;
varying vec3 vHaloToEye;
void main() {
  vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
  vHaloNormal = normalMatrix * normal;
  vHaloToEye = -viewPosition.xyz;
  gl_Position = projectionMatrix * viewPosition;
}`;

const fragmentShader = /* glsl */ `
uniform vec3 uColor;
uniform float uOpacity;
varying vec3 vHaloNormal;
varying vec3 vHaloToEye;
void main() {
  float facing = clamp(abs(dot(normalize(vHaloNormal), normalize(vHaloToEye))), 0.0, 1.0);
  float rim = 1.0 - facing;
  gl_FragColor = vec4(uColor, uOpacity * rim * rim);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;

/** Lab-only: retain the supervision color/envelope, remove its filled cap. */
export function createSupervisedHaloMaterial() {
  return new THREE.ShaderMaterial({ vertexShader, fragmentShader,
    uniforms: { uColor: { value: new THREE.Color('#54f0a0') }, uOpacity: { value: 0.06 } },
    transparent: true, opacity: 0.06,
    blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false });
}

export function updateSupervisedHaloFrame(material: THREE.ShaderMaterial, elapsed: number, reducedMotion: boolean) {
  const pulse = reducedMotion ? 0.5 : 0.5 + 0.5 * Math.sin(elapsed * 1.1);
  material.opacity = 0.04 + pulse * 0.05;
  material.uniforms.uOpacity.value = material.opacity;
}
