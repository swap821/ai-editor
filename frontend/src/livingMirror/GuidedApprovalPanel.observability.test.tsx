import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import GuidedApprovalPanel from './GuidedApprovalPanel';

const recordFrontendMetric = vi.hoisted(() => vi.fn());
const approvePendingApproval = vi.hoisted(() => vi.fn());
const rejectPendingApproval = vi.hoisted(() => vi.fn());

vi.mock('./observability/frontendMetrics', () => ({ recordFrontendMetric }));
vi.mock('@/lib/aiosAdapter', () => ({
  approvePendingApproval,
  rejectPendingApproval,
}));

const pending = {
  token: 'approval-token',
  prompt: 'create a file',
  summary: 'Approval required to create a file.',
  explanation: 'The file will be created in the project.',
  diff: '--- /dev/null\n+++ b/example.txt',
  command: '',
  url: '',
  kind: 'create' as const,
  filepath: 'example.txt',
  content: 'hello\n',
};

describe('GuidedApprovalPanel observability', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    recordFrontendMetric.mockReset();
    approvePendingApproval.mockReset();
    rejectPendingApproval.mockReset();
  });

  it('records a positive measured approval render sample', async () => {
    let now = 100;
    vi.spyOn(performance, 'now').mockImplementation(() => {
      now += 1;
      return now;
    });

    render(<GuidedApprovalPanel pending={pending} onSettled={() => {}} />);

    await waitFor(() => expect(recordFrontendMetric).toHaveBeenCalledWith('approval-render', expect.any(Number)));
    const sample = recordFrontendMetric.mock.calls.find(([name]) => name === 'approval-render');
    expect(sample?.[1]).toBeGreaterThan(0);
  });

  it('keeps keyboard focus inside the approval boundary', async () => {
    render(<GuidedApprovalPanel pending={pending} onSettled={() => {}} />);
    const dialog = screen.getByRole('alertdialog', { name: 'GAGOS permission request' });
    const explain = screen.getByText('Explain');
    const allow = screen.getByRole('button', { name: 'Allow once' });
    const deny = screen.getByRole('button', { name: "Don't allow" });

    await waitFor(() => expect(allow).toHaveFocus());

    deny.focus();
    fireEvent.keyDown(dialog, { key: 'Tab' });
    expect(explain).toHaveFocus();

    explain.focus();
    fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });
    expect(deny).toHaveFocus();
  });

  it('reports a replay pause without presenting the first step as completed', async () => {
    approvePendingApproval.mockResolvedValue({ ok: true, paused: true, answer: '' });
    const onSettled = vi.fn();
    render(<GuidedApprovalPanel pending={pending} onSettled={onSettled} />);

    fireEvent.click(screen.getByRole('button', { name: 'Allow once' }));

    await waitFor(() => expect(onSettled).toHaveBeenCalledWith(expect.objectContaining({
      action: 'authorize',
      succeeded: false,
      paused: true,
    })));
  });

  it('keeps model and provider vocabulary out of the Guided browse explanation', async () => {
    const browsePending = {
      ...pending,
      kind: 'browse' as const,
      filepath: '',
      url: 'https://example.test/reference',
      diff: '',
      explanation: '',
    };
    render(<GuidedApprovalPanel pending={browsePending} onSettled={() => {}} />);

    fireEvent.click(screen.getByText('Explain'));

    expect(screen.getByText(/sends the page content to GAGOS/i)).toBeInTheDocument();
    expect(screen.getByText(/approval record names this public page/i)).toBeInTheDocument();
    expect(screen.queryByText(/no local files or credentials are exposed/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/\bmodel\b/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/\bprovider\b/i)).not.toBeInTheDocument();
  });

  it('does not infer a project-wide effect boundary when the approval record omits one', () => {
    const commandPending = {
      ...pending,
      kind: 'command' as const,
      filepath: '',
      diff: '',
      command: 'pytest -q',
    };
    render(<GuidedApprovalPanel pending={commandPending} onSettled={() => {}} />);

    expect(screen.getByText(/complete effect boundary is not included in the approval record/i)).toBeInTheDocument();
    expect(screen.queryByText(/project scope/i)).not.toBeInTheDocument();
  });
});
