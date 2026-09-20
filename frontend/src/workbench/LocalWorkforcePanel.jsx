import { useMirrorStore } from '../superbrain/lib/mirrorStore';
import { useResource } from '../livingMirror/resource';
import { ResourceNotice } from '../livingMirror/ResourceNotice';
import { identifiedRecords, noRecords, textValue } from '../livingMirror/recordCollections';
const parse = (value) => identifiedRecords(value, 'model_id');

export default function LocalWorkforcePanel() {
  const mirror = useMirrorStore();
  const resource = useResource('/api/v1/local-workforce', parse, noRecords);
  return <section className="gagos-panel"><h3>Local workforce</h3>
    <ResourceNotice resource={resource} empty="No local models are recorded in the durable registry." />
    <ul>{resource.data?.map((model) => <li key={model.model_id}>
      <strong>{model.model_id}</strong><dl>{[['Installed', model.installed], ['Operator approval', model.operator_approved], ['Health', model.health],
        ['Admission', model.admission_status], ['Admission reason', model.admission_reason], ['Qualified roles', model.allowed_job_profiles],
        ['Qualification evidence', model.qualification_evidence_digest], ['Qualification expiry', model.expires_at], ['Limits', model.limitations]]
        .map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{textValue(value)}</dd></div>)}</dl>
    </li>)}</ul>
    <h4>Worker observations</h4>
    <p>{mirror.observations.activeWorkers.status === 'unavailable' ? 'Active worker count unavailable.' : `${mirror.activeWorkers.length} observed active workers · ${mirror.observations.activeWorkers.status}.`}</p>
    <p>Provider locality and qualification belong to each worker's actual records; an active worker ID alone does not establish either.</p>
    <ul>{mirror.activeWorkers.map((id) => <li key={id}><code>{id}</code><p>{mirror.workers[id]?.state ?? 'Active in last snapshot'} · {mirror.workers[id]?.missionId ?? 'Mission binding unavailable'}</p></li>)}</ul>
  </section>;
}
