export type ExperienceMode = 'beginner' | 'expert';

export const EXPERIENCE_MODE_STORAGE_KEY = 'gagos-experience-mode';

export function isExperienceMode(value: unknown): value is ExperienceMode {
  return value === 'beginner' || value === 'expert';
}

function getBrowserStorage(): Storage | null {
  if (typeof window === 'undefined') return null;

  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function readExperienceMode(storage: Storage | null | undefined = getBrowserStorage()): ExperienceMode {
  try {
    return storage?.getItem(EXPERIENCE_MODE_STORAGE_KEY) === 'expert' ? 'expert' : 'beginner';
  } catch {
    return 'beginner';
  }
}

export function writeExperienceMode(
  mode: ExperienceMode,
  storage: Storage | null | undefined = getBrowserStorage(),
): void {
  try {
    storage?.setItem(EXPERIENCE_MODE_STORAGE_KEY, isExperienceMode(mode) ? mode : 'beginner');
  } catch {
    // Private browsing and hardened WebViews can reject localStorage writes.
    // The in-memory React state remains the current-session source of truth.
  }
}
