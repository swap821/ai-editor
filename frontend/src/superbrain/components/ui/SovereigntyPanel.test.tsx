import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import SovereigntyPanel from './SovereigntyPanel';
import { __resetSovereignIdentityForTests } from '../../lib/sovereignIdentity';

function jsonResponse(body: Record<string, unknown>, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

/** Default: anonymous session (active, no operator). */
function stubAnonymousStatus(fetchMock: ReturnType<typeof vi.fn>): void {
  fetchMock.mockResolvedValue(jsonResponse({ authenticated: true, operatorId: null }));
}

describe('SovereigntyPanel — the bond ceremony', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    __resetSovereignIdentityForTests();
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('opens in the claim state for an anonymous session', async () => {
    stubAnonymousStatus(fetchMock);
    render(<SovereigntyPanel onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/no sovereign session is active/i)).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /claim sovereignty/i })).toBeDisabled();
  });

  it('opens in the bonded state when the measured session is sovereign', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ authenticated: true, operatorId: 'op-kumar' }));
    render(<SovereigntyPanel onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/the bond holds/i)).toBeInTheDocument();
    });
    expect(screen.getByText('op-kumar')).toBeInTheDocument();
  });

  it('LOCKOUT-CRITICAL: the reveal state hides the close control, ignores Escape, and gates SEAL behind acknowledgment', async () => {
    const onClose = vi.fn();
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).endsWith('/auth/enroll')) {
        return Promise.resolve(
          jsonResponse(
            {
              enrolled: true,
              operatorId: 'op-1',
              enrollmentCredential: 'cred-ONCE',
              recoveryCode: 'recovery-ONCE',
            },
            201,
          ),
        );
      }
      if (init?.method === 'GET' || init === undefined) {
        return Promise.resolve(jsonResponse({ authenticated: true, operatorId: null }));
      }
      return Promise.resolve(jsonResponse({ authenticated: true, operatorId: null }));
    });

    render(<SovereigntyPanel onClose={onClose} />);
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/display name/i)).toBeInTheDocument();
    });

    // Claim.
    fireEvent.change(screen.getByPlaceholderText(/display name/i), {
      target: { value: 'Kumar' },
    });
    fireEvent.click(screen.getByRole('button', { name: /claim sovereignty/i }));

    // The one-time material is revealed.
    await waitFor(() => {
      expect(screen.getByText('cred-ONCE')).toBeInTheDocument();
    });
    expect(screen.getByText('recovery-ONCE')).toBeInTheDocument();

    // No close control exists in the reveal state.
    expect(screen.queryByRole('button', { name: /close/i })).toBeNull();

    // Escape does NOT dismiss it.
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByText('cred-ONCE')).toBeInTheDocument();

    // SEAL is disarmed until the acknowledgment is checked.
    const seal = screen.getByRole('button', { name: /seal the bond/i });
    expect(seal).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    expect(seal).not.toBeDisabled();
  });

  it('a failed seal keeps the one-time material visible and narrates the failure', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const path = String(url);
      if (path.endsWith('/auth/enroll')) {
        return Promise.resolve(
          jsonResponse(
            {
              enrolled: true,
              operatorId: 'op-1',
              enrollmentCredential: 'cred-ONCE',
              recoveryCode: 'recovery-ONCE',
            },
            201,
          ),
        );
      }
      if (path.endsWith('/auth/login')) {
        return Promise.resolve(jsonResponse({ detail: 'nope' }, 401));
      }
      if (init?.method === 'GET' || init === undefined) {
        return Promise.resolve(jsonResponse({ authenticated: true, operatorId: null }));
      }
      return Promise.resolve(jsonResponse({}));
    });

    render(<SovereigntyPanel onClose={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/display name/i)).toBeInTheDocument();
    });
    fireEvent.change(screen.getByPlaceholderText(/display name/i), {
      target: { value: 'Kumar' },
    });
    fireEvent.click(screen.getByRole('button', { name: /claim sovereignty/i }));
    await waitFor(() => {
      expect(screen.getByText('cred-ONCE')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: /seal the bond/i }));

    await waitFor(() => {
      expect(screen.getByText(/could not be sealed/i)).toBeInTheDocument();
    });
    // The material MUST survive a failed seal — discarding it here is lockout.
    expect(screen.getByText('cred-ONCE')).toBeInTheDocument();
    expect(screen.getByText('recovery-ONCE')).toBeInTheDocument();
  });

  it('enroll 409 flips honestly to the credential prompt', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).endsWith('/auth/enroll')) {
        return Promise.resolve(jsonResponse({ detail: 'already' }, 409));
      }
      if (init?.method === 'GET' || init === undefined) {
        return Promise.resolve(jsonResponse({ authenticated: true, operatorId: null }));
      }
      return Promise.resolve(jsonResponse({}));
    });

    render(<SovereigntyPanel onClose={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/display name/i)).toBeInTheDocument();
    });
    fireEvent.change(screen.getByPlaceholderText(/display name/i), {
      target: { value: 'Kumar' },
    });
    fireEvent.click(screen.getByRole('button', { name: /claim sovereignty/i }));

    await waitFor(() => {
      expect(screen.getByText(/a sovereign is already bound/i)).toBeInTheDocument();
    });
    expect(screen.getByPlaceholderText(/enrollment credential/i)).toBeInTheDocument();
  });

  it('an invalid login credential narrates failure, never success', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).endsWith('/auth/login')) {
        return Promise.resolve(jsonResponse({ detail: 'invalid' }, 401));
      }
      if (init?.method === 'GET' || init === undefined) {
        return Promise.resolve(jsonResponse({ authenticated: true, operatorId: null }));
      }
      return Promise.resolve(jsonResponse({}));
    });

    render(<SovereigntyPanel onClose={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /already hold the credential/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /already hold the credential/i }));
    fireEvent.change(screen.getByPlaceholderText(/enrollment credential/i), {
      target: { value: 'wrong' },
    });
    fireEvent.click(screen.getByRole('button', { name: /present credential/i }));

    await waitFor(() => {
      expect(screen.getByText(/not recognized/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/the bond holds/i)).toBeNull();
  });
});
