import { useState } from 'react';
import { API_BASE } from '../config';
import { isRecord } from './contracts';
import { sendGuardedCommand } from './commands';

/**
 * One finding's repair, in GAGOS's own UI (2026-10-30, the daily frontend worker).
 *
 * The governed pipeline, step by step, each step an explicit operator action:
 * 1. Preview: the registered operation's exact diff on the current file. Read it first.
 * 2. Prepare: a draft repair mission bound to this finding.
 * 3. Approve: the privileged act. Needs a freshly re-authenticated session and the exact capability.
 * 4. Run: a staged copy is repaired, verified by rescan, promoted with a checkpoint, smoke-checked,
 *    and rolled back if any check fails.
 * Nothing here applies a change the operator has not read and approved.
 */
interface Preview { diff: string; current: boolean; operation: string }
interface Mission { missionId: string; contractDigest: string; approved: boolean }

export function MaintenanceRepairFlow({ fingerprint, available, refresh }: { fingerprint: string; available: boolean; refresh: () => void }) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mission, setMission] = useState<Mission | null>(null);
  const [read, setRead] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [outcome, setOutcome] = useState<string | null>(null);

  async function loadPreview() {
    setBusy(true); setMessage(''); setRead(false);
    try {
      const response = await fetch(`${API_BASE}/api/v1/maintenance/findings/${encodeURIComponent(fingerprint)}/preview`, { credentials: 'include' });
      const body: unknown = await response.json().catch(() => null);
      if (response.ok && isRecord(body) && typeof body.diff === 'string') {
        setPreview({ diff: body.diff, current: body.current === true, operation: typeof body.operation_id === 'string' ? body.operation_id : '' });
      } else {
        const detail = isRecord(body) && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`;
        setMessage(`No preview: ${detail}`);
      }
    } catch { setMessage('The preview could not be loaded.'); }
    finally { setBusy(false); }
  }

  async function prepare() {
    if (!preview || !read || !preview.current) return;
    setBusy(true);
    try {
      const result = await sendGuardedCommand('/api/v1/maintenance/repairs/missions', { finding_fingerprint: fingerprint });
      const data = result.data;
      if (result.status === 'accepted' && data && typeof data.mission_id === 'string' && typeof data.contract_digest === 'string') {
        setMission({ missionId: data.mission_id, contractDigest: data.contract_digest, approved: false });
        setMessage('Repair mission prepared. Approving it is the next, separate step.');
      } else setMessage(result.message);
    } finally { setBusy(false); }
  }

  async function approve() {
    if (!mission || mission.approved) return;
    setBusy(true);
    try {
      const result = await sendGuardedCommand(`/api/v1/maintenance/repairs/${encodeURIComponent(mission.missionId)}/approve`, { contract_digest: mission.contractDigest });
      if (result.status === 'accepted' && result.data?.state === 'approved') {
        setMission({ ...mission, approved: true });
        setMessage('Approved. Running it is the next, separate step.');
      } else if (result.httpStatus === 401 || result.httpStatus === 403) {
        setMessage(`${result.message} Approval needs a freshly re-authenticated session: re-authenticate in the Sovereign Bond panel, then approve again.`);
      } else setMessage(result.message);
    } finally { setBusy(false); }
  }

  async function run() {
    if (!mission?.approved) return;
    setBusy(true); setMessage('Running in a staged copy: repair, rescan, promotion, smoke check. This can take a few minutes.');
    try {
      const result = await sendGuardedCommand('/api/v1/maintenance/repairs/run', { mission_id: mission.missionId }, 600000);
      const status = isRecord(result.data) && typeof result.data.status === 'string' ? result.data.status : null;
      const reason = isRecord(result.data) && typeof result.data.reason === 'string' && result.data.reason ? ` (${result.data.reason})` : '';
      setOutcome(status ?? result.status);
      setMessage(result.status === 'accepted' ? `Repair finished: ${status ?? 'see the mission record'}${reason}.` : result.message);
    } finally { setBusy(false); refresh(); }
  }

  return <div className="lm-repair-flow">
    {!preview && <button type="button" disabled={!available || busy} onClick={() => void loadPreview()}>Preview the repair</button>}
    {preview && <>
      <p>The exact change <code>{preview.operation}</code> would make:</p>
      <pre aria-label="Repair diff">{preview.diff || '(no change)'}</pre>
      {!preview.current && <p role="alert">The file changed since this finding was scanned. Scan again before repairing.</p>}
      {!mission && <>
        <label className="lm-check"><input type="checkbox" checked={read} disabled={!preview.current} onChange={(event) => setRead(event.target.checked)} />I read this exact change.</label>
        <button type="button" disabled={!available || busy || !read || !preview.current} onClick={() => void prepare()}>Prepare the repair</button>
      </>}
      {mission && !mission.approved && <button type="button" disabled={!available || busy} onClick={() => void approve()}>Approve the repair</button>}
      {mission?.approved && !outcome && <button type="button" disabled={!available || busy} onClick={() => void run()}>Run the approved repair</button>}
    </>}
    {busy && <p role="status">Request pending…</p>}
    {message && <p role="status">{message}</p>}
  </div>;
}
