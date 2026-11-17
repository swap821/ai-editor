import type { BootstrapCheck, BootstrapReadinessState } from './BootstrapReadiness';

export const UNAVAILABLE_STATE: BootstrapReadinessState = {
  state: 'unavailable',
  summary: 'The local setup endpoint did not answer with a trustworthy status.',
  checks: [],
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function parseBootstrapReadiness(value: unknown): BootstrapReadinessState {
  if (!isRecord(value) || typeof value.ok !== 'boolean' || typeof value.summary !== 'string' || !Array.isArray(value.checks)) {
    return UNAVAILABLE_STATE;
  }

  const checks: BootstrapCheck[] = [];
  for (const candidate of value.checks) {
    if (!isRecord(candidate)
      || typeof candidate.name !== 'string'
      || typeof candidate.passed !== 'boolean'
      || typeof candidate.required !== 'boolean'
      || typeof candidate.message !== 'string') {
      return UNAVAILABLE_STATE;
    }
    checks.push({
      name: candidate.name,
      passed: candidate.passed,
      required: candidate.required,
      message: candidate.message,
    });
  }

  return {
    state: value.ok ? 'ready' : 'blocked',
    summary: value.summary,
    checks,
  };
}
