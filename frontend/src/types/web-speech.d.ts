/**
 * Ambient type declarations for the Web Speech API (SpeechRecognition + SpeechSynthesis).
 *
 * The Web Speech API is not part of TypeScript's bundled DOM lib, so the code
 * that uses it fails `tsc --noEmit` with "Cannot find name 'SpeechRecognition'"
 * etc. This file declares the minimal surface actually used by:
 *   - frontend/src/App.jsx (window.SpeechRecognition / webkitSpeechRecognition,
 *     SpeechSynthesisUtterance, window.speechSynthesis)
 *   - frontend/src/superbrain/components/ui/SuperbrainHUD.tsx (same surface)
 *
 * It lives in the PRODUCT tree (src/types/) — NOT in the generated src/superbrain/**
 * tree — so it survives `npm run port` and fixes the errors without editing any
 * ported file. Ambient `.d.ts` files are loaded by tsc automatically (no import).
 *
 * Refs:
 *   https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API
 *   https://www.w3.org/TR/speech-api/
 */

declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognition;
    webkitSpeechRecognition?: new () => SpeechRecognition;
    speechSynthesis: SpeechSynthesis;
  }

  /**
   * SpeechRecognition interface (voice input / STT).
   * Supports both the standard (window.SpeechRecognition) and webkit prefix.
   */
  class SpeechRecognition extends EventTarget {
    continuous: boolean;
    interimResults: boolean;
    lang: string;
    maxAlternatives: number;

    start(): void;
    stop(): void;
    abort(): void;

    onstart: ((event: Event) => void) | null;
    onresult: ((event: SpeechRecognitionEvent) => void) | null;
    onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
    onend: ((event: Event) => void) | null;
  }

  /** Fired when recognition produces a result. */
  interface SpeechRecognitionEvent extends Event {
    resultIndex: number;
    results: SpeechRecognitionResultList;
  }

  /** Array-like collection of results. */
  interface SpeechRecognitionResultList {
    readonly length: number;
    [index: number]: SpeechRecognitionResult;
  }

  /** One result (may contain multiple alternatives). */
  interface SpeechRecognitionResult {
    readonly length: number;
    readonly isFinal: boolean;
    [index: number]: SpeechRecognitionAlternative;
  }

  /** One transcription + confidence. */
  interface SpeechRecognitionAlternative {
    readonly transcript: string;
    readonly confidence: number;
  }

  /** Fired on STT error. */
  interface SpeechRecognitionErrorEvent extends Event {
    error:
      | 'no-speech'
      | 'audio-capture'
      | 'network'
      | 'aborted'
      | 'service-not-allowed'
      | 'bad-grammar'
      | 'language-not-supported'
      | string;
  }

  /** Text-to-speech (TTS). */
  interface SpeechSynthesis extends EventTarget {
    pending: boolean;
    paused: boolean;
    speaking: boolean;

    speak(utterance: SpeechSynthesisUtterance): void;
    cancel(): void;
    pause(): void;
    resume(): void;
    getVoices(): SpeechSynthesisVoice[];

    onvoiceschanged: ((event: Event) => void) | null;
  }

  /** One piece of text to speak. */
  class SpeechSynthesisUtterance extends EventTarget {
    constructor(text?: string);

    text: string;
    lang: string;
    pitch: number;
    rate: number;
    volume: number;
    voice: SpeechSynthesisVoice | null;

    onstart: ((event: Event) => void) | null;
    onend: ((event: Event) => void) | null;
    onerror: ((event: SpeechSynthesisErrorEvent) => void) | null;
    onpause: ((event: Event) => void) | null;
    onresume: ((event: Event) => void) | null;
  }

  /** Fired when a TTS error occurs. */
  interface SpeechSynthesisErrorEvent extends Event {
    error: 'network' | 'synthesis-unavailable' | string;
  }

  /** One available voice for TTS. */
  interface SpeechSynthesisVoice {
    readonly voiceURI: string;
    readonly name: string;
    readonly lang: string;
    readonly localService: boolean;
    readonly default: boolean;
  }
}

export {};
