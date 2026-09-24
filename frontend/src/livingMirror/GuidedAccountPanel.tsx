import { useEffect, useRef } from 'react';
import type { SovereignStatus } from '../superbrain/lib/sovereignIdentity';

type GuidedAccountPanelProps = {
  status: SovereignStatus;
  onClose: () => void;
  onOpenExpert: () => void;
};

/**
 * The Guided account surface reports measured identity without turning the
 * front door into an authority ceremony. Credential enrollment, presentation,
 * and release remain available through the existing Expert surface.
 */
export function GuidedAccountPanel({ status, onClose, onOpenExpert }: GuidedAccountPanelProps) {
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;

      const panel = panelRef.current;
      if (!panel) return;
      const focusable = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => !element.hasAttribute('aria-hidden'));
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const measured = status.measured === 'measured';
  const linked = measured && Boolean(status.operatorId);

  return (
    <section
      ref={panelRef}
      className="gagos-account-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="gagos-account-panel-title"
      aria-describedby="gagos-account-panel-description"
    >
      <header className="gagos-account-panel__head">
        <div>
          <span className="gagos-account-panel__eyebrow">ACCOUNT CONNECTION</span>
          <h2 id="gagos-account-panel-title">
            {measured ? (linked ? 'Account linked' : 'Account not linked') : 'Account status unavailable'}
          </h2>
        </div>
        <button ref={closeRef} type="button" className="gagos-account-panel__close" onClick={onClose}>
          Close
        </button>
      </header>

      <div className="gagos-account-panel__body">
        <p id="gagos-account-panel-description">
          {measured
            ? linked
              ? 'GAGOS measured an active account connection. This panel only reports status; it does not change what GAGOS is allowed to do.'
              : 'GAGOS measured no linked account. You can still ask questions, review work, and stop the system at any time.'
            : 'GAGOS could not confirm the account connection yet. No account state is being guessed.'}
        </p>
        <p className="gagos-account-panel__note">
          Detailed account controls are available in Expert / Mirror.
        </p>
        <div className="gagos-account-panel__actions">
          <button type="button" className="gagos-account-panel__primary" onClick={onOpenExpert}>
            Open Expert / Mirror
          </button>
          <button type="button" className="gagos-account-panel__secondary" onClick={onClose}>
            Keep working
          </button>
        </div>
      </div>
    </section>
  );
}
