// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { ReadFailure, readResource, useResource } from './resource';

vi.mock('../config', () => ({ API_BASE: 'http://api.test' }));

const fetchMock = vi.fn();

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

const parseItems = (value: unknown): string[] => {
  if (!Array.isArray(value)) throw new Error('Expected a list');
  return value as string[];
};
const isEmptyList = (data: string[]): boolean => data.length === 0;

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe('readResource', () => {
  it('requests the API path with credentials and the signal, and returns the parsed body', async () => {
    fetchMock.mockResolvedValue(json(['a', 'b']));
    const controller = new AbortController();
    const result = await readResource('/things', parseItems, controller.signal, { method: 'POST' });
    expect(result).toEqual(['a', 'b']);
    expect(fetchMock).toHaveBeenCalledWith('http://api.test/things', {
      method: 'POST',
      credentials: 'include',
      signal: controller.signal,
    });
  });

  it.each([
    [401, 'unavailable', 'Connect your operator session to inspect these records.'],
    [403, 'unavailable', 'Your current session cannot inspect these records.'],
    [404, 'unavailable', 'Records could not be read (HTTP 404).'],
    [503, 'unavailable', 'Records could not be read (HTTP 503).'],
    [500, 'failed', 'Records could not be read (HTTP 500).'],
  ])('maps HTTP %i to a %s ReadFailure', async (code, status, message) => {
    fetchMock.mockResolvedValue(new Response('', { status: code }));
    const error = await readResource('/x', parseItems).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ReadFailure);
    expect(error).toMatchObject({ status, message });
  });

  it('reports an unreachable service as unavailable, but rethrows the original error when aborted', async () => {
    fetchMock.mockRejectedValue(new TypeError('network down'));
    await expect(readResource('/x', parseItems)).rejects.toMatchObject({
      status: 'unavailable',
      message: 'Local service could not be reached. Last-known records may be out of date.',
    });

    const abortError = new Error('aborted');
    const controller = new AbortController();
    controller.abort();
    fetchMock.mockRejectedValue(abortError);
    await expect(readResource('/x', parseItems, controller.signal)).rejects.toBe(abortError);
  });

  it('fails on non-JSON bodies and on parser errors', async () => {
    fetchMock.mockResolvedValue(new Response('not json', { status: 200 }));
    await expect(readResource('/x', parseItems)).rejects.toMatchObject({
      status: 'failed',
      message: 'Records could not be read. The service returned an unsupported response.',
    });

    fetchMock.mockResolvedValue(json({ nope: true }));
    await expect(readResource('/x', parseItems)).rejects.toMatchObject({
      status: 'failed',
      message: 'Expected a list',
    });
  });
});

describe('useResource', () => {
  it('starts loading, then becomes available with data and a receivedAt timestamp', async () => {
    fetchMock.mockResolvedValue(json(['one']));
    const { result } = renderHook(() => useResource('/a', parseItems, isEmptyList));
    expect(result.current.status).toBe('loading');
    await waitFor(() => expect(result.current.status).toBe('available'));
    expect(result.current.data).toEqual(['one']);
    expect(result.current.error).toBeNull();
    expect(result.current.source).toBe('/a');
    expect(result.current.receivedAt).not.toBeNull();
  });

  it('reports empty data as empty and read errors as unavailable with a message', async () => {
    fetchMock.mockResolvedValue(json([]));
    const empty = renderHook(() => useResource('/a', parseItems, isEmptyList));
    await waitFor(() => expect(empty.result.current.status).toBe('empty'));

    fetchMock.mockResolvedValue(new Response('', { status: 401 }));
    const denied = renderHook(() => useResource('/b', parseItems, isEmptyList));
    await waitFor(() => expect(denied.result.current.status).toBe('unavailable'));
    expect(denied.result.current.error).toBe('Connect your operator session to inspect these records.');
  });

  it('does not show the previous path\'s data while a newly selected path is loading', async () => {
    let resolveSecond: (r: Response) => void = () => undefined;
    fetchMock.mockResolvedValueOnce(json(['old']));
    fetchMock.mockReturnValueOnce(new Promise<Response>((resolve) => { resolveSecond = resolve; }));

    const { result, rerender } = renderHook(
      ({ path }: { path: string }) => useResource(path, parseItems, isEmptyList),
      { initialProps: { path: '/first' } },
    );
    await waitFor(() => expect(result.current.data).toEqual(['old']));

    rerender({ path: '/second' });
    expect(result.current.status).toBe('loading');
    expect(result.current.data).toBeNull();
    expect(result.current.source).toBe('/second');

    await act(async () => { resolveSecond(json(['new'])); });
    await waitFor(() => expect(result.current.data).toEqual(['new']));
  });

  it('refresh re-reads the same path', async () => {
    fetchMock.mockResolvedValueOnce(json(['v1']));
    fetchMock.mockResolvedValueOnce(json(['v2']));
    const { result } = renderHook(() => useResource('/a', parseItems, isEmptyList));
    await waitFor(() => expect(result.current.data).toEqual(['v1']));
    act(() => result.current.refresh());
    await waitFor(() => expect(result.current.data).toEqual(['v2']));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('does not fetch when the path is null', () => {
    const { result } = renderHook(() => useResource(null, parseItems, isEmptyList));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.status).toBe('loading');
    expect(result.current.source).toBe('');
  });
});
