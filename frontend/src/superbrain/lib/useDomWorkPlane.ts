import { useLayoutEffect, useRef, useState } from 'react';
import { useThree } from '@react-three/fiber';
import { getTabStoreSnapshot, type MaterializedTabRecord } from './tabStore';

/** Presentation ownership only. A measured operational reader or pending
 * conversation dialog owns its readable surface; do not paint a second slab
 * over the cortex. Approval authority stays in the existing adapter callbacks.
 * Standalone/lab scenes without that owner keep their 3D surface. */
export function useDomWorkPlane(tab: MaterializedTabRecord): boolean {
  const canvas = useThree(state => state.gl.domElement);
  const invalidate = useThree(state => state.invalidate);
  const owns = useRef(false);
  const [domOwned, setDomOwned] = useState(false);

  useLayoutEffect(() => {
    const host = canvas?.closest('.lm-app');
    const conversationApproval = tab.kind === 'approval' && tab.approval?.requestRef === 'conversation-approval';
    if (!host || (tab.kind !== 'content' && !conversationApproval)) return;
    const selector = conversationApproval
      ? '.gagos-chrome[data-approval-pending="true"] .approval-panel[role="alertdialog"]'
      : '.lm-surface';
    let plane: HTMLElement | null = null;
    let resize: ResizeObserver | null = null;
    let layout: MutationObserver | null = null;
    const measure = () => {
      const next = host.querySelector<HTMLElement>(selector);
      if (next !== plane) {
        if (plane) resize?.unobserve(plane);
        plane = next;
        if (plane) resize?.observe(plane);
        layout?.disconnect();
        layout?.observe(host, { attributes: true, attributeFilter: ['data-working', 'data-being-focus', 'data-being-phase', 'data-experience-mode', 'style', 'class'] });
        if (plane) layout?.observe(plane, { attributes: true, attributeFilter: ['data-workspace-id', 'data-workspace-collapsed', 'role', 'hidden', 'style', 'class'] });
        const chrome = conversationApproval ? plane?.closest('.gagos-chrome') : null;
        if (chrome) layout?.observe(chrome, { attributes: true, attributeFilter: ['data-approval-pending', 'hidden', 'style', 'class'] });
      }
      const rect = plane?.getBoundingClientRect();
      const stage = canvas.getBoundingClientRect();
      const style = plane ? window.getComputedStyle(plane) : null;
      const identityMatches = conversationApproval || plane?.getAttribute('data-workspace-id') === tab.id;
      const visible = !!plane && identityMatches && !plane.closest('[hidden]')
        && style?.display !== 'none' && style?.visibility !== 'hidden'
        && !!rect && [rect.left, rect.top, rect.width, rect.height, stage.left, stage.top, stage.width, stage.height].every(Number.isFinite)
        && rect.width > 0 && rect.height > 0 && stage.width > 0 && stage.height > 0
        && rect.right > stage.left && rect.left < stage.right && rect.bottom > stage.top && rect.top < stage.bottom;
      // The product's observed Stop replaces its actionable decision panel
      // with a held-request notice. Keep that same conversation request
      // delegated: missing-panel fallback must not revive 3D approval targets.
      // This is presentation only; it cannot settle or authorize the request.
      const delegated = visible || (conversationApproval && host.getAttribute('data-being-phase') === 'stopped');
      // Close changes the DOM identity before an older R3F prop can update.
      // Read the existing retirement owner so the delegated slab cannot flash
      // back at its old body-local location during that handoff.
      const lifecycle = getTabStoreSnapshot().tabs.find(record => record.id === tab.id)?.lifecycle ?? tab.lifecycle;
      if (!delegated && lifecycle === 'retracting') return;
      if (owns.current === delegated) return;
      owns.current = delegated;
      setDomOwned(delegated);
      invalidate();
    };
    resize = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : null;
    layout = typeof MutationObserver === 'function' ? new MutationObserver(measure) : null;
    const discovery = typeof MutationObserver === 'function' ? new MutationObserver(() => {
      if (host.querySelector(selector) !== plane) measure();
    }) : null;
    resize?.observe(canvas);
    discovery?.observe(host, { childList: true, subtree: true,
      ...(conversationApproval ? { attributes: true, attributeFilter: ['data-approval-pending', 'role', 'class'] } : {}),
    });
    // Observe Stop even on a cold mount with no dialog: next === plane ===
    // null would otherwise skip the ownership observer's initial registration.
    layout?.observe(host, { attributes: true, attributeFilter: ['data-working', 'data-being-focus', 'data-being-phase', 'data-experience-mode', 'style', 'class'] });
    measure();
    window.addEventListener('resize', measure);
    window.addEventListener('transitionend', measure, true);
    const viewport = window.visualViewport;
    viewport?.addEventListener('resize', measure); viewport?.addEventListener('scroll', measure);
    return () => {
      resize?.disconnect(); layout?.disconnect(); discovery?.disconnect();
      window.removeEventListener('resize', measure);
      window.removeEventListener('transitionend', measure, true);
      viewport?.removeEventListener('resize', measure); viewport?.removeEventListener('scroll', measure);
    };
  }, [canvas, invalidate, tab.id, tab.kind, tab.lifecycle, tab.approval?.requestRef]);
  return domOwned;
}
