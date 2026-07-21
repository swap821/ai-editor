import { describe, it, expect } from 'vitest';
import {
  deriveBodySpeech,
  BODY_SPEECH_HOLD_MS,
  BODY_SPEECH_FADE_MS,
  decideBodySpeechSync,
  BODY_SPEECH_SYNC_STALL_MS,
} from './bodySpeech';

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

// Real defect (2026-07-05, live-browser reproduced): troika-three-text's async
// sync() has no error handling anywhere in its promise chain (font load + SDF
// generation). If that chain never settles for any reason — a transient WebGL
// hiccup during first-time glyph-atlas creation is the realistic trigger — its
// completion callback never fires, troika's internal `_isSyncing` flag is stuck
// `true` forever, and BodySpeech's fire-and-forget `t.sync()` calls silently
// queue behind it for the rest of the page's life. Nothing throws, nothing logs
// — the reply just never appears, permanently, with the bus state showing a
// perfectly healthy 'streaming'/'complete' phase and full text the whole time
// (confirmed live: `_isSyncing` stuck true, one dead queued callback, group
// visible, opacity correct, text populated, canvas showing nothing).
// decideBodySpeechSync is the pure watchdog: it tells BodySpeech when to force
// a fresh sync attempt instead of trusting a stuck in-flight one to ever resolve.
describe('decideBodySpeechSync', () => {
  it('syncs when the visible text changed and nothing is pending', () => {
    expect(decideBodySpeechSync('hello', '', false, 0, 100)).toBe('sync');
  });
  it('skips when text is unchanged and nothing is pending', () => {
    expect(decideBodySpeechSync('hello', 'hello', false, 0, 100)).toBe('skip');
  });
  it('skips a redundant sync while one is pending and still within the stall window', () => {
    expect(decideBodySpeechSync('hello', 'hello', true, 0, 500)).toBe('skip');
  });
  it('still syncs new text while a prior sync is pending but not yet stalled (troika queues it safely)', () => {
    expect(decideBodySpeechSync('hello world', 'hello', true, 1000, 1100)).toBe('sync');
  });
  it('forces a resync once a pending sync has exceeded the stall timeout', () => {
    expect(decideBodySpeechSync('hello', 'hello', true, 0, BODY_SPEECH_SYNC_STALL_MS + 1)).toBe('force-resync');
  });
  it('is not yet stalled exactly at the timeout boundary', () => {
    expect(decideBodySpeechSync('hello', 'hello', true, 0, BODY_SPEECH_SYNC_STALL_MS)).toBe('skip');
  });
  it('prioritizes force-resync over a text change once stalled', () => {
    expect(decideBodySpeechSync('hello world', 'hello', true, 0, BODY_SPEECH_SYNC_STALL_MS + 1)).toBe('force-resync');
  });
});
