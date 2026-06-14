import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  getSessionId,
  FALLBACK_SESSION_ID,
  SESSION_STORAGE_KEY,
} from '../superbrain/lib/sessionId';

/* P1-3 — the single shared session resolver. The contract that matters: every
   face of the AI-OS (canon HUD adapter, workbench organs, classic shell) calls
   THIS and gets the SAME persisted `aios_session_id`, so the conversation never
   silently forks across faces. The module is generated from the lab via
   `npm run port`; this product-side test imports it so the contract is enforced
   in CI regardless of the port. */
describe('getSessionId (shared session resolver, anti-fork)', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('mints and persists a real id on first use (not the fallback constant)', () => {
    expect(window.localStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
    const id = getSessionId();
    expect(id).toBeTruthy();
    expect(id).not.toBe(FALLBACK_SESSION_ID);
    expect(window.localStorage.getItem(SESSION_STORAGE_KEY)).toBe(id);
  });

  it('returns the SAME id on every later call (no drift across faces)', () => {
    const owner = getSessionId(); // first face mints + persists
    const secondFace = getSessionId(); // another face reads
    const thirdFace = getSessionId();
    expect(secondFace).toBe(owner);
    expect(thirdFace).toBe(owner);
  });

  it('reuses an already-persisted id rather than minting a new one', () => {
    window.localStorage.setItem(SESSION_STORAGE_KEY, 'preexisting-shared-id');
    expect(getSessionId()).toBe('preexisting-shared-id');
    expect(getSessionId()).toBe('preexisting-shared-id');
  });

  it('falls back to the stable constant when storage throws (never throws, never forks)', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage blocked');
    });
    expect(getSessionId()).toBe(FALLBACK_SESSION_ID);
    // a second blocked caller resolves to the identical constant, still no fork.
    expect(getSessionId()).toBe(FALLBACK_SESSION_ID);
  });
});
