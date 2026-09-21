import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { EmergencyControl } from './EmergencyControl';

const state = (overrides: Record<string, unknown> = {}) => ({
  engaged: false,
  generation: 4,
  operatorId: null,
  authenticationEventId: null,
  reason: '',
  actions: {},
  failure: null,
  engagedAt: null,
  clearedAt: null,
  ...overrides,
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('EmergencyControl', () => {
  it('keeps an engage request pending until a fresh server read confirms the latch', async () => {
    let liveState = state();
    let resolveEngage: ((response: Response) => void) | undefined;
    const fetchMock = vi.fn((url: string, options?: RequestInit) => {
      if (!options?.method) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(liveState) } as Response);
      }
      if (url.endsWith('/emergency-stop/engage')) {
        return new Promise<Response>((resolve) => { resolveEngage = resolve; });
      }
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) } as Response);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<EmergencyControl />);
    fireEvent.click(screen.getByRole('button', { name: 'Inspect emergency stop' }));
    expect(await screen.findByText('Confirmed latch disengaged.')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'maintenance' } });
    fireEvent.click(screen.getByRole('button', { name: 'Emergency stop' }));
    expect(await screen.findByRole('button', { name: 'Stop request pending' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Stop latch engaged' })).not.toBeInTheDocument();

    liveState = state({
      engaged: true,
      generation: 5,
      operatorId: 'operator-1',
      authenticationEventId: 'auth-event-5',
      reason: 'maintenance',
      actions: {
        revoke_capabilities: 'completed',
        cancel_queued_missions: 'completed',
        kill_active_workers: 'completed',
        disable_autonomy: 'completed',
        preserve_evidence: 'completed',
      },
      engagedAt: '2026-09-15T12:00:00Z',
    });
    resolveEngage?.({ ok: true, status: 200, json: () => Promise.resolve(liveState) } as Response);

    await waitFor(() => expect(screen.getByRole('button', { name: 'Stop latch engaged' })).toBeInTheDocument());
    expect(screen.getByText('Operator')).toBeInTheDocument();
    expect(screen.getByText('operator-1')).toBeInTheDocument();
  });

  it('surfaces partial hook completion and controller failure as recorded state', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(state({
        engaged: true,
        generation: 9,
        operatorId: 'operator-2',
        authenticationEventId: 'auth-event-9',
        failure: 'worker termination receipt unavailable',
        actions: { revoke_capabilities: 'completed', kill_active_workers: 'failed:timeout' },
      })),
    } as Response)));

    render(<EmergencyControl />);
    fireEvent.click(screen.getByRole('button', { name: 'Inspect emergency stop' }));

    expect(await screen.findByText('Confirmed latch engaged.')).toBeInTheDocument();
    expect(screen.getByText('Stopping is only partially confirmed; inspect the recorded hooks.')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('worker termination receipt unavailable');
    expect(screen.getByText('auth-event-9')).toBeInTheDocument();
  });
});
