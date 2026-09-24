import { describe, expect, it } from 'vitest';
import { describeConnection, describeMemoryReuse, describeTaskState, describeVerification } from './copy';

describe('human copy contract', () => {
  it('uses plain language for continuity', () => {
    expect(describeConnection('stale')).toMatchObject({ title: 'Showing the last known state' });
    expect(describeConnection('fresh').detail).not.toMatch(/cursor|sequence|transport/i);
  });

  it('never calls unverified work done', () => {
    expect(describeTaskState('done-unverified').title).toMatch(/not verified/i);
    expect(describeVerification('unverified').title).toBe('Unverified');
  });

  it('makes reflex copy explicitly conditional on measured reuse', () => {
    expect(describeMemoryReuse(true).detail).toMatch(/verified routine/i);
    expect(describeMemoryReuse(false).detail).toMatch(/No learned routine/i);
  });
});
