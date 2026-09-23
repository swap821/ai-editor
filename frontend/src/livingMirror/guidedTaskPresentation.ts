import type { CouncilMission } from './contracts';

export function guidedTaskStatus(task: CouncilMission): string {
  if (task.approvalNeeded === true) return 'Permission needed before GAGOS can continue.';
  const status = task.status.toLowerCase();
  if (['active', 'acting', 'executing', 'running', 'streaming'].includes(status)) return 'In progress.';
  if (['failed', 'error'].includes(status)) return 'This task needs attention.';
  if (['refused', 'rejected', 'declined'].includes(status)) return 'GAGOS did not continue.';
  if (['complete', 'completed', 'done', 'verified'].includes(status)) return 'Finished.';
  if (['planning', 'deliberating', 'queued', 'pending'].includes(status)) return 'Preparing.';
  return 'Status unavailable.';
}

export function guidedTaskVerification(task: CouncilMission): string {
  if (task.verificationPassed === true) return 'Verified result recorded.';
  if (task.verificationPassed === false) return 'The result did not pass its check.';
  return 'Verification status is not available yet.';
}
