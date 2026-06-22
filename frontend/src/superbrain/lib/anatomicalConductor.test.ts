import { describe, expect, it } from 'vitest';
import { deriveAnatomicalConductor } from './anatomicalConductor';
import { deriveLivingOrchestration } from './livingOrchestrator';
import type { MaterializedTabRecord } from './tabStore';

const NOW = 40_000;

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
    ...contentTab('approval-1', seatIndex),
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

function anatomyFor(tabs: MaterializedTabRecord[], focusId: string | null) {
  const orchestration = deriveLivingOrchestration({ tabs, focusId });
  return deriveAnatomicalConductor({ tabs, orchestration });
}

describe('anatomicalConductor', () => {
  it('rests with no occupied vertebral seats', () => {
    const anatomy = anatomyFor([], null);

    expect(anatomy.activeSeatIndex).toBeNull();
    expect(anatomy.occupiedSeatIndexes).toEqual([]);
    expect(anatomy.conductingSeatIndexes).toEqual([]);
    expect(anatomy.trunkIntensity).toBe(0);
    expect(anatomy.vertebrae.every((signal) => signal.role === 'idle')).toBe(true);
  });

  it('marks the focused workspace as the active vertebra and lights the path down the cord', () => {
    const tab = contentTab('active-work', 3);
    const anatomy = anatomyFor([tab], tab.id);

    expect(anatomy.phase).toBe('working');
    expect(anatomy.activeSeatIndex).toBe(3);
    expect(anatomy.occupiedSeatIndexes).toEqual([3]);
    expect(anatomy.conductingSeatIndexes).toEqual([0, 1, 2, 3]);
    expect(anatomy.vertebrae[3].role).toBe('active');
    expect(anatomy.vertebrae[3].socketOpacity).toBeGreaterThan(0.25);
    expect(anatomy.trunkIntensity).toBeGreaterThan(0.6);
  });

  it('keeps waiting vertebrae visible but subordinate to the attended seat', () => {
    const lower = contentTab('lower-work', 4);
    const upper = contentTab('upper-work', 2);
    const anatomy = anatomyFor([lower, upper], lower.id);

    expect(anatomy.phase).toBe('conducting');
    expect(anatomy.activeSeatIndex).toBe(4);
    expect(anatomy.occupiedSeatIndexes).toEqual([2, 4]);
    expect(anatomy.vertebrae[4].role).toBe('active');
    expect(anatomy.vertebrae[2].role).toBe('waiting');
    expect(anatomy.vertebrae[2].socketOpacity).toBeLessThan(anatomy.vertebrae[4].socketOpacity);
  });

  it('turns an approval seat into a held conductor socket', () => {
    const approval = approvalTab(2);
    const anatomy = anatomyFor([approval], approval.id);

    expect(anatomy.phase).toBe('approval_hold');
    expect(anatomy.hold).toBe(true);
    expect(anatomy.vertebrae[2].role).toBe('held');
    expect(anatomy.trunkTint).toBe('#ffb06e');
  });

  it('uses a retracting workspace as the reabsorption target after focus is gone', () => {
    const tab = contentTab('done-work', 5, { lifecycle: 'retracting' });
    const anatomy = anatomyFor([tab], null);

    expect(anatomy.phase).toBe('reabsorbing');
    expect(anatomy.activeSeatIndex).toBe(5);
    expect(anatomy.vertebrae[5].role).toBe('reabsorbing');
    expect(anatomy.conductingSeatIndexes).toEqual([0, 1, 2, 3, 4, 5]);
    expect(anatomy.trunkTint).toBe('#a9fff3');
  });
});
