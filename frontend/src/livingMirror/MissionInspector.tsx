import { useCallback, useState } from 'react';
import { isRecord, parseCouncilDetail, type CouncilDetail } from './contracts';
import { readResource, useResource } from './resource';
import { ResourceNotice } from './ResourceNotice';
import { sendGuardedCommand, type CommandResult } from './commands';
import { redactProjection } from './redaction';
import { useMirrorStore } from '../superbrain/lib/mirrorStore';

const neverEmpty = () => false;
const show = (value: unknown) => value === null || value === undefined ? 'Unavailable' : typeof value === 'string' ? value : JSON.stringify(redactProjection(value), null, 2);
function RecordedObject({ title, value }: { title: string; value: unknown }) {
  return <details><summary>{title}</summary>{value == null ? <p>No supported record was returned for this field.</p> : <pre>{show(value)}</pre>}</details>;
}
function decisionBinding(detail: CouncilDetail, requestId: string) {
  const request = detail.pendingApprovals.find((r) => r.requestId === requestId);
  return JSON.stringify([detail.missionId, detail.missionAuthority?.contractDigest ?? null, requestId, request?.action ?? null]);
}

export function MissionInspector({ id }: { id: string }) {
  const parser = useCallback((data: unknown) => parseCouncilDetail(data, id), [id]);
  const path = `/api/v1/council/missions/${encodeURIComponent(id)}`;
  const resource = useResource(path, parser, neverEmpty);
  const workers = useMirrorStore((s) => s.workers);
  const [requestId, setRequestId] = useState('');
  const [reviewed, setReviewed] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [result, setResult] = useState<CommandResult | null>(null);
  const detail = resource.data;
  const request = detail?.pendingApprovals.find((r) => r.requestId === requestId);
  const binding = detail ? decisionBinding(detail, requestId) : '';
  const actionable = !!detail && resource.status === 'available' && !busy
    && (request ? true : requestId === '' && detail.summary.approvalNeeded === true && !!detail.missionAuthority?.contractDigest && !detail.kingDecision);
  async function decide(approved: boolean) {
    if (!detail || !actionable || reviewed !== binding) return;
    setBusy(true); setMessage('Checking the current request…'); setResult(null);
    try {
      const current = await readResource(path, parser);
      if (decisionBinding(current, requestId) !== binding || (requestId && !current.pendingApprovals.some((r) => r.requestId === requestId))) {
        setReviewed(''); setMessage('The request changed. Review the refreshed contract and scope before deciding.'); return;
      }
      setMessage('Submitting the reviewed decision…');
      const outcome = await sendGuardedCommand(`/api/v1/council/${approved ? 'approve' : 'reject'}`, {
        missionId: id, ...(requestId ? { requestId } : {}), ...(current.missionAuthority ? { contractDigest: current.missionAuthority.contractDigest } : {}),
        reason: approved ? 'Approved after reviewing the mission authority surface' : 'Rejected from mission authority surface',
      });
      setResult(outcome);
      setMessage(outcome.status === 'accepted' && outcome.data?.execution === 'scheduled'
        ? 'Decision accepted; execution scheduled. Verification and project effects require their own records.' : outcome.message);
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Current authority could not be checked.'); }
    finally { setBusy(false); setReviewed(''); resource.refresh(); }
  }
  if (!detail) return <ResourceNotice resource={resource} empty="Mission detail unavailable." />;
  const report = detail.report;
  const ledger = detail.ledger;
  const evidence = isRecord(ledger?.evidence) ? ledger.evidence : isRecord(report.evidence) ? report.evidence : null;
  const promotion = isRecord(evidence?.promotion) ? evidence.promotion : null;
  const verification = report.verification_result ?? ledger?.verification ?? null;
  const council = isRecord(report.council_summary) ? report.council_summary : null;
  const workerRecords = Object.values(workers).filter((w) => w.missionId === id);
  return <section className="lm-mission" aria-label={`Inspect mission ${id}`}>
    <ResourceNotice resource={resource} empty="Mission detail unavailable." />
    <h3>{detail.summary.mission}</h3>
    <dl><dt>Mission</dt><dd><code>{id}</code></dd><dt>Authoritative state</dt><dd>{detail.missionAuthority?.state ?? 'Unavailable'}</dd>
      <dt>Report state</dt><dd>{detail.summary.status}</dd><dt>Risk</dt><dd>{detail.summary.risk ?? 'Unavailable'}</dd></dl>
    <details open><summary>Brief & deliberation</summary>
      <p>{detail.summary.mission}</p>
      <RecordedObject title="Recorded Council assessments" value={council?.council_verdicts ?? detail.report.councilVerdicts} />
      <RecordedObject title="Synthesis and participation records" value={council} />
      <p>Roles absent from these records are not represented as participating.</p>
    </details>
    <details open={detail.summary.approvalNeeded === true || detail.pendingApprovals.length > 0}><summary>Authority & decisions</summary>
      <dl><dt>Contract digest</dt><dd><code>{detail.missionAuthority?.contractDigest ?? 'Unavailable'}</code></dd>
        <dt>Runtime contract</dt><dd><code>{detail.missionAuthority?.runtimeContractDigest ?? 'Unavailable'}</code></dd>
        <dt>Operator binding</dt><dd>{detail.missionAuthority?.operatorId ?? 'Unavailable'}</dd>
        <dt>Validity / expiry</dt><dd>Not exposed by this route. The server validates current authority on submission.</dd></dl>
      <label>Decision request<select value={requestId} onChange={(e) => { setRequestId(e.target.value); setReviewed(''); }}>
        <option value="">Mission-level request</option>{detail.pendingApprovals.map((r) => <option key={r.requestId} value={r.requestId}>{r.requestId} · Worker {r.workerId}</option>)}
      </select></label>
      {request && <><p>{request.reason ?? 'No request rationale recorded.'}</p><pre>{show(request.action)}</pre></>}
      <RecordedObject title="Recorded contract and scope" value={report.contract ?? ledger?.contract ?? report.royal_decree ?? null} />
      <p>Only the backend can grant, consume, revoke or expire authority. Opening or closing this surface performs no action.</p>
      <label className="lm-check"><input type="checkbox" checked={reviewed === binding} disabled={!actionable} onChange={(e) => setReviewed(e.target.checked ? binding : '')} />I have reviewed this request and its current contract binding.</label>
      <div className="lm-actions"><button type="button" disabled={!actionable || reviewed !== binding} onClick={() => void decide(true)}>Approve this request</button>
        <button type="button" disabled={!actionable || reviewed !== binding} onClick={() => void decide(false)}>Reject this request</button></div>
      {message && <p role="status">{message}</p>}
      {result && <RecordedObject title="Decision response" value={result.data} />}
      <RecordedObject title="Last stored decision" value={detail.kingDecision} />
    </details>
    <details><summary>Workers & work</summary>
      {workerRecords.length === 0 ? <p>No bound worker observations received in this browser session.</p> : <ul>{workerRecords.map((worker) => <li key={worker.id}>
        <strong>{worker.role ?? 'Worker'} · {worker.state}</strong><p><code>{worker.id}</code></p>
        <RecordedObject title="Scope, workspace, job and latest observation" value={worker.payload} />
      </li>)}</ul>}
      <RecordedObject title="Reported artifacts" value={report.files} />
      <p>An artifact name or worker completion does not establish verification or promotion.</p>
    </details>
    <details open={detail.summary.verificationPassed === false}><summary>Evidence & verification</summary>
      <dl><dt>Reported verification</dt><dd>{detail.summary.verificationPassed === null ? 'Unavailable' : detail.summary.verificationPassed ? 'Passed' : 'Failed'}</dd>
        <dt>Strength</dt><dd>{detail.summary.verificationStrength ?? 'Unavailable'}</dd><dt>Required floor met</dt><dd>{show(detail.summary.verificationMeetsFloor)}</dd>
        <dt>Evidence bundle digest</dt><dd><code>{show(evidence?.evidence_bundle_digest)}</code></dd></dl>
      <RecordedObject title="Verification targets and results" value={verification} />
      <RecordedObject title="Recorded evidence" value={evidence} />
      <p>Exact staged diff content and independent evidence lookup are unavailable unless present in these recorded artifacts.</p>
    </details>
    <details open={!!promotion && promotion.status !== 'promoted'}><summary>Effects & recovery</summary>
      <dl>{[['Disposition', promotion?.status], ['Diff digest', promotion?.diff_digest], ['Checkpoint', promotion?.checkpoint_id], ['Hold reasons', promotion?.reason_codes], ['Restoration confirmed', promotion?.restored]].map(([label, value]) => <div key={String(label)}><dt>{String(label)}</dt><dd><code>{show(value)}</code></dd></div>)}</dl>
      <RecordedObject title="Promotion and post-check receipt" value={promotion?.post_promotion_receipt} />
      <RecordedObject title="Recorded rollback" value={evidence?.rollback} />
      <p>A general recovery journal is not exposed to this frontend. Unresolved effects remain unresolved.</p>
    </details>
    <details><summary>Experience & durable history</summary>
      <RecordedObject title="Mission ledger" value={ledger} />
      <p>Candidate skill lineage is inspected in Experience. A completed mission does not automatically activate a skill.</p>
    </details>
  </section>;
}
