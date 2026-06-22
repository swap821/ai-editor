import { describe, it, expect } from 'vitest';
import { deriveBodySpeech, BODY_SPEECH_HOLD_MS, BODY_SPEECH_FADE_MS } from './bodySpeech';

describe('deriveBodySpeech', () => {
  it('idle: nothing visible', () => {
    const o = deriveBodySpeech({ text: '', phase: 'idle', sinceMs: 0, reducedMotion: false });
    expect(o.active).toBe(false);
    expect(o.visibleText).toBe('');
    expect(o.glow).toBe(0);
  });
  it('streaming: full text, full glow, no fade', () => {
    const o = deriveBodySpeech({ text: 'hello there', phase: 'streaming', sinceMs: 200, reducedMotion: false });
    expect(o.active).toBe(true);
    expect(o.visibleText).toBe('hello there');
    expect(o.glow).toBeGreaterThan(0.6);
    expect(o.fade).toBe(0);
  });
  it('complete within hold: still visible, fade 0', () => {
    const o = deriveBodySpeech({ text: 'done', phase: 'complete', sinceMs: BODY_SPEECH_HOLD_MS - 1, reducedMotion: false });
    expect(o.active).toBe(true);
    expect(o.fade).toBe(0);
  });
  it('complete after hold: fades over the fade window', () => {
    const mid = deriveBodySpeech({ text: 'done', phase: 'complete', sinceMs: BODY_SPEECH_HOLD_MS + BODY_SPEECH_FADE_MS / 2, reducedMotion: false });
    expect(mid.fade).toBeGreaterThan(0.3);
    expect(mid.fade).toBeLessThan(0.7);
    const gone = deriveBodySpeech({ text: 'done', phase: 'complete', sinceMs: BODY_SPEECH_HOLD_MS + BODY_SPEECH_FADE_MS + 10, reducedMotion: false });
    expect(gone.active).toBe(false);
  });
  it('caps very long replies to a readable tail', () => {
    const long = 'x'.repeat(2000);
    const o = deriveBodySpeech({ text: long, phase: 'streaming', sinceMs: 10, reducedMotion: false });
    expect(o.visibleText.length).toBeLessThanOrEqual(360);
  });
});
