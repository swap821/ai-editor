import * as THREE from 'three';
import { shaderMaterial } from '@react-three/drei';
import { extend } from '@react-three/fiber';

export const THOUGHT_WAVE_GLSL = /* glsl */ `
  uniform vec3 uWaveOrigins[3];
  uniform float uWaveTimes[3];

  // Expanding spherical wavefront in brain-group-local space. The 3.02 factor
  // converts local distance into the ~world-scale units the 1.4 u/s front
  // speed and 0.8/s decay were tuned for (BRAIN_SCALE). All terms are clamped
  // so dormant slots (startTime << 0) can never produce inf * 0 = NaN.
  float thoughtWave(vec3 p, float t, float sharpness) {
    float w = 0.0;
    for (int i = 0; i < 3; i++) {
      float age = t - uWaveTimes[i];
      float live = step(0.0, age) * (1.0 - smoothstep(5.0, 6.0, age));
      float a = clamp(age, 0.0, 6.0);
      float d = distance(p, uWaveOrigins[i]) * 3.02;
      float front = abs(d - a * 1.4) * sharpness;
      w += live * exp(-front * front) * exp(-a * 0.8);
    }
    return w;
  }
`;

const FIREFLY_VERTEX_SHADER = /* glsl */ `
  ${THOUGHT_WAVE_GLSL}

  uniform float uTime;
  uniform float uActivity;
  uniform float uPixelRatio;

  attribute vec3 aColor;
  attribute float aPhase;
  attribute float aSpeed;
  attribute float aSize;

  varying vec3 vColor;
  varying float vAlpha;

  void main() {
    // Sharp synapse spike, not a lava lamp: pow-8 narrows the sine to a blink.
    float flash = pow(0.5 + 0.5 * sin(uTime * aSpeed * 4.0 + aPhase), 8.0);

    // Sentience bias: synapses fire WHERE the thought-wave passes. The
    // proximity lobe is wider (sharpness 3) than the cortex's tight front.
    float prox = clamp(thoughtWave(position, uTime, 3.0) * 1.6, 0.0, 1.0);
    flash *= 0.3 + 0.7 * prox;
    flash *= 0.7 + uActivity * 0.5;

    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    // Large glowing nodes
    gl_PointSize = max(
      aSize * flash * 120.0 * uPixelRatio / max(2.0, -mvPosition.z),
      12.0 * uPixelRatio
    );
    gl_Position = projectionMatrix * mvPosition;

    vColor = aColor;
    vAlpha = flash;
  }
`;

const FIREFLY_FRAGMENT_SHADER = /* glsl */ `
  varying vec3 vColor;
  varying float vAlpha;
  uniform vec3 uPostureColor;
  uniform float uPostureTint;

  void main() {
    float dist = length(gl_PointCoord - 0.5);
    if (dist > 0.5) discard;

    // Soft glowing edge
    float glow = 1.0 - smoothstep(0.0, 0.5, dist);
    // Bright hot core
    float core = 1.0 - smoothstep(0.0, 0.15, dist);

    vec3 finalColor = mix(vColor, vec3(1.0), core * 0.6);
    // Posture wash: the cortical motes shift toward the body's current hue.
    finalColor = mix(finalColor, finalColor * uPostureColor * 1.9, clamp(uPostureTint, 0.0, 0.8));
    gl_FragColor = vec4(finalColor, vAlpha * glow);
  }
`;

export const RoutingMaterial = shaderMaterial(
  {
    uTime: 0,
    uWaveOrigins: [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()],
    uWaveTimes: [-1000, -1000, -1000],
    uActivity: 0,
    uPixelRatio: 1,
    uPostureColor: new THREE.Color(),
    uPostureTint: 0,
  },
  FIREFLY_VERTEX_SHADER,
  FIREFLY_FRAGMENT_SHADER
);

extend({ RoutingMaterial });

declare module '@react-three/fiber' {
  interface ThreeElements {
    routingMaterial: any;
  }
}
