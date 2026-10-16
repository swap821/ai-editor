import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';

/** Compact working layout. Slots move controls, never their state owners. */
export function CompactWorkingChrome({ children, onHost, blocked }: {
  children: ReactNode;
  onHost: (element: HTMLDivElement | null) => void;
  blocked: boolean;
}) {
  const details = useRef<HTMLDetailsElement>(null);
  const summary = useRef<HTMLElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [availableHeight, setAvailableHeight] = useState(44);
  const measure = useCallback(() => {
    const work = details.current?.closest('.lm-app')?.querySelector('.lm-surface');
    if (!summary.current || !work) return;
    // Popup may cover the decorative body, never the result/decision plane.
    setAvailableHeight(Math.max(44, Math.floor(work.getBoundingClientRect().top - summary.current.getBoundingClientRect().bottom - 16)));
  }, []);
  useLayoutEffect(() => {
    if (open && !blocked) { measure(); return; }
    // The action owner may already have focused its reader or decision. Only
    // retire focus still owned by content that this disclosure just hid.
    if (!content.current?.contains(document.activeElement)) return;
    summary.current?.focus({ preventScroll: true });
  }, [open, blocked, measure]);
  useEffect(() => {
    const element = details.current;
    const root = element?.closest('.lm-app');
    if (!element || !root) return;
    const work = root.querySelector('.lm-surface');
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : null;
    observer?.observe(root);
    if (work) observer?.observe(work);
    if (summary.current) observer?.observe(summary.current);
    // The existing dock owner settles composer/header/permission geometry by
    // publishing root styles. That can MOVE a fixed-size reader without any
    // ResizeObserver notification. Watch only that presentation boundary,
    // not streaming text or our own menu-height write; no frame polling.
    const layoutObserver = typeof MutationObserver === 'function' ? new MutationObserver(measure) : null;
    layoutObserver?.observe(root, { attributes: true, attributeFilter: ['style'] });
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !element.contains(event.target)) setOpen(false);
    };
    const closeNavigation = (event: MouseEvent) => {
      // Portal events follow their React owner tree, not this DOM slot. A
      // native boundary observes the actual navigation without replacing it.
      if (event.target instanceof Element && event.target.closest('nav button')) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented || !element.open) return;
      const childNavigation = event.target instanceof Element
        ? event.target.closest<HTMLDetailsElement>('.lm-expert-mobile-surfaces') : null;
      // The existing navigation owner dismisses its open child first. Once
      // closed, capture Escape here before that child's summary consumes it.
      if (childNavigation?.open) return;
      event.preventDefault(); event.stopPropagation(); setOpen(false);
      summary.current?.focus({ preventScroll: true });
    };
    element.addEventListener('click', closeNavigation);
    element.addEventListener('keydown', closeOnEscape, true);
    document.addEventListener('pointerdown', closeOutside, true);
    window.addEventListener('resize', measure);
    measure();
    return () => {
      observer?.disconnect();
      layoutObserver?.disconnect();
      element.removeEventListener('click', closeNavigation);
      element.removeEventListener('keydown', closeOnEscape, true);
      document.removeEventListener('pointerdown', closeOutside, true);
      window.removeEventListener('resize', measure);
    };
  }, [measure]);
  return <details ref={details} className="lm-compact-more" open={open && !blocked}
    onToggle={(event) => setOpen(event.currentTarget.open && !blocked)}>
    <summary ref={summary} aria-disabled={blocked || undefined} tabIndex={blocked ? -1 : 0}
      onClick={(event) => { if (blocked) event.preventDefault(); }}>More</summary>
    <div ref={content} className="lm-compact-more__content" style={{ maxHeight: availableHeight }}>
      {children}
      <div ref={onHost} className="lm-compact-more__slots" />
    </div>
  </details>;
}
