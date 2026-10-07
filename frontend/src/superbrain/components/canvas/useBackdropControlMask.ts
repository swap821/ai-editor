import { useLayoutEffect, useRef } from 'react';
import { useThree } from '@react-three/fiber';
import { MathUtils, Vector4 } from 'three';

// Presentation-only quiet zones, not a second workspace/authority store.
// Keep the lab's standalone field intact when no product host is present.
const CONTROL_SELECTOR = [
  '.lm-header', '.lm-navigation', '.lm-workspace-rail', '.lm-workspace-list',
  '.lm-surface', '.lm-expert-mobile-surfaces__groups', '.lm-connection',
  '.gagos-experience-switch', '.gagos-chat', '.gagos-status',
  '.gagos-approval-hold', '.gagos-verify-toast', '.gagos-humanstate__picker',
  '.gagos-coach', '.gagos-hint', '[role="dialog"]',
].join(',');
export const BACKDROP_CONTROL_LIMIT = 16;
const QUIET_MARGIN = 8;

interface ControlUniforms {
  uControlRects: { value: Vector4[] };
  uControlRectCount: { value: number };
}

/** Observe layout once it changes; never read DOM from a frame/draw callback. */
export function useBackdropControlMask(uniforms: ControlUniforms) {
  const gl = useThree(state => state.gl);
  const invalidate = useThree(state => state.invalidate);
  // Share host eligibility with the draw callback, without a per-draw DOM
  // query or another product/semantic owner. Standalone stays unmodified.
  const productHost = useRef(false);
  useLayoutEffect(() => {
    const canvas = gl.domElement;
    const host = canvas.closest('.lm-app');
    if (!host) return;
    productHost.current = true;
    let controls: Element[] = [];
    const observed = new Set<Element>();

    const measure = () => {
      const stage = canvas.getBoundingClientRect();
      let count = 0;
      let changed = false;
      if (![stage.left, stage.top, stage.width, stage.height].every(Number.isFinite)
        || stage.width <= 0 || stage.height <= 0) {
        // Fail quiet on unavailable layout, rather than reusing stale masks.
        // This disables ONLY optional glyph fragments, never body/intake/DOM.
        count = -1;
      } else {
        for (const control of controls) {
          const rect = control.getBoundingClientRect();
          if (![rect.left, rect.top, rect.width, rect.height].every(Number.isFinite)
            || rect.width <= 0 || rect.height <= 0) continue;
          if (rect.right + QUIET_MARGIN <= stage.left || rect.left - QUIET_MARGIN >= stage.right
            || rect.bottom + QUIET_MARGIN <= stage.top || rect.top - QUIET_MARGIN >= stage.bottom) continue;
          if (count === BACKDROP_CONTROL_LIMIT) { count = -1; break; }
          const x = MathUtils.clamp((rect.left - stage.left - QUIET_MARGIN) / stage.width, 0, 1);
          const y = MathUtils.clamp((stage.bottom - rect.bottom - QUIET_MARGIN) / stage.height, 0, 1);
          const z = MathUtils.clamp((rect.right - stage.left + QUIET_MARGIN) / stage.width, 0, 1);
          const w = MathUtils.clamp((stage.bottom - rect.top + QUIET_MARGIN) / stage.height, 0, 1);
          const mask = uniforms.uControlRects.value[count++];
          changed ||= mask.x !== x || mask.y !== y || mask.z !== z || mask.w !== w;
          mask.set(x, y, z, w);
        }
      }
      changed ||= uniforms.uControlRectCount.value !== count;
      uniforms.uControlRectCount.value = count;
      // A layout change must repaint even while ambient motion is paused.
      if (changed) invalidate();
    };

    const resize = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
    const discover = () => {
      controls = Array.from(host.querySelectorAll(CONTROL_SELECTOR));
      const targets = new Set<Element>([canvas, ...controls]);
      for (const element of observed) {
        if (!targets.has(element)) { resize?.unobserve(element); observed.delete(element); }
      }
      for (const element of targets) {
        if (!observed.has(element)) { resize?.observe(element); observed.add(element); }
      }
      measure();
    };
    const mutation = typeof MutationObserver !== 'undefined' ? new MutationObserver(records => {
      // Token text mutations aren't layout subscriptions. ResizeObserver owns
      // text-driven reflow; discover only element/attribute layout changes.
      if (records.some(record => record.type === 'attributes'
        || [...record.addedNodes, ...record.removedNodes].some(node => node instanceof Element))) discover();
    }) : null;
    discover();
    mutation?.observe(host, { subtree: true, childList: true, attributes: true,
      attributeFilter: ['class', 'style', 'hidden', 'open', 'data-working', 'data-being-focus',
        'data-experience-mode', 'data-details-open', 'data-keyboard-open'],
    });
    const viewport = window.visualViewport;
    viewport?.addEventListener('resize', measure);
    viewport?.addEventListener('scroll', measure);
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    host.addEventListener('transitionend', measure, true);
    return () => {
      productHost.current = false;
      mutation?.disconnect();
      resize?.disconnect();
      viewport?.removeEventListener('resize', measure);
      viewport?.removeEventListener('scroll', measure);
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
      host.removeEventListener('transitionend', measure, true);
    };
  }, [gl, invalidate, uniforms]);
  return productHost;
}
