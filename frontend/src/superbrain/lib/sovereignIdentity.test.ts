import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  __resetSovereignIdentityForTests,
  enrollSovereign,
  getSovereignStatus,
  loginSovereign,
  refreshSovereignStatus,
  releaseSovereignSession,
} from './sovereignIdentity';

function jsonResponse(body: Record<string, unknown>, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe('sovereignIdentity adapter', () => {
  beforeEach(() => {
    __resetSovereignIdentityForTests();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('measures sovereign status from the real session endpoint', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(jsonResponse({ authenticated: true, operatorId: 'op-1' })),
    );

    const status = await refreshSovereignStatus();

    expect(status).toEqual({ sessionActive: true, operatorId: 'op-1', measured: 'measured' });
  });

  it('an anonymous session is measured as active but NOT sovereign', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(jsonResponse({ authenticated: true, operatorId: null })),
    );

    const status = await refreshSovereignStatus();

    expect(status.sessionActive).toBe(true);
    expect(status.operatorId).toBeNull();
  });

  it('a fetch failure reports unknown, never a fabricated anonymous state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new Error('offline')));

    const status = await refreshSovereignStatus();

    expect(status.measured).toBe('unknown');
    expect(getSovereignStatus().measured).toBe('unknown');
  });

  it('enroll passes the one-time material through and never stores it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(
        jsonResponse(
          {
            enrolled: true,
            operatorId: 'op-1',
            enrollmentCredential: 'cred-SECRET',
            recoveryCode: 'recovery-SECRET',
          },
          201,
        ),
      ),
    );

    const outcome = await enrollSovereign('Kumar');

    expect(outcome).toEqual({
      kind: 'enrolled',
      material: {
        operatorId: 'op-1',
        enrollmentCredential: 'cred-SECRET',
        recoveryCode: 'recovery-SECRET',
      },
    });
    // The module-level status store must never have captured the secret.
    expect(JSON.stringify(getSovereignStatus())).not.toContain('SECRET');
  });

  it('enroll 409 reports already_enrolled, not a generic failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(jsonResponse({ detail: 'already enrolled' }, 409)),
    );

    expect(await enrollSovereign('Kumar')).toEqual({ kind: 'already_enrolled' });
  });

  it('login 401 is narrated as invalid_credential, never success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(jsonResponse({ detail: 'invalid' }, 401)),
    );

    expect(await loginSovereign('wrong')).toEqual({ kind: 'invalid_credential' });
  });

  it('login success is only reported after the MEASURED status confirms the operator', async () => {
    const fetchMock = vi
      .fn()
      // POST /login says authenticated...
      .mockResolvedValueOnce(jsonResponse({ authenticated: true, operatorId: 'op-1' }))
      // ...and the measured refetch confirms it.
      .mockResolvedValueOnce(jsonResponse({ authenticated: true, operatorId: 'op-1' }));
    vi.stubGlobal('fetch', fetchMock);

    const outcome = await loginSovereign('cred');

    expect(outcome).toEqual({ kind: 'authenticated', operatorId: 'op-1' });
    expect(getSovereignStatus().operatorId).toBe('op-1');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('login is a failure when the measured session does NOT reflect the operator', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ authenticated: true, operatorId: 'op-1' }))
      // The refetch disagrees — cookie never landed.
      .mockResolvedValueOnce(jsonResponse({ authenticated: true, operatorId: null }));
    vi.stubGlobal('fetch', fetchMock);

    const outcome = await loginSovereign('cred');

    expect(outcome.kind).toBe('failed');
  });

  it('releasing the session refetches measured truth instead of assuming logout', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ ok: true }))
      .mockResolvedValueOnce(jsonResponse({ authenticated: false }));
    vi.stubGlobal('fetch', fetchMock);

    await releaseSovereignSession();

    expect(getSovereignStatus().sessionActive).toBe(false);
    expect(getSovereignStatus().operatorId).toBeNull();
  });
});
