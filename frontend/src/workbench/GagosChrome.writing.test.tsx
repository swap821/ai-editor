import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { act } from 'react';
import { getTabStoreSnapshot, __resetTabStoreForTests } from '../superbrain/lib/tabStore';

vi.mock('../superbrain/SuperbrainApp', () => ({
  default: () => <div data-testid="mock-being">being</div>,
}));

// Force the work path so the materialization runs deterministically.
vi.mock('../superbrain/lib/intentRouting', async () => {
  const actual = await vi.importActual<typeof import('../superbrain/lib/intentRouting')>(
    '../superbrain/lib/intentRouting',
  );
  return { ...actual, isWorkIntent: () => true };
});

let resolveDirective: (r: unknown) => void = () => {};
const sendDirective = vi.fn(
  () =>
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

describe('GagosChrome — live writing slab', () => {
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

  it('materializes a "writing" slab on send, then fills the SAME slab with the code', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const input = screen.getByLabelText('Talk to GAGOS');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'create hello.py that prints hi' } });
    });
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    // In flight: a content slab exists on the spine in the streaming "writing" state.
    await waitFor(() => {
      const tab = getTabStoreSnapshot().tabs.find((t) => t.kind === 'content');
      expect(tab?.content?.streaming).toBe(true);
    });

    // The turn finishes and the being emits the file.
    getLastEmittedCode.mockReturnValue({ code: 'print("hi")', language: 'python', filepath: 'hello.py' });
    await act(async () => {
      resolveDirective({ ok: true, paused: false, answer: '' });
    });

    // The SAME slab fills (streaming off, code present) — exactly one content slab.
    await waitFor(() => {
      const tabs = getTabStoreSnapshot().tabs.filter((t) => t.kind === 'content');
      expect(tabs.length).toBe(1);
      expect(tabs[0].content?.streaming).toBe(false);
      expect(tabs[0].content?.code).toContain('print("hi")');
    });
  });

  it('retracts the writing slab if the turn produces no code (conversation)', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const input = screen.getByLabelText('Talk to GAGOS');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'what files are here?' } });
    });
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });
    await waitFor(() => {
      expect(getTabStoreSnapshot().tabs.find((t) => t.kind === 'content')?.content?.streaming).toBe(true);
    });

    // No code emitted — the being just talks.
    await act(async () => {
      resolveDirective({ ok: true, paused: false, answer: 'There are a few files.' });
    });

    // The premature writing slab is retracting (not left as an empty "writing…").
    await waitFor(() => {
      const tab = getTabStoreSnapshot().tabs.find((t) => t.kind === 'content');
      expect(tab?.lifecycle).toBe('retracting');
    });
  });
});
