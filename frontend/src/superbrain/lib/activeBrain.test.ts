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
  it('coerces non-string fields without throwing', () => {
    // route data is typed unknown; a backend could send a numeric model id
    expect(formatActiveBrainLine({ model: 7 as unknown as string, privacy: 'cloud' })).toBe('7 · cloud');
  });
  it('falls back to provider when model is an empty string', () => {
    expect(formatActiveBrainLine({ model: '', provider: 'ollama', privacy: 'local' })).toBe('ollama · local');
  });
  it('includes mode when present', () => {
    expect(formatActiveBrainLine({ model: 'Opus 4.8', privacy: 'cloud', mode: 'mission' })).toBe('Opus 4.8 · cloud · mission');
  });
  it('omits empty mode and privacy', () => {
    expect(formatActiveBrainLine({ model: 'Llama 3.1', mode: '', privacy: '' })).toBe('Llama 3.1');
  });
});

describe('active brain turn identity', () => {
  beforeEach(() => __resetActiveBrainForTests());
  it('stores turn_id and mode from a route event', () => {
    setActiveBrain({
      provider: 'ollama',
      model: 'qwen2.5-coder',
      privacy: 'local',
      turn_id: 'turn-7a9f',
      mode: 'conversation',
    });
    const brain = getActiveBrain();
    expect(brain.turn_id).toBe('turn-7a9f');
    expect(brain.mode).toBe('conversation');
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
