export interface ActiveBrain {
  provider?: string;
  model?: string;
  privacy?: string;
  turn_id?: string;
  mode?: string;
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

/** One compact line for the GAGOS readout, e.g. "Opus 4.8 · cloud · mission". */
export function formatActiveBrainLine(brain: ActiveBrain): string {
  const name = String(brain.model || brain.provider || '').trim();
  const privacy = String(brain.privacy || '').trim().toLowerCase();
  const mode = String(brain.mode || '').trim().toLowerCase();
  if (!name) return 'auto';
  const parts = [name];
  if (privacy) parts.push(privacy);
  if (mode) parts.push(mode);
  return parts.join(' · ');
}

export function __resetActiveBrainForTests(): void {
  active = {};
  listeners.clear();
}
