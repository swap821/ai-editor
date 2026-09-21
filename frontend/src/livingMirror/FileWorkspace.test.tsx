import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FileWorkspace } from './LivingWorkspaceShell';
import type { WorkspacePanel } from '../superbrain/lib/tabStore';

vi.mock('../superbrain/lib/monacoConfig', () => ({}));
vi.mock('@monaco-editor/react', () => ({ default: ({ value, onChange }: { value: string; onChange: (value: string) => void }) =>
  <textarea aria-label="File contents" value={value} onChange={(event) => onChange(event.target.value)} /> }));
vi.mock('../components/HUDPanel', () => ({ default: ({ children }: { children: React.ReactNode }) => <section>{children}</section> }));

function panel(path: string): WorkspacePanel {
  return { id: `file:${path}`, title: path, kind: 'file', seatIndex: 2, open: true, pinned: false,
    file: { path, name: path, content: '' } };
}
const ok = (content: string) => ({ ok: true, json: async () => ({ content }) });

afterEach(() => vi.unstubAllGlobals());

describe('project file reads', () => {
  it('uses the real POST read contract once and keeps unsent editor changes local', async () => {
    const fetch = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/api/v1/files/read') && init?.method === 'POST'
        && init.credentials === 'include' && init.body === JSON.stringify({ path: '/src/a.ts' })) return ok('first file');
      return { ok: false, status: 405, json: async () => ({}) };
    });
    vi.stubGlobal('fetch', fetch);
    const view = render(<FileWorkspace panel={panel('/src/a.ts')} />);
    expect(await screen.findByRole('textbox', { name: 'File contents' })).toHaveValue('first file');
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'unsent draft' } });
    view.rerender(<FileWorkspace panel={panel('/src/a.ts')} />);
    expect(screen.getByRole('textbox')).toHaveValue('unsent draft');
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][1]?.headers).toMatchObject({ 'Content-Type': 'application/json' });
  });

  it('never labels the previous file contents as a different file while its POST read is pending', async () => {
    let resolveSecond!: (value: ReturnType<typeof ok>) => void;
    const second = new Promise<ReturnType<typeof ok>>((resolve) => { resolveSecond = resolve; });
    const fetch = vi.fn().mockResolvedValueOnce(ok('private contents of A')).mockReturnValueOnce(second);
    vi.stubGlobal('fetch', fetch);
    const view = render(<FileWorkspace panel={panel('/a.txt')} />);
    expect(await screen.findByRole('textbox')).toHaveValue('private contents of A');
    view.rerender(<FileWorkspace panel={panel('/b.txt')} />);
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    await act(async () => resolveSecond(ok('contents of B')));
    expect(await screen.findByRole('textbox')).toHaveValue('contents of B');
  });
});
