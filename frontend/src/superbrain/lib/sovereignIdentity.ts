/**
 * sovereignIdentity — the frontend's one truth source for the Human Sovereign bond.
 *
 * GAGOS serves exactly one human (aios/api/routes/auth.py: "Bootstrap exactly
 * one Human Sovereign"). This module wraps the real backend identity routes —
 * enroll / login / reauth — and a subscribable measured-status store, so the
 * sovereignty pill and the Bond panel always render the SAME truth.
 *
 * HONESTY RULES (same discipline as the rest of this codebase):
 *  - Status is always MEASURED via GET /api/v1/auth/session — never assumed
 *    after a mutation. Every mutation refetches before reporting success.
 *  - A 401 is a real failure and is narrated as one; a network error is
 *    `unknown`, never silently rendered as "anonymous".
 *  - The one-time enrollment credential/recovery code pass through the caller
 *    exactly once and are NEVER stored in this module, storage, or logs.
 */

const AIOS_BASE = process.env.NEXT_PUBLIC_AIOS_URL ?? 'http://localhost:8000';

export interface SovereignStatus {
  /** Whether ANY session (anonymous or sovereign) exists. */
  sessionActive: boolean;
  /** The enrolled operator id when the session is sovereign-authenticated. */
  operatorId: string | null;
  /** 'unknown' until the first measurement resolves, or after a fetch error. */
  measured: 'unknown' | 'measured';
}

export interface EnrollmentMaterial {
  operatorId: string;
  /** Shown ONCE. The backend cannot re-derive it. */
  enrollmentCredential: string;
  /** Shown ONCE. The backend cannot re-derive it. */
  recoveryCode: string;
}

export type EnrollOutcome =
  | { kind: 'enrolled'; material: EnrollmentMaterial }
  | { kind: 'already_enrolled' }
  | { kind: 'failed'; detail: string };

export type CredentialOutcome =
  | { kind: 'authenticated'; operatorId: string }
  | { kind: 'invalid_credential' }
  | { kind: 'failed'; detail: string };

const UNKNOWN_STATUS: SovereignStatus = {
  sessionActive: false,
  operatorId: null,
  measured: 'unknown',
};

let currentStatus: SovereignStatus = UNKNOWN_STATUS;
const listeners = new Set<(status: SovereignStatus) => void>();

function setStatus(next: SovereignStatus): void {
  currentStatus = next;
  for (const listener of listeners) listener(currentStatus);
}

export function getSovereignStatus(): SovereignStatus {
  return currentStatus;
}

/** Subscribe to status changes; emits the current value immediately. */
export function subscribeSovereignStatus(
  listener: (status: SovereignStatus) => void,
): () => void {
  listeners.add(listener);
  listener(currentStatus);
  return () => {
    listeners.delete(listener);
  };
}

/** Measure the real session/identity state from the backend. */
export async function refreshSovereignStatus(): Promise<SovereignStatus> {
  try {
    const res = await fetch(`${AIOS_BASE}/api/v1/auth/session`, {
      method: 'GET',
      credentials: 'include',
    });
    if (!res.ok) {
      setStatus(UNKNOWN_STATUS);
      return currentStatus;
    }
    const data = (await res.json()) as {
      authenticated?: boolean;
      operatorId?: string | null;
    };
    setStatus({
      sessionActive: data.authenticated === true,
      operatorId: typeof data.operatorId === 'string' && data.operatorId ? data.operatorId : null,
      measured: 'measured',
    });
  } catch {
    setStatus(UNKNOWN_STATUS);
  }
  return currentStatus;
}

/** Claim sovereignty: enroll the one Human Sovereign. 409 = already bound. */
export async function enrollSovereign(displayName: string): Promise<EnrollOutcome> {
  try {
    const res = await fetch(`${AIOS_BASE}/api/v1/auth/enroll`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ displayName }),
    });
    if (res.status === 409) return { kind: 'already_enrolled' };
    if (!res.ok) return { kind: 'failed', detail: `backend responded ${res.status}` };
    const data = (await res.json()) as {
      enrolled?: boolean;
      operatorId?: string;
      enrollmentCredential?: string;
      recoveryCode?: string;
    };
    if (!data.enrolled || !data.operatorId || !data.enrollmentCredential || !data.recoveryCode) {
      return { kind: 'failed', detail: 'enrollment response was incomplete' };
    }
    return {
      kind: 'enrolled',
      material: {
        operatorId: data.operatorId,
        enrollmentCredential: data.enrollmentCredential,
        recoveryCode: data.recoveryCode,
      },
    };
  } catch {
    return { kind: 'failed', detail: 'the backend could not be reached' };
  }
}

async function presentCredential(
  path: '/api/v1/auth/login' | '/api/v1/auth/reauth',
  credential: string,
): Promise<CredentialOutcome> {
  try {
    const res = await fetch(`${AIOS_BASE}${path}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credential }),
    });
    if (res.status === 401) return { kind: 'invalid_credential' };
    if (!res.ok) return { kind: 'failed', detail: `backend responded ${res.status}` };
    const data = (await res.json()) as { authenticated?: boolean; operatorId?: string };
    if (data.authenticated !== true || !data.operatorId) {
      return { kind: 'failed', detail: 'authentication response was incomplete' };
    }
    // Success is only reported after the MEASURED status confirms it — the
    // cookie the server just set is the authority, not the JSON body alone.
    const status = await refreshSovereignStatus();
    if (status.operatorId !== data.operatorId) {
      return { kind: 'failed', detail: 'session did not reflect the authenticated operator' };
    }
    return { kind: 'authenticated', operatorId: data.operatorId };
  } catch {
    return { kind: 'failed', detail: 'the backend could not be reached' };
  }
}

/** Present the credential to open a sovereign session. */
export function loginSovereign(credential: string): Promise<CredentialOutcome> {
  return presentCredential('/api/v1/auth/login', credential);
}

/** Re-present the credential to rotate the sovereign session (privileged acts). */
export function reauthSovereign(credential: string): Promise<CredentialOutcome> {
  return presentCredential('/api/v1/auth/reauth', credential);
}

/** Release the SESSION (logout). The bond itself persists server-side. */
export async function releaseSovereignSession(): Promise<void> {
  try {
    await fetch(`${AIOS_BASE}/api/v1/auth/session`, {
      method: 'DELETE',
      credentials: 'include',
    });
  } catch {
    // Best-effort; the measured refetch below reports whatever is true.
  }
  await refreshSovereignStatus();
}

/** Test seam: reset module state without reloading. */
export function __resetSovereignIdentityForTests(): void {
  currentStatus = UNKNOWN_STATUS;
  listeners.clear();
}
