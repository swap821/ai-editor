import { useEffect, useMemo, useRef, type MutableRefObject } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { subscribeCognition } from '@/lib/cognitionBus';
import type { BurstRef, CognitionUniforms } from '../../components/canvas/SuperbrainScene.LEGACY';
import { createDiskData, BASE_TILT_X, BASE_TILT_Z, PULSE_GAIN, PULSE_DECAY_RATE } from './CoreGeometry';
import './DecayAura'; // ensures DecayAuraMaterial is registered

export default function MemoryParticles({
  activity,
  burst,
  arrival,
  sceneUniforms,
}: {
  activity: number;
  burst: BurstRef;
  /** Shared coalescence scalar: 1 = arriving (motes stream in), 0 = settled. */
  arrival: MutableRefObject<number>;
  /** Shared cognition uniforms — used for the posture hue leaves (optional). */
  sceneUniforms?: CognitionUniforms;
}) {
  const groupRef = useRef<THREE.Group>(null);
  const diskMaterialRef = useRef<any>(null);
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
  
  // The shaderMaterial from drei creates an instance where we can just assign uniforms directly
  // or via JSX props. We'll use props for static ones and update dynamic ones in useFrame.

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
      diskMaterialRef.current.uFlowTime = flowTimeRef.current;
      diskMaterialRef.current.uActivity = smoothedActivity;
      diskMaterialRef.current.uBurst = burstPow;
      diskMaterialRef.current.uPulse = 1 + pulseRef.current * PULSE_GAIN;
      diskMaterialRef.current.uArrival = arrival.current;
      
      if (sceneUniforms) {
        diskMaterialRef.current.uPostureColor = sceneUniforms.uPosture.value;
        diskMaterialRef.current.uPostureTint = sceneUniforms.uPostureTint.value;
      }
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
        <decayAuraMaterial
          ref={diskMaterialRef}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </points>
    </group>
  );
}
