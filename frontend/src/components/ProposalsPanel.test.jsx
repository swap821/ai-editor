import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ProposalsPanel from './ProposalsPanel';

const YELLOW_PROPOSAL = {
  id: 1,
  target_path: 'aios/memory/db.py',
  finding_type: 'complexity',
  evidence: 'cyclomatic complexity 13 (> 12)',
  proposed_zone: 'YELLOW',
  proposed_diff: '--- a/aios/memory/db.py\n+++ b/aios/memory/db.py\n@@ -1 +1 @@\n-old\n+new\n',
  status: 'proposed',
};

const RED_PROPOSAL = {
  id: 2,
  target_path: 'aios/security/gateway.py',
  finding_type: 'smell',
  evidence: 'frozen core',
  proposed_zone: 'RED',
  proposed_diff: '--- a/aios/security/gateway.py\n+++ b/aios/security/gateway.py\n@@ -1 +1 @@\n-a\n+b\n',
  status: 'proposed',
};

function mockFetch(
  proposals,
  applyResult = { status: 'applied', reason: 'applied and verified: aios/memory/db.py', verify: 'ok' },
) {
  return vi.fn((url) => {
    if (String(url).includes('/proposals?status=proposed')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ proposals }) });
    }
    if (String(url).includes('/apply')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(applyResult) });
    }
    if (String(url).includes('/reject')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ id: 1, status: 'rejected' }) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ proposals: [] }) });
  });
}

describe('ProposalsPanel', () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('renders a fetched proposal with its diff', async () => {
    vi.stubGlobal('fetch', mockFetch([YELLOW_PROPOSAL]));
    render(<ProposalsPanel />);
    expect(await screen.findByText('aios/memory/db.py')).toBeInTheDocument();
    expect(screen.getByText('+new')).toBeInTheDocument();   // diff via DiffView
  });

  it('approves: POSTs to the apply endpoint with approvedBy and shows the result', async () => {
    const fetchMock = mockFetch([YELLOW_PROPOSAL]);
    vi.stubGlobal('fetch', fetchMock);
    render(<ProposalsPanel />);

    const approve = await screen.findByRole('button', { name: /approve & apply/i });
    fireEvent.click(approve);

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(c => String(c[0]).includes('/proposals/1/apply'));
      expect(call).toBeTruthy();
      expect(call[1].method).toBe('POST');
      expect(JSON.parse(call[1].body)).toEqual({ approvedBy: 'operator' });
    });
    expect(await screen.findByTestId('apply-result')).toHaveTextContent(/applied/i);
  });

  it('renders a RED proposal with Approve disabled (apply blocked, T4)', async () => {
    vi.stubGlobal('fetch', mockFetch([RED_PROPOSAL]));
    render(<ProposalsPanel />);
    const blocked = await screen.findByRole('button', { name: /red — apply blocked/i });
    expect(blocked).toBeDisabled();
  });

  it('rejects: POSTs to the reject endpoint', async () => {
    const fetchMock = mockFetch([YELLOW_PROPOSAL]);
    vi.stubGlobal('fetch', fetchMock);
    render(<ProposalsPanel />);

    const reject = await screen.findByRole('button', { name: /^reject$/i });
    fireEvent.click(reject);

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(c => String(c[0]).includes('/proposals/1/reject'));
      expect(call).toBeTruthy();
      expect(call[1].method).toBe('POST');
    });
  });
});
