import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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

afterEach(() => {
  vi.unstubAllGlobals();
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

  it('keeps the full technical receipt visible by default on desktop', () => {
    useMirrorStore.setState({
      status: 'stale',
      connection: 'connected',
      projection: 'snapshot',
      snapshotReceivedAt: '2026-09-21T12:00:00.000Z',
      lastEventId: 18,
    });

    render(<MirrorConnectionNotice experienceMode="expert" />);

    expect(screen.getByText(/cursor 18/i)).toBeVisible();
  });

  it('keeps phone diagnostics reachable without spending the resting status band', () => {
    vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
      matches: query === '(max-width: 767px)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
    useMirrorStore.setState({
      status: 'stale',
      connection: 'connected',
      projection: 'stale',
      snapshotReceivedAt: '2026-09-21T12:00:00.000Z',
      lastEventId: 18,
    });

    render(<MirrorConnectionNotice experienceMode="expert" />);

    expect(screen.getByRole('status')).toHaveTextContent('Transport reconnecting');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
    expect(screen.getByText(/the displayed projection is stale/i)).not.toBeVisible();
    expect(screen.getByText(/cursor 18/i)).not.toBeVisible();

    fireEvent.click(screen.getByText('More connection details'));

    expect(screen.getByText(/cursor 18/i)).toBeVisible();
    expect(screen.getByText(/the displayed projection is stale/i)).toBeVisible();
  });

  it('restores the desktop receipt when the viewport leaves the compact breakpoint', () => {
    let compact = true;
    const listeners = new Set<(event: MediaQueryListEvent) => void>();
    const media = {
      get matches() { return compact; },
      addEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => listeners.add(listener),
      removeEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => listeners.delete(listener),
    };
    vi.stubGlobal('matchMedia', vi.fn(() => media));
    useMirrorStore.setState({
      status: 'stale',
      connection: 'connected',
      projection: 'stale',
      snapshotReceivedAt: '2026-09-21T12:00:00.000Z',
      lastEventId: 18,
    });

    render(<MirrorConnectionNotice experienceMode="expert" />);
    expect(screen.getByText(/cursor 18/i)).not.toBeVisible();

    act(() => {
      compact = false;
      listeners.forEach((listener) => listener({ matches: false } as MediaQueryListEvent));
    });
    expect(screen.getByText(/cursor 18/i)).toBeVisible();

    act(() => {
      compact = true;
      listeners.forEach((listener) => listener({ matches: true } as MediaQueryListEvent));
    });
    expect(screen.getByText(/cursor 18/i)).not.toBeVisible();
  });

  it('does not expose the authority launcher in Guided mode', () => {
    useMirrorStore.setState({ approvalRequired: true });
    render(<MirrorConnectionNotice experienceMode="beginner" onOpenAuthority={vi.fn()} />);

    expect(screen.queryByRole('button', { name: 'Review permission request' })).not.toBeInTheDocument();
  });
});
