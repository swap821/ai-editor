import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, it, expect, vi } from 'vitest';
import StigmergyPanel from './StigmergyPanel';
import { API_BASE } from '../config';

vi.mock('../components/HUDPanel', () => ({
  default: ({ title, children, tint }) => (
    <div data-testid="hud-panel" data-title={title} data-tint={tint}>{children}</div>
  )
}));

describe('StigmergyPanel unavailable graph regression', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('does not leak a parser error when the graph response is not JSON', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => { throw new SyntaxError('Unexpected token < in JSON at position 0'); }
    });

    render(<StigmergyPanel onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(/could not be read/);
    });
    expect(screen.queryByText(/Unexpected token/)).not.toBeInTheDocument();
  });

  it('reads the configured local API with the operator session and labels only submitted queries', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ start: 'system', depth: 2, edges: [] }) });
    vi.stubGlobal('fetch', fetch);
    render(<StigmergyPanel />);
    expect(await screen.findByText('No edges found for "system".')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(`${API_BASE}/api/v1/memory/facts/graph?start=system&depth=2`,
      expect.objectContaining({ credentials: 'include', signal: expect.any(AbortSignal) }));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'draft not queried' } });
    expect(screen.getByText('No edges found for "system".')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('cancels superseded requests so late results cannot replace the selected graph', async () => {
    let resolveFirst;
    const fetch = vi.fn().mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
      .mockResolvedValueOnce({ ok: true, json: async () => ({ start: 'next', depth: 2,
        edges: [{ subject: 'next', predicate: 'uses', object: 'current result', depth: 1, path: 'next -> current result' }] }) });
    vi.stubGlobal('fetch', fetch);
    const view = render(<StigmergyPanel />);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'next' } });
    fireEvent.click(screen.getByRole('button', { name: 'Query' }));
    expect(await screen.findByText('current result')).toBeInTheDocument();
    await act(async () => resolveFirst({ ok: true, json: async () => ({ start: 'system', depth: 2,
      edges: [{ subject: 'system', predicate: 'uses', object: 'old result', depth: 1, path: 'system -> old result' }] }) }));
    expect(screen.queryByText('old result')).not.toBeInTheDocument();
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
    view.unmount();
    expect(fetch.mock.calls[1][1].signal.aborted).toBe(true);
  });

  it('retains valid last-known edges but marks a malformed refresh as failed, not empty', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ start: 'system', depth: 2,
      edges: [{ subject: 'system', predicate: 'uses', object: 'known fact', depth: 1, path: 'system -> known fact' }] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ start: 'system', depth: 2, edges: [{}] }) }));
    render(<StigmergyPanel />);
    expect(await screen.findByText('known fact')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/last-known/i));
    expect(screen.getByText('known fact')).toBeInTheDocument();
    expect(screen.queryByText(/No edges found/)).not.toBeInTheDocument();
  });
});
