'use client';

import { useEffect, useRef, useSyncExternalStore } from 'react';
import styles from './CyberCursor.module.css';

/**
 * CyberCursor — the canonical award-site dot + ring.
 *
 * - 4px accent dot tracks the pointer 1:1; 28px ring trails it via a
 *   frame-rate-independent lerp: r += (m - r) * (1 - Math.pow(0.001, dt)).
 * - ZERO React state in the move path: ONE rAF loop writes
 *   transform: translate3d(...) straight onto two refs. The loop cancels
 *   itself once the ring settles (idle = free) and wakes on pointermove.
 * - Hover morph (ring 1.6x + fill, dot shrink) is a pure class toggle whose
 *   transitions are transform/opacity only — see CyberCursor.module.css.
 * - The native cursor is hidden through a :global html.cursor-active rule
 *   gated by @media (pointer: fine); over text inputs the class is removed
 *   so the native I-beam returns and the command bar stays usable.
 * - Coarse/touch pointers: renders nothing, attaches nothing.
 */

/** Elements that morph the cursor into its hover state. */
const INTERACTIVE_SELECTOR = 'button, a, input, [role="button"], [data-interactive]';

/** Text-entry surfaces where the native I-beam must come back. */
const TEXT_SELECTOR = [
  'textarea',
  '[contenteditable]:not([contenteditable="false"])',
  'input:not([type])',
  'input[type="text"]',
  'input[type="search"]',
  'input[type="email"]',
  'input[type="password"]',
  'input[type="url"]',
  'input[type="tel"]',
  'input[type="number"]',
].join(', ');

/** Global class on <html> that activates the cursor:none rule. */
const HTML_ACTIVE_CLASS = 'cursor-active';

/** Below this remaining ring->pointer delta (px) the rAF loop parks itself. */
const SETTLE_EPSILON = 0.001;

/* matchMedia as an external store: fine pointer => enabled. Server snapshot
 * is false, so SSR/hydration renders nothing and touch devices stay empty. */
function subscribePointerFine(onChange: () => void): () => void {
  const mql = window.matchMedia('(pointer: fine)');
  mql.addEventListener('change', onChange);
  return () => mql.removeEventListener('change', onChange);
}

const getPointerFine = () => window.matchMedia('(pointer: fine)').matches;
const getPointerFineServer = () => false;

export default function CyberCursor() {
  // Touch / coarse pointers: render nothing (no listeners, no DOM).
  const enabled = useSyncExternalStore(subscribePointerFine, getPointerFine, getPointerFineServer);
  const dotRef = useRef<HTMLDivElement>(null);
  const ringRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!enabled) return;
    const dot = dotRef.current;
    const ring = ringRef.current;
    if (!dot || !ring) return;

    const html = document.documentElement;
    html.classList.add(HTML_ACTIVE_CLASS);

    const state = {
      mx: 0, // pointer position — the dot follows this 1:1
      my: 0,
      rx: 0, // ring position — lerped toward (mx, my)
      ry: 0,
      raf: 0,
      lastT: 0,
      running: false,
      visible: false,
      overText: false,
    };

    const step = (now: number) => {
      // Clamp dt so a background-tab stall never produces a teleport spike.
      const dt = Math.min(Math.max((now - state.lastT) / 1000, 0), 0.1);
      state.lastT = now;

      // Frame-rate-independent lerp (identical feel at 60 / 120 / 144 Hz).
      const k = 1 - Math.pow(0.001, dt);
      state.rx += (state.mx - state.rx) * k;
      state.ry += (state.my - state.ry) * k;

      dot.style.transform = `translate3d(${state.mx}px, ${state.my}px, 0)`;
      ring.style.transform = `translate3d(${state.rx}px, ${state.ry}px, 0)`;

      // Idle = free: once the ring has settled onto the pointer, park the
      // loop entirely. pointermove wakes it again.
      if (
        Math.abs(state.mx - state.rx) < SETTLE_EPSILON &&
        Math.abs(state.my - state.ry) < SETTLE_EPSILON
      ) {
        state.rx = state.mx;
        state.ry = state.my;
        ring.style.transform = `translate3d(${state.rx}px, ${state.ry}px, 0)`;
        state.running = false;
        return;
      }
      state.raf = requestAnimationFrame(step);
    };

    const wake = () => {
      if (state.running) return;
      state.running = true;
      state.lastT = performance.now();
      state.raf = requestAnimationFrame(step);
    };

    const onPointerMove = (event: PointerEvent) => {
      state.mx = event.clientX;
      state.my = event.clientY;
      if (!state.visible) {
        state.visible = true;
        // First movement: snap the ring onto the pointer so it never lerps
        // in from the top-left origin.
        state.rx = event.clientX;
        state.ry = event.clientY;
        dot.classList.add(styles.isVisible);
        ring.classList.add(styles.isVisible);
      }
      wake();
    };

    const onPointerOver = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) return;

      const overText = target.closest(TEXT_SELECTOR) !== null;
      const overInteractive = !overText && target.closest(INTERACTIVE_SELECTOR) !== null;

      if (overText !== state.overText) {
        state.overText = overText;
        // Text inputs keep the native I-beam: drop the html class so the
        // browser cursor returns, and fade the custom cursor out.
        html.classList.toggle(HTML_ACTIVE_CLASS, !overText);
        dot.classList.toggle(styles.isText, overText);
        ring.classList.toggle(styles.isText, overText);
      }
      dot.classList.toggle(styles.isHover, overInteractive);
      ring.classList.toggle(styles.isHover, overInteractive);
    };

    const onPointerOut = (event: PointerEvent) => {
      // relatedTarget === null means the pointer left the window.
      if (event.relatedTarget === null) {
        state.visible = false;
        dot.classList.remove(styles.isVisible);
        ring.classList.remove(styles.isVisible);
      }
    };

    const opts: AddEventListenerOptions = { passive: true };
    window.addEventListener('pointermove', onPointerMove, opts);
    window.addEventListener('pointerover', onPointerOver, opts);
    window.addEventListener('pointerout', onPointerOut, opts);

    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerover', onPointerOver);
      window.removeEventListener('pointerout', onPointerOut);
      cancelAnimationFrame(state.raf);
      state.running = false;
      html.classList.remove(HTML_ACTIVE_CLASS);
    };
  }, [enabled]);

  if (!enabled) return null;

  return (
    <>
      {/* Ring first, dot after — the dot paints on top at the same z-index. */}
      <div ref={ringRef} className={styles.ring} aria-hidden="true">
        <div className={styles.ringShape}>
          <div className={styles.ringFill} />
        </div>
      </div>
      <div ref={dotRef} className={styles.dot} aria-hidden="true">
        <div className={styles.dotShape} />
      </div>
    </>
  );
}
