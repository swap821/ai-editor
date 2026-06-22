const WORK_INTENT_RE = /^(write|build|create|make|code|implement|fix|add|generate)\b/i;

export function isWorkIntent(text: string): boolean {
  return WORK_INTENT_RE.test(text.trim());
}
