import { describe, expect, it } from 'vitest';
import { createSeededRandom } from './seededRandom';

function draw(next: () => number, count: number): number[] {
  const values: number[] = [];
  for (let i = 0; i < count; i += 1) {
    values.push(next());
  }
  return values;
}

describe('createSeededRandom', () => {
  it('returns values in the half-open range [0, 1)', () => {
    const next = createSeededRandom(12345);
    const values = draw(next, 1000);

    for (const value of values) {
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThan(1);
    }
  });

  it('produces the same sequence for the same seed', () => {
    const first = draw(createSeededRandom(42), 10);
    const second = draw(createSeededRandom(42), 10);

    expect(second).toEqual(first);
  });

  it('keeps each generator\'s state independent of other generators', () => {
    const reference = draw(createSeededRandom(7), 6);

    const a = createSeededRandom(7);
    const b = createSeededRandom(7);
    const interleaved: number[] = [];
    for (let i = 0; i < 3; i += 1) {
      interleaved.push(a());
      interleaved.push(b());
    }

    expect(interleaved.filter((_, index) => index % 2 === 0)).toEqual(reference.slice(0, 3));
    expect(interleaved.filter((_, index) => index % 2 === 1)).toEqual(reference.slice(0, 3));
  });

  it('produces different sequences for different seeds', () => {
    const seedOne = draw(createSeededRandom(1), 5);
    const seedTwo = draw(createSeededRandom(2), 5);

    expect(seedTwo).not.toEqual(seedOne);
  });

  it('advances its state on every call rather than repeating one value', () => {
    const next = createSeededRandom(99);
    const values = draw(next, 5);

    expect(new Set(values).size).toBe(values.length);
  });
});
