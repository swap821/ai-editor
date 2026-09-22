import { describe, expect, it } from 'vitest';
import { isEstablishedTurn, isCompleteWorkResult } from './turnOutcome';

describe('turn outcome guards', () => {
  it('only treats a terminal response or approval pause as an established turn', () => {
    expect(isEstablishedTurn({ ok: true, paused: false })).toBe(true);
    expect(isEstablishedTurn({ ok: false, paused: true })).toBe(true);
    expect(isEstablishedTurn({ ok: false, paused: false, answer: '' })).toBe(false);
    expect(isEstablishedTurn(null)).toBe(false);
  });

  it('does not materialize code from a stream that never reached a terminal frame', () => {
    expect(isCompleteWorkResult({ ok: true, paused: false }, true)).toBe(true);
    expect(isCompleteWorkResult({ ok: false, paused: false }, true)).toBe(false);
    expect(isCompleteWorkResult({ ok: true, paused: true }, true)).toBe(false);
    expect(isCompleteWorkResult({ ok: true, paused: false }, false)).toBe(false);
  });
});
