import { describe, expect, it } from 'vitest';
import { deriveSemanticSignals, semanticSignalForEvent } from './semanticSignals';

describe('semantic mirror signals', () => {
  it('maps admitted canonical events without exposing internal event names', () => {
    expect(semanticSignalForEvent({ type: 'worker.started' })).toBe('worker-born');
    expect(semanticSignalForEvent({ type: 'cerebellum.replayed' })).toBe('reflex-reused');
    expect(semanticSignalForEvent({ type: 'security.refusal.recorded' })).toBe('refusal');
  });

  it('does not invent route or verification meaning when the payload is incomplete', () => {
    expect(semanticSignalForEvent({ type: 'route.selected' })).toBeUndefined();
    expect(semanticSignalForEvent({ type: 'verification.completed' })).toBeUndefined();
  });

  it('uses measured payload values for route and verification signals', () => {
    expect(semanticSignalForEvent({ type: 'route.selected', payload: { provider: 'ollama' } })).toBe('route-local');
    expect(semanticSignalForEvent({ type: 'route.selected', payload: { provider: 'gemini' } })).toBe('route-cloud');
    expect(semanticSignalForEvent({ type: 'verify_result', payload: { verdict: 'pass' } })).toBe('verification-pass');
    expect(semanticSignalForEvent({ type: 'verify_result', payload: { verdict: 'fail' } })).toBe('verification-fail');
  });

  it('deduplicates the bounded presentation vocabulary', () => {
    expect(deriveSemanticSignals([
      { type: 'worker.started' },
      { type: 'worker.completed' },
      { type: 'worker.dissolved' },
      { type: 'worker.started' },
    ])).toEqual(['worker-born', 'worker-returned', 'worker-dissolved']);
  });
});
