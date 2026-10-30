import { useState } from 'react';
import { useResource } from '../livingMirror/resource';
import { ResourceNotice } from '../livingMirror/ResourceNotice';
import { durableCollection, noRecords, textValue } from '../livingMirror/recordCollections';
import { sendGuardedCommand } from '../livingMirror/commands';
import { MaintenanceRepairFlow } from '../livingMirror/MaintenanceRepairFlow';
const parseFindings = (value) => durableCollection(value, 'finding_id');
const parseScans = (value) => durableCollection(value, 'scan_id');

/**
 * The frontend scan: unused imports in GAGOS's own frontend, through the
 * governed pipeline (2026-10-30, the daily frontend worker). Bounds sized for
 * the whole frontend (about 500 source files), read from the project root.
 */
const FRONTEND_SCAN = {
  scanner_id: 'frontend_unused_imports',
  target_id: '.',
  max_files: 2000,
  max_total_bytes: 50_000_000,
  deadline_seconds: 120,
};

export default function MaintenanceCenterPanel() {
  const findings = useResource('/api/v1/maintenance/findings', parseFindings, noRecords);
  const scans = useResource('/api/v1/maintenance/scans', parseScans, noRecords);
  const [scanning, setScanning] = useState(false);
  const [scanMessage, setScanMessage] = useState('');
  const available = findings.status !== 'failed' && findings.status !== 'unavailable';
  const refreshAll = () => { findings.refresh(); scans.refresh(); };

  async function scanFrontend() {
    setScanning(true); setScanMessage('');
    try {
      const result = await sendGuardedCommand('/api/v1/maintenance/scans', FRONTEND_SCAN, 180000);
      const count = result.data?.finding_count;
      setScanMessage(result.status === 'accepted'
        ? `Frontend scanned: ${typeof count === 'number' ? count : 'an unknown number of'} finding(s).`
        : result.message);
    } finally { setScanning(false); refreshAll(); }
  }

  return <section className="gagos-panel"><h3>Maintenance</h3>
    <h4>Daily care</h4>
    <p>GAGOS looks after its own frontend: scan, read the exact change, approve, and it repairs a staged copy, verifies it, and rolls back if any check fails.</p>
    <button type="button" disabled={scanning} onClick={() => void scanFrontend()}>Scan the frontend</button>
    {scanning && <p role="status">Scanning…</p>}
    {scanMessage && <p role="status">{scanMessage}</p>}
    <h4>Durable findings</h4><ResourceNotice resource={findings} empty="No findings are recorded in the durable repository." />
    <ul>{findings.data?.map((finding) => <li key={finding.finding_id}>
      <strong>{textValue(finding.kind)} · {textValue(finding.severity)}</strong><p>{textValue(finding.status)} · <code>{finding.finding_id}</code></p>
      <p>Target <code>{textValue(finding.target_id)}</code></p>
      <details><summary>Evidence and proposed remedy</summary><p>{textValue(finding.deterministic_evidence)}</p>
        <dl>{[['Source digest', finding.source_digest], ['Evidence quality', finding.evidence_quality], ['Mission', finding.mission_id],
          ['Frontier analysis', finding.frontier_analysis], ['Verification IDs', finding.verification_ids], ['Resolution evidence', finding.resolution_evidence]]
          .map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{textValue(value)}</dd></div>)}</dl>
      </details>
      {finding.status === 'OPEN' && typeof finding.fingerprint === 'string'
        ? <MaintenanceRepairFlow fingerprint={finding.fingerprint} available={available} refresh={refreshAll} />
        : <p>Inspecting this finding does not start a repair.</p>}
    </li>)}</ul>
    <h4>Recorded scans</h4><ResourceNotice resource={scans} empty="No scans are recorded in the durable repository." />
    <ul>{scans.data?.map((scan) => <li key={scan.scan_id}><code>{scan.scan_id}</code><details><summary>Bounded scan record</summary><pre>{JSON.stringify(scan, null, 2)}</pre></details></li>)}</ul>
  </section>;
}
