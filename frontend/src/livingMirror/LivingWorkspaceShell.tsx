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
import { presentHistoryEvent } from './experience/historyPresentation';
import { isWorkspacePanelVisible } from './experience/workspaceVisibility';
import GuidedTaskPanel from './GuidedTaskPanel';
import { detectSystemReducedMotion } from './motionPreference';
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

const expertSurfaceGroups = [
  {
    id: 'task',
    label: 'Task',
    surfaces: [['missions', 'Missions'], ['files', 'Project files'], ['skills', 'Experience'], ['history', 'Recent observations']],
  },
  {
    id: 'intelligence',
    label: 'Intelligence',
    surfaces: [['workforce', 'Local workforce'], ['hiring', 'Hiring'], ['deliberation', 'Council deliberation']],
  },
  {
    id: 'authority',
    label: 'Authority',
    surfaces: [['governance', 'Governance'], ['settings', 'Settings'], ['profile', 'Human preferences']],
  },
  {
    id: 'memory',
    label: 'Memory',
    surfaces: [['memory', 'Memory'], ['stigmergy', 'Memory trails']],
  },
  {
    id: 'evidence',
    label: 'Evidence',
    surfaces: [['maintenance', 'Maintenance'], ['vulture', 'Maintenance feed'], ['ecosystem', 'Resources & ecosystem'], ['terminal', 'Terminal']],
  },
] as const;

const guidedSurfaces = [
  ['missions', 'Tasks'],
  ['files', 'Project files'],
  ['history', 'Recent activity'],
] as const;

const NARROW_VIEWPORT_QUERY = '(max-width: 767px)';

function readNarrowViewport(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia(NARROW_VIEWPORT_QUERY).matches;
}

function History({ guided }: { guided: boolean }) {
  const mirror = useMirrorStore();
  return <section><h3>{guided ? 'Recent activity' : 'Recent observations'}</h3><p>{guided ? 'A short record of what GAGOS has measured in this session.' : 'Up to 256 observations retained in this browser session. Durable mission reports are available under Missions.'}</p>
    {mirror.recentEvents.length === 0 && <p>No events received in this session.</p>}
    <ol className="lm-history">{[...mirror.recentEvents].reverse().map((event) => {
      const presented = presentHistoryEvent(event, guided ? 'guided' : 'expert');
      return <li key={event.id}>
        <strong>{presented.label}</strong><p>{presented.message}</p>
        <small>{presented.occurredAt ? new Date(presented.occurredAt).toLocaleString() : 'Observation time unavailable'} · Received {new Date(presented.receivedAt).toLocaleTimeString()}</small>
        {presented.technical?.missionId && <p>Mission <code>{presented.technical.missionId}</code></p>}
        {presented.technical?.workerId && <p>Worker <code>{presented.technical.workerId}</code></p>}
      </li>;
    })}</ol>
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

function PanelContent({ panel, experienceMode }: { panel: WorkspacePanel; experienceMode: ExperienceMode }) {
  const onClose = () => closeWorkspace(panel.id);
  switch (panel.kind) {
    case 'missions': return experienceMode === 'beginner' ? <GuidedTaskPanel /> : <Missions />;
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
    case 'history': return <History guided={experienceMode === 'beginner'} />;
    default: return <p>This workspace is unavailable.</p>;
  }
}

export function LivingWorkspaceShell({ experienceMode = 'beginner' }: { experienceMode?: ExperienceMode }) {
  const snapshot = useTabStore();
  const [listOpen, setListOpen] = useState(false);
  const [narrowViewport, setNarrowViewport] = useState(readNarrowViewport);
  const reducedMotion = useReducedMotion();
  // The generated reduced-motion store may be unable to subscribe in an SSR
  // or test-like environment without matchMedia. Keep the product-owned
  // control responsive immediately after its own explicit toggle; the store
  // remains the source for OS preference changes when available.
  const [manualMotionPaused, setManualMotionPaused] = useState(false);
  const motionPaused = reducedMotion || manualMotionPaused;
  const systemReducedMotion = detectSystemReducedMotion();
  const heading = useRef<HTMLHeadingElement>(null);
  const conversationButton = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const panels = snapshot.panels ?? [];
  const focusedPanel = panels.find((panel) => panel.id === snapshot.focusId && panel.open);
  const focused = focusedPanel && isWorkspacePanelVisible(focusedPanel, experienceMode) ? focusedPanel : undefined;
  const artifact = snapshot.tabs.find((tab) => tab.id === snapshot.focusId && tab.kind === 'content' && tab.lifecycle !== 'retracting');
  const handles = [
    ...panels.filter((p) => p.open && isWorkspacePanelVisible(p, experienceMode)).map((p) => ({ id: p.id, title: p.title, seat: p.seatIndex, pinned: p.pinned })),
    ...snapshot.tabs.filter((t) => t.kind !== 'input' && t.lifecycle !== 'retracting').map((t) => ({ id: t.id, title: t.content?.filepath ?? 'Approval review', seat: t.seatIndex, pinned: t.pinned })),
  ];
  const working = !!focused || !!artifact;
  const wasWorking = useRef(working);
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined;
    const media = window.matchMedia(NARROW_VIEWPORT_QUERY);
    const sync = () => setNarrowViewport(media.matches);
    sync();
    if (typeof media.addEventListener === 'function') {
      media.addEventListener('change', sync);
      return () => media.removeEventListener('change', sync);
    }
    media.addListener?.(sync);
    return () => media.removeListener?.(sync);
  }, []);
  const rememberReturnFocus = (trigger?: HTMLElement | null) => {
    const active = trigger ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    returnFocus.current = active === document.body ? null : active;
  };
  const restoreWorkspaceFocus = () => {
    const target = returnFocus.current;
    returnFocus.current = null;
    const removedOnDismiss = target?.closest('.lm-workspace-rail, .lm-workspace-list, .lm-surface');
    const unavailable = target?.closest('[hidden], [inert], [aria-hidden="true"], details:not([open])');
    if (target?.isConnected && !removedOnDismiss && !unavailable && !target.matches(':disabled')) {
      target.focus({ preventScroll: true });
      return;
    }
    conversationButton.current?.focus({ preventScroll: true });
  };
  const open = (id: string, title: string, trigger?: HTMLElement | null) => {
    rememberReturnFocus(trigger);
    openWorkspacePanel(id, title);
  };
  const focusFromControl = (id: string, trigger: HTMLElement) => {
    returnFocus.current = trigger;
    focusWorkspace(id);
  };
  const dismiss = () => {
    if (snapshot.focusId) closeWorkspace(snapshot.focusId);
  };
  useEffect(() => {
    if (working) {
      heading.current?.focus({ preventScroll: true });
    } else if (wasWorking.current) {
      restoreWorkspaceFocus();
    }
    wasWorking.current = working;
  }, [snapshot.focusId, working]);
  useEffect(() => {
    const handle = (event: KeyboardEvent) => {
      if (experienceMode !== 'expert' || event.defaultPrevented || event.key !== '`' || !event.ctrlKey) return;
      event.preventDefault();
      rememberReturnFocus();
      openWorkspacePanel('terminal', 'Terminal');
    };
    window.addEventListener('keydown', handle); return () => window.removeEventListener('keydown', handle);
  }, [experienceMode]);
  const renderExpertButtons = (group: typeof expertSurfaceGroups[number]) => group.surfaces.map(([id, title]: readonly [string, string]) => (
    <button key={id} type="button" aria-current={focused?.id === id ? 'page' : undefined} onClick={(event) => open(id, title, event.currentTarget)}>{title}</button>
  ));
  const renderDesktopExpertGroups = () => expertSurfaceGroups.map((group, index) => {
    const buttons = renderExpertButtons(group);
    return index === 0
      ? <div className="lm-expert-group lm-expert-group--primary" key={group.id} aria-label={group.label}><span className="lm-expert-group__label">{group.label}</span>{buttons}</div>
      : <details className="lm-expert-group" key={group.id}><summary>{group.label}</summary><div className="lm-expert-group__items">{buttons}</div></details>;
  });
  const renderMobileExpertGroups = () => (
    <details className="lm-expert-mobile-surfaces">
      <summary>Expert surfaces</summary>
      <div className="lm-expert-mobile-surfaces__groups">
        {expertSurfaceGroups.map((group) => (
          <details className="lm-expert-mobile-surface-group" key={group.id}>
            <summary>{group.label}</summary>
            <div className="lm-expert-mobile-surface-group__items">{renderExpertButtons(group)}</div>
          </details>
        ))}
      </div>
    </details>
  );
  return <div className="lm-shell" data-experience-mode={experienceMode} data-motion-reduced={motionPaused ? 'true' : 'false'}>
    <header className="lm-header">
      <div className="lm-brand lm-expert-only"><h1>GAGOS</h1><span className="lm-subtitle">Local-first intelligence. Human authority.</span></div>
      <EmergencyControl guided={experienceMode === 'beginner'} />
    </header>
    <nav className="lm-navigation" aria-label="Workspaces">
      <button ref={conversationButton} type="button" aria-current={!working ? 'page' : undefined} onClick={(event) => {
        returnFocus.current = event.currentTarget;
        focusWorkspace(null);
      }}>Conversation</button>
      {experienceMode === 'expert'
        ? narrowViewport ? renderMobileExpertGroups() : renderDesktopExpertGroups()
        : guidedSurfaces.map(([id, title]) => <button key={id} type="button" aria-current={focused?.id === id ? 'page' : undefined} onClick={(event) => open(id, title, event.currentTarget)}>{title}</button>)}
      <button
        type="button"
        disabled={systemReducedMotion}
        aria-pressed={motionPaused}
        onClick={() => {
          const next = !motionPaused;
          setManualMotionPaused(next);
          setAmbientMotionPaused(next);
        }}
      >
        {systemReducedMotion ? 'Motion reduced by system' : motionPaused ? 'Resume ambient motion' : 'Pause ambient motion'}
      </button>
    </nav>
    <MirrorConnectionNotice experienceMode={experienceMode} onOpenAuthority={experienceMode === 'expert' ? (trigger) => open('governance', 'Governance', trigger) : undefined} />
    <aside className="lm-workspace-rail" aria-label="Spinal workspace anchors">
      {handles.slice(0, 4).map((handle) => <button type="button" key={handle.id} aria-current={snapshot.focusId === handle.id ? 'true' : undefined} onClick={(event) => focusFromControl(handle.id, event.currentTarget)}>
        <span className="lm-vertebra" aria-hidden="true" />{handle.title}{handle.pinned ? ' · pinned' : ''}
      </button>)}
      {handles.length > 0 && <button type="button" aria-expanded={listOpen} onClick={() => setListOpen(!listOpen)}>All {handles.length} workspaces</button>}
      {listOpen && <div className="lm-workspace-list">{handles.map((handle) => <button key={handle.id} type="button" onClick={(event) => { focusFromControl(handle.id, event.currentTarget); setListOpen(false); }}>{handle.title} · Anchor {handle.seat ?? 'unassigned'}</button>)}</div>}
    </aside>
    <section className="lm-surface" hidden={!working} aria-label="Selected workspace" onKeyDown={(event) => {
      if (event.key === 'Escape' && !event.defaultPrevented && !(event.target as HTMLElement).closest('.monaco-editor')) { event.stopPropagation(); dismiss(); }
    }}>
      <header className="lm-surface__header"><h2 ref={heading} tabIndex={-1}>{focused?.title ?? artifact?.content?.filepath}</h2>
        <button type="button" onClick={() => snapshot.focusId && pinWorkspace(snapshot.focusId)}>{(focused ?? artifact)?.pinned ? 'Unpin' : 'Pin'}</button>
        <button type="button" onClick={dismiss} aria-label="Close workspace">Close</button>
      </header>
      <WorkspaceHostContext.Provider value={true}>
        {focused && <div key={focused.id} className="lm-surface__body">
          <Suspense fallback={<p role="status">Loading {focused.title}…</p>}><PanelContent panel={focused} experienceMode={experienceMode} /></Suspense>
        </div>}
      </WorkspaceHostContext.Provider>
      {artifact?.content && <div className="lm-surface__body"><p>Generated artifact · Project effects require separate receipts.</p><pre className="lm-artifact" tabIndex={0}>{artifact.content.code}</pre>
        {artifact.content.verifyOutput && <details><summary>Reported check output</summary><pre>{artifact.content.verifyOutput}</pre></details>}
      </div>}
    </section>
  </div>;
}
