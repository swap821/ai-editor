const controlSelectors = {
  beginner: '[data-experience-choice="beginner"]',
  expert: '[data-experience-choice="expert"]',
  focus: '.gagos-focus-toggle',
  diagnostics: '.lm-connection__details > summary',
  quality: '.lm-rendering-preferences select',
  more: '.lm-compact-more > summary',
  navigation: '.lm-navigation button, .lm-navigation summary',
} as const;

export type CompactControlFocus = {
  key: keyof typeof controlSelectors;
  previous: HTMLElement;
};

/** One transient UI focus intent, never task/permission or preference state. */
export function captureCompactControlFocus(root: HTMLElement | null, lastKnown: CompactControlFocus | null = null): CompactControlFocus | null {
  if (!root || root.dataset.working !== 'true') return null;
  const active = root.ownerDocument.activeElement;
  if (active instanceof HTMLElement && root.contains(active)) {
    for (const key of Object.keys(controlSelectors) as Array<keyof typeof controlSelectors>) {
      if (active.matches(controlSelectors[key])) return { key, previous: active };
    }
  }
  // Native media CSS can blur a desktop control before its change callback.
  // Recover only that still-owned, now CSS-hidden control, never a stale or
  // deliberately abandoned focus. The app clears lastKnown on other focus,
  // an outside pointer action and window blur.
  if (active !== root.ownerDocument.body || !lastKnown || !root.contains(lastKnown.previous)) return null;
  const view = root.ownerDocument.defaultView;
  for (let node: HTMLElement | null = lastKnown.previous; node && node !== root; node = node.parentElement) {
    const style = view?.getComputedStyle(node);
    if (style?.display === 'none' || style?.visibility === 'hidden') return lastKnown;
  }
  return null;
}

export function restoreCompactControlFocus(root: HTMLElement | null, intent: CompactControlFocus): void {
  if (!root) return;
  const active = root.ownerDocument.activeElement;
  // Do not replace an explicit reader/input/decision handoff during resize.
  if (active?.isConnected && active !== root.ownerDocument.body && active !== intent.previous) return;
  const more = root.querySelector<HTMLDetailsElement>('.lm-compact-more');
  // Desktop diagnostics are expanded inline; their summary is CSS-hidden.
  // Continue at the visible existing control, never focus that hidden summary.
  const destination = !more && intent.key === 'diagnostics' ? 'quality' : intent.key;
  let target = more && !more.open ? more.querySelector<HTMLElement>(':scope > summary')
    : root.querySelector<HTMLElement>(destination === 'more' && !more
      ? '[data-experience-choice][aria-pressed="true"]'
      : destination === 'navigation' ? '.lm-navigation > button' : controlSelectors[destination]);
  // Never place focus inside a collapsed diagnostic disclosure. Its summary
  // is still visible; a closed outer More is handled by the same rule.
  let closed = target?.closest<HTMLDetailsElement>('details:not([open])');
  while (closed && target) {
    const summary = closed.querySelector<HTMLElement>(':scope > summary');
    if (!summary?.contains(target)) target = summary;
    closed = closed.parentElement?.closest<HTMLDetailsElement>('details:not([open])');
  }
  if (!target || target.closest('[hidden], [inert], [aria-hidden="true"]') || target.matches(':disabled')) return;
  target.focus({ preventScroll: true });
}
