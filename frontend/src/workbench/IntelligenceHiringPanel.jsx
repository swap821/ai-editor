import { useResource } from '../livingMirror/resource';
import { ResourceNotice } from '../livingMirror/ResourceNotice';
import { durableCollection, noRecords, textValue } from '../livingMirror/recordCollections';
const parse = (value) => durableCollection(value, 'request_id');

export default function IntelligenceHiringPanel() {
  const resource = useResource('/api/v1/hiring/proposals', parse, noRecords);
  return <section className="gagos-panel"><h3>Intelligence routing & hiring</h3>
    <p>Persisted decisions identify the effective provider, data boundary and reason. A configured adapter is not proof of a qualified worker.</p>
    <ResourceNotice resource={resource} empty="No hiring decisions are recorded in the durable repository." />
    <ul>{resource.data?.map((record) => <li key={record.request_id}>
      <strong>{textValue(record.purpose)}</strong><p>{textValue(record.status)} · <code>{record.request_id}</code></p>
      <dl>{[['Mission', record.mission_id], ['Selected provider', record.selected_provider], ['Selected model', record.selected_model],
        ['Data classification', record.data_classification], ['Permitted external context', record.external_data_scope], ['Reason', record.reason], ['Redactions', record.redactions]]
        .map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{textValue(value)}</dd></div>)}</dl>
      <details><summary>Provider-call provenance</summary><pre>{textValue(record.provider_call_provenance)}</pre></details>
    </li>)}</ul>
  </section>;
}
