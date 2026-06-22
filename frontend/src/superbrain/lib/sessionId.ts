/**
 * getSessionId — the single source of truth for the operator's session id.
 *
 * ONE conversation per operator, SHARED across every face of the AI-OS (the
 * canon HUD command bar, the workbench organs, and the classic IDE) so they all
 * continue the SAME backend conversation under the SAME `aios_session_id`.
 *
 * Four callsites used to hand-copy this resolver in two subtly different
 * flavours: the adapter + the classic shell CREATED and persisted a UUID, while
 * the read-only organs only READ (falling back to the 'gag-superbrain-hud'
 * constant, never creating). When a read-only organ ran before the owner minted
 * the UUID, it returned the constant while the owner persisted a UUID — the two
 * faces silently forked and the brain "forgot" across them. This module ends
 * that: every caller read-or-creates the SAME persisted id.
 *
 * SSR-safe (the lab is Next.js): with no `window` it returns the stable
 * fallback constant and never throws.
 */

/** The storage key both faces share — change here and nowhere else. */
export const SESSION_STORAGE_KEY = 'aios_session_id';

/** The stable id used when storage is unavailable (SSR, privacy mode, sandbox). */
export const FALLBACK_SESSION_ID = 'gag-superbrain-hud';

/**
 * Resolve the shared session id: return the persisted one, or mint + persist a
 * new UUID on first use. Falls back to {@link FALLBACK_SESSION_ID} when there is
 * no usable storage, so it is safe to call during SSR or in a locked-down tab.
 */
export function getSessionId(): string {
  if (typeof window === 'undefined') return FALLBACK_SESSION_ID;
  try {
    const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (existing) return existing;
    const created =
      typeof window.crypto?.randomUUID === 'function'
        ? window.crypto.randomUUID()
        : `sb-${Date.now().toString(36)}`;
    window.localStorage.setItem(SESSION_STORAGE_KEY, created);
    return created;
  } catch {
    return FALLBACK_SESSION_ID;
  }
}
