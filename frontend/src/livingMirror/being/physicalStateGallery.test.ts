import { describe, expect, it } from 'vitest';
import { derivePhysicalSnapshot } from './physicalSnapshot';
import { formatPhysicalStateGalleryAnnouncement, PHYSICAL_STATE_GALLERY } from './physicalStateGallery';
import type { BeingPhase } from './semanticKernel';

const EXPECTED_PHASES: readonly BeingPhase[] = [
  'booting',
  'arriving',
  'resting',
  'listening',
  'understanding',
  'planning',
  'awaiting-human',
  'acting',
  'verifying',
  'learning',
  'reflex',
  'recovering',
  'stale',
  'degraded',
  'stopped',
];

describe('physical state gallery fixtures', () => {
  it('covers the semantic phase map and all render quality tiers', () => {
    const phases = new Set(PHYSICAL_STATE_GALLERY.map((entry) => entry.presentation.phase));
    const tiers = new Set(PHYSICAL_STATE_GALLERY.map((entry) => entry.qualityTier));
    const ids = PHYSICAL_STATE_GALLERY.map((entry) => entry.id);

    expect([...phases]).toEqual(expect.arrayContaining([...EXPECTED_PHASES]));
    expect(tiers).toEqual(new Set(['low', 'medium', 'high']));
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('keeps every fixture inside the bounded physical projection contract', () => {
    for (const entry of PHYSICAL_STATE_GALLERY) {
      const physical = derivePhysicalSnapshot(entry.presentation);

      expect(physical.branches.length, entry.id).toBeLessThanOrEqual(8);
      expect(JSON.stringify(physical), entry.id).not.toMatch(/authorized|approved|allowed|canExecute/);
      expect(physical.phase, entry.id).toBe(entry.presentation.phase);
    }
  });

  it('preserves the high-risk boundaries as explicit gallery cases', () => {
    const byId = new Map(PHYSICAL_STATE_GALLERY.map((entry) => [entry.id, entry]));

    expect(derivePhysicalSnapshot(byId.get('approval-hold')!.presentation).membrane).toEqual({
      state: 'held',
      actionTravel: 'closed',
    });
    expect(derivePhysicalSnapshot(byId.get('worker-burst')!.presentation).conductor).toMatchObject({
      posture: 'held',
      travel: 'held',
    });
    expect(derivePhysicalSnapshot(byId.get('worker-burst')!.presentation).membrane).toEqual({
      state: 'held',
      actionTravel: 'closed',
    });
    expect(derivePhysicalSnapshot(byId.get('refusal')!.presentation).membrane).toEqual({
      state: 'refused',
      actionTravel: 'closed',
    });
    expect(derivePhysicalSnapshot(byId.get('stopped')!.presentation).membrane).toEqual({
      state: 'stopped',
      actionTravel: 'closed',
    });
    expect(derivePhysicalSnapshot(byId.get('verification-pending')!.presentation).verification.settlement).toBe('unsettled');
    expect(derivePhysicalSnapshot(byId.get('verification-pass')!.presentation).verification.settlement).toBe('stable');
    expect(derivePhysicalSnapshot(byId.get('verification-fail')!.presentation).verification.settlement).toBe('unsettled');
    expect(derivePhysicalSnapshot(byId.get('unverified')!.presentation)).toMatchObject({
      coherence: 'unverified',
      cortex: { posture: 'unverified' },
      verification: { state: 'unverified', settlement: 'unsettled' },
    });
    expect(derivePhysicalSnapshot(byId.get('worker-burst')!.presentation).branches).toHaveLength(8);
    expect(derivePhysicalSnapshot(byId.get('memory-recall')!.presentation).memory).toEqual({
      layer: 'recalled',
      pulse: 'inward',
    });
    expect(derivePhysicalSnapshot(byId.get('learning')!.presentation).memory).toEqual({
      layer: 'promoted',
      pulse: 'settle',
    });
    expect(derivePhysicalSnapshot(byId.get('reflex')!.presentation).memory).toEqual({
      layer: 'reflex',
      pulse: 'conduct',
    });
  });

  it('formats a live-region announcement for fixture selection and motion mode', () => {
    const entry = PHYSICAL_STATE_GALLERY.find((fixture) => fixture.id === 'worker-burst')!;

    expect(formatPhysicalStateGalleryAnnouncement(entry, 'high', true)).toBe(
      'Selected Bounded worker burst with terminal receipts. Quality High. Reduced motion enabled.',
    );
  });
});
