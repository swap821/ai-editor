import { describe, it, expect, beforeEach } from 'vitest';
import {
  formatActiveBrainLine,
  getActiveBrain,
  setActiveBrain,
  __resetActiveBrainForTests,
} from './activeBrain';

describe('formatActiveBrainLine', () => {
  it('renders "Model · privacy"', () => {
    expect(formatActiveBrainLine({ model: 'Opus 4.8', privacy: 'cloud' })).toBe('Opus 4.8 · cloud');
  });
  it('falls back to provider when model is missing', () => {
    expect(formatActiveBrainLine({ provider: 'ollama', privacy: 'local' })).toBe('ollama · local');
  });
  it('shows a sensible default when nothing is known', () => {
    expect(formatActiveBrainLine({})).toBe('auto');
  });
});

describe('active brain store', () => {
  beforeEach(() => __resetActiveBrainForTests());
  it('starts at the default and updates on setActiveBrain', () => {
    expect(getActiveBrain().model).toBeUndefined();
    setActiveBrain({ model: 'Llama 3.1', privacy: 'local' });
    expect(getActiveBrain().model).toBe('Llama 3.1');
  });
});
