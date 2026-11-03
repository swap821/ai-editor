import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import GagosTasksPanel from './GagosTasksPanel';

type Call = { url: string; method: string; body: unknown };

const TASKS = [
  { task_id: 'gt-0000000001', created_at: 't1', rel: 'aios/a.py', text: 'Rename x to y', said_by: 'operator-principal-SECRET', status: 'open', proposal_id: null, reason: null, proposal: null },
  {
    task_id: 'gt-0000000002', created_at: 't2', rel: 'aios/b.py', text: 'line one\nline two\nline three\nline four-hidden', said_by: 'operator-principal-SECRET',
    status: 'taken', proposal_id: 'p1', reason: null,
    proposal: {
      proposal_id: 'p1', model: 'claude-sonnet', status: 'reviewed', refusal: null, changed_lines: 4, sandbox: 'passed',
      reviews: { 'claude-code': { verdict: 'accept', reason: 'small and tested' } }, pr_url: 'https://github.com/swap821/ai-editor/pull/900',
    },
  },
  { task_id: 'gt-0000000003', created_at: 't3', rel: 'aios/security/x.py', text: 'Touch security', said_by: 'operator-principal-SECRET', status: 'refused', proposal_id: null, reason: 'a file GAGOS may not edit', proposal: null },
  { task_id: 'gt-0000000004', created_at: 't4', rel: 'aios/d.py', text: 'Never mind', said_by: 'operator-principal-SECRET', status: 'cancelled', proposal_id: null, reason: 'withdrawn by the operator', proposal: null },
];

function backend(calls: Call[], overrides: Record<string, { status: number; body: unknown }> = {}) {
  return vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
    const key = `${method} ${url.replace(/^.*\/api\//, '/api/')}`;
    const hit = overrides[key] ?? (method === 'GET' ? { status: 200, body: { tasks: TASKS } } : { status: 201, body: { task: TASKS[0] } });
    return Promise.resolve({ ok: hit.status < 400, status: hit.status, json: () => Promise.resolve(hit.body) } as Response);
  });
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers(); });

describe('GagosTasksPanel', () => {
  it('shows tasks of every status, a taken one with its reviews and PR link, and never the principal', async () => {
    vi.stubGlobal('fetch', backend([]));
    const { container } = render(<GagosTasksPanel />);
    expect(await screen.findByText('gt-0000000001')).toBeInTheDocument();
    for (const status of ['open', 'taken', 'refused', 'cancelled']) {
      expect(screen.getByText(`Status: ${status}`)).toBeInTheDocument();
    }
    expect(screen.getByText('a file GAGOS may not edit')).toBeInTheDocument();
    expect(screen.getByText('claude-sonnet')).toBeInTheDocument();
    expect(screen.getByText('passed')).toBeInTheDocument();
    expect(screen.getByText('Review by claude-code')).toBeInTheDocument();
    expect(screen.getByText(/accept — small and tested/)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'https://github.com/swap821/ai-editor/pull/900' });
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(container.textContent).not.toContain('operator-principal-SECRET');
    // Only the open task can be cancelled.
    expect(screen.getAllByRole('button', { name: 'Cancel this task' })).toHaveLength(1);
  });

  it('collapses a long task to its first lines and expands it', async () => {
    vi.stubGlobal('fetch', backend([]));
    render(<GagosTasksPanel />);
    const summary = await screen.findByText(/show all 4 lines/);
    const details = summary.closest('details')!;
    expect(details).not.toHaveAttribute('open');
    fireEvent.click(summary);
    expect(details).toHaveAttribute('open');
  });

  it('does not make a link of a PR address that is not https', async () => {
    const bad = TASKS.map((t) => (t.proposal ? { ...t, proposal: { ...t.proposal, pr_url: 'javascript:alert(1)' } } : t));
    vi.stubGlobal('fetch', backend([], { 'GET /api/gagos/tasks': { status: 200, body: { tasks: bad } } }));
    render(<GagosTasksPanel />);
    await screen.findByText('gt-0000000002');
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('posts exactly {file, text}, clears the text and refreshes the list', async () => {
    const calls: Call[] = [];
    vi.stubGlobal('fetch', backend(calls));
    render(<GagosTasksPanel />);
    await screen.findByText('gt-0000000001');
    fireEvent.change(screen.getByLabelText(/File/), { target: { value: ' aios/a.py ' } });
    fireEvent.change(screen.getByLabelText('What should change'), { target: { value: 'Rename x to y' } });
    expect(screen.getByText('13 / 4000 characters')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Give GAGOS this task' }));
    await waitFor(() => expect(screen.getByLabelText('What should change')).toHaveValue(''));
    const post = calls.find((c) => c.method === 'POST')!;
    expect(post.url).toMatch(/\/api\/gagos\/tasks$/);
    expect(post.body).toEqual({ file: 'aios/a.py', text: 'Rename x to y' });
    await waitFor(() => expect(calls.filter((c) => c.method === 'GET').length).toBeGreaterThanOrEqual(2));
  });

  it('shows the server detail of a 422 and keeps the text', async () => {
    vi.stubGlobal('fetch', backend([], { 'POST /api/gagos/tasks': { status: 422, body: { detail: 'aios/security is a file GAGOS may not edit' } } }));
    render(<GagosTasksPanel />);
    await screen.findByText('gt-0000000001');
    fireEvent.change(screen.getByLabelText(/File/), { target: { value: 'aios/security/x.py' } });
    fireEvent.change(screen.getByLabelText('What should change'), { target: { value: 'do it' } });
    fireEvent.click(screen.getByRole('button', { name: 'Give GAGOS this task' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('aios/security is a file GAGOS may not edit');
    expect(screen.getByLabelText('What should change')).toHaveValue('do it');
  });

  it('will not send text over 4000 characters', async () => {
    vi.stubGlobal('fetch', backend([]));
    render(<GagosTasksPanel />);
    await screen.findByText('gt-0000000001');
    fireEvent.change(screen.getByLabelText(/File/), { target: { value: 'a.py' } });
    fireEvent.change(screen.getByLabelText('What should change'), { target: { value: 'x'.repeat(4001) } });
    expect(screen.getByText('4001 / 4000 characters')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Give GAGOS this task' })).toBeDisabled();
  });

  it('cancels an open task at its own URL and shows a 409 detail', async () => {
    const calls: Call[] = [];
    vi.stubGlobal('fetch', backend(calls, { 'POST /api/gagos/tasks/gt-0000000001/cancel': { status: 409, body: { detail: 'the task is no longer open' } } }));
    render(<GagosTasksPanel />);
    const item = (await screen.findByText('gt-0000000001')).closest('li')!;
    fireEvent.click(within(item).getByRole('button', { name: 'Cancel this task' }));
    expect(await within(item).findByRole('alert')).toHaveTextContent('the task is no longer open');
    const post = calls.find((c) => c.method === 'POST')!;
    expect(post.url).toMatch(/\/api\/gagos\/tasks\/gt-0000000001\/cancel$/);
  });

  it('polls gently while open and stops when closed', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const calls: Call[] = [];
    vi.stubGlobal('fetch', backend(calls));
    const { unmount } = render(<GagosTasksPanel />);
    await screen.findByText('gt-0000000001');
    const before = calls.length;
    await vi.advanceTimersByTimeAsync(60_000);
    await waitFor(() => expect(calls.length).toBeGreaterThan(before));
    unmount();
    const after = calls.length;
    await vi.advanceTimersByTimeAsync(120_000);
    expect(calls.length).toBe(after);
  });
});
