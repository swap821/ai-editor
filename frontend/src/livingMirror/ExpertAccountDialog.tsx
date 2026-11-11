import { useEffect, useRef } from 'react';
import SovereigntyPanel from '../superbrain/components/ui/SovereigntyPanel';

/** Product focus adapter; the managed ceremony keeps all account authority. */
export function ExpertAccountDialog({ onClose }: { onClose: () => void }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const dialog = host.current?.querySelector<HTMLElement>('[role="dialog"]');
    if (!dialog) return;
    const controls = () => Array.from(dialog.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    )).filter(element => !element.closest('[hidden], [inert], [aria-hidden="true"]'));
    // Focus Close, not a name/credential field that would raise the keyboard.
    controls()[0]?.focus({ preventScroll: true });
    const onKeyDown = (event: KeyboardEvent) => {
      // Escape/reveal lockout remain exclusively the ceremony's decision.
      if (event.key !== 'Tab' || event.defaultPrevented) return;
      const focusable = controls();
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;
      const active = dialog.ownerDocument.activeElement;
      if (!dialog.contains(active) || (event.shiftKey ? active === first : active === last)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus({ preventScroll: true });
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);
  return <div ref={host} style={{ display: 'contents' }}><SovereigntyPanel onClose={onClose} /></div>;
}
