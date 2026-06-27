import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import CouncilDashboard from './CouncilDashboard';

const missionsPayload = {
  missions: [
    {
      missionId: 'mission-ui-1',
      mission: 'Improve login page without backend changes.',
      status: 'completed',
      recommendation: 'approve',
      risk: 'YELLOW',
      approvalNeeded: true,
      rollbackAvailable: false,
      filesTouched: ['frontend/src/pages/Login.jsx'],
      blockedAttempts: 1,
      verificationPassed: true,
      councilVerdicts: [{ queen: 'security', verdict: 'allow_with_approval', risk: 'YELLOW' }],
      modelRouting: { provider: 'ollama', used_cloud: false, fallback_used: false },
      pendingApprovals: [{ requestId: 'approval-ui-1', action: 'write_file', reason: 'YELLOW write needs King decision' }],
      kingDecision: null,
    },
  ],
  count: 1,
};

const detailPayload = {
  missionId: 'mission-ui-1',
  report: {
    mission_id: 'mission-ui-1',
    mission: 'Improve login page without backend changes.',
    status: 'completed',
    council_summary: {
      council_verdicts: [
        { queen: 'planner', verdict: 'allow_with_approval', risk: 'YELLOW' },
        { queen: 'security', verdict: 'allow_with_approval', risk: 'YELLOW' },
        { queen: 'testing', verdict: 'allow', risk: 'GREEN' },
      ],
      model_routing: { provider: 'ollama', model: 'llama3.1:8b', used_cloud: false, fallback_used: false },
    },
    recommendation: 'approve',
    risk: 'YELLOW',
    files: ['frontend/src/pages/Login.jsx'],
    verification_result: { commands: [{ command: ['python', '-m', 'pytest'], returncode: 0 }] },
    approval_needed: true,
    rollback_available: false,
    rollback_id: null,
    human_summary: 'Worker completed the mission under its MissionContract.',
  },
  ledger: {
    blocked_attempts: [{ tool: 'read_file', reason: 'path forbidden' }],
    verification: { commands: [{ command: ['python', '-m', 'pytest'], returncode: 0 }] },
  },
  pendingApprovals: [{ requestId: 'approval-ui-1', action: 'write_file', reason: 'YELLOW write needs King decision' }],
  kingDecision: null,
};

describe('CouncilDashboard', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn((url: string, options?: RequestInit) => {
      if (options?.method === 'POST' && url.includes('/api/v1/council/approve')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            missionId: 'mission-ui-1',
            approvalResponseWritten: true,
            decision: {
              mission_id: 'mission-ui-1',
              request_id: 'approval-ui-1',
              decision: 'approve',
              approved: true,
              reason: 'Approved from Council dashboard',
            },
          }),
        });
      }
      if (url.includes('/api/v1/council/missions/mission-ui-1')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(detailPayload) });
      }
      if (url.includes('/api/v1/council/missions')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(missionsPayload) });
      }
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders mission summary, verdicts, files, verification, and model route', async () => {
    render(<CouncilDashboard />);

    await waitFor(() => {
      expect(screen.getAllByText('Improve login page without backend changes.').length).toBeGreaterThan(0);
    });

    expect(screen.getByText('YELLOW')).toBeInTheDocument();
    expect(await screen.findByText('Testing: Allow')).toBeInTheDocument();
    expect(screen.getByText('Security: Allow With Approval')).toBeInTheDocument();
    expect(screen.getByText('frontend/src/pages/Login.jsx')).toBeInTheDocument();
    expect(screen.getByText('Passed')).toBeInTheDocument();
    expect(screen.getByText('ollama')).toBeInTheDocument();
    expect(screen.getByText(/YELLOW write needs King decision/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Approve Council mission' }));

    await waitFor(() => {
      expect(screen.getByText('Approved by King')).toBeInTheDocument();
    });
    const approveCall = fetchMock.mock.calls.find(([url]) => String(url).includes('/api/v1/council/approve'));
    expect(JSON.parse(String(approveCall?.[1]?.body))).toMatchObject({
      missionId: 'mission-ui-1',
      requestId: 'approval-ui-1',
    });
  });
});
