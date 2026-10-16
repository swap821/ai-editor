const WORKSPACE_DOCK_GAP_PX = 12;
const WORKSPACE_DOCK_CLEARANCE_PROPERTY = '--lm-workspace-dock-clearance';
const WORKSPACE_APP_HEIGHT_PROPERTY = '--lm-workspace-app-height';
// Existing CSS's compact/tall boundary, applied to the available app box.
// Private presentation geometry only; not a workspace/task fact.
const TALL_WORKSPACE_HEIGHT_PX = 740;
const PERMISSION_WORK_RESERVATION_PROPERTY = '--lm-permission-work-reservation';
const HEADER_BOTTOM_PROPERTY = '--lm-header-bottom';
const MODE_SWITCH_WIDTH_PROPERTY = '--lm-mode-switch-width';
const MODE_SWITCH_HEIGHT_PROPERTY = '--lm-mode-switch-height';

export function calculateWorkspaceDockClearance(rootBottom: number, composerTop: number, gap = WORKSPACE_DOCK_GAP_PX): number | null {
  if (![rootBottom, composerTop, gap].every(Number.isFinite) || gap < 0) return null;
  return Math.max(0, Math.ceil(rootBottom - composerTop + gap));
}

/** Keep the mobile DOM work plane above the composer's real, possibly keyboard-shifted dock. */
export function installWorkspaceDockTracking(root: HTMLElement, host: Window = window): () => void {
  let animationFrame: number | null = null;
  let disposed = false;
  let permissionChrome: HTMLElement[] = [];

  const update = () => {
    animationFrame = null;
    if (disposed) return;

    const composer = root.querySelector<HTMLElement>('.gagos-chat');
    const rootBounds = root.getBoundingClientRect();
    const appHeight = Number.isFinite(rootBounds.height) && rootBounds.height > 0
      ? Math.floor(rootBounds.height) : null;
    const composerBounds = composer?.getBoundingClientRect();
    const headerBounds = root.querySelector<HTMLElement>('.lm-header')?.getBoundingClientRect();
    const modeBounds = root.querySelector<HTMLElement>('.gagos-experience-switch')?.getBoundingClientRect();
    const headerBottom = rootBounds.height > 0 && headerBounds && headerBounds.width > 0 && headerBounds.height > 0
      && Number.isFinite(headerBounds.bottom - rootBounds.top) && headerBounds.bottom > rootBounds.top
      ? Math.ceil(headerBounds.bottom - rootBounds.top)
      : null;
    const modeSize = modeBounds && [modeBounds.width, modeBounds.height].every(value => Number.isFinite(value) && value > 0)
      ? { width: Math.ceil(modeBounds.width), height: Math.ceil(modeBounds.height) }
      : null;
    const clearance = rootBounds.height > 0 && composerBounds && composerBounds.height > 0
      ? calculateWorkspaceDockClearance(rootBounds.bottom, composerBounds.top)
      : null;

    // Permission owns the work plane, not the body band. Measure only its
    // non-scrolling chrome; expanded proposal content must not grow this slot.
    const panel = root.querySelector<HTMLElement>('.approval-panel');
    const nextChrome = panel
      ? Array.from(panel.querySelectorAll<HTMLElement>('.approval-head, .approval-actions'))
      : [];
    for (const element of permissionChrome) if (!nextChrome.includes(element)) resizeObserver?.unobserve(element);
    for (const element of nextChrome) if (!permissionChrome.includes(element)) resizeObserver?.observe(element);
    permissionChrome = nextChrome;
    const heights = permissionChrome.map(element => element.getBoundingClientRect().height);
    let reservation: number | null = null;
    if (panel && heights.length === 2 && heights.every(height => Number.isFinite(height) && height > 0)) {
      const paint = host.getComputedStyle(panel);
      const borders = parseFloat(paint.borderTopWidth) + parseFloat(paint.borderBottomWidth);
      //44px readable proposal,8px clear separation from the body. Neither is a
      // task fact; this observer-fed property is private presentation geometry.
      if (Number.isFinite(borders)) reservation = Math.ceil(heights[0] + heights[1] + borders + 44 + 8);
    }
    // Finish reads before layout writes; no per-frame polling. These private
    // header metrics keep control rows clear even when fonts or labels resize.
    if (clearance === null) root.style.removeProperty(WORKSPACE_DOCK_CLEARANCE_PROPERTY);
    else root.style.setProperty(WORKSPACE_DOCK_CLEARANCE_PROPERTY, `${clearance}px`);
    if (appHeight === null) root.style.removeProperty(WORKSPACE_APP_HEIGHT_PROPERTY);
    else root.style.setProperty(WORKSPACE_APP_HEIGHT_PROPERTY, `${appHeight}px`);
    if (appHeight === null) delete root.dataset.workspaceHeight;
    else root.dataset.workspaceHeight = appHeight < TALL_WORKSPACE_HEIGHT_PX ? 'compact' : 'tall';
    if (reservation === null) root.style.removeProperty(PERMISSION_WORK_RESERVATION_PROPERTY);
    else root.style.setProperty(PERMISSION_WORK_RESERVATION_PROPERTY, `${reservation}px`);
    if (headerBottom === null) root.style.removeProperty(HEADER_BOTTOM_PROPERTY);
    else root.style.setProperty(HEADER_BOTTOM_PROPERTY, `${headerBottom}px`);
    if (modeSize === null) {
      root.style.removeProperty(MODE_SWITCH_WIDTH_PROPERTY);
      root.style.removeProperty(MODE_SWITCH_HEIGHT_PROPERTY);
    } else {
      root.style.setProperty(MODE_SWITCH_WIDTH_PROPERTY, `${modeSize.width}px`);
      root.style.setProperty(MODE_SWITCH_HEIGHT_PROPERTY, `${modeSize.height}px`);
    }
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
  const hostWithObservers = host as Window & { ResizeObserver?: typeof ResizeObserver; MutationObserver?: typeof MutationObserver };
  const ResizeObserverConstructor = hostWithObservers.ResizeObserver;
  const resizeObserver = ResizeObserverConstructor
    ? new ResizeObserverConstructor(scheduleUpdate)
    : null;
  resizeObserver?.observe(root);
  const composer = root.querySelector<HTMLElement>('.gagos-chat');
  if (composer) resizeObserver?.observe(composer);
  for (const selector of ['.lm-header', '.gagos-experience-switch']) {
    const element = root.querySelector(selector);
    if (element) resizeObserver?.observe(element);
  }
  // The dialog is admitted/removed as a direct chrome child. Do not observe
  // streaming text, editor mutations or our own CSS-property writes.
  const chrome = root.querySelector('.gagos-chrome');
  const mutationObserver = chrome && hostWithObservers.MutationObserver
    ? new hostWithObservers.MutationObserver(scheduleUpdate)
    : null;
  if (chrome) mutationObserver?.observe(chrome, { childList: true });

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
    mutationObserver?.disconnect();
    if (animationFrame !== null && typeof host.cancelAnimationFrame === 'function') {
      host.cancelAnimationFrame(animationFrame);
    }
    root.style.removeProperty(WORKSPACE_DOCK_CLEARANCE_PROPERTY);
    root.style.removeProperty(WORKSPACE_APP_HEIGHT_PROPERTY);
    delete root.dataset.workspaceHeight;
    root.style.removeProperty(PERMISSION_WORK_RESERVATION_PROPERTY);
    root.style.removeProperty(HEADER_BOTTOM_PROPERTY);
    root.style.removeProperty(MODE_SWITCH_WIDTH_PROPERTY);
    root.style.removeProperty(MODE_SWITCH_HEIGHT_PROPERTY);
  };
}
