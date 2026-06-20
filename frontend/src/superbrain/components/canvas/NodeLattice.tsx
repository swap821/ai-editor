'use client';

/* -------------------------------------------------------------------------- */
/*  NodeLattice — the supercomputer NEUROLOGY inside the brain shape           */
/*                                                                            */
/*  Operator's vision: the cherished brain GLB *silhouette stays*; the         */
/*  INTERIOR becomes a living lattice of glowing, colorful COMPUTE NODES wired */
/*  together (a real topology), with signals firing node→node in the SAME     */
/*  fiber-optic packet language as the external NervousSystem bus. It is       */
/*  DATA-TRUE: the hubs are the four REAL anatomical work-anchors the engine   */
/*  already routes tools to (waveLabelForTool: CAUSAL/ARCHIVE/LATTICE/SIGNAL), */
/*  plus one clearly-authored central ROUTER/SECURITY bus node.                */
/*                                                                            */
/*  Build is PHASED (see .aios/state/NODE_BRAIN_RESEARCH.md). THIS is PHASE 1: */
/*  the STATIC lattice — prove the shape, glow, and distinct-from-tissue read  */
/*  in the operator's browser BEFORE deeper data wiring. P2 binds cognition-   */
/*  bus events to per-node firing (the activation path is live here); P3       */
/*  renders live skill-trail nodes; P4 adds the real backend graph-traversal   */
/*  capability. Nothing here publishes or mutates the bus — it is (and stays)  */
/*  a pure consumer of the shared SCENE_UNIFORMS.                              */
/*                                                                            */
/*  THREE draw calls only: 1 InstancedMesh (nodes) + 1 merged TubeGeometry     */
/*  (intra-region edges) + 1 merged TubeGeometry (the cross-region backbone    */
/*  bus). Energy-not-matter identity throughout: near-black carrier + additive */
/*  + depthWrite:false, exactly like the cortex filaments, NeuralAura and the  */
/*  fiber-optic bus — so it ADDS light to the cortex rather than occluding it. */
/*                                                                            */
/*  The DATA-TRUE topology is a PURE function (buildLatticeData) so it can be  */
/*  unit-tested independent of WebGL; the component only turns that data into  */
/*  THREE objects. FIDELITY: additive, his GLB/textures untouched, the canon   */
/*  cortex silhouette is preserved. Mounted by SuperbrainScene's BrainModel    */
/*  ONLY when `NODE_BRAIN === true`; flip that const off to restore the canon  */
/*  organ path byte-for-byte. Final call: HIS eyes.                            */
/*                                                                            */
/*  THE LAW (opening-motion + a11y):                                          */
/*   • uArrival drives a 3-beat COALESCENCE — nodes ignite ROUTER→outward,     */
/*     edges wipe in along their cables, first packets fire as breath settles. */
/*   • uReducedMotion freezes packet travel + snaps coalescence to assembled   */
/*     (still a lit, wired graph — just no motion).                           */
/*   • uBreath/uHold/uBurst ride for free from SCENE_UNIFORMS.                 */
/* -------------------------------------------------------------------------- */

import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { createSeededRandom } from '@/lib/seededRandom';
import { subscribeCognition } from '@/lib/cognitionBus';
import { fetchFactGraph, getKnownTrails } from '@/lib/aiosAdapter';
import type { FactEdge, TrailRow } from '@/lib/aiosAdapter';
import type { CognitionUniforms } from './SuperbrainScene';
import type { QualityTier } from '@/components/QualityTierProvider';

const TAU = Math.PI * 2;

/* ---------------------------------------------------------------------------
 * Brain-group-local bounds of /models/brain.glb (root scale 0.01) — IDENTICAL
 * to the constants in SuperbrainScene. Nodes live in this same space (the
 * lattice mounts as a child of the BrainModel group, so the group's
 * BRAIN_SCALE/rotation/drift carry it for free — like CorticalSignals).
 * ------------------------------------------------------------------------- */
const BRAIN_MIN = new THREE.Vector3(-0.379, -0.222, -0.439);
const BRAIN_MAX = new THREE.Vector3(0.382, 0.633, 0.553);
const BRAIN_CENTER = new THREE.Vector3().addVectors(BRAIN_MIN, BRAIN_MAX).multiplyScalar(0.5);
/** Risk R1 (clipping through the non-box mesh): keep placement 15% inward of
 *  the bounding box for Phase 1. A three-mesh-bvh inside-test is a later phase
 *  IF the operator sees leaks — the inward margin is the cheap honest first move. */
const INWARD = 0.85;

/* ---------------------------------------------------------------------------
 * THE HUBS — 4 REAL anatomical anchors (verbatim from SuperbrainScene's
 * WAVE_REGION_ANCHORS, ANTERIOR_SIGN=+1) + 1 AUTHORED central bus node.
 * Colors are the brain's own baked region palette, so the lattice reads as the
 * same organism. (Research correction #1: there is NO 5th data anchor — the
 * ROUTER node is a deliberately authored interior position, NOT a real anchor.)
 * ------------------------------------------------------------------------- */
export interface Hub {
  key: string;
  /** brain-group-local position */
  pos: THREE.Vector3;
  color: string;
  /** the work this lobe owns (waveLabelForTool routing), for P2 wiring */
  routes: string;
  authored?: boolean;
}

export const HUBS: Hub[] = [
  { key: 'CAUSAL', pos: new THREE.Vector3(0.0, 0.26, 0.48), color: '#ff3b28', routes: 'plan/skill/recall/memory' }, // frontal
  { key: 'ARCHIVE', pos: new THREE.Vector3(0.34, 0.16, 0.11), color: '#36f07a', routes: 'read/search/list/web/fetch' }, // temporal
  { key: 'LATTICE', pos: new THREE.Vector3(0.0, 0.61, 0.11), color: '#19d4f0', routes: 'create/edit/write/exec/verify' }, // parietal crown
  { key: 'SIGNAL', pos: new THREE.Vector3(0.05, 0.31, -0.38), color: '#9b3bff', routes: 'signal/route/security' }, // occipital
  // AUTHORED (not a data anchor): the central compute/router bus the four lobes feed.
  { key: 'ROUTER', pos: BRAIN_CENTER.clone(), color: '#6a35ff', routes: 'router/provider/security spine', authored: true },
];

/* ---------------------------------------------------------------------------
 * TUNABLES — the operator's dials. Every visual knob lives here so the look
 * can be retuned without hunting through shader strings.
 * ------------------------------------------------------------------------- */
/** Tier budget — conservative for a 16GB box (matches NODE_BRAIN_RESEARCH).
 *  Total NODE_COUNT = (HUBS.length) + (HUBS.length × satellites). */
export const SATELLITES_PER_HUB: Record<QualityTier, number> = { high: 24, medium: 16, low: 3 };
/** EDGE topology density: k-nearest INTRA-cluster links per satellite
 *  (cross-region links are backbone-only — R2). 0 = spokes only. */
export const EDGE_K: Record<QualityTier, number> = { high: 3, medium: 2, low: 0 };

/** NODE_SIZE — energy-sphere radii (brain-group-local units). */
const HUB_RADIUS = 0.05;
const SAT_RADIUS = 0.03;
/** EDGE_MAX_DIST proxy: satellite scatter radius around each hub. Clusters stay
 *  distinct (R2); intra-cluster k-NN only ever links within this sphere. */
const LOBE_RADIUS = 0.11;
/** GLOW levers (idle brightness; firing/burst push past the bloom knee). */
const NODE_GAIN = 0.7; // idle node brightness — keep BELOW the PostFX bloom knee
const EDGE_CARRIER_GAIN = 4.0; // lobe-wire always-visible (dial down if too web-like)
const BACKBONE_CARRIER_GAIN = 4.5; // major bus slightly brighter than lobe edges
const SIGNAL_GAIN = 3.0; // packet peak luma >> 1 so glitters cross the bloom knee
/** FLOW_SPEED — packet travel multipliers (per-edge speed jitter on top). */
const EDGE_TUBE_RADIUS = 0.0034;
const BACKBONE_TUBE_RADIUS = 0.005;

/** Map a tool name to the hub whose lobe owns that kind of work — MIRRORS
 *  SuperbrainScene.waveLabelForTool so the lattice and the cortex agree on
 *  which region a given tool lights. */
export function hubKeyForTool(tool: string): string {
  const t = tool.toLowerCase();
  if (/plan|orchestr|skill|recall|memory|lesson/.test(t)) return 'CAUSAL';
  if (/read|search|list|web|fetch|grep|inspect/.test(t)) return 'ARCHIVE';
  if (/create|edit|write|exec|verify|run|build/.test(t)) return 'LATTICE';
  return 'SIGNAL';
}

/** Which hub a REAL cognition-bus event should fire: a HUBS index, -1 for ALL
 *  hubs (a whole-organism pulse), or null for events the lattice ignores.
 *  DATA-TRUE — keyed off the real bus events + the engine's own tool->lobe
 *  routing (see WORKING_BRAIN_CANON_RESEARCH §1.2). The lattice is a pure
 *  SUBSCRIBER: it never publishes and never adds bus types. */
export function hubIndexForEvent(event: { type: string; label?: string; detail?: string }): number | null {
  const idx = (key: string) => HUBS.findIndex((h) => h.key === key);
  const label = event.label ?? '';
  const detail = event.detail ?? '';
  switch (event.type) {
    case 'route':
      return idx('ROUTER');
    case 'directive':
    case 'synthesis':
    case 'burst':
      return -1; // whole-organism pulse
    case 'agent-dispatch': {
      const m = detail.match(/tool engaged: (.+)/);
      if (m) return idx(hubKeyForTool(m[1]));
      if (/caste online/i.test(detail) || /INTENT|TRAIL WEAKENED/i.test(label)) return idx('CAUSAL');
      return idx('SIGNAL');
    }
    case 'knowledge-acquired': {
      if (/VERIFICATION/i.test(label)) return idx('LATTICE');
      if (/SKILL MASTERED|CAPABILITY EARNED|AUTONOMOUS/i.test(label) || /trail #/i.test(detail)) return idx('CAUSAL');
      if (/SIGNAL|TITAN/i.test(label)) return idx('SIGNAL');
      if (/ARCHIVE|MYTHOS|MEMORY/i.test(label)) return idx('ARCHIVE');
      if (/CAUSAL|GRAPH|DELTA/i.test(label)) return idx('CAUSAL');
      if (/SEMANTIC|LATTICE/i.test(label)) return idx('LATTICE');
      return idx('ARCHIVE'); // generic knowledge intake -> the archive lobe
    }
    default:
      return null; // approval-required/-resolved (uHold handles), telemetry, voice-speaking
  }
}

/* ---------------------------------------------------------------------------
 * PURE DATA MODEL (no THREE rendering) — unit-testable. The component below
 * turns this into InstancedMesh / merged TubeGeometry edges + backbone.
 * ------------------------------------------------------------------------- */
export interface LatticeNode {
  pos: THREE.Vector3;
  color: THREE.Color;
  radius: number;
  /** index into HUBS this node belongs to */
  hub: number;
  isHub: boolean;
  /** 0..1 normalized distance from BRAIN_CENTER — the COALESCENCE ignite delay
   *  (ROUTER core lights first, the four lobes bloom outward). Baked once. */
  igniteDelay: number;
}
export interface LatticeEdge {
  /** endpoint position refs (shared with the owning nodes) */
  a: THREE.Vector3;
  b: THREE.Vector3;
  color: THREE.Color;
  phase: number;
  speed: number;
}
export interface LatticeData {
  nodes: LatticeNode[];
  edges: LatticeEdge[];
}

/** Uniform direction on the unit sphere from a seeded PRNG. */
function randomUnit(rng: () => number): THREE.Vector3 {
  const u = rng() * 2 - 1;
  const t = rng() * TAU;
  const s = Math.sqrt(Math.max(0, 1 - u * u));
  return new THREE.Vector3(s * Math.cos(t), s * Math.sin(t), u);
}

/** Clamp a point to 15% inside the brain bounding box (R1). */
function clampInward(p: THREE.Vector3): void {
  const lo = new THREE.Vector3().lerpVectors(BRAIN_CENTER, BRAIN_MIN, INWARD);
  const hi = new THREE.Vector3().lerpVectors(BRAIN_CENTER, BRAIN_MAX, INWARD);
  p.x = THREE.MathUtils.clamp(p.x, lo.x, hi.x);
  p.y = THREE.MathUtils.clamp(p.y, lo.y, hi.y);
  p.z = THREE.MathUtils.clamp(p.z, lo.z, hi.z);
}

/** Largest center→corner distance of the inward-clamped box. Normalizes the
 *  per-node ignite delay into 0..1 so coalescence is resolution-independent. */
const MAX_CENTER_DIST = (() => {
  const lo = new THREE.Vector3().lerpVectors(BRAIN_CENTER, BRAIN_MIN, INWARD);
  const hi = new THREE.Vector3().lerpVectors(BRAIN_CENTER, BRAIN_MAX, INWARD);
  return Math.max(BRAIN_CENTER.distanceTo(lo), BRAIN_CENTER.distanceTo(hi));
})();

/** Max real nodes before we cap (prevents InstancedMesh explosion on big graphs). */
const MAX_REAL_NODES = 160;

/** Deterministic integer hash of a string — used to assign entities to hubs
 *  and to seed per-entity positional jitter. Stable across reloads. */
function strHash(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h;
}

/** Real-data input for buildLatticeData. Both fields are optional; whichever
 *  is non-empty first wins (graph > trails > synthetic). */
export interface RealLatticeData {
  graphEdges?: FactEdge[];
  trails?: TrailRow[];
}

/**
 * Build the DATA-TRUE lattice topology. Deterministic (seeded) so mounts and
 * screenshot baselines stay identical.
 *
 * Priority: real.graphEdges → real.trails → synthetic fallback.
 * Edges are STRICTLY intra-region (each lobe is a distinct cluster) in the
 * synthetic path; cross-region connection is the backbone only.
 */
export function buildLatticeData(tier: QualityTier, real?: RealLatticeData): LatticeData {
  // House rule: never unseeded randomness.
  const random = createSeededRandom(0x4e4f4445); // "NODE"

  const igniteDelayFor = (p: THREE.Vector3) =>
    THREE.MathUtils.clamp(BRAIN_CENTER.distanceTo(p) / MAX_CENTER_DIST, 0, 1);

  /* ================================================================
   * BRANCH A — knowledge-graph edges (subject → predicate → object)
   * ============================================================== */
  if (real?.graphEdges && real.graphEdges.length > 0) {
    // Collect unique entity strings (subjects + objects).
    const entitySet = new Set<string>();
    for (const e of real.graphEdges) {
      entitySet.add(e.subject);
      entitySet.add(e.object);
    }
    // Cap: prefer shallowest entities (depth 1 before depth 2, etc.).
    // We use a stable sort keyed on the min depth the entity appears at.
    const depthOf = new Map<string, number>();
    for (const e of real.graphEdges) {
      depthOf.set(e.subject, Math.min(depthOf.get(e.subject) ?? 99, e.depth));
      depthOf.set(e.object, Math.min(depthOf.get(e.object) ?? 99, e.depth));
    }
    let entities = Array.from(entitySet).sort(
      (a, b) => (depthOf.get(a) ?? 0) - (depthOf.get(b) ?? 0),
    );
    if (entities.length > MAX_REAL_NODES) entities = entities.slice(0, MAX_REAL_NODES);

    // Build one LatticeNode per entity.
    const posMap = new Map<string, THREE.Vector3>();
    const nodes: LatticeNode[] = [];
    for (const entity of entities) {
      const h = strHash(entity);
      const hi = h % HUBS.length;
      const hub = HUBS[hi];
      // Seeded offset inside LOBE_RADIUS so positions are stable across re-renders.
      const rng = createSeededRandom(h);
      const dir = randomUnit(rng);
      const r = LOBE_RADIUS * Math.cbrt(rng());
      const pos = hub.pos.clone().addScaledVector(dir, r);
      clampInward(pos);
      posMap.set(entity, pos);
      const depth = depthOf.get(entity) ?? 1;
      nodes.push({
        pos,
        color: new THREE.Color(hub.color),
        radius: SAT_RADIUS,
        hub: hi,
        isHub: false,
        igniteDelay: THREE.MathUtils.clamp(depth / 3, 0, 1),
      });
    }

    // Build one LatticeEdge per fact (subject→object pair in entity set).
    const edgeRng = createSeededRandom(0x46415445); // "FATE"
    const edges: LatticeEdge[] = [];
    const entityInSet = new Set(entities);
    for (const e of real.graphEdges) {
      if (!entityInSet.has(e.subject) || !entityInSet.has(e.object)) continue;
      const a = posMap.get(e.subject)!;
      const b = posMap.get(e.object)!;
      const hi = strHash(e.subject) % HUBS.length;
      const color = new THREE.Color(HUBS[hi].color).multiplyScalar(0.85);
      edges.push({ a, b, color, phase: edgeRng() * TAU, speed: 0.5 + edgeRng() * 1.5 });
    }
    return { nodes, edges };
  }

  /* ================================================================
   * BRANCH B — live skill-trail nodes (pheromone map)
   * ============================================================== */
  if (real?.trails && real.trails.length > 0) {
    // Cap: prefer strongest (highest strength) trails.
    let trails = [...real.trails].sort((a, b) => b.strength - a.strength);
    if (trails.length > MAX_REAL_NODES) trails = trails.slice(0, MAX_REAL_NODES);

    const nodes: LatticeNode[] = [];
    const posBySkill = new Map<number, THREE.Vector3>();
    for (const t of trails) {
      const hi = strHash(t.goal_pattern) % HUBS.length;
      const hub = HUBS[hi];
      const rng = createSeededRandom(strHash(String(t.skill_id)));
      const dir = randomUnit(rng);
      const r = LOBE_RADIUS * Math.cbrt(rng());
      const pos = hub.pos.clone().addScaledVector(dir, r);
      clampInward(pos);
      posBySkill.set(t.skill_id, pos);
      nodes.push({
        pos,
        color: new THREE.Color(hub.color),
        radius: SAT_RADIUS * (0.6 + THREE.MathUtils.clamp(t.strength, 0, 1) * 0.8),
        hub: hi,
        isHub: false,
        igniteDelay: THREE.MathUtils.clamp(1 - t.freshness, 0, 1),
      });
    }

    // Edges: link trails that share the same hub to their 1-2 nearest same-hub peers.
    const edgeRng = createSeededRandom(0x54524c53); // "TRLS"
    const edges: LatticeEdge[] = [];
    const seen = new Set<string>();
    for (let i = 0; i < trails.length; i++) {
      const ti = trails[i];
      const hiI = strHash(ti.goal_pattern) % HUBS.length;
      const posI = posBySkill.get(ti.skill_id)!;
      // Find up to 2 nearest same-hub peers.
      const peers = trails
        .map((tj, j) => ({
          j,
          hi: strHash(tj.goal_pattern) % HUBS.length,
          d: posI.distanceTo(posBySkill.get(tj.skill_id)!),
        }))
        .filter((x) => x.j !== i && x.hi === hiI)
        .sort((a, b) => a.d - b.d)
        .slice(0, 2);
      for (const { j } of peers) {
        const key = i < j ? `${i}-${j}` : `${j}-${i}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const posJ = posBySkill.get(trails[j].skill_id)!;
        const color = new THREE.Color(HUBS[hiI].color).multiplyScalar(0.8);
        edges.push({ a: posI, b: posJ, color, phase: edgeRng() * TAU, speed: 0.4 + edgeRng() });
      }
    }
    return { nodes, edges };
  }

  /* ================================================================
   * BRANCH C — synthetic fallback (original implementation, unchanged)
   * ============================================================== */

  /* ---- nodes: 1 hub per anchor + tier-budgeted satellites per lobe ---- */
  const nodes: LatticeNode[] = [];
  HUBS.forEach((hub, hi) => {
    const pos = hub.pos.clone();
    nodes.push({
      pos,
      color: new THREE.Color(hub.color),
      radius: HUB_RADIUS,
      hub: hi,
      isHub: true,
      igniteDelay: igniteDelayFor(pos),
    });
  });
  const satN = SATELLITES_PER_HUB[tier];
  HUBS.forEach((hub, hi) => {
    const base = new THREE.Color(hub.color);
    for (let s = 0; s < satN; s++) {
      // Uniform-in-sphere scatter (cbrt for even volume density).
      const dir = randomUnit(random);
      const r = LOBE_RADIUS * Math.cbrt(random());
      const p = hub.pos.clone().addScaledVector(dir, r);
      clampInward(p);
      // Slight per-node value variation gives the cluster depth.
      const c = base.clone().multiplyScalar(0.7 + random() * 0.5);
      nodes.push({
        pos: p,
        color: c,
        radius: SAT_RADIUS * (0.8 + random() * 0.5),
        hub: hi,
        isHub: false,
        igniteDelay: igniteDelayFor(p),
      });
    }
  });

  /* ---- edges: hub→satellite spokes + k-nearest INTRA-cluster links ---- */
  const edges: LatticeEdge[] = [];
  const k = EDGE_K[tier];
  HUBS.forEach((hub, hi) => {
    const hubNode = nodes.find((n) => n.hub === hi && n.isHub)!;
    const cluster = nodes.filter((n) => n.hub === hi && !n.isHub);
    const hubColor = new THREE.Color(hub.color);
    const pushEdge = (a: THREE.Vector3, b: THREE.Vector3, color: THREE.Color) =>
      edges.push({ a, b, color, phase: random() * TAU, speed: 0.5 + random() * 1.5 });

    // Spokes: every satellite links to its hub.
    cluster.forEach((sat) => pushEdge(hubNode.pos, sat.pos, hubColor));

    // k-nearest links within the cluster (deduped, intra-region only).
    if (k > 0) {
      const seen = new Set<string>();
      cluster.forEach((sat, si) => {
        const near = cluster
          .map((o, oi) => ({ oi, d: sat.pos.distanceTo(o.pos) }))
          .filter((x) => x.oi !== si)
          .sort((a, b) => a.d - b.d)
          .slice(0, k);
        near.forEach(({ oi }) => {
          const key = si < oi ? `${si}-${oi}` : `${oi}-${si}`;
          if (seen.has(key)) return;
          seen.add(key);
          pushEdge(sat.pos, cluster[oi].pos, hubColor.clone().multiplyScalar(0.85));
        });
      });
    }
  });

  return { nodes, edges };
}

/* ---------------------------------------------------------------------------
 * Shaders. The edge + backbone fragment is a VERBATIM copy of NervousSystem's
 * WIRE_FRAGMENT (plus the reduced-motion + arrival deltas required by THE LAW)
 * — a lattice packet and a nervous-bus packet MUST be the same visual language
 * (internal circuit + external spinal bundle = one nervous infrastructure).
 * KEEP IN SYNC if NervousSystem.tsx's WIRE_FRAGMENT changes. (Copied, not
 * imported, to avoid touching the frozen nerve component.)
 * ------------------------------------------------------------------------- */

// Edge + backbone vertex (TubeGeometry): the built-in uv.x runs along the tube, so it
// is the travel coordinate directly (same as NervousSystem's WIRE_VERTEX).
const BACKBONE_VERTEX = /* glsl */ `
  attribute vec3 aWireColor;
  attribute float aPhase;
  attribute float aSpeed;

  varying vec2 vUv;
  varying vec3 vColor;
  varying float vPhase;
  varying float vSpeed;

  void main() {
    vUv = uv;
    vColor = aWireColor;
    vPhase = aPhase;
    vSpeed = aSpeed;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

// Adapted from NervousSystem.tsx WIRE_FRAGMENT (same packet visual language).
// NervousSystem additionally multiplies flowTime by a directional uFlowDir
// (data-true I/O: knowledge up / directives down); the lattice keeps its flow
// one-directional, so this copy intentionally omits uFlowDir. Keep the packet
// math in sync if NervousSystem's changes.
//
// LAW deltas vs. the lab/NervousSystem copy:
//  • uReducedMotion freezes packet travel (settles to a static dim/bright
//    dither — the graph stays LIT and WIRED, it just stops flowing).
//  • uArrival wipes each cable in along its own length (edges snap into place
//    only after the nodes they join have ignited).
const WIRE_FRAGMENT = /* glsl */ `
  uniform float uTime;
  uniform float uBurst;
  uniform float uHold;
  uniform float uSignalGain;
  uniform float uCarrierGain; // lifts the dim wire so the GRAPH reads even between packets
  uniform float uArrival;       // 0 settled .. 1 arriving (coalescence wipe)
  uniform float uReducedMotion; // 1 = no packet travel (a11y)

  varying vec2 vUv;
  varying vec3 vColor;
  varying float vPhase;
  varying float vSpeed;

  void main() {
    // FIBER-OPTIC identity: a near-black whispered carrier (the cable body) with
    // bright packets racing on top. uCarrierGain lifts the carrier just enough
    // that the connection itself is faintly ALWAYS visible — so the lattice
    // reads as a WIRED graph, not isolated dots.
    vec3 carrier = vColor * 0.08 * uCarrierGain;

    // Discrete light-bead (packet) racing root→tip. Flow time is gated by
    // (1.0 - uHold) AND (1.0 - uReducedMotion): when either is 1 the fract
    // freezes, packets stop mid-cable — the "waiting on you" hold + the a11y
    // calm both read as a still, lit graph.
    float motion = (1.0 - uHold) * (1.0 - uReducedMotion);
    float flowTime = uTime * vSpeed * motion;
    float flow = fract(vUv.x * 4.0 - flowTime + vPhase);

    // Hard sparse bead — tight window, NO wake term. ~90% of each wire is dark
    // at any frame → mitigates additive stack-up.
    float packet = smoothstep(0.86, 0.90, flow) * smoothstep(0.98, 0.94, flow);

    // Signal color: pure cyan at idle, shifts toward white on real burst. Gain
    // pushes peak luma >> 1.0 so the bead crosses the bloom knee.
    vec3 signal = mix(vec3(0.0, 1.0, 1.0), vec3(1.0), uBurst);
    vec3 finalColor = carrier + signal * packet * uSignalGain;

    // Burst surge: doubles intensity + whitens signal.
    finalColor *= (1.0 + uBurst * 2.5);

    // Hold dim: approval pause freezes packets (time gate above) AND dims the
    // residual carrier to near-zero — the bus goes dark while the mind defers.
    finalColor *= mix(1.0, 0.2, uHold);

    // ── COALESCENCE wipe (additive: uArrival==0 -> canon settled wire) ──
    // The cable draws in along its own length. progress runs 0..1 as arrival
    // sweeps 1 -> 0, but only after a 0.4 lead-in (so a wire appears AFTER the
    // nodes it joins have started igniting): visible front = step(vUv.x, front).
    float front = clamp(((1.0 - uArrival) - 0.4) / 0.6, 0.0, 1.0);
    float wipe = (uArrival <= 0.0) ? 1.0 : step(vUv.x, front);
    finalColor *= wipe;

    // Hard physical cut at the endpoints (no fading into the nodes).
    if (vUv.x < 0.005 || vUv.x > 0.995) discard;

    gl_FragColor = vec4(finalColor, 1.0);
  }
`;

// NODE shader — glowing energy-sphere: dim region-hued core + bright fresnel
// halo. Idle stays BELOW the bloom knee (uNodeGain lever); the scene burst
// lifts every node past it (per-node firing is live below). instanceColor +
// instanceMatrix are injected by three's instancing prefix on InstancedMesh.
const NODE_VERTEX = /* glsl */ `
  attribute float aActivation;
  attribute float aIgniteDelay;

  varying vec3 vColor;
  varying vec3 vNormalV;
  varying vec3 vViewDirV;
  varying float vActivation;
  varying float vIgniteDelay;

  void main() {
    #ifdef USE_INSTANCING_COLOR
      vColor = instanceColor;
    #else
      vColor = vec3(0.0, 1.0, 1.0);
    #endif
    vActivation = aActivation;
    vIgniteDelay = aIgniteDelay;
    vec4 mvPosition = modelViewMatrix * instanceMatrix * vec4(position, 1.0);
    vNormalV = normalize(normalMatrix * mat3(instanceMatrix) * normal);
    vViewDirV = -mvPosition.xyz;
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const NODE_FRAGMENT = /* glsl */ `
  uniform float uBurst;
  uniform float uHold;
  uniform float uNodeGain;
  uniform float uArrival; // 0 settled .. 1 arriving (coalescence ignite)

  varying vec3 vColor;
  varying vec3 vNormalV;
  varying vec3 vViewDirV;
  varying float vActivation;
  varying float vIgniteDelay;

  void main() {
    vec3 N = normalize(vNormalV);
    vec3 V = normalize(vViewDirV);
    float fres = pow(1.0 - clamp(dot(N, V), 0.0, 1.0), 2.5);

    // Energy sphere: dim core + bright region-hued fresnel halo.
    vec3 core = vColor * 0.55;
    vec3 rim = vColor * fres * 1.35;
    vec3 col = (core + rim) * uNodeGain;

    // P2 — DATA-TRUE per-node firing: when this node's hub ran its kind of real
    // work, surge in the node's own hue (crossing the bloom knee) + whiten the
    // core. This is the lattice "thinking" region-by-region on live events.
    float act = clamp(vActivation, 0.0, 1.0);
    col += vColor * act * 2.2;
    col = mix(col, vec3(1.0), act * 0.5);

    // Whole-organism pulse on directive / synthesis / burst events.
    col = mix(col, vec3(1.0), uBurst * 0.5);
    col *= (1.0 + uBurst * 1.8);

    // Approval hold: defer to amber + dim, mirroring the cortex and the bus.
    vec3 amber = vec3(1.0, 0.62, 0.22);
    col = mix(col, col * amber + amber * 0.04, uHold * 0.85);
    col *= mix(1.0, 0.4, uHold);

    // ── COALESCENCE ignite (additive: uArrival==0 -> fully lit) ──
    // The computer powers on from the ROUTER core outward: each node fades up
    // over a 0.25 window starting at its own normalized distance-from-center,
    // measured against (1.0 - uArrival) so the wave sweeps as arrival -> 0.
    float ignite = (uArrival <= 0.0)
      ? 1.0
      : smoothstep(vIgniteDelay, vIgniteDelay + 0.25, 1.0 - uArrival);
    col *= ignite;
    // A small spark overshoot exactly at the ignition front.
    col += vColor * pow(ignite, 4.0) * (1.0 - ignite) * 3.0;

    gl_FragColor = vec4(col, 1.0);
  }
`;

/** A near-black teal carrier for the backbone (packets are cyan regardless). */
const BACKBONE_TINT = new THREE.Color('#0a3a44');

export default function NodeLattice({
  uniforms,
  tier = 'high',
  reducedMotion = false,
}: {
  uniforms: CognitionUniforms;
  tier?: QualityTier;
  /** a11y: when true, packets freeze and coalescence is assembled (no travel). */
  reducedMotion?: boolean;
}) {
  // One shared lever the frame loop writes; both wire materials + the node
  // material read it. Snapping it (vs. a per-material literal) keeps the three
  // draw calls in lock-step and lets reduced-motion be honored live.
  const reducedMotionUniform = useRef({ value: reducedMotion ? 1 : 0 });
  reducedMotionUniform.current.value = reducedMotion ? 1 : 0;

  // ── REAL-DATA self-fetch ──────────────────────────────────────────────────
  // Mount once: try knowledge-graph, fall back to trails. If both are empty,
  // `real` stays undefined → synthetic fallback in buildLatticeData.
  // Re-fetch on every `telemetry` cognition event (debounced: only one
  // in-flight fetch at a time via the fetchingRef guard).
  const [real, setReal] = useState<RealLatticeData | undefined>(undefined);
  const fetchingRef = useRef(false);

  const doFetch = () => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    void (async () => {
      try {
        const [graphEdges, trails] = await Promise.all([
          fetchFactGraph('project', 2),
          Promise.resolve(getKnownTrails() as TrailRow[]),
        ]);
        // Only set real if we have actual data — keeps synthetic alive offline.
        if (graphEdges.length > 0 || trails.length > 0) {
          setReal({ graphEdges, trails });
        }
      } finally {
        fetchingRef.current = false;
      }
    })();
  };

  // Initial fetch on mount.
  useEffect(() => {
    doFetch();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-fetch on telemetry events (trails may have grown since mount).
  useEffect(() => {
    return subscribeCognition((event) => {
      if (event.type === 'telemetry') {
        doFetch();
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // ─────────────────────────────────────────────────────────────────────────

  const built = useMemo(() => {
    const { nodes, edges } = buildLatticeData(tier, real);

    /* ---- 1. NODES → InstancedMesh ---- */
    const nodeGeo = new THREE.IcosahedronGeometry(1, 1); // unit; per-instance scale = radius
    const nodeMat = new THREE.ShaderMaterial({
      vertexShader: NODE_VERTEX,
      fragmentShader: NODE_FRAGMENT,
      uniforms: {
        uBurst: uniforms.uBurst,
        uHold: uniforms.uHold,
        uArrival: uniforms.uArrival,
        uNodeGain: { value: NODE_GAIN }, // idle-brightness lever (keep idle below knee)
      },
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      // depthTest off so the glowing interior reads THROUGH the (now glass)
      // cortex shell — an x-ray of the living circuitry. Tuning point for HIS eyes.
      depthTest: false,
      toneMapped: false,
    });
    const nodeMesh = new THREE.InstancedMesh(nodeGeo, nodeMat, nodes.length);
    const dummy = new THREE.Object3D();
    const colorArray = new Float32Array(nodes.length * 3);
    nodes.forEach((n, i) => {
      dummy.position.copy(n.pos);
      dummy.scale.setScalar(n.radius);
      dummy.updateMatrix();
      nodeMesh.setMatrixAt(i, dummy.matrix);
      colorArray[i * 3] = n.color.r;
      colorArray[i * 3 + 1] = n.color.g;
      colorArray[i * 3 + 2] = n.color.b;
    });
    nodeMesh.instanceColor = new THREE.InstancedBufferAttribute(colorArray, 3);
    nodeMesh.instanceMatrix.needsUpdate = true;
    nodeMesh.frustumCulled = false;
    nodeMesh.renderOrder = 4;

    // P2 — per-node firing: a 0..1 activation per instance, bumped when this
    // node's hub runs its kind of real work, decayed each frame. Dynamic
    // instanced attribute the node shader reads as aActivation.
    const activationArr = new Float32Array(nodes.length);
    const activationAttr = new THREE.InstancedBufferAttribute(activationArr, 1);
    activationAttr.setUsage(THREE.DynamicDrawUsage);
    nodeGeo.setAttribute('aActivation', activationAttr);

    // COALESCENCE: static per-instance ignite delay (router→out). Baked once.
    const igniteArr = new Float32Array(nodes.map((n) => n.igniteDelay));
    nodeGeo.setAttribute('aIgniteDelay', new THREE.InstancedBufferAttribute(igniteArr, 1));

    const hubOfInstance = new Int8Array(nodes.map((n) => n.hub));

    /* ---- 2. EDGES → merged thin tubes (legible "wired graph") ---- */
    // 1px LineSegments were near-invisible (esp. additive over a busy scene);
    // thin tubes read as actual connections. Same WIRE shader + tube-uv vertex
    // as the backbone, so packets travel identically. One merged draw call.
    const edgeTubes: THREE.BufferGeometry[] = [];
    edges.forEach((e) => {
      const g = new THREE.TubeGeometry(new THREE.LineCurve3(e.a.clone(), e.b.clone()), 1, EDGE_TUBE_RADIUS, 5, false);
      const vc = g.attributes.position.count;
      const cArr = new Float32Array(vc * 3);
      const pArr = new Float32Array(vc);
      const sArr = new Float32Array(vc);
      for (let i = 0; i < vc; i++) {
        cArr[i * 3] = e.color.r;
        cArr[i * 3 + 1] = e.color.g;
        cArr[i * 3 + 2] = e.color.b;
        pArr[i] = e.phase;
        sArr[i] = e.speed;
      }
      g.setAttribute('aWireColor', new THREE.BufferAttribute(cArr, 3));
      g.setAttribute('aPhase', new THREE.BufferAttribute(pArr, 1));
      g.setAttribute('aSpeed', new THREE.BufferAttribute(sArr, 1));
      edgeTubes.push(g);
    });
    const edgeGeo = mergeGeometries(edgeTubes);
    edgeTubes.forEach((g) => g.dispose());
    const edgeMat = new THREE.ShaderMaterial({
      vertexShader: BACKBONE_VERTEX,
      fragmentShader: WIRE_FRAGMENT,
      uniforms: {
        uTime: uniforms.uTime,
        uBurst: uniforms.uBurst,
        uHold: uniforms.uHold,
        uArrival: uniforms.uArrival,
        uReducedMotion: reducedMotionUniform.current,
        uSignalGain: { value: SIGNAL_GAIN },
        uCarrierGain: { value: EDGE_CARRIER_GAIN }, // wires always-visible = the graph reads (dial down if too web-like)
      },
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      depthTest: false,
    });
    const edgeMesh = new THREE.Mesh(edgeGeo, edgeMat);
    edgeMesh.frustumCulled = false;
    edgeMesh.renderOrder = 4;

    /* ---- 3. BACKBONE → merged tubes (center ROUTER → each anatomical hub) ---- */
    const bbRandom = createSeededRandom(0x4242424e); // "BBBN" — own deterministic stream
    const router = HUBS[HUBS.length - 1];
    const tubeGeoms: THREE.BufferGeometry[] = [];
    for (let i = 0; i < HUBS.length - 1; i++) {
      const hub = HUBS[i];
      const mid = new THREE.Vector3().lerpVectors(router.pos, hub.pos, 0.5);
      // Slight bow so the four buses don't read as flat spokes.
      mid.addScaledVector(randomUnit(bbRandom), 0.03);
      const curve = new THREE.CatmullRomCurve3([router.pos.clone(), mid, hub.pos.clone()]);
      const g = new THREE.TubeGeometry(curve, 32, BACKBONE_TUBE_RADIUS, 6, false);
      const vc = g.attributes.position.count;
      const cArr = new Float32Array(vc * 3);
      const pArr = new Float32Array(vc);
      const sArr = new Float32Array(vc);
      const phase = bbRandom() * TAU;
      const speed = 0.4 + bbRandom() * 0.8; // backbone pulses slower (major bus)
      for (let v = 0; v < vc; v++) {
        cArr[v * 3] = BACKBONE_TINT.r;
        cArr[v * 3 + 1] = BACKBONE_TINT.g;
        cArr[v * 3 + 2] = BACKBONE_TINT.b;
        pArr[v] = phase;
        sArr[v] = speed;
      }
      g.setAttribute('aWireColor', new THREE.BufferAttribute(cArr, 3));
      g.setAttribute('aPhase', new THREE.BufferAttribute(pArr, 1));
      g.setAttribute('aSpeed', new THREE.BufferAttribute(sArr, 1));
      tubeGeoms.push(g);
    }
    const backboneGeo = mergeGeometries(tubeGeoms);
    tubeGeoms.forEach((g) => g.dispose());
    const backboneMat = new THREE.ShaderMaterial({
      vertexShader: BACKBONE_VERTEX,
      fragmentShader: WIRE_FRAGMENT,
      uniforms: {
        uTime: uniforms.uTime,
        uBurst: uniforms.uBurst,
        uHold: uniforms.uHold,
        uArrival: uniforms.uArrival,
        uReducedMotion: reducedMotionUniform.current,
        uSignalGain: { value: SIGNAL_GAIN },
        uCarrierGain: { value: BACKBONE_CARRIER_GAIN }, // the major bus: wire slightly brighter than the edges
      },
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      depthTest: false,
    });
    const backboneMesh = new THREE.Mesh(backboneGeo, backboneMat);
    backboneMesh.frustumCulled = false;
    backboneMesh.renderOrder = 4;

    return {
      nodeMesh, nodeGeo, nodeMat, edgeMesh, edgeGeo, edgeMat, backboneMesh, backboneGeo, backboneMat,
      activationArr, activationAttr, hubOfInstance,
    };
  }, [uniforms, tier, real]);

  // P2 — live firing: bump the activation of the hub a real cognition event maps
  // to (DATA-TRUE; same tool->lobe routing the cortex uses), then decay it each
  // frame. The lattice stays a pure SUBSCRIBER. useFrame is a no-op while idle.
  const firingRef = useRef(false);
  useEffect(() => {
    const { activationArr, hubOfInstance } = built;
    return subscribeCognition((event) => {
      const target = hubIndexForEvent(event);
      if (target === null) return;
      const amount = target === -1 ? 0.6 : 1.0;
      for (let i = 0; i < activationArr.length; i++) {
        if ((target === -1 || hubOfInstance[i] === target) && activationArr[i] < amount) {
          activationArr[i] = amount;
        }
      }
      firingRef.current = true;
    });
  }, [built]);

  useFrame(() => {
    if (!firingRef.current) return;
    const { activationArr, activationAttr } = built;
    let maxAct = 0;
    for (let i = 0; i < activationArr.length; i++) {
      const a = activationArr[i] * 0.93; // ~0.5s firing pulse
      activationArr[i] = a;
      if (a > maxAct) maxAct = a;
    }
    if (maxAct < 0.003) {
      activationArr.fill(0);
      firingRef.current = false;
    }
    activationAttr.needsUpdate = true;
  });

  useEffect(() => {
    return () => {
      built.nodeGeo.dispose();
      built.nodeMat.dispose();
      built.edgeGeo.dispose();
      built.edgeMat.dispose();
      built.backboneGeo.dispose();
      built.backboneMat.dispose();
    };
  }, [built]);

  return (
    <group>
      <primitive object={built.nodeMesh} />
      <primitive object={built.edgeMesh} />
      <primitive object={built.backboneMesh} />
    </group>
  );
}
