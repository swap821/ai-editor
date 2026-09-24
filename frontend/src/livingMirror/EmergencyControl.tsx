import { useEffect, useRef, useState } from 'react';
import { isRecord } from './contracts';
import { useResource } from './resource';
import { ResourceNotice } from './ResourceNotice';
import { sendGuardedCommand, type CommandResult } from './commands';
import { setEmergencyStopPresentation } from './emergencyStopPresentation';

const stopPath = '/api/v1/governance/emergency-stop';
const guidedDefaultReason = 'I asked GAGOS to stop';
const expertDefaultReason = 'Operator requested emergency stop';
function parseStop(value: unknown) {
  if (!isRecord(value) || typeof value.engaged !== 'boolean' || typeof value.generation !== 'number' || !isRecord(value.actions)) throw new Error('Stop state response is incomplete.');
  return { engaged: value.engaged, generation: value.generation, reason: typeof value.reason === 'string' ? value.reason : null,
    operatorId: typeof value.operatorId === 'string' ? value.operatorId : null,
    authenticationEventId: typeof value.authenticationEventId === 'string' ? value.authenticationEventId : null,
    failure: typeof value.failure === 'string' ? value.failure : null,
    engagedAt: typeof value.engagedAt === 'string' ? value.engagedAt : null, clearedAt: typeof value.clearedAt === 'string' ? value.clearedAt : null,
    actions: Object.fromEntries(Object.entries(value.actions).filter((entry): entry is [string, string] => typeof entry[1] === 'string')) };
}
const neverEmpty = () => false;
export function EmergencyControl({ guided = false }: { guided?: boolean }) {
  const state = useResource(stopPath, parseStop, neverEmpty);
  const [expanded, expand] = useState(false);
  const detailsButtonRef = useRef<HTMLButtonElement>(null);
  const restoreDetailsFocus = useRef(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CommandResult | null>(null);
  const [reason, setReason] = useState(guided ? guidedDefaultReason : expertDefaultReason);
  const displayedReason = reason === guidedDefaultReason || reason === expertDefaultReason
    ? (guided ? guidedDefaultReason : expertDefaultReason)
    : reason;
  useEffect(() => {
    const observed = state.data?.engaged;
    setEmergencyStopPresentation(observed === true ? 'engaged' : observed === false ? 'clear' : 'unknown');
  }, [state.data?.engaged]);
  useEffect(() => {
    if (expanded || !restoreDetailsFocus.current) return;
    restoreDetailsFocus.current = false;
    detailsButtonRef.current?.focus();
  }, [expanded]);
  function toggleDetails() {
    if (expanded) restoreDetailsFocus.current = true;
    expand(!expanded);
  }
  function closeDetails() {
    restoreDetailsFocus.current = true;
    expand(false);
  }
  async function submit(action: 'engage' | 'clear') {
    if (busy) return;
    setBusy(true); expand(true); setResult(null);
    try { setResult(await sendGuardedCommand(`${stopPath}/${action}`, action === 'engage' ? { reason: displayedReason } : {})); }
    finally { setBusy(false); state.refresh(); }
  }
  const latched = state.data?.engaged === true;
  const confirmed = state.status === 'available';
  const hooks = Object.entries(state.data?.actions ?? {});
  const hooksComplete = ['revoke_capabilities', 'cancel_queued_missions', 'kill_active_workers', 'disable_autonomy', 'preserve_evidence']
    .every((key) => /^(completed|completed:\d+)$/.test(state.data?.actions[key] ?? ''));
  return <aside className="lm-stop" aria-label="Emergency stop">
    <button type="button" className="lm-stop__engage" disabled={busy || (confirmed && latched)} onClick={() => void submit('engage')}>
      {busy ? 'Stop request pending' : confirmed && latched ? (guided ? 'Stop is on' : 'Stop latch engaged') : 'Emergency stop'}
    </button>
    <button ref={detailsButtonRef} type="button" aria-expanded={expanded} aria-controls="emergency-stop-details" onClick={toggleDetails} aria-label="Inspect emergency stop">Details</button>
    {expanded && <section id="emergency-stop-details" className="lm-stop__detail" aria-label="Stop state and outcomes">
      <h2>Human control</h2>
      <p>{!state.data ? 'Stop state unavailable.' : latched ? `${confirmed ? 'Confirmed' : 'Last-known'} ${guided ? 'stop is on.' : 'latch engaged.'}` : `${confirmed ? 'Confirmed' : 'Last-known'} ${guided ? 'stop is off.' : 'latch disengaged.'}`}</p>
      <ResourceNotice resource={state} empty="Stop state unavailable." />
      {busy && <p role="status">Request sent; awaiting the server.</p>}
      {result && <p role="status">{result.message}</p>}
      {latched && guided && <p>{hooksComplete ? 'The stop actions recorded by GAGOS are complete.' : 'Some stop actions are still being confirmed.'}</p>}
      {latched && !guided && <p>{hooksComplete ? 'All recorded stop hooks completed.' : 'Stopping is only partially confirmed; inspect the recorded hooks.'}</p>}
      {state.data?.failure && guided && <p role="alert">The stop controller reported an issue. Recorded details are available in Expert/Mirror.</p>}
      {state.data?.failure && !guided && <p role="alert">Stop controller reported: {state.data.failure}</p>}
      {!guided && state.data?.operatorId && <p>Operator <code>{state.data.operatorId}</code></p>}
      {!guided && state.data?.authenticationEventId && <p>Authentication event <code>{state.data.authenticationEventId}</code></p>}
      {!guided && <dl>{hooks.map(([key, value]) => <div key={key}><dt>{key.replace(/_/g, ' ')}</dt><dd>{value}</dd></div>)}</dl>}
      {!guided && <p>Hook completion reports are aggregate outcomes. Individual worker termination receipts are not exposed here.</p>}
      {guided && hooks.length > 0 && <p>Expert/Mirror can show the recorded stop details.</p>}
      <label>Reason<input value={displayedReason} onChange={(e) => setReason(e.target.value)} /></label>
      {latched && <button type="button" disabled={busy || !confirmed} onClick={() => void submit('clear')}>{guided ? 'Request resume' : 'Request latch clear'}</button>}
      <p>{guided ? 'Resuming requires a fresh security check and does not restart work.' : 'Clearing the latch requires fresh privileged authentication and does not restart work.'}</p>
      <button type="button" onClick={closeDetails}>Close details</button>
    </section>}
  </aside>;
}
