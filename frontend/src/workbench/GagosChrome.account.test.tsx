import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import GagosChrome from './GagosChrome';

interface SessionReply {
  authenticated: boolean;
  cookieBased: boolean;
  operatorId: string | null;
  csrfToken: string | null;
}

const SIGNED_OUT: SessionReply = {
  authenticated: false,
  cookieBased: true,
  operatorId: null,
  csrfToken: null,
};

const LINKED: SessionReply = {
  authenticated: true,
  cookieBased: true,
  operatorId: 'operator-1',
  csrfToken: 'csrf-operator-1',
};

const SIGN_IN_NAME = 'Sign in or claim the account. Open the account panel to sign in.';

function stubSession(session: SessionReply) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      const body = url.includes('/session') ? session : {};
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }),
  );
}

describe('GagosChrome account pill', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('reads "Sign in" in guided mode when no operator is linked', async () => {
    stubSession(SIGNED_OUT);
    render(<GagosChrome experienceMode="beginner" />);
    const pill = await screen.findByRole('button', { name: SIGN_IN_NAME });
    expect(pill.textContent).toContain('Sign in');
  });

  it('reads "Sign in" in expert mode when no operator is linked', async () => {
    stubSession(SIGNED_OUT);
    render(<GagosChrome experienceMode="expert" integrated />);
    const pill = await screen.findByRole('button', { name: SIGN_IN_NAME });
    expect(pill.textContent).toContain('Sign in');
  });

  it('opens the account panel from the sign-in pill', async () => {
    stubSession(SIGNED_OUT);
    render(<GagosChrome experienceMode="beginner" />);
    const pill = await screen.findByRole('button', { name: SIGN_IN_NAME });
    fireEvent.click(pill);
    expect(await screen.findByRole('dialog', { name: 'Account not linked' })).toBeTruthy();
  });

  it('keeps the linked wording when an operator is linked', async () => {
    stubSession(LINKED);
    render(<GagosChrome experienceMode="beginner" />);
    const pill = await screen.findByRole('button', {
      name: 'Account identity status. Open the account panel.',
    });
    expect(pill.textContent).toContain('account linked');
    expect(screen.queryByRole('button', { name: SIGN_IN_NAME })).toBeNull();
  });
});
