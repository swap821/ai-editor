export type BootstrapReadinessCopyState = {
  state: 'loading' | 'ready' | 'blocked' | 'unavailable';
  checks: Array<{ passed: boolean }>;
};

export type BootstrapReadinessHumanCopy = {
  detail: string;
  failedCheckCount: number;
};

/** Keep backend setup vocabulary and provider identities out of Guided copy. */
export function getBootstrapReadinessHumanCopy(readiness: BootstrapReadinessCopyState): BootstrapReadinessHumanCopy {
  const failedCheckCount = readiness.checks.filter((check) => !check.passed).length;
  if (readiness.state === 'loading') return { detail: 'Checking the local setup needed to begin.', failedCheckCount: 0 };
  if (readiness.state === 'ready') return { detail: 'GAGOS confirmed the local setup needed to begin.', failedCheckCount: 0 };
  if (readiness.state === 'unavailable') return { detail: 'GAGOS could not confirm the local setup yet.', failedCheckCount: 0 };
  return {
    detail: failedCheckCount === 1
      ? 'One local setup check needs attention.'
      : `${failedCheckCount || 'Some'} local setup checks need attention.`,
    failedCheckCount,
  };
}
