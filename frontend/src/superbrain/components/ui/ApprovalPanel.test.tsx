import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ComponentProps } from 'react';
import ApprovalPanel from './ApprovalPanel';
import { approvePendingApproval, rejectPendingApproval } from '@/lib/aiosAdapter';

vi.mock('@/lib/aiosAdapter', () => ({
  approvePendingApproval: vi.fn(),
  rejectPendingApproval: vi.fn(),
}));

type Pending = ComponentProps<typeof ApprovalPanel>['pending'];

function makePending(overrides: Record<string, unknown> = {}): Pending {
  return {
    token: 'tok-1',
    kind: 'other',
    filepath: 'src/a.ts',
    summary: 'Change a thing',
    explanation: '',
    url: '',
    command: '',
    content: 'full content',
    diff: '',
    ...overrides,
  } as unknown as Pending;
}

const approveMock = vi.mocked(approvePendingApproval);
const rejectMock = vi.mocked(rejectPendingApproval);

beforeEach(() => {
  approveMock.mockReset();
  rejectMock.mockReset();
});

afterEach(() => {
  cleanup();
});

describe('ApprovalPanel', () => {
  it('renders the summary, path and classifies diff lines', () => {
    const diff = '--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new\n ctx';
    render(<ApprovalPanel pending={makePending({ diff })} onSettled={vi.fn()} />);

    expect(screen.getByText('OPERATOR APPROVAL REQUIRED')).toBeTruthy();
    expect(screen.getByText('src/a.ts')).toBeTruthy();
    expect(screen.getByText('Change a thing')).toBeTruthy();

    const pre = screen.getByLabelText('Proposed change');
    const classOf = (text: string) =>
      Array.from(pre.querySelectorAll('span')).find((s) => s.textContent === `${text}\n`)?.className;
    expect(classOf('--- a')).toBe('diff-file');
    expect(classOf('+++ b')).toBe('diff-file');
    expect(classOf('@@ -1 +1 @@')).toBe('diff-hunk');
    expect(classOf('-old')).toBe('diff-del');
    expect(classOf('+new')).toBe('diff-add');
    expect(classOf(' ctx')).toBe('');
    expect(within(pre).getAllByText(/\S/).length).toBe(6);
  });

  it('shows the kind suffix and the hostname for browse requests', () => {
    render(
      <ApprovalPanel
        pending={makePending({ kind: 'browse', url: 'https://example.com/page?q=1', filepath: '' })}
        onSettled={vi.fn()}
      />,
    );
    expect(screen.getByText(/· BROWSE/)).toBeTruthy();
    const region = screen.getByLabelText('Public web page request');
    expect(within(region).getByText('example.com')).toBeTruthy();
    expect(within(region).getByText('https://example.com/page?q=1')).toBeTruthy();
  });

  it('authorizes: disables buttons while replaying, then settles with success', async () => {
    let resolve: (v: Awaited<ReturnType<typeof approvePendingApproval>>) => void = () => {};
    approveMock.mockReturnValue(
      new Promise((r) => {
        resolve = r;
      }),
    );
    const onSettled = vi.fn();
    const onReplayStarted = vi.fn();
    render(
      <ApprovalPanel pending={makePending()} onSettled={onSettled} onReplayStarted={onReplayStarted} />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'AUTHORIZE' }));

    expect(onReplayStarted).toHaveBeenCalledTimes(1);
    const busyButton = screen.getByRole('button', { name: 'EXECUTING…' }) as HTMLButtonElement;
    expect(busyButton.disabled).toBe(true);
    expect((screen.getByRole('button', { name: 'REJECT' }) as HTMLButtonElement).disabled).toBe(true);
    expect(onSettled).not.toHaveBeenCalled();

    resolve({ ok: true, paused: false, answer: 'all done' } as Awaited<
      ReturnType<typeof approvePendingApproval>
    >);

    await waitFor(() => expect(onSettled).toHaveBeenCalledTimes(1));
    expect(onSettled).toHaveBeenCalledWith({
      action: 'authorize',
      kind: 'other',
      filepath: 'src/a.ts',
      content: 'full content',
      diff: '',
      succeeded: true,
      paused: false,
      answer: 'all done',
    });
    expect((screen.getByRole('button', { name: 'AUTHORIZE' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('treats a paused replay and a thrown replay as not succeeded', async () => {
    approveMock.mockResolvedValueOnce({ ok: true, paused: true, answer: '' } as Awaited<
      ReturnType<typeof approvePendingApproval>
    >);
    const onSettled = vi.fn();
    render(<ApprovalPanel pending={makePending()} onSettled={onSettled} />);

    fireEvent.click(screen.getByRole('button', { name: 'AUTHORIZE' }));
    await waitFor(() => expect(onSettled).toHaveBeenCalledTimes(1));
    expect(onSettled.mock.calls[0][0]).toMatchObject({ action: 'authorize', succeeded: false, paused: true });
    expect(onSettled.mock.calls[0][0]).not.toHaveProperty('answer');

    approveMock.mockRejectedValueOnce(new Error('aborted'));
    fireEvent.click(screen.getByRole('button', { name: 'AUTHORIZE' }));
    await waitFor(() => expect(onSettled).toHaveBeenCalledTimes(2));
    expect(onSettled.mock.calls[1][0]).toMatchObject({ action: 'authorize', succeeded: false, paused: false });
  });

  it('rejects through the audited endpoint with the token and reports confirmation', async () => {
    rejectMock.mockResolvedValueOnce({ confirmed: true } as Awaited<ReturnType<typeof rejectPendingApproval>>);
    const onSettled = vi.fn();
    const onRejectStarted = vi.fn();
    render(
      <ApprovalPanel pending={makePending()} onSettled={onSettled} onRejectStarted={onRejectStarted} />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'REJECT' }));

    await waitFor(() => expect(onSettled).toHaveBeenCalledTimes(1));
    expect(onRejectStarted).toHaveBeenCalledTimes(1);
    expect(rejectMock).toHaveBeenCalledWith('tok-1');
    expect(approveMock).not.toHaveBeenCalled();
    expect(onSettled).toHaveBeenCalledWith({
      action: 'reject',
      kind: 'other',
      filepath: 'src/a.ts',
      content: 'full content',
      diff: '',
      succeeded: true,
      paused: false,
    });
  });

  it('reports an unconfirmed reject when the endpoint fails', async () => {
    rejectMock.mockRejectedValueOnce(new Error('offline'));
    const onSettled = vi.fn();
    render(<ApprovalPanel pending={makePending()} onSettled={onSettled} />);

    fireEvent.click(screen.getByRole('button', { name: 'REJECT' }));

    await waitFor(() => expect(onSettled).toHaveBeenCalledTimes(1));
    expect(onSettled.mock.calls[0][0]).toMatchObject({ action: 'reject', succeeded: false, paused: false });
  });
});
