import * as THREE from 'three';
import { shaderMaterial } from '@react-three/drei';
import { extend } from '@react-three/fiber';
import { OUTER_RADIUS, INNER_RADIUS, INFALL_PERIOD, SPIN_TURNS, TAU } from './CoreGeometry';

const DISK_VERTEX_SHADER = `
  uniform float uFlowTime;
  uniform float uActivity;
  uniform float uBurst;
  uniform float uPulse;
  uniform float uArrival;

  attribute float aAngle;
  attribute float aOffsetY;
  attribute float aSpeed;
  attribute float aPhase;
  attribute float aSize;
  attribute float aTint;
  attribute float aJitter;

  varying vec3 vColor;
  varying float vAlpha;

  vec3 accretionColor(float tint) {
    if (tint < 0.5) return vec3(0.20, 0.72, 0.94);
    if (tint < 1.5) return vec3(0.48, 0.32, 0.86);
    if (tint < 2.5) return vec3(0.88, 0.62, 0.26);
    return vec3(0.70, 0.24, 0.46);
  }

  void main() {
    // Inflow progress: 0 = spawned at the rim, 1 = absorbed by the core.
    float progress = fract(aPhase + uFlowTime * aSpeed / ${INFALL_PERIOD.toFixed(1)});
    float infall = pow(progress, 1.65);
    float radius = mix(${OUTER_RADIUS.toFixed(2)}, ${INNER_RADIUS.toFixed(2)}, infall)
      + aJitter * (0.55 - infall * 0.38);
    float radiusNorm = clamp(
      (radius - ${INNER_RADIUS.toFixed(2)}) / ${(OUTER_RADIUS - INNER_RADIUS).toFixed(2)},
      0.0,
      1.0
    );

    // Swirl accelerates as the mote falls inward, like orbital decay.
    float swirl = (progress * 0.35 + pow(progress, 2.4) * 0.65) * ${(SPIN_TURNS * TAU).toFixed(4)};
    float angle = aAngle + swirl * (0.85 + aSpeed * 0.18);

    vec3 transformed = vec3(
      cos(angle) * radius,
      aOffsetY * (0.07 + 0.34 * radiusNorm),
      sin(angle) * radius
    );

    vec4 mvPosition = modelViewMatrix * vec4(transformed, 1.0);
    float distanceScale = 46.0 / max(8.0, -mvPosition.z);
    gl_PointSize = clamp(aSize * distanceScale * (0.85 + uActivity * 0.3), 0.55, 2.2);
    gl_Position = projectionMatrix * mvPosition;

    float fadeIn = smoothstep(0.0, 0.07, progress);
    float fadeOut = 1.0 - smoothstep(0.94, 1.0, progress);
    float ember = pow(1.0 - radiusNorm, 1.8);
    float flash = smoothstep(0.86, 0.97, progress);

    vAlpha = fadeIn * fadeOut * (0.08 + uActivity * 0.11) * (0.45 + ember * 0.82);
    vAlpha *= 1.0 + uBurst * 0.5;
    // Coalescence: the motes read as STREAMING IN while the field condenses
    // (uArrival 1 -> 0), settling to the exact canon inflow at rest (uArrival==0).
    vAlpha *= 1.0 + uArrival * 0.8;
    vColor = accretionColor(aTint) * (0.5 + ember * 0.9 + uActivity * 0.18);
    vColor = mix(vColor, vec3(0.88, 0.98, 1.0), flash * 0.65);
    vColor *= 1.0 + uBurst * 0.45;
    // The disc is the stomach: it glows for ~1.2s whenever the grasp
    // tendrils feed it a knowledge packet (uPulse: 1.0 -> 1.5 -> 1.0).
    vColor *= uPulse;
  }
`;

const DISK_FRAGMENT_SHADER = `
  varying vec3 vColor;
  varying float vAlpha;
  uniform vec3 uPostureColor;
  uniform float uPostureTint;

  void main() {
    float radius = length(gl_PointCoord - vec2(0.5));
    if (radius > 0.5) discard;
    float core = 1.0 - smoothstep(0.06, 0.5, radius);
    vec3 col = vColor * (0.7 + core * 0.55);
    // Posture wash: the accretion core settles into the body's current hue.
    col = mix(col, col * uPostureColor * 1.9, clamp(uPostureTint, 0.0, 0.8));
    gl_FragColor = vec4(col, vAlpha * core);
  }
`;

export const DecayAuraMaterial = shaderMaterial(
  {
    uFlowTime: 0,
    uActivity: 0,
    uBurst: 0,
    uPulse: 1,
    uArrival: 0,
    uPostureColor: new THREE.Color(150 / 255, 120 / 255, 255 / 255),
    uPostureTint: 0,
  },
  DISK_VERTEX_SHADER,
  DISK_FRAGMENT_SHADER
);

extend({ DecayAuraMaterial });

declare module '@react-three/fiber' {
  interface ThreeElements {
    decayAuraMaterial: any;
  }
}
