/**
 * SuperbrainReactiveEffects — product-only 3D reactions to the AI-OS agent loop.
 *
 * This component is injected into <WorkspaceCanvas> from SuperbrainApp.jsx, so it
 * shares the same R3F context as the being but lives outside the ported lab files.
 * It adds:
 *   - cloud_route  → jagged lightning arc up the spine
 *   - verify pass  → green aurora bloom around the cortex
 *   - caste_start/end → orbiting worker motes at vertebra seats
 */
import { useEffect, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Line } from '@react-three/drei';
import * as THREE from 'three';
import {
  subscribeSwarmHUD,
} from '../superbrain/lib/swarmHUDStore';
import { subscribeCognition } from '../superbrain/lib/cognitionBus';
import {
  fuseSpinePoint,
  getBrainDockScale,
  getCortexAnchor,
} from '../superbrain/lib/spineFusionBus';
import { SEGMENT_ANCHORS } from '../superbrain/lib/spineAnatomy';
import {
  getAuroraIntensity,
  setAuroraIntensity,
  subscribeAurora,
} from './verifyAuroraBridge';
import {
  advanceSpineFlash,
  getSpineFlashState,
  subscribeSpineFlash,
} from './spineFlashBridge';

const CLOUD_COLORS = {
  bedrock: new THREE.Color('#f5c542'),
  gemini: new THREE.Color('#4aa8ff'),
  default: new THREE.Color('#ffffff'),
};

function providerColor(provider) {
  return CLOUD_COLORS[provider] ?? CLOUD_COLORS.default;
}

function jaggedArc(start, end, segments = 9) {
  const points = [start.clone()];
  for (let i = 1; i < segments; i++) {
    const t = i / segments;
    const p = new THREE.Vector3().lerpVectors(start, end, t);
    // jitter perpendicular to the arc
    p.x += (Math.random() - 0.5) * 0.12 * (1 - Math.abs(t - 0.5) * 2);
    p.z += (Math.random() - 0.5) * 0.12 * (1 - Math.abs(t - 0.5) * 2);
    points.push(p);
  }
  points.push(end.clone());
  return points;
}

function seatForIndex(index) {
  return index % SEGMENT_ANCHORS.length;
}

const BEAD_HALF_ANCHORS = 2;

function anchorWorldPosition(i) {
  const clamped = Math.min(SEGMENT_ANCHORS.length - 1, Math.max(0, i));
  const raw = SEGMENT_ANCHORS[clamped];
  const fused = new THREE.Vector3(...fuseSpinePoint([raw.x, raw.y, raw.z]));
  return fused.multiplyScalar(getBrainDockScale());
}

function sampleWorldPosition(t) {
  const i0 = Math.floor(t);
  const frac = t - i0;
  const a = anchorWorldPosition(i0);
  const b = anchorWorldPosition(i0 + 1);
  return a.clone().lerp(b, frac);
}

function beadPointsForProgress(progress) {
  const n = SEGMENT_ANCHORS.length;
  const center = progress * (n - 1);
  const start = Math.max(0, center - BEAD_HALF_ANCHORS);
  const end = Math.min(n - 1, center + BEAD_HALF_ANCHORS);
  const steps = Math.max(2, Math.ceil(end - start) * 2 + 1);
  const points = [];
  for (let s = 0; s < steps; s += 1) {
    const t = start + (end - start) * (s / (steps - 1));
    points.push(sampleWorldPosition(t));
  }
  return points;
}

export default function SuperbrainReactiveEffects() {
  const [lightnings, setLightnings] = useState([]);
  const [motes, setMotes] = useState({});
  const motesRef = useRef({});
  const [aurora, setAurora] = useState(getAuroraIntensity);
  const [spineFlash, setSpineFlash] = useState(getSpineFlashState);
  const lastCloudIndices = useRef(new Set());
  const lastCastes = useRef(new Set());

  useEffect(() => {
    // Sync local React state with the product-only aurora bridge so the
    // sphere mounts/unmounts and animates correctly.
    const unsub = subscribeAurora(setAurora);
    return unsub;
  }, []);

  useEffect(() => {
    // Sync local React state with the product-only spine-flash bridge.
    const unsub = subscribeSpineFlash(setSpineFlash);
    return unsub;
  }, []);

  useEffect(() => {
    // Cloud-route lightning.
    const unsubSwarm = subscribeSwarmHUD((state) => {
      const current = new Set(state.cloudIndices);
      const added = [...current].filter((i) => !lastCloudIndices.current.has(i));
      if (added.length > 0) {
        setLightnings((prev) => {
          const next = [...prev];
          for (const idx of added) {
            const seat = seatForIndex(idx);
            const raw = SEGMENT_ANCHORS[seat];
            const fused = new THREE.Vector3(...fuseSpinePoint([raw.x, raw.y, raw.z]));
            const dockScale = getBrainDockScale();
            const start = fused.clone().multiplyScalar(dockScale);
            const end = start.clone().add(new THREE.Vector3(0.35, 0.55, 0.25));
            next.push({
              id: `${Date.now()}-${idx}`,
              points: jaggedArc(start, end),
              color: providerColor(state.provider ?? 'default'),
              born: performance.now(),
            });
          }
          return next;
        });
      }
      lastCloudIndices.current = current;
    });

    // Verify-pass aurora.
    const unsubCognition = subscribeCognition((event) => {
      if (event.type === 'verify' && event.data?.verdict === 'pass') {
        setAuroraIntensity(1);
      }
    });

    return () => {
      unsubSwarm();
      unsubCognition();
    };
  }, []);

  // Caste start/end motes: compare activeCastes sets.
  useEffect(() => {
    const unsub = subscribeSwarmHUD((state) => {
      const current = new Set(state.activeCastes);
      const added = [...current].filter((c) => !lastCastes.current.has(c));
      const removed = [...lastCastes.current].filter((c) => !current.has(c));
      if (added.length === 0 && removed.length === 0) return;

      setMotes((prev) => {
        const next = { ...prev };
        for (const caste of removed) delete next[caste];
        for (let i = 0; i < added.length; i++) {
          const caste = added[i];
          const seat = seatForIndex(Object.keys(next).length + i);
          const raw = SEGMENT_ANCHORS[seat];
          const fused = new THREE.Vector3(...fuseSpinePoint([raw.x, raw.y, raw.z]));
          next[caste] = {
            seat,
            origin: fused,
            angle: Math.random() * Math.PI * 2,
            speed: 0.5 + Math.random() * 0.4,
            radius: 0.18 + Math.random() * 0.06,
          };
        }
        return next;
      });
      lastCastes.current = current;
    });
    return unsub;
  }, []);

  useFrame((_, delta) => {
    // Decay aurora intensity in the bridge; the subscriber updates React state.
    const intensity = getAuroraIntensity();
    if (intensity > 0) {
      const target = Math.max(0, intensity - delta * 0.9);
      if (target !== intensity) {
        setAuroraIntensity(target);
      }
    }

    // Advance the first-cloud-route spine flash; the subscriber updates React state.
    advanceSpineFlash(delta);

    // Age-out lightnings only when there are any to avoid per-frame re-renders.
    const now = performance.now();
    setLightnings((prev) => {
      if (prev.length === 0) return prev;
      const next = prev.filter((l) => now - l.born < 900);
      return next.length === prev.length ? prev : next;
    });

    // Orbit motes only when there are any.
    if (Object.keys(motesRef.current).length > 0) {
      setMotes((prev) => {
        if (Object.keys(prev).length === 0) return prev;
        const next = {};
        for (const [caste, m] of Object.entries(prev)) {
          next[caste] = { ...m, angle: m.angle + m.speed * delta };
        }
        return next;
      });
    }
  });

  // Keep a ref in sync so useFrame can guard against empty-object churn.
  useEffect(() => {
    motesRef.current = motes;
  }, [motes]);

  const [cx, cy, cz] = getCortexAnchor();
  const cortex = new THREE.Vector3(cx, cy, cz).multiplyScalar(getBrainDockScale());
  const auroraScale = 0.22 + aurora * 0.18;

  return (
    <group name="superbrain-reactive-effects">
      {lightnings.map((l) => (
        <Line
          key={l.id}
          points={l.points}
          color={l.color}
          lineWidth={2}
          transparent
          opacity={0.9}
        />
      ))}

      {/* First-cloud-route spine flash: a bright bead travelling down the spine. */}
      {spineFlash.intensity > 0.01 && (
        <group name="spine-flash">
          <Line
            data-testid="spine-flash"
            points={beadPointsForProgress(spineFlash.progress)}
            color="#e0ffff"
            lineWidth={5}
            transparent
            opacity={spineFlash.intensity * 0.85}
          />
          <mesh
            data-testid="spine-flash-bead"
            position={sampleWorldPosition(spineFlash.progress * (SEGMENT_ANCHORS.length - 1))}
            scale={[
              0.07 + spineFlash.intensity * 0.05,
              0.07 + spineFlash.intensity * 0.05,
              0.07 + spineFlash.intensity * 0.05,
            ]}
          >
            <sphereGeometry args={[1, 16, 16]} />
            <meshBasicMaterial
              color="#e0ffff"
              transparent
              opacity={spineFlash.intensity * 0.45}
              depthWrite={false}
              blending={THREE.AdditiveBlending}
            />
          </mesh>
        </group>
      )}

      {/* Verify-pass aurora: a soft, transient green bloom around the cortex. */}
      {aurora > 0.01 && (
        <mesh
          data-testid="verify-aurora"
          position={cortex}
          scale={[auroraScale, auroraScale, auroraScale]}
        >
          <sphereGeometry args={[1, 32, 32]} />
          <meshBasicMaterial
            color="#2fffa1"
            transparent
            opacity={aurora * 0.14}
            depthWrite={false}
            side={THREE.DoubleSide}
            blending={THREE.AdditiveBlending}
          />
        </mesh>
      )}

      {/* Worker caste orbiters. */}
      {Object.entries(motes).map(([caste, m]) => {
        const pos = m.origin.clone();
        pos.x += Math.cos(m.angle) * m.radius;
        pos.z += Math.sin(m.angle) * m.radius;
        pos.multiplyScalar(getBrainDockScale());
        return (
          <mesh key={caste} position={pos}>
            <sphereGeometry args={[0.04, 8, 8]} />
            <meshBasicMaterial color="#aefeff" transparent opacity={0.85} />
          </mesh>
        );
      })}
    </group>
  );
}
