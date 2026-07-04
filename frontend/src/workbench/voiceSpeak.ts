// Browser-native TTS loop for the GAGOS voice surface.
// Subscribes to cognition voice-speaking events, speaks the final reply,
// and publishes speaking/speaking-complete events so the 3D brain keeps glowing.
// SSR-safe: no window access until startVoiceSpeak() is called.
import { useEffect, useState } from 'react';
import { publishCognition, subscribeCognition } from '../superbrain/lib/cognitionBus';
import { speakText } from '../superbrain/lib/aiosAdapter';

export interface VoiceSpeakState {
  supported: boolean;
  muted: boolean;
  speaking: boolean;
}

const MUTE_KEY = 'gagos-voice-muted';

let state: VoiceSpeakState = { supported: false, muted: false, speaking: false };
const listeners = new Set<(s: VoiceSpeakState) => void>();
let cognitionUnsub: (() => void) | null = null;
let startCount = 0;
let pendingText = '';
let currentUtterance: SpeechSynthesisUtterance | null = null;
let backendTTSEnabled = false;
let audioCtx: AudioContext | null = null;

function set(next: Partial<VoiceSpeakState>): void {
  state = { ...state, ...next };
  for (const l of listeners) {
    try {
      l(state);
    } catch {
      // one bad listener never breaks the rest
    }
  }
}

function isSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.speechSynthesis !== 'undefined' &&
    typeof window.SpeechSynthesisUtterance !== 'undefined'
  );
}

function readMute(): boolean {
  try {
    return window.localStorage.getItem(MUTE_KEY) === '1';
  } catch {
    return false;
  }
}

function writeMute(muted: boolean): void {
  try {
    if (muted) window.localStorage.setItem(MUTE_KEY, '1');
    else window.localStorage.removeItem(MUTE_KEY);
  } catch {
    // storage may be blocked
  }
}

function selectVoice(): SpeechSynthesisVoice | undefined {
  if (typeof window === 'undefined' || !window.speechSynthesis) return undefined;
  const voices = window.speechSynthesis.getVoices();
  return (
    voices.find((v) => v.lang.toLowerCase().startsWith('hi-in')) ??
    voices.find((v) => v.lang.toLowerCase().startsWith('en-in')) ??
    voices.find((v) => v.lang.toLowerCase().startsWith('en')) ??
    voices[0]
  );
}

function cancelSpeech(): void {
  if (typeof window === 'undefined' || !window.speechSynthesis) return;
  try {
    window.speechSynthesis.cancel();
  } catch {
    // ignore
  }
  currentUtterance = null;
}

function publishSpeaking(text: string): void {
  publishCognition({
    type: 'voice-speaking',
    source: 'voice-tts',
    intensity: 0.75,
    data: { phase: 'speaking', reply: text },
  });
}

function publishSpeakingComplete(): void {
  publishCognition({
    type: 'voice-speaking',
    source: 'voice-tts',
    intensity: 0.5,
    data: { phase: 'speaking-complete' },
  });
}

function speakViaBrowser(trimmed: string): void {
  const utter = new window.SpeechSynthesisUtterance(trimmed);
  const voice = selectVoice();
  if (voice) utter.voice = voice;
  utter.rate = 1;
  utter.pitch = 1;
  utter.onstart = () => {
    currentUtterance = utter;
    set({ speaking: true });
    publishSpeaking(trimmed);
  };
  utter.onend = () => {
    if (currentUtterance === utter) currentUtterance = null;
    set({ speaking: false });
    publishSpeakingComplete();
  };
  utter.onerror = () => {
    if (currentUtterance === utter) currentUtterance = null;
    set({ speaking: false });
    publishCognition({
      type: 'voice-speaking',
      source: 'voice-tts',
      intensity: 0.4,
      data: { phase: 'error' },
    });
  };
  window.speechSynthesis.speak(utter);
}

function speakViaBackend(trimmed: string): void {
  set({ speaking: true });
  publishSpeaking(trimmed);
  speakText(trimmed)
    .then((buf) => {
      if (!audioCtx) audioCtx = new AudioContext();
      return audioCtx.decodeAudioData(buf);
    })
    .then((decoded) => {
      const src = audioCtx!.createBufferSource();
      src.buffer = decoded;
      src.connect(audioCtx!.destination);
      src.onended = () => {
        set({ speaking: false });
        publishSpeakingComplete();
      };
      src.start();
    })
    .catch(() => {
      set({ speaking: false });
      speakViaBrowser(trimmed);
    });
}

function speak(text: string): void {
  if (!state.supported || state.muted || !text.trim()) return;
  cancelSpeech();
  const trimmed = text.trim();
  if (backendTTSEnabled) {
    speakViaBackend(trimmed);
  } else {
    speakViaBrowser(trimmed);
  }
}

function ingest(event: { type: string; source?: string; data?: { phase?: string; reply?: string; text?: string } }): void {
  if (event.type !== 'voice-speaking') return;
  if (event.source === 'voice-tts') return; // ignore our own feedback
  const p = event.data?.phase ?? '';
  if (p === 'question' || p === 'stopped' || p === 'error') {
    pendingText = '';
    cancelSpeech();
    return;
  }
  if (p === 'reply') {
    pendingText = String(event.data?.reply ?? '');
    return;
  }
  if (p === 'reply-complete') {
    const text = pendingText || String(event.data?.reply ?? '');
    pendingText = '';
    speak(text);
  }
}

/** Start the TTS engine. Safe to call multiple times (reference counted). */
export function startVoiceSpeak(): () => void {
  startCount += 1;
  if (startCount === 1) {
    set({ supported: isSupported(), muted: readMute() });
    if (state.supported) {
      // Prime the voice list; browsers that load voices asynchronously will still
      // fall back to the default voice on the first utterance.
      try {
        window.speechSynthesis.getVoices();
      } catch {
        // ignore
      }
    }
    cognitionUnsub = subscribeCognition((e) => ingest(e as Parameters<typeof ingest>[0]));
  }
  return () => {
    startCount -= 1;
    if (startCount === 0 && cognitionUnsub) {
      cognitionUnsub();
      cognitionUnsub = null;
      cancelSpeech();
    }
  };
}

export function setVoiceSpeakMuted(muted: boolean): void {
  writeMute(muted);
  set({ muted });
  if (muted) cancelSpeech();
}

export function setBackendTTS(enabled: boolean): void {
  backendTTSEnabled = enabled;
}

export function isVoiceSpeakMuted(): boolean {
  return state.muted;
}

export function getVoiceSpeakState(): VoiceSpeakState {
  return state;
}

export function subscribeVoiceSpeak(l: (s: VoiceSpeakState) => void): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

/** React hook: reads live TTS state and starts/stops the engine with the component. */
export function useVoiceSpeak(): VoiceSpeakState {
  const [s, setS] = useState(getVoiceSpeakState);
  useEffect(() => {
    setS(getVoiceSpeakState());
    const stop = startVoiceSpeak();
    const unsub = subscribeVoiceSpeak(setS);
    return () => {
      unsub();
      stop();
    };
  }, []);
  return s;
}

export function __resetVoiceSpeakForTests(): void {
  state = { supported: false, muted: false, speaking: false };
  listeners.clear();
  if (startCount > 0 && cognitionUnsub) {
    cognitionUnsub();
    cognitionUnsub = null;
  }
  startCount = 0;
  pendingText = '';
  currentUtterance = null;
  try {
    window.localStorage.removeItem(MUTE_KEY);
  } catch {
    // storage may be blocked
  }
}
