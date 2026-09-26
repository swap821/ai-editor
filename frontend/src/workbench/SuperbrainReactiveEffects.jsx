/**
 * SuperbrainReactiveEffects — product-only 3D reactions to the GAGOS agent loop.
 *
 * This component is injected into <WorkspaceCanvas> from SuperbrainApp.jsx, so it
 * shares the same R3F context as the being but lives outside the ported lab files.
 * It adds:
 *   - cloud_route  → jagged lightning arc up the spine
 *   - semantic verification  → aurora bloom around the cortex
 *   - semantic worker posture → bounded motes at vertebra seats
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Line } from '@react-three/drei';
import * as THREE from 'three';
import {
  subscribeSwarmHUD,
} from '../superbrain/lib/swarmHUDStore';
import { subscribeCognition } from '../superbrain/lib/cognitionBus';
import { getKnownTrails } from '../superbrain/lib/aiosAdapter';
import {
  copyBodyGroupWorldMatrix,
  fuseSpinePoint,
  getSpineFusion,
  getBrainDockScale,
  getCortexAnchor,
} from '../superbrain/lib/spineFusionBus';
import { SEGMENT_ANCHORS } from '../superbrain/lib/spineAnatomy';
import { deriveAnatomicalConductor } from '../superbrain/lib/anatomicalConductor';
import { deriveLivingOrchestration } from '../superbrain/lib/livingOrchestrator';
import { useTabStore } from '../superbrain/lib/tabStore';
import { useQualityTier } from '../superbrain/components/QualityTierProvider';
import {
  getAuroraState,
  setAuroraIntensity,
  subscribeAurora,
} from './verifyAuroraBridge';
import {
  getSpineFlashState,
  subscribeSpineFlash,
} from './spineFlashBridge';
import { useBeingPresentation } from '../livingMirror/being/useBeingPresentation';
import {
  deriveSemanticEffectTransition,
  pruneExpiredWorkerMotes,
} from '../livingMirror/being/semanticEffects';
import { derivePhysicalSnapshot } from '../livingMirror/being/physicalSnapshot';
import { derivePhysicalMaterialization } from '../livingMirror/being/physicalMaterialization';
import { useReducedMotion } from '../superbrain/lib/reducedMotion';
import { updateLineGeometryPoints } from './lineGeometry';
import {
  createComposerFrameDrawCallSampler,
  recordFrontendSceneDiagnostic,
} from '../livingMirror/observability/frontendMetrics';
import {
  advanceCortexAttentionPulse,
  advanceCortexAttentionSpring,
  CORTEX_COMPOSER_INTAKE_LOCAL,
  createCortexAttentionPulseState,
  createCortexAttentionSpring,
  deriveCortexAttentionPaths,
  retargetCortexAttentionPulse,
  retargetCortexAttentionSpring,
} from './cortexAttentionPaths';
import { copyBodyGroupPoseMatrix } from './bodyEffectsFrame';
import { reconcileWorkerSeats } from './workerSeatRegistry';

const CLOUD_COLORS = {
  bedrock: new THREE.Color('#f5c542'),
  gemini: new THREE.Color('#4aa8ff'),
  default: new THREE.Color('#ffffff'),
};

function providerColor(provider) {
  return CLOUD_COLORS[provider] ?? CLOUD_COLORS.default;
}

/** @param {THREE.Vector3[]} points @returns {import('./cortexAttentionPaths').CortexCurrentPath} */
function toCortexAttentionPath(points) {
  return /** @type {import('./cortexAttentionPaths').CortexCurrentPath} */ (
    points.map(({ x, y, z }) => [x, y, z])
  );
}

function syncCortexAttentionGeometry(spring, scratchPoints, geometry) {
  for (let index = 0; index < scratchPoints.length; index += 1) {
    const offset = index * 3;
    scratchPoints[index].set(
      spring.positions[offset],
      spring.positions[offset + 1],
      spring.positions[offset + 2],
    );
  }
  updateLineGeometryPoints(geometry, scratchPoints);
}

/**
 * @param {{ points: THREE.Vector3[], color: string | THREE.Color, lineWidth: number,
 *   opacity: number, reducedMotion: boolean, inputAttention?: boolean }} props
 */
function CortexAttentionCurrent({ points, color, lineWidth, opacity, reducedMotion, inputAttention = false }) {
  const lineRef = useRef(null);
  const pulseMeshRef = useRef(null);
  const pulsePositionRef = useRef(new THREE.Vector3());
  const [pulseState] = useState(() => createCortexAttentionPulseState());
  const pulsePathRef = useRef(new THREE.LineCurve3(points[0].clone(), points[points.length - 1].clone()));
  const [buffer] = useState(() => {
    const initialPath = toCortexAttentionPath(points);
    return {
      spring: createCortexAttentionSpring([initialPath]),
      initialPoints: points.map((point) => point.clone()),
      scratchPoints: points.map((point) => point.clone()),
    };
  });

  useLayoutEffect(() => {
    const { spring } = buffer;
    retargetCortexAttentionSpring(spring, [toCortexAttentionPath(points)], reducedMotion);
    if (inputAttention) {
      pulsePathRef.current.v1.copy(points[0]);
      pulsePathRef.current.v2.copy(points[points.length - 1]);
    }
    retargetCortexAttentionPulse(pulseState, inputAttention, reducedMotion);
    if (pulseMeshRef.current) pulseMeshRef.current.visible = pulseState.direction !== 'hidden';
    if (reducedMotion && lineRef.current?.geometry) {
      syncCortexAttentionGeometry(spring, buffer.scratchPoints, lineRef.current.geometry);
    }
  }, [buffer, inputAttention, points, pulseState, reducedMotion]);

  useFrame((_, delta) => {
    const line = lineRef.current;
    if (line?.geometry && advanceCortexAttentionSpring(buffer.spring, delta)) {
      syncCortexAttentionGeometry(buffer.spring, buffer.scratchPoints, line.geometry);
    }

    const pulse = pulseMeshRef.current;
    if (!pulse) return;
    const progress = advanceCortexAttentionPulse(pulseState, delta, reducedMotion);
    if (progress === null) {
      pulse.visible = false;
      return;
    }
    pulsePathRef.current.getPoint(THREE.MathUtils.smoothstep(progress, 0, 1), pulsePositionRef.current);
    pulse.position.copy(pulsePositionRef.current);
    const returning = pulseState.direction === 'outbound';
    pulse.scale.setScalar(returning ? 0.024 + progress * 0.028 : 0.036 + progress * 0.034);
    if (pulse.material instanceof THREE.MeshBasicMaterial) {
      pulse.material.opacity = returning ? 0.48 * progress : 0.82 + progress * 0.14;
    }
  });

  return (
    <>
    <Line
      ref={lineRef}
      data-testid="cortex-current"
      points={buffer.initialPoints}
      color={color}
      lineWidth={inputAttention ? Math.max(2, lineWidth) : lineWidth}
      frustumCulled={false}
      depthTest={!inputAttention}
      renderOrder={inputAttention ? 10 : 0}
      transparent
      opacity={inputAttention ? Math.max(0.64, opacity) : opacity}
    />
      <mesh
        ref={pulseMeshRef}
        data-testid="cortex-attention-pulse"
        name="cortex-attention-pulse"
        position={points[0].toArray()}
        scale={0.036}
        renderOrder={11}
        frustumCulled={false}
      >
        <sphereGeometry args={[1, 16, 16]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={0.9}
          depthTest={false}
          depthWrite={false}
          toneMapped={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
    </>
  );
}

const CLOUD_THICKNESS = {
  bedrock: 4,
  gemini: 3,
  default: 2,
};

function providerThickness(provider) {
  return CLOUD_THICKNESS[provider] ?? CLOUD_THICKNESS.default;
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
const MAX_LIGHTNINGS = 4;
const MAX_MOTES = 8;
const MAX_TERMINAL_WORKER_EXPIRIES = 256;
const SPINE_FLASH_DURATION_S = 1.6;

const CONDUCTOR_COLORS = {
  active: '#8dffd1',
  waiting: '#6f9dff',
  held: '#ffb06e',
  reabsorbing: '#a9fff3',
};

const CORTEX_POSTURE_COLORS = {
  rest: '#7bf5fb',
  arrive: '#b06eff',
  attention: '#7bf5fb',
  conduct: '#54f0a0',
  verify: '#54f0a0',
  unverified: '#9e78f5',
  recover: '#ffb454',
  stopped: '#ff5f6d',
};

const MEMORY_LAYER_COLORS = {
  recalled: '#6f9dff',
  promoted: '#a9fff3',
  reflex: '#54f0a0',
};

const VERIFICATION_FIELD_COLORS = {
  pending: '#ffb454',
  pass: '#2fffa1',
  fail: '#ff5f6d',
  unverified: '#9e78f5',
};

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

// Keep the initial Drei <Line> geometry at the same bounded size as the
// ref-mutated frame-loop scratch pool. A shorter initial point list causes
// BufferGeometry.setFromPoints to warn and reallocate when the flash reaches
// the middle of the spine, even though the visual effect is capped.
const FLASH_POINT_COUNT = BEAD_HALF_ANCHORS * 4 + 1;

function beadPointsForProgress(progress) {
  const n = SEGMENT_ANCHORS.length;
  const center = progress * (n - 1);
  const start = Math.max(0, center - BEAD_HALF_ANCHORS);
  const end = Math.min(n - 1, center + BEAD_HALF_ANCHORS);
  const points = [];
  for (let s = 0; s < FLASH_POINT_COUNT; s += 1) {
    const t = start + (end - start) * (s / (FLASH_POINT_COUNT - 1));
    points.push(sampleWorldPosition(t));
  }
  return points;
}

// The travelling spine bead is the one product-owned effect that can touch
// the frame loop continuously. Keep its hot path on a fixed scratch pool so a
// long cloud-route flash does not create short-lived Vector3/array garbage on
// every frame. The existing allocating helpers remain for initial JSX props
// and event-time construction, where they are not frame-bound.
function anchorWorldPositionInto(index, target, dockScale) {
  const clamped = Math.min(SEGMENT_ANCHORS.length - 1, Math.max(0, index));
  const raw = SEGMENT_ANCHORS[clamped];
  const fusion = getSpineFusion();
  if (fusion.ready) {
    target.set(
      raw.x * fusion.spineScale + fusion.weld[0],
      raw.y * fusion.spineScale + fusion.weld[1],
      raw.z * fusion.spineScale + fusion.weld[2],
    );
  } else {
    target.set(raw.x, raw.y, raw.z);
  }
  return target.multiplyScalar(dockScale);
}

function sampleWorldPositionInto(t, target, start, end, dockScale) {
  const i0 = Math.floor(t);
  const frac = t - i0;
  anchorWorldPositionInto(i0, start, dockScale);
  anchorWorldPositionInto(i0 + 1, end, dockScale);
  return target.lerpVectors(start, end, frac);
}

function beadPointsForProgressInto(progress, points, start, end, dockScale) {
  const n = SEGMENT_ANCHORS.length;
  const center = progress * (n - 1);
  const from = Math.max(0, center - BEAD_HALF_ANCHORS);
  const to = Math.min(n - 1, center + BEAD_HALF_ANCHORS);
  for (let s = 0; s < points.length; s += 1) {
    const t = from + (to - from) * (s / (points.length - 1));
    sampleWorldPositionInto(t, points[s], start, end, dockScale);
  }
  return points;
}

function getStableRandom(seed) {
  let t = (seed + 0x6d2b79f5) >>> 0;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

/**
 * @param {{ presentationOverride?: import('../livingMirror/being/semanticKernel').BeingPresentation | null,
 *   physicalOverride?: import('../livingMirror/being/physicalSnapshot').PhysicalSnapshot | null,
 *   tabSnapshotOverride?: import('../superbrain/lib/tabStore').TabSnapshot | null,
 *   inputDraftPresent?: boolean }} [props]
 */
export default function SuperbrainReactiveEffects({ presentationOverride = null, physicalOverride = null, tabSnapshotOverride = null, inputDraftPresent = false } = {}) {
  const liveBeing = useBeingPresentation();
  // The override is a development/test inspection seam only. Production uses
  // the live presentation projection; the gallery never mutates a store or
  // claims that a fixture represents backend truth.
  const being = presentationOverride ?? liveBeing;
  const physical = useMemo(
    () => physicalOverride ?? derivePhysicalSnapshot(being),
    [being, physicalOverride],
  );
  const { tier } = useQualityTier();
  const storedTabSnapshot = useTabStore();
  // Deterministic, render-only fixtures let the dev gallery exercise a whole
  // body-to-seat posture without writing the live tab or mirror stores.
  const { tabs, focusId, attention, panels = [] } = tabSnapshotOverride ?? storedTabSnapshot;
  const orchestration = useMemo(
    () => deriveLivingOrchestration({ tabs, focusId, attention }),
    [tabs, focusId, attention],
  );
  // A permission decision is the being's current point of attention even when
  // the underlying work tab remains the keyboard/workspace focus. Keep those
  // identities separate: the body may turn toward the held approval surface
  // without stealing focus from the work the operator is reviewing.
  const heldApprovalSeat = physical.membrane.state === 'held'
    ? tabs.find((tab) => tab.kind === 'approval'
      && tab.lifecycle !== 'retracting'
      && Number.isInteger(tab.seatIndex)
      && tab.seatIndex >= 0
      && tab.seatIndex < SEGMENT_ANCHORS.length)?.seatIndex ?? null
    : null;
  const attentionOrchestration = useMemo(
    () => heldApprovalSeat === null
      ? orchestration
      : { ...orchestration, activeSeatIndex: heldApprovalSeat },
    [heldApprovalSeat, orchestration],
  );
  const conductor = useMemo(
    () => deriveAnatomicalConductor({ tabs, orchestration: attentionOrchestration }),
    [tabs, attentionOrchestration],
  );
  const conductorPathPoints = useMemo(
    () => conductor.conductingSeatIndexes.map((seatIndex) => anchorWorldPosition(seatIndex)),
    [conductor.conductingSeatIndexes],
  );
  const conductorSeatSignals = useMemo(
    () => conductor.vertebrae.filter((signal) => signal.role !== 'idle'),
    [conductor.vertebrae],
  );
  const physicalSurfaces = useMemo(
    () => derivePhysicalMaterialization({ tabs, conductor, focusId }),
    [tabs, conductor, focusId],
  );
  const physicalSurfaceBySeat = useMemo(
    () => new Map(
      physicalSurfaces
        .filter((surface) => typeof surface.seatIndex === 'number')
        .map((surface) => [surface.seatIndex, surface]),
    ),
    [physicalSurfaces],
  );
  const actionPresentationStopped = physical.membrane.state === 'stopped';
  const coherenceSemantics = physical.coherencePhysics;
  const reducedMotion = useReducedMotion();
  const [lightnings, setLightnings] = useState([]);
  const [motes, setMotes] = useState({});
  const [stigmergyTrails, setStigmergyTrails] = useState(() => [...(getKnownTrails() || [])]);
  const motesRef = useRef({});
  const [aurora, setAurora] = useState(getAuroraState);
  const [spineFlash, setSpineFlash] = useState(getSpineFlashState);
  const lastCloudIndices = useRef(new Set());
  const moteNodesRef = useRef({});
  const branchLineNodesRef = useRef({});
  const branchScratchRef = useRef({});
  const moteAnglesRef = useRef({});
  // Keep a product-owned mutable animation snapshot. The bridge state is
  // replaced on event boundaries; the frame loop must not spread a new object
  // on every tick just to decay intensity.
  const auroraAnimationRef = useRef({ ...getAuroraState() });
  const auroraMeshRef = useRef(null);
  const auroraMaterialRef = useRef(null);
  const spineFlashAnimationRef = useRef(getSpineFlashState());
  const spineFlashElapsedRef = useRef(0);
  const spineFlashLineRef = useRef(null);
  const spineFlashBeadRef = useRef(null);
  const spineFlashScratchRef = useRef(null);
  const sceneDiagnosticElapsedRef = useRef(0);
  const rendererInfoRef = useRef(null);
  const composerDrawCallSamplerRef = useRef(null);
  if (spineFlashScratchRef.current === null) {
    spineFlashScratchRef.current = {
      points: Array.from({ length: FLASH_POINT_COUNT }, () => new THREE.Vector3()),
      start: new THREE.Vector3(),
      end: new THREE.Vector3(),
      sample: new THREE.Vector3(),
    };
  }
  const previousBeingRef = useRef(null);
  const terminalWorkerExpiryRef = useRef(new Map());
  const semanticPulseRef = useRef(0);
  const semanticPulseMeshRef = useRef(null);
  const semanticPulseMaterialRef = useRef(null);
  const actionPresentationStoppedRef = useRef(actionPresentationStopped);
  const reducedMotionRef = useRef(reducedMotion);
  const coherenceSemanticsRef = useRef(coherenceSemantics);

  useEffect(() => () => {
    composerDrawCallSamplerRef.current?.dispose();
    composerDrawCallSamplerRef.current = null;
    rendererInfoRef.current = null;
  }, []);

  useEffect(() => {
    actionPresentationStoppedRef.current = actionPresentationStopped;
  }, [actionPresentationStopped]);

  useEffect(() => {
    reducedMotionRef.current = reducedMotion;
  }, [reducedMotion]);

  useEffect(() => {
    coherenceSemanticsRef.current = coherenceSemantics;
  }, [coherenceSemantics]);

  // The presentation kernel is the source for semantic organism cues in this
  // product-owned R3F seam. Raw buses remain available to evidence-specific
  // projections, but posture transitions do not branch on event strings here.
  useEffect(() => {
    const transition = deriveSemanticEffectTransition(previousBeingRef.current, being);
    previousBeingRef.current = being;
    if (!actionPresentationStopped && !reducedMotion && transition.actionPulse) semanticPulseRef.current = Math.max(semanticPulseRef.current, 0.72);
    if (!actionPresentationStopped && !reducedMotion && transition.enteredSignals.includes('verification-pass')) setAuroraIntensity(1, 'pass');
    if (!actionPresentationStopped && !reducedMotion && transition.enteredSignals.includes('verification-fail')) setAuroraIntensity(1, 'fail');
  }, [actionPresentationStopped, being, reducedMotion]);

  useEffect(() => {
    if (!actionPresentationStopped) return;
    // Stop is a presentation boundary: remove transient action effects and
    // freeze their local bridges while preserving workers and evidence trails.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the stop boundary must synchronously clear an already-mounted transient.
    setLightnings([]);
    setAuroraIntensity(0, 'caution');
    setSpineFlash({ intensity: 0, progress: 1 });
    spineFlashAnimationRef.current = { intensity: 0, progress: 1 };
    spineFlashElapsedRef.current = SPINE_FLASH_DURATION_S;
    semanticPulseRef.current = 0;
  }, [actionPresentationStopped]);

  useEffect(() => {
    if (!reducedMotion) return;
    // Reduced motion keeps the measured state and DOM explanation, but drops
    // product-owned travel, bloom, and pulse effects. The underlying canvas
    // receives the same preference through its existing shared store; this
    // seam must not reintroduce motion around it.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- clear already-mounted transient effects at the preference boundary.
    setLightnings([]);
    setAuroraIntensity(0, 'caution');
    setSpineFlash({ intensity: 0, progress: 1 });
    spineFlashAnimationRef.current = { intensity: 0, progress: 1 };
    spineFlashElapsedRef.current = SPINE_FLASH_DURATION_S;
    semanticPulseRef.current = 0;
  }, [reducedMotion]);

  useEffect(() => {
    // Sync local React state with the product-only aurora bridge so the
    // sphere mounts/unmounts and animates correctly.
    const unsub = subscribeAurora((next) => {
      auroraAnimationRef.current.intensity = next.intensity;
      auroraAnimationRef.current.verdict = next.verdict;
      setAurora(next);
    });
    return unsub;
  }, []);

  useEffect(() => {
    // Sync local React state with the product-only spine-flash bridge.
    const unsub = subscribeSpineFlash((next) => {
      spineFlashAnimationRef.current = next;
      if (reducedMotionRef.current) {
        setSpineFlash({ intensity: 0, progress: 1 });
        spineFlashAnimationRef.current = { intensity: 0, progress: 1 };
        spineFlashElapsedRef.current = SPINE_FLASH_DURATION_S;
        return;
      }
      if (next.intensity > 0) spineFlashElapsedRef.current = 0;
      setSpineFlash(next);
    });
    return unsub;
  }, []);

  useEffect(() => {
    // Cloud-route lightning.
    const unsubSwarm = subscribeSwarmHUD((state) => {
      const current = new Set(state.cloudIndices);
      if (actionPresentationStoppedRef.current || reducedMotionRef.current) {
        lastCloudIndices.current = current;
        return;
      }
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
              thickness: providerThickness(state.provider ?? 'default'),
              born: performance.now(),
            });
          }
          return next.slice(-MAX_LIGHTNINGS);
        });
      }
      lastCloudIndices.current = current;
    });

    // Verify-pass aurora and Stigmergy trails/scars updates.
    // getKnownTrails might return the same array reference so we spread.
    const unsubCognition = subscribeCognition((event) => {
      if (event.type === 'telemetry') {
        setStigmergyTrails([...(getKnownTrails() || [])]);
      }
    });

    return () => {
      unsubSwarm();
      unsubCognition();
    };
  }, []);

  // Temporary worker motes are keyed by admitted identity so roster changes do
  // not transfer a worker's seat, orbit, or pooled scene nodes to another.
  // Terminal states get a short visual reabsorption window.
  useEffect(() => {
    const branches = physical.branches;
    const now = performance.now();
    setMotes((prev) => {
      const next = Object.create(null);
      const assignments = reconcileWorkerSeats(
        Object.entries(prev).map(([workerId, mote]) => ({ workerId, seat: mote.seat })),
        branches.map((branch) => branch.workerId),
        MAX_MOTES,
      );
      const seatByWorkerId = new Map(assignments.map(({ workerId, seat }) => [workerId, seat]));
      branches.slice(0, MAX_MOTES).forEach((branch) => {
        const { visual: visualState, terminal } = branch;
        const { workerId } = branch;
        const key = workerId;
        const existing = prev[key];
        if (!terminal) terminalWorkerExpiryRef.current.delete(key);
        const rememberedTerminalAt = terminalWorkerExpiryRef.current.get(key) ?? null;
        const terminalAt = existing?.terminalAt ?? rememberedTerminalAt ?? (terminal ? now : null);
        if (terminal && terminalAt !== null && !terminalWorkerExpiryRef.current.has(key)) {
          terminalWorkerExpiryRef.current.set(key, terminalAt);
          while (terminalWorkerExpiryRef.current.size > MAX_TERMINAL_WORKER_EXPIRIES) {
            const oldestWorkerId = terminalWorkerExpiryRef.current.keys().next().value;
            terminalWorkerExpiryRef.current.delete(oldestWorkerId);
          }
        }
        if (terminalAt !== null && now - terminalAt >= 1600) return;
        const seat = seatByWorkerId.get(key);
        if (seat === undefined) return;
        const raw = SEGMENT_ANCHORS[seat];
        const fused = existing?.origin ?? new THREE.Vector3(...fuseSpinePoint([raw.x, raw.y, raw.z]));
        const angle = existing?.angle ?? Math.random() * Math.PI * 2;
        next[key] = {
          seat,
          origin: fused,
          angle,
          speed: existing?.speed ?? 0.5 + Math.random() * 0.4,
          radius: existing?.radius ?? 0.18 + Math.random() * 0.06,
          visualState,
          terminalAt,
        };
        moteAnglesRef.current[key] = angle;
      });
      for (const key of Object.keys(moteAnglesRef.current)) {
        if (!next[key]) delete moteAnglesRef.current[key];
      }
      return Object.fromEntries(Object.entries(next).slice(0, MAX_MOTES));
    });
  }, [physical]);

  // Expire transient effects on a coarse timer. Their visual movement is
  // handled by refs below; React only reconciles lifecycle changes, never each
  // rendered frame.
  useEffect(() => {
    if (lightnings.length === 0) return undefined;
    const timer = window.setInterval(() => {
      const now = performance.now();
      setLightnings((prev) => {
        const next = prev.filter((lightning) => now - lightning.born < 900);
        return next.length === prev.length ? prev : next;
      });
    }, 100);
    return () => window.clearInterval(timer);
  }, [lightnings.length]);

  // Terminal workers must reabsorb even when the mirror goes quiet after the
  // return/dissolve event. This coarse lifecycle timer never drives motion;
  // it only removes expired React entities from the bounded visual pool.
  const hasTerminalWorkerMotes = Object.values(motes).some((mote) => mote.terminalAt !== null);
  useEffect(() => {
    if (!hasTerminalWorkerMotes) return undefined;
    const timer = window.setInterval(() => {
      const now = performance.now();
      setMotes((prev) => pruneExpiredWorkerMotes(prev, now));
    }, 250);
    return () => window.clearInterval(timer);
  }, [hasTerminalWorkerMotes]);

  const coherenceOpacity = coherenceSemantics.opacity;
  const cortexPostureOpacity = Math.min(
    0.11,
    (0.028 + physical.cortex.activity * 0.045 + physical.cortex.convergence * 0.025) * coherenceOpacity,
  );
  const conductorHeld = conductor.hold
    || physical.membrane.state === 'held'
    || physical.membrane.state === 'refused'
    || physical.conductor.posture === 'held';
  const conductorStopped = actionPresentationStopped || physical.conductor.posture === 'stopped';
  const conductorLineOpacity = coherenceOpacity * (conductorStopped ? 0.18 : conductorHeld ? 0.4 : 0.58);
  const conductorLineWidth = tier === 'high' ? 1.8 : tier === 'medium' ? 1.35 : 1;

  useFrame((state, delta) => {
    const info = state?.gl?.info ?? null;
    if (info !== rendererInfoRef.current) {
      composerDrawCallSamplerRef.current?.dispose();
      rendererInfoRef.current = info ?? null;
      composerDrawCallSamplerRef.current = createComposerFrameDrawCallSampler(info);
    }
    if (actionPresentationStopped || reducedMotionRef.current) {
      semanticPulseRef.current = 0;
      if (semanticPulseMaterialRef.current) {
        semanticPulseMaterialRef.current.opacity = actionPresentationStopped ? 0 : cortexPostureOpacity;
      }
      return;
    }
    const coherence = coherenceSemanticsRef.current;
    // Decay transient effects through refs and native scene objects. React
    // state changes only when a real cognition event arrives, not per frame.
    const currentAurora = auroraAnimationRef.current;
    if (currentAurora.intensity > 0) {
      const intensity = Math.max(0, currentAurora.intensity - delta * 0.9);
      currentAurora.intensity = intensity;
      if (auroraMeshRef.current) auroraMeshRef.current.scale.setScalar(0.22 + intensity * 0.18);
      if (auroraMaterialRef.current) auroraMaterialRef.current.opacity = intensity * 0.14 * coherence.opacity;
    }

    const flash = spineFlashAnimationRef.current;
    if (flash.intensity > 0 || flash.progress < 1) {
      // Older/incomplete projections may retain a historical flash, but it
      // must conduct more slowly and at lower opacity than fresh truth.
      spineFlashElapsedRef.current += delta * Math.max(0.12, coherence.motionScale);
      const progress = Math.min(1, spineFlashElapsedRef.current / SPINE_FLASH_DURATION_S);
      const intensity = Math.max(0, 1 - spineFlashElapsedRef.current / (SPINE_FLASH_DURATION_S * 0.85));
      spineFlashAnimationRef.current.intensity = intensity;
      spineFlashAnimationRef.current.progress = progress;
      if (spineFlashLineRef.current) {
        const scratch = spineFlashScratchRef.current;
        beadPointsForProgressInto(
          progress,
          scratch.points,
          scratch.start,
          scratch.end,
          getBrainDockScale(),
        );
        updateLineGeometryPoints(spineFlashLineRef.current.geometry, scratch.points);
        spineFlashLineRef.current.material.opacity = intensity * 0.85 * coherence.opacity;
      }
      if (spineFlashBeadRef.current) {
        const scratch = spineFlashScratchRef.current;
        sampleWorldPositionInto(
          progress * (SEGMENT_ANCHORS.length - 1),
          scratch.sample,
          scratch.start,
          scratch.end,
          getBrainDockScale(),
        );
        spineFlashBeadRef.current.position.copy(scratch.sample);
        spineFlashBeadRef.current.material.opacity = intensity * 0.45 * coherence.opacity;
      }
    }

    // Orbit motes by mutating pooled mesh nodes. No React state update occurs
    // in this frame path, and the bounded pool cannot grow with event history.
    for (const [workerId, m] of Object.entries(motesRef.current)) {
      const node = moteNodesRef.current[workerId];
      if (!node) continue;
      const motionScale = (m.visualState === 'held' ? 0 : m.visualState === 'conduct' ? 1 : 0.42)
        * coherence.motionScale;
      const angle = (moteAnglesRef.current[workerId] ?? m.angle) + m.speed * delta * motionScale;
      moteAnglesRef.current[workerId] = angle;
      const scale = getBrainDockScale();
      const radiusScale = m.visualState === 'bud' ? 0.32 : m.visualState === 'branch' ? 0.68 : 1;
      node.position.set(
        (m.origin.x + Math.cos(angle) * m.radius * radiusScale) * scale,
        m.origin.y * scale,
        (m.origin.z + Math.sin(angle) * m.radius * radiusScale) * scale,
      );
      const visualScale = m.visualState === 'held' ? 0.82 : m.visualState === 'conduct' ? 1.2 : 1;
      node.scale.setScalar(visualScale);

      const branchLine = branchLineNodesRef.current[workerId];
      if (branchLine?.geometry) {
        const scratch = branchScratchRef.current[workerId] ?? {
          points: [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()],
        };
        branchScratchRef.current[workerId] = scratch;
        scratch.points[0].copy(m.origin).multiplyScalar(scale);
        scratch.points[2].copy(node.position);
        scratch.points[1].lerpVectors(scratch.points[0], scratch.points[2], 0.5);
        updateLineGeometryPoints(branchLine.geometry, scratch.points);
        branchLine.material.opacity = (m.visualState === 'dissolved' ? 0.14 : m.visualState === 'held' ? 0.4 : 0.58) * coherence.opacity;
      }
    }
    semanticPulseRef.current = Math.max(0, semanticPulseRef.current - delta * 0.8);
    if (semanticPulseMeshRef.current) {
      semanticPulseMeshRef.current.scale.setScalar(0.24 + semanticPulseRef.current * 0.2);
    }
    if (semanticPulseMaterialRef.current) {
      semanticPulseMaterialRef.current.opacity = Math.min(
        0.14,
        cortexPostureOpacity + semanticPulseRef.current * 0.12 * coherence.opacity,
      );
    }
  });

  // EffectComposer takes render priority 1 and performs multiple WebGL draws.
  // Sample at priority 2 so this frame's aggregate is captured after its final
  // pass; renderer.info is reset once here, not once per internal pass.
  useFrame((state, delta) => {
    const drawCalls = composerDrawCallSamplerRef.current?.capture() ?? null;
    sceneDiagnosticElapsedRef.current += delta;
    if (sceneDiagnosticElapsedRef.current < 1) return;

    let sceneObjects = 0;
    state?.scene?.traverse?.(() => {
      sceneObjects += 1;
    });
    const info = state?.gl?.info;
    const workerMoteCount = Object.keys(motesRef.current).length;
    const lightningCount = lightnings.length;
    const materializationSurfaceCount = physicalSurfaces.length;
    const workerBranchCount = physical.branches.length;
    recordFrontendSceneDiagnostic({
      sceneObjects,
      drawCalls,
      geometries: info?.memory?.geometries ?? null,
      textures: info?.memory?.textures ?? null,
      transientPoolSize: workerMoteCount + lightningCount + (spineFlash.intensity > 0.01 ? 1 : 0) + (aurora.intensity > 0.01 ? 1 : 0),
      workerBranchCount,
      workerMoteCount,
      materializationSurfaceCount,
      lightningCount,
    });
    sceneDiagnosticElapsedRef.current = 0;
  }, 2);

  // Keep a ref in sync so useFrame can guard against empty-object churn.
  useEffect(() => {
    motesRef.current = motes;
  }, [motes]);

  const bodyEffectsGroupRef = useRef(null);
  const bodyGroupWorldMatrixRef = useRef(new THREE.Matrix4());
  const bodyEffectsPoseMatrixRef = useRef(new THREE.Matrix4());
  // These paths and motes are derived in body-group-local coordinates. The
  // product scene mounts them beside the body. Follow its live pose while
  // preserving authored effect-space sizing (the body root scale is already
  // represented by calibrated anchors and dock/fusion scale).
  useFrame(() => {
    const group = bodyEffectsGroupRef.current;
    if (!group || !copyBodyGroupWorldMatrix(bodyGroupWorldMatrixRef.current)) return;
    copyBodyGroupPoseMatrix(bodyGroupWorldMatrixRef.current, bodyEffectsPoseMatrixRef.current);
    group.matrix.copy(bodyEffectsPoseMatrixRef.current);
    group.matrixWorldNeedsUpdate = true;
  });

  const [cx, cy, cz] = getCortexAnchor();
  const brainDockScale = getBrainDockScale();
  const cortex = new THREE.Vector3(cx, cy, cz).multiplyScalar(brainDockScale);
  const cortexOriginX = cx * brainDockScale;
  const cortexOriginY = cy * brainDockScale;
  const cortexOriginZ = cz * brainDockScale;
  const cortexPostureColor = CORTEX_POSTURE_COLORS[physical.cortex.posture];
  const heldForApproval = physical.membrane.state === 'held';
  const cortexCurrentColor = heldForApproval ? CONDUCTOR_COLORS.held : cortexPostureColor;
  const attentionOnInput = inputDraftPresent && !heldForApproval;
  const focusedPanelSeat = panels.find((panel) => panel.open && panel.id === focusId)?.seatIndex;
  const focusSeatIndex = heldApprovalSeat ?? (Number.isInteger(focusedPanelSeat)
    ? focusedPanelSeat
    : conductor.activeSeatIndex);
  const cortexCurrentPaths = useMemo(() => {
    if (physical.cortex.posture === 'stopped') return [];
    const pathCount = attentionOnInput ? 1 : tier === 'high' ? 3 : tier === 'medium' ? 2 : 1;
    const target = attentionOnInput
      ? CORTEX_COMPOSER_INTAKE_LOCAL.map((value) => value * brainDockScale)
      : Number.isInteger(focusSeatIndex)
        ? anchorWorldPosition(focusSeatIndex).toArray()
        : null;
    return deriveCortexAttentionPaths({
      origin: [cortexOriginX, cortexOriginY, cortexOriginZ],
      target,
      activity: physical.cortex.activity,
      convergence: physical.cortex.convergence,
      count: pathCount,
      contactTarget: attentionOnInput,
    }).map((path) => path.map((point) => new THREE.Vector3(...point)));
  }, [attentionOnInput, brainDockScale, cortexOriginX, cortexOriginY, cortexOriginZ, focusSeatIndex, physical.cortex.activity, physical.cortex.convergence, physical.cortex.posture, tier]);
  const councilDissent = physical.signals.includes('council-dissent');
  const councilDissentPaths = useMemo(() => {
    if (!councilDissent || physical.cortex.posture === 'stopped') return [];
    const pathCount = tier === 'high' ? 3 : tier === 'medium' ? 2 : 1;
    const axes = [
      [0.84, 0.2, 0.34],
      [-0.58, 0.46, 0.32],
      [0.12, -0.58, 0.52],
    ];
    const cortexOrigin = new THREE.Vector3(cortex.x, cortex.y, cortex.z);
    return axes.slice(0, pathCount).map((axis, index) => {
      const origin = cortexOrigin.clone().add(new THREE.Vector3(axis[0] * 0.12, axis[1] * 0.12, axis[2] * 0.12));
      const nucleus = cortexOrigin.clone().add(new THREE.Vector3(axis[0] * (0.28 + index * 0.025), axis[1] * (0.28 + index * 0.025), axis[2] * (0.28 + index * 0.025)));
      const returnPath = cortexOrigin.clone().add(new THREE.Vector3(axis[0] * 0.17, axis[1] * 0.17, axis[2] * 0.17));
      return [origin, nucleus, returnPath];
    });
  }, [cortex.x, cortex.y, cortex.z, councilDissent, physical.cortex.posture, tier]);
  const auroraScale = 0.22 + aurora.intensity * 0.18;
  const memoryFieldColor = MEMORY_LAYER_COLORS[physical.memory.layer];
  const memoryFieldScale = physical.memory.layer === 'promoted'
    ? 1.08
    : physical.memory.layer === 'reflex'
      ? 0.9
      : 0.78;
  const memoryFieldPosition = [cortex.x - 0.16, cortex.y - 0.06, cortex.z + 0.035];
  
  const VERDICT_COLORS = {
    pass: '#2fffa1',
    fail: '#ff2f2f',
    caution: '#ffb454',
  };
  const auroraColor = VERDICT_COLORS[aurora.verdict] || VERDICT_COLORS.pass;
  const verificationState = physical.verification.state;
  const verificationFieldColor = VERIFICATION_FIELD_COLORS[verificationState] ?? '#ffb454';
  const verificationFieldScale = verificationState === 'pass' ? 1.05 : verificationState === 'fail' ? 0.78 : verificationState === 'unverified' ? 0.82 : 0.9;
  const verificationFieldOpacity = verificationState === 'pass' ? 0.4 : verificationState === 'fail' ? 0.32 : verificationState === 'unverified' ? 0.16 : 0.26;
  const membraneColors = {
    held: '#ffb454',
    refused: '#ff8c69',
    stopped: '#ff5f6d',
  };
  const membraneColor = membraneColors[physical.membrane.state] ?? '#ffb454';
  const membraneOpacity = physical.membrane.state === 'stopped' ? 0.46 : 0.34;

  return (
    <group ref={bodyEffectsGroupRef} matrixAutoUpdate={false} name="superbrain-reactive-effects">
      {!actionPresentationStopped && lightnings.map((l) => (
        <Line
          key={l.id}
          points={l.points}
          color={l.color}
          lineWidth={l.thickness}
          transparent
          opacity={0.9 * coherenceOpacity}
        />
      ))}

      {/* First-cloud-route spine flash: a bright bead travelling down the spine. */}
      {!actionPresentationStopped && spineFlash.intensity > 0.01 && (
        <group name="spine-flash">
          <Line
            ref={spineFlashLineRef}
            data-testid="spine-flash"
            points={beadPointsForProgress(spineFlash.progress)}
            color="#e0ffff"
            lineWidth={5}
            frustumCulled={false}
            transparent
            opacity={spineFlash.intensity * 0.85 * coherenceOpacity}
          />
          <mesh
            ref={spineFlashBeadRef}
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
              opacity={spineFlash.intensity * 0.45 * coherenceOpacity}
              depthWrite={false}
              blending={THREE.AdditiveBlending}
            />
          </mesh>
        </group>
      )}

      {/* Verify-pass aurora: a soft, transient bloom around the cortex. */}
      {!actionPresentationStopped && aurora.intensity > 0.01 && (
        <mesh
          ref={auroraMeshRef}
          data-testid="verify-aurora"
          position={cortex}
          scale={[auroraScale, auroraScale, auroraScale]}
        >
          <sphereGeometry args={[1, 32, 32]} />
          <meshBasicMaterial
            ref={auroraMaterialRef}
            color={auroraColor}
            transparent
            opacity={aurora.intensity * 0.14 * coherenceOpacity}
            depthWrite={false}
            side={THREE.DoubleSide}
            blending={THREE.AdditiveBlending}
          />
        </mesh>
      )}

      {!conductorStopped && conductorPathPoints.length > 1 && (
        <Line
          data-testid="physical-conductor-path"
          points={conductorPathPoints}
          color={conductorHeld ? CONDUCTOR_COLORS.held : conductor.trunkTint}
          lineWidth={conductorLineWidth}
          frustumCulled={false}
          transparent
          opacity={conductorLineOpacity}
        />
      )}

      {cortexCurrentPaths.map((points, index) => (
        <CortexAttentionCurrent
          key={`cortex-current-${index}`}
          points={points}
          color={cortexCurrentColor}
          lineWidth={attentionOnInput ? 2.8 : tier === 'high' ? 1.3 : tier === 'medium' ? 1 : 0.8}
          opacity={attentionOnInput ? 0.88 : Math.min(0.32, (0.06 + physical.cortex.activity * 0.12) * coherenceOpacity)}
          reducedMotion={reducedMotion}
          inputAttention={attentionOnInput}
        />
      ))}

      {councilDissentPaths.map((points, index) => (
        <Line
          key={`council-dissent-${index}`}
          data-testid="council-dissent"
          points={points}
          color="#c9b6ff"
          lineWidth={tier === 'high' ? 1.05 : tier === 'medium' ? 0.85 : 0.7}
          frustumCulled={false}
          transparent
          opacity={0.16 * coherenceOpacity}
        />
      ))}

      {conductorSeatSignals.map((signal) => {
        const color = CONDUCTOR_COLORS[signal.role];
        const seat = anchorWorldPosition(signal.seatIndex);
        const isActive = signal.role === 'active';
        const surface = physicalSurfaceBySeat.get(signal.seatIndex);
        return (
          <mesh
            key={`physical-conductor-seat-${signal.seatIndex}`}
            data-testid="physical-conductor-seat"
            position={seat}
            scale={(0.72 + signal.intensity * 0.38) * (surface?.focused ? 1.08 : 1)}
          >
            <sphereGeometry args={[isActive ? 0.035 : 0.025, tier === 'high' ? 12 : 8, tier === 'high' ? 10 : 6]} />
            <meshBasicMaterial
              color={color}
              transparent
              opacity={Math.min(0.72, signal.socketOpacity * (conductorStopped ? 0.48 : 1) * coherenceOpacity)}
              depthWrite={false}
              blending={THREE.AdditiveBlending}
            />
          </mesh>
        );
      })}

      {/* Conduct pulse: a bounded semantic cue around the cortex. */}
      {!conductorStopped && <mesh
        ref={semanticPulseMeshRef}
        data-testid="cortex-posture-field"
        position={cortex}
        scale={[0.24, 0.24, 0.24]}
      >
        <sphereGeometry args={[1, 20, 20]} />
        <meshBasicMaterial
          ref={semanticPulseMaterialRef}
          color={cortexPostureColor}
          transparent
          opacity={cortexPostureOpacity}
          depthWrite={false}
          side={THREE.DoubleSide}
          blending={THREE.AdditiveBlending}
        />
      </mesh>}

      {physical.memory.layer !== 'none' && (
        <mesh
          data-testid="memory-cerebellar-field"
          position={memoryFieldPosition}
          scale={[memoryFieldScale, memoryFieldScale, memoryFieldScale]}
          rotation={physical.memory.pulse === 'inward' ? [0, Math.PI / 2, 0] : [Math.PI / 2, 0, 0]}
        >
          <torusGeometry args={[0.16, 0.012, tier === 'high' ? 8 : 6, tier === 'high' ? 24 : 14]} />
          <meshBasicMaterial
            color={memoryFieldColor}
            transparent
            opacity={Math.min(0.38, (physical.memory.layer === 'promoted' ? 0.34 : 0.26) * coherenceOpacity)}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </mesh>
      )}

      {physical.membrane.state !== 'clear' && (
        <mesh
          data-testid="sovereign-membrane"
          position={cortex}
          rotation={[Math.PI / 2, 0, 0]}
        >
          <torusGeometry args={[0.42, 0.012, 8, 64]} />
          <meshBasicMaterial
            color={membraneColor}
            transparent
            opacity={membraneOpacity * coherenceOpacity}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </mesh>
      )}

      {verificationState !== 'none' && (
        <mesh
          data-testid="verification-field"
          position={[cortex.x, cortex.y, cortex.z + 0.02]}
          rotation={[Math.PI / 2, 0, verificationState === 'fail' ? 0.22 : 0]}
          scale={[verificationFieldScale, verificationFieldScale, verificationFieldScale]}
        >
          <torusGeometry args={[0.3, 0.014, tier === 'high' ? 8 : 6, tier === 'high' ? 32 : 20]} />
          <meshBasicMaterial
            color={verificationFieldColor}
            transparent
            opacity={verificationFieldOpacity * coherenceOpacity}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </mesh>
      )}

      {/* Temporary worker postures derived from the semantic kernel. */}
      {Object.entries(motes).map(([workerId, m]) => {
        const angle = m.angle;
        const scale = getBrainDockScale();
        const pos = [
          (m.origin.x + Math.cos(angle) * m.radius) * scale,
          m.origin.y * scale,
          (m.origin.z + Math.sin(angle) * m.radius) * scale,
        ];
        
        const WORKER_COLORS = {
          bud: '#b9a7ff',
          branch: '#cf9cff',
          conduct: '#50e8ff',
          held: '#ffb36b',
          returning: '#82f0b5',
          dissolved: '#71809d',
        };
        const color = WORKER_COLORS[m.visualState] || WORKER_COLORS.bud;
        const opacity = (m.visualState === 'dissolved' ? 0.32 : m.visualState === 'held' ? 0.64 : 0.85)
          * coherenceOpacity;
        
        const branchStart = m.origin.clone().multiplyScalar(scale);
        const branchTip = new THREE.Vector3(...pos);
        const branchMid = branchStart.clone().lerp(branchTip, 0.5);
        return (
          <group key={workerId} name={`worker-seat-${m.seat}`}>
            <Line
              ref={(line) => {
                if (line) branchLineNodesRef.current[workerId] = line;
                else delete branchLineNodesRef.current[workerId];
              }}
              data-testid="worker-branch"
              points={[branchStart, branchMid, branchTip]}
              color={color}
              lineWidth={1.5}
              frustumCulled={false}
              transparent
              opacity={(m.visualState === 'dissolved' ? 0.14 : m.visualState === 'held' ? 0.4 : 0.58) * coherenceOpacity}
            />
            <mesh
              data-testid="worker-mote"
              position={pos}
              ref={(node) => {
                if (node) moteNodesRef.current[workerId] = node;
                else delete moteNodesRef.current[workerId];
              }}
            >
              <sphereGeometry args={[0.04, 8, 8]} />
              <meshBasicMaterial color={color} transparent opacity={opacity} />
            </mesh>
          </group>
        );
      })}

      {/* Trails and Scars (Stigmergy pheromones and mistakes) */}
      {stigmergyTrails.map((t, i) => {
        const seed = t.skill_id ?? i;
        const rand1 = getStableRandom(seed);
        const rand2 = getStableRandom(seed + 9999);
        const radius = 3.25; // float slightly above brain
        const phi = Math.acos(2 * rand1 - 1);
        const theta = 2 * Math.PI * rand2;
        
        const pos = new THREE.Vector3(
          radius * Math.sin(phi) * Math.cos(theta),
          radius * Math.sin(phi) * Math.sin(theta),
          radius * Math.cos(phi)
        ).add(cortex);

        const isScar = t.failure_count > 0 || t.status === 'failed';
        const color = isScar ? '#ff2a2a' : (t.status === 'verified' ? '#00e5ff' : '#aefeff');
        const opacity = Math.max(0.15, (t.strength ?? 0.5) * (isScar ? 0.8 : 1.0));

        if (isScar) {
          return (
            <mesh key={`scar-${seed}`} position={pos}>
              <boxGeometry args={[0.07, 0.07, 0.07]} />
              <meshBasicMaterial color={color} transparent opacity={opacity} depthWrite={false} blending={THREE.AdditiveBlending} />
            </mesh>
          );
        } else {
          // generate short arc along the sphere
          const phi2 = phi + (getStableRandom(seed + 1) - 0.5) * 0.4;
          const theta2 = theta + (getStableRandom(seed + 2) - 0.5) * 0.4;
          const pos2 = new THREE.Vector3(
            radius * Math.sin(phi2) * Math.cos(theta2),
            radius * Math.sin(phi2) * Math.sin(theta2),
            radius * Math.cos(phi2)
          ).add(cortex);
          
          const arcPoints = [];
          for (let s = 0; s <= 5; s++) {
             const t_val = s / 5;
             const p = new THREE.Vector3()
               .lerpVectors(pos, pos2, t_val)
               .sub(cortex)
               .normalize()
               .multiplyScalar(radius)
               .add(cortex);
             arcPoints.push(p);
          }
          return (
            <Line 
              key={`trail-${seed}`} 
              points={arcPoints} 
              color={color} 
              lineWidth={2} 
              transparent 
              opacity={opacity} 
              blending={THREE.AdditiveBlending} 
              depthWrite={false} 
            />
          );
        }
      })}
    </group>
  );
}
