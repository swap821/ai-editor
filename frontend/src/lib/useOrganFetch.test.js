import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useOrganFetch } from './useOrganFetch';
import { publishCognition } from '../superbrain/lib/cognitionBus';

/* useOrganFetch — the reusable honest-state organ fetch hook. These pin the five
   truth-states (loading → ready / empty / offline / error) plus the cold-offline
   timeout, bus-driven re-fetch, keep-last, and unmount cleanup. fetch is stubbed
   globally; nothing here touches the real backend. */

function okJson(body) {
  return { ok: true, status: 200, json: async () => body };
}
function status(code, body = {}) {
  return { ok: code < 400, status: code, json: async () => body };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('useOrganFetch — truth-state transitions', () => {
  it('loading → ready: a successful non-empty fetch lands on ready with mapped data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okJson({ items: [1, 2, 3] })));
    const { result } = renderHook(() =>
      useOrganFetch('/x', { onData: (j) => j.items }),
    );
    // Initial synchronous render is the honest loading state.
    expect(result.current.phase).toBe('loading');
    await waitFor(() => expect(result.current.phase).toBe('ready'));
    expect(result.current.data).toEqual([1, 2, 3]);
    expect(result.current.hadData).toBe(true);
    expect(result.current.isError).toBe(false);
  });

  it("ready + empty: response.ok but onData returns a zero-length array → 'empty' (not offline)", async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okJson({ items: [] })));
    const { result } = renderHook(() =>
      useOrganFetch('/x', { onData: (j) => j.items }),
    );
    await waitFor(() => expect(result.current.phase).toBe('empty'));
    // EMPTY is a SUCCESSFUL fetch — hadData is true, and it is NOT an error/offline.
    expect(result.current.hadData).toBe(true);
    expect(result.current.isError).toBe(false);
  });

  it("empty: onData returning null (no frame) → 'empty', distinct from offline", async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okJson({ alignment: null })));
    const { result } = renderHook(() =>
      useOrganFetch('/x', { onData: (j) => j.alignment ?? null }),
    );
    await waitFor(() => expect(result.current.phase).toBe('empty'));
    expect(result.current.data).toBeNull();
    expect(result.current.hadData).toBe(true);
  });

  it("offline: a network throw on first load → 'offline' with hadData=false (placeholder, not loading-forever)", async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    const { result } = renderHook(() => useOrganFetch('/x', { onData: (j) => j }));
    await waitFor(() => expect(result.current.phase).toBe('offline'));
    expect(result.current.hadData).toBe(false);
    expect(result.current.isError).toBe(false);
  });

  it("error: response.status >= 500 → 'error' with the status code in the message", async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(status(503)));
    const { result } = renderHook(() => useOrganFetch('/x', { onData: (j) => j }));
    await waitFor(() => expect(result.current.phase).toBe('error'));
    expect(result.current.isError).toBe(true);
    expect(result.current.error?.message).toContain('503');
  });

  it("error: malformed JSON on an ok response → 'error' (not empty, not ready)", async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => { throw new SyntaxError('Unexpected token'); },
    }));
    const { result } = renderHook(() => useOrganFetch('/x', { onData: (j) => j }));
    await waitFor(() => expect(result.current.phase).toBe('error'));
    expect(result.current.isError).toBe(true);
  });

  it("offline: a non-5xx not-ok response (e.g. 404) → 'offline', not 'error'", async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(status(404)));
    const { result } = renderHook(() => useOrganFetch('/x', { onData: (j) => j }));
    await waitFor(() => expect(result.current.phase).toBe('offline'));
    expect(result.current.isError).toBe(false);
  });
});

describe('useOrganFetch — cold-offline timeout (W2-5)', () => {
  it("aborts after the timeout and reports 'offline' on a hung fetch", async () => {
    vi.useFakeTimers();
    // A fetch that rejects with AbortError when its signal fires (jsdom has no
    // native abort wiring on a stub), so we simulate the abort the hook triggers.
    vi.stubGlobal('fetch', vi.fn((url, init) => new Promise((_resolve, reject) => {
      init.signal.addEventListener('abort', () => {
        const e = new Error('aborted');
        e.name = 'AbortError';
        reject(e);
      });
    })));
    const { result } = renderHook(() =>
      useOrganFetch('/x', { onData: (j) => j, timeoutMs: 4000 }),
    );
    expect(result.current.phase).toBe('loading');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4001);
    });
    expect(result.current.phase).toBe('offline');
    expect(result.current.hadData).toBe(false);
  });
});

describe('useOrganFetch — bus-driven re-fetch + keep-last', () => {
  it('re-fetches when a matching cognition-bus event fires (type/label matcher)', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(okJson({ items: [1] }))
      .mockResolvedValueOnce(okJson({ items: [1, 2] }));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() =>
      useOrganFetch('/x', {
        events: ['synthesis/SYNTHESIS COMPLETE'],
        onData: (j) => j.items,
      }),
    );
    // Let the mount fetch settle.
    await waitFor(() => expect(result.current.data).toEqual([1]));

    // A NON-matching event must NOT trigger a re-fetch (wait past the debounce).
    act(() => { publishCognition({ type: 'telemetry', label: 'PING' }); });
    await new Promise((r) => setTimeout(r, 600));
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // The matching event fires → debounced re-fetch → fresh data.
    act(() => { publishCognition({ type: 'synthesis', label: 'SYNTHESIS COMPLETE' }); });
    await waitFor(() => expect(result.current.data).toEqual([1, 2]));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('keep-last: an offline AFTER a good fetch keeps the prior data and flips phase to offline', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(okJson({ items: [9] }))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() =>
      useOrganFetch('/x', {
        events: ['AI-OS LINK ESTABLISHED'],
        onData: (j) => j.items,
      }),
    );
    await waitFor(() => expect(result.current.phase).toBe('ready'));
    expect(result.current.data).toEqual([9]);

    act(() => { publishCognition({ type: 'synthesis', label: 'AI-OS LINK ESTABLISHED' }); });
    await waitFor(() => expect(result.current.phase).toBe('offline'));
    // Last-known data is preserved (we never blank a populated organ on a blip),
    // and hadData stays true so the organ shows the "· link offline" tag, not the
    // first-load placeholder.
    expect(result.current.data).toEqual([9]);
    expect(result.current.hadData).toBe(true);
  });
});

describe('useOrganFetch — cleanup', () => {
  it('does not throw and stops updating after unmount', async () => {
    let resolveFetch;
    const fetchMock = vi.fn(() => new Promise((res) => { resolveFetch = () => res(okJson({ items: [1] })); }));
    vi.stubGlobal('fetch', fetchMock);
    const { result, unmount } = renderHook(() => useOrganFetch('/x', { onData: (j) => j.items }));
    expect(result.current.phase).toBe('loading');
    unmount();
    // Resolving the in-flight fetch after unmount must be a no-op (no act warning,
    // no state write) — the hook guards on mountedRef.
    await act(async () => { resolveFetch(); await Promise.resolve(); });
    expect(result.current.phase).toBe('loading');
  });
});
