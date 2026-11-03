import { afterEach, describe, expect, it, vi } from 'vitest';
import { installKeyboardViewportTracking } from './keyboardViewport';

interface FakeViewport extends EventTarget {
  offsetTop: number;
  height: number;
  scale: number;
}

function setup(extra: Record<string, unknown> = {}) {
  const viewport: FakeViewport = Object.assign(new EventTarget(), {
    offsetTop: 0,
    height: 800,
    scale: 1,
  });
  const host = Object.assign(new EventTarget(), {
    innerHeight: 800,
    visualViewport: viewport,
    ...extra,
  }) as unknown as Window;

  const root = document.createElement('div');
  root.innerHTML = '<div class="gagos-chat"><textarea id="composer"></textarea></div><input id="outside" type="text" />';
  document.body.appendChild(root);
  vi.spyOn(root, 'getBoundingClientRect').mockReturnValue({
    top: 0,
    left: 0,
    right: 400,
    width: 400,
    height: 800,
    bottom: 800,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
  const composer = root.querySelector<HTMLTextAreaElement>('#composer')!;
  const outside = root.querySelector<HTMLInputElement>('#outside')!;
  return { viewport, host, root, composer, outside };
}

afterEach(() => {
  document.body.innerHTML = '';
  vi.restoreAllMocks();
});

describe('keyboard viewport tracking', () => {
  it('marks the keyboard open and records the occluded height while the chat composer is focused', () => {
    const { viewport, host, root, composer } = setup();
    viewport.height = 500;
    composer.focus();

    const stop = installKeyboardViewportTracking(root, host);

    expect(root.dataset.keyboardOpen).toBe('true');
    expect(root.style.getPropertyValue('--lm-keyboard-inset')).toBe('300px');
    stop();
  });

  it('ignores a shrunken viewport when focus is outside the chat or the page is zoomed', () => {
    const { viewport, host, root, composer, outside } = setup();
    viewport.height = 500;

    outside.focus();
    const stop = installKeyboardViewportTracking(root, host);
    expect(root.dataset.keyboardOpen).toBeUndefined();
    expect(root.style.getPropertyValue('--lm-keyboard-inset')).toBe('');

    composer.focus();
    viewport.scale = 2;
    viewport.dispatchEvent(new Event('resize'));
    expect(root.dataset.keyboardOpen).toBeUndefined();
    stop();
  });

  it('reacts to viewport resize events and stops reacting after cleanup', () => {
    const { viewport, host, root, composer } = setup();
    composer.focus();
    const stop = installKeyboardViewportTracking(root, host);
    expect(root.dataset.keyboardOpen).toBeUndefined();

    viewport.height = 450;
    viewport.dispatchEvent(new Event('resize'));
    expect(root.dataset.keyboardOpen).toBe('true');
    expect(root.style.getPropertyValue('--lm-keyboard-inset')).toBe('350px');

    viewport.height = 800;
    viewport.dispatchEvent(new Event('scroll'));
    expect(root.dataset.keyboardOpen).toBeUndefined();
    expect(root.style.getPropertyValue('--lm-keyboard-inset')).toBe('');

    viewport.height = 450;
    viewport.dispatchEvent(new Event('resize'));
    expect(root.dataset.keyboardOpen).toBe('true');

    stop();
    expect(root.dataset.keyboardOpen).toBeUndefined();
    expect(root.style.getPropertyValue('--lm-keyboard-inset')).toBe('');

    viewport.dispatchEvent(new Event('resize'));
    expect(root.dataset.keyboardOpen).toBeUndefined();
  });

  it('does nothing and returns a safe disposer when visualViewport is unavailable', () => {
    const { host, root, composer } = setup({ visualViewport: null });
    composer.focus();

    const stop = installKeyboardViewportTracking(root, host);

    expect(root.dataset.keyboardOpen).toBeUndefined();
    expect(() => stop()).not.toThrow();
  });

  it('defers updates to an animation frame when available and cancels a pending one on cleanup', () => {
    const requestAnimationFrame = vi.fn(() => 7);
    const cancelAnimationFrame = vi.fn();
    const { viewport, host, root, composer } = setup({ requestAnimationFrame, cancelAnimationFrame });
    viewport.height = 500;
    composer.focus();

    const stop = installKeyboardViewportTracking(root, host);

    expect(requestAnimationFrame).toHaveBeenCalledTimes(1);
    expect(root.dataset.keyboardOpen).toBeUndefined();

    stop();
    expect(cancelAnimationFrame).toHaveBeenCalledWith(7);
  });
});
