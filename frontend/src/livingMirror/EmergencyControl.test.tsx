import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { EmergencyControl } from './EmergencyControl';
import { getEmergencyStopPresentation, setEmergencyStopPresentation } from './emergencyStopPresentation';
import { readLivingMirrorStylesheet } from '../test/livingMirrorStylesheet';

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
  document.querySelectorAll('style[data-emergency-layout-test]').forEach((style) => style.remove());
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  setEmergencyStopPresentation('unknown');
});

describe('EmergencyControl', () => {
  it.each([
    { viewportHeight: 568, available: '270px' },
    { viewportHeight: 450, available: '152px' },
  ])('bounds details below their actual opening in a $viewportHeight px visible viewport', async ({ viewportHeight, available }) => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(state()) } as Response)));
    vi.stubGlobal('innerHeight', 568);
    const viewport = Object.assign(new EventTarget(), { height: viewportHeight, offsetTop: 0 });
    vi.stubGlobal('visualViewport', viewport);
    let panelTop = 298;
    const originalBounds = HTMLElement.prototype.getBoundingClientRect;
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      if (this.classList.contains('lm-stop__detail')) return { top: panelTop, bottom: panelTop + 400, height: 400 } as DOMRect;
      if (this.classList.contains('lm-app')) return { top: 182, bottom: 568, height: 386 } as DOMRect;
      return originalBounds.call(this);
    });
    render(<div className="lm-app"><div className="lm-shell"><header className="lm-header"><EmergencyControl guided /></header></div></div>);
    fireEvent.click(screen.getByRole('button', { name: 'Inspect emergency stop' }));
    const panel = await screen.findByRole('region', { name: 'Stop state and outcomes' });
    await waitFor(() => expect(panel.style.getPropertyValue('--lm-stop-details-available-height')).toBe(available));
    panelTop = 318;
    viewport.dispatchEvent(new Event('scroll'));
    await waitFor(() => expect(panel.style.getPropertyValue('--lm-stop-details-available-height')).toBe(viewportHeight === 568 ? '250px' : '132px'));
    fireEvent.click(screen.getByRole('button', { name: 'Close details' }));
    expect(panel.style.getPropertyValue('--lm-stop-details-available-height')).toBe('');
  });

  it.each([false, true])('anchors wide details to the full header, not the narrower Stop buttons (guided=%s)', async (guided) => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true, json: () => Promise.resolve(state()),
    } as Response)));
    const stylesheet = document.createElement('style');
    stylesheet.dataset.emergencyLayoutTest = 'true';
    stylesheet.textContent = readLivingMirrorStylesheet();
    document.head.append(stylesheet);
    render(<div className="lm-app"><div className="lm-shell" data-experience-mode={guided ? 'beginner' : 'expert'}>
      <header className="lm-header"><EmergencyControl guided={guided} /></header>
    </div></div>);
    fireEvent.click(screen.getByRole('button', { name: 'Inspect emergency stop' }));
    const panel = await screen.findByRole('region', { name: 'Stop state and outcomes' });
    // JSDOM cannot measure pixels. This checks the real CSS containing-block
    // contract; the actual viewport/Close bounds are qualified in the browser.
    let anchor = panel.parentElement;
    while (anchor && !['absolute', 'relative', 'fixed', 'sticky'].includes(getComputedStyle(anchor).position)) {
      anchor = anchor.parentElement;
    }
    expect(anchor).toBe(document.querySelector('.lm-header'));
  });

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
    await waitFor(() => expect(getEmergencyStopPresentation()).toBe('clear'));

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
    // The fetched DOM snapshot and the external presentation store are
    // published by separate React commits. Wait for the store itself so this
    // regression proves the action-bearing shell sees the measured latch,
    // rather than depending on passive-effect scheduling.
    await waitFor(() => expect(getEmergencyStopPresentation()).toBe('engaged'));
    expect(screen.getByText('Stopping is only partially confirmed; inspect the recorded hooks.')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('worker termination receipt unavailable');
    expect(screen.getByText('auth-event-9')).toBeInTheDocument();
  });

  it('keeps raw stop hook and operator identities out of Guided details', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(state({
        engaged: true,
        operatorId: 'operator-guided-hidden',
        authenticationEventId: 'auth-guided-hidden',
        actions: {
          revoke_capabilities: 'completed',
          kill_active_workers: 'completed',
        },
      })),
    } as Response)));

    render(<EmergencyControl guided />);
    fireEvent.click(screen.getByRole('button', { name: 'Inspect emergency stop' }));

    expect(await screen.findByText('Confirmed stop is on.')).toBeInTheDocument();
    expect(screen.getByText('Some stop actions are still being confirmed.')).toBeInTheDocument();
    expect(screen.queryByText('The stop actions recorded by GAGOS are complete.')).not.toBeInTheDocument();
    expect(screen.getByText('Expert/Mirror can show the recorded stop details.')).toBeInTheDocument();
    expect(screen.queryByText('operator-guided-hidden')).not.toBeInTheDocument();
    expect(screen.queryByText('auth-guided-hidden')).not.toBeInTheDocument();
    expect(screen.queryByText('revoke capabilities')).not.toBeInTheDocument();
    expect(screen.queryByText('kill active workers')).not.toBeInTheDocument();
  });

  it('uses human stop language throughout Guided controls', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(state({ engaged: true, actions: { preserve_evidence: 'completed' } })),
    } as Response)));

    render(<EmergencyControl guided />);
    expect(await screen.findByRole('button', { name: 'Stop is on' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Inspect emergency stop' }));

    expect(await screen.findByText('Confirmed stop is on.')).toBeInTheDocument();
    expect(screen.getByLabelText('Reason')).toHaveValue('I asked GAGOS to stop');
    expect(screen.getByRole('button', { name: 'Request resume' })).toBeInTheDocument();
    expect(screen.getByText('Resuming requires a fresh security check and does not restart work.')).toBeInTheDocument();
    expect(screen.queryByText(/latch|privileged authentication|operator requested/i)).not.toBeInTheDocument();
  });

  it('updates the untouched default reason when the experience mode changes', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(state({ engaged: true })),
    } as Response)));

    const view = render(<EmergencyControl />);
    fireEvent.click(screen.getByRole('button', { name: 'Inspect emergency stop' }));
    expect(await screen.findByDisplayValue('Operator requested emergency stop')).toBeInTheDocument();

    view.rerender(<EmergencyControl guided />);

    expect(screen.getByLabelText('Reason')).toHaveValue('I asked GAGOS to stop');
  });

  it('restores focus to the details trigger when the disclosure closes', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(state()),
    } as Response)));

    render(<EmergencyControl guided />);
    const details = screen.getByRole('button', { name: 'Inspect emergency stop' });
    fireEvent.click(details);
    expect(await screen.findByText('Confirmed stop is off.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Close details' }));
    await waitFor(() => expect(details).toHaveFocus());
  });
});
