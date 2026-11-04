import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MissionControlPanel from './MissionControlPanel';

const mocks = vi.hoisted(() => ({
  useMirrorStore: vi.fn(),
  useTabStore: vi.fn(),
  useResource: vi.fn(),
  selectMission: vi.fn(),
  parseCouncilMissions: vi.fn(),
}));

vi.mock('../superbrain/lib/mirrorStore', () => ({ useMirrorStore: mocks.useMirrorStore }));
vi.mock('../livingMirror/contracts', () => ({ parseCouncilMissions: mocks.parseCouncilMissions }));
vi.mock('../livingMirror/resource', () => ({ useResource: mocks.useResource }));
vi.mock('../livingMirror/ResourceNotice', () => ({
  ResourceNotice: ({ empty }) => <div>{empty}</div>,
}));
vi.mock('../livingMirror/MissionInspector', () => ({
  MissionInspector: ({ id }) => <div>Inspector for {id}</div>,
}));
vi.mock('../superbrain/lib/tabStore', () => ({
  useTabStore: mocks.useTabStore,
  selectMission: mocks.selectMission,
}));

describe('MissionControlPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.useMirrorStore.mockReturnValue({ activeMissions: [] });
    mocks.useTabStore.mockReturnValue({ selectedMissionId: null });
    mocks.useResource.mockReturnValue({ data: null });
  });

  it('requests Council reports and identifies an empty response', () => {
    render(<MissionControlPanel />);

    const [url, parser, isEmpty] = mocks.useResource.mock.calls[0];
    expect(url).toBe('/api/v1/council/missions?limit=100');
    expect(parser).toBe(mocks.parseCouncilMissions);
    expect(isEmpty({ missions: [] })).toBe(true);
    expect(isEmpty({ missions: [{ missionId: 'one' }] })).toBe(false);
    expect(screen.getByText('No readable Council reports were returned.')).toBeTruthy();
  });

  it('shows reports and only lists unmatched active missions separately', () => {
    mocks.useMirrorStore.mockReturnValue({ activeMissions: ['one', 'live-only'] });
    mocks.useResource.mockReturnValue({
      data: {
        count: 3,
        missions: [{ missionId: 'one', mission: 'First mission', status: 'running' }],
      },
    });

    render(<MissionControlPanel />);

    expect(screen.getByText('1 of 3 readable reports')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'First mission' }).getAttribute('aria-expanded')).toBe('false');
    expect(screen.getByText('Report: running', { exact: false })).toBeTruthy();
    expect(screen.getAllByText('one')).toHaveLength(1);
    expect(screen.getByText('live-only')).toBeTruthy();
    expect(screen.getByText('Observed active mission; Council detail unavailable.')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'First mission' }));
    expect(mocks.selectMission).toHaveBeenCalledWith('one');
  });

  it('shows the selected mission inspector and deselects on another click', () => {
    mocks.useTabStore.mockReturnValue({ selectedMissionId: 'one' });
    mocks.useResource.mockReturnValue({
      data: {
        count: 1,
        missions: [{ missionId: 'one', mission: 'First mission', status: 'complete' }],
      },
    });

    render(<MissionControlPanel />);

    const button = screen.getByRole('button', { name: 'First mission' });
    expect(button.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('Inspector for one')).toBeTruthy();
    fireEvent.click(button);
    expect(mocks.selectMission).toHaveBeenCalledWith(null);
  });
});
