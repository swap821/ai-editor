import { describe, expect, it } from 'vitest';
import { presentVoiceStatus } from './voicePresentation';

describe('presentVoiceStatus', () => {
  it('uses human Guided copy for unavailable local voice input', () => {
    const result = presentVoiceStatus({
      state: 'local transcription unavailable',
      error: null,
      guided: true,
    });

    expect(result.status).toBe('Voice input unavailable');
    expect(result.error).toBeNull();
    expect(result.status).not.toContain('transcription');
  });

  it('keeps technical voice evidence visible in Expert mode', () => {
    const result = presentVoiceStatus({
      state: 'ready · local transcription',
      error: 'Local transcription is unavailable. Choose the browser route explicitly, or type your message.',
      guided: false,
    });

    expect(result).toEqual({
      status: 'ready · local transcription',
      error: 'Local transcription is unavailable. Choose the browser route explicitly, or type your message.',
    });
  });

  it('maps a measured Guided voice error without exposing route terminology', () => {
    const result = presentVoiceStatus({
      state: 'capture failed',
      error: 'Browser recognition failed: network',
      guided: true,
    });

    expect(result.status).toBe('Voice input failed');
    expect(result.error).toBe('Voice input failed. You can type your message.');
    expect(result.error).not.toContain('Browser recognition');
  });

  it('keeps unknown Guided states unavailable instead of inventing activity', () => {
    const result = presentVoiceStatus({
      state: 'unseen backend voice state',
      error: null,
      guided: true,
    });

    expect(result.status).toBe('Voice input status unavailable');
    expect(result.status).not.toContain('ready');
    expect(result.status).not.toContain('listening');
  });
});
