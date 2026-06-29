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
let lastOnChunk: ((answer: string) => void) | undefined;
const sendDirective = vi.fn(
  (_text: string, _signal?: AbortSignal, onChunk?: (answer: string) => void) => {
    lastOnChunk = onChunk;
    return new Promise((res) => {
      resolveDirective = res as (r: unknown) => void;
    });
  },
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

  it('grows the slab live as the answer streams (Slice 2 / A)', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const input = screen.getByLabelText('Talk to GAGOS');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'create count.py that counts to three' } });
    });
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });
    await waitFor(() => expect(lastOnChunk).toBeTypeOf('function'));

    // A code fence opens and grows token-by-token in the streaming answer.
    await act(async () => {
      lastOnChunk?.('Sure, here it is:\n```python\nfor i in range(1');
    });
    await waitFor(() => {
      const tab = getTabStoreSnapshot().tabs.find((t) => t.kind === 'content');
      expect(tab?.content?.streaming).toBe(true);
      expect(tab?.content?.code).toContain('for i in range(1');
    });

    // More tokens arrive — the SAME slab keeps growing.
    await act(async () => {
      lastOnChunk?.('Sure, here it is:\n```python\nfor i in range(1, 4):\n    print(i)\n```');
    });
    await waitFor(() => {
      const tab = getTabStoreSnapshot().tabs.find((t) => t.kind === 'content');
      expect(tab?.content?.code).toContain('print(i)');
    });

    // The turn settles — one slab, streaming off.
    getLastEmittedCode.mockReturnValue({ code: 'for i in range(1, 4):\n    print(i)', language: 'python', filepath: 'count.py' });
    await act(async () => {
      resolveDirective({ ok: true, paused: false, answer: '```python\nfor i in range(1, 4):\n    print(i)\n```' });
    });
    await waitFor(() => {
      const tabs = getTabStoreSnapshot().tabs.filter((t) => t.kind === 'content');
      expect(tabs.length).toBe(1);
      expect(tabs[0].content?.streaming).toBe(false);
    });
  });

  it('folds a re-edit into the existing slab when the real filename matches (#3)', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    const { showContentSurface, getTabStoreSnapshot: snap } = await import('../superbrain/lib/tabStore');
    render(<GagosChrome />);

    act(() => {
      showContentSurface({ code: 'print("old")', language: 'python', filepath: 'greet.py' });
    });

    const input = screen.getByLabelText('Talk to GAGOS');
    // directive whose filename GUESS differs from the real emitted file
    await act(async () => {
      fireEvent.change(input, { target: { value: 'update the greeting message' } });
    });
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });
    await waitFor(() => expect(lastOnChunk).toBeTypeOf('function'));

    getLastEmittedCode.mockReturnValue({ code: 'print("new")', language: 'python', filepath: 'greet.py' });
    await act(async () => {
      resolveDirective({ ok: true, paused: false, answer: '' });
    });

    // The re-edit folds into the existing greet.py slab — one greet.py, updated.
    await waitFor(() => {
      const greets = snap().tabs.filter(
        (t) =>
          t.kind === 'content' &&
          t.lifecycle !== 'retracting' &&
          t.content?.filepath?.split(/[\\/]/).pop() === 'greet.py',
      );
      expect(greets.length).toBe(1);
      expect(greets[0].content?.code).toContain('new');
    });
  });

  it('attaches the verify result to the matching slab (preview)', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    const { showContentSurface, getTabStoreSnapshot: snap } = await import('../superbrain/lib/tabStore');
    const { publishCognition } = await import('../superbrain/lib/cognitionBus');
    render(<GagosChrome />);

    act(() => {
      showContentSurface({ code: 'print("hi")', language: 'python', filepath: 'greet.py' });
    });
    // A verify result arrives on the bus (target carries a dir; match by basename).
    act(() => {
      publishCognition({
        type: 'verify',
        label: 'VERIFY PASS',
        detail: 'greet.py',
        intensity: 0.75,
        source: 'aios',
        data: { verdict: 'pass', target: 'training_ground/greet.py', output: 'hi\n' },
      });
    });

    await waitFor(() => {
      const tab = snap().tabs.find((t) => t.content?.filepath === 'greet.py');
      expect(tab?.content?.verifyVerdict).toBe('pass');
      expect(tab?.content?.verifyOutput).toContain('hi');
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

describe('workFilepath', () => {
  it('prefers an explicit filename, then an identifier, dropping filler words', async () => {
    const { workFilepath } = await import('./GagosChrome');
    // explicit filename in the directive wins
    expect(workFilepath('create hello.py that prints hi')).toBe('hello.py');
    expect(workFilepath('Create a Python file streamtest.py that prints x')).toBe('streamtest.py');
    // a function/identifier name + inferred language
    expect(workFilepath('Write a Python function bubble_sort with inline comments')).toBe('bubble-sort.py');
    // no longer the old ugly "a-python-function-…" filler guess
    expect(workFilepath('Write a Python function bubble_sort with inline comments')).not.toContain('a-python');
    // graceful fallback when there is nothing clean
    expect(workFilepath('do the thing')).toMatch(/\.\w+$/);
  });
});

describe('extractStreamingCode', () => {
  it('returns no code until a fence opens, then the code-so-far (open or closed)', async () => {
    const { extractStreamingCode } = await import('./GagosChrome');
    // Before any fence: nothing to show.
    expect(extractStreamingCode('thinking about it...').code).toBe('');
    // Open (unclosed) fence: everything after it, live.
    const open = extractStreamingCode('here:\n```py\nprint(1)');
    expect(open.code).toContain('print(1)');
    expect(open.language).toBe('py');
    // Closed fence: just the block, trailing prose dropped.
    const closed = extractStreamingCode('```python\nprint(1)\n```\nDone!');
    expect(closed.code).toBe('print(1)\n');
    expect(closed.language).toBe('python');
  });
});
