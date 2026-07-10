/**
 * NodeLattice — the supercomputer node-lattice inside the brain shape.
 *
 * These tests pin the DATA-TRUE topology contract (the operator's two
 * non-negotiables): the hubs ARE the real anatomical work-anchors, and the
 * intra-region edges keep each lobe a distinct cluster. The WebGL rendering is
 * deliberately NOT tested here (no GL context in vitest); the topology is a
 * pure function so the invariants can be locked without a renderer.
 */
import { describe, expect, it } from 'vitest';

import {
  buildLatticeData,
  HUBS,
  SATELLITES_PER_HUB,
  EDGE_K,
  hubKeyForTool,
  hubIndexForEvent,
} from './NodeLattice';
import type { QualityTier } from '@/components/QualityTierProvider';

const TIERS: QualityTier[] = ['high', 'medium', 'low'];
const idx = (key: string) => HUBS.findIndex((h) => h.key === key);

describe('NodeLattice hubs (DATA-TRUE anchors)', () => {
  it('are the 4 REAL anatomical anchors + 1 clearly-authored ROUTER', () => {
    expect(HUBS.map((h) => h.key)).toEqual(['CAUSAL', 'ARCHIVE', 'LATTICE', 'SIGNAL', 'ROUTER']);
    // Only the authored central node is flagged authored; the 4 anchors are real.
    expect(HUBS.filter((h) => h.authored).map((h) => h.key)).toEqual(['ROUTER']);
  });

  it('the 4 anchor positions match SuperbrainScene WAVE_REGION_ANCHORS verbatim', () => {
    expect(HUBS[0].pos.toArray()).toEqual([0.0, 0.26, 0.48]); // CAUSAL — frontal
    expect(HUBS[1].pos.toArray()).toEqual([0.34, 0.16, 0.11]); // ARCHIVE — temporal
    expect(HUBS[2].pos.toArray()).toEqual([0.0, 0.61, 0.11]); // LATTICE — parietal crown
    expect(HUBS[3].pos.toArray()).toEqual([0.05, 0.31, -0.38]); // SIGNAL — occipital
  });
});

describe('NodeLattice topology', () => {
  it('node count is tier-budgeted (1 hub + N satellites per lobe)', () => {
    for (const tier of TIERS) {
      const { nodes } = buildLatticeData(tier);
      expect(nodes).toHaveLength(HUBS.length + HUBS.length * SATELLITES_PER_HUB[tier]);
      expect(nodes.filter((n) => n.isHub)).toHaveLength(HUBS.length);
    }
  });

  it('is deterministic (seeded) — identical positions across builds', () => {
    const a = buildLatticeData('high');
    const b = buildLatticeData('high');
    expect(a.nodes.map((n) => n.pos.toArray())).toEqual(b.nodes.map((n) => n.pos.toArray()));
  });

  it('coalescence igniteDelay is deterministic, in 0..1, and lowest at the ROUTER core', () => {
    const a = buildLatticeData('high');
    const b = buildLatticeData('high');
    expect(a.nodes.map((n) => n.igniteDelay)).toEqual(b.nodes.map((n) => n.igniteDelay));
    for (const n of a.nodes) {
      expect(n.igniteDelay).toBeGreaterThanOrEqual(0);
      expect(n.igniteDelay).toBeLessThanOrEqual(1);
    }
    // The authored ROUTER hub sits at BRAIN_CENTER → it ignites first (delay ~0).
    const routerHub = a.nodes.find((n) => n.isHub && n.hub === idx('ROUTER'))!;
    expect(routerHub.igniteDelay).toBeCloseTo(0, 5);
    // Some lobe node ignites meaningfully later (the wave reaches outward).
    expect(Math.max(...a.nodes.map((n) => n.igniteDelay))).toBeGreaterThan(0.3);
  });

  it('edges are STRICTLY intra-region (both endpoints in the same lobe)', () => {
    for (const tier of TIERS) {
      const { nodes, edges } = buildLatticeData(tier);
      // endpoints are shared position refs with the owning nodes.
      const hubOf = (p: unknown) => nodes.find((n) => n.pos === p)?.hub;
      for (const e of edges) {
        const ha = hubOf(e.a);
        const hb = hubOf(e.b);
        expect(ha).toBeTypeOf('number');
        expect(ha).toBe(hb);
      }
    }
  });

  it('low tier drops intra-cluster knn — every edge is a hub spoke', () => {
    expect(EDGE_K.low).toBe(0);
    const { nodes, edges } = buildLatticeData('low');
    const hubPos = new Set(nodes.filter((n) => n.isHub).map((n) => n.pos));
    for (const e of edges) {
      expect(hubPos.has(e.a) || hubPos.has(e.b)).toBe(true);
    }
  });

  it('high tier adds intra-cluster links beyond the spokes', () => {
    const { edges } = buildLatticeData('high');
    const spokeCount = HUBS.length * SATELLITES_PER_HUB.high; // one spoke per satellite
    expect(edges.length).toBeGreaterThan(spokeCount);
  });
});

describe('NodeLattice P2 firing map (DATA-TRUE event -> hub)', () => {
  it('routes tools to the same lobe the cortex uses (waveLabelForTool parity)', () => {
    expect(hubKeyForTool('plan')).toBe('CAUSAL');
    expect(hubKeyForTool('recall_memory')).toBe('CAUSAL');
    expect(hubKeyForTool('read_file')).toBe('ARCHIVE');
    expect(hubKeyForTool('create_file')).toBe('LATTICE');
    expect(hubKeyForTool('verify')).toBe('LATTICE');
    expect(hubKeyForTool('something_unknown')).toBe('SIGNAL');
  });

  it('fires a real tool-engaged dispatch at its owning hub', () => {
    expect(hubIndexForEvent({ type: 'agent-dispatch', detail: 'tool engaged: read_file' })).toBe(idx('ARCHIVE'));
    expect(hubIndexForEvent({ type: 'agent-dispatch', detail: 'tool engaged: edit_file' })).toBe(idx('LATTICE'));
    expect(hubIndexForEvent({ type: 'agent-dispatch', detail: 'PLANNER caste online' })).toBe(idx('CAUSAL'));
  });

  it('maps verification + recall + route to the right hubs', () => {
    expect(hubIndexForEvent({ type: 'knowledge-acquired', label: 'VERIFICATION GREEN' })).toBe(idx('LATTICE'));
    expect(hubIndexForEvent({ type: 'knowledge-acquired', detail: 'trail #12 reinforced — strength 0.7' })).toBe(idx('CAUSAL'));
    expect(hubIndexForEvent({ type: 'route', label: 'OLLAMA' })).toBe(idx('ROUTER'));
  });

  it('directive/synthesis/burst pulse ALL hubs (-1); ignored events return null', () => {
    expect(hubIndexForEvent({ type: 'directive' })).toBe(-1);
    expect(hubIndexForEvent({ type: 'synthesis' })).toBe(-1);
    expect(hubIndexForEvent({ type: 'approval-required' })).toBeNull();
    expect(hubIndexForEvent({ type: 'telemetry' })).toBeNull();
    expect(hubIndexForEvent({ type: 'voice-speaking' })).toBeNull();
  });
});
