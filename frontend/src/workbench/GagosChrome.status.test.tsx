import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import { act } from 'react';
import { publishCognition } from '../superbrain/lib/cognitionBus';
import { __resetActiveBrainForTests } from '../superbrain/lib/activeBrain';
import { __resetTabStoreForTests } from '../superbrain/lib/tabStore';
import { __resetConversationPhaseForTests, setConversationPhase } from '../superbrain/lib/conversationPhaseBus';

vi.mock('../superbrain/SuperbrainApp', () => ({
  default: () => <div data-testid="mock-being">being</div>,
}));

vi.mock('../livingMirror/being/useBeingPresentation', () => ({
  useBeingPresentation: () => ({
    phase: 'awaiting-human',
    taskState: 'needs-permission',
    coherence: 'fresh',
    motion: 'attention',
    attention: 'approval',
    signals: [],
    workers: [],
  }),
}));

vi.mock('../superbrain/lib/intentRouting', async () => {
  const actual = await vi.importActual<typeof import('../superbrain/lib/intentRouting')>(
    '../superbrain/lib/intentRouting',
  );
  return { ...actual, isWorkIntent: () => true };
});

let resolveDirective: (r: unknown) => void = () => {};
const sendDirective = vi.fn(
  (_text: string, _signal?: AbortSignal) =>
    new Promise((res) => {
      resolveDirective = res as (r: unknown) => void;
    }),
);
const getLastEmittedCode = vi.fn<() => unknown>(() => null);
const previewIntent = vi.fn().mockResolvedValue({ intent: 'code', confidence: 0.9, tool: 'create_file' });
const fetchOnboardingState = vi.fn().mockResolvedValue({
  firstDirective: true,
  firstApproval: true,
  firstVerify: true,
  firstCloudRoute: true,
  firstAutonomy: true,
});

vi.mock('../superbrain/lib/aiosAdapter', async () => {
  const actual = await vi.importActual<typeof import('../superbrain/lib/aiosAdapter')>(
    '../superbrain/lib/aiosAdapter',
  );
  return { ...actual, sendDirective, getLastEmittedCode, previewIntent, fetchOnboardingState };
});

describe('GagosChrome W3 status chrome', () => {
  afterEach(() => {
    window.localStorage.removeItem('gagos-pause-motion-v1');
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    __resetActiveBrainForTests();
    __resetTabStoreForTests();
    __resetConversationPhaseForTests();
    sendDirective.mockClear();
    getLastEmittedCode.mockReset().mockReturnValue(null);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }));
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
  });

  it('does not present the health link as connected before /health is measured', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    expect(within(screen.getByLabelText('GAGOS status')).getByText('checking…')).toBeInTheDocument();
  });

  it('announces the measured organism phase in human language', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    expect(screen.getByRole('status', { name: 'GAGOS organism status' })).toHaveTextContent(
      'GAGOS is waiting for your decision.',
    );
  });

  it('projects the shared motion pause onto the DOM shell without hiding controls', async () => {
    window.localStorage.setItem('gagos-pause-motion-v1', 'true');
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const chrome = screen.getByLabelText('GAGOS conversation');
    expect(chrome).toHaveAttribute('data-motion-reduced', 'true');
    expect(screen.getByLabelText('Talk to GAGOS')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Skip to the chat' })).toBeInTheDocument();
  });

  it('moves keyboard users from the skip control to the primary conversation input', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const skip = screen.getByRole('button', { name: 'Skip to the chat' });
    const input = screen.getByLabelText('Talk to GAGOS');
    skip.focus();

    await act(async () => {
      fireEvent.keyDown(skip, { key: 'Enter', code: 'Enter' });
      fireEvent.click(skip);
    });

    expect(document.activeElement).toBe(input);
  });

  it('describes a measured health response as reachable rather than current', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    await waitFor(() => {
      expect(within(screen.getByLabelText('GAGOS status')).getByText('reachable')).toBeInTheDocument();
    });
  });

  it('renders model and provider as hierarchical state-chip text', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome experienceMode="expert" />);

    act(() => {
      publishCognition({
        type: 'route',
        label: 'ROUTE',
        detail: 'ollama:qwen2.5-coder:32b',
        intensity: 0.5,
        source: 'aios',
        data: { provider: 'ollama', model: 'qwen2.5-coder:32b', privacy: 'local' },
      });
    });

    const status = screen.getByLabelText('GAGOS status');
    await waitFor(() => {
      expect(within(status).getByText('qwen2.5-coder:32b')).toHaveClass('gagos-pill__main');
    });
    expect(within(status).getByText('ollama · local')).toHaveClass('gagos-pill__meta');
    expect(status.querySelector('.gagos-pill--model')).toBeTruthy();
    expect(status.querySelector('.gagos-pill--supervised')).toBeTruthy();
  });

  it('renders a mode badge when the route event carries a TurnCoordinator mode', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome experienceMode="expert" />);

    act(() => {
      publishCognition({
        type: 'route',
        label: 'ROUTE',
        detail: 'ollama:qwen2.5-coder:32b',
        intensity: 0.5,
        source: 'aios',
        data: {
          provider: 'ollama',
          model: 'qwen2.5-coder:32b',
          privacy: 'local',
          turn_id: 'turn-7a9f-44d2',
          mode: 'mission',
        },
      });
    });

    const status = screen.getByLabelText('GAGOS status');
    await waitFor(() => {
      expect(within(status).getByText('mission')).toHaveClass('gagos-pill__main');
    });
    expect(status.querySelector('.gagos-pill--mode')).toBeTruthy();
    expect(status.querySelector('.gagos-pill--mode-mission')).toBeTruthy();
  });

  it('shows a visible calm thinking echo above the dock while a turn is pending', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    const { container } = render(<GagosChrome />);

    const input = screen.getByLabelText('Talk to GAGOS');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'think before answering' } });
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    const echo = await screen.findByText('thinking…');
    expect(echo.closest('.gagos-thinking-echo')).toBeTruthy();
    expect(container.querySelector('.gagos-thinking-echo .gagos-typing')).toBeTruthy();

    await act(async () => {
      resolveDirective({ paused: false, answer: 'Done.' });
    });
  });

  it('labels an in-flight streamed reply as replying rather than thinking', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const input = screen.getByLabelText('Talk to GAGOS');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'write a small file' } });
      fireEvent.keyDown(input, { key: 'Enter' });
      setConversationPhase('streaming');
    });

    expect(await screen.findByText('replying…')).toBeInTheDocument();
    expect(screen.queryByText('thinking…')).not.toBeInTheDocument();

    await act(async () => {
      resolveDirective({ paused: false, answer: 'Done.' });
    });
  });

  it('does not simulate model thinking when the cognition bus reports a reflex replay', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome experienceMode="expert" />);

    const input = screen.getByLabelText('Talk to GAGOS');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'reuse the verified routine' } });
      fireEvent.keyDown(input, { key: 'Enter' });
      publishCognition({ type: 'reflex-recall', source: 'cerebellum', detail: 'verified routine replay' });
    });

    expect(screen.queryByText('thinking…')).not.toBeInTheDocument();
    expect(screen.getByText('Used a verified routine. No model call.')).toBeInTheDocument();

    await act(async () => {
      resolveDirective({ paused: false, answer: 'Done.' });
    });
  });

  it('does not expose the internal forge hint in Guided mode', async () => {
    window.localStorage.setItem('gagos-onboarded', '1');
    window.localStorage.removeItem('gagos-onboarding-hint-dismissed');
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    await waitFor(() => {
      expect(screen.queryByText(/ORGANS · forge/i)).not.toBeInTheDocument();
    });
    window.localStorage.removeItem('gagos-onboarded');
    window.localStorage.removeItem('gagos-onboarding-hint-dismissed');
  });

  it('keeps the full Guided conversation shell free of internal architecture terms', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome experienceMode="beginner" />);

    await waitFor(() => expect(screen.getByLabelText('GAGOS conversation')).toBeInTheDocument());
    const guidedText = screen.getByLabelText('GAGOS conversation').textContent ?? '';
    expect(guidedText).not.toMatch(
      /\b(governance|stigmergy|council|workforce|hiring|vulture|ecosystem|terminal|provider|model|worker|organ|capability|policy|swarm|sovereign)\b/i,
    );
  });

  it('keeps Guided account status human-readable while preserving the Expert ceremony', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    const { rerender } = render(<GagosChrome />);

    fireEvent.click(screen.getByRole('button', { name: /account identity status/i }));
    expect(screen.getByRole('dialog', { name: 'Account status unavailable' })).toBeInTheDocument();
    expect(screen.queryByText(/sovereign bond|claim sovereignty|human sovereign/i)).not.toBeInTheDocument();

    rerender(<GagosChrome experienceMode="expert" />);
    expect(await screen.findByRole('dialog', { name: 'Sovereign bond' })).toBeInTheDocument();
  });
});
