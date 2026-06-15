'use client';

import { useEffect, useMemo, useRef, type MutableRefObject } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { subscribeCognition } from '@/lib/cognitionBus';
import type { BurstRef } from './SuperbrainScene';

const PARTICLE_COUNT = 820;
const INNER_RADIUS = 1.55;
const OUTER_RADIUS = 4.85;
const INFALL_PERIOD = 34;
const SPIN_TURNS = 1.6;
const TAU = Math.PI * 2;

const BASE_TILT_X = 0.42;
const BASE_TILT_Z = -0.14;

// "Knowledge-acquired" feeding pulse: disc brightness multiplies x1.0 -> x1.5
// at full strength, decaying over ~1.2s (exp(-3.6 * 1.2s) ~= 1.3%).
const PULSE_GAIN = 0.5;
const PULSE_DECAY_RATE = 3.6;

interface DiskGeometryData {
  positions: Float32Array;
  angles: Float32Array;
  offsets: Float32Array;
  speeds: Float32Array;
  phases: Float32Array;
  sizes: Float32Array;
  tints: Float32Array;
  jitters: Float32Array;
}

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

  void main() {
    float radius = length(gl_PointCoord - vec2(0.5));
    if (radius > 0.5) discard;
    float core = 1.0 - smoothstep(0.06, 0.5, radius);
    gl_FragColor = vec4(vColor * (0.7 + core * 0.55), vAlpha * core);
  }
`;

function createSeededRandom(seed: number) {
  let state = seed >>> 0;
  return () => {
    state += 0x6d2b79f5;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function pickTint(roll: number) {
  if (roll < 0.6) return 0;
  if (roll < 0.78) return 3;
  if (roll < 0.9) return 1;
  return 2;
}

function createDiskData(): DiskGeometryData {
  const random = createSeededRandom(0x41434352);
  const positions = new Float32Array(PARTICLE_COUNT * 3);
  const angles = new Float32Array(PARTICLE_COUNT);
  const offsets = new Float32Array(PARTICLE_COUNT);
  const speeds = new Float32Array(PARTICLE_COUNT);
  const phases = new Float32Array(PARTICLE_COUNT);
  const sizes = new Float32Array(PARTICLE_COUNT);
  const tints = new Float32Array(PARTICLE_COUNT);
  const jitters = new Float32Array(PARTICLE_COUNT);

  for (let index = 0; index < PARTICLE_COUNT; index += 1) {
    angles[index] = random() * TAU;
    offsets[index] = random() + random() - 1;
    speeds[index] = 0.75 + random() * 0.55;
    phases[index] = random();
    sizes[index] = 0.5 + random() * 0.85;
    tints[index] = pickTint(random());
    jitters[index] = random() * 2 - 1;
  }

  return { positions, angles, offsets, speeds, phases, sizes, tints, jitters };
}

export default function AccretionCore({
  activity,
  burst,
  arrival,
}: {
  activity: number;
  burst: BurstRef;
  /** Shared coalescence scalar: 1 = arriving (motes stream in), 0 = settled. */
  arrival: MutableRefObject<number>;
}) {
  const groupRef = useRef<THREE.Group>(null);
  const diskMaterialRef = useRef<THREE.ShaderMaterial>(null);
  const flowTimeRef = useRef(0);
  const smoothedActivityRef = useRef(THREE.MathUtils.clamp(activity, 0, 1));
  /** 0..1 feeding-pulse strength, set on knowledge-acquired, decays in-frame. */
  const pulseRef = useRef(0);

  // The disc is the stomach: whenever a grasp tendril publishes an absorbed
  // knowledge packet, the inflow glows briefly. Ref write only (no re-render);
  // unsubscribed on unmount.
  useEffect(() => {
    const unsubscribe = subscribeCognition((event) => {
      if (event.type === 'knowledge-acquired') {
        pulseRef.current = THREE.MathUtils.clamp(0.6 + (event.intensity ?? 1) * 0.4, 0, 1);
      }
    });
    return unsubscribe;
  }, []);

  const diskData = useMemo(() => createDiskData(), []);
  const uniforms = useMemo(
    () => ({
      uFlowTime: { value: 0 },
      uActivity: { value: 0 },
      uBurst: { value: 0 },
      uPulse: { value: 1 },
      uArrival: { value: 0 },
    }),
    [],
  );

  useFrame((state, delta) => {
    const time = state.clock.elapsedTime;
    const nextActivity = THREE.MathUtils.clamp(activity, 0, 1);
    smoothedActivityRef.current = THREE.MathUtils.damp(smoothedActivityRef.current, nextActivity, 4, delta);
    const smoothedActivity = smoothedActivityRef.current;
    const burstPow = burst.current.intensity;

    // Integrate flow speed so activity changes accelerate the inflow without
    // jumps; cognition bursts briefly spin the disk faster.
    flowTimeRef.current += delta * (0.72 + smoothedActivity * 0.6 + burstPow * 0.55);

    // Feeding pulse decays smoothly back to neutral over ~1.2s.
    pulseRef.current *= Math.exp(-PULSE_DECAY_RATE * delta);
    if (pulseRef.current < 0.001) pulseRef.current = 0;

    if (diskMaterialRef.current) {
      diskMaterialRef.current.uniforms.uFlowTime.value = flowTimeRef.current;
      diskMaterialRef.current.uniforms.uActivity.value = smoothedActivity;
      diskMaterialRef.current.uniforms.uBurst.value = burstPow;
      diskMaterialRef.current.uniforms.uPulse.value = 1 + pulseRef.current * PULSE_GAIN;
      diskMaterialRef.current.uniforms.uArrival.value = arrival.current;
    }

    if (groupRef.current) {
      groupRef.current.rotation.x = BASE_TILT_X + Math.sin(time * 0.07) * 0.035;
      groupRef.current.rotation.z = BASE_TILT_Z + Math.cos(time * 0.06) * 0.03;
    }

  });

  return (
    <group ref={groupRef} position={[0, 0.12, -1.18]} rotation={[BASE_TILT_X, 0, BASE_TILT_Z]}>
      <points frustumCulled={false}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[diskData.positions, 3]} />
          <bufferAttribute attach="attributes-aAngle" args={[diskData.angles, 1]} />
          <bufferAttribute attach="attributes-aOffsetY" args={[diskData.offsets, 1]} />
          <bufferAttribute attach="attributes-aSpeed" args={[diskData.speeds, 1]} />
          <bufferAttribute attach="attributes-aPhase" args={[diskData.phases, 1]} />
          <bufferAttribute attach="attributes-aSize" args={[diskData.sizes, 1]} />
          <bufferAttribute attach="attributes-aTint" args={[diskData.tints, 1]} />
          <bufferAttribute attach="attributes-aJitter" args={[diskData.jitters, 1]} />
        </bufferGeometry>
        <shaderMaterial
          ref={diskMaterialRef}
          vertexShader={DISK_VERTEX_SHADER}
          fragmentShader={DISK_FRAGMENT_SHADER}
          uniforms={uniforms}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </points>

    </group>
  );
}
