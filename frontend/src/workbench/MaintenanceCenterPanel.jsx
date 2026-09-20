import { useResource } from '../livingMirror/resource';
import { ResourceNotice } from '../livingMirror/ResourceNotice';
import { durableCollection, noRecords, textValue } from '../livingMirror/recordCollections';
const parseFindings = (value) => durableCollection(value, 'finding_id');
const parseScans = (value) => durableCollection(value, 'scan_id');

export default function MaintenanceCenterPanel() {
  const findings = useResource('/api/v1/maintenance/findings', parseFindings, noRecords);
  const scans = useResource('/api/v1/maintenance/scans', parseScans, noRecords);
  return <section className="gagos-panel"><h3>Maintenance</h3>
    <h4>Durable findings</h4><ResourceNotice resource={findings} empty="No findings are recorded in the durable repository." />
    <ul>{findings.data?.map((finding) => <li key={finding.finding_id}>
      <strong>{textValue(finding.kind)} · {textValue(finding.severity)}</strong><p>{textValue(finding.status)} · <code>{finding.finding_id}</code></p>
      <p>Target <code>{textValue(finding.target_id)}</code></p>
      <details><summary>Evidence and proposed remedy</summary><p>{textValue(finding.deterministic_evidence)}</p>
        <dl>{[['Source digest', finding.source_digest], ['Evidence quality', finding.evidence_quality], ['Mission', finding.mission_id],
          ['Frontier analysis', finding.frontier_analysis], ['Verification IDs', finding.verification_ids], ['Resolution evidence', finding.resolution_evidence]]
          .map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{textValue(value)}</dd></div>)}</dl>
        <p>Inspecting this finding does not start a repair.</p>
      </details>
    </li>)}</ul>
    <h4>Recorded scans</h4><ResourceNotice resource={scans} empty="No scans are recorded in the durable repository." />
    <ul>{scans.data?.map((scan) => <li key={scan.scan_id}><code>{scan.scan_id}</code><details><summary>Bounded scan record</summary><pre>{JSON.stringify(scan, null, 2)}</pre></details></li>)}</ul>
  </section>;
}
