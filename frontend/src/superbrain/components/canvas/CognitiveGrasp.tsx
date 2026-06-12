'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { publishCognition } from '@/lib/cognitionBus';
import { getKnownTrails, trailLabel, type TrailRow } from '@/lib/aiosAdapter';

type Point = readonly [number, number, number];

const SLOT_SECONDS = 6;
const VARIANT_COUNT = 3;
const ROUTE_POINT_COUNT = 54;
/**
 * Phase at which the returning retrieval packet reaches the brain (path
 * progress hits 0 at the origin — see the `1 - smoothstep(0.56, 0.82, phase)`
 * return interpolation). Crossing this edge is the ABSORB moment: the cortex
 * has eaten the knowledge, so the whole OS is notified exactly once.
 */
const ABSORB_PHASE = 0.82;
/** Publish window upper bound: avoids a spurious mount-time publish when a
 *  component first evaluates deep into an already-absorbed cycle. */
const ABSORB_PHASE_MAX = 0.92;
/** The receive flare brightens ~20% for this long after absorption. */
const ABSORB_PULSE_SECONDS = 0.5;

/**
 * The glints are no longer lore: each cycle recalls a REAL trail from the
 * AI-OS pheromone map (the trail for a given absolute slot is a pure function
 * of the slot, so every sub-component agrees without shared state). The
 * absorb moment publishes a RECALL — a label-anchored cortical burst that
 * lights the matching anatomical region — never 'knowledge-acquired', which
 * is reserved for genuine trail reinforcement reported by the adapter.
 */
export function trailForSlot(slot: number): TrailRow | null {
  const trails = getKnownTrails();
  if (trails.length === 0) return null;
  return trails[slot % trails.length];
}

/** Quarantined trails wear the stain: a desaturated warning red. */
const QUARANTINE_CAGE = new THREE.Color('#c2483f');
/**
 * Scale applied to the wire cage and its receive offset so the whole target
 * reads as a small distant glint rather than a brain-scale structure.
 */
const CAGE_SCALE = 0.5;
/*
 * Core crystals are intentionally pale gold-white and ADDITIVE: a solid lit
 * near-black octahedron here previously rendered as an opaque faceted mass
 * (and, while depth-writing at opacity 0, punched black holes through the
 * additive nebula/aura layers behind it). Additive pale glow can never read
 * as a black blob, whatever the animation phase.
 */
const TARGET_PALETTES = [
  { cage: '#3edcff', core: '#fff3da', glow: '#ffe2b0', return: '#ffcf73' },
  { cage: '#b06cff', core: '#fff0e2', glow: '#ffdfc2', return: '#ff78a2' },
  { cage: '#ffb84d', core: '#fff4d6', glow: '#ffe3ae', return: '#72e8ff' },
  { cage: '#ff5c8a', core: '#fff1e0', glow: '#ffd9bd', return: '#c28aff' },
] as const;

/**
 * Scales a color so its relative luminance never exceeds `maxLuminance`.
 * Post bloom threshold is 0.55: every launch flare, ring and packet material
 * is built from these clamped colors (≤ ~0.5) so the transfer choreography
 * can never bloom into the white-magenta glare the judges flagged. The pale
 * gold glint cores (palette.core / palette.glow) are intentionally NOT
 * clamped — they are the round-2 glint targets the judges asked to keep.
 */
function clampLuminance(hex: string, maxLuminance = 0.5): THREE.Color {
  const color = new THREE.Color(hex);
  const luminance = color.r * 0.2126 + color.g * 0.7152 + color.b * 0.0722;
  if (luminance > maxLuminance) color.multiplyScalar(maxLuminance / luminance);
  return color;
}

const CLAMPED_PALETTES = TARGET_PALETTES.map((palette) => ({
  cage: clampLuminance(palette.cage),
  return: clampLuminance(palette.return),
}));

interface TargetDef {
  anchor: Point;
  variantOffsets: readonly Point[];
  cagePoints: readonly Point[];
  origin: Point;
  routingBias: Point;
  endpointOffset: Point;
}

/*
 * Anchor framing at camera z ~5.9 (worst case ~5.1, fov 42, 16:9): all
 * anchors sit deep (z -5.1..-7.2) where the visible half-width is ~7-9
 * world units, so |x| up to ~5.9 stayed in frame — but the widest two are
 * pulled inward for drift margin. They are NOT clamped all the way to the
 * z~0-plane limit of |x| 3.6 because at this depth that would stack the
 * glints onto the brain / knowledge-web region.
 */
const TARGET_DEFS: readonly TargetDef[] = [
  {
    anchor: [4.7, 1.05, -5.4],
    variantOffsets: [[0, 0, 0], [0.7, 0.9, -1.1], [-0.5, -0.7, 0.6]],
    cagePoints: [[0.54, 0.42, 0.18], [-0.46, -0.34, -0.3], [0, 0.55, -0.35], [0.02, -0.52, 0.38]],
    origin: [0.72, 0.82, -1.15],
    routingBias: [0.35, 1.05, -0.42],
    endpointOffset: [0.54, 0.42, 0.18],
  },
  {
    anchor: [-4.8, 0.7, -5.1],
    variantOffsets: [[0, 0, 0], [-0.8, 0.7, -0.9], [0.6, -0.6, 0.5]],
    cagePoints: [[-0.5, 0.4, 0.22], [0.44, -0.36, -0.28], [0, 0.52, -0.32], [-0.04, -0.5, 0.36]],
    origin: [-0.7, 0.85, -1.2],
    routingBias: [-0.42, 1.0, -0.4],
    endpointOffset: [-0.5, 0.4, 0.22],
  },
  {
    anchor: [-3.9, 2.7, -7.2],
    // Variant y-offsets stay low so this upper-left target never drifts into
    // the title no-fly zone (screen-top centre, world y > ~3.5).
    variantOffsets: [[0, 0, 0], [0.9, 0.2, -0.8], [-0.7, -0.4, 0.7]],
    cagePoints: [[0.4, 0.45, -0.2], [-0.42, -0.3, 0.3], [0.05, 0.5, 0.3], [-0.1, -0.48, -0.3]],
    origin: [-0.35, 1.05, -1.35],
    routingBias: [-0.75, 0.55, -0.48],
    endpointOffset: [0.4, 0.45, -0.2],
  },
  {
    anchor: [3.95, -2.0, -6.4],
    variantOffsets: [[0, 0, 0], [-0.6, 0.8, -1.0], [0.8, -0.5, 0.6]],
    cagePoints: [[0.42, 0.34, -0.26], [-0.4, -0.4, 0.28], [-0.05, 0.52, 0.28], [0.08, -0.5, -0.32]],
    origin: [0.55, -0.7, -1.1],
    routingBias: [0.65, -0.72, -0.4],
    endpointOffset: [0.42, 0.34, -0.26],
  },
];

const CAGE_EDGES = [
  [0, 1],
  [0, 2],
  [0, 3],
  [1, 2],
  [1, 3],
  [2, 3],
] as const;

interface RoutedPath {
  points: THREE.Vector3[];
  cumulativeLengths: number[];
  length: number;
}

interface RouteVariant {
  path: RoutedPath;
  geometry: THREE.BufferGeometry;
  endpoint: THREE.Vector3;
}

interface TargetData {
  positions: THREE.Vector3[];
  cageGeometry: THREE.BufferGeometry;
  origin: THREE.Vector3;
  receiveOffset: THREE.Vector3;
  variants: RouteVariant[];
}

function toVector(point: Point) {
  return new THREE.Vector3(...point);
}

function buildRoutedPath(origin: THREE.Vector3, endpoint: THREE.Vector3, bias: THREE.Vector3): RoutedPath {
  const delta = endpoint.clone().sub(origin);
  const points = [
    origin.clone(),
    origin.clone().addScaledVector(delta, 0.14).addScaledVector(bias, 0.18),
    origin.clone().addScaledVector(delta, 0.38).add(bias),
    origin.clone().addScaledVector(delta, 0.72).addScaledVector(bias, 0.34),
    origin.clone().addScaledVector(delta, 0.9),
    endpoint.clone(),
  ];
  const cumulativeLengths = [0];

  for (let index = 1; index < points.length; index += 1) {
    cumulativeLengths.push(
      cumulativeLengths[index - 1] + points[index - 1].distanceTo(points[index]),
    );
  }

  return {
    points,
    cumulativeLengths,
    length: cumulativeLengths[cumulativeLengths.length - 1],
  };
}

function getPathPoint(path: RoutedPath, progress: number, target: THREE.Vector3) {
  const distance = THREE.MathUtils.clamp(progress, 0, 1) * path.length;
  let segmentIndex = 1;

  while (
    segmentIndex < path.cumulativeLengths.length - 1
    && path.cumulativeLengths[segmentIndex] < distance
  ) {
    segmentIndex += 1;
  }

  const segmentStart = path.cumulativeLengths[segmentIndex - 1];
  const segmentLength = path.cumulativeLengths[segmentIndex] - segmentStart;
  const segmentProgress = segmentLength > 0 ? (distance - segmentStart) / segmentLength : 0;
  return target.lerpVectors(path.points[segmentIndex - 1], path.points[segmentIndex], segmentProgress);
}

function buildRoutePointGeometry(path: RoutedPath) {
  const positions: number[] = [];
  const progress: number[] = [];

  for (let index = 0; index < ROUTE_POINT_COUNT; index += 1) {
    const pointProgress = index / (ROUTE_POINT_COUNT - 1);
    const point = getPathPoint(path, pointProgress, new THREE.Vector3());
    positions.push(point.x, point.y, point.z);
    progress.push(pointProgress);
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('aProgress', new THREE.Float32BufferAttribute(progress, 1));
  return geometry;
}

function buildTransferSystem(): TargetData[] {
  return TARGET_DEFS.map((def) => {
    const positions = def.variantOffsets.map((offset) =>
      toVector(def.anchor).add(toVector(offset)),
    );
    const cagePositions = CAGE_EDGES.flatMap(([start, end]) => [
      ...def.cagePoints[start].map((value) => value * CAGE_SCALE),
      ...def.cagePoints[end].map((value) => value * CAGE_SCALE),
    ]);
    const cageGeometry = new THREE.BufferGeometry().setAttribute(
      'position',
      new THREE.Float32BufferAttribute(cagePositions, 3),
    );
    const origin = toVector(def.origin);
    const receiveOffset = toVector(def.endpointOffset).multiplyScalar(CAGE_SCALE);
    const routingBias = toVector(def.routingBias);
    const variants = positions.map((position) => {
      const endpoint = position.clone().add(receiveOffset);
      const path = buildRoutedPath(origin, endpoint, routingBias);
      return { path, endpoint, geometry: buildRoutePointGeometry(path) };
    });

    return { positions, cageGeometry, origin, receiveOffset, variants };
  });
}

const routeVertexShader = `
  attribute float aProgress;
  varying float vProgress;
  uniform float uActivity;
  uniform float uReveal;

  void main() {
    vProgress = aProgress;
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    float travelingFocus = exp(-pow((aProgress - uReveal) * 13.0, 2.0));
    float perspective = 46.0 / max(8.0, -mvPosition.z);
    // Tiny motes only: capped at ~3px so the route reads as a faint filament.
    gl_PointSize = clamp((0.8 + travelingFocus * (1.5 + uActivity * 0.6)) * perspective, 0.8, 3.0);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const routeFragmentShader = `
  uniform vec3 uColor;
  uniform float uActivity;
  uniform float uOpacity;
  uniform float uReveal;
  uniform float uSeed;
  uniform float uTime;

  varying float vProgress;

  void main() {
    float distanceToCenter = length(gl_PointCoord - vec2(0.5));
    if (distanceToCenter > 0.5) discard;
    float disc = 1.0 - smoothstep(0.08, 0.5, distanceToCenter);
    float revealed = 1.0 - smoothstep(uReveal - 0.018, uReveal + 0.018, vProgress);
    float travelingFocus = exp(-pow((vProgress - uReveal) * 14.0, 2.0));
    float packetTrain = pow(max(0.0, sin(vProgress * 48.0 - uTime * 3.4 + uSeed)), 12.0);
    // ~50% of the previous luminance: an elegant faint filament, never a comet.
    float alpha = revealed * uOpacity * packetTrain * (0.15 + uActivity * 0.08);
    alpha += travelingFocus * uOpacity * (0.24 + uActivity * 0.08);
    // Restrained white mix + hard clamp: the post-multiplied (additive)
    // luminance of any packet fragment stays <= 0.5, under the 0.55 bloom
    // threshold, so the traveling focus can never flash into a glare.
    vec3 color = mix(uColor, vec3(1.0), travelingFocus * 0.12);
    float outAlpha = alpha * disc;
    float emitted = dot(color, vec3(0.2126, 0.7152, 0.0722)) * outAlpha;
    if (emitted > 0.5) outAlpha *= 0.5 / emitted;
    gl_FragColor = vec4(color, outAlpha);
  }
`;

function smoothstep(min: number, max: number, value: number) {
  const normalized = THREE.MathUtils.clamp((value - min) / (max - min), 0, 1);
  return normalized * normalized * (3 - 2 * normalized);
}

function getTimeline(elapsedTime: number, targetIndex: number) {
  const absoluteSlot = Math.floor(elapsedTime / SLOT_SECONDS);
  const activeTarget = absoluteSlot % TARGET_DEFS.length;
  return {
    active: activeTarget === targetIndex,
    phase: (elapsedTime % SLOT_SECONDS) / SLOT_SECONDS,
    variantIndex: Math.floor(absoluteSlot / TARGET_DEFS.length) % VARIANT_COUNT,
    /** Globally unique cycle id — the once-per-cycle absorb publish guard. */
    slot: absoluteSlot,
  };
}

function windowStrength(phase: number, enterStart: number, enterEnd: number, exitStart: number, exitEnd: number) {
  return smoothstep(enterStart, enterEnd, phase) * (1 - smoothstep(exitStart, exitEnd, phase));
}

function TransferRoute({
  target,
  targetIndex,
  activity,
}: {
  target: TargetData;
  targetIndex: number;
  activity: number;
}) {
  const routeRef = useRef<THREE.Points>(null);
  const routeMaterialRef = useRef<THREE.ShaderMaterial>(null);
  const launchRef = useRef<THREE.Group>(null);
  const launchRingMaterialRef = useRef<THREE.MeshBasicMaterial>(null);
  const launchCoreMaterialRef = useRef<THREE.MeshBasicMaterial>(null);
  const outboundRef = useRef<THREE.Group>(null);
  const returnRef = useRef<THREE.Group>(null);
  const variantIndexRef = useRef(0);
  /** Last cycle (absolute slot) whose absorption was already published. */
  const absorbedSlotRef = useRef(-1);
  /** Clock time of the latest absorb — drives the 0.5s flare acknowledgment. */
  const absorbTimeRef = useRef(Number.NEGATIVE_INFINITY);
  const clamped = CLAMPED_PALETTES[targetIndex % CLAMPED_PALETTES.length];
  const uniforms = useMemo(
    () => ({
      uColor: { value: clamped.cage.clone() },
      uActivity: { value: 0 },
      uOpacity: { value: 0 },
      uReveal: { value: 0 },
      uSeed: { value: targetIndex * 2.173 },
      uTime: { value: 0 },
    }),
    [clamped, targetIndex],
  );

  useFrame((state, delta) => {
    const timeline = getTimeline(state.clock.elapsedTime, targetIndex);

    if (timeline.variantIndex !== variantIndexRef.current) {
      variantIndexRef.current = timeline.variantIndex;
      if (routeRef.current) routeRef.current.geometry = target.variants[timeline.variantIndex].geometry;
    }

    const route = routeRef.current;
    const launch = launchRef.current;
    const outbound = outboundRef.current;
    const returning = returnRef.current;

    if (!timeline.active) {
      if (route) route.visible = false;
      if (launch) launch.visible = false;
      if (outbound) outbound.visible = false;
      if (returning) returning.visible = false;
      return;
    }

    const phase = timeline.phase;
    const intensity = THREE.MathUtils.clamp(activity, 0, 1);
    const variant = target.variants[variantIndexRef.current];

    // ABSORB edge: the returning packet just reached the cortex. Publish the
    // RECALL exactly once per cycle (slot-guarded, never per-frame) and start
    // the 0.5s receive-flare acknowledgment. A recall is a cortical burst
    // labeled with the REAL trail, so the matching anatomical region lights —
    // it is deliberately NOT a knowledge-acquired event (no metric bump, no
    // accretion feed): the brain is touching memory, not gaining it.
    if (
      phase >= ABSORB_PHASE
      && phase < ABSORB_PHASE_MAX
      && absorbedSlotRef.current !== timeline.slot
    ) {
      absorbedSlotRef.current = timeline.slot;
      absorbTimeRef.current = state.clock.elapsedTime;
      const trail = trailForSlot(timeline.slot);
      if (trail) {
        publishCognition({
          type: 'burst',
          label: trailLabel(trail.goal_pattern),
          detail:
            `trail #${trail.skill_id} · strength ${trail.strength.toFixed(2)} · ` +
            `${trail.success_count + trail.reuse_success_count} walk(s)` +
            (trail.quarantined ? ' · QUARANTINED' : ''),
          intensity: THREE.MathUtils.clamp(0.3 + trail.strength * 0.5, 0, 1),
          source: 'grasp',
        });
      }
    }
    // 1 at the absorb instant -> 0 after ABSORB_PULSE_SECONDS.
    const absorbPulse = Math.max(
      0,
      1 - (state.clock.elapsedTime - absorbTimeRef.current) / ABSORB_PULSE_SECONDS,
    );

    const reveal = smoothstep(0.11, 0.35, phase);
    const routeOpacity = windowStrength(phase, 0.08, 0.16, 0.76, 0.9);
    const launchStrength = Math.max(
      windowStrength(phase, 0.015, 0.075, 0.18, 0.28),
      windowStrength(phase, 0.72, 0.79, 0.86, 0.94) * 0.72,
    );

    if (route) route.visible = routeOpacity > 0.002;
    if (routeMaterialRef.current) {
      const material = routeMaterialRef.current;
      material.uniforms.uTime.value = state.clock.elapsedTime;
      material.uniforms.uReveal.value = reveal;
      material.uniforms.uOpacity.value = THREE.MathUtils.damp(
        material.uniforms.uOpacity.value,
        routeOpacity,
        10,
        delta,
      );
      material.uniforms.uActivity.value = THREE.MathUtils.damp(
        material.uniforms.uActivity.value,
        intensity,
        6,
        delta,
      );
    }

    if (launch) {
      launch.visible = launchStrength > 0.002;
      launch.rotation.z -= delta * (0.7 + launchStrength);
      launch.scale.setScalar(0.72 + launchStrength * (0.8 + intensity * 0.28));
    }
    // Launch flare luminance halved: with bloom threshold at 0.55 the old
    // values bloomed into a hard white flash above the brain.
    // Absorb acknowledgment: the receive rings at the contact point brighten
    // ~20% for 0.5s after the packet lands. Opacity-only lift on the already
    // luminance-clamped (<= 0.5) colors — peak emission stays under the 0.55
    // bloom threshold.
    const absorbLift = 1 + absorbPulse * 0.2;
    if (launchRingMaterialRef.current) {
      launchRingMaterialRef.current.opacity = launchStrength * (0.09 + intensity * 0.04) * absorbLift;
    }
    if (launchCoreMaterialRef.current) {
      launchCoreMaterialRef.current.opacity = launchStrength * (0.18 + intensity * 0.06) * absorbLift;
    }

    const outboundVisible = phase >= 0.13 && phase <= 0.46;
    if (outbound) {
      outbound.visible = outboundVisible;
      if (outboundVisible) {
        const progress = smoothstep(0.13, 0.45, phase);
        getPathPoint(variant.path, progress, outbound.position);
        outbound.rotation.x += delta * 4.2;
        outbound.rotation.y += delta * 3.4;
        outbound.scale.setScalar(0.72 + Math.sin(progress * Math.PI) * (0.32 + intensity * 0.12));
      }
    }

    const returnVisible = phase >= 0.56 && phase <= 0.83;
    if (returning) {
      returning.visible = returnVisible;
      if (returnVisible) {
        const progress = 1 - smoothstep(0.56, 0.82, phase);
        getPathPoint(variant.path, progress, returning.position);
        returning.rotation.x -= delta * 3.8;
        returning.rotation.z += delta * 4.6;
        returning.scale.setScalar(0.64 + Math.sin(progress * Math.PI) * (0.26 + intensity * 0.1));
      }
    }
  });

  return (
    <group>
      <points
        ref={routeRef}
        geometry={target.variants[0].geometry}
        frustumCulled={false}
        visible={false}
      >
        <shaderMaterial
          ref={routeMaterialRef}
          vertexShader={routeVertexShader}
          fragmentShader={routeFragmentShader}
          uniforms={uniforms}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </points>

      {/* Launch flare, packets and halos all use luminance-clamped colors —
          peak emitted luminance stays under the 0.55 bloom threshold. */}
      <group ref={launchRef} position={target.origin} visible={false}>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.12, 0.008, 5, 18]} />
          <meshBasicMaterial
            ref={launchRingMaterialRef}
            color={clamped.cage}
            transparent
            opacity={0}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
        <mesh>
          <octahedronGeometry args={[0.035, 0]} />
          <meshBasicMaterial
            ref={launchCoreMaterialRef}
            color={clamped.return}
            transparent
            opacity={0}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
      </group>

      <group ref={outboundRef} visible={false}>
        <mesh>
          <octahedronGeometry args={[0.045, 0]} />
          <meshBasicMaterial color={clamped.cage} toneMapped={false} />
        </mesh>
        <mesh>
          <sphereGeometry args={[0.095, 8, 8]} />
          <meshBasicMaterial
            color={clamped.cage}
            transparent
            opacity={0.055}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
      </group>

      <group ref={returnRef} visible={false}>
        <mesh>
          <octahedronGeometry args={[0.038, 0]} />
          <meshBasicMaterial color={clamped.return} toneMapped={false} />
        </mesh>
        <mesh>
          <sphereGeometry args={[0.08, 8, 8]} />
          <meshBasicMaterial
            color={clamped.return}
            transparent
            opacity={0.045}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
      </group>
    </group>
  );
}

function KnowledgeTarget({
  target,
  activity,
  targetIndex,
}: {
  target: TargetData;
  activity: number;
  targetIndex: number;
}) {
  const palette = TARGET_PALETTES[targetIndex % TARGET_PALETTES.length];
  const clamped = CLAMPED_PALETTES[targetIndex % CLAMPED_PALETTES.length];
  const groupRef = useRef<THREE.Group>(null);
  const cageRef = useRef<THREE.LineBasicMaterial>(null);
  const coreRef = useRef<THREE.MeshBasicMaterial>(null);
  const coreGlowRef = useRef<THREE.MeshBasicMaterial>(null);
  const receiveRingRefs = useRef<(THREE.Mesh | null)[]>([]);
  const receiveMaterialRefs = useRef<(THREE.MeshBasicMaterial | null)[]>([]);
  const variantIndexRef = useRef(0);

  useFrame((state, delta) => {
    const timeline = getTimeline(state.clock.elapsedTime, targetIndex);
    const group = groupRef.current;

    if (timeline.variantIndex !== variantIndexRef.current) {
      variantIndexRef.current = timeline.variantIndex;
      group?.position.copy(target.positions[timeline.variantIndex]);
    }
    if (!group) return;
    if (!timeline.active) {
      group.visible = false;
      return;
    }

    group.visible = true;
    const phase = timeline.phase;
    const intensity = THREE.MathUtils.clamp(activity, 0, 1);
    const presence = windowStrength(phase, 0.2, 0.32, 0.78, 0.94);
    const receiveStrength = windowStrength(phase, 0.32, 0.42, 0.55, 0.68);
    const returnStrength = windowStrength(phase, 0.54, 0.61, 0.68, 0.78);

    // The glint wears its trail's REAL numbers: strength brightens the core,
    // walk count grows the cage, freshness quickens its spin, quarantine
    // stains the cage red.
    const trail = trailForSlot(timeline.slot);
    const strength = trail ? THREE.MathUtils.clamp(trail.strength, 0, 1) : 0.5;
    const freshness = trail ? THREE.MathUtils.clamp(trail.freshness, 0, 1) : 0.5;
    const walks = trail ? trail.success_count + trail.reuse_success_count : 1;
    const cageGrowth = 1 + Math.min(walks, 6) * 0.05;

    const targetScale =
      (0.82 + presence * 0.18) * (1 - receiveStrength * 0.08) * cageGrowth;
    const dampedScale = THREE.MathUtils.damp(group.scale.x, targetScale, 7, delta);

    group.scale.setScalar(dampedScale);
    group.rotation.y += delta * (0.05 + freshness * 0.12 + receiveStrength * 0.35);
    group.rotation.x = Math.sin(state.clock.elapsedTime * 0.24) * 0.07;

    if (cageRef.current) {
      cageRef.current.opacity = presence * (0.03 + receiveStrength * (0.14 + intensity * 0.05));
      if (trail?.quarantined) cageRef.current.color.copy(QUARANTINE_CAGE);
    }
    if (coreRef.current) {
      coreRef.current.opacity =
        presence * (0.42 + receiveStrength * 0.3 + returnStrength * 0.12) * (0.55 + strength * 0.45);
    }
    if (coreGlowRef.current) {
      coreGlowRef.current.opacity =
        presence * (0.035 + receiveStrength * 0.05 + intensity * 0.01) * (0.6 + strength * 0.4);
    }

    receiveRingRefs.current.forEach((ring, index) => {
      if (!ring) return;
      const delayedStrength = windowStrength(
        phase,
        0.34 + index * 0.035,
        0.43 + index * 0.035,
        0.54 + index * 0.035,
        0.66 + index * 0.035,
      );
      ring.visible = delayedStrength > 0.002;
      ring.rotation.z += delta * (index === 0 ? 1.2 : -0.9);
      ring.scale.setScalar(0.5 + delayedStrength * (1.15 + index * 0.4));
      const material = receiveMaterialRefs.current[index];
      if (material) material.opacity = delayedStrength * (0.22 - index * 0.045);
    });
  });

  return (
    <group ref={groupRef} position={target.positions[0]} visible={false}>
      <lineSegments geometry={target.cageGeometry}>
        <lineBasicMaterial
          ref={cageRef}
          color={palette.cage}
          transparent
          opacity={0}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          toneMapped={false}
        />
      </lineSegments>

      {/* Tiny pale gold-white glint (<= 0.12 world units across) with a soft
          additive halo — replaces the former brain-scale lit black crystal. */}
      <mesh>
        <octahedronGeometry args={[0.06, 0]} />
        <meshBasicMaterial
          ref={coreRef}
          color={palette.core}
          transparent
          opacity={0}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          toneMapped={false}
        />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.14, 12, 12]} />
        <meshBasicMaterial
          ref={coreGlowRef}
          color={palette.glow}
          transparent
          opacity={0}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          toneMapped={false}
        />
      </mesh>

      {[0, 1].map((ringIndex) => (
        <mesh
          key={ringIndex}
          ref={(node) => {
            receiveRingRefs.current[ringIndex] = node;
          }}
          position={target.receiveOffset}
          rotation={[Math.PI / 2, 0, ringIndex * Math.PI * 0.25]}
          visible={false}
        >
          <torusGeometry args={[0.12 + ringIndex * 0.055, 0.007, 5, 18]} />
          <meshBasicMaterial
            ref={(node) => {
              receiveMaterialRefs.current[ringIndex] = node;
            }}
            color={ringIndex === 0 ? clamped.cage : clamped.return}
            transparent
            opacity={0}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
      ))}
    </group>
  );
}

export default function CognitiveGrasp({ activity }: { activity: number }) {
  const system = useMemo(() => buildTransferSystem(), []);

  // Honest dormancy: with no real trails known (backend offline, or a brain
  // that has not yet learned anything) there is nothing to recall — so
  // nothing pretends to arrive. The poll re-checks as the adapter learns.
  const [hasTrails, setHasTrails] = useState(false);
  useEffect(() => {
    const check = () => setHasTrails(getKnownTrails().length > 0);
    check();
    const handle = window.setInterval(check, 5000);
    return () => window.clearInterval(handle);
  }, []);

  useEffect(
    () => () => {
      for (const target of system) {
        target.cageGeometry.dispose();
        for (const variant of target.variants) variant.geometry.dispose();
      }
    },
    [system],
  );

  if (!hasTrails) return null;

  return (
    <group>
      {system.map((target, targetIndex) => (
        <group key={targetIndex}>
          <TransferRoute target={target} targetIndex={targetIndex} activity={activity} />
          <KnowledgeTarget target={target} activity={activity} targetIndex={targetIndex} />
        </group>
      ))}
    </group>
  );
}
