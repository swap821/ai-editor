import { useCallback, useEffect, useRef, useState } from 'react';
import { transcribeAudio, AIOS_BASE } from '../../superbrain/lib/aiosAdapter';
import { setBackendTTS } from '../voiceSpeak';

/** One microphone owner. Browser recognition is an explicitly selected route. */
export function useVoiceInput({ voiceLang, busyRef, inputRef, setDraft }) {
  const [listening, setListening] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [backendVoice, setBackendVoice] = useState({ stt: false, tts: false });
  const [voiceState, setVoiceState] = useState('checking local voice');
  const [voiceError, setVoiceError] = useState('');
  const [browserVoiceAllowed, setBrowserVoiceAllowed] = useState(false);
  const [transcriptPending, setTranscriptPending] = useState(false);
  const recognitionRef = useRef(null);
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const isHoldingMicRef = useRef(false);
  const meterCleanup = useRef(null);
  const transcription = useRef(null);
  const generation = useRef(0);
  const alive = useRef(true);
  const browserVoiceAvailable = typeof window !== 'undefined' && !!(window.SpeechRecognition ?? window.webkitSpeechRecognition);

  const cleanCapture = useCallback(() => {
    meterCleanup.current?.(); meterCleanup.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop()); streamRef.current = null;
    if (alive.current) { setListening(false); setMicLevel(0); }
  }, []);
  useEffect(() => {
    alive.current = true;
    const request = new AbortController();
    void fetch(`${AIOS_BASE}/api/v1/voice/models`, { credentials: 'include', signal: request.signal })
      .then((r) => r.ok ? r.json() : Promise.reject(new Error('Local voice service unavailable.')))
      .then((data) => {
        if (request.signal.aborted) return;
        const voice = { stt: data.stt?.enabled === true, tts: data.tts?.enabled === true };
        setBackendVoice(voice); setBackendTTS(voice.tts); setVoiceState(voice.stt ? 'ready · local transcription' : 'local transcription unavailable');
      }).catch(() => { if (!request.signal.aborted) setVoiceState('local transcription unavailable'); });
    return () => {
      alive.current = false; generation.current += 1; isHoldingMicRef.current = false; request.abort(); transcription.current?.abort();
      try { if (recorderRef.current?.state === 'recording') recorderRef.current.stop(); } catch { /* already stopped */ }
      recorderRef.current = null; cleanCapture();
    };
  }, [cleanCapture]);

  useEffect(() => {
    if (backendVoice.stt || !browserVoiceAllowed || !browserVoiceAvailable) return;
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    const rec = new Recognition();
    rec.continuous = false; rec.interimResults = true; rec.lang = voiceLang;
    rec.onstart = () => { if (alive.current) { setListening(true); setVoiceState('capturing · browser recognition'); } };
    rec.onend = () => { isHoldingMicRef.current = false; if (alive.current) setListening(false); };
    rec.onerror = (event) => { isHoldingMicRef.current = false; if (alive.current) { setListening(false); setVoiceError(`Browser recognition failed: ${event.error || 'unavailable'}`); setVoiceState('capture failed'); } };
    rec.onresult = (event) => {
      if (!alive.current) return;
      let finalText = '', interim = '';
      for (let i = 0; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal) finalText += result[0].transcript; else interim += result[0].transcript;
      }
      setDraft(String(finalText || interim).slice(0, 8000));
      if (finalText.trim()) { setTranscriptPending(true); setVoiceState('transcript ready · review before sending'); inputRef.current?.focus(); }
    };
    recognitionRef.current = rec;
    return () => { rec.onresult = null; rec.onstart = null; rec.onend = null; rec.onerror = null; recognitionRef.current = null; try { rec.abort(); } catch { /* closed */ } };
  }, [backendVoice.stt, browserVoiceAllowed, browserVoiceAvailable, voiceLang, setDraft, inputRef]);

  const startMic = useCallback(async () => {
    if (busyRef?.current || isHoldingMicRef.current) return;
    setVoiceError('');
    if (!backendVoice.stt) {
      if (!browserVoiceAllowed || !recognitionRef.current) { setVoiceError('Local transcription is unavailable. Choose the browser route explicitly, or type your message.'); return; }
      isHoldingMicRef.current = true;
      try { recognitionRef.current.start(); } catch { isHoldingMicRef.current = false; setVoiceError('Browser microphone could not start.'); }
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { setVoiceError('Microphone recording is unavailable in this browser.'); return; }
    isHoldingMicRef.current = true;
    const epoch = ++generation.current;
    setVoiceState('requesting microphone permission');
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!alive.current || generation.current !== epoch || !isHoldingMicRef.current) { stream.getTracks().forEach((t) => t.stop()); return; }
      streamRef.current = stream;
      const mime = typeof MediaRecorder.isTypeSupported === 'function' && MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : undefined;
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      const chunks = [];
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recorder.onerror = () => { cleanCapture(); isHoldingMicRef.current = false; setVoiceError('Microphone recording failed.'); setVoiceState('capture failed'); };
      recorder.onstop = () => {
        cleanCapture();
        if (!alive.current || generation.current !== epoch) return;
        setVoiceState('transcribing locally');
        const request = new AbortController(); transcription.current = request;
        void transcribeAudio(new Blob(chunks, { type: recorder.mimeType || mime || 'audio/webm' }), { language: voiceLang, signal: request.signal })
          .then((result) => {
            if (!alive.current || request.signal.aborted || generation.current !== epoch) return;
            if (typeof result.text !== 'string') throw new Error('Missing transcript');
            setDraft(result.text.slice(0, 8000)); setTranscriptPending(!!result.text.trim());
            setVoiceState(result.text.trim() ? 'transcript ready · review before sending' : 'no speech detected'); inputRef.current?.focus();
          }).catch(() => { if (alive.current && !request.signal.aborted && generation.current === epoch) { setVoiceError('Local transcription failed. Your previous draft is retained.'); setVoiceState('transcription failed'); } });
      };
      recorderRef.current = recorder; recorder.start(); setListening(true); setVoiceState('capturing · local microphone');
      try {
        const context = new AudioContext(); const analyser = context.createAnalyser(); analyser.fftSize = 256;
        context.createMediaStreamSource(stream).connect(analyser);
        const buffer = new Uint8Array(analyser.frequencyBinCount);
        const meter = setInterval(() => {
          analyser.getByteTimeDomainData(buffer);
          const rms = Math.sqrt(buffer.reduce((sum, value) => sum + ((value - 128) / 128) ** 2, 0) / buffer.length);
          if (alive.current) setMicLevel(Math.min(1, rms * 3));
        }, 100);
        meterCleanup.current = () => { clearInterval(meter); void context.close(); };
      } catch { /* Capture still works without a level meter. */ }
    } catch (error) {
      stream?.getTracks().forEach((t) => t.stop());
      if (alive.current && generation.current === epoch) { isHoldingMicRef.current = false; setVoiceState('microphone unavailable'); setVoiceError(error?.name === 'NotAllowedError' ? 'Microphone permission denied.' : 'Microphone could not start.'); }
    }
  }, [backendVoice.stt, browserVoiceAllowed, voiceLang, busyRef, setDraft, inputRef, cleanCapture]);

  const stopMic = useCallback(() => {
    isHoldingMicRef.current = false;
    if (recorderRef.current?.state === 'recording') { recorderRef.current.stop(); recorderRef.current = null; }
    else { generation.current += 1; try { recognitionRef.current?.stop(); } catch { /* closed */ } cleanCapture(); }
  }, [cleanCapture]);
  return { listening, setListening, micLevel, backendVoice, transcriptPending, setTranscriptPending, startMic, stopMic, recognitionRef, isHoldingMicRef,
    voiceState, voiceError, browserVoiceAvailable, browserVoiceAllowed, setBrowserVoiceAllowed };
}
