import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  __resetVoiceSpeakForTests,
  getVoiceSpeakState,
  interruptSpeech,
  isVoiceSpeakMuted,
  setBackendTTS,
  setVoiceSpeakMuted,
  startVoiceSpeak,
  subscribeVoiceSpeak,
} from './voiceSpeak';
import { publishCognition, subscribeCognition } from '../superbrain/lib/cognitionBus';
import { getReplyVoice, __resetReplyVoiceForTests } from '../superbrain/lib/replyVoiceBus';
import { speakText } from '../superbrain/lib/aiosAdapter';

vi.mock('../superbrain/lib/aiosAdapter', () => ({
  speakText: vi.fn(),
}));

function deferred<T>(): { promise: Promise<T>; resolve: (v: T) => void } {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

interface MockUtterance {
  text: string;
  voice?: SpeechSynthesisVoice;
  rate: number;
  pitch: number;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
}

function installSpeechMocks(voices: SpeechSynthesisVoice[] = []) {
  let last: MockUtterance | null = null;
  const speak = vi.fn((u: MockUtterance) => {
    last = u;
    if (u.onstart) u.onstart();
  });
  const cancel = vi.fn(() => {
    const l = last;
    if (l?.onend) {
      last = null;
      l.onend();
    }
  });
  const getVoices = vi.fn(() => voices);
  vi.stubGlobal('speechSynthesis', {
    speak,
    cancel,
    getVoices,
    pause: vi.fn(),
    resume: vi.fn(),
  });
  vi.stubGlobal(
    'SpeechSynthesisUtterance',
    class {
      text: string;
      voice?: SpeechSynthesisVoice;
      rate = 1;
      pitch = 1;
      onstart: (() => void) | null = null;
      onend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(text: string) {
        this.text = text;
      }
    },
  );
  return { speak, cancel, getVoices, getLastUtterance: () => last };
}

function voice(name: string, lang: string): SpeechSynthesisVoice {
  return { name, lang, default: false, localService: true, voiceURI: '' };
}

beforeEach(() => {
  __resetVoiceSpeakForTests();
  __resetReplyVoiceForTests();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function startOptedInVoiceSpeak(): () => void {
  const stop = startVoiceSpeak();
  setVoiceSpeakMuted(false);
  return stop;
}

describe('voice output opt-in', () => {
  it.each([null, '1', 'invalid'])('keeps completed captions readable without playback when preference=%s', (preference) => {
    installSpeechMocks();
    if (preference !== null) localStorage.setItem('gagos-voice-muted', preference);
    const stop = startVoiceSpeak();
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Readable without sound' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    expect(getVoiceSpeakState()).toMatchObject({ speaking: false, muted: true });
    expect(getReplyVoice()).toMatchObject({ phase: 'complete', text: 'Readable without sound' });
    stop();
  });

  it('does not request backend synthesis without output opt-in', () => {
    installSpeechMocks();
    const requests = vi.mocked(speakText).mock.calls.length;
    setBackendTTS(true);
    const stop = startVoiceSpeak();
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'A quiet answer' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    expect(vi.mocked(speakText).mock.calls.length).toBe(requests);
    expect(getVoiceSpeakState().speaking).toBe(false);
    expect(getReplyVoice()).toMatchObject({ phase: 'complete', text: 'A quiet answer' });
    stop();
  });

  it('fails quiet when the output preference cannot be read', () => {
    installSpeechMocks();
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Storage unavailable'); });
    const stop = startVoiceSpeak();
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Read this answer' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    expect(getVoiceSpeakState()).toMatchObject({ speaking: false, muted: true });
    expect(getReplyVoice()).toMatchObject({ phase: 'complete', text: 'Read this answer' });
    stop();
  });

  it('persists explicit unmute through service restart, and subsequent mute prevents another playback', () => {
    installSpeechMocks();
    const firstStop = startVoiceSpeak();
    setVoiceSpeakMuted(false);
    firstStop();
    const secondStop = startVoiceSpeak();
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Deliberate output' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    expect(getVoiceSpeakState()).toMatchObject({ muted: false, speaking: true });
    expect(getReplyVoice()).toMatchObject({ phase: 'streaming', text: 'Deliberate output' });
    setVoiceSpeakMuted(true);
    secondStop();
    const thirdStop = startVoiceSpeak();
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Keep this quiet' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    expect(getVoiceSpeakState()).toMatchObject({ muted: true, speaking: false });
    expect(getReplyVoice()).toMatchObject({ phase: 'complete', text: 'Keep this quiet' });
    thirdStop();
  });

  it('a saved explicit opt-in still permits genuine playback', () => {
    installSpeechMocks();
    localStorage.setItem('gagos-voice-muted', '0');
    const stop = startVoiceSpeak();
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Remembered output choice' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    expect(getVoiceSpeakState()).toMatchObject({ muted: false, speaking: true });
    expect(getReplyVoice()).toMatchObject({ phase: 'streaming', text: 'Remembered output choice' });
    stop();
  });
});

describe('voiceSpeak', () => {
  it('reports unsupported when speechSynthesis is absent', () => {
    const stop = startVoiceSpeak();
    expect(getVoiceSpeakState().supported).toBe(false);
    expect(getVoiceSpeakState().muted).toBe(true);
    stop();
  });

  it('speaks the final reply when reply-complete arrives', () => {
    const mocks = installSpeechMocks();
    const stop = startOptedInVoiceSpeak();
    expect(getVoiceSpeakState().supported).toBe(true);

    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Hello there' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });

    expect(mocks.speak).toHaveBeenCalledTimes(1);
    const utter = mocks.getLastUtterance();
    expect(utter?.text).toBe('Hello there');
    expect(getVoiceSpeakState().speaking).toBe(true);

    utter?.onend?.();
    expect(getVoiceSpeakState().speaking).toBe(false);
    stop();
  });

  it('cancels current speech on a new question', () => {
    const mocks = installSpeechMocks();
    const stop = startOptedInVoiceSpeak();

    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Hello there' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    expect(mocks.speak).toHaveBeenCalledTimes(1);

    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'question', text: 'next' } });
    expect(mocks.cancel).toHaveBeenCalled();
    stop();
  });

  it.each(['question', 'stopped', 'error'])('clears active playback on %s even when the browser sends no cancellation callback', (phase) => {
    const mocks = installSpeechMocks();
    mocks.cancel.mockImplementation(() => {});
    const stop = startOptedInVoiceSpeak();
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete', reply: 'An actual spoken answer' } });
    expect(getVoiceSpeakState().speaking).toBe(true);
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase } });
    expect(getVoiceSpeakState().speaking).toBe(false);
    stop();
  });

  it('ignores late browser callbacks after Stop and after a newer utterance starts', () => {
    const mocks = installSpeechMocks();
    mocks.cancel.mockImplementation(() => {});
    const stop = startOptedInVoiceSpeak();
    const events: string[] = [];
    const unsub = subscribeCognition((event) => { if (event.source === 'voice-tts') events.push(String(event.data?.phase)); });
    try {
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete', reply: 'Old' } });
      const old = mocks.getLastUtterance()!;
      expect(events).toEqual(['speaking']);
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'stopped' } });
      const stoppedCaption = getReplyVoice();
      old.onstart?.(); old.onend?.(); old.onerror?.();
      expect(getVoiceSpeakState().speaking).toBe(false);
      expect(getReplyVoice()).toBe(stoppedCaption);
      expect(events).toEqual(['speaking']);
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete', reply: 'New' } });
      const current = mocks.getLastUtterance()!;
      const currentCaption = getReplyVoice();
      old.onstart?.(); old.onend?.(); old.onerror?.();
      expect(getVoiceSpeakState().speaking).toBe(true);
      expect(getReplyVoice()).toBe(currentCaption);
      expect(events).toEqual(['speaking', 'speaking']);
      current.onend?.();
      expect(getVoiceSpeakState().speaking).toBe(false);
      expect(getReplyVoice()).toMatchObject({ phase: 'complete', text: 'New' });
      expect(events).toEqual(['speaking', 'speaking', 'speaking-complete']);
    } finally { unsub(); stop(); }
  });

  it('mic interruption cancels a queued browser utterance before onstart without fabricating playback completion', () => {
    const mocks = installSpeechMocks();
    mocks.speak.mockImplementation(() => {});
    mocks.cancel.mockImplementation(() => {});
    const stop = startOptedInVoiceSpeak();
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Queued' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    const queued = mocks.speak.mock.calls[0][0];
    const completedCaption = getReplyVoice();
    expect(getVoiceSpeakState().speaking).toBe(false);
    const cancels = mocks.cancel.mock.calls.length;
    interruptSpeech();
    expect(mocks.cancel).toHaveBeenCalledTimes(cancels + 1);
    queued.onstart?.(); queued.onend?.();
    expect(getVoiceSpeakState().speaking).toBe(false);
    expect(getReplyVoice()).toBe(completedCaption);
    stop();
  });

  it.each(['mute', 'last-unmount'])('settles a genuinely played caption on %s without trusting a cancellation callback', (cause) => {
    const mocks = installSpeechMocks();
    mocks.cancel.mockImplementation(() => {});
    const stop = startOptedInVoiceSpeak();
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'A spoken answer remains readable' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    const old = mocks.getLastUtterance()!;
    expect(getVoiceSpeakState().speaking).toBe(true);
    expect(getReplyVoice().phase).toBe('streaming');
    if (cause === 'mute') setVoiceSpeakMuted(true); else stop();
    expect(getVoiceSpeakState().speaking).toBe(false);
    expect(getReplyVoice()).toMatchObject({ phase: 'complete', text: 'A spoken answer remains readable' });
    const settled = getReplyVoice();
    old.onstart?.(); old.onend?.(); old.onerror?.();
    expect(getReplyVoice()).toBe(settled);
    expect(getVoiceSpeakState().speaking).toBe(false);
    if (cause === 'mute') stop();
  });

  it('does not speak while muted', () => {
    const mocks = installSpeechMocks();
    const stop = startOptedInVoiceSpeak();
    setVoiceSpeakMuted(true);
    expect(isVoiceSpeakMuted()).toBe(true);

    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Hello there' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });

    expect(mocks.speak).not.toHaveBeenCalled();
    stop();
  });

  it('settles a synchronous browser enqueue failure rather than leaving phantom pending speech', () => {
    const mocks = installSpeechMocks();
    mocks.speak.mockImplementation(() => { throw new Error('Speech queue unavailable'); });
    const stop = startOptedInVoiceSpeak();
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Readable answer' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    expect(getVoiceSpeakState().speaking).toBe(false);
    expect(getReplyVoice()).toMatchObject({ phase: 'error', text: 'Readable answer' });
    const cancels = mocks.cancel.mock.calls.length;
    interruptSpeech();
    expect(mocks.cancel).toHaveBeenCalledTimes(cancels);
    stop();
  });

  it('ignores its own voice-tts feedback events', () => {
    const mocks = installSpeechMocks();
    const stop = startOptedInVoiceSpeak();

    publishCognition({ type: 'voice-speaking', source: 'voice-tts', data: { phase: 'speaking-complete' } });
    publishCognition({ type: 'voice-speaking', source: 'voice-tts', data: { phase: 'speaking', reply: 'loop' } });

    expect(mocks.speak).not.toHaveBeenCalled();
    stop();
  });

  it('publishes speaking and speaking-complete cognition events', () => {
    installSpeechMocks();
    const stop = startOptedInVoiceSpeak();
    // cognition bus subscriber order is a singleton; use a lightweight spy on publishCognition
    // by observing state transitions instead.
    const stateLog: boolean[] = [];
    const unsubState = subscribeVoiceSpeak(() => stateLog.push(getVoiceSpeakState().speaking));

    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Hi' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });

    expect(stateLog).toContain(true);
    stop();
    unsubState();
  });

  it('prefers hi-IN, then en-IN, then any en voice', () => {
    const mocks = installSpeechMocks([
      voice('Google US English', 'en-US'),
      voice('Google हिन्दी', 'hi-IN'),
      voice('Google UK English', 'en-GB'),
    ]);
    const stop = startOptedInVoiceSpeak();

    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Namaste' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });

    expect(mocks.speak).toHaveBeenCalledTimes(1);
    const utter = mocks.getLastUtterance();
    expect(utter?.voice?.lang).toBe('hi-IN');
    stop();
  });

  describe('backend TTS', () => {
    class MockSource {
      buffer: { tag: string } | null = null;
      onended: (() => void) | null = null;
      connect(): void {}
      start(): void {
        startedTags.push(this.buffer?.tag ?? '');
      }
      stop(): void {}
    }

    const closeSpy = vi.fn();

    class MockAudioContext {
      destination = {};
      createBufferSource(): MockSource {
        const source = new MockSource();
        sources.push(source);
        return source;
      }
      decodeAudioData(buf: unknown): Promise<unknown> {
        return Promise.resolve(buf);
      }
      close(): Promise<void> {
        closeSpy();
        return Promise.resolve();
      }
    }

    let startedTags: string[];
    let sources: MockSource[];

    beforeEach(() => {
      startedTags = [];
      sources = [];
      closeSpy.mockClear();
      installSpeechMocks();
      vi.stubGlobal('AudioContext', MockAudioContext);
      setBackendTTS(true);
    });

    it('does not let a stale reply start playing after a newer reply already started', async () => {
      const stop = startOptedInVoiceSpeak();
      const speakTextMock = vi.mocked(speakText);
      const first = deferred<ArrayBuffer>();
      const second = deferred<ArrayBuffer>();
      speakTextMock.mockImplementationOnce(() => first.promise);
      speakTextMock.mockImplementationOnce(() => second.promise);

      // FIRST reply starts speaking; its network round-trip is still in flight.
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'FIRST' } });
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });

      // SECOND reply supersedes it before FIRST's network resolves.
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'SECOND' } });
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });

      // SECOND's network resolves first, then the stale FIRST's resolves after.
      second.resolve({ tag: 'SECOND' } as unknown as ArrayBuffer);
      await flush();
      first.resolve({ tag: 'FIRST' } as unknown as ArrayBuffer);
      await flush();

      expect(startedTags).toEqual(['SECOND']);
      stop();
    });

    it('still plays a reply normally when nothing supersedes it', async () => {
      const stop = startOptedInVoiceSpeak();
      const speakTextMock = vi.mocked(speakText);
      speakTextMock.mockResolvedValueOnce({ tag: 'ONLY' } as unknown as ArrayBuffer);

      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'ONLY' } });
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
      await flush();

      expect(startedTags).toEqual(['ONLY']);
      stop();
    });

    it('keeps a genuine completed caption while fetching/decoding and announces speech only after audio starts', async () => {
      const fetched = deferred<ArrayBuffer>();
      const decoded = deferred<unknown>();
      vi.mocked(speakText).mockReturnValueOnce(fetched.promise);
      vi.spyOn(MockAudioContext.prototype, 'decodeAudioData').mockReturnValueOnce(decoded.promise);
      const stop = startOptedInVoiceSpeak();
      const observations: string[][] = [];
      const unsub = subscribeCognition((event) => {
        if (event.source === 'voice-tts' && event.data?.phase === 'speaking') observations.push([...startedTags]);
      });
      try {
        publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Ready answer' } });
        publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
        const completedCaption = getReplyVoice();
        expect(getVoiceSpeakState().speaking).toBe(false);
        expect(completedCaption).toMatchObject({ phase: 'complete', text: 'Ready answer' });
        expect(observations).toEqual([]);
        fetched.resolve({ tag: 'Ready answer' } as unknown as ArrayBuffer);
        await flush();
        expect(getVoiceSpeakState().speaking).toBe(false);
        expect(getReplyVoice()).toBe(completedCaption);
        expect(startedTags).toEqual([]);
        decoded.resolve({ tag: 'Ready answer' });
        await flush();
        expect(getVoiceSpeakState().speaking).toBe(true);
        expect(getReplyVoice()).toMatchObject({ phase: 'streaming', text: 'Ready answer' });
        expect(observations).toEqual([['Ready answer']]);
        sources[0].onended?.();
        expect(getVoiceSpeakState().speaking).toBe(false);
        expect(getReplyVoice()).toMatchObject({ phase: 'complete', text: 'Ready answer' });
      } finally { unsub(); stop(); }
    });

    it('mic interruption cancels pending decode without a later start or caption-lease extension', async () => {
      const decoded = deferred<unknown>();
      vi.mocked(speakText).mockResolvedValueOnce({ tag: 'Cancelled' } as unknown as ArrayBuffer);
      vi.spyOn(MockAudioContext.prototype, 'decodeAudioData').mockReturnValueOnce(decoded.promise);
      const stop = startOptedInVoiceSpeak();
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Cancelled' } });
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
      const completedCaption = getReplyVoice();
      await flush();
      interruptSpeech();
      decoded.resolve({ tag: 'Cancelled' });
      await flush();
      expect(startedTags).toEqual([]);
      expect(getVoiceSpeakState().speaking).toBe(false);
      expect(getReplyVoice()).toBe(completedCaption);
      stop();
    });

    it('falls back to browser speech after backend failure without reporting queued fallback as playback', async () => {
      const mocks = installSpeechMocks();
      mocks.speak.mockImplementation(() => {});
      vi.mocked(speakText).mockRejectedValueOnce(new Error('TTS unavailable'));
      const stop = startOptedInVoiceSpeak();
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Fallback answer' } });
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
      const completedCaption = getReplyVoice();
      await flush();
      expect(startedTags).toEqual([]);
      expect(getVoiceSpeakState().speaking).toBe(false);
      expect(getReplyVoice()).toBe(completedCaption);
      expect(mocks.speak).toHaveBeenCalledTimes(1);
      const fallback = mocks.speak.mock.calls[0][0];
      fallback.onstart?.();
      expect(getVoiceSpeakState().speaking).toBe(true);
      expect(getReplyVoice()).toMatchObject({ phase: 'streaming', text: 'Fallback answer' });
      fallback.onend?.();
      expect(getVoiceSpeakState().speaking).toBe(false);
      expect(getReplyVoice()).toMatchObject({ phase: 'complete', text: 'Fallback answer' });
      stop();
    });

    it('ignores a superseded source end while the current source is playing', async () => {
      vi.mocked(speakText).mockResolvedValueOnce({ tag: 'Old' } as unknown as ArrayBuffer)
        .mockResolvedValueOnce({ tag: 'New' } as unknown as ArrayBuffer);
      const stop = startOptedInVoiceSpeak();
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete', reply: 'Old' } });
      await flush();
      const old = sources[0];
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete', reply: 'New' } });
      await flush();
      expect(startedTags).toEqual(['Old', 'New']);
      const currentCaption = getReplyVoice();
      old.onended?.();
      expect(getVoiceSpeakState().speaking).toBe(true);
      expect(getReplyVoice()).toBe(currentCaption);
      sources[1].onended?.();
      expect(getVoiceSpeakState().speaking).toBe(false);
      expect(getReplyVoice()).toMatchObject({ phase: 'complete', text: 'New' });
      stop();
    });

    it('does not recreate an audio context or decode a late response after the final consumer unmounts', async () => {
      const fetched = deferred<ArrayBuffer>();
      vi.mocked(speakText).mockReturnValueOnce(fetched.promise);
      const decode = vi.spyOn(MockAudioContext.prototype, 'decodeAudioData');
      const stop = startOptedInVoiceSpeak();
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete', reply: 'Late' } });
      stop();
      fetched.resolve({ tag: 'Late' } as unknown as ArrayBuffer);
      await flush();
      expect(decode).not.toHaveBeenCalled();
      expect(startedTags).toEqual([]);
      expect(getVoiceSpeakState().speaking).toBe(false);
    });

    it('closes the AudioContext when the last consumer stops', async () => {
      const stop = startOptedInVoiceSpeak();
      const speakTextMock = vi.mocked(speakText);
      speakTextMock.mockResolvedValueOnce({ tag: 'ONLY' } as unknown as ArrayBuffer);

      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'ONLY' } });
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
      await flush();

      expect(closeSpy).not.toHaveBeenCalled();
      stop();
      expect(closeSpy).toHaveBeenCalledTimes(1);
    });

    it('does not close the AudioContext while other consumers are still mounted', async () => {
      const stopA = startOptedInVoiceSpeak();
      const stopB = startOptedInVoiceSpeak();
      const speakTextMock = vi.mocked(speakText);
      speakTextMock.mockResolvedValueOnce({ tag: 'ONLY' } as unknown as ArrayBuffer);

      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'ONLY' } });
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
      await flush();

      stopA();
      expect(closeSpy).not.toHaveBeenCalled();
      stopB();
      expect(closeSpy).toHaveBeenCalledTimes(1);
    });
  });

  describe('interruptSpeech', () => {
    it('stops active speech and sets speaking to false', () => {
      const mocks = installSpeechMocks();
      const stop = startOptedInVoiceSpeak();

      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Long text' } });
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
      expect(getVoiceSpeakState().speaking).toBe(true);

      interruptSpeech();
      expect(getVoiceSpeakState().speaking).toBe(false);
      expect(mocks.cancel).toHaveBeenCalled();
      stop();
    });

    it('does nothing when not speaking', () => {
      const mocks = installSpeechMocks();
      const stop = startOptedInVoiceSpeak();
      expect(getVoiceSpeakState().speaking).toBe(false);

      interruptSpeech();
      expect(getVoiceSpeakState().speaking).toBe(false);
      expect(mocks.cancel).not.toHaveBeenCalled();
      stop();
    });

    it('does not toggle mute state', () => {
      installSpeechMocks();
      const stop = startOptedInVoiceSpeak();
      expect(getVoiceSpeakState().muted).toBe(false);

      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Hi' } });
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
      interruptSpeech();

      expect(getVoiceSpeakState().muted).toBe(false);
      stop();
    });
  });
});
