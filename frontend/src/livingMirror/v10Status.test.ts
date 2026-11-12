import { describe, expect, it } from 'vitest';
import {
  parseV10EcosystemStatus,
  parseV10Scanner,
  parseV10VultureStatus,
} from './v10Status';

describe('parseV10Scanner', () => {
  it('returns null for null and undefined input', () => {
    expect(parseV10Scanner(null, 'x')).toBeNull();
    expect(parseV10Scanner(undefined, 'x')).toBeNull();
  });

  it('throws a labelled error for non-record input', () => {
    expect(() => parseV10Scanner('nope', 'ecosystem')).toThrow('Unsupported ecosystem status response.');
  });

  it('normalises invalid scalar fields to null and leaves lastScan undefined when absent', () => {
    expect(parseV10Scanner({ available: 'yes', activation: '   ', localOnly: true }, 'x')).toEqual({
      available: null,
      activation: null,
      localOnly: true,
      lastScan: undefined,
    });
  });

  it('parses a scan, rejecting invalid counts', () => {
    const result = parseV10Scanner(
      {
        available: true,
        activation: 'manual',
        lastScan: {
          findingCount: 3,
          cloudCalls: -1,
          networkCalls: 1.5,
          writesPerformed: false,
          topFindings: [
            { kind: 'dead', severity: 'low', targetId: 'a', recommendation: 'remove' },
            { kind: 5 },
          ],
        },
      },
      'x',
    );
    expect(result?.lastScan).toEqual({
      findingCount: 3,
      cloudCalls: null,
      networkCalls: null,
      writesPerformed: false,
      topFindings: [
        { kind: 'dead', severity: 'low', targetId: 'a', recommendation: 'remove' },
        { kind: null, severity: null, targetId: null, recommendation: null },
      ],
    });
  });

  it('keeps an explicit null lastScan and rejects malformed scans and findings', () => {
    expect(parseV10Scanner({ lastScan: null }, 'x')?.lastScan).toBeNull();
    expect(() => parseV10Scanner({ lastScan: 4 }, 'vulture')).toThrow('Unsupported vulture scan response.');
    expect(() => parseV10Scanner({ lastScan: { topFindings: [1] } }, 'vulture')).toThrow(
      'Unsupported vulture finding response.',
    );
  });
});

describe('parseV10VultureStatus', () => {
  it('parses the vulture entry', () => {
    expect(parseV10VultureStatus({ vulture: { available: true } })).toEqual({
      available: true,
      activation: null,
      localOnly: null,
      lastScan: undefined,
    });
  });

  it('returns null when vulture is missing and throws for non-records', () => {
    expect(parseV10VultureStatus({})).toBeNull();
    expect(() => parseV10VultureStatus([])).toThrow('Unsupported v10 status response.');
  });
});

describe('parseV10EcosystemStatus', () => {
  it('returns nulls for absent sections', () => {
    expect(parseV10EcosystemStatus({})).toEqual({
      ecosystem: null,
      constitution: null,
      symbolRepoMap: null,
      metaLoop: null,
      councilMemory: null,
    });
  });

  it('parses every section', () => {
    const result = parseV10EcosystemStatus({
      ecosystem: { available: false },
      constitution: { casteCount: 4, frozenCoreProtected: true },
      symbolRepoMap: { activation: 'auto', lastScan: { symbolCount: 10, evidenceFileCount: -2 } },
      metaLoop: { safetyStatus: 'ok', proposalCount: 2 },
      councilMemory: { deliberationCount: 7 },
    });
    expect(result.ecosystem?.available).toBe(false);
    expect(result.constitution).toEqual({ casteCount: 4, frozenCoreProtected: true });
    expect(result.symbolRepoMap).toEqual({
      activation: 'auto',
      lastScan: { symbolCount: 10, evidenceFileCount: null },
    });
    expect(result.metaLoop).toEqual({ safetyStatus: 'ok', proposalCount: 2 });
    expect(result.councilMemory).toEqual({ deliberationCount: 7 });
  });

  it('handles symbol RepoMap lastScan variants and errors', () => {
    expect(parseV10EcosystemStatus({ symbolRepoMap: { lastScan: null } }).symbolRepoMap?.lastScan).toBeNull();
    expect(() => parseV10EcosystemStatus({ symbolRepoMap: 'x' })).toThrow('Unsupported symbol RepoMap response.');
    expect(() => parseV10EcosystemStatus({ symbolRepoMap: { lastScan: 3 } })).toThrow(
      'Unsupported symbol RepoMap scan response.',
    );
    expect(() => parseV10EcosystemStatus(null)).toThrow('Unsupported v10 status response.');
  });
});
