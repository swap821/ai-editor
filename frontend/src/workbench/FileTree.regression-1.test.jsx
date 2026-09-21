import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import FileTree from './FileTree';

vi.mock('../components/HUDPanel', () => ({
  default: ({ title, children }) => (
    <div data-testid="hud-panel" data-title={title}>{children}</div>
  )
}));

describe('FileTree failure recovery', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('keeps a child-load failure visible and retries the same directory', async () => {
    const root = [{ name: 'src', path: '/src', type: 'directory', status: 'normal', children: [] }];
    const fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => root })
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce({ ok: true, json: async () => [{ name: 'main.jsx', path: '/src/main.jsx', type: 'file', status: 'normal' }] });
    globalThis.fetch = fetch;

    render(<FileTree onOpenFile={vi.fn()} onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Could not load src. Try again.'));
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('main.jsx')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it('offers a root retry when the initial tree is unavailable', async () => {
    const fetch = vi.fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce({ ok: true, json: async () => [{ name: 'README.md', path: '/README.md', type: 'file', status: 'normal' }] });
    globalThis.fetch = fetch;

    render(<FileTree onOpenFile={vi.fn()} onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('File tree offline'));
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('README.md')).toBeInTheDocument();
  });
});
