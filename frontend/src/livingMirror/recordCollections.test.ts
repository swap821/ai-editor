import { describe, expect, it, vi } from 'vitest';
import { durableCollection, identifiedRecords, noRecords, textValue } from './recordCollections';
import { redactProjection } from './redaction';

vi.mock('./redaction', () => ({
  redactProjection: vi.fn((value: unknown) =>
    (value as Record<string, unknown>[]).map((row) => ({ ...row, redacted: true }))),
}));

describe('identifiedRecords', () => {
  it('returns the redacted projection of records with unique string identities', () => {
    const rows = [{ id: 'a', n: 1 }, { id: 'b', n: 2 }];
    const result = identifiedRecords(rows, 'id');
    expect(redactProjection).toHaveBeenCalledWith(rows);
    expect(result).toEqual([
      { id: 'a', n: 1, redacted: true },
      { id: 'b', n: 2, redacted: true },
    ]);
  });

  it('rejects non-arrays, missing, empty or non-string identities', () => {
    expect(() => identifiedRecords({}, 'id')).toThrow('Records lack id identity.');
    expect(() => identifiedRecords([{ name: 'x' }], 'id')).toThrow('Records lack id identity.');
    expect(() => identifiedRecords([{ id: '' }], 'id')).toThrow('Records lack id identity.');
    expect(() => identifiedRecords([{ id: 5 }], 'id')).toThrow('Records lack id identity.');
    expect(() => identifiedRecords(['a'], 'id')).toThrow('Records lack id identity.');
  });

  it('rejects duplicate identities', () => {
    expect(() => identifiedRecords([{ id: 'a' }, { id: 'a' }], 'id')).toThrow('Duplicate record identity.');
  });
});

describe('durableCollection', () => {
  it('accepts an available collection and an empty one', () => {
    const available = durableCollection(
      { source: 'durable_repository', status: 'available', items: [{ key: 'k1' }] },
      'key',
    );
    expect(available).toEqual([{ key: 'k1', redacted: true }]);
    expect(
      durableCollection({ source: 'durable_repository', status: 'empty', items: [] }, 'key'),
    ).toEqual([]);
  });

  it('rejects wrong source, unknown status, and status that contradicts the items', () => {
    const message = 'Unsupported durable collection response.';
    const item = [{ key: 'k1' }];
    expect(() => durableCollection(null, 'key')).toThrow(message);
    expect(() => durableCollection({ source: 'cache', status: 'available', items: item }, 'key')).toThrow(message);
    expect(() => durableCollection({ source: 'durable_repository', status: 'error', items: item }, 'key')).toThrow(message);
    expect(() => durableCollection({ source: 'durable_repository', status: 'empty', items: item }, 'key')).toThrow(message);
    expect(() => durableCollection({ source: 'durable_repository', status: 'available', items: [] }, 'key')).toThrow(message);
    expect(() => durableCollection({ source: 'durable_repository', status: 'available' }, 'key')).toThrow(message);
  });

  it('still enforces record identity on otherwise valid collections', () => {
    expect(() =>
      durableCollection({ source: 'durable_repository', status: 'available', items: [{ other: 1 }] }, 'key'),
    ).toThrow('Records lack key identity.');
  });
});

describe('textValue and noRecords', () => {
  it('renders null and undefined as Unavailable, strings as-is, others as JSON', () => {
    expect(textValue(null)).toBe('Unavailable');
    expect(textValue(undefined)).toBe('Unavailable');
    expect(textValue('hello')).toBe('hello');
    expect(textValue('')).toBe('');
    expect(textValue(42)).toBe('42');
    expect(textValue(false)).toBe('false');
    expect(textValue({ a: [1] })).toBe('{"a":[1]}');
  });

  it('reports whether a row list is empty', () => {
    expect(noRecords([])).toBe(true);
    expect(noRecords([undefined])).toBe(false);
  });
});
