import type { ContinuityState, VerificationState } from '../being/beingPresentation';
import type { HumanTaskState } from './humanTaskStory';

export interface PlainCopy {
  title: string;
  detail: string;
  nextAction?: string;
}

export function describeConnection(state: ContinuityState): PlainCopy {
  switch (state) {
    case 'fresh': return { title: 'Up to date', detail: 'New changes are confirmed.' };
    case 'snapshot': return { title: 'Confirming changes', detail: 'The last known picture is loaded while new changes are checked.' };
    case 'stale': return { title: 'Showing the last known state', detail: 'New changes are not confirmed yet.', nextAction: 'Wait for the live picture to catch up.' };
    case 'stopped': return { title: 'Stopped by you', detail: 'No new action can begin until the stop is cleared.' };
    default: return { title: 'Connecting to GAGOS', detail: 'The current picture is not confirmed yet.' };
  }
}

export function describeTaskState(state: HumanTaskState): PlainCopy {
  switch (state) {
    case 'idle': return { title: 'Ready when you are', detail: 'Tell GAGOS what you would like to get done.' };
    case 'understood': return { title: 'I understood', detail: 'Your request is captured. Nothing has been changed.' };
    case 'preparing': return { title: 'I am preparing', detail: 'GAGOS is working out a safe next step.' };
    case 'needs-permission': return { title: 'Your permission is needed', detail: 'Review exactly what will happen before anything acts.', nextAction: 'Choose Allow once or Don’t allow.' };
    case 'working': return { title: 'I am working', detail: 'The requested work is in progress.' };
    case 'checking': return { title: 'I am checking the result', detail: 'The work is not called done until a check reports back.' };
    case 'done-verified': return { title: 'Done', detail: 'The result was checked successfully.', nextAction: 'Review the result or restore the previous state.' };
    case 'done-unverified': return { title: 'The work finished, but it is not verified', detail: 'GAGOS could not confirm the result.', nextAction: 'Review the result or run a check.' };
    case 'refused': return { title: 'I did not do that', detail: 'The request was declined or exceeded the permission available.', nextAction: 'Choose a safer option or inspect why.' };
    case 'failed': return { title: 'That did not work', detail: 'The attempted change did not pass its check.', nextAction: 'Try another approach or inspect what failed.' };
    case 'restored': return { title: 'Previous state restored', detail: 'The failed change was rolled back.', nextAction: 'Review what failed before trying again.' };
    case 'stopped': return { title: 'Stopped', detail: 'The current task was stopped. No new action will begin.', nextAction: 'Review the last confirmed state.' };
    case 'stale': return { title: 'The current picture is stale', detail: 'This task cannot be described as current until continuity is confirmed.', nextAction: 'Reconnect before relying on the result.' };
  }
}

export function describeVerification(state: VerificationState): PlainCopy {
  switch (state) {
    case 'passed': return { title: 'Verified', detail: 'A real check reported success.' };
    case 'failed': return { title: 'Verification failed', detail: 'The result did not pass the available check.' };
    case 'pending': return { title: 'Checking', detail: 'The result is not final yet.' };
    case 'unverified': return { title: 'Unverified', detail: 'The work exists, but the system could not confirm it.' };
    default: return { title: 'Not checked', detail: 'No verification result is available.' };
  }
}

export function describeApproval(action?: string | null): PlainCopy {
  return {
    title: 'Your permission is needed',
    detail: action ? `GAGOS wants to ${action}. Nothing happens until you choose.` : 'GAGOS is waiting for your choice before it acts.',
    nextAction: 'Allow once or Don’t allow.',
  };
}

export function describeRefusal(reason?: string | null): PlainCopy {
  return { title: 'I did not do that', detail: reason ? `The request was blocked because ${reason}.` : 'The request was blocked by the safety boundary.', nextAction: 'Choose a safer option or inspect why.' };
}

export function describeRecovery(restored: boolean): PlainCopy {
  return restored
    ? { title: 'Previous state restored', detail: 'The failed change was rolled back.' }
    : { title: 'Recovery is in progress', detail: 'GAGOS is checking what remains confirmed.' };
}

export function describeMemoryReuse(reused: boolean): PlainCopy {
  return reused
    ? { title: 'Used a learned routine', detail: 'A previously verified routine was reused. No model call is implied.' }
    : { title: 'New reasoning', detail: 'No learned routine was reported for this request.' };
}
