const CHAT_TEXT_ENTRY_SELECTOR = [
  'input:not([type])',
  'input[type="text"]',
  'input[type="search"]',
  'input[type="email"]',
  'input[type="url"]',
  'input[type="tel"]',
  'input[type="password"]',
  'input[type="number"]',
  'textarea',
  '[contenteditable]:not([contenteditable="false"])',
].join(',');

const MIN_KEYBOARD_OCCLUSION_PX = 100;
const MAX_UNZOOMED_SCALE = 1.05;

/** Track the on-screen keyboard only while the conversation composer is being edited. */
export function installKeyboardViewportTracking(root: HTMLElement, host: Window = window): () => void {
  const viewport = host.visualViewport;
  if (!viewport) return () => {};

  let animationFrame: number | null = null;

  const update = () => {
    animationFrame = null;

    const active = root.ownerDocument.activeElement;
    const chat = root.querySelector('.gagos-chat');
    const editingChat = !!active
      && !!chat?.contains(active)
      && active.matches(CHAT_TEXT_ENTRY_SELECTOR);
    const viewportTop = Math.max(0, viewport.offsetTop);
    const viewportBottom = viewportTop + viewport.height;
    const rootBounds = root.getBoundingClientRect();
    const rootBottom = rootBounds.height > 0 && Number.isFinite(rootBounds.bottom)
      ? rootBounds.bottom
      : host.innerHeight;
    const occludedHeight = Math.max(0, rootBottom - viewportBottom);
    const keyboardOpen = editingChat
      && viewport.scale <= MAX_UNZOOMED_SCALE
      && occludedHeight >= MIN_KEYBOARD_OCCLUSION_PX;

    if (!keyboardOpen) {
      delete root.dataset.keyboardOpen;
      root.style.removeProperty('--lm-keyboard-inset');
      root.style.removeProperty('--lm-visible-viewport-height');
      return;
    }

    root.dataset.keyboardOpen = 'true';
    root.style.setProperty('--lm-keyboard-inset', `${occludedHeight}px`);
    root.style.setProperty('--lm-visible-viewport-height', `${viewport.height}px`);
  };

  const scheduleUpdate = () => {
    if (animationFrame !== null) return;
    if (typeof host.requestAnimationFrame === 'function') {
      animationFrame = host.requestAnimationFrame(update);
    } else {
      update();
    }
  };

  root.addEventListener('focusin', scheduleUpdate);
  root.addEventListener('focusout', scheduleUpdate);
  host.addEventListener('resize', scheduleUpdate);
  viewport.addEventListener('resize', scheduleUpdate);
  viewport.addEventListener('scroll', scheduleUpdate);
  scheduleUpdate();

  return () => {
    root.removeEventListener('focusin', scheduleUpdate);
    root.removeEventListener('focusout', scheduleUpdate);
    host.removeEventListener('resize', scheduleUpdate);
    viewport.removeEventListener('resize', scheduleUpdate);
    viewport.removeEventListener('scroll', scheduleUpdate);
    if (animationFrame !== null && typeof host.cancelAnimationFrame === 'function') {
      host.cancelAnimationFrame(animationFrame);
    }
    delete root.dataset.keyboardOpen;
    root.style.removeProperty('--lm-keyboard-inset');
    root.style.removeProperty('--lm-visible-viewport-height');
  };
}
