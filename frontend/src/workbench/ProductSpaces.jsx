import { useState } from 'react';
import { Activity, BriefcaseBusiness, Clock3, FolderTree, ShieldCheck } from 'lucide-react';
import { useMirrorStore } from '../superbrain/lib/mirrorStore';
import CouncilDashboard from './CouncilDashboard';
import CodeEditor from './CodeEditor';
import FileTree from './FileTree';
import './ProductSpaces.css';

const SPACES = [
  { id: 'home', label: 'Living Mind', icon: Activity },
  { id: 'workbench', label: 'Workbench', icon: BriefcaseBusiness },
  { id: 'governance', label: 'Governance', icon: ShieldCheck },
  { id: 'history', label: 'History', icon: Clock3 },
];

function valueOrUnavailable(value) {
  return value === null || value === undefined || value === '' ? 'Unavailable' : String(value);
}

function Metric({ label, value, status = 'measured' }) {
  return (
    <div className="gagos-space__metric">
      <span>{label}</span>
      <strong>{valueOrUnavailable(value)}</strong>
      <small>{status}</small>
    </div>
  );
}

function LivingMind({ mirror }) {
  const bootFacts = mirror.bootFacts || {};
  const state = mirror.status === 'stale' ? 'stale' : mirror.status;
  const modelsEngaged = mirror.activeModels.length > 0
    ? mirror.activeModels.length
    : bootFacts.models_engaged ?? null;
  return (
    <section className="gagos-space__home" aria-label="Living Mind">
      <div className="gagos-space__eyebrow">Home · measured self-portrait</div>
      <h2>Living Mind</h2>
      <p className="gagos-space__lede">
        The organism is beautiful at rest; operational claims appear only when the control plane reports them.
      </p>
      <div className="gagos-space__metrics">
        <Metric label="Control plane" value={state} status={state === 'online' ? 'measured' : state === 'stale' ? 'stale' : 'unavailable'} />
        <Metric label="Directive phase" value={mirror.phase} />
        <Metric label="Active missions" value={mirror.activeMissions.length} />
        <Metric label="Active workers" value={mirror.activeWorkers.length} />
        <Metric label="Models participating" value={modelsEngaged} />
        <Metric label="Approval" value={mirror.approvalRequired ? 'required' : 'none reported'} status={mirror.approvalRequired ? 'measured' : 'measured'} />
      </div>
      <div className={`gagos-space__portrait gagos-space__portrait--${state}`}>
        <span className="gagos-space__pulse" aria-hidden="true" />
        <div>
          <strong>{state === 'online' ? 'Sovereign spine connected' : state === 'stale' ? 'Portrait is stale' : 'Control plane unavailable'}</strong>
          <span>{mirror.lastAnnouncement || 'Ambient life continues without claiming backend activity.'}</span>
        </div>
      </div>
      <div className="gagos-space__sr" aria-live="polite">{mirror.lastAnnouncement || `Control plane ${state}.`}</div>
    </section>
  );
}

function Workbench({ activeFile, setActiveFile }) {
  const [treeOpen, setTreeOpen] = useState(false);
  return (
    <section className="gagos-space__workbench" aria-label="Workbench">
      <div className="gagos-space__eyebrow">Workbench · materialized work surfaces</div>
      <h2>Workbench</h2>
      <div className="gagos-space__workbench-actions">
        <button type="button" onClick={() => setTreeOpen(true)}><FolderTree size={14} /> Open project tree</button>
        <span>Terminal: use the existing terminal control or Ctrl+`</span>
      </div>
      <div className="gagos-space__surface-grid">
        <article><strong>Project tree</strong><span>{treeOpen ? 'Open' : 'Closed by default'}</span></article>
        <article><strong>Code editor</strong><span>{activeFile ? activeFile.name || activeFile.path : 'Select a file from the tree'}</span></article>
        <article><strong>Diff</strong><span>Unavailable until a staged diff is reported</span></article>
        <article><strong>Verification output</strong><span>Unavailable until a verification event arrives</span></article>
      </div>
      {treeOpen ? <FileTree onClose={() => setTreeOpen(false)} onOpenFile={setActiveFile} /> : null}
      {activeFile ? <CodeEditor file={activeFile} onClose={() => setActiveFile(null)} /> : null}
    </section>
  );
}

function History({ mirror }) {
  const events = [...mirror.recentEvents].reverse();
  return (
    <section className="gagos-space__history" aria-label="History">
      <div className="gagos-space__eyebrow">History · bounded event journal</div>
      <h2>History</h2>
      <p className="gagos-space__lede">A bounded replay of measured operational observations. Evidence and provenance appear only when emitted by the backend.</p>
      {events.length === 0 ? (
        <div className="gagos-space__empty">No operational events have been reported.</div>
      ) : (
        <ol className="gagos-space__timeline">
          {events.map((event) => (
            <li key={`${event.id}-${event.type}`}>
              <time dateTime={event.occurredAt}>{new Date(event.occurredAt).toLocaleTimeString()}</time>
              <div><strong>{event.type}</strong><span>{event.summary}</span></div>
              {event.missionId ? <small>mission · {event.missionId}</small> : null}
              {event.workerId ? <small>worker · {event.workerId}</small> : null}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export default function ProductSpaces() {
  const [space, setSpace] = useState('home');
  const [activeFile, setActiveFile] = useState(null);
  const mirror = useMirrorStore();
  const current = SPACES.find((item) => item.id === space) || SPACES[0];

  return (
    <section className="gagos-spaces" aria-label="GAGOS product spaces">
      <nav className="gagos-spaces__nav" aria-label="Product spaces">
        {SPACES.map(({ id, label, icon: Icon }) => (
          <button key={id} type="button" className={space === id ? 'is-active' : ''} onClick={() => setSpace(id)} aria-current={space === id ? 'page' : undefined}>
            <Icon size={14} aria-hidden="true" />{label}
          </button>
        ))}
      </nav>
      <div className="gagos-spaces__content">
        {current.id === 'home' ? <LivingMind mirror={mirror} /> : null}
        {current.id === 'workbench' ? <Workbench activeFile={activeFile} setActiveFile={setActiveFile} /> : null}
        {current.id === 'governance' ? (
          <section className="gagos-space__governance" aria-label="Governance">
            <div className="gagos-space__eyebrow">Governance · actual Council state</div>
            <h2>Governance</h2>
            <p className="gagos-space__mobile-note">Privileged governance is read-only on narrow screens.</p>
            <CouncilDashboard />
          </section>
        ) : null}
        {current.id === 'history' ? <History mirror={mirror} /> : null}
      </div>
    </section>
  );
}
