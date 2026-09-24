import { describe, expect, it } from 'vitest';
import { deriveAnatomicalConductor } from '../../superbrain/lib/anatomicalConductor';
import type { MaterializedTabRecord } from '../../superbrain/lib/tabStore';
import { derivePhysicalMaterialization } from './physicalMaterialization';

const tab = (overrides: Partial<MaterializedTabRecord> = {}): MaterializedTabRecord => ({
  id: 'surface-1',
  kind: 'content',
  lifecycle: 'live',
  originLocal: [0, 0, 0],
  targetLocal: [1, 1, 1],
  seatIndex: 3,
  content: { code: 'answer', language: 'text', filepath: 'answer.txt' },
  input: null,
  approval: null,
  bornAt: 1,
  phaseStartedAt: 1,
  ...overrides,
});

const conductor = (tabs: readonly MaterializedTabRecord[], phase: 'conducting' | 'approval_hold' = 'conducting') => deriveAnatomicalConductor({
  tabs,
  orchestration: { phase, focusId: 'surface-1', activeSeatIndex: 3 },
});

describe('derivePhysicalMaterialization', () => {
  it('keeps a live canonical surface anchored to its conductor role', () => {
    const surface = derivePhysicalMaterialization({
      tabs: [tab()],
      conductor: conductor([tab()]),
      focusId: 'surface-1',
    })[0];

    expect(surface).toMatchObject({
      id: 'surface-1',
      kind: 'content',
      seatIndex: 3,
      role: 'active',
      posture: 'live',
      focused: true,
      domContinuity: 'mounted',
    });
    expect(surface.originLocal).toEqual([0, 0, 0]);
    expect(surface.targetLocal).toEqual([1, 1, 1]);
  });

  it('preserves approval hold, input continuity, and reabsorption as projection cues', () => {
    const approval = tab({ id: 'approval-1', kind: 'approval', lifecycle: 'unfurling', seatIndex: 2, content: null, approval: {
      requestRef: 'approval', summary: 'Approve', explanation: '', diff: '+x', command: '', kindLabel: 'create', filepath: 'x.ts', content: 'x',
    } });
    const input = tab({ id: 'input-1', kind: 'input', seatIndex: null, content: null, input: { text: 'hello' } });
    const retracting = tab({ id: 'retracting-1', lifecycle: 'retracting' });
    const surfaces = derivePhysicalMaterialization({
      tabs: [approval, input, retracting],
      conductor: conductor([approval, retracting], 'approval_hold'),
      focusId: 'approval-1',
    });

    expect(surfaces[0]).toMatchObject({ role: 'held', posture: 'approaching', focused: true, domContinuity: 'mounted' });
    expect(surfaces[1]).toMatchObject({ role: 'input', seatIndex: null, domContinuity: 'mounted' });
    expect(surfaces[2]).toMatchObject({ role: 'reabsorbing', posture: 'reabsorbing', domContinuity: 'retracting' });
  });

  it('keeps the physical continuity list bounded and authority-neutral', () => {
    const tabs = Array.from({ length: 20 }, (_, index) => tab({ id: `surface-${index}`, seatIndex: index % 12 }));
    const surfaces = derivePhysicalMaterialization({ tabs, conductor: conductor(tabs), focusId: null });

    expect(surfaces).toHaveLength(12);
    expect(Object.keys(surfaces[0])).not.toEqual(expect.arrayContaining([
      'approved', 'authorized', 'allowed', 'canExecute', 'execute',
    ]));
  });
});
