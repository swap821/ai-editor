export type VoicePresentationInput = {
  state: string | null | undefined;
  error: string | null | undefined;
  guided: boolean;
};

export type VoicePresentation = {
  status: string;
  error: string | null;
};

const GUIDED_STATUS: Readonly<Record<string, string>> = {
  'ready · local transcription': 'Voice input ready',
  'local transcription unavailable': 'Voice input unavailable',
  'capturing · browser recognition': 'Listening',
  'transcript ready · review before sending': 'Ready to review',
  'capture failed': 'Voice input failed',
  'requesting microphone permission': 'Microphone permission needed',
};

function guidedErrorCopy(error: string): string {
  const normalized = error.toLowerCase();
  if (normalized.includes('local transcription is unavailable')) {
    return 'Voice input unavailable. You can choose browser voice or type your message.';
  }
  if (normalized.includes('browser recognition') || normalized.includes('capture failed')) {
    return 'Voice input failed. You can type your message.';
  }
  if (normalized.includes('microphone')) {
    return 'Microphone input unavailable. You can type your message.';
  }
  return 'Voice input needs attention. You can type your message.';
}

export function presentVoiceStatus({ state, error, guided }: VoicePresentationInput): VoicePresentation {
  const rawStatus = state || 'local transcription unavailable';
  if (!guided) {
    return { status: rawStatus, error: error || null };
  }

  return {
    status: GUIDED_STATUS[rawStatus] || 'Voice input status unavailable',
    error: error ? guidedErrorCopy(error) : null,
  };
}
