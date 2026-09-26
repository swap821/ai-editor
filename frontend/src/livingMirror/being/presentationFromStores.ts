import {
  getEffectiveOrganismPhase,
  getConversationPhase,
  type ConversationPhase,
} from '../../superbrain/lib/conversationPhaseBus';
import type { CortexMirrorState } from '../../superbrain/lib/mirrorStore';
import type { TabSnapshot } from '../../superbrain/lib/tabStore';
import {
  deriveBeingPresentation,
  type BeingFacts,
  type BeingPresentation,
  type RouteClass,
  type VerificationState,
  type WorkerPresentationRecord,
  type WorkerPresentationState,
} from './semanticKernel';

const WORKER_STATES = new Set<WorkerPresentationState>([
  'requested', 'admitted', 'active', 'awaiting-capability', 'returned', 'dissolved', 'failed', 'killed',
]);
const MAX_PRESENTATION_WORKERS = 8;
const TERMINAL_WORKER_STATES = new Set<WorkerPresentationState>(['returned', 'dissolved', 'failed', 'killed']);
const VERIFICATION_EVENT_TYPES = new Set(['verify_result', 'verification.passed', 'verification.failed', 'verification.completed']);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function eventPayload(event: Record<string, unknown>): Record<string, unknown> {
  if (isRecord(event.payload)) return event.payload;
  return event;
}

function lastEventOf(
  mirror: CortexMirrorState,
  predicate: (type: string) => boolean,
): CortexMirrorState['recentEvents'][number] | null {
  const event = [...mirror.recentEvents].reverse().find((candidate) => predicate(candidate.type));
  return event ?? null;
}

function mirrorVerification(mirror: CortexMirrorState): VerificationState {
  const envelope = mirror.lastVerification;
  const payload = envelope ? eventPayload(envelope) : null;
  const verdict = payload && typeof payload.verdict === 'string' ? payload.verdict.toLowerCase() : '';
  if (verdict === 'pass' || verdict === 'passed' || verdict === 'green') return 'pass';
  if (verdict === 'fail' || verdict === 'failed' || verdict === 'red') return 'fail';
  if (mirror.phase === 'active' && (mirror.pendingEvents > 0 || mirror.approvalRequired)) return 'pending';
  return 'unknown';
}

function verificationFromStores(
  mirror: CortexMirrorState,
  tabs: TabSnapshot,
  currentTurnStarted: boolean,
  currentTurnHasVerification: boolean,
): VerificationState {
  const focused = tabs.tabs.find((tab) => tab.id === tabs.focusId);

  // A surface verdict remains valid for its artifact, but cannot stand in for
  // the current turn's result once a newer turn boundary has been observed.
  // Prefer that turn's measured mirror verdict before consulting an older tab.
  if (currentTurnStarted) {
    if (currentTurnHasVerification) return mirrorVerification(mirror);
    return focused?.kind === 'content' && focused.content?.streaming ? 'pending' : 'unknown';
  }

  if (focused?.kind === 'content') {
    if (focused.content?.streaming) return 'pending';
    if (focused.content?.verifyVerdict === 'pass') return 'pass';
    if (focused.content?.verifyVerdict === 'fail') return 'fail';
    // A retained mirror verification belongs to an earlier observation unless
    // this materialized surface carries its own explicit verdict. Conservatism
    // here protects the completed != verified invariant across turns.
    return 'unknown';
  }
  // `lastVerification` is retained by the mirror for Expert inspection, but
  // it is not a current-task verdict by itself. Only a verification event in
  // the current measured turn can promote this fallback path. A content tab
  // with its own explicit verdict is handled above because that evidence is
  // bound to the surface being presented.
  if (!currentTurnHasVerification) return 'unknown';
  return mirrorVerification(mirror);
}

function workerStates(mirror: CortexMirrorState): WorkerPresentationRecord[] {
  if (mirror.projection === 'stale' || mirror.projection === 'unavailable') return [];

  const eventWorkers = Object.entries(mirror.workers)
    .map(([workerId, worker]) => {
      const state = worker.state.replace(/_/g, '-');
      const presentationState = state === 'started' ? 'active' : state === 'completed' ? 'returned' : state;
      return { workerId, state: presentationState as WorkerPresentationState, cursor: worker.cursor };
    })
    .filter(({ state }) => WORKER_STATES.has(state));
  const observation = mirror.observations?.activeWorkers;
  const rosterCursor = observation
    && (observation.status === 'measured' || observation.status === 'derived')
    && typeof observation.cursor === 'number'
    && Number.isSafeInteger(observation.cursor)
    && observation.cursor >= 0
    ? observation.cursor
    : null;

  let projectedWorkers: WorkerPresentationRecord[] = eventWorkers;
  if (rosterCursor !== null) {
    const currentIds = new Set(mirror.activeWorkers);
    const byId = new Map<string, WorkerPresentationRecord>();

    for (const worker of eventWorkers) {
      if (worker.cursor > rosterCursor || (worker.cursor === rosterCursor
        && TERMINAL_WORKER_STATES.has(worker.state) && !currentIds.has(worker.workerId))) {
        byId.set(worker.workerId, worker);
      }
    }
    for (const workerId of currentIds) {
      const newerEvent = byId.get(workerId);
      byId.set(workerId, newerEvent ?? { workerId, state: 'active', cursor: rosterCursor });
    }
    projectedWorkers = [...byId.values()];
  }

  return projectedWorkers
    .sort((a, b) => {
      const terminalOrder = Number(TERMINAL_WORKER_STATES.has(a.state)) - Number(TERMINAL_WORKER_STATES.has(b.state));
      if (terminalOrder || b.cursor !== a.cursor) return terminalOrder || b.cursor - a.cursor;
      return a.workerId < b.workerId ? -1 : a.workerId > b.workerId ? 1 : 0;
    })
    .slice(0, MAX_PRESENTATION_WORKERS);
}

function routeClass(events: CortexMirrorState['recentEvents']): RouteClass {
  const event = [...events].reverse().find((candidate) => candidate.type === 'route.selected' || candidate.type === 'route') ?? null;
  if (!event) return 'unknown';
  const payload = eventPayload(event);
  const privacy = typeof payload.privacy === 'string' ? payload.privacy.toLowerCase() : '';
  if (privacy === 'local' || privacy === 'on-device') return 'local';
  if (privacy === 'cloud' || privacy === 'remote') return 'cloud';
  return 'unknown';
}

function stopState(mirror: CortexMirrorState): BeingFacts['stop'] {
  const event = lastEventOf(mirror, (type) => type.includes('emergency_stop'));
  if (!event) return 'unknown';
  return event.type.includes('engaged') ? 'engaged' : 'clear';
}

export function beingFactsFromStores(
  mirror: CortexMirrorState,
  tabs: TabSnapshot,
  conversation: ConversationPhase = getConversationPhase(),
): BeingFacts {
  const materializingSurface = tabs.tabs.some((tab) => tab.kind === 'content' && (tab.lifecycle === 'reaching' || tab.lifecycle === 'unfurling'));
  const reabsorbingSurface = tabs.tabs.some((tab) => tab.kind === 'content' && tab.lifecycle === 'retracting');
  const contentTabs = tabs.tabs.filter((tab) => tab.kind === 'content' && tab.lifecycle !== 'retracting');
  const hasStreamingSurface = contentTabs.some((tab) => tab.content?.streaming === true);
  const hasResultSurface = contentTabs.some((tab) => tab.content?.streaming === false);
  // Recent events are bounded history, not current-task state. Keep the
  // monotonic turn cursor separately so a long turn remains attributable after
  // its `turn.started` entry rolls out of the 256-event display buffer.
  const attributionInvalidated = mirror.turnAttributionInvalidated;
  const recentTurnStartedId = attributionInvalidated
    ? null
    : [...mirror.recentEvents].reverse().find((event) => event.type === 'turn.started')?.id ?? null;
  const latestTurnStartedId = attributionInvalidated ? null : mirror.lastTurnStartedEventId ?? recentTurnStartedId;
  // Treat the unresolved boundary as a current-but-unattributed turn. This
  // prevents a focused artifact or retained verifier receipt from supplying
  // success until a new turn.started event establishes ownership.
  const currentTurnStarted = attributionInvalidated || latestTurnStartedId !== null;
  const currentTurnEvents = attributionInvalidated
    ? []
    : latestTurnStartedId === null
      ? mirror.recentEvents.slice(-32)
      : mirror.recentEvents.filter((event) => event.id > latestTurnStartedId);
  // The latest structured verification receipt and its cursor outlive the
  // bounded event history. It belongs to this turn only when newer than the
  // persistent turn boundary.
  const currentTurnHasVerification = !attributionInvalidated && (currentTurnEvents.some((event) => VERIFICATION_EVENT_TYPES.has(event.type))
    || (latestTurnStartedId !== null && mirror.lastVerificationEventId !== null && mirror.lastVerificationEventId > latestTurnStartedId));
  const currentTurnTypes = new Set(currentTurnEvents.map((event) => event.type));
  const refusalObserved = currentTurnTypes.has('security.refusal.recorded');
  const failureObserved = currentTurnTypes.has('mission.failed')
    || currentTurnTypes.has('worker.failed')
    || currentTurnTypes.has('worker.killed')
    || currentTurnTypes.has('worker.work_incomplete');
  const rollbackObserved = currentTurnTypes.has('mission.rolled_back')
    || currentTurnTypes.has('worker.rolled_back')
    || currentTurnTypes.has('rollback');
  const taskActivity: BeingFacts['taskActivity'] = refusalObserved
    ? 'refused'
    : rollbackObserved
      ? 'restored'
      : failureObserved || conversation === 'error'
        ? 'failed'
    : hasStreamingSurface || mirror.phase === 'active' || conversation === 'thinking' || conversation === 'streaming'
      ? 'streaming'
      : hasResultSurface || conversation === 'complete'
        ? 'complete'
        : 'idle';
  const verification = verificationFromStores(
    mirror,
    tabs,
    currentTurnStarted,
    currentTurnHasVerification,
  );
  const organismLifecycle = materializingSurface
    ? 'materializing'
    : reabsorbingSurface
      ? 'reabsorbing'
      : getEffectiveOrganismPhase();

  return {
    lifecycle: organismLifecycle,
    transport: mirror.connection,
    projection: mirror.projection,
    mirrorStatus: mirror.status,
    hasSnapshot: mirror.snapshotReceivedAt !== null,
    inputActive: conversation === 'awakening' || conversation === 'thinking',
    hasInput: tabs.tabs.some((tab) => tab.kind === 'input' && Boolean(tab.input?.text?.trim())),
    hasUnderstanding: conversation === 'complete' && !hasResultSurface,
    hasPlan: mirror.phase === 'planning' || currentTurnTypes.has('plan.created') || currentTurnTypes.has('plan'),
    taskActivity,
    approvalPending: mirror.approvalRequired || tabs.tabs.some((tab) => tab.kind === 'approval' && tab.lifecycle !== 'retracting'),
    verification,
    // Route is turn-local evidence. A new measured turn without its own route
    // event must not inherit the previous turn's local/cloud label.
    route: routeClass(currentTurnEvents),
    stop: stopState(mirror),
    reflexUsed: currentTurnTypes.has('cerebellum.replayed'),
    learning: currentTurnTypes.has('memory.promoted') || currentTurnTypes.has('skill.mastered'),
    memoryRecalled: currentTurnTypes.has('memory.recalled') || currentTurnTypes.has('memory.trusted_workflow_surfaced'),
    memoryPromoted: currentTurnTypes.has('memory.promoted'),
    injectionBlocked: currentTurnTypes.has('security.injection.detected'),
    councilDissent: currentTurnTypes.has('council.dissent') || currentTurnTypes.has('council.dissent.recorded'),
    curriculumMastered: currentTurnTypes.has('skill.mastered'),
    rollback: rollbackObserved,
    workers: workerStates(mirror),
  };
}

export function beingPresentationFromStores(
  mirror: CortexMirrorState,
  tabs: TabSnapshot,
  conversation: ConversationPhase = getConversationPhase(),
): BeingPresentation {
  return deriveBeingPresentation(beingFactsFromStores(mirror, tabs, conversation));
}

export function beingStatusText(presentation: BeingPresentation): string {
  switch (presentation.taskState) {
    case 'done-verified': return 'GAGOS finished the task and verification passed.';
    case 'done-unverified': return 'GAGOS finished the work, but it is not verified yet.';
    case 'refused': return 'GAGOS did not do that because it would have exceeded your permission.';
    case 'failed': return 'GAGOS could not complete the action.';
    case 'restored': return 'GAGOS restored the previous state.';
    case 'stopped': return 'GAGOS is stopped.';
    case 'stale': return 'GAGOS is showing a last-known picture; current state is not confirmed.';
    case 'needs-permission': return 'GAGOS is waiting for your decision.';
    default: break;
  }
  switch (presentation.phase) {
    case 'awaiting-human': return 'GAGOS is waiting for your decision.';
    case 'acting': return 'GAGOS is working.';
    case 'verifying': return 'GAGOS is checking the result.';
    case 'learning': return 'GAGOS is recording a verified lesson.';
    case 'reflex': return 'GAGOS is reusing a verified routine.';
    case 'recovering': return 'GAGOS is recovering from an interrupted or refused action.';
    case 'stale': return 'GAGOS is showing a last-known picture; current state is not confirmed.';
    case 'degraded': return 'GAGOS has no live state to show; the organism is in its resting view.';
    case 'stopped': return 'GAGOS is stopped.';
    case 'listening': return 'GAGOS is listening.';
    case 'understanding': return 'GAGOS is understanding your request.';
    case 'planning': return 'GAGOS is preparing a bounded next step.';
    case 'arriving': return 'GAGOS is arriving.';
    case 'booting': return 'GAGOS is starting.';
    default: return 'GAGOS is resting.';
  }
}
