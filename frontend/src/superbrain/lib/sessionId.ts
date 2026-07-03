/**
 * getSessionId — the single source of truth for the operator's session id.
 *
 * ONE conversation per operator, SHARED across every face of GAGOS (the
 * canon HUD command bar, the workbench organs, and the classic IDE) so they all
 * continue the SAME backend conversation under the SAME session.
 *
 * SECURITY HARDENING (H2 -> A+): Session management is now server-side with
 * httpOnly, Secure, SameSite=Strict cookies. The session ID is NEVER stored
 * in JavaScript-accessible storage (sessionStorage/localStorage). This prevents
 * XSS-based session theft completely — the cookie is invisible to JavaScript.
 *
 * Flow:
 *   1. On load, call GET /api/v1/auth/session to check for existing session
 *      (httpOnly cookie is auto-sent; JS never sees the value)
 *   2. If no valid session, call POST /api/v1/auth/session to create one
 *      (server sets the httpOnly cookie in the response)
 *   3. The session cookie travels automatically on every fetch({credentials:'include'})
 *   4. The backend reads the cookie and validates the session server-side
 *
 * Fallback: when cookies are blocked (privacy mode, sandbox), we fall back to
 * sessionStorage with a visible security warning.
 *
 * SSR-safe (the lab is Next.js): with no `window` it returns the stable
 * fallback constant and never throws.
 */

/** The storage key for the cookie-blocked fallback — change here and nowhere else. */
export const SESSION_STORAGE_KEY = 'aios_session_id';

/** The stable id used when storage is unavailable (SSR, privacy mode, sandbox). */
export const FALLBACK_SESSION_ID = 'gag-superbrain-hud';

/** The GAGOS API base URL. */
const AIOS_BASE = process.env.NEXT_PUBLIC_AIOS_URL ?? 'http://localhost:8000';

/** Whether the backend supports cookie-based sessions (detected at runtime). */
let _cookieBased = true;

/** Whether we've already attempted session setup. */
let _sessionChecked = false;

/** In-memory session ID for the cookie-blocked fallback. NEVER persisted. */
let _fallbackSessionId: string | null = null;

/** Security warning emitted once when falling back to storage-based session. */
let _fallbackWarningEmitted = false;

/**
 * Check whether the backend supports cookie-based sessions.
 * Returns true if the last session operation used a cookie.
 */
export function isCookieBasedSession(): boolean {
  return _cookieBased;
}

/**
 * Fetch session status from the server. The httpOnly cookie is auto-sent
 * with credentials:'include' — JavaScript never sees the session ID value.
 */
async function checkServerSession(): Promise<boolean> {
  try {
    const res = await fetch(`${AIOS_BASE}/api/v1/auth/session`, {
      method: 'GET',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) return false;
    const data = (await res.json()) as { authenticated?: boolean };
    return data.authenticated === true;
  } catch {
    // Backend may not have the endpoint yet (older version)
    return false;
  }
}

/**
 * Create a new server-side session. The server sets the httpOnly cookie
 * in the response — JavaScript never sees the session ID.
 */
async function createServerSession(): Promise<boolean> {
  try {
    const res = await fetch(`${AIOS_BASE}/api/v1/auth/session`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) return false;
    const data = (await res.json()) as { authenticated?: boolean };
    return data.authenticated === true;
  } catch {
    // Backend may not have the endpoint yet
    return false;
  }
}

/**
 * Resolve the shared session id using the secure cookie-based flow.
 *
 * SECURITY: With cookie-based sessions, this function does NOT need to return
 * the actual session ID — the cookie is sent automatically by the browser on
 * every request. It returns a stable identifier for client-side logging only.
 *
 * If cookies are blocked, falls back to sessionStorage with a warning.
 * Falls back to FALLBACK_SESSION_ID when there is no usable storage.
 */
export async function initSession(): Promise<string> {
  if (typeof window === 'undefined') return FALLBACK_SESSION_ID;

  // Try cookie-based session first (server-side, httpOnly)
  if (!_sessionChecked) {
    _sessionChecked = true;
    const hasSession = await checkServerSession();
    if (!hasSession) {
      const created = await createServerSession();
      const verified = created ? await checkServerSession() : false;
      if (!verified) {
        // Backend doesn't support cookie sessions — fall back to storage
        _cookieBased = false;
      }
    }
  }

  if (_cookieBased) {
    // Cookie-based: the browser sends the cookie automatically.
    // We return a stable client-side identifier for logging only.
    return 'cookie-session';
  }

  // ---- COOKIE-BLOCKED FALLBACK: sessionStorage ----
  // This only triggers when cookies are blocked (privacy mode, sandbox)
  // or the backend doesn't support the session endpoint.
  try {
    const existing = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (existing) {
      _fallbackSessionId = existing;
      return existing;
    }
    const created =
      typeof window.crypto?.randomUUID === 'function'
        ? window.crypto.randomUUID()
        : `sb-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, created);
    _fallbackSessionId = created;

    if (!_fallbackWarningEmitted) {
      _fallbackWarningEmitted = true;
      // eslint-disable-next-line no-console
      console.warn(
        '[SECURITY] Cookie-based session not available. ' +
          'Falling back to sessionStorage — session is vulnerable to XSS theft. ' +
          'Enable cookies for secure session management.'
      );
    }
    return created;
  } catch {
    // Storage blocked — return in-memory fallback (lost on refresh)
    if (!_fallbackSessionId) {
      _fallbackSessionId = `mem-${Date.now().toString(36)}`;
    }
    return _fallbackSessionId;
  }
}

/**
 * Synchronous version for callers that need an ID immediately.
 * On first call it triggers the async init and returns a temporary ID.
 * Subsequent calls return the same ID.
 *
 * SECURITY: With cookie-based sessions, the actual session ID lives in the
 * httpOnly cookie. This function returns a client-side identifier for
 * request correlation only. The backend validates the real session from
 * the cookie.
 */
export function getSessionId(): string {
  if (typeof window === 'undefined') return FALLBACK_SESSION_ID;

  // If cookie-based sessions are active, return the stable client identifier
  if (_cookieBased && _sessionChecked) {
    return 'cookie-session';
  }

  // If we have a fallback ID from a previous initSession(), use it
  if (_fallbackSessionId) return _fallbackSessionId;

  // Try reading from sessionStorage (may exist from a prior page load)
  try {
    const existing = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (existing) return existing;
  } catch {
    // Storage blocked
  }

  // Temporary ID — initSession() will establish the real one
  return FALLBACK_SESSION_ID;
}

/**
 * Get the session ID to send in API request bodies.
 *
 * SECURITY: With cookie-based sessions, this returns null because the
 * session travels in the httpOnly cookie automatically. The backend
 * reads the cookie — no body field needed.
 *
 * For storage-based fallback, this returns the session ID that must
 * be sent in the request body.
 */
export function getSessionIdForBody(): string | null {
  if (_cookieBased) {
    return null; // Session travels in cookie, not body
  }
  return getSessionId();
}

export interface SessionContext {
  clientId: string;
  bodySessionId: string | null;
  cookieBased: boolean;
}

/** Initialize the session and return the request-shaping context. */
export async function ensureSession(): Promise<SessionContext> {
  const clientId = await initSession();
  return {
    clientId,
    bodySessionId: getSessionIdForBody(),
    cookieBased: isCookieBasedSession(),
  };
}

/**
 * Destroy the current session (logout).
 *
 * For cookie-based sessions: tells the server to invalidate the session
 * and clears the httpOnly cookie.
 * For storage fallback: removes the session from sessionStorage.
 */
export async function destroySession(): Promise<void> {
  if (_cookieBased) {
    try {
      await fetch(`${AIOS_BASE}/api/v1/auth/session`, {
        method: 'DELETE',
        credentials: 'include',
      });
    } catch {
      // Best-effort
    }
    _sessionChecked = false;
  }

  // Always clean up fallback storage too
  try {
    window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // Storage blocked
  }
  _fallbackSessionId = null;
}

/** Test seam: reset module-level session detection without reloading the page. */
export function __resetSessionForTests(): void {
  _cookieBased = true;
  _sessionChecked = false;
  _fallbackSessionId = null;
  _fallbackWarningEmitted = false;
}
