import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { act } from 'react';
import { __resetTabStoreForTests } from '../superbrain/lib/tabStore';

vi.mock('../superbrain/SuperbrainApp', () => ({
  default: () => <div data-testid="mock-being">being</div>,
}));

// Force the work path so the directive branch runs deterministically.
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

describe('GagosChrome — backend redaction tokens render as chips, never raw', () => {
  beforeEach(() => {
    __resetTabStoreForTests();
    sendDirective.mockClear();
    getLastEmittedCode.mockReset().mockReturnValue(null);
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((q: string) => ({
        matches: false,
        media: q,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  it('replaces a [SENSITIVE: <hash>] token with a legible redaction chip', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    const { container } = render(<GagosChrome />);

    const input = screen.getByLabelText('Talk to GAGOS');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'save the token file for me' } });
    });
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    // The turn resolves conversationally (no code) with a backend-redacted
    // filename in the reply — the raw token must never reach the DOM as text.
    await act(async () => {
      resolveDirective({
        paused: false,
        answer: 'Saved training_ground/test_[SENSITIVE: dd53bbede2b1].py for you.',
      });
    });

    expect(container.textContent).not.toContain('[SENSITIVE');
    expect(container.textContent).not.toContain('dd53bbede2b1');
    const chips = container.querySelectorAll('.gagos-redaction');
    expect(chips.length).toBe(1);
    expect(chips[0].textContent).toBe('restricted');
    // The surrounding message text still renders around the chip.
    expect(container.textContent).toContain('Saved training_ground/test_');
    expect(container.textContent).toContain('.py for you.');
  });

  it('leaves ordinary bracketed text untouched', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    const { container } = render(<GagosChrome />);

    const input = screen.getByLabelText('Talk to GAGOS');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'explain the plan' } });
    });
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });
    await act(async () => {
      resolveDirective({ paused: false, answer: 'Step [1 of 2]: read the file list.' });
    });

    expect(container.textContent).toContain('Step [1 of 2]: read the file list.');
    expect(container.querySelectorAll('.gagos-redaction').length).toBe(0);
  });
});
