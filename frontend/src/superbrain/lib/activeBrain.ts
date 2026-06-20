export interface ActiveBrain {
  provider?: string;
  model?: string;
  privacy?: string;
}

let active: ActiveBrain = {};
const listeners = new Set<() => void>();

export function getActiveBrain(): ActiveBrain {
  return active;
}

export function setActiveBrain(next: ActiveBrain): void {
  active = { ...next };
  for (const l of listeners) {
    try { l(); } catch { /* one bad listener never breaks the rest */ }
  }
}

export function subscribeActiveBrain(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** One compact line for the GAGOS readout, e.g. "Opus 4.8 · cloud". */
export function formatActiveBrainLine(brain: ActiveBrain): string {
  const name = (brain.model || brain.provider || '').trim();
  const privacy = (brain.privacy || '').trim().toLowerCase();
  if (!name) return 'auto';
  return privacy ? `${name} · ${privacy}` : name;
}

export function __resetActiveBrainForTests(): void {
  active = {};
  listeners.clear();
}
