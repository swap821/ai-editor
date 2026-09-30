import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { API_HEADERS } from '../config';
import { useTabStore, getTabStoreSnapshot, openWorkspacePanel, focusWorkspace, closeWorkspace, clearMaterializedTab, pinWorkspace, type WorkspacePanel } from '../superbrain/lib/tabStore';
import { useMirrorStore } from '../superbrain/lib/mirrorStore';
import { getSovereignStatus, subscribeSovereignStatus } from '../superbrain/lib/sovereignIdentity';
import { WorkspaceHostContext } from './WorkspaceHostContext';
import { PersistentWorkspaceBody } from './PersistentWorkspaceBody';
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
const COMPACT_WORKSPACE_QUERY = '(max-width: 360px)';

function readNarrowViewport(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia(NARROW_VIEWPORT_QUERY).matches;
}

function readCompactWorkspaceViewport(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia(COMPACT_WORKSPACE_QUERY).matches;
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
    case 'terminal': return <Terminal embedded onClose={onClose} />;
    case 'history': return <History guided={experienceMode === 'beginner'} />;
    default: return <p>This workspace is unavailable.</p>;
  }
}

export function LivingWorkspaceShell({ experienceMode = 'beginner' }: { experienceMode?: ExperienceMode }) {
  const snapshot = useTabStore();
  const [listOpen, setListOpen] = useState(false);
  const [narrowViewport, setNarrowViewport] = useState(readNarrowViewport);
  const [compactWorkspaceViewport, setCompactWorkspaceViewport] = useState(readCompactWorkspaceViewport);
  const [expandedWorkspaceId, setExpandedWorkspaceId] = useState<string | null>(null);
  const reducedMotion = useReducedMotion();
  // The generated reduced-motion store may be unable to subscribe in an SSR
  // or test-like environment without matchMedia. Keep the product-owned
  // control responsive immediately after its own explicit toggle; the store
  // remains the source for OS preference changes when available.
  const [manualMotionPaused, setManualMotionPaused] = useState(false);
  const motionPaused = reducedMotion || manualMotionPaused;
  const systemReducedMotion = detectSystemReducedMotion();
  const heading = useRef<HTMLHeadingElement>(null);
  const workspaceContent = useRef<HTMLDivElement>(null);
  const workspaceToggle = useRef<HTMLButtonElement>(null);
  const conversationButton = useRef<HTMLButtonElement>(null);
  const navigation = useRef<HTMLElement>(null);
  const workspaceRail = useRef<HTMLElement>(null);
  const mobileMenu = useRef<HTMLDetailsElement>(null);
  const previousNarrowViewport = useRef(narrowViewport);
  const focusNavigationAfterResize = useRef(false);
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
  const compactWorkspace = experienceMode === 'expert' && compactWorkspaceViewport;
  const workspaceCollapsed = compactWorkspace && expandedWorkspaceId !== snapshot.focusId;
  useLayoutEffect(() => {
    // Desktop can scroll its long toolbar. Do not carry that offset into the
    // phone's two-control layout; workspace content owns its own scroll state.
    if (navigation.current) navigation.current.scrollLeft = 0;
    if (focusNavigationAfterResize.current) {
      conversationButton.current?.focus({ preventScroll: true });
      focusNavigationAfterResize.current = false;
    }
  }, [narrowViewport]);
  const wasWorking = useRef(working);
  const workspaceOwner = useRef(getSovereignStatus());
  useEffect(() => subscribeSovereignStatus((status) => {
    // An outage is not sign-out. Keep the last measured owner through unknown
    // readings; release retained private views on a measured identity change.
    if (status.measured !== 'measured') return;
    const previous = workspaceOwner.current;
    workspaceOwner.current = status;
    if (previous.measured !== 'measured' || (previous.operatorId === status.operatorId
      && previous.sessionActive === status.sessionActive)) return;
    const current = getTabStoreSnapshot();
    for (const panel of current.panels ?? []) if (panel.open) closeWorkspace(panel.id);
    clearMaterializedTab();
  }), []);
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined;
    const narrowMedia = window.matchMedia(NARROW_VIEWPORT_QUERY);
    const compactMedia = window.matchMedia(COMPACT_WORKSPACE_QUERY);
    const sync = () => {
      if (narrowMedia.matches !== previousNarrowViewport.current) {
        // Responsive navigation replaces its controls. Preserve keyboard
        // access only when focus was there; never steal focus from a draft.
        focusNavigationAfterResize.current = !!(navigation.current?.contains(document.activeElement)
          || workspaceRail.current?.contains(document.activeElement));
        previousNarrowViewport.current = narrowMedia.matches;
      }
      setNarrowViewport(narrowMedia.matches);
      setCompactWorkspaceViewport(compactMedia.matches);
    };
    sync();
    const subscribe = (media: MediaQueryList) => {
      if (typeof media.addEventListener === 'function') media.addEventListener('change', sync);
      else media.addListener?.(sync);
    };
    const unsubscribe = (media: MediaQueryList) => {
      if (typeof media.removeEventListener === 'function') media.removeEventListener('change', sync);
      else media.removeListener?.(sync);
    };
    subscribe(narrowMedia);
    subscribe(compactMedia);
    return () => {
      unsubscribe(narrowMedia);
      unsubscribe(compactMedia);
    };
  }, []);
  const rememberReturnFocus = (trigger?: HTMLElement | null) => {
    const active = trigger ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    returnFocus.current = active === document.body ? null : active;
  };
  const closeMobileExpertMenus = (trigger?: HTMLElement | null) => {
    const groupMenu = trigger?.closest<HTMLDetailsElement>('.lm-expert-mobile-surface-group');
    const surfacesMenu = trigger?.closest<HTMLDetailsElement>('.lm-expert-mobile-surfaces') ?? mobileMenu.current;
    if (groupMenu) groupMenu.open = false;
    if (surfacesMenu) surfacesMenu.open = false;
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
  const focusSelectedWorkspace = useCallback(() => {
    if (working) {
      if (workspaceCollapsed) workspaceToggle.current?.focus({ preventScroll: true });
      else heading.current?.focus({ preventScroll: true });
    } else {
      conversationButton.current?.focus({ preventScroll: true });
    }
  }, [working, workspaceCollapsed]);
  const open = (id: string, title: string, trigger?: HTMLElement | null) => {
    closeMobileExpertMenus(trigger);
    rememberReturnFocus(trigger);
    openWorkspacePanel(id, title);
    if (id === snapshot.focusId) focusSelectedWorkspace();
  };
  const focusFromControl = (id: string, trigger: HTMLElement) => {
    closeMobileExpertMenus(trigger);
    returnFocus.current = trigger;
    focusWorkspace(id);
    if (id === snapshot.focusId) focusSelectedWorkspace();
  };
  const dismiss = () => {
    if (snapshot.focusId) closeWorkspace(snapshot.focusId);
  };
  useEffect(() => {
    if (working) {
      focusSelectedWorkspace();
    } else if (wasWorking.current) {
      restoreWorkspaceFocus();
    } else if (returnFocus.current?.closest('details:not([open])')) {
      conversationButton.current?.focus({ preventScroll: true });
    }
    wasWorking.current = working;
  }, [snapshot.focusId, working, workspaceCollapsed, focusSelectedWorkspace]);
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
  const renderMotionControl = () => (
    <button
      type="button"
      disabled={systemReducedMotion}
      aria-pressed={motionPaused}
      onClick={() => {
        const next = !motionPaused;
        setManualMotionPaused(next);
        setAmbientMotionPaused(next);
      }}
    >{systemReducedMotion ? 'Motion reduced by system' : motionPaused ? 'Resume ambient motion' : 'Pause ambient motion'}</button>
  );
  const renderMobileExpertGroups = () => (
    <details ref={mobileMenu} className="lm-expert-mobile-surfaces" onKeyDown={(event) => {
      if (event.key !== 'Escape' || event.defaultPrevented) return;
      event.preventDefault();
      event.stopPropagation();
      event.currentTarget.open = false;
      event.currentTarget.querySelector('summary')?.focus({ preventScroll: true });
    }}>
      <summary><span>Workspaces</span>{handles.length > 0 && <span className="lm-expert-mobile-surfaces__count" aria-label={`${handles.length} open`}>{handles.length}</span>}</summary>
      <div className="lm-expert-mobile-surfaces__groups">
        {handles.length > 0 && <section className="lm-expert-mobile-open" aria-label="Open workspaces">
          <h3>Open workspaces</h3>
          {handles.map((handle) => <button type="button" key={handle.id} aria-current={snapshot.focusId === handle.id ? 'page' : undefined} onClick={(event) => focusFromControl(handle.id, event.currentTarget)}>
            {handle.title}{handle.pinned ? ' · pinned' : ''}
          </button>)}
        </section>}
        {expertSurfaceGroups.map((group) => (
          <details className="lm-expert-mobile-surface-group" key={group.id}>
            <summary>{group.label}</summary>
            <div className="lm-expert-mobile-surface-group__items">{renderExpertButtons(group)}</div>
          </details>
        ))}
        {renderMotionControl()}
      </div>
    </details>
  );
  return <div className="lm-shell" data-experience-mode={experienceMode} data-motion-reduced={motionPaused ? 'true' : 'false'}>
    <header className="lm-header">
      <div className="lm-brand lm-expert-only"><h1>GAGOS</h1><span className="lm-subtitle">Local-first intelligence. Human authority.</span></div>
      <EmergencyControl guided={experienceMode === 'beginner'} />
    </header>
    <nav ref={navigation} className="lm-navigation" aria-label="Workspaces">
      <button ref={conversationButton} type="button" aria-current={!working ? 'page' : undefined} onClick={(event) => {
        closeMobileExpertMenus(event.currentTarget);
        returnFocus.current = event.currentTarget;
        focusWorkspace(null);
      }}>Conversation</button>
      {experienceMode === 'expert'
        ? narrowViewport ? renderMobileExpertGroups() : renderDesktopExpertGroups()
        : guidedSurfaces.map(([id, title]) => <button key={id} type="button" aria-current={focused?.id === id ? 'page' : undefined} onClick={(event) => open(id, title, event.currentTarget)}>{title}</button>)}
      {!(narrowViewport && experienceMode === 'expert') && renderMotionControl()}
    </nav>
    <MirrorConnectionNotice experienceMode={experienceMode} onOpenAuthority={experienceMode === 'expert' ? (trigger) => open('governance', 'Governance', trigger) : undefined} />
    {!(narrowViewport && experienceMode === 'expert') && <aside ref={workspaceRail} className="lm-workspace-rail" aria-label="Spinal workspace anchors">
      {handles.slice(0, 4).map((handle) => <button type="button" key={handle.id} aria-current={snapshot.focusId === handle.id ? 'true' : undefined} onClick={(event) => focusFromControl(handle.id, event.currentTarget)}>
        <span className="lm-vertebra" aria-hidden="true" />{handle.title}{handle.pinned ? ' · pinned' : ''}
      </button>)}
      {handles.length > 0 && <button type="button" aria-expanded={listOpen} onClick={() => setListOpen(!listOpen)}>All {handles.length} workspaces</button>}
      {listOpen && <div className="lm-workspace-list">{handles.map((handle) => <button key={handle.id} type="button" onClick={(event) => { focusFromControl(handle.id, event.currentTarget); setListOpen(false); }}>{handle.title} · Anchor {handle.seat ?? 'unassigned'}</button>)}</div>}
    </aside>}
    <section className="lm-surface" data-workspace-collapsed={workspaceCollapsed ? 'true' : undefined} hidden={!working} aria-label="Selected workspace" onKeyDown={(event) => {
      if (event.key === 'Escape' && !event.defaultPrevented && !(event.target as HTMLElement).closest('.monaco-editor')) { event.stopPropagation(); dismiss(); }
    }}>
      <header className="lm-surface__header"><h2 ref={heading} tabIndex={-1}>{focused?.title ?? artifact?.content?.filepath}</h2>
        {compactWorkspace && <button
          ref={workspaceToggle}
          type="button"
          aria-label={workspaceCollapsed ? 'Expand workspace' : 'Collapse workspace'}
          aria-controls="lm-surface-content"
          aria-expanded={!workspaceCollapsed}
          onClick={(event) => {
            const expand = workspaceCollapsed;
            if (!expand && workspaceContent.current?.contains(document.activeElement)) {
              event.currentTarget.focus({ preventScroll: true });
            }
            setExpandedWorkspaceId(expand ? snapshot.focusId : null);
          }}
        >{workspaceCollapsed ? 'Expand' : 'Collapse'}</button>}
        <button type="button" onClick={() => snapshot.focusId && pinWorkspace(snapshot.focusId)}>{(focused ?? artifact)?.pinned ? 'Unpin' : 'Pin'}</button>
        <button type="button" onClick={dismiss} aria-label="Close workspace">Close</button>
      </header>
      <div
        id="lm-surface-content"
        ref={workspaceContent}
        className="lm-surface__content"
        hidden={workspaceCollapsed}
      >
        <WorkspaceHostContext.Provider value={true}>
          {panels.filter((panel) => panel.open).map((panel) => <PersistentWorkspaceBody
            key={panel.id}
            className={panel.kind === 'terminal' ? 'lm-surface__body--terminal' : undefined}
            selected={focused?.id === panel.id}
            visible={focused?.id === panel.id && !workspaceCollapsed}
          >
            <Suspense fallback={<p role="status">Loading {panel.title}…</p>}><PanelContent panel={panel} experienceMode={experienceMode} /></Suspense>
          </PersistentWorkspaceBody>)}
        </WorkspaceHostContext.Provider>
        {snapshot.tabs.filter((tab) => tab.kind === 'content' && tab.lifecycle !== 'retracting' && tab.content).map((tab) => <PersistentWorkspaceBody
          key={tab.id}
          selected={artifact?.id === tab.id}
          visible={artifact?.id === tab.id && !workspaceCollapsed}
        ><p>Generated artifact · Project effects require separate receipts.</p><pre className="lm-artifact" tabIndex={0}>{tab.content!.code}</pre>
          {tab.content!.verifyOutput && <details><summary>Reported check output</summary><pre>{tab.content!.verifyOutput}</pre></details>}
        </PersistentWorkspaceBody>)}
      </div>
    </section>
  </div>;
}
