import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import { act } from 'react';
import { publishCognition } from '../superbrain/lib/cognitionBus';
import { __resetActiveBrainForTests } from '../superbrain/lib/activeBrain';
import { __resetTabStoreForTests } from '../superbrain/lib/tabStore';

vi.mock('../superbrain/SuperbrainApp', () => ({
  default: () => <div data-testid="mock-being">being</div>,
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
  beforeEach(() => {
    __resetActiveBrainForTests();
    __resetTabStoreForTests();
    sendDirective.mockClear();
    getLastEmittedCode.mockReset().mockReturnValue(null);
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

  it('renders model and provider as hierarchical state-chip text', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

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
    render(<GagosChrome />);

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
});
