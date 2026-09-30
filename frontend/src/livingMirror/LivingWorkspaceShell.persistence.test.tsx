import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  __resetTabStoreForTests,
  closeWorkspace,
  focusWorkspace,
  getTabStoreSnapshot,
  openWorkspacePanel,
  showContentSurface,
  updateMaterializedTab,
} from '../superbrain/lib/tabStore';
import { LivingWorkspaceShell } from './LivingWorkspaceShell';
import { __resetSovereignIdentityForTests, refreshSovereignStatus } from '../superbrain/lib/sovereignIdentity';
// This is a continuity test, not a cold-chunk benchmark. Resolve the real
// editor module before the test's interaction deadline starts.
import '../workbench/CodeEditor';
import '../workbench/TerminalPanel';

// Keep the real shell, file-read boundary and CodeEditor draft state. Only
// Monaco's browser engine is replaced, so a shell remount still loses the draft.
vi.mock('../superbrain/lib/monacoConfig', () => ({}));
vi.mock('@monaco-editor/react', () => ({
  default: ({ value, onChange }: { value: string; onChange: (value: string) => void }) =>
    <textarea aria-label="File contents" value={value} onChange={(event) => onChange(event.target.value)} />,
}));

function openFile(path: string) {
  openWorkspacePanel(`file:${path}`, path, 'file', { path, name: path, content: '' });
}

beforeEach(() => {
  __resetTabStoreForTests();
  __resetSovereignIdentityForTests();
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/api/v1/files/read') && init?.method === 'POST') {
      const { path } = JSON.parse(String(init.body));
      return { ok: true, json: async () => ({ content: `Read from ${path}` }) };
    }
    return { ok: false, status: 503, json: async () => ({}) };
  }));
});

afterEach(() => {
  __resetTabStoreForTests();
  __resetSovereignIdentityForTests();
  vi.unstubAllGlobals();
});

describe('workspace instance continuity', () => {
  it('releases the embedded Terminal on its own Close and reopens with fresh input', async () => {
    render(<LivingWorkspaceShell experienceMode="expert" />);
    act(() => openWorkspacePanel('terminal', 'Terminal'));
    const input = await screen.findByPlaceholderText('Type a command...');
    fireEvent.change(input, { target: { value: 'disposable unsent draft' } });
    fireEvent.click(within(screen.getByRole('region', { name: 'Selected workspace' }))
      .getByRole('button', { name: /^Close$/ }));
    expect(getTabStoreSnapshot().panels?.find((panel) => panel.id === 'terminal')?.open).toBe(false);
    expect(input).not.toBeInTheDocument();
    act(() => openWorkspacePanel('terminal', 'Terminal'));
    expect(await screen.findByPlaceholderText('Type a command...')).toHaveValue('');
    expect(screen.queryByText('Terminal (Ctrl+`)')).not.toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith('/api/terminal'))).toBe(false);
  });

  it('keeps unsent file edits, selection and scroll when attention moves to another workspace or Conversation', async () => {
    render(<LivingWorkspaceShell experienceMode="expert" />);
    act(() => openFile('/a.ts'));
    const editor = await screen.findByRole<HTMLTextAreaElement>('textbox', { name: 'File contents' }, { timeout: 5000 });
    fireEvent.change(editor, { target: { value: 'unsent draft A' } });
    editor.setSelectionRange(2, 8);
    const body = editor.closest<HTMLElement>('.lm-surface__body')!;
    body.scrollTop = 120;
    fireEvent.scroll(body);

    act(() => openFile('/b.ts'));
    expect(await screen.findByRole('textbox', { name: 'File contents' })).toHaveValue('Read from /b.ts');
    expect(editor).toBeInTheDocument();
    expect(editor).not.toBeVisible();
    expect(body).toHaveAttribute('inert');

    act(() => focusWorkspace('file:/a.ts'));
    expect(screen.getByRole('textbox', { name: 'File contents' })).toBe(editor);
    expect(editor).toHaveValue('unsent draft A');
    expect([editor.selectionStart, editor.selectionEnd]).toEqual([2, 8]);
    expect(body.scrollTop).toBe(120);

    const navigation = screen.getByRole('navigation', { name: 'Workspaces' });
    fireEvent.click(within(navigation).getByRole('button', { name: 'Conversation' }));
    expect(screen.queryByRole('textbox', { name: 'File contents' })).not.toBeInTheDocument();
    expect(editor).toBeInTheDocument();
    act(() => focusWorkspace('file:/a.ts'));
    expect(screen.getByRole('textbox', { name: 'File contents' })).toBe(editor);
    expect(editor).toHaveValue('unsent draft A');
    expect(body).not.toHaveAttribute('inert');
  });

  it('does not load a never-selected file and releases an editor on explicit close', async () => {
    render(<LivingWorkspaceShell experienceMode="expert" />);
    act(() => { openFile('/a.ts'); openFile('/b.ts'); });
    const editorB = await screen.findByRole('textbox', { name: 'File contents' });
    expect(editorB).toHaveValue('Read from /b.ts');
    const readPaths = () => vi.mocked(fetch).mock.calls
      .filter(([url]) => String(url).endsWith('/api/v1/files/read'))
      .map(([, init]) => JSON.parse(String(init?.body)).path);
    expect(readPaths()).toEqual(['/b.ts']);

    act(() => focusWorkspace('file:/a.ts'));
    const editorA = await screen.findByRole('textbox', { name: 'File contents' });
    fireEvent.change(editorA, { target: { value: 'draft to discard on close' } });
    act(() => closeWorkspace('file:/a.ts'));
    expect(editorA).not.toBeInTheDocument();
    act(() => openFile('/a.ts'));
    expect(await screen.findByRole('textbox', { name: 'File contents' })).toHaveValue('Read from /a.ts');
    expect(readPaths()).toEqual(['/b.ts', '/a.ts', '/a.ts']);
    expect(editorB).toBeInTheDocument();
  });

  it('preserves a file editor through a mode change and compact workspace collapse', async () => {
    vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
      matches: query.includes('max-width'), media: query,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
    })));
    const view = render(<LivingWorkspaceShell experienceMode="beginner" />);
    act(() => openFile('/mobile.ts'));
    const editor = await screen.findByRole('textbox', { name: 'File contents' });
    fireEvent.change(editor, { target: { value: 'phone draft' } });
    view.rerender(<LivingWorkspaceShell experienceMode="expert" />);
    expect(editor).toBeInTheDocument();
    expect(editor).not.toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Expand workspace' }));
    expect(screen.getByRole('textbox', { name: 'File contents' })).toBe(editor);
    expect(editor).toHaveValue('phone draft');
    view.rerender(<LivingWorkspaceShell experienceMode="beginner" />);
    expect(screen.getByRole('textbox', { name: 'File contents' })).toBe(editor);
  });

  it('retains drafts during an unknown identity measurement but releases open views on measured sign-out', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => ({ authenticated: true, operatorId: 'operator-a' }) } as Response);
    await refreshSovereignStatus();
    render(<LivingWorkspaceShell experienceMode="expert" />);
    act(() => openFile('/private.ts'));
    const editor = await screen.findByRole('textbox', { name: 'File contents' });
    fireEvent.change(editor, { target: { value: 'private unsent draft' } });
    act(() => focusWorkspace(null));
    vi.mocked(fetch).mockRejectedValueOnce(new Error('temporarily offline'));
    await act(async () => { await refreshSovereignStatus(); });
    expect(editor).toBeInTheDocument();

    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => ({ authenticated: false, operatorId: null }) } as Response);
    await act(async () => { await refreshSovereignStatus(); });
    expect(editor).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '/private.ts' })).not.toBeInTheDocument();
  });

  it('keeps artifact scroll and disclosure while another workspace is selected and updates arrive', async () => {
    await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
    let artifactId = '';
    act(() => {
      artifactId = showContentSurface({ filepath: 'result.ts', code: 'first chunk', language: 'typescript', verifyOutput: 'Reported output' }).id;
    });
    const output = screen.getByText('first chunk');
    const body = output.closest<HTMLElement>('.lm-surface__body')!;
    const disclosure = screen.getByText('Reported check output').closest('details')!;
    fireEvent.click(screen.getByText('Reported check output'));
    body.scrollTop = 80;
    fireEvent.scroll(body);

    act(() => openWorkspacePanel('history', 'Recent observations'));
    expect(output).toBeInTheDocument();
    expect(output).not.toBeVisible();
    act(() => updateMaterializedTab(artifactId, {
      content: { filepath: 'result.ts', code: 'finished chunk', language: 'typescript', verifyOutput: 'Reported output' },
    }));
    act(() => focusWorkspace(artifactId));
    expect(screen.getByText('finished chunk')).toBe(output);
    expect(disclosure).toHaveAttribute('open');
    expect(body.scrollTop).toBe(80);

    act(() => closeWorkspace(artifactId));
    expect(output).not.toBeInTheDocument();
  });
});
