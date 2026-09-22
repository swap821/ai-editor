import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { API_HEADERS } from '../config';
import { useTabStore, openWorkspacePanel, focusWorkspace, closeWorkspace, pinWorkspace, type WorkspacePanel } from '../superbrain/lib/tabStore';
import { useMirrorStore } from '../superbrain/lib/mirrorStore';
import { WorkspaceHostContext } from './WorkspaceHostContext';
import { EmergencyControl } from './EmergencyControl';
import { MirrorConnectionNotice } from './MirrorConnectionNotice';
import { ResourceNotice } from './ResourceNotice';
import { useResource } from './resource';
import { isRecord } from './contracts';
import { useReducedMotion, setAmbientMotionPaused } from '../superbrain/lib/reducedMotion';
import type { ExperienceMode } from './experienceMode';
import './livingMirror.css';

const Council = lazy(() => import('../workbench/CouncilDashboard'));
const Missions = lazy(() => import('../workbench/MissionControlPanel'));
const Skills = lazy(() => import('../workbench/SkillLibraryPanel'));
const Files = lazy(() => import('../workbench/FileTree'));
const Editor = lazy(() => import('../workbench/CodeEditor'));
const Memory = lazy(() => import('../workbench/MemoryBrowser'));
const Hiring = lazy(() => import('../workbench/IntelligenceHiringPanel'));
const Workforce = lazy(() => import('../workbench/LocalWorkforcePanel'));
const Maintenance = lazy(() => import('../workbench/MaintenanceCenterPanel'));
const Settings = lazy(() => import('../workbench/SettingsPanel'));
const Profile = lazy(() => import('../workbench/OperatorProfileCard'));
const Stigmergy = lazy(() => import('../workbench/StigmergyPanel'));
const Vulture = lazy(() => import('../workbench/VultureFeed'));
const Ecosystem = lazy(() => import('../workbench/EcosystemDashboard'));
const Deliberation = lazy(() => import('../workbench/CouncilDeliberationPanel'));
const Terminal = lazy(() => import('../workbench/TerminalPanel'));

const surfaces = [
  ['missions', 'Missions'], ['governance', 'Governance'], ['files', 'Project files'], ['skills', 'Experience'],
  ['memory', 'Memory'], ['workforce', 'Local workforce'], ['hiring', 'Hiring'], ['maintenance', 'Maintenance'],
  ['history', 'Recent observations'], ['settings', 'Settings'], ['profile', 'Human preferences'], ['stigmergy', 'Memory trails'],
  ['vulture', 'Maintenance feed'], ['ecosystem', 'Resources & ecosystem'], ['deliberation', 'Council deliberation'], ['terminal', 'Terminal'],
] as const;

function History() {
  const mirror = useMirrorStore();
  return <section><h3>Recent observations</h3><p>Up to 256 observations retained in this browser session. Durable mission reports are available under Missions.</p>
    {mirror.recentEvents.length === 0 && <p>No events received in this session.</p>}
    <ol className="lm-history">{[...mirror.recentEvents].reverse().map((event) => <li key={event.id}>
      <strong>{event.type}</strong><p>{event.summary}</p>
      <small>{event.occurredAt ? new Date(event.occurredAt).toLocaleString() : 'Observation time unavailable'} · Received {new Date(event.receivedAt).toLocaleTimeString()}</small>
      {event.missionId && <p>Mission <code>{event.missionId}</code></p>}
      {event.workerId && <p>Worker <code>{event.workerId}</code></p>}
    </li>)}</ol>
  </section>;
}

function parseFile(value: unknown) {
  if (!isRecord(value) || typeof value.content !== 'string') throw new Error('File content unavailable.');
  return { content: value.content };
}
const neverEmpty = () => false;
export function FileWorkspace({ panel }: { panel: WorkspacePanel }) {
  const path = panel.file!.path;
  const request = useMemo(() => ({ method: 'POST', headers: { ...API_HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }) }), [path]);
  const resource = useResource('/api/v1/files/read', parseFile, neverEmpty, request);
  return resource.data ? <Editor key={path} file={{ ...panel.file!, content: resource.data.content }} onClose={() => closeWorkspace(panel.id)} />
    : <ResourceNotice resource={resource} empty="File content unavailable." />;
}

function PanelContent({ panel }: { panel: WorkspacePanel }) {
  const onClose = () => closeWorkspace(panel.id);
  switch (panel.kind) {
    case 'missions': return <Missions />;
    case 'governance': return <Council />;
    case 'skills': return <Skills />;
    case 'files': return <Files onClose={onClose} onOpenFile={(file) => openWorkspacePanel(`file:${file.path}`, file.name ?? file.path, 'file', file)} />;
    case 'file': return <FileWorkspace panel={panel} />;
    case 'memory': return <Memory onClose={onClose} />;
    case 'workforce': return <Workforce />;
    case 'hiring': return <Hiring />;
    case 'maintenance': return <Maintenance />;
    case 'settings': return <Settings onClose={onClose} />;
    case 'profile': return <Profile />;
    case 'stigmergy': return <Stigmergy onClose={onClose} />;
    case 'vulture': return <Vulture onClose={onClose} />;
    case 'ecosystem': return <Ecosystem onClose={onClose} />;
    case 'deliberation': return <Deliberation onClose={onClose} />;
    case 'terminal': return <Terminal embedded />;
    case 'history': return <History />;
    default: return <p>This workspace is unavailable.</p>;
  }
}

export function LivingWorkspaceShell({ experienceMode = 'beginner' }: { experienceMode?: ExperienceMode }) {
  const snapshot = useTabStore();
  const [listOpen, setListOpen] = useState(false);
  const reducedMotion = useReducedMotion();
  const systemReducedMotion = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const heading = useRef<HTMLHeadingElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const panels = snapshot.panels ?? [];
  const focused = panels.find((panel) => panel.id === snapshot.focusId && panel.open);
  const artifact = snapshot.tabs.find((tab) => tab.id === snapshot.focusId && tab.kind === 'content' && tab.lifecycle !== 'retracting');
  const handles = [
    ...panels.filter((p) => p.open).map((p) => ({ id: p.id, title: p.title, seat: p.seatIndex, pinned: p.pinned })),
    ...snapshot.tabs.filter((t) => t.kind !== 'input' && t.lifecycle !== 'retracting').map((t) => ({ id: t.id, title: t.content?.filepath ?? 'Approval review', seat: t.seatIndex, pinned: t.pinned })),
  ];
  const working = !!focused || !!artifact;
  useEffect(() => {
    if (working) heading.current?.focus({ preventScroll: true });
  }, [snapshot.focusId, working]);
  const open = (id: string, title: string) => { returnFocus.current = document.activeElement as HTMLElement; openWorkspacePanel(id, title); };
  const dismiss = () => { if (snapshot.focusId) closeWorkspace(snapshot.focusId); returnFocus.current?.focus(); };
  useEffect(() => {
    const handle = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.key !== '`' || !event.ctrlKey) return;
      event.preventDefault(); openWorkspacePanel('terminal', 'Terminal');
    };
    window.addEventListener('keydown', handle); return () => window.removeEventListener('keydown', handle);
  }, []);
  return <div className="lm-shell" data-experience-mode={experienceMode}>
    <header className="lm-header">
      <div className="lm-brand lm-expert-only"><h1>GAGOS</h1><span className="lm-subtitle">Local-first intelligence. Human authority.</span></div>
      <EmergencyControl />
    </header>
    <nav className="lm-navigation" aria-label="Workspaces">
      <button type="button" aria-current={!working ? 'page' : undefined} onClick={() => focusWorkspace(null)}>Conversation</button>
      {surfaces.slice(0, 4).map(([id, title]) => <button key={id} type="button" aria-current={focused?.id === id ? 'page' : undefined} onClick={() => open(id, title)}>{title}</button>)}
      <label className="lm-more">More<select aria-label="More workspaces" value="" onChange={(event) => { const surface = surfaces.find(([id]) => id === event.target.value); if (surface) open(surface[0], surface[1]); }}>
        <option value="">Choose a surface</option>{surfaces.slice(4).map(([id, title]) => <option value={id} key={id}>{title}</option>)}
      </select></label>
      <button type="button" disabled={systemReducedMotion} aria-pressed={reducedMotion} onClick={() => setAmbientMotionPaused(!reducedMotion)}>
        {systemReducedMotion ? 'Motion reduced by system' : reducedMotion ? 'Resume ambient motion' : 'Pause ambient motion'}
      </button>
    </nav>
    <MirrorConnectionNotice experienceMode={experienceMode} onOpenAuthority={() => open('governance', 'Governance')} />
    <aside className="lm-workspace-rail" aria-label="Spinal workspace anchors">
      {handles.slice(0, 4).map((handle) => <button type="button" key={handle.id} aria-current={snapshot.focusId === handle.id ? 'true' : undefined} onClick={() => focusWorkspace(handle.id)}>
        <span className="lm-vertebra" aria-hidden="true" />{handle.title}{handle.pinned ? ' · pinned' : ''}
      </button>)}
      {handles.length > 0 && <button type="button" aria-expanded={listOpen} onClick={() => setListOpen(!listOpen)}>All {handles.length} workspaces</button>}
      {listOpen && <div className="lm-workspace-list">{handles.map((handle) => <button key={handle.id} type="button" onClick={() => { focusWorkspace(handle.id); setListOpen(false); }}>{handle.title} · Anchor {handle.seat ?? 'unassigned'}</button>)}</div>}
    </aside>
    <section className="lm-surface" hidden={!working} aria-label="Selected workspace" onKeyDown={(event) => {
      if (event.key === 'Escape' && !event.defaultPrevented && !(event.target as HTMLElement).closest('.monaco-editor')) { event.stopPropagation(); dismiss(); }
    }}>
      <header className="lm-surface__header"><h2 ref={heading} tabIndex={-1}>{focused?.title ?? artifact?.content?.filepath}</h2>
        <button type="button" onClick={() => snapshot.focusId && pinWorkspace(snapshot.focusId)}>{(focused ?? artifact)?.pinned ? 'Unpin' : 'Pin'}</button>
        <button type="button" onClick={dismiss} aria-label="Close workspace">Close</button>
      </header>
      <WorkspaceHostContext.Provider value={true}>
        {panels.map((panel) => <div key={panel.id} className="lm-surface__body" hidden={panel.id !== focused?.id}>
          <Suspense fallback={<p role="status">Loading {panel.title}…</p>}><PanelContent panel={panel} /></Suspense>
        </div>)}
      </WorkspaceHostContext.Provider>
      {artifact?.content && <div className="lm-surface__body"><p>Generated artifact · Project effects require separate receipts.</p><pre className="lm-artifact" tabIndex={0}>{artifact.content.code}</pre>
        {artifact.content.verifyOutput && <details><summary>Reported check output</summary><pre>{artifact.content.verifyOutput}</pre></details>}
      </div>}
    </section>
  </div>;
}
