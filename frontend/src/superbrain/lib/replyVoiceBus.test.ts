import { describe, it, expect, beforeEach } from 'vitest';
import { getReplyVoice, __ingestVoiceForTests, __resetReplyVoiceForTests } from './replyVoiceBus';
import { publishCognition } from './cognitionBus';
import { deriveBodySpeech } from './bodySpeech';

describe('replyVoiceBus', () => {
  beforeEach(() => __resetReplyVoiceForTests());
  it('starts idle', () => {
    expect(getReplyVoice().phase).toBe('idle');
    expect(getReplyVoice().text).toBe('');
  });
  it('retires a streamed caption on the actual Stop event without retiring a completed caption early', () => {
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Completed answer' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    expect(deriveBodySpeech({ ...getReplyVoice(), sinceMs: 100, reducedMotion: false })).toMatchObject({ active: true, visibleText: 'Completed answer' });

    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'question' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Partial answer' } });
    expect(deriveBodySpeech({ ...getReplyVoice(), sinceMs: 9000, reducedMotion: false }).active).toBe(true);
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'stopped' } });
    expect(getReplyVoice()).toMatchObject({ phase: 'idle', text: '' });
    expect(deriveBodySpeech({ ...getReplyVoice(), sinceMs: 0, reducedMotion: false }).active).toBe(false);
  });
  it('question resets, reply accumulates (latest chunk is full text), complete marks complete', () => {
    __ingestVoiceForTests({ type: 'voice-speaking', source: 'gagos', data: { phase: 'question', text: 'hi' } });
    expect(getReplyVoice().phase).toBe('idle');
    __ingestVoiceForTests({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Hel' } });
    __ingestVoiceForTests({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Hello' } });
    expect(getReplyVoice().phase).toBe('streaming');
    expect(getReplyVoice().text).toBe('Hello');
    __ingestVoiceForTests({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    expect(getReplyVoice().phase).toBe('complete');
    expect(getReplyVoice().text).toBe('Hello');
  });
  it('ignores non-voice-speaking events', () => {
    __ingestVoiceForTests({ type: 'directive', source: 'hud' });
    expect(getReplyVoice().phase).toBe('idle');
  });
  it('maps TTS speaking phase to streaming and speaking-complete to complete', () => {
    __ingestVoiceForTests({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Hello' } });
    __ingestVoiceForTests({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    expect(getReplyVoice().phase).toBe('complete');
    __ingestVoiceForTests({ type: 'voice-speaking', source: 'gagos', data: { phase: 'speaking', reply: 'Hello' } });
    expect(getReplyVoice().phase).toBe('streaming');
    expect(getReplyVoice().text).toBe('Hello');
    __ingestVoiceForTests({ type: 'voice-speaking', source: 'gagos', data: { phase: 'speaking-complete' } });
    expect(getReplyVoice().phase).toBe('complete');
  });
});
