import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { GuidedApprovalPanel } from './GuidedApprovalPanel';

const mocks = vi.hoisted(() => ({
  approvePendingApproval: vi.fn(),
  rejectPendingApproval: vi.fn(),
  recordFrontendMetric: vi.fn(),
  measuredLatency: vi.fn(),
}));

vi.mock('@/lib/aiosAdapter', () => ({
  approvePendingApproval: mocks.approvePendingApproval,
  rejectPendingApproval: mocks.rejectPendingApproval,
}));
vi.mock('./observability/frontendMetrics', () => ({ recordFrontendMetric: mocks.recordFrontendMetric }));
vi.mock('./observability/latency', () => ({ measuredLatency: mocks.measuredLatency }));

type Pending = Parameters<typeof GuidedApprovalPanel>[0]['pending'];

function makePending(overrides: Record<string, unknown> = {}): Pending {
  return {
    token: 'tok-1',
    kind: 'create',
    filepath: 'src/a.ts',
    content: 'const a = 1;',
    diff: '',
    summary: '',
    explanation: '',
    command: '',
    url: '',
    ...overrides,
  } as unknown as Pending;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.measuredLatency.mockReturnValue(5);
});

afterEach(() => {
  cleanup();
});

describe('GuidedApprovalPanel', () => {
  it('explains a create request in plain language and focuses the Allow button', () => {
    render(<GuidedApprovalPanel pending={makePending()} onSettled={vi.fn()} />);

    expect(screen.getByRole('alertdialog').getAttribute('aria-label')).toBe('GAGOS permission request');
    const facts = screen.getByLabelText('Permission details').textContent ?? '';
    expect(facts).toContain('Whatcreate src/a.ts');
    expect(facts).toContain('Wheresrc/a.ts');
    expect(facts).toContain('If you say noGAGOS will not perform this action.');
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Allow once' }));
    expect(mocks.recordFrontendMetric).toHaveBeenCalledWith('approval-render', 5);
  });

  it('shows the hostname and URL for a browse request', () => {
    render(
      <GuidedApprovalPanel
        pending={makePending({ kind: 'browse', filepath: '', url: 'https://example.com/page' })}
        onSettled={vi.fn()}
      />,
    );

    expect(screen.getAllByText('fetch a web page').length).toBeGreaterThan(0);
    expect(screen.getByText('example.com')).toBeTruthy();
    expect(screen.getAllByText('https://example.com/page').length).toBeGreaterThan(0);
  });

  it('reports a successful authorization and disables both buttons while busy', async () => {
    let resolve: (value: unknown) => void = () => {};
    mocks.approvePendingApproval.mockReturnValue(new Promise((r) => { resolve = r; }));
    const onSettled = vi.fn();
    render(<GuidedApprovalPanel pending={makePending()} onSettled={onSettled} />);

    fireEvent.click(screen.getByRole('button', { name: 'Allow once' }));

    const allowing = screen.getByRole('button', { name: 'Allowing…' }) as HTMLButtonElement;
    expect(allowing.disabled).toBe(true);
    expect((screen.getByRole('button', { name: "Don't allow" }) as HTMLButtonElement).disabled).toBe(true);

    resolve({ ok: true, paused: false, emittedCode: undefined, answer: '' });
    await waitFor(() => expect(onSettled).toHaveBeenCalledTimes(1));
    expect(onSettled).toHaveBeenCalledWith({
      action: 'authorize',
      kind: 'create',
      filepath: 'src/a.ts',
      content: 'const a = 1;',
      diff: '',
      succeeded: true,
      paused: false,
    });
    expect(mocks.approvePendingApproval).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect((screen.getByRole('button', { name: 'Allow once' }) as HTMLButtonElement).disabled).toBe(false),
    );
  });

  it('treats a paused replay as not succeeded and forwards the answer', async () => {
    mocks.approvePendingApproval.mockResolvedValue({ ok: true, paused: true, answer: 'next step' });
    const onSettled = vi.fn();
    render(<GuidedApprovalPanel pending={makePending()} onSettled={onSettled} />);

    fireEvent.click(screen.getByRole('button', { name: 'Allow once' }));

    await waitFor(() => expect(onSettled).toHaveBeenCalledTimes(1));
    expect(onSettled).toHaveBeenCalledWith({
      action: 'authorize',
      kind: 'create',
      filepath: 'src/a.ts',
      content: 'const a = 1;',
      diff: '',
      succeeded: false,
      paused: true,
      answer: 'next step',
    });
  });

  it('rejects with the token, notifies onRejectStarted, and reports confirmation', async () => {
    mocks.rejectPendingApproval.mockResolvedValue({ confirmed: true });
    const onSettled = vi.fn();
    const onRejectStarted = vi.fn();
    render(
      <GuidedApprovalPanel
        pending={makePending()}
        onSettled={onSettled}
        onRejectStarted={onRejectStarted}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: "Don't allow" }));

    await waitFor(() => expect(onSettled).toHaveBeenCalledTimes(1));
    expect(onRejectStarted).toHaveBeenCalledTimes(1);
    expect(mocks.rejectPendingApproval).toHaveBeenCalledWith('tok-1');
    expect(onSettled).toHaveBeenCalledWith({
      action: 'reject',
      kind: 'create',
      filepath: 'src/a.ts',
      content: 'const a = 1;',
      diff: '',
      succeeded: true,
      paused: false,
    });
  });

  it('reports failure when rejecting throws', async () => {
    mocks.rejectPendingApproval.mockRejectedValue(new Error('offline'));
    const onSettled = vi.fn();
    render(<GuidedApprovalPanel pending={makePending()} onSettled={onSettled} />);

    fireEvent.click(screen.getByRole('button', { name: "Don't allow" }));

    await waitFor(() => expect(onSettled).toHaveBeenCalledTimes(1));
    expect(onSettled.mock.calls[0][0]).toMatchObject({ action: 'reject', succeeded: false, paused: false });
  });

  it('wraps Tab focus from the last control to the first', () => {
    render(<GuidedApprovalPanel pending={makePending()} onSettled={vi.fn()} />);

    const dontAllow = screen.getByRole('button', { name: "Don't allow" });
    dontAllow.focus();
    fireEvent.keyDown(dontAllow, { key: 'Tab' });

    expect(document.activeElement).not.toBe(dontAllow);
    expect(screen.getByRole('alertdialog').contains(document.activeElement)).toBe(true);
  });
});
