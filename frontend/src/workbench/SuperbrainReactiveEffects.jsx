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
import { useEffect, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Line } from '@react-three/drei';
import * as THREE from 'three';
import {
  subscribeSwarmHUD,
} from '../superbrain/lib/swarmHUDStore';
import { subscribeCognition } from '../superbrain/lib/cognitionBus';
import { getKnownTrails } from '../superbrain/lib/aiosAdapter';
import {
  fuseSpinePoint,
  getSpineFusion,
  getBrainDockScale,
  getCortexAnchor,
} from '../superbrain/lib/spineFusionBus';
import { SEGMENT_ANCHORS } from '../superbrain/lib/spineAnatomy';
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
  isActionPresentationStopped,
  pruneExpiredWorkerMotes,
} from '../livingMirror/being/semanticEffects';
import { coherenceSemanticsFor } from '../livingMirror/being/coherenceSemantics';
import { useReducedMotion } from '../superbrain/lib/reducedMotion';
import { updateLineGeometryPoints } from './lineGeometry';

const CLOUD_COLORS = {
  bedrock: new THREE.Color('#f5c542'),
  gemini: new THREE.Color('#4aa8ff'),
  default: new THREE.Color('#ffffff'),
};

function providerColor(provider) {
  return CLOUD_COLORS[provider] ?? CLOUD_COLORS.default;
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
const SPINE_FLASH_DURATION_S = 1.6;

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

export default function SuperbrainReactiveEffects() {
  const being = useBeingPresentation();
  const actionPresentationStopped = isActionPresentationStopped(being);
  const coherenceSemantics = coherenceSemanticsFor(being.coherence);
  const reducedMotion = useReducedMotion();
  const [lightnings, setLightnings] = useState([]);
  const [motes, setMotes] = useState({});
  const [stigmergyTrails, setStigmergyTrails] = useState(() => [...(getKnownTrails() || [])]);
  const motesRef = useRef({});
  const [aurora, setAurora] = useState(getAuroraState);
  const [spineFlash, setSpineFlash] = useState(getSpineFlashState);
  const lastCloudIndices = useRef(new Set());
  const moteNodesRef = useRef({});
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
  if (spineFlashScratchRef.current === null) {
    spineFlashScratchRef.current = {
      points: Array.from({ length: FLASH_POINT_COUNT }, () => new THREE.Vector3()),
      start: new THREE.Vector3(),
      end: new THREE.Vector3(),
      sample: new THREE.Vector3(),
    };
  }
  const previousBeingRef = useRef(null);
  const terminalWorkerExpiryRef = useRef({});
  const semanticEffectsRef = useRef({ enteredSignals: [], workerVisualStates: [], actionPulse: false });
  const semanticPulseRef = useRef(0);
  const semanticPulseMeshRef = useRef(null);
  const semanticPulseMaterialRef = useRef(null);
  const actionPresentationStoppedRef = useRef(actionPresentationStopped);
  const reducedMotionRef = useRef(reducedMotion);
  const coherenceSemanticsRef = useRef(coherenceSemantics);

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
    semanticEffectsRef.current = transition;
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

  // Temporary worker motes are derived from bounded semantic worker posture,
  // not worker IDs or caste event names. Terminal states get a short visual
  // reabsorption window and cannot remain mounted forever.
  useEffect(() => {
    const workerVisualStates = deriveSemanticEffectTransition(null, being).workerVisualStates;
    const now = performance.now();
    setMotes((prev) => {
      const next = {};
      workerVisualStates.forEach((visualState, index) => {
        const key = `worker-${index}`;
        const existing = prev[key];
        const terminal = visualState === 'returning' || visualState === 'dissolved';
        if (!terminal) delete terminalWorkerExpiryRef.current[key];
        const rememberedTerminalAt = terminalWorkerExpiryRef.current[key] ?? null;
        const terminalAt = existing?.terminalAt ?? rememberedTerminalAt ?? (terminal ? now : null);
        if (terminal && terminalAt !== null) terminalWorkerExpiryRef.current[key] = terminalAt;
        if (terminalAt !== null && now - terminalAt >= 1600) return;
        const seat = existing?.seat ?? seatForIndex(index);
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
  }, [being]);

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

  useFrame((_, delta) => {
    if (actionPresentationStopped || reducedMotionRef.current) {
      semanticPulseRef.current = 0;
      if (semanticPulseMaterialRef.current) semanticPulseMaterialRef.current.opacity = 0;
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
    for (const [caste, m] of Object.entries(motesRef.current)) {
      const node = moteNodesRef.current[caste];
      if (!node) continue;
      const motionScale = (m.visualState === 'held' ? 0 : m.visualState === 'conduct' ? 1 : 0.42)
        * coherence.motionScale;
      const angle = (moteAnglesRef.current[caste] ?? m.angle) + m.speed * delta * motionScale;
      moteAnglesRef.current[caste] = angle;
      const scale = getBrainDockScale();
      const radiusScale = m.visualState === 'bud' ? 0.32 : m.visualState === 'branch' ? 0.68 : 1;
      node.position.set(
        (m.origin.x + Math.cos(angle) * m.radius * radiusScale) * scale,
        m.origin.y * scale,
        (m.origin.z + Math.sin(angle) * m.radius * radiusScale) * scale,
      );
      const visualScale = m.visualState === 'held' ? 0.82 : m.visualState === 'conduct' ? 1.2 : 1;
      node.scale.setScalar(visualScale);
    }
    semanticPulseRef.current = Math.max(0, semanticPulseRef.current - delta * 0.8);
    if (semanticPulseMeshRef.current) {
      semanticPulseMeshRef.current.scale.setScalar(0.24 + semanticPulseRef.current * 0.2);
    }
    if (semanticPulseMaterialRef.current) {
      semanticPulseMaterialRef.current.opacity = semanticPulseRef.current * 0.12 * coherence.opacity;
    }
  });

  // Keep a ref in sync so useFrame can guard against empty-object churn.
  useEffect(() => {
    motesRef.current = motes;
  }, [motes]);

  const [cx, cy, cz] = getCortexAnchor();
  const cortex = new THREE.Vector3(cx, cy, cz).multiplyScalar(getBrainDockScale());
  const auroraScale = 0.22 + aurora.intensity * 0.18;
  const coherenceOpacity = coherenceSemantics.opacity;
  
  const VERDICT_COLORS = {
    pass: '#2fffa1',
    fail: '#ff2f2f',
    caution: '#ffb454',
  };
  const auroraColor = VERDICT_COLORS[aurora.verdict] || VERDICT_COLORS.pass;

  return (
    <group name="superbrain-reactive-effects">
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

      {/* Conduct pulse: a bounded semantic cue around the cortex. */}
      {!actionPresentationStopped && <mesh ref={semanticPulseMeshRef} position={cortex} scale={[0.24, 0.24, 0.24]}>
        <sphereGeometry args={[1, 20, 20]} />
        <meshBasicMaterial
          ref={semanticPulseMaterialRef}
          color="#7bf5fb"
          transparent
          opacity={0}
          depthWrite={false}
          side={THREE.DoubleSide}
          blending={THREE.AdditiveBlending}
        />
      </mesh>}

      {/* Temporary worker postures derived from the semantic kernel. */}
      {Object.entries(motes).map(([caste, m]) => {
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
        
        return (
          <mesh
            key={caste}
            data-testid="worker-mote"
            position={pos}
            ref={(node) => {
              if (node) moteNodesRef.current[caste] = node;
              else delete moteNodesRef.current[caste];
            }}
          >
            <sphereGeometry args={[0.04, 8, 8]} />
            <meshBasicMaterial color={color} transparent opacity={opacity} />
          </mesh>
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
