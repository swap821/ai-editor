import { describe, expect, it } from 'vitest';
import { EXPERIENCE_MODE_STORAGE_KEY, readExperienceMode, writeExperienceMode } from './experienceMode';

function memoryStorage(initial?: string): Storage {
  let value = initial ?? null;
  return {
    getItem: () => value,
    setItem: (_key, next) => { value = next; },
    removeItem: () => { value = null; },
    clear: () => { value = null; },
    key: () => null,
    get length() { return value === null ? 0 : 1; },
  };
}

describe('experience mode contract', () => {
  it('defaults to Beginner when storage is empty or contains an unknown value', () => {
    expect(readExperienceMode(memoryStorage())).toBe('beginner');
    expect(readExperienceMode(memoryStorage('operator'))).toBe('beginner');
  });

  it('round-trips the explicit Expert choice through the one shared key', () => {
    const storage = memoryStorage();
    writeExperienceMode('expert', storage);

    expect(storage.getItem(EXPERIENCE_MODE_STORAGE_KEY)).toBe('expert');
    expect(readExperienceMode(storage)).toBe('expert');
  });

  it('fails closed to Beginner when browser storage is unavailable', () => {
    const unavailable = {
      getItem: () => { throw new Error('storage blocked'); },
      setItem: () => { throw new Error('storage blocked'); },
    } as unknown as Storage;

    expect(readExperienceMode(unavailable)).toBe('beginner');
    expect(() => writeExperienceMode('expert', unavailable)).not.toThrow();
  });
});
