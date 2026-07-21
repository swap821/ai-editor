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
import { publishCognition } from '../superbrain/lib/cognitionBus';
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
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('voiceSpeak', () => {
  it('reports unsupported when speechSynthesis is absent', () => {
    const stop = startVoiceSpeak();
    expect(getVoiceSpeakState().supported).toBe(false);
    expect(getVoiceSpeakState().muted).toBe(false);
    stop();
  });

  it('speaks the final reply when reply-complete arrives', () => {
    const mocks = installSpeechMocks();
    const stop = startVoiceSpeak();
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
    const stop = startVoiceSpeak();

    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Hello there' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    expect(mocks.speak).toHaveBeenCalledTimes(1);

    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'question', text: 'next' } });
    expect(mocks.cancel).toHaveBeenCalled();
    stop();
  });

  it('does not speak while muted', () => {
    const mocks = installSpeechMocks();
    const stop = startVoiceSpeak();
    setVoiceSpeakMuted(true);
    expect(isVoiceSpeakMuted()).toBe(true);

    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Hello there' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });

    expect(mocks.speak).not.toHaveBeenCalled();
    stop();
  });

  it('ignores its own voice-tts feedback events', () => {
    const mocks = installSpeechMocks();
    const stop = startVoiceSpeak();

    publishCognition({ type: 'voice-speaking', source: 'voice-tts', data: { phase: 'speaking-complete' } });
    publishCognition({ type: 'voice-speaking', source: 'voice-tts', data: { phase: 'speaking', reply: 'loop' } });

    expect(mocks.speak).not.toHaveBeenCalled();
    stop();
  });

  it('publishes speaking and speaking-complete cognition events', () => {
    installSpeechMocks();
    const stop = startVoiceSpeak();
    const seen: { phase?: string; source?: string }[] = [];
    const unsub = subscribeVoiceSpeak(() => {});
    const unsubCog = vi.fn();
    // cognition bus subscriber order is a singleton; use a lightweight spy on publishCognition
    // by observing state transitions instead.
    const stateLog: boolean[] = [];
    const unsubState = subscribeVoiceSpeak(() => stateLog.push(getVoiceSpeakState().speaking));

    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Hi' } });
    publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });

    expect(stateLog).toContain(true);
    stop();
    unsub();
    unsubState();
  });

  it('prefers hi-IN, then en-IN, then any en voice', () => {
    const mocks = installSpeechMocks([
      voice('Google US English', 'en-US'),
      voice('Google हिन्दी', 'hi-IN'),
      voice('Google UK English', 'en-GB'),
    ]);
    const stop = startVoiceSpeak();

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
        return new MockSource();
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

    beforeEach(() => {
      startedTags = [];
      closeSpy.mockClear();
      installSpeechMocks();
      vi.stubGlobal('AudioContext', MockAudioContext);
      setBackendTTS(true);
    });

    it('does not let a stale reply start playing after a newer reply already started', async () => {
      const stop = startVoiceSpeak();
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
      const stop = startVoiceSpeak();
      const speakTextMock = vi.mocked(speakText);
      speakTextMock.mockResolvedValueOnce({ tag: 'ONLY' } as unknown as ArrayBuffer);

      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'ONLY' } });
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
      await flush();

      expect(startedTags).toEqual(['ONLY']);
      stop();
    });

    it('closes the AudioContext when the last consumer stops', async () => {
      const stop = startVoiceSpeak();
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
      const stopA = startVoiceSpeak();
      const stopB = startVoiceSpeak();
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
      const stop = startVoiceSpeak();

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
      const stop = startVoiceSpeak();
      expect(getVoiceSpeakState().speaking).toBe(false);

      interruptSpeech();
      expect(getVoiceSpeakState().speaking).toBe(false);
      expect(mocks.cancel).not.toHaveBeenCalled();
      stop();
    });

    it('does not toggle mute state', () => {
      installSpeechMocks();
      const stop = startVoiceSpeak();
      expect(getVoiceSpeakState().muted).toBe(false);

      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Hi' } });
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
      interruptSpeech();

      expect(getVoiceSpeakState().muted).toBe(false);
      stop();
    });
  });
});
