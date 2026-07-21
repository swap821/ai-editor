import { useCallback, useEffect, useRef, useState } from 'react';
import { transcribeAudio, AIOS_BASE } from '../../superbrain/lib/aiosAdapter';
import { setBackendTTS } from '../voiceSpeak';

function cleanText(input, maxLen = 8000) {
  return String(input ?? '').slice(0, maxLen);
}

export function useVoiceInput({
  voiceLang,
  busyRef,
  inputRef,
  setDraft,
}) {
  const [listening, setListening] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [backendVoice, setBackendVoice] = useState({ stt: false, tts: false });
  const [transcriptPending, setTranscriptPending] = useState(false);

  const recognitionRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const isHoldingMicRef = useRef(false);
  const analyserCleanupRef = useRef(null);

  // Fetch voice models capability on mount
  useEffect(() => {
    fetch(`${AIOS_BASE}/api/v1/voice/models`, { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) {
          setBackendVoice({ stt: !!d.stt?.enabled, tts: !!d.tts?.enabled });
          setBackendTTS(!!d.tts?.enabled);
        }
      })
      .catch(() => {});
  }, []);

  // Voice input recognition setup
  useEffect(() => {
    if (backendVoice.stt) {
      recognitionRef.current = null;
      return undefined;
    }
    const SR = typeof window !== 'undefined' ? (window.SpeechRecognition ?? window.webkitSpeechRecognition) : null;
    if (!SR) return undefined;
    const rec = new SR();
    rec.continuous = false;
    rec.interimResults = true;
    rec.lang = voiceLang;
    rec.onstart = () => setListening(true);
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    rec.onresult = (event) => {
      let finalText = '';
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const r = event.results[i];
        if (r.isFinal) finalText += r[0].transcript;
        else interim += r[0].transcript;
      }
      setDraft(cleanText(finalText || interim, 200));
      if (finalText.trim()) {
        setTranscriptPending(true);
        inputRef.current?.focus();
      }
    };
    recognitionRef.current = rec;
    return () => {
      recognitionRef.current = null;
      try { rec.abort(); } catch { /* already closed */ }
    };
  }, [backendVoice.stt, voiceLang, setDraft, inputRef]);

  const startMic = useCallback(() => {
    if (busyRef?.current || isHoldingMicRef.current) return;
    isHoldingMicRef.current = true;
    setDraft('');
    if (backendVoice.stt) {
      navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
        const mr = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        const chunks = [];
        mr.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
        mr.onstop = () => {
          stream.getTracks().forEach((t) => t.stop());
          const blob = new Blob(chunks, { type: 'audio/webm' });
          setListening(false);
          transcribeAudio(blob, { language: voiceLang })
            .then((r) => { setDraft(r.text); if (r.text.trim()) { setTranscriptPending(true); inputRef.current?.focus(); } })
            .catch(() => setDraft(''));
        };
        mediaRecorderRef.current = mr;
        mr.start();
        setListening(true);

        try {
          const actx = new AudioContext();
          const src = actx.createMediaStreamSource(stream);
          const analyser = actx.createAnalyser();
          analyser.fftSize = 256;
          src.connect(analyser);
          const buf = new Uint8Array(analyser.frequencyBinCount);
          let raf;
          const tick = () => {
            analyser.getByteTimeDomainData(buf);
            let sum = 0;
            for (let i = 0; i < buf.length; i++) {
              const v = (buf[i] - 128) / 128;
              sum += v * v;
            }
            const rms = Math.sqrt(sum / buf.length);
            setMicLevel(Math.min(1, rms * 3));
            raf = requestAnimationFrame(tick);
          };
          raf = requestAnimationFrame(tick);
          analyserCleanupRef.current = () => {
            cancelAnimationFrame(raf);
            try { actx.close(); } catch { /* already closed */ }
            setMicLevel(0);
          };
        } catch { /* AudioContext unavailable */ }
      }).catch(() => { isHoldingMicRef.current = false; });
    } else {
      try { recognitionRef.current?.start(); } catch { /* already started */ }
    }
  }, [backendVoice.stt, voiceLang, busyRef, setDraft, inputRef]);

  const stopMic = useCallback(() => {
    if (!isHoldingMicRef.current) return;
    isHoldingMicRef.current = false;
    if (analyserCleanupRef.current) {
      analyserCleanupRef.current();
      analyserCleanupRef.current = null;
    }
    if (backendVoice.stt && mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current = null;
    } else {
      try { recognitionRef.current?.stop(); } catch { /* already stopped */ }
    }
  }, [backendVoice.stt]);

  return {
    listening,
    setListening,
    micLevel,
    backendVoice,
    transcriptPending,
    setTranscriptPending,
    startMic,
    stopMic,
    recognitionRef,
    isHoldingMicRef,
  };
}
