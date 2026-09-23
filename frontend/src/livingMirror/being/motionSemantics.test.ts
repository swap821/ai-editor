import { describe, expect, it } from 'vitest';
import { BEING_MOTION_SEMANTICS, motionSemanticsFor } from './motionSemantics';
import type { BeingMotion } from './semanticKernel';

describe('being motion semantics', () => {
  it('covers the complete shared motion vocabulary', () => {
    const motions: BeingMotion[] = ['calm', 'attention', 'materialize', 'conduct', 'verify', 'refuse', 'reabsorb', 'stop'];
    expect(Object.keys(BEING_MOTION_SEMANTICS).sort()).toEqual([...motions].sort());
    for (const motion of motions) {
      expect(motionSemanticsFor(motion)).toMatchObject({
        id: `motion.${motion}`,
        meaning: expect.any(String),
        startCondition: expect.any(String),
        endCondition: expect.any(String),
        reducedMotion: expect.any(String),
      });
    }
  });

  it('keeps stop semantics explicit and dominant', () => {
    expect(motionSemanticsFor('stop')).toMatchObject({
      meaning: expect.stringContaining('overrides'),
      reducedMotion: expect.stringContaining('Freeze'),
    });
  });
});
