import { describe, expect, it } from 'vitest';
import { deriveAnatomicalRootSystem } from './anatomicalRootSystem';
import { deriveLivingOrchestration } from './livingOrchestrator';
import type { OutcomeImprintSnapshot } from './outcomeImprint';
import type { MaterializedTabRecord } from './tabStore';
import type { TurnMetabolismSnapshot } from './turnMetabolism';

const NOW = 46_000;

const working: TurnMetabolismSnapshot = {
  phase: 'working',
  intensity: 1,
  surfaceExcitation: 0.55,
  rootExcitation: 0.7,
  breathGain: 0.32,
  tint: '#ffbe78',
  held: false,
  changedAt: NOW,
};

const approval: TurnMetabolismSnapshot = {
  phase: 'approval',
  intensity: 1,
  surfaceExcitation: 0.68,
  rootExcitation: 0.78,
  breathGain: -0.18,
  tint: '#ffc36e',
  held: true,
  changedAt: NOW,
};

const scar: OutcomeImprintSnapshot = {
  kind: 'scar',
  intensity: 1,
  ringOpacity: 0.1,
  scarOpacity: 0.46,
  rootGlow: 0.7,
  surfaceGlow: 0.12,
  tint: '#ff5f7a',
  label: 'VERIFICATION RED',
  detail: 'failed',
  changedAt: NOW,
};

const verified: OutcomeImprintSnapshot = {
  kind: 'verified',
  intensity: 1,
  ringOpacity: 0.28,
  scarOpacity: 0.1,
  rootGlow: 0.68,
  surfaceGlow: 0.15,
  tint: '#8dffd1',
  label: 'VERIFICATION GREEN',
  detail: 'passed',
  changedAt: NOW,
};

function contentTab(id: string, seatIndex: number, patch: Partial<MaterializedTabRecord> = {}): MaterializedTabRecord {
  return {
    id,
    kind: 'content',
    lifecycle: 'live',
    originLocal: [0.04, -1.1 - seatIndex * 0.1, -0.36],
    targetLocal: [0.82, -0.96 - seatIndex * 0.1, -0.14],
    seatIndex,
    content: { code: `export const ${id.replace(/-/g, '')} = true;`, language: 'typescript', filepath: `${id}.ts` },
    input: null,
    approval: null,
    bornAt: NOW + seatIndex,
    phaseStartedAt: NOW + seatIndex,
    ...patch,
  };
}

function approvalTab(seatIndex: number): MaterializedTabRecord {
  return {
    ...contentTab('approval-root', seatIndex),
    kind: 'approval',
    content: null,
    approval: {
      token: 'approval-token',
      summary: 'Approval required',
      explanation: '',
      diff: '+demo',
      command: '',
      kindLabel: 'create',
      filepath: 'demo.ts',
      content: 'export const demo = true;',
    },
  };
}

function rootSystemFor(
  tabs: MaterializedTabRecord[],
  focusId: string | null,
  patch: Partial<Parameters<typeof deriveAnatomicalRootSystem>[0]> = {},
) {
  const orchestration = deriveLivingOrchestration({ tabs, focusId });
  return deriveAnatomicalRootSystem({ surfaces: orchestration.surfaces, ...patch });
}

describe('anatomicalRootSystem', () => {
  it('rests without visible anatomical root actuation', () => {
    const rootSystem = rootSystemFor([], null);

    expect(rootSystem.strands).toHaveLength(0);
    expect(rootSystem.caudaTraces).toHaveLength(0);
    expect(rootSystem.dominantRole).toBe('resting');
    expect(rootSystem.sprayIntensity).toBe(0);
  });

  it('promotes focused work into bilateral conducting root fans', () => {
    const tab = contentTab('active-work', 3);
    const rootSystem = rootSystemFor([tab], tab.id, { metabolism: working });

    expect(rootSystem.activeSeatIndexes).toEqual([3]);
    expect(rootSystem.strands).toHaveLength(6);
    expect(new Set(rootSystem.strands.map((strand) => strand.side))).toEqual(new Set(['left', 'right']));
    expect(new Set(rootSystem.strands.map((strand) => strand.channel))).toEqual(new Set(['upper', 'middle', 'lower']));
    expect(rootSystem.strands.every((strand) => strand.role === 'conducting')).toBe(true);
    expect(rootSystem.strands.every((strand) => strand.flow === 'outbound')).toBe(true);
    expect(rootSystem.strands[0].clampOpacity).toBeGreaterThan(0.4);
    expect(rootSystem.strands[0].beadSpeed).toBeGreaterThan(0.2);
  });

  it('keeps waiting roots alive but subordinate to the focused seat', () => {
    const active = contentTab('active-work', 4);
    const waiting = contentTab('waiting-work', 2);
    const rootSystem = rootSystemFor([active, waiting], active.id, { metabolism: working });

    const activeStrand = rootSystem.strands.find((strand) => strand.seatIndex === 4);
    const waitingStrand = rootSystem.strands.find((strand) => strand.seatIndex === 2);

    expect(rootSystem.activeSeatIndexes).toEqual([4]);
    expect(rootSystem.waitingSeatIndexes).toEqual([2]);
    expect(activeStrand?.role).toBe('conducting');
    expect(waitingStrand?.role).toBe('sensing');
    expect(waitingStrand?.opacity).toBeLessThan(activeStrand?.opacity ?? 0);
    expect(waitingStrand?.tension).toBeLessThan(activeStrand?.tension ?? 0);
  });

  it('locks approval roots into a bilateral hold clamp', () => {
    const tab = approvalTab(2);
    const rootSystem = rootSystemFor([tab], tab.id, { metabolism: approval });

    expect(rootSystem.heldSeatIndexes).toEqual([2]);
    expect(rootSystem.dominantRole).toBe('holding');
    expect(rootSystem.strands.every((strand) => strand.role === 'holding')).toBe(true);
    expect(rootSystem.strands.every((strand) => strand.flow === 'bidirectional')).toBe(true);
    expect(Math.min(...rootSystem.strands.map((strand) => strand.clampOpacity))).toBeGreaterThan(0.55);
  });

  it('returns scarred work through the roots and stains the lower spray', () => {
    const tab = contentTab('scarred-work', 3);
    const rootSystem = rootSystemFor([tab], tab.id, { outcome: scar });

    expect(rootSystem.errorSeatIndexes).toEqual([3]);
    expect(rootSystem.dominantRole).toBe('error');
    expect(rootSystem.strands.every((strand) => strand.role === 'error')).toBe(true);
    expect(rootSystem.strands.every((strand) => strand.flow === 'return')).toBe(true);
    expect(rootSystem.caudaTraces).toHaveLength(2);
    expect(rootSystem.caudaTraces.every((trace) => trace.tint === '#ff5f7a')).toBe(true);
    expect(rootSystem.sprayIntensity).toBeGreaterThan(0.4);
  });

  it('carries verified reabsorption into a cyan cauda-equina memory trace', () => {
    const tab = contentTab('done-work', 5, { lifecycle: 'retracting' });
    const rootSystem = rootSystemFor([tab], null, { outcome: verified });

    expect(rootSystem.reabsorbingSeatIndexes).toEqual([5]);
    expect(rootSystem.dominantRole).toBe('reabsorbing');
    expect(rootSystem.strands.every((strand) => strand.role === 'reabsorbing')).toBe(true);
    expect(rootSystem.caudaTraces).toHaveLength(2);
    expect(rootSystem.caudaTraces.every((trace) => trace.tint === '#a9fff3')).toBe(true);
    expect(Math.min(...rootSystem.caudaTraces.map((trace) => trace.memoryStrength))).toBeGreaterThan(0.7);
  });
});
