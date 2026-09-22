import { useEffect, useState } from 'react';
import { API_BASE, API_HEADERS } from '../config';

export type BootstrapCheck = {
  name: string;
  passed: boolean;
  required: boolean;
  message: string;
};

export type BootstrapReadinessState =
  | { state: 'loading'; summary: string; checks: BootstrapCheck[] }
  | { state: 'ready' | 'blocked' | 'unavailable'; summary: string; checks: BootstrapCheck[] };

const LOADING_STATE: BootstrapReadinessState = {
  state: 'loading',
  summary: 'Reading local setup status.',
  checks: [],
};

const UNAVAILABLE_STATE: BootstrapReadinessState = {
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

type BootstrapReadinessProps = {
  apiBase?: string;
};

export function BootstrapReadiness({ apiBase = API_BASE }: BootstrapReadinessProps) {
  const [readiness, setReadiness] = useState<BootstrapReadinessState>(LOADING_STATE);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    void fetch(`${apiBase}/api/v1/system/bootstrap`, {
      credentials: 'include',
      headers: API_HEADERS as HeadersInit,
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error(`bootstrap status ${response.status}`);
        return response.json();
      })
      .then((payload: unknown) => {
        if (active) setReadiness(parseBootstrapReadiness(payload));
      })
      .catch((error: unknown) => {
        if (active && !(error instanceof DOMException && error.name === 'AbortError')) {
          setReadiness(UNAVAILABLE_STATE);
        }
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [apiBase]);

  if (readiness.state === 'loading') {
    return <section className="gagos-readiness" aria-label="Local setup readiness">
      <p className="gagos-readiness__label">Local setup</p>
      <p className="gagos-readiness__status" role="status">Reading local setup status</p>
    </section>;
  }

  if (readiness.state === 'ready') {
    return <section className="gagos-readiness gagos-readiness--ready" aria-label="Local setup readiness">
      <p className="gagos-readiness__label">Local setup</p>
      <p className="gagos-readiness__status" role="status">Local setup is ready.</p>
      <p className="gagos-readiness__detail">{readiness.summary}</p>
    </section>;
  }

  const failedChecks = readiness.checks.filter((check) => !check.passed);
  return <section className={`gagos-readiness gagos-readiness--${readiness.state}`} aria-label="Local setup readiness">
    <p className="gagos-readiness__label">Local setup</p>
    <p className="gagos-readiness__status" role="status">
      {readiness.state === 'blocked' ? 'Setup needs attention.' : 'Setup status is unavailable.'}
    </p>
    <p className="gagos-readiness__detail">{readiness.summary}</p>
    {failedChecks.length > 0 ? <ul className="gagos-readiness__checks">
      {failedChecks.map((check) => <li key={check.name}><strong>{check.name}</strong>: {check.message}</li>)}
    </ul> : null}
    <a className="gagos-readiness__recovery-link" href="#gagos-recovery">Recovery guidance</a>
    <details id="gagos-recovery" className="gagos-readiness__recovery">
      <summary>What to check</summary>
      <p>Keep the local API running, confirm the data folder is writable, and make sure Ollama or another permitted provider is available. Refresh this status before starting a task.</p>
    </details>
  </section>;
}
