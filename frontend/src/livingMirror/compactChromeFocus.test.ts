import { afterEach, describe, expect, it } from 'vitest';
import {
  captureCompactControlFocus,
  restoreCompactControlFocus,
  type CompactControlFocus,
} from './compactChromeFocus';

function mount(html: string, working = true): HTMLElement {
  const root = document.createElement('div');
  if (working) root.dataset.working = 'true';
  root.innerHTML = html;
  document.body.appendChild(root);
  return root;
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('captureCompactControlFocus', () => {
  it('returns null without a root or when the root is not working', () => {
    expect(captureCompactControlFocus(null)).toBeNull();
    const idle = mount('<button class="gagos-focus-toggle">Focus</button>', false);
    idle.querySelector<HTMLElement>('.gagos-focus-toggle')?.focus();
    expect(captureCompactControlFocus(idle)).toBeNull();
  });

  it('identifies the focused control by key while working', () => {
    const root = mount(
      '<button class="gagos-focus-toggle">Focus</button>'
      + '<nav class="lm-navigation"><button id="nav">Go</button></nav>'
      + '<details class="lm-compact-more"><summary tabindex="0">More</summary></details>'
      + '<button id="other">Other</button>',
    );
    const focusBtn = root.querySelector<HTMLElement>('.gagos-focus-toggle');
    const nav = root.querySelector<HTMLElement>('#nav');
    const summary = root.querySelector<HTMLElement>('summary');
    const other = root.querySelector<HTMLElement>('#other');

    focusBtn?.focus();
    expect(captureCompactControlFocus(root)).toEqual({ key: 'focus', previous: focusBtn });
    nav?.focus();
    expect(captureCompactControlFocus(root)).toEqual({ key: 'navigation', previous: nav });
    summary?.focus();
    expect(captureCompactControlFocus(root)).toEqual({ key: 'more', previous: summary });
    other?.focus();
    expect(captureCompactControlFocus(root)).toBeNull();
  });

  it('recovers last known focus only when its control became CSS-hidden', () => {
    const root = mount('<div id="wrap"><button class="gagos-focus-toggle">Focus</button></div>');
    const wrap = root.querySelector<HTMLElement>('#wrap');
    const button = root.querySelector<HTMLElement>('.gagos-focus-toggle');
    if (!wrap || !button) throw new Error('fixture missing');
    button.focus();
    const lastKnown = captureCompactControlFocus(root);
    expect(lastKnown).not.toBeNull();
    button.blur();
    expect(document.activeElement).toBe(document.body);

    // Still visible: focus was abandoned, so nothing is recovered.
    expect(captureCompactControlFocus(root, lastKnown)).toBeNull();

    wrap.style.display = 'none';
    expect(captureCompactControlFocus(root, lastKnown)).toBe(lastKnown);

    const stale: CompactControlFocus = { key: 'focus', previous: document.createElement('button') };
    expect(captureCompactControlFocus(root, stale)).toBeNull();
  });
});

describe('restoreCompactControlFocus', () => {
  it('focuses the matching visible control when focus was lost', () => {
    const root = mount(
      '<button class="gagos-focus-toggle">Focus</button>'
      + '<nav class="lm-navigation"><button id="first">A</button><button id="second">B</button></nav>',
    );
    const toggle = root.querySelector<HTMLElement>('.gagos-focus-toggle');
    const first = root.querySelector<HTMLElement>('#first');
    if (!toggle || !first) throw new Error('fixture missing');

    restoreCompactControlFocus(root, { key: 'focus', previous: document.createElement('button') });
    expect(document.activeElement).toBe(toggle);

    toggle.blur();
    restoreCompactControlFocus(root, { key: 'navigation', previous: toggle });
    expect(document.activeElement).toBe(first);
  });

  it('does not steal an explicit focus handoff to another element', () => {
    const root = mount('<button class="gagos-focus-toggle">Focus</button><button id="other">Other</button>');
    const other = root.querySelector<HTMLElement>('#other');
    const toggle = root.querySelector<HTMLElement>('.gagos-focus-toggle');
    if (!other || !toggle) throw new Error('fixture missing');
    other.focus();
    restoreCompactControlFocus(root, { key: 'focus', previous: toggle });
    expect(document.activeElement).toBe(other);
  });

  it('lands on the summary of a collapsed More instead of inside it', () => {
    const root = mount(
      '<details class="lm-compact-more"><summary tabindex="0">More</summary>'
      + '<button class="gagos-focus-toggle">Focus</button></details>',
    );
    const summary = root.querySelector<HTMLElement>('summary');
    restoreCompactControlFocus(root, { key: 'focus', previous: document.createElement('button') });
    expect(document.activeElement).toBe(summary);
  });

  it('never focuses a disabled or hidden target', () => {
    const disabled = mount('<button class="gagos-focus-toggle" disabled>Focus</button>');
    restoreCompactControlFocus(disabled, { key: 'focus', previous: document.createElement('button') });
    expect(document.activeElement).toBe(document.body);

    document.body.innerHTML = '';
    const hidden = mount('<div aria-hidden="true"><button class="gagos-focus-toggle">Focus</button></div>');
    restoreCompactControlFocus(hidden, { key: 'focus', previous: document.createElement('button') });
    expect(document.activeElement).toBe(document.body);
  });

  it('ignores a null root', () => {
    expect(() => restoreCompactControlFocus(null, { key: 'focus', previous: document.createElement('button') })).not.toThrow();
  });
});
