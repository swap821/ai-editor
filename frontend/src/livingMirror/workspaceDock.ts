const WORKSPACE_DOCK_GAP_PX = 12;
const WORKSPACE_DOCK_CLEARANCE_PROPERTY = '--lm-workspace-dock-clearance';

export function calculateWorkspaceDockClearance(rootBottom: number, composerTop: number, gap = WORKSPACE_DOCK_GAP_PX): number | null {
  if (![rootBottom, composerTop, gap].every(Number.isFinite) || gap < 0) return null;
  return Math.max(0, Math.ceil(rootBottom - composerTop + gap));
}

/** Keep the mobile DOM work plane above the composer's real, possibly keyboard-shifted dock. */
export function installWorkspaceDockTracking(root: HTMLElement, host: Window = window): () => void {
  let animationFrame: number | null = null;
  let disposed = false;

  const update = () => {
    animationFrame = null;
    if (disposed) return;

    const composer = root.querySelector<HTMLElement>('.gagos-chat');
    const rootBounds = root.getBoundingClientRect();
    const composerBounds = composer?.getBoundingClientRect();
    const clearance = rootBounds.height > 0 && composerBounds && composerBounds.height > 0
      ? calculateWorkspaceDockClearance(rootBounds.bottom, composerBounds.top)
      : null;

    if (clearance === null) {
      root.style.removeProperty(WORKSPACE_DOCK_CLEARANCE_PROPERTY);
      return;
    }

    root.style.setProperty(WORKSPACE_DOCK_CLEARANCE_PROPERTY, `${clearance}px`);
  };

  const scheduleUpdate = () => {
    if (animationFrame !== null || disposed) return;
    if (typeof host.requestAnimationFrame === 'function') {
      animationFrame = host.requestAnimationFrame(update);
    } else {
      update();
    }
  };

  const viewport = host.visualViewport;
  const hostWithObservers = host as Window & { ResizeObserver?: typeof ResizeObserver };
  const ResizeObserverConstructor = hostWithObservers.ResizeObserver;
  const resizeObserver = ResizeObserverConstructor
    ? new ResizeObserverConstructor(scheduleUpdate)
    : null;
  resizeObserver?.observe(root);
  const composer = root.querySelector<HTMLElement>('.gagos-chat');
  if (composer) resizeObserver?.observe(composer);

  root.addEventListener('transitionend', scheduleUpdate);
  host.addEventListener('resize', scheduleUpdate);
  viewport?.addEventListener('resize', scheduleUpdate);
  viewport?.addEventListener('scroll', scheduleUpdate);
  scheduleUpdate();

  return () => {
    disposed = true;
    root.removeEventListener('transitionend', scheduleUpdate);
    host.removeEventListener('resize', scheduleUpdate);
    viewport?.removeEventListener('resize', scheduleUpdate);
    viewport?.removeEventListener('scroll', scheduleUpdate);
    resizeObserver?.disconnect();
    if (animationFrame !== null && typeof host.cancelAnimationFrame === 'function') {
      host.cancelAnimationFrame(animationFrame);
    }
    root.style.removeProperty(WORKSPACE_DOCK_CLEARANCE_PROPERTY);
  };
}
