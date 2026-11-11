import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MissionInspector } from './MissionInspector';

const mocks = vi.hoisted(() => ({
  useResource: vi.fn(),
  readResource: vi.fn(),
  sendGuardedCommand: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock('./resource', () => ({
  useResource: mocks.useResource,
  readResource: mocks.readResource,
}));

vi.mock('./commands', () => ({
  sendGuardedCommand: mocks.sendGuardedCommand,
}));

vi.mock('./ResourceNotice', () => ({
  ResourceNotice: ({ empty }: { empty: string }) => <div data-testid="notice">{empty}</div>,
}));

function makeDetail() {
  return {
    missionId: 'm/1',
    missionAuthority: { contractDigest: 'digest-1', state: 'authorised', operatorId: 'op-7' },
    summary: {
      mission: 'Ship the parser',
      status: 'running',
      risk: 'medium',
      approvalNeeded: true,
      verificationPassed: null,
      verificationStrength: null,
    },
    pendingApprovals: [{ requestId: 'req-1', workerId: 'w-9', action: { kind: 'write' }, reason: 'Needs write access' }],
    report: {},
    ledger: null,
    kingDecision: null,
  };
}

function available(data: unknown) {
  return { status: 'available', data, refresh: mocks.refresh };
}

describe('MissionInspector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.useResource.mockReturnValue(available(makeDetail()));
    mocks.readResource.mockResolvedValue(makeDetail());
  });

  afterEach(() => {
    cleanup();
  });

  it('requests the mission with an encoded id and shows the notice when no detail is loaded', () => {
    mocks.useResource.mockReturnValue({ status: 'loading', data: null, refresh: mocks.refresh });
    render(<MissionInspector id="m/1" />);

    const path = mocks.useResource.mock.calls[0][0] as string;
    expect(path.endsWith('m%2F1')).toBe(true);
    expect(screen.getByTestId('notice').textContent).toBe('Mission detail unavailable.');
    expect(screen.queryByRole('heading', { name: 'Ship the parser' })).toBeNull();
  });

  it('renders mission summary and authority details', () => {
    render(<MissionInspector id="m/1" />);

    expect(screen.getByLabelText('Inspect mission m/1')).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Ship the parser' })).toBeTruthy();
    expect(screen.getByText('digest-1')).toBeTruthy();
    expect(screen.getByText('op-7')).toBeTruthy();
    expect(screen.getByText('running')).toBeTruthy();
    expect(screen.getByText('No bound worker observations received in this browser session.')).toBeTruthy();
  });

  it('keeps decision buttons disabled until the review checkbox is ticked', () => {
    render(<MissionInspector id="m/1" />);

    const approve = screen.getByRole('button', { name: 'Approve this request' }) as HTMLButtonElement;
    const reject = screen.getByRole('button', { name: 'Reject this request' }) as HTMLButtonElement;
    expect(approve.disabled).toBe(true);
    expect(reject.disabled).toBe(true);

    fireEvent.click(screen.getByRole('checkbox'));
    expect(approve.disabled).toBe(false);
    expect(reject.disabled).toBe(false);
  });

  it('submits a reviewed approval with the current contract digest and refreshes', async () => {
    mocks.sendGuardedCommand.mockResolvedValue({
      status: 'accepted',
      message: 'ignored',
      data: { execution: 'scheduled' },
    });
    render(<MissionInspector id="m/1" />);

    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Approve this request' }));

    const status = await screen.findByText(
      'Decision accepted; execution scheduled. Verification and project effects require their own records.',
    );
    expect(status.getAttribute('role')).toBe('status');
    expect(mocks.sendGuardedCommand).toHaveBeenCalledTimes(1);
    expect(mocks.sendGuardedCommand).toHaveBeenCalledWith(expect.any(String), {
      missionId: 'm/1',
      contractDigest: 'digest-1',
      reason: 'Approved after reviewing the mission authority surface',
    });
    expect(mocks.refresh).toHaveBeenCalled();
  });

  it('does not submit when the request changed after review', async () => {
    const changed = makeDetail();
    changed.missionAuthority.contractDigest = 'digest-2';
    mocks.readResource.mockResolvedValue(changed);
    render(<MissionInspector id="m/1" />);

    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Reject this request' }));

    expect(
      await screen.findByText('The request changed. Review the refreshed contract and scope before deciding.'),
    ).toBeTruthy();
    expect(mocks.sendGuardedCommand).not.toHaveBeenCalled();
  });
});
