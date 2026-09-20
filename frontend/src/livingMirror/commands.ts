import { API_BASE } from '../config';
import { isRecord } from './contracts';
import { redactProjection } from './redaction';

export interface CommandResult {
  status: 'accepted' | 'rejected' | 'outcome_unknown';
  message: string;
  data: Record<string, unknown> | null;
  httpStatus: number | null;
  /** Opaque, in-memory continuation for the already-reviewed exact rollback. Never a scene record. */
  continueRollback?: () => Promise<CommandResult>;
}
/** Called only from an explicit operator action. The capability stays in this call's closure. */
export async function sendGuardedCommand(path: string, body: Record<string, unknown>, timeoutMs = 20000): Promise<CommandResult> {
  const serialized = JSON.stringify(body); // capture the exact reviewed body before asynchronous work
  const abort = new AbortController();
  const timeout = setTimeout(() => abort.abort(), timeoutMs);
  let attempted = false;
  const request = (capability?: string) => {
    attempted = true;
    return fetch(`${API_BASE}${path}`, { method: 'POST', credentials: 'include', signal: abort.signal,
      headers: { 'Content-Type': 'application/json', ...(capability ? { 'X-AIOS-Capability': capability } : {}) }, body: serialized });
  };
  try {
    let response = await request();
    if (response.status === 428) {
      const challenge: unknown = await response.json();
      const detail = isRecord(challenge) && isRecord(challenge.detail) ? challenge.detail : null;
      if (!detail || typeof detail.approvalToken !== 'string' || (typeof detail.route === 'string' && detail.route !== path)) {
        return { status: 'rejected', message: 'The authority challenge could not be matched to this request. Refresh and review it again.', data: null, httpStatus: 428 };
      }
      response = await request(detail.approvalToken);
    }
    let raw: unknown;
    try { raw = await response.json(); } catch { raw = null; }
    const data = isRecord(raw) ? redactProjection(raw) as Record<string, unknown> : null;
    if (response.ok && data) {
      const result: CommandResult = { status: 'accepted', message: 'Request accepted. Refreshing its authoritative outcome.', data, httpStatus: response.status };
      if (/^\/api\/v1\/council\/missions\/[^/]+\/rollback$/.test(path) && isRecord(raw) && raw.requiresApproval === true
        && raw.executed === false && raw.actionType === 'rollback' && raw.snapshotId === body.snapshotId && typeof raw.approvalToken === 'string') {
        const rollbackBody = { ...JSON.parse(serialized), approvalToken: raw.approvalToken };
        result.continueRollback = () => sendGuardedCommand(path, rollbackBody, timeoutMs);
      }
      return result;
    }
    const detail = data?.detail;
    const description = typeof detail === 'string' ? detail : isRecord(detail) && typeof detail.error === 'string' ? detail.error : `HTTP ${response.status}`;
    if (response.status >= 500 || response.ok) return { status: 'outcome_unknown', message: 'The response did not establish the outcome. Inspect refreshed records before retrying.', data, httpStatus: response.status };
    return { status: 'rejected', message: `Request rejected: ${description}`, data, httpStatus: response.status };
  } catch {
    return { status: attempted ? 'outcome_unknown' : 'rejected', message: 'Delivery or outcome is unknown. Inspect refreshed records before retrying.', data: null, httpStatus: null };
  } finally { clearTimeout(timeout); }
}
