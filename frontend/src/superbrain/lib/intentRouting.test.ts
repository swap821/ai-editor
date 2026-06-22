import { describe, expect, it } from 'vitest';
import { isWorkIntent } from './intentRouting';

describe('isWorkIntent', () => {
  it('matches leading work verbs', () => {
    expect(isWorkIntent('write me a python file')).toBe(true);
    expect(isWorkIntent('Build a calculator')).toBe(true);
    expect(isWorkIntent('  create a vite app')).toBe(true);
  });

  it('does not classify plain conversation as work', () => {
    expect(isWorkIntent('how are you today')).toBe(false);
    expect(isWorkIntent('tell me about the nervous system')).toBe(false);
  });
});
