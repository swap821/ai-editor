import { useFrame } from '@react-three/fiber';
import { BODY_POSTURES, postureColor01, POSTURE_DIAL, type BodyPosture } from '@/lib/bodyPosture';
import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import type { AnatomicalConductorSnapshot, AnatomicalVertebraSignal } from '@/lib/anatomicalConductor';
import type { AnatomicalRootSystemSnapshot, AnatomicalRootStrand, CaudaEquinaTrace } from '@/lib/anatomicalRootSystem';

const BEAD_COUNT = 3;
const ROOT_FAN_PUNCTA = 4;
const CAUDA_TRACE_PUNCTA = 3;

type RenderRootFan = {
  key: string;
  role: AnatomicalRootStrand['role'];
  flow: AnatomicalRootStrand['flow'];
  opacity: number;
  tension: number;
  beadSpeed: number;
  pulseRate: number;
  tint: string;
  secondaryTint: string;
  memoryTrace: number;
  flowDelay: number;
  side: AnatomicalRootStrand['side'];
  channel: AnatomicalRootStrand['channel'];
  curve: THREE.CatmullRomCurve3;
  geometry: THREE.TubeGeometry;
};

function clamp01(value: number): number {
  return THREE.MathUtils.clamp(value, 0, 1);
}

function signalPosition(signal: AnatomicalVertebraSignal): THREE.Vector3 {
  const [x, y, z] = signal.anchorLocal;
  return new THREE.Vector3(x, y, z + 0.09);
}

function tuplePosition(tuple: [number, number, number]): THREE.Vector3 {
  return new THREE.Vector3(tuple[0], tuple[1], tuple[2] + 0.09);
}

function rootRoleGain(role: AnatomicalRootStrand['role']): number {
  if (role === 'holding') return 1.28;
  if (role === 'error') return 1.34;
  if (role === 'conducting') return 1.18;
  if (role === 'gripping') return 1.08;
  if (role === 'reabsorbing') return 1.02;
  if (role === 'sensing') return 0.66;
  return 0;
}

function rootWaveRate(root: Pick<AnatomicalRootStrand, 'role' | 'flow' | 'pulseRate'>): number {
  if (root.role === 'holding') return 1.1;
  if (root.role === 'error') return 5.2;
  if (root.role === 'reabsorbing') return 1.8;
  if (root.flow === 'return') return 2.3;
  return Math.max(1.2, root.pulseRate);
}

function rootTravelDirection(flow: AnatomicalRootStrand['flow'] | CaudaEquinaTrace['flow']): number {
  return flow === 'return' ? -1 : 1;
}

export default function AnatomicalConductorOverlay({
  anatomy,
  rootSystem,
  reducedMotion,
  bodyPosture = BODY_POSTURES.rest,
}: {
  anatomy: AnatomicalConductorSnapshot;
  rootSystem?: AnatomicalRootSystemSnapshot;
  reducedMotion: boolean;
  bodyPosture?: BodyPosture;
}) {
  const socketRefs = useRef<THREE.Mesh[]>([]);
  const nodeRefs = useRef<THREE.Mesh[]>([]);
  const lateralRefs = useRef<THREE.Mesh[]>([]);
  const fanRefs = useRef<THREE.Mesh[]>([]);
  const fanPunctaRefs = useRef<THREE.Mesh[]>([]);
  const caudaRefs = useRef<THREE.Mesh[]>([]);
  const caudaPunctaRefs = useRef<THREE.Mesh[]>([]);
  const trunkRef = useRef<THREE.Mesh>(null);
  const beadRefs = useRef<THREE.Mesh[]>([]);
  // Posture wash: the conductor trunk/beads/cauda/puncta settle into the body's
  // current hue (spectral-v1), blended OVER the anatomy tint. Role-colored signals
  // and fans (amber hold / red error) keep their semantic colors on top.
  const trunkColor = useMemo(() => {
    const [pr, pg, pb] = postureColor01(bodyPosture.color);
    return new THREE.Color(anatomy.trunkTint).lerp(new THREE.Color(pr, pg, pb), POSTURE_DIAL.surfaceTint);
  }, [anatomy.trunkTint, bodyPosture.color]);

  const activeSignals = anatomy.vertebrae.filter((signal) => signal.role !== 'idle');

  const trunkCurve = useMemo(() => {
    const points = anatomy.conductingSeatIndexes
      .map((seatIndex) => anatomy.vertebrae[seatIndex])
      .filter(Boolean)
      .map(signalPosition);
    if (points.length < 2) return null;
    return new THREE.CatmullRomCurve3(points);
  }, [anatomy.conductingSeatIndexes, anatomy.vertebrae]);

  const trunkGeometry = useMemo(() => {
    if (!trunkCurve) return null;
    return new THREE.TubeGeometry(trunkCurve, 42, 0.0055, 7, false);
  }, [trunkCurve]);

  const fallbackRootFans = useMemo<RenderRootFan[]>(() => {
    return activeSignals.flatMap((signal) => {
      const anchor = signalPosition(signal);
      const seatFactor = signal.seatIndex / Math.max(1, anatomy.vertebrae.length - 1);
      const length = 0.22 + seatFactor * 0.34 + signal.intensity * 0.08;
      const droop = 0.08 + seatFactor * 0.16;
      return [-1, 1].flatMap((side) =>
        [-1, 1].map((channel) => {
          const channelOffset = channel * (0.018 + seatFactor * 0.01);
          const start = anchor.clone().add(new THREE.Vector3(side * 0.025, channelOffset, 0.006));
          const midA = anchor
            .clone()
            .add(new THREE.Vector3(side * (length * 0.26), channelOffset - droop * 0.18, 0.042));
          const midB = anchor
            .clone()
            .add(new THREE.Vector3(side * (length * 0.64), channelOffset - droop * 0.55, 0.035));
          const end = anchor
            .clone()
            .add(new THREE.Vector3(side * length, channelOffset - droop * (0.86 + channel * 0.16), 0.018));
          const curve = new THREE.CatmullRomCurve3([start, midA, midB, end]);
          const role: AnatomicalRootStrand['role'] =
            signal.role === 'held'
              ? 'holding'
              : signal.role === 'active'
                ? 'conducting'
                : signal.role === 'reabsorbing'
                  ? 'reabsorbing'
                  : 'sensing';
          return {
            key: `${signal.seatIndex}-${side}-${channel}`,
            role,
            flow: role === 'reabsorbing' ? 'return' : role === 'conducting' ? 'outbound' : 'bidirectional',
            opacity: signal.rootOpacity,
            tension: signal.intensity,
            beadSpeed: signal.role === 'held' ? 0.07 : signal.role === 'waiting' ? 0.08 : 0.2,
            pulseRate: signal.role === 'held' ? 1.1 : 2.6,
            tint: signal.tint,
            secondaryTint: anatomy.trunkTint,
            memoryTrace: signal.role === 'reabsorbing' ? 0.7 : 0,
            flowDelay: signal.flowDelay,
            side: side > 0 ? 'right' : 'left',
            channel: channel > 0 ? 'upper' : 'lower',
            curve,
            geometry: new THREE.TubeGeometry(curve, 24, 0.0036 + signal.intensity * 0.0028, 6, false),
          };
        }),
      );
    });
  }, [activeSignals, anatomy.vertebrae.length]);

  const rootFans = useMemo<RenderRootFan[]>(() => {
    if (!rootSystem) return fallbackRootFans;
    return rootSystem.strands.map((strand) => {
      const curve = new THREE.CatmullRomCurve3([
        tuplePosition(strand.startLocal),
        tuplePosition(strand.midALocal),
        tuplePosition(strand.midBLocal),
        tuplePosition(strand.endLocal),
      ]);
      return {
        key: strand.id,
        role: strand.role,
        flow: strand.flow,
        opacity: strand.opacity,
        tension: strand.tension,
        beadSpeed: strand.beadSpeed,
        pulseRate: strand.pulseRate,
        tint: strand.tint,
        secondaryTint: strand.secondaryTint,
        memoryTrace: strand.memoryTrace,
        flowDelay: strand.flowDelay,
        side: strand.side,
        channel: strand.channel,
        curve,
        geometry: new THREE.TubeGeometry(curve, 28, strand.radius, 7, false),
      };
    });
  }, [fallbackRootFans, rootSystem]);

  const caudaTraces = useMemo(() => {
    return (rootSystem?.caudaTraces ?? []).map((trace) => {
      const curve = new THREE.CatmullRomCurve3([
        tuplePosition(trace.startLocal),
        tuplePosition(trace.midLocal),
        tuplePosition(trace.endLocal),
      ]);
      return {
        ...trace,
        curve,
        geometry: new THREE.TubeGeometry(curve, 32, trace.radius, 7, false),
      };
    });
  }, [rootSystem]);

  useEffect(() => {
    return () => {
      trunkGeometry?.dispose();
      rootFans.forEach((fan) => fan.geometry.dispose());
      caudaTraces.forEach((trace) => trace.geometry.dispose());
    };
  }, [caudaTraces, rootFans, trunkGeometry]);

  useFrame((state) => {
    const time = state.clock.elapsedTime;
    const globalWave = reducedMotion ? 0.82 : 0.72 + 0.28 * (0.5 + 0.5 * Math.sin(time * 2.7));

    for (const signal of activeSignals) {
      const socket = socketRefs.current[signal.seatIndex];
      const node = nodeRefs.current[signal.seatIndex];
      const color = new THREE.Color(signal.tint);
      const wave =
        reducedMotion || signal.role === 'waiting'
          ? 0.86
          : 0.76 + 0.24 * (0.5 + 0.5 * Math.sin(time * (signal.role === 'held' ? 1.35 : 3.2) + signal.flowDelay * 18));
      const socketOpacity = clamp01(signal.socketOpacity * wave);
      const rootOpacity = clamp01(signal.rootOpacity * (0.72 + globalWave * 0.28));

      if (socket) {
        socket.scale.setScalar(signal.ringScale * (0.92 + signal.intensity * 0.18 * wave));
        const mat = socket.material as THREE.MeshBasicMaterial;
        mat.color.copy(color);
        mat.opacity = socketOpacity;
      }

      if (node) {
        node.scale.setScalar(0.62 + signal.intensity * 0.42);
        const mat = node.material as THREE.MeshBasicMaterial;
        mat.color.copy(color);
        mat.opacity = rootOpacity;
      }

      const left = lateralRefs.current[signal.seatIndex * 2];
      const right = lateralRefs.current[signal.seatIndex * 2 + 1];
      for (const lateral of [left, right]) {
        if (!lateral) continue;
        lateral.scale.setScalar(0.46 + signal.intensity * 0.32);
        const mat = lateral.material as THREE.MeshBasicMaterial;
        mat.color.copy(color);
        mat.opacity = Math.min(0.3, rootOpacity * 0.92);
      }
    }

    rootFans.forEach((fan, index) => {
      const root = fanRefs.current[index];
      if (!root) return;
      const color = new THREE.Color(fan.tint);
      const roleGain = rootRoleGain(fan.role);
      const wave =
        reducedMotion || fan.role === 'sensing'
          ? 0.8
          : 0.66 + 0.34 * (0.5 + 0.5 * Math.sin(time * rootWaveRate(fan) + fan.flowDelay * 16));
      const mat = root.material as THREE.MeshBasicMaterial;
      mat.color.copy(color);
      mat.opacity = Math.min(0.34, fan.opacity * roleGain * wave);
    });

    caudaTraces.forEach((trace, index) => {
      const root = caudaRefs.current[index];
      if (!root) return;
      const color = new THREE.Color(trace.tint);
      const wave = reducedMotion ? 0.78 : 0.68 + 0.32 * (0.5 + 0.5 * Math.sin(time * 1.7 + trace.flowDelay * 13));
      const mat = root.material as THREE.MeshBasicMaterial;
      mat.color.copy(color).lerp(trunkColor, 0.14);
      mat.opacity = Math.min(0.32, trace.opacity * (0.7 + trace.memoryStrength * 0.48) * wave);
    });

    if (trunkRef.current && trunkGeometry) {
      const geometry = trunkRef.current.geometry;
      const drawCount = geometry.getIndex()?.count ?? geometry.getAttribute('position').count;
      geometry.setDrawRange(0, Math.max(2, Math.floor(drawCount * Math.max(0.08, anatomy.trunkIntensity))));
      const mat = trunkRef.current.material as THREE.MeshBasicMaterial;
      mat.color.copy(trunkColor);
      mat.opacity = Math.min(0.18, anatomy.trunkIntensity * globalWave * 0.18);
    }

    if (!trunkCurve) return;
    beadRefs.current.forEach((bead, index) => {
      if (!bead) return;
      const travel = reducedMotion ? 0.92 : (time * 0.24 + index * 0.31) % 1;
      bead.position.copy(trunkCurve.getPointAt(clamp01(travel)));
      bead.scale.setScalar(0.32 + anatomy.trunkIntensity * 0.42);
      const mat = bead.material as THREE.MeshBasicMaterial;
      mat.color.copy(trunkColor);
      mat.opacity = Math.min(0.54, anatomy.trunkIntensity * (0.45 + globalWave * 0.35));
    });

    rootFans.forEach((fan, fanIndex) => {
      const color = new THREE.Color(fan.tint);
      for (let punctaIndex = 0; punctaIndex < ROOT_FAN_PUNCTA; punctaIndex += 1) {
        const punctum = fanPunctaRefs.current[fanIndex * ROOT_FAN_PUNCTA + punctaIndex];
        if (!punctum) continue;
        const base = (punctaIndex + 1) / (ROOT_FAN_PUNCTA + 1);
        const travel =
          reducedMotion || fan.role === 'holding'
            ? base
            : (base + time * rootTravelDirection(fan.flow) * Math.max(0.02, fan.beadSpeed * 0.12) + fan.flowDelay) % 1;
        punctum.position.copy(fan.curve.getPointAt(clamp01(travel < 0 ? travel + 1 : travel)));
        const roleGain = fan.role === 'sensing' ? 0.48 : fan.role === 'holding' ? 1.12 : fan.role === 'error' ? 1.22 : 0.92;
        punctum.scale.setScalar((0.34 + fan.tension * 0.3 + fan.memoryTrace * 0.18) * (0.82 + globalWave * 0.2));
        const mat = punctum.material as THREE.MeshBasicMaterial;
        mat.color.copy(color).lerp(trunkColor, 0.18).lerp(new THREE.Color(fan.secondaryTint), 0.18);
        mat.opacity = Math.min(0.56, fan.opacity * roleGain * (0.68 + globalWave * 0.28));
      }
    });

    caudaTraces.forEach((trace, traceIndex) => {
      const color = new THREE.Color(trace.tint);
      for (let punctaIndex = 0; punctaIndex < CAUDA_TRACE_PUNCTA; punctaIndex += 1) {
        const punctum = caudaPunctaRefs.current[traceIndex * CAUDA_TRACE_PUNCTA + punctaIndex];
        if (!punctum) continue;
        const base = (punctaIndex + 1) / (CAUDA_TRACE_PUNCTA + 1);
        const travel = reducedMotion
          ? base
          : (base - time * Math.max(0.018, trace.beadSpeed * 0.09) + trace.flowDelay) % 1;
        punctum.position.copy(trace.curve.getPointAt(clamp01(travel < 0 ? travel + 1 : travel)));
        punctum.scale.setScalar((0.4 + trace.memoryStrength * 0.35) * (0.82 + globalWave * 0.24));
        const mat = punctum.material as THREE.MeshBasicMaterial;
        mat.color.copy(color).lerp(trunkColor, 0.2);
        mat.opacity = Math.min(0.58, trace.opacity * (0.76 + trace.memoryStrength * 0.48) * (0.66 + globalWave * 0.3));
      }
    });
  });

  if (activeSignals.length === 0) return null;

  return (
    <group renderOrder={11}>
      {trunkGeometry ? (
        <mesh ref={trunkRef} geometry={trunkGeometry} frustumCulled={false} renderOrder={10}>
          <meshBasicMaterial
            color={trunkColor}
            transparent
            opacity={0}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      ) : null}
      {trunkCurve
        ? Array.from({ length: BEAD_COUNT }, (_, index) => (
            <mesh
              key={`anatomical-conductor-bead-${index}`}
              ref={(mesh) => {
                if (mesh) beadRefs.current[index] = mesh;
              }}
              renderOrder={12}
            >
              <sphereGeometry args={[0.017, 12, 10]} />
              <meshBasicMaterial
                color={trunkColor}
                transparent
                opacity={0}
                blending={THREE.AdditiveBlending}
                depthWrite={false}
              />
            </mesh>
          ))
        : null}
      {rootFans.map((fan, index) => (
        <mesh
          key={`anatomical-root-fan-${fan.key}`}
          ref={(mesh) => {
            if (mesh) fanRefs.current[index] = mesh;
          }}
          geometry={fan.geometry}
          frustumCulled={false}
          renderOrder={11}
        >
          <meshBasicMaterial
            color={fan.tint}
            transparent
            opacity={0}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      ))}
      {caudaTraces.map((trace, index) => (
        <mesh
          key={`cauda-memory-trace-${trace.id}`}
          ref={(mesh) => {
            if (mesh) caudaRefs.current[index] = mesh;
          }}
          geometry={trace.geometry}
          frustumCulled={false}
          renderOrder={10}
        >
          <meshBasicMaterial
            color={trace.tint}
            transparent
            opacity={0}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      ))}
      {rootFans.flatMap((fan, fanIndex) =>
        Array.from({ length: ROOT_FAN_PUNCTA }, (_, punctaIndex) => {
          const index = fanIndex * ROOT_FAN_PUNCTA + punctaIndex;
          return (
            <mesh
              key={`anatomical-root-puncta-${fan.key}-${punctaIndex}`}
              ref={(mesh) => {
                if (mesh) fanPunctaRefs.current[index] = mesh;
              }}
              renderOrder={12}
            >
              <sphereGeometry args={[0.0105, 9, 7]} />
              <meshBasicMaterial
                color={fan.tint}
                transparent
                opacity={0}
                blending={THREE.AdditiveBlending}
                depthWrite={false}
              />
            </mesh>
          );
        }),
      )}
      {caudaTraces.flatMap((trace, traceIndex) =>
        Array.from({ length: CAUDA_TRACE_PUNCTA }, (_, punctaIndex) => {
          const index = traceIndex * CAUDA_TRACE_PUNCTA + punctaIndex;
          return (
            <mesh
              key={`cauda-trace-puncta-${trace.id}-${punctaIndex}`}
              ref={(mesh) => {
                if (mesh) caudaPunctaRefs.current[index] = mesh;
              }}
              renderOrder={12}
            >
              <sphereGeometry args={[0.0115, 9, 7]} />
              <meshBasicMaterial
                color={trace.tint}
                transparent
                opacity={0}
                blending={THREE.AdditiveBlending}
                depthWrite={false}
              />
            </mesh>
          );
        }),
      )}
      {activeSignals.map((signal) => (
        <group key={`anatomical-vertebra-${signal.seatIndex}`} position={signal.anchorLocal}>
          <mesh
            ref={(mesh) => {
              if (mesh) socketRefs.current[signal.seatIndex] = mesh;
            }}
            position={[0, 0, 0.086]}
            renderOrder={12}
          >
            <torusGeometry args={[0.088, 0.0042, 7, 36]} />
            <meshBasicMaterial
              color={signal.tint}
              transparent
              opacity={0}
              blending={THREE.AdditiveBlending}
              depthWrite={false}
              side={THREE.DoubleSide}
            />
          </mesh>
          <mesh
            ref={(mesh) => {
              if (mesh) nodeRefs.current[signal.seatIndex] = mesh;
            }}
            position={[0, 0, 0.108]}
            renderOrder={13}
          >
            <sphereGeometry args={[0.018, 12, 10]} />
            <meshBasicMaterial
              color={signal.tint}
              transparent
              opacity={0}
              blending={THREE.AdditiveBlending}
              depthWrite={false}
            />
          </mesh>
          {[-1, 1].map((side, sideIndex) => (
            <mesh
              key={`anatomical-vertebra-lateral-${signal.seatIndex}-${side}`}
              ref={(mesh) => {
                if (mesh) lateralRefs.current[signal.seatIndex * 2 + sideIndex] = mesh;
              }}
              position={[side * 0.112, 0, 0.1]}
              renderOrder={13}
            >
              <sphereGeometry args={[0.012, 10, 8]} />
              <meshBasicMaterial
                color={signal.tint}
                transparent
                opacity={0}
                blending={THREE.AdditiveBlending}
                depthWrite={false}
              />
            </mesh>
          ))}
        </group>
      ))}
    </group>
  );
}
