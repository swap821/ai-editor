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
      if (options?.method === 'POST' && url.includes('/api/v1/council/missions')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ missionId: 'mission-new', status: 'deliberating' }),
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
    vi.restoreAllMocks();
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

  it('renders verification strength and flags a weak below-floor approval', async () => {
    const weakMission = {
      missionId: 'mission-weak',
      mission: 'Touch the login copy.',
      status: 'completed',
      recommendation: 'approve',
      risk: 'YELLOW',
      approvalNeeded: true,
      verificationStrength: 'WEAK',
      verificationMeetsFloor: false,
      verificationBelowFloorWarning:
        'verification strength WEAK is below the STRONG floor — review before approving',
      pendingApprovals: [{ requestId: 'a-weak', action: 'write_file', reason: 'YELLOW write needs King decision' }],
      kingDecision: null,
    };
    const weakDetail = {
      missionId: 'mission-weak',
      report: {
        mission_id: 'mission-weak',
        mission: 'Touch the login copy.',
        status: 'completed',
        recommendation: 'approve',
        risk: 'YELLOW',
        files: ['frontend/src/pages/Login.jsx'],
        verification_result: {
          commands: [{ command: ['echo', 'done'], returncode: 0 }],
          strength: 'WEAK',
          meets_floor: false,
          below_floor_warning:
            'verification strength WEAK is below the STRONG floor — review before approving',
        },
        approval_needed: true,
        human_summary: '⚠ Weak verification (WEAK < STRONG floor). Worker completed the mission.',
      },
      ledger: { blocked_attempts: [], verification: { commands: [{ command: ['echo', 'done'], returncode: 0 }] } },
      pendingApprovals: [{ requestId: 'a-weak', action: 'write_file', reason: 'YELLOW write needs King decision' }],
      kingDecision: null,
    };
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/api/v1/council/missions/mission-weak')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(weakDetail) });
      }
      if (url.includes('/api/v1/council/missions')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ missions: [weakMission], count: 1 }) });
      }
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
    });

    render(<CouncilDashboard />);

    // Strength rendered as anatomy (not a Passed/Failed cell).
    expect(await screen.findByText('WEAK')).toBeInTheDocument();
    // The caution is surfaced at the decision point.
    const caution = await screen.findByRole('alert');
    expect(caution).toHaveTextContent(/review before approving/i);
  });

  it('restores a mission through the rollback recovery action', async () => {
    const rollbackId = '1234567890abcdef1234567890abcdef12345678';
    const rollbackMission = {
      ...missionsPayload.missions[0],
      rollbackAvailable: true,
      rollbackId,
    };
    const rollbackDetail = {
      ...detailPayload,
      report: {
        ...detailPayload.report,
        rollback_available: true,
        rollback_id: rollbackId,
      },
      summary: rollbackMission,
    };
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    fetchMock.mockImplementation((url: string, options?: RequestInit) => {
      if (options?.method === 'POST' && url.includes('/api/v1/council/missions/mission-ui-1/rollback')) {
        const body = JSON.parse(String(options.body || '{}'));
        if (!body.approvalToken) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
              requiresApproval: true,
              approvalToken: 'rollback-token',
              snapshotId: rollbackId,
              executed: false,
            }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            requiresApproval: false,
            missionId: 'mission-ui-1',
            snapshotId: rollbackId,
            executed: true,
            result: { restored: true },
            report: {
              ...rollbackDetail.report,
              status: 'rolled_back',
              recommendation: 'observe',
              rollback_available: false,
            },
          }),
        });
      }
      if (url.includes('/api/v1/council/missions/mission-ui-1')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(rollbackDetail) });
      }
      if (url.includes('/api/v1/council/missions')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ missions: [rollbackMission], count: 1 }) });
      }
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
    });

    render(<CouncilDashboard />);

    const rollback = await screen.findByRole('button', { name: 'Rollback Council mission' });
    fireEvent.click(rollback);

    await waitFor(() => {
      const rollbackCalls = fetchMock.mock.calls.filter(([url]) => String(url).includes('/rollback'));
      expect(rollbackCalls).toHaveLength(2);
      expect(JSON.parse(String(rollbackCalls[0][1]?.body))).toMatchObject({ snapshotId: rollbackId });
      expect(JSON.parse(String(rollbackCalls[1][1]?.body))).toMatchObject({
        snapshotId: rollbackId,
        approvalToken: 'rollback-token',
      });
    });
    expect(confirmSpy).toHaveBeenCalled();
    expect(await screen.findByText('Restored')).toBeInTheDocument();
  });

  it('originates a mission from the form', async () => {
    render(<CouncilDashboard />);

    await waitFor(() => {
      expect(screen.getByLabelText('Mission goal')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText('Mission goal'), {
      target: { value: 'add aria labels to login' },
    });
    fireEvent.change(screen.getByLabelText('Allowed files'), {
      target: { value: 'frontend/src/pages/Login.jsx' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send to Council' }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, options]) =>
          (options as RequestInit | undefined)?.method === 'POST' &&
          String(url).includes('/api/v1/council/missions'),
      );
      expect(call).toBeTruthy();
      expect(JSON.parse(String((call?.[1] as RequestInit)?.body))).toMatchObject({
        goal: 'add aria labels to login',
        allowedFiles: ['frontend/src/pages/Login.jsx'],
      });
    });
  });

  it('keeps Mission goal and Allowed files as independent fields while typing keystroke-by-keystroke', async () => {
    render(<CouncilDashboard />);

    await waitFor(() => {
      expect(screen.getByLabelText('Mission goal')).toBeInTheDocument();
    });

    const goalField = screen.getByLabelText('Mission goal') as HTMLTextAreaElement;
    const filesField = screen.getByLabelText('Allowed files') as HTMLInputElement;

    // Simulate real sequential typing (one fireEvent.change per keystroke,
    // reading back the field's own current DOM value each time) rather than
    // a single fireEvent.change with the whole final string — this is what
    // actually exercises a per-keystroke re-render and would surface a
    // handler wired to the wrong setter.
    const type = (el: HTMLInputElement | HTMLTextAreaElement, text: string) => {
      for (const char of text) {
        fireEvent.change(el, { target: { value: el.value + char } });
      }
    };

    // 1. Click + type into Mission goal (matches the reported repro).
    fireEvent.click(goalField);
    type(goalField, 'add a docstring to a training_ground helper function');

    // 2. Click + type into Allowed files.
    fireEvent.click(filesField);
    type(filesField, 'training_ground/test_calculator.py');

    // Allowed files must contain ONLY what was typed into it, and Mission
    // goal must be untouched by the second round of typing — each field's
    // onChange must update only its own state.
    expect(filesField.value).toBe('training_ground/test_calculator.py');
    expect(goalField.value).toBe('add a docstring to a training_ground helper function');
  });
});
