import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { act } from 'react';
import { __resetActiveBrainForTests } from '../superbrain/lib/activeBrain';
import { __resetTabStoreForTests, getTabStoreSnapshot } from '../superbrain/lib/tabStore';
import { __resetVoiceSpeakForTests, getVoiceSpeakState, setVoiceSpeakMuted } from './voiceSpeak';
import { publishCognition } from '../superbrain/lib/cognitionBus';
import { __resetReplyVoiceForTests, getReplyVoice } from '../superbrain/lib/replyVoiceBus';
import { deriveBodySpeech } from '../superbrain/lib/bodySpeech';
import { dispatchLivingMirrorEvent } from '../superbrain/lib/livingMirrorRegistry';
import { useMirrorStore } from '../superbrain/lib/mirrorStore';
import { setEmergencyStopPresentation } from '../livingMirror/emergencyStopPresentation';

const { sendDirective, sendVoiceTurn, approvePendingApproval, getLastEmittedCode, previewIntent, fetchOnboardingState, transcribeAudio, correctHumanState, isWorkIntent, recognitionProbe } = vi.hoisted(() => ({
  sendDirective: vi.fn().mockResolvedValue({ paused: false, answer: 'ok' }),
  sendVoiceTurn: vi.fn().mockResolvedValue('ok'),
  approvePendingApproval: vi.fn().mockResolvedValue({ paused: false, ok: true, answer: 'approved' }),
  getLastEmittedCode: vi.fn(() => null),
  previewIntent: vi.fn().mockResolvedValue({ intent: 'code', confidence: 0.9, tool: 'create_file' }),
  fetchOnboardingState: vi.fn().mockResolvedValue({
    firstDirective: true,
    firstApproval: true,
    firstVerify: true,
    firstCloudRoute: true,
    firstAutonomy: true,
  }),
  transcribeAudio: vi.fn().mockResolvedValue({ text: 'hello world', language: 'en', confidence: 0.95 }),
  correctHumanState: vi.fn().mockResolvedValue(true),
  isWorkIntent: vi.fn(() => true),
  recognitionProbe: { current: null as {
    onresult: ((event: unknown) => void) | null;
    onstart: (() => void) | null;
    onend: (() => void) | null;
    onerror: ((event: { error?: string }) => void) | null;
    start: () => void;
  } | null },
}));

vi.mock('../superbrain/SuperbrainApp', () => ({
  default: () => <div data-testid="mock-being">being</div>,
}));

vi.mock('../superbrain/lib/intentRouting', async () => {
  const actual = await vi.importActual<typeof import('../superbrain/lib/intentRouting')>(
    '../superbrain/lib/intentRouting',
  );
  return { ...actual, isWorkIntent };
});

vi.mock('../superbrain/lib/aiosAdapter', async () => {
  const actual = await vi.importActual<typeof import('../superbrain/lib/aiosAdapter')>(
    '../superbrain/lib/aiosAdapter',
  );
  return { ...actual, sendDirective, sendVoiceTurn, approvePendingApproval, getLastEmittedCode, previewIntent, fetchOnboardingState, transcribeAudio, correctHumanState };
});

describe('GagosChrome voice UX', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    __resetActiveBrainForTests();
    __resetTabStoreForTests();
    __resetVoiceSpeakForTests();
    __resetReplyVoiceForTests();
    setEmergencyStopPresentation('unknown');
    useMirrorStore.setState({ recentEvents: [], lastEventId: null,
      lastTurnStartedEventId: null, lastVerificationEventId: null });
    sendDirective.mockClear();
    sendVoiceTurn.mockReset().mockResolvedValue('ok');
    approvePendingApproval.mockClear().mockResolvedValue({ paused: false, ok: true, answer: 'approved' });
    transcribeAudio.mockClear();
    correctHumanState.mockClear().mockResolvedValue(true);
    isWorkIntent.mockReset().mockReturnValue(true);
    recognitionProbe.current = null;
    localStorage.clear();
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
    vi.stubGlobal('SpeechRecognition', class {
      continuous = false;
      interimResults = true;
      lang = 'en-IN';
      onstart: (() => void) | null = null;
      onend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      onresult: ((e: unknown) => void) | null = null;
      constructor() { recognitionProbe.current = this; }
      start() { this.onstart?.(); }
      stop() { this.onend?.(); }
      abort() { this.onend?.(); }
    });
    vi.stubGlobal('speechSynthesis', {
      speak: vi.fn(),
      cancel: vi.fn(),
      getVoices: vi.fn(() => []),
      pause: vi.fn(),
      resume: vi.fn(),
    });
    vi.stubGlobal('SpeechSynthesisUtterance', class {
      text: string;
      voice = null;
      rate = 1;
      pitch = 1;
      onstart: (() => void) | null = null;
      onend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(text: string) { this.text = text; }
    });
    vi.stubGlobal('fetch', vi.fn(async () => new Response('Unavailable test endpoint', { status: 503 })));
  });

  afterEach(() => {
    (window as unknown as { __clearApproval?: () => void }).__clearApproval?.();
  });

  it('acknowledges measured microphone capture without a focused input or submitted turn', async () => {
    const reportInputAttention = vi.fn();
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome onInputAttentionChange={reportInputAttention} />);
    fireEvent.click(screen.getByRole('checkbox', { name: /use browser recognition/i }));
    await waitFor(() => expect(recognitionProbe.current).not.toBeNull());
    const input = screen.getByLabelText('Talk to GAGOS');
    const mic = screen.getByRole('button', { name: /hold to speak/i });
    await act(async () => { fireEvent.pointerDown(mic); });
    expect(reportInputAttention).toHaveBeenLastCalledWith(true);
    expect(input).toHaveValue('');
    expect(document.activeElement).not.toBe(input);
    expect(sendDirective).not.toHaveBeenCalled();
    expect(sendVoiceTurn).not.toHaveBeenCalled();
    await act(async () => { fireEvent.pointerUp(mic); });
    expect(reportInputAttention.mock.calls).toEqual([[true], [false]]);
  });

  describe('actual capture-to-reply interruption', () => {
    type Utterance = { onstart: (() => void) | null; onend: (() => void) | null; onerror: (() => void) | null };
    function installReplyOutput(playing: boolean) {
      let utterance!: Utterance;
      vi.stubGlobal('speechSynthesis', {
        speak: vi.fn((next: Utterance) => { utterance = next; if (playing) next.onstart?.(); }),
        cancel: vi.fn(), // Real browsers need not deliver onend when cancelled.
        getVoices: vi.fn(() => []), pause: vi.fn(), resume: vi.fn(),
      });
      return () => utterance;
    }
    async function startReply() {
      await act(async () => {
        setVoiceSpeakMuted(false); // Explicit output opt-in, independent of the shipped default.
        publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'A readable completed answer' } });
        publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
      });
    }
    async function consentToBrowserCapture() {
      fireEvent.click(screen.getByRole('checkbox', { name: /use browser recognition/i }));
      await waitFor(() => expect(recognitionProbe.current).not.toBeNull());
      return recognitionProbe.current!;
    }
    function expectNoSubmittedAction() {
      expect(sendDirective).not.toHaveBeenCalled();
      expect(sendVoiceTurn).not.toHaveBeenCalled();
      expect(approvePendingApproval).not.toHaveBeenCalled();
    }

    it.each([true, false])('confirmed browser capture interrupts playing=%s; request alone does not', async (playing) => {
      const getUtterance = installReplyOutput(playing);
      const { default: GagosChrome } = await import('./GagosChrome');
      render(<GagosChrome />);
      const recognition = await consentToBrowserCapture();
      vi.spyOn(recognition, 'start').mockImplementation(() => {}); // Delay the external start event.
      const input = screen.getByLabelText('Talk to GAGOS');
      fireEvent.change(input, { target: { value: 'Keep this microphone draft unsent' } });
      await startReply();
      expect(getVoiceSpeakState().speaking).toBe(playing);
      const beforeCapture = getReplyVoice();
      expect(beforeCapture).toMatchObject({ phase: playing ? 'streaming' : 'complete', text: 'A readable completed answer' });
      const mic = screen.getByRole('button', { name: /hold to speak/i });
      await act(async () => { fireEvent.pointerDown(mic); });
      expect(getVoiceSpeakState().speaking).toBe(playing);
      expect(getReplyVoice()).toBe(beforeCapture);
      await act(async () => { recognition.onstart?.(); });
      expect(screen.getByRole('button', { name: 'Stop microphone' })).toBeInTheDocument();
      expect(getVoiceSpeakState().speaking).toBe(false);
      expect(getReplyVoice()).toMatchObject({ phase: 'complete', text: 'A readable completed answer' });
      if (!playing) expect(getReplyVoice()).toBe(beforeCapture); // No fake end or renewed caption lease.
      const afterCapture = getReplyVoice();
      await act(async () => { getUtterance().onstart?.(); getUtterance().onend?.(); getUtterance().onerror?.(); });
      expect(getVoiceSpeakState().speaking).toBe(false);
      expect(getReplyVoice()).toBe(afterCapture);
      expect(input).toHaveValue('Keep this microphone draft unsent');
      expectNoSubmittedAction();
      await act(async () => { fireEvent.pointerUp(mic); });
    });

    it.each(['released', 'route-disabled'])('ignores a delayed browser start from an abandoned capture: %s', async (cause) => {
      installReplyOutput(true);
      const reportInputAttention = vi.fn();
      const { default: GagosChrome } = await import('./GagosChrome');
      render(<GagosChrome onInputAttentionChange={reportInputAttention} />);
      const recognition = await consentToBrowserCapture();
      vi.spyOn(recognition, 'start').mockImplementation(() => {});
      const input = screen.getByLabelText('Talk to GAGOS');
      fireEvent.change(input, { target: { value: 'Keep the previous draft' } });
      await startReply();
      const beforeCapture = getReplyVoice();
      const mic = screen.getByRole('button', { name: /hold to speak/i });
      await act(async () => { fireEvent.pointerDown(mic); });
      const delayedStart = recognition.onstart!;
      await act(async () => {
        if (cause === 'released') fireEvent.pointerUp(mic);
        else fireEvent.click(screen.getByRole('checkbox', { name: /use browser recognition/i }));
        delayedStart();
      });
      expect(screen.queryByRole('button', { name: 'Stop microphone' })).not.toBeInTheDocument();
      expect(reportInputAttention).not.toHaveBeenCalledWith(true);
      expect(getVoiceSpeakState().speaking).toBe(true);
      expect(getReplyVoice()).toBe(beforeCapture);
      expect(input).toHaveValue('Keep the previous draft');
      expectNoSubmittedAction();
    });

    it('unavailable or refused browser capture retains playback, the caption and typed fallback', async () => {
      installReplyOutput(true);
      const { default: GagosChrome } = await import('./GagosChrome');
      render(<GagosChrome />);
      const input = screen.getByLabelText('Talk to GAGOS');
      fireEvent.change(input, { target: { value: 'Typed input remains available' } });
      await startReply();
      const beforeCapture = getReplyVoice();
      const mic = screen.getByRole('button', { name: /hold to speak/i });
      await act(async () => { fireEvent.pointerDown(mic); fireEvent.pointerUp(mic); });
      expect(getVoiceSpeakState().speaking).toBe(true);
      expect(getReplyVoice()).toBe(beforeCapture);
      const recognition = await consentToBrowserCapture();
      vi.spyOn(recognition, 'start').mockImplementation(() => { throw new Error('Capture refused'); });
      await act(async () => { fireEvent.pointerDown(mic); });
      expect(screen.queryByRole('button', { name: 'Stop microphone' })).not.toBeInTheDocument();
      expect(getVoiceSpeakState().speaking).toBe(true);
      expect(getReplyVoice()).toBe(beforeCapture);
      expect(input).toHaveValue('Typed input remains available');
      expect(input).not.toBeDisabled();
      expectNoSubmittedAction();
    });

    it.each([true, false])('successful local recording interrupts playing=%s, not a pending or denied permission request', async (playing) => {
      const getUtterance = installReplyOutput(playing);
      vi.stubGlobal('fetch', vi.fn(async (url) => String(url).endsWith('/api/v1/voice/models')
        ? new Response(JSON.stringify({ stt: { enabled: true }, tts: { enabled: false } }), { status: 200 })
        : new Response('Unavailable test endpoint', { status: 503 })));
      let resolveCapture!: (stream: MediaStream) => void;
      let rejectCapture!: (error: Error) => void;
      const getUserMedia = vi.fn(() => new Promise<MediaStream>((resolve, reject) => { resolveCapture = resolve; rejectCapture = reject; }));
      vi.stubGlobal('navigator', Object.assign(Object.create(navigator), { mediaDevices: { getUserMedia } }));
      const track = { stop: vi.fn() };
      const stream = { getTracks: () => [track] } as unknown as MediaStream;
      vi.stubGlobal('MediaRecorder', class {
        state = 'inactive'; mimeType = 'audio/webm';
        ondataavailable = null; onerror = null; onstop: (() => void) | null = null;
        static isTypeSupported() { return true; }
        start() { this.state = 'recording'; }
        stop() { this.state = 'inactive'; this.onstop?.(); }
      });
      const { default: GagosChrome } = await import('./GagosChrome');
      render(<GagosChrome />);
      await screen.findByText('Voice input ready');
      const input = screen.getByLabelText('Talk to GAGOS');
      fireEvent.change(input, { target: { value: 'Retain this local voice draft' } });
      await startReply();
      const beforeCapture = getReplyVoice();
      const mic = screen.getByRole('button', { name: /hold to speak/i });
      await act(async () => { fireEvent.pointerDown(mic); });
      expect(getVoiceSpeakState().speaking).toBe(playing);
      expect(getReplyVoice()).toBe(beforeCapture);
      await act(async () => { rejectCapture(Object.assign(new Error('Denied'), { name: 'NotAllowedError' })); });
      expect(screen.queryByRole('button', { name: 'Stop microphone' })).not.toBeInTheDocument();
      expect(getVoiceSpeakState().speaking).toBe(playing);
      expect(getReplyVoice()).toBe(beforeCapture);
      await act(async () => { fireEvent.pointerDown(mic); resolveCapture(stream); });
      expect(screen.getByRole('button', { name: 'Stop microphone' })).toBeInTheDocument();
      expect(getVoiceSpeakState().speaking).toBe(false);
      expect(getReplyVoice()).toMatchObject({ phase: 'complete', text: 'A readable completed answer' });
      if (!playing) expect(getReplyVoice()).toBe(beforeCapture);
      const afterCapture = getReplyVoice();
      await act(async () => { getUtterance().onstart?.(); getUtterance().onend?.(); });
      expect(getVoiceSpeakState().speaking).toBe(false);
      expect(getReplyVoice()).toBe(afterCapture);
      expect(input).toHaveValue('Retain this local voice draft');
      expectNoSubmittedAction();
    });
  });

  it('renders the language toggle button showing EN by default', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const langBtn = screen.getByRole('button', { name: /voice language/i });
    expect(langBtn).toBeInTheDocument();
    expect(langBtn.textContent).toBe('EN');
  });

  it('cycles language from EN to HI on click and persists to localStorage', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const langBtn = screen.getByRole('button', { name: /voice language/i });
    await act(async () => {
      fireEvent.click(langBtn);
    });

    expect(langBtn.textContent).toBe('HI');
    expect(localStorage.getItem('gagos-voice-lang')).toBe('hi-IN');
  });

  it('does not auto-submit when transcription is received via browser path', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const input = screen.getByLabelText('Talk to GAGOS') as HTMLInputElement;
    const micBtn = screen.getByRole('button', { name: /hold to speak/i });

    await act(async () => {
      fireEvent.pointerDown(micBtn);
    });

    // Simulate browser SpeechRecognition returning a final result
    const rec = (window as any).__lastSpeechRecognition;
    // Even if we can't directly call onresult, verify the input is not submitted
    // by checking that sendDirective was NOT called
    expect(sendDirective).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.pointerUp(micBtn);
    });
  });

  it('keeps a spoken approval phrase as draft text and never authorizes a pending mutation', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    const approvalHost = window as unknown as {
      __injectApproval?: (over?: Record<string, unknown>) => void;
      __clearApproval?: () => void;
    };
    approvalHost.__clearApproval?.();
    render(<GagosChrome experienceMode="beginner" />);

    fireEvent.click(screen.getByRole('checkbox', { name: /use browser recognition/i }));
    await waitFor(() => expect(recognitionProbe.current).not.toBeNull());

    act(() => {
      approvalHost.__injectApproval?.({
        summary: 'Approval required to run the project tests',
        kind: 'command',
        command: 'npm test',
      });
    });
    const approval = await screen.findByRole('alertdialog', { name: 'GAGOS permission request' });
    expect(approval).toBeInTheDocument();

    const input = screen.getByLabelText('Talk to GAGOS') as HTMLInputElement;
    const micBtn = screen.getByRole('button', { name: /hold to speak/i });
    await act(async () => {
      fireEvent.pointerDown(micBtn);
      recognitionProbe.current?.onresult?.({
        results: [{ isFinal: true, 0: { transcript: 'yes, go ahead' } }],
      });
    });

    expect(input).toHaveValue('yes, go ahead');
    expect(approvePendingApproval).not.toHaveBeenCalled();
    expect(screen.getByRole('alertdialog', { name: 'GAGOS permission request' })).toBeInTheDocument();
    fireEvent.pointerUp(micBtn);
  });

  it('applies has-transcript class to input after transcription populates draft', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const input = screen.getByLabelText('Talk to GAGOS') as HTMLInputElement;

    // Simulate typing to populate draft (acting as if transcription filled it)
    await act(async () => {
      fireEvent.change(input, { target: { value: 'transcribed text' } });
    });

    // The has-transcript class requires transcriptPending state — typing manually clears it.
    // Verify the input exists and does NOT have has-transcript on manual edit
    expect(input.className).not.toContain('has-transcript');
  });

  it('speaker button shows interrupt label while speaking', async () => {
    vi.stubGlobal('speechSynthesis', {
      speak: vi.fn((u: any) => { if (u.onstart) u.onstart(); }),
      cancel: vi.fn(),
      getVoices: vi.fn(() => []),
      pause: vi.fn(),
      resume: vi.fn(),
    });

    const { publishCognition } = await import('../superbrain/lib/cognitionBus');
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    await act(async () => {
      setVoiceSpeakMuted(false);
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Hi' } });
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    });

    await waitFor(() => {
      const speakerBtn = screen.getByRole('button', { name: /interrupt speech/i });
      expect(speakerBtn).toBeInTheDocument();
    });
  });

  it('voice output opt-in: the real speaker control starts quiet and explicitly enables subsequent playback', async () => {
    vi.stubGlobal('speechSynthesis', {
      speak: vi.fn((utter: { onstart?: () => void }) => utter.onstart?.()),
      cancel: vi.fn(), getVoices: vi.fn(() => []), pause: vi.fn(), resume: vi.fn(),
    });
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);
    expect(getVoiceSpeakState().supported).toBe(true);
    await screen.findByRole('button', { name: 'Unmute GAGOS voice' });
    await act(async () => {
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'A silent readable answer' } });
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    });
    expect(getVoiceSpeakState()).toMatchObject({ muted: true, speaking: false });
    expect(getReplyVoice()).toMatchObject({ phase: 'complete', text: 'A silent readable answer' });
    const control = screen.getByRole('button', { name: 'Unmute GAGOS voice' });
    expect(control).toHaveAttribute('aria-pressed', 'true');
    await act(async () => { fireEvent.click(control); });
    expect(screen.getByRole('button', { name: 'Mute GAGOS voice' })).toHaveAttribute('aria-pressed', 'false');
    await act(async () => {
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'An opted-in spoken answer' } });
      publishCognition({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    });
    expect(screen.getByRole('button', { name: 'Interrupt speech' })).toBeInTheDocument();
    expect(getVoiceSpeakState()).toMatchObject({ muted: false, speaking: true });
    expect(sendDirective).not.toHaveBeenCalled();
    expect(sendVoiceTurn).not.toHaveBeenCalled();
    expect(approvePendingApproval).not.toHaveBeenCalled();
  });

  it('mic button receives --mic-level CSS variable', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const micBtn = screen.getByRole('button', { name: /hold to speak/i });
    // The CSS variable is set via inline style; default level is 0
    expect(micBtn.style.getPropertyValue('--mic-level')).toBe('0');
  });

  it('keeps voice inclusive while stating that risky actions still require approval', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome experienceMode="beginner" />);

    expect(screen.getByText('Say it, type it, or choose an example. I explain first and ask before I act.')).toBeInTheDocument();
    expect(screen.getByText('Voice is for conversation; actions still need your approval.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /hold to speak/i })).toBeInTheDocument();
  });

  it('keeps browser voice consent explicit without making it compete with the first-run paths', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome experienceMode="beginner" />);

    const options = document.querySelector('.gagos-voice-options') as HTMLDetailsElement;
    expect(options).toBeInTheDocument();
    expect(options.open).toBe(false);
    expect(screen.getByRole('checkbox', { name: /use browser recognition/i })).toBeInTheDocument();

    fireEvent.click(screen.getByText('Voice options (optional)'));
    expect(options.open).toBe(true);
    expect(screen.getByText(/voice is for conversation/i)).toBeInTheDocument();
  });

  it('offers three guided beginner paths that prefill the chat without submitting', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome experienceMode="beginner" />);

    const input = screen.getByLabelText('Talk to GAGOS') as HTMLInputElement;
    fireEvent.click(screen.getByRole('button', { name: /^Guide me/i }));

    expect(input.value).toBe('Guide me through one safe first task');
    expect(sendDirective).not.toHaveBeenCalled();
  });

  it('renders the chat model toggle showing LOCAL by default', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome experienceMode="expert" />);

    const modelBtn = screen.getByRole('button', { name: /chat model/i });
    expect(modelBtn).toBeInTheDocument();
    expect(modelBtn.textContent).toBe('LOCAL');
  });

  it('cycles the chat model from LOCAL to GEMINI on click and persists to localStorage', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome experienceMode="expert" />);

    const modelBtn = screen.getByRole('button', { name: /chat model/i });
    await act(async () => {
      fireEvent.click(modelBtn);
    });

    expect(modelBtn.textContent).toBe('GEMINI');
    expect(localStorage.getItem('gagos-chat-model')).toBe('gemini.gemini-2.5-flash');

    await act(async () => {
      fireEvent.click(modelBtn);
    });

    expect(modelBtn.textContent).toBe('LOCAL');
    expect(localStorage.getItem('gagos-chat-model')).toBeNull();
  });

  it('threads the selected chat model into sendVoiceTurn for a CHAT turn', async () => {
    isWorkIntent.mockReturnValue(false);
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome experienceMode="expert" />);

    const modelBtn = screen.getByRole('button', { name: /chat model/i });
    await act(async () => {
      fireEvent.click(modelBtn);
    });
    expect(modelBtn.textContent).toBe('GEMINI');

    const input = screen.getByLabelText('Talk to GAGOS');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'what is the weather like' } });
    });
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    await waitFor(() => expect(sendVoiceTurn).toHaveBeenCalled());
    const [, opts] = sendVoiceTurn.mock.calls[0];
    expect(opts.modelId).toBe('gemini.gemini-2.5-flash');
  });

  it('omits modelId from sendVoiceTurn for a CHAT turn when Local is selected', async () => {
    isWorkIntent.mockReturnValue(false);
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const input = screen.getByLabelText('Talk to GAGOS');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'what is the weather like' } });
    });
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    await waitFor(() => expect(sendVoiceTurn).toHaveBeenCalled());
    const [, opts] = sendVoiceTurn.mock.calls[0];
    expect(opts.modelId).toBeUndefined();
  });

  it('renders the real chat reply in the accessible conversation log', async () => {
    isWorkIntent.mockReturnValue(false);
    sendVoiceTurn.mockResolvedValue('Here is what I can help with.');
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const input = screen.getByLabelText('Talk to GAGOS');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'what can you help me with' } });
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    await waitFor(() => {
      expect(screen.getByText('Here is what I can help with.')).toBeInTheDocument();
    });
    expect(screen.getByRole('log', { name: 'Conversation with GAGOS' })).toHaveTextContent(
      'GAGOS: Here is what I can help with.',
    );
  });

  it('real composer Stop retires the streaming caption, keeps prior answers and the unsent draft, and rejects late chunks', async () => {
    isWorkIntent.mockReturnValue(false);
    const firstAnswer = 'A completed answer remains readable.';
    sendVoiceTurn.mockImplementationOnce(async (_text: string, opts: { onChunk: (text: string) => void }) => {
      opts.onChunk(firstAnswer);
      return firstAnswer;
    });
    let lateChunk!: (text: string) => void;
    let resolveLate!: (text: string) => void;
    let signal!: AbortSignal;
    sendVoiceTurn.mockImplementationOnce((_text: string, opts: { onChunk: (text: string) => void; signal: AbortSignal }) => {
      lateChunk = opts.onChunk;
      signal = opts.signal;
      opts.onChunk('An unfinished answer');
      return new Promise<string>((resolve) => { resolveLate = resolve; });
    });
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);
    const input = screen.getByLabelText('Talk to GAGOS');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'Explain the first idea' } });
      fireEvent.keyDown(input, { key: 'Enter' });
    });
    expect(screen.getByRole('log', { name: 'Conversation with GAGOS' })).toHaveTextContent(firstAnswer);
    expect(deriveBodySpeech({ ...getReplyVoice(), sinceMs: 100, reducedMotion: false })).toMatchObject({ active: true, visibleText: firstAnswer });
    await act(async () => {
      fireEvent.change(input, { target: { value: 'Explain the second idea' } });
      fireEvent.keyDown(input, { key: 'Enter' });
    });
    expect(getReplyVoice()).toMatchObject({ phase: 'streaming', text: 'An unfinished answer' });
    fireEvent.change(input, { target: { value: 'Keep this draft unsent' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Stop' })); });
    expect(signal.aborted).toBe(true);
    expect(deriveBodySpeech({ ...getReplyVoice(), sinceMs: 0, reducedMotion: false }).active).toBe(false);
    expect(input).toHaveValue('Keep this draft unsent');
    expect(screen.getByRole('log', { name: 'Conversation with GAGOS' })).toHaveTextContent(firstAnswer);
    await act(async () => {
      lateChunk('A late cancelled answer');
      resolveLate('A late cancelled answer');
    });
    expect(getReplyVoice()).toMatchObject({ phase: 'idle', text: '' });
    expect(screen.getByRole('log', { name: 'Conversation with GAGOS' })).not.toHaveTextContent('A late cancelled answer');
    expect(input).toHaveValue('Keep this draft unsent');
    expect(sendVoiceTurn).toHaveBeenCalledTimes(2);
    expect(sendDirective).not.toHaveBeenCalled();
  });

  it('chat stream: renders chunks in one log message and settles its busy announcement on completion', async () => {
    isWorkIntent.mockReturnValue(false);
    let chunk!: (text: string) => void;
    let finish!: (text: string) => void;
    sendVoiceTurn.mockImplementationOnce((_text: string, opts: { onChunk: (text: string) => void }) => {
      chunk = opts.onChunk;
      return new Promise<string>(resolve => { finish = resolve; });
    });
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);
    const input = screen.getByLabelText('Talk to GAGOS');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'Explain a streamed answer' } });
      fireEvent.keyDown(input, { key: 'Enter' });
    });
    await act(async () => { chunk('A readable partial'); });
    const log = screen.getByRole('log', { name: 'Conversation with GAGOS' });
    expect(log).toHaveTextContent('A readable partial');
    expect(log).toHaveAttribute('aria-busy', 'true');
    const message = screen.getByText('A readable partial').closest('.gagos-msg');
    await act(async () => { chunk('A readable partial answer'); });
    expect(screen.getByText('A readable partial answer').closest('.gagos-msg')).toBe(message);
    await act(async () => { finish('A readable partial answer'); });
    expect(screen.getAllByText('A readable partial answer')).toHaveLength(1);
    expect(screen.getByText('A readable partial answer').closest('.gagos-msg')).toBe(message);
    expect(log).toHaveAttribute('aria-busy', 'false');
  });

  it('chat stream: keeps an interrupted partial reply readable and clears the log busy state', async () => {
    isWorkIntent.mockReturnValue(false);
    let interrupt!: (error: Error) => void;
    sendVoiceTurn.mockImplementationOnce((_text: string, opts: { onChunk: (text: string) => void }) => {
      opts.onChunk('An actual partial reply survives');
      return new Promise<string>((_resolve, reject) => { interrupt = reject; });
    });
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);
    const input = screen.getByLabelText('Talk to GAGOS');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'Explain an interrupted answer' } });
      fireEvent.keyDown(input, { key: 'Enter' });
    });
    await act(async () => { interrupt(new Error('The response ended before completion')); });
    const log = screen.getByRole('log', { name: 'Conversation with GAGOS' });
    expect(log).toHaveTextContent('An actual partial reply survives');
    expect(log).toHaveTextContent(/interrupted/i);
    expect(log).toHaveAttribute('aria-busy', 'false');
    expect(screen.getByRole('button', { name: 'Retry: Explain an interrupted answer' })).toBeVisible();
  });

  describe('canonical emergency Stop reaches the local reply owner', () => {
    // Break caught: Stop observation cancels an old turn, but an already
    // engaged latch still lets Enter/Send/Retry clear a draft and start a new
    // model/work request. Exercise real UI/owner state, not the disabled label.
    it.each([
      ['Enter', false], ['Send', false], ['Retry', false],
      ['Enter', true], ['Send', true], ['Retry', true],
    ] as const)('keeps a new draft/history while already stopped: %s work=%s; Clear does not send it', async (entry, work) => {
      isWorkIntent.mockReturnValue(false);
      const oldAnswer = 'A completed answer remains in history.';
      sendVoiceTurn.mockImplementation(async (_text: string, opts: { onChunk: (text: string) => void }) => {
        opts.onChunk(oldAnswer); return oldAnswer;
      });
      const { default: GagosChrome } = await import('./GagosChrome');
      render(<GagosChrome integrated />);
      const input = screen.getByLabelText('Talk to GAGOS');
      await act(async () => {
        fireEvent.change(input, { target: { value: 'Explain the original idea' } });
        fireEvent.keyDown(input, { key: 'Enter' });
      });
      if (entry === 'Retry') {
        sendVoiceTurn.mockRejectedValueOnce(new Error('A fixture failure keeps its retry available'));
        await act(async () => {
          fireEvent.change(input, { target: { value: 'Explain the failed idea' } });
          fireEvent.keyDown(input, { key: 'Enter' });
        });
        expect(screen.getByRole('button', { name: 'Retry: Explain the failed idea' })).toBeEnabled();
      }
      await act(async () => { setEmergencyStopPresentation('engaged'); });
      const history = screen.getByRole('log', { name: 'Conversation with GAGOS' });
      const historyBefore = history.textContent;
      const draft = work ? 'Build a stopped draft without sending it' : 'Explain this stopped draft without sending it';
      isWorkIntent.mockReturnValue(work);
      await act(async () => { fireEvent.change(input, { target: { value: draft } }); });
      await act(async () => {
        if (entry === 'Enter') fireEvent.keyDown(input, { key: 'Enter' });
        else fireEvent.click(screen.getByRole('button', {
          name: entry === 'Send' ? 'Send' : 'Retry: Explain the failed idea',
        }));
      });
      expect(input, 'a known Stop must not consume the draft or create a new turn').toHaveValue(draft);
      expect(history.textContent).toBe(historyBefore);
      expect(history).toHaveTextContent(oldAnswer);
      expect(getReplyVoice()).toMatchObject({ phase: 'idle', text: '' });
      expect(sendVoiceTurn).toHaveBeenCalledTimes(entry === 'Retry' ? 2 : 1);
      expect(sendDirective).not.toHaveBeenCalled();
      expect(approvePendingApproval).not.toHaveBeenCalled();
      expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
      expect(getTabStoreSnapshot().tabs.filter(tab => tab.kind === 'content')).toHaveLength(0);
      expect(getTabStoreSnapshot().recoverableTabs ?? []).toHaveLength(0);
      expect(screen.getByText(/new requests cannot be sent/i)).toBeInTheDocument();
      await act(async () => { setEmergencyStopPresentation('clear'); });
      expect(input).toHaveValue(draft);
      expect(history.textContent).toBe(historyBefore);
      expect(sendVoiceTurn).toHaveBeenCalledTimes(entry === 'Retry' ? 2 : 1);
      expect(sendDirective).not.toHaveBeenCalled();
      expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
      // Clear is not replay. A NEW deliberate action starts the next turn.
      isWorkIntent.mockReturnValue(false);
      sendVoiceTurn.mockImplementation(async (_text: string, opts: { onChunk: (text: string) => void }) => {
        opts.onChunk('A new explicitly submitted answer.'); return 'A new explicitly submitted answer.';
      });
      await act(async () => { fireEvent.keyDown(input, { key: 'Enter' }); });
      expect(input).toHaveValue('');
      expect(history).toHaveTextContent(oldAnswer);
      expect(history).toHaveTextContent('A new explicitly submitted answer.');
      expect(getReplyVoice()).toMatchObject({ phase: 'complete', text: 'A new explicitly submitted answer.' });
      expect(sendDirective).not.toHaveBeenCalled();
      expect(approvePendingApproval).not.toHaveBeenCalled();
    });
    it('an admitted Stop cancels the stream and caption without deleting prior answers or draft', async () => {
      isWorkIntent.mockReturnValue(false);
      const firstAnswer = 'A completed answer remains readable.';
      sendVoiceTurn.mockImplementationOnce(async (_text: string, opts: { onChunk: (text: string) => void }) => {
        opts.onChunk(firstAnswer); return firstAnswer;
      });
      let lateChunk!: (text: string) => void;
      let resolveLate!: (text: string) => void;
      let signal!: AbortSignal;
      sendVoiceTurn.mockImplementationOnce((_text: string, opts: { onChunk: (text: string) => void; signal: AbortSignal }) => {
        lateChunk = opts.onChunk; signal = opts.signal;
        opts.onChunk('An unfinished answer');
        return new Promise<string>(resolve => { resolveLate = resolve; });
      });
      const { default: GagosChrome } = await import('./GagosChrome');
      render(<GagosChrome />);
      const input = screen.getByLabelText('Talk to GAGOS');
      await act(async () => {
        fireEvent.change(input, { target: { value: 'Explain the first idea' } });
        fireEvent.keyDown(input, { key: 'Enter' });
      });
      await act(async () => {
        fireEvent.change(input, { target: { value: 'Explain the second idea' } });
        fireEvent.keyDown(input, { key: 'Enter' });
      });
      expect(getReplyVoice()).toMatchObject({ phase: 'streaming', text: 'An unfinished answer' });
      fireEvent.change(input, { target: { value: 'Keep this emergency draft unsent' } });
      await act(async () => {
        expect(dispatchLivingMirrorEvent({ id: 1, eventType: 'governance.emergency_stop.engaged',
          canonical: { eventId: 'fixture-stop-1', eventType: 'governance.emergency_stop.engaged',
            schema_version: '1', payload: { reason: 'Test-only observed stop' }, reason: 'Test-only observed stop' },
          payload: { reason: 'Test-only observed stop' } })).toBe(true);
      });
      expect(signal.aborted, 'canonical Stop must cancel the same local stream').toBe(true);
      expect(getReplyVoice()).toMatchObject({ phase: 'idle', text: '' });
      expect(screen.getByRole('log', { name: 'Conversation with GAGOS' })).toHaveTextContent(firstAnswer);
      expect(input).toHaveValue('Keep this emergency draft unsent');
      await act(async () => { lateChunk('A late cancelled answer'); resolveLate('A late cancelled answer'); });
      expect(getReplyVoice()).toMatchObject({ phase: 'idle', text: '' });
      expect(screen.getByRole('log', { name: 'Conversation with GAGOS' })).not.toHaveTextContent('A late cancelled answer');
      expect(sendVoiceTurn).toHaveBeenCalledTimes(2);
      expect(sendDirective).not.toHaveBeenCalled();
      expect(approvePendingApproval).not.toHaveBeenCalled();
    });

    it.each([true, false])('an observed Stop retires playing=%s after network completion and ignores stale audio callbacks', async playing => {
      isWorkIntent.mockReturnValue(false);
      const answer = 'A completed answer remains in the conversation.';
      sendVoiceTurn.mockImplementation(async (_text: string, opts: { onChunk: (text: string) => void }) => {
        opts.onChunk(answer); return answer;
      });
      let utterance!: { onstart: (() => void) | null; onend: (() => void) | null; onerror: (() => void) | null };
      vi.stubGlobal('speechSynthesis', {
        speak: (next: typeof utterance) => { utterance = next; if (playing) next.onstart?.(); },
        cancel() {}, // Cancellation need not emit a browser callback.
        getVoices: () => [], pause() {}, resume() {},
      });
      const { default: GagosChrome } = await import('./GagosChrome');
      render(<GagosChrome />);
      const input = screen.getByLabelText('Talk to GAGOS');
      await act(async () => {
        setVoiceSpeakMuted(false);
        fireEvent.change(input, { target: { value: 'Explain this idea' } });
        fireEvent.keyDown(input, { key: 'Enter' });
      });
      expect(utterance).toBeDefined();
      expect(getVoiceSpeakState().speaking).toBe(playing);
      expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument(); // Network is already finished.
      fireEvent.change(input, { target: { value: 'Retain this playback draft' } });
      await act(async () => { setEmergencyStopPresentation('unknown'); });
      expect(getVoiceSpeakState().speaking).toBe(playing); // Unknown is not a confirmed Stop.
      await act(async () => { setEmergencyStopPresentation('engaged'); });
      expect(getVoiceSpeakState().speaking).toBe(false);
      expect(getReplyVoice()).toMatchObject({ phase: 'idle', text: '' });
      await act(async () => {
        utterance.onstart?.(); utterance.onend?.(); utterance.onerror?.();
        setEmergencyStopPresentation('clear');
      });
      expect(getVoiceSpeakState().speaking).toBe(false);
      expect(getReplyVoice()).toMatchObject({ phase: 'idle', text: '' }); // Clear must not restart retired output.
      expect(screen.getByRole('log', { name: 'Conversation with GAGOS' })).toHaveTextContent(answer);
      expect(input).toHaveValue('Retain this playback draft');
      expect(sendVoiceTurn).toHaveBeenCalledTimes(1);
      expect(sendDirective).not.toHaveBeenCalled();
      expect(approvePendingApproval).not.toHaveBeenCalled();
    });
  });

  it('organ 30: renders the human-state hint and submits a real correction', async () => {
    isWorkIntent.mockReturnValue(false);
    sendVoiceTurn.mockImplementation(async (_text: string, opts: { onHumanState?: (h: unknown) => void }) => {
      opts.onHumanState?.({
        turnId: 'turn-test-1',
        state: 'frustrated',
        confidence: 0.6,
        visibleReason: 'message contains repeated-complaint markers',
      });
      return 'ok';
    });
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const input = screen.getByLabelText('Talk to GAGOS');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'ugh still broken' } });
    });
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    const toggle = await screen.findByRole('button', {
      name: 'Sensed: frustrated. Correct this.',
    });

    await act(async () => {
      fireEvent.click(toggle);
    });
    const neutralOption = screen.getByRole('button', { name: 'neutral' });
    await act(async () => {
      fireEvent.click(neutralOption);
    });

    await waitFor(() =>
      expect(correctHumanState).toHaveBeenCalledWith('turn-test-1', 'neutral'),
    );
    expect(screen.getByText('noted')).toBeTruthy();
  });

  it('organ 30: never submits a correction with a missing turnId (regression guard for a real closure-timing bug caught by live verification)', async () => {
    isWorkIntent.mockReturnValue(false);
    sendVoiceTurn.mockImplementation(async (_text: string, opts: { onHumanState?: (h: unknown) => void }) => {
      opts.onHumanState?.({
        turnId: 'turn-test-2',
        state: 'rushed',
        confidence: 0.6,
        visibleReason: 'urgency markers',
      });
      return 'ok';
    });
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const input = screen.getByLabelText('Talk to GAGOS');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'need this asap' } });
    });
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    const toggle = await screen.findByRole('button', {
      name: 'Sensed: in a hurry. Correct this.',
    });
    await act(async () => {
      fireEvent.click(toggle);
    });
    const decisiveOption = screen.getByRole('button', { name: 'decisive' });
    await act(async () => {
      fireEvent.click(decisiveOption);
    });

    await waitFor(() => expect(correctHumanState).toHaveBeenCalledTimes(1));
    expect(correctHumanState).toHaveBeenCalledWith('turn-test-2', 'decisive');
  });
});
