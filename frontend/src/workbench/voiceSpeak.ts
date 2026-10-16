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

let state: VoiceSpeakState = { supported: false, muted: true, speaking: false };
const listeners = new Set<(s: VoiceSpeakState) => void>();
let cognitionUnsub: (() => void) | null = null;
let startCount = 0;
let pendingText = '';
// Loading/queued speech is cancellable, but is not yet observed playback.
let pendingSpeech = false;
let currentUtterance: SpeechSynthesisUtterance | null = null;
let backendTTSEnabled = false;
let audioCtx: AudioContext | null = null;
let currentSource: AudioBufferSourceNode | null = null;
/**
 * Bumped by cancelSpeech() (called at the top of every speak()). Each
 * speakViaBackend() call captures the generation it was started under and
 * checks it before applying the network response's side effects -- without
 * this, a stale reply whose fetch/decode round-trip is still in flight when
 * a newer reply arrives can win the race and start playing after the newer
 * reply already started (cancelSpeech() has nothing to stop yet, since the
 * stale call's AudioBufferSourceNode doesn't exist until its own decode
 * resolves, which can happen after the new call's).
 */
let speakGeneration = 0;

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
    // Missing/legacy/unknown preference is not evidence of output opt-in.
    return window.localStorage.getItem(MUTE_KEY) !== '0';
  } catch {
    return true;
  }
}

function writeMute(muted: boolean): void {
  try {
    window.localStorage.setItem(MUTE_KEY, muted ? '1' : '0');
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

function cancelSpeech(): boolean {
  const wasSpeaking = state.speaking;
  // Invalidate callbacks before cancel/stop: browsers may call them synchronously.
  speakGeneration += 1;
  pendingSpeech = false;
  if (typeof window !== 'undefined' && window.speechSynthesis) {
    try { window.speechSynthesis.cancel(); } catch { /* ignore */ }
  }
  if (currentSource) {
    try { currentSource.stop(); } catch { /* already stopped */ }
    currentSource = null;
  }
  currentUtterance = null;
  if (state.speaking) set({ speaking: false });
  return wasSpeaking;
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
  const myGeneration = speakGeneration;
  const utter = new window.SpeechSynthesisUtterance(trimmed);
  currentUtterance = utter;
  const voice = selectVoice();
  if (voice) utter.voice = voice;
  utter.rate = 1;
  utter.pitch = 1;
  utter.onstart = () => {
    if (myGeneration !== speakGeneration || currentUtterance !== utter) return;
    pendingSpeech = false;
    set({ speaking: true });
    publishSpeaking(trimmed);
  };
  utter.onend = () => {
    if (myGeneration !== speakGeneration || currentUtterance !== utter) return;
    currentUtterance = null;
    pendingSpeech = false;
    const wasSpeaking = state.speaking;
    set({ speaking: false });
    if (wasSpeaking) publishSpeakingComplete();
  };
  const onError = () => {
    if (myGeneration !== speakGeneration || currentUtterance !== utter) return;
    currentUtterance = null;
    pendingSpeech = false;
    set({ speaking: false });
    publishCognition({
      type: 'voice-speaking',
      source: 'voice-tts',
      intensity: 0.4,
      data: { phase: 'error' },
    });
  };
  utter.onerror = onError;
  try { window.speechSynthesis.speak(utter); } catch { onError(); }
}

function speakViaBackend(trimmed: string): void {
  const myGeneration = speakGeneration;
  speakText(trimmed)
    .then((buf) => {
      if (myGeneration !== speakGeneration) return;
      if (!audioCtx) audioCtx = new AudioContext();
      return audioCtx.decodeAudioData(buf);
    })
    .then((decoded) => {
      if (myGeneration !== speakGeneration || !decoded) return; // superseded while decoding
      const src = audioCtx!.createBufferSource();
      currentSource = src;
      src.buffer = decoded;
      src.connect(audioCtx!.destination);
      src.onended = () => {
        if (myGeneration !== speakGeneration || currentSource !== src) return;
        currentSource = null;
        set({ speaking: false });
        publishSpeakingComplete();
      };
      src.start();
      pendingSpeech = false;
      set({ speaking: true });
      publishSpeaking(trimmed);
    })
    .catch(() => {
      if (myGeneration !== speakGeneration) return; // superseded; don't clobber the active call
      currentSource = null;
      set({ speaking: false });
      speakViaBrowser(trimmed);
    });
}

function speak(text: string): void {
  if (!state.supported || state.muted || !text.trim()) return;
  cancelSpeech();
  pendingSpeech = true;
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
    if (startCount === 0) {
      if (cognitionUnsub) {
        cognitionUnsub();
        cognitionUnsub = null;
      }
      if (cancelSpeech()) publishSpeakingComplete();
      // Close the backend-TTS AudioContext (a separate context from
      // soundEngine.ts's own) when the last consumer unmounts, instead of
      // holding an audio device handle open for the life of the tab.
      if (audioCtx) {
        try { void audioCtx.close(); } catch { /* already closed */ }
        audioCtx = null;
      }
    }
  };
}

export function setVoiceSpeakMuted(muted: boolean): void {
  writeMute(muted);
  set({ muted });
  if (muted && cancelSpeech()) publishSpeakingComplete();
}

export function setBackendTTS(enabled: boolean): void {
  backendTTSEnabled = enabled;
}

export function interruptSpeech(): void {
  if (!state.speaking && !pendingSpeech) return;
  const wasSpeaking = cancelSpeech();
  if (wasSpeaking) publishSpeakingComplete();
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
    const unsub = subscribeVoiceSpeak(setS);
    const stop = startVoiceSpeak();
    setS(getVoiceSpeakState());
    return () => {
      unsub();
      stop();
    };
  }, []);
  return s;
}

export function __resetVoiceSpeakForTests(): void {
  state = { supported: false, muted: true, speaking: false };
  listeners.clear();
  if (startCount > 0 && cognitionUnsub) {
    cognitionUnsub();
    cognitionUnsub = null;
  }
  startCount = 0;
  pendingText = '';
  pendingSpeech = false;
  currentUtterance = null;
  currentSource = null;
  backendTTSEnabled = false;
  audioCtx = null;
  speakGeneration = 0;
  try {
    window.localStorage.removeItem(MUTE_KEY);
  } catch {
    // storage may be blocked
  }
}
