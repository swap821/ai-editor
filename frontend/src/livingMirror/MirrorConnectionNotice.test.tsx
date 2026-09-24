import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useMirrorStore } from '../superbrain/lib/mirrorStore';
import { MirrorConnectionNotice } from './MirrorConnectionNotice';

const { startMirrorClient, stopMirrorClient } = vi.hoisted(() => ({
  startMirrorClient: vi.fn(),
  stopMirrorClient: vi.fn(),
}));

vi.mock('../superbrain/lib/aiosMirror', () => ({ startMirrorClient, stopMirrorClient }));

beforeEach(() => {
  useMirrorStore.setState({
    status: 'offline',
    connection: 'disconnected',
    projection: 'unknown',
    snapshotReceivedAt: null,
    lastEventId: null,
    compatibility: null,
    approvalRequired: false,
  });
  startMirrorClient.mockClear();
  stopMirrorClient.mockClear();
});

describe('MirrorConnectionNotice', () => {
  it('shows a newcomer a truthful recovery action', () => {
    render(<MirrorConnectionNotice />);

    expect(screen.getByRole('status')).toHaveTextContent('GAGOS is offline');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(stopMirrorClient).toHaveBeenCalledTimes(1);
    expect(startMirrorClient).toHaveBeenCalledTimes(1);
  });

  it('exposes cursor and continuity evidence only in Expert mode', () => {
    useMirrorStore.setState({
      status: 'stale',
      connection: 'connected',
      projection: 'snapshot',
      snapshotReceivedAt: '2026-09-21T12:00:00.000Z',
      lastEventId: 18,
    });

    render(<MirrorConnectionNotice experienceMode="expert" />);

    expect(screen.getByText('Transport connected', { exact: true })).toBeInTheDocument();
    expect(screen.getByText(/cursor 18/i)).toBeInTheDocument();
    expect(screen.getByText(/continuity is not yet confirmed/i)).toBeInTheDocument();
  });

  it('does not expose the authority launcher in Guided mode', () => {
    useMirrorStore.setState({ approvalRequired: true });
    render(<MirrorConnectionNotice experienceMode="beginner" onOpenAuthority={vi.fn()} />);

    expect(screen.queryByRole('button', { name: 'Review permission request' })).not.toBeInTheDocument();
  });
});
