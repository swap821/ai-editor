import { useState, useEffect } from 'react';

/**
 * VoiceCommandHandler provides continuous listening mode using the Web Speech API.
 * It is a non-UI component that emits spoken transcripts to an 'onCommand' callback.
 *
 * NOT MOUNTED ANYWHERE as of 2026-08-04. The shipped voice path is the mic button
 * in `frontend/src/workbench/GagosChrome.jsx`, which owns SpeechRecognition and
 * calls `sendVoiceTurn`. This component was previously mounted by SuperbrainApp
 * with `isListening` pinned to false, so it never ran. It is kept because it is
 * a working, tested generic wrapper worth reusing if a second surface ever needs
 * one -- but it is unreferenced today, and its passing tests prove only that the
 * component works in isolation, NOT that voice input works in the product.
 * Do not cite this file or its tests as evidence of a shipped voice feature.
 */
export default function VoiceCommandHandler({ onCommand, isListening, language = 'en-US' }) {
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!isListening) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setError('Web Speech API is not supported in this browser.');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = language;

    recognition.onresult = (event) => {
      const last = event.results.length - 1;
      const transcript = event.results[last][0].transcript.trim();
      if (transcript && onCommand) {
        onCommand(transcript);
      }
    };

    recognition.onerror = (event) => {
      console.error('[VoiceCommandHandler] Error:', event.error);
      setError(`Speech error: ${event.error}`);
    };

    try {
      recognition.start();
    } catch (error) {
      console.error('[VoiceCommandHandler] Failed to start recognition', error);
    }

    return () => {
      try {
        recognition.stop();
      } catch {
        // ignore
      }
    };
  }, [isListening, onCommand, language]);

  if (error) {
    return <div style={{ display: 'none' }} data-testid="voice-error">{error}</div>;
  }

  return <div style={{ display: 'none' }} data-testid="voice-listening-status">{isListening ? 'listening' : 'idle'}</div>;
}
