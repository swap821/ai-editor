import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { useVoiceInput } from './useVoiceInput';
import { setBackendTTS } from '../voiceSpeak';

vi.mock('../../superbrain/lib/aiosAdapter', () => ({
  AIOS_BASE: '',
  transcribeAudio: vi.fn(),
}));

vi.mock('../voiceSpeak', () => ({
  interruptSpeech: vi.fn(),
  setBackendTTS: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('useVoiceInput', () => {
  it('reports unavailable transcription and requires an explicit browser route', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ stt: { enabled: false }, tts: { enabled: true } }),
    }));

    const { result } = renderHook(() => useVoiceInput({
      voiceLang: 'en-US',
      busyRef: { current: false },
      inputRef: { current: null },
      setDraft: vi.fn(),
    }));

    await waitFor(() => {
      expect(result.current.voiceState).toBe('local transcription unavailable');
    });
    expect(result.current.backendVoice).toEqual({ stt: false, tts: true });
    expect(setBackendTTS).toHaveBeenCalledWith(true);

    await act(async () => {
      await result.current.startMic();
    });

    expect(result.current.listening).toBe(false);
    expect(result.current.voiceError).toBe(
      'Local transcription is unavailable. Choose the browser route explicitly, or type your message.',
    );
  });

  it('does not start capture while busy', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ stt: { enabled: false }, tts: { enabled: false } }),
    }));

    const { result } = renderHook(() => useVoiceInput({
      voiceLang: 'en-US',
      busyRef: { current: true },
      inputRef: { current: null },
      setDraft: vi.fn(),
    }));

    await waitFor(() => {
      expect(result.current.voiceState).toBe('local transcription unavailable');
    });

    await act(async () => {
      await result.current.startMic();
    });

    expect(result.current.listening).toBe(false);
    expect(result.current.voiceError).toBe('');
    expect(result.current.isHoldingMicRef.current).toBe(false);
  });
});
