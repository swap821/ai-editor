import { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { getAutonomy } from '../../superbrain/lib/aiosAdapter';
import { subscribeCognition } from '../../superbrain/lib/cognitionBus';
import AutonomyLedgerPort from './AutonomyLedgerPort';
import CurriculumPort from './CurriculumPort';
import SkillsPort from './SkillsPort';
import ProposalsPort from './ProposalsPort';
import MemorySearchPort from './MemorySearchPort';
import './organs.css';

/* ─── ORGANS DOCK ──────────────────────────────────────────────────────────────
   Additive, read-only HUD-layer glass console docked TOP-RIGHT, below the topbar,
   COLLAPSED BY DEFAULT. Houses two observability organs: the AUTONOMY LEDGER (the
   brain's earned grown-up capabilities) and the CURRICULUM growth ladder.

   It self-portals into document.body (NOT the frozen #hud-portal-root the canon HUD
   owns) so the shell's stacking context is irrelevant and it can NEVER enter the R3F
   reconciler or perturb the brain's voyage. Pointer-transparent wrapper at z-index
   55 — strictly BELOW the canon command bar / approval / dock (z 60), so a live
   approval decision is always clickable above it.

   The collapsed tab shows a live ⚡N chip from getAutonomy() (already polled by the
   adapter every 20s — zero new poll for the badge) and FLARES on the real
   CAPABILITY EARNED / AUTONOMOUS ACTION / SKILL MASTERED bus events, so the organ
   visibly reacts when the brain EARNS something.
   ──────────────────────────────────────────────────────────────────────────── */

const OPEN_KEY = 'organs-dock-open-v1';
const TAB_KEY = 'organs-dock-tab-v1';

function readBool(key, fallback) {
  try {
    const v = window.localStorage.getItem(key);
    return v === null ? fallback : v === 'true';
  } catch {
    return fallback;
  }
}
const TABS = ['autonomy', 'curriculum', 'skills', 'proposals', 'memory'];
function readTab(fallback) {
  try {
    const v = window.localStorage.getItem(TAB_KEY);
    return TABS.includes(v) ? v : fallback;
  } catch {
    return fallback;
  }
}

export default function OrgansDock() {
  // SSR-safe lazy init (this is a pure client SPA; document always exists at render,
  // but the guard keeps the component honest if ever rendered without a DOM).
  const hasDom = typeof document !== 'undefined';
  // Hydrate open/active from the FRESH localStorage keys (default collapsed). The
  // readers guard window themselves, so these are safe one-shot initializers — no
  // hydration-effect, no setState-in-effect.
  const [open, setOpen] = useState(() => readBool(OPEN_KEY, false));
  // 'autonomy' | 'curriculum' | 'skills' | 'proposals' | 'memory'
  const [active, setActive] = useState(() => readTab('autonomy'));
  const [earned, setEarned] = useState(() => getAutonomy()?.summary?.earned ?? 0);
  const [flaring, setFlaring] = useState(false);
  const flareTimer = useRef(null);
  const tabRef = useRef(null);
  const panelRef = useRef(null);

  // Live earned-count chip + tab flare on real earn/master events. Reuses the
  // adapter's existing poll (it refreshes getAutonomy() and fires the labels).
  useEffect(() => {
    const unsub = subscribeCognition((e) => {
      if (!e) return;
      if (e.type === 'telemetry') {
        // The adapter just refreshed the ledger — re-read the cheap snapshot.
        const next = getAutonomy()?.summary?.earned;
        if (typeof next === 'number') setEarned(next);
        return;
      }
      const label = String(e.label || '');
      if (
        label === 'CAPABILITY EARNED' ||
        label === 'AUTONOMOUS ACTION' ||
        /^SKILL MASTERED/.test(label)
      ) {
        setFlaring(true);
        clearTimeout(flareTimer.current);
        flareTimer.current = setTimeout(() => setFlaring(false), 780);
        const next = getAutonomy()?.summary?.earned;
        if (typeof next === 'number') setEarned(next);
      }
    });
    return () => {
      unsub();
      clearTimeout(flareTimer.current);
    };
  }, []);

  const persist = useCallback((nextOpen) => {
    try {
      window.localStorage.setItem(OPEN_KEY, String(nextOpen));
    } catch {
      // storage unavailable — state still toggles for the session
    }
  }, []);

  const toggle = useCallback(() => {
    setOpen((v) => {
      const next = !v;
      persist(next);
      return next;
    });
  }, [persist]);

  const close = useCallback(() => {
    setOpen(false);
    persist(false);
    if (tabRef.current) tabRef.current.focus();
  }, [persist]);

  const pickTab = useCallback((tab) => {
    setActive(tab);
    try {
      window.localStorage.setItem(TAB_KEY, tab);
    } catch {
      // ignore
    }
  }, []);

  // Esc collapses; focus moves into the panel on open.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') close();
    };
    document.addEventListener('keydown', onKey);
    if (panelRef.current) panelRef.current.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [open, close]);

  if (!hasDom) return null;

  const dock = (
    <div className="organs-dock" data-open={open ? 'true' : 'false'}>
      <button
        type="button"
        ref={tabRef}
        className="organs-tab"
        aria-expanded={open}
        aria-label="Open organs dock"
        onClick={toggle}
      >
        <span>▣ ORGANS</span>
        {earned > 0 && (
          <span className="organs-tab-chip">⚡{earned}</span>
        )}
        <span
          className={`organs-tab-pip${flaring ? ' is-flaring' : ''}`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <section
          ref={panelRef}
          tabIndex={-1}
          role="dialog"
          aria-label="Organs dock"
          className="organs-panel glass-surface"
        >
          <header className="organs-head">
            {/* Eyebrow is decorative; with 5 tabs on a 360px header it is icon-only
                (the dot) so the tablist fits without truncating tab labels. */}
            <span className="organs-eyebrow organs-eyebrow--icon" aria-label="Organs">
              <span aria-hidden="true" />
            </span>
            <div className="organs-switch" role="tablist" aria-label="Organ ports">
              <button
                type="button"
                role="tab"
                aria-selected={active === 'autonomy'}
                className={active === 'autonomy' ? 'is-active' : ''}
                onClick={() => pickTab('autonomy')}
              >
                Autonomy
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={active === 'curriculum'}
                className={active === 'curriculum' ? 'is-active' : ''}
                onClick={() => pickTab('curriculum')}
              >
                Growth
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={active === 'skills'}
                className={active === 'skills' ? 'is-active' : ''}
                onClick={() => pickTab('skills')}
              >
                Skills
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={active === 'proposals'}
                className={active === 'proposals' ? 'is-active' : ''}
                onClick={() => pickTab('proposals')}
              >
                Proposals
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={active === 'memory'}
                className={active === 'memory' ? 'is-active' : ''}
                onClick={() => pickTab('memory')}
              >
                Memory
              </button>
            </div>
            <button
              type="button"
              className="organs-close"
              aria-label="Collapse organs dock"
              onClick={close}
            >
              ×
            </button>
          </header>
          <div className="organs-body">
            {active === 'autonomy' ? (
              <AutonomyLedgerPort />
            ) : active === 'curriculum' ? (
              <CurriculumPort />
            ) : active === 'skills' ? (
              <SkillsPort />
            ) : active === 'proposals' ? (
              <ProposalsPort />
            ) : (
              <MemorySearchPort />
            )}
          </div>
          <i className="glass-grain" aria-hidden="true" />
        </section>
      )}
    </div>
  );

  return createPortal(dock, document.body);
}
