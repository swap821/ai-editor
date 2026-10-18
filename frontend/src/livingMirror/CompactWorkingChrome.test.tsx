import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { CSSProperties } from 'react';
import { CompactWorkingChrome } from './CompactWorkingChrome';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function mountMenu() {
  let readerTop = 344;
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    if (this.matches('.lm-surface')) return new DOMRect(0, readerTop, 390, 240);
    if (this.matches('.lm-compact-more > summary')) return new DOMRect(314, 8, 64, 44);
    if (this.matches('.lm-app')) return new DOMRect(0, 0, 390, 844);
    return new DOMRect();
  });
  const view = render(<div className="lm-app" style={{ '--lm-workspace-dock-clearance': '260px' } as CSSProperties}>
    <CompactWorkingChrome blocked={false} onHost={() => {}}><button>Optional control</button></CompactWorkingChrome>
    <section className="lm-surface">Retained result</section>
  </div>);
  return {
    root: view.container.querySelector<HTMLElement>('.lm-app')!,
    more: view.container.querySelector<HTMLDetailsElement>('.lm-compact-more')!,
    content: view.container.querySelector<HTMLElement>('.lm-compact-more__content')!,
    reader: view.container.querySelector<HTMLElement>('.lm-surface')!,
    moveReader: () => { readerTop = 304; },
  };
}

it('remeasures More on opening after a position-only reader move', () => {
  const { more, content, reader, moveReader } = mountMenu();
  expect(content.style.maxHeight).toBe('276px');
  moveReader(); // Same240px reader; no root, reader or summary resize.
  more.open = true;
  fireEvent(more, new Event('toggle'));
  expect(content.style.maxHeight).toBe('236px');
  expect(reader.getBoundingClientRect().height).toBe(240);
});

it.each([false, true])('keeps More clear of a fixed-height reader after settled dock growth; open=%s', async open => {
  const { root, more, content, reader, moveReader } = mountMenu();
  if (open) { more.open = true; fireEvent(more, new Event('toggle')); }
  expect(content.style.maxHeight).toBe('276px');
  // The real dock owner publishes this presentation property after composer
  // growth. CSS can move a fixed-height reader without any ResizeObserver
  // notification for the three boxes previously watched by More.
  act(() => { moveReader(); root.style.setProperty('--lm-workspace-dock-clearance', '300px'); });
  await waitFor(() => expect(content.style.maxHeight).toBe('236px'));
  expect(more.open).toBe(open);
  expect(reader.getBoundingClientRect().height).toBe(240);
  // Actual popup top is52px summary bottom +8px; retain8px reading clearance.
  expect(60 + Number.parseFloat(content.style.maxHeight)).toBeLessThanOrEqual(reader.getBoundingClientRect().top - 8);
});
