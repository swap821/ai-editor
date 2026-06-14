import { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { getAutonomy } from '../../superbrain/lib/aiosAdapter';
import { subscribeCognition } from '../../superbrain/lib/cognitionBus';
import AutonomyLedgerPort from './AutonomyLedgerPort';
import CurriculumPort from './CurriculumPort';
import SkillsPort from './SkillsPort';
import ProposalsPort from './ProposalsPort';
import MemorySearchPort from './MemorySearchPort';
import ZoneProbePort from './ZoneProbePort';
import PlanPort from './PlanPort';
import ModelsPort from './ModelsPort';
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
// Grouped nav taxonomy — the single source of truth for the dock's organs. The
// flat row stopped scaling at 8 organs (illegible on a fixed 360px header), so the
// header now shows only SECTION + active organ and a slide-down grouped menu opens
// the full categorized list on demand.
const NAV = [
  {
    section: 'GOVERNANCE',
    items: [
      { id: 'autonomy', label: 'Autonomy' },
      { id: 'proposals', label: 'Proposals' },
    ],
  },
  {
    section: 'LEARNING',
    items: [
      { id: 'curriculum', label: 'Growth' },
      { id: 'skills', label: 'Skills' },
    ],
  },
  {
    section: 'MEMORY',
    items: [{ id: 'memory', label: 'Memory' }],
  },
  {
    section: 'REASONING',
    items: [{ id: 'plan', label: 'Plan' }],
  },
  {
    section: 'SECURITY',
    items: [{ id: 'zone', label: 'Zone Probe' }],
  },
  {
    section: 'SYSTEM',
    items: [{ id: 'models', label: 'Models' }],
  },
];
const NAV_ITEMS = NAV.flatMap((g) => g.items); // flat lookup
const TAB_IDS = NAV_ITEMS.map((i) => i.id); // validates persisted tab
const sectionOf = (id) => NAV.find((g) => g.items.some((i) => i.id === id))?.section ?? '';
const labelOf = (id) => NAV_ITEMS.find((i) => i.id === id)?.label ?? '';

function readTab(fallback) {
  try {
    const v = window.localStorage.getItem(TAB_KEY);
    return TAB_IDS.includes(v) ? v : fallback;
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
  // One of TAB_IDS (autonomy | proposals | curriculum | skills | memory | plan |
  // zone | models) — validated against the NAV taxonomy on read.
  const [active, setActive] = useState(() => readTab('autonomy'));
  const [earned, setEarned] = useState(() => getAutonomy()?.summary?.earned ?? 0);
  const [flaring, setFlaring] = useState(false);
  // The grouped nav menu is closed on every open (collapsed-by-default posture).
  const [menuOpen, setMenuOpen] = useState(false);
  const flareTimer = useRef(null);
  const tabRef = useRef(null);
  const panelRef = useRef(null);
  const menuRef = useRef(null);
  const navTriggerRef = useRef(null);

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
    setMenuOpen(false);
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
    // Selecting an organ closes the menu (it has done its job).
    setMenuOpen(false);
  }, []);

  // Esc: close the menu first if it's open, else collapse the dock. Focus moves
  // into the panel on open.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      if (menuOpen) {
        setMenuOpen(false);
        if (navTriggerRef.current) navTriggerRef.current.focus();
      } else {
        close();
      }
    };
    document.addEventListener('keydown', onKey);
    if (panelRef.current) panelRef.current.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [open, close, menuOpen]);

  // Outside click while the menu is open closes it (but a click on the trigger is
  // its own toggle, so ignore that target). Mirrors the keydown effect's cleanup.
  useEffect(() => {
    if (!menuOpen) return undefined;
    const onDown = (e) => {
      const t = e.target;
      if (menuRef.current && menuRef.current.contains(t)) return;
      if (navTriggerRef.current && navTriggerRef.current.contains(t)) return;
      setMenuOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [menuOpen]);

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
            {/* Two-tier nav: the header shows only SECTION + active organ; the full
                grouped list lives behind this trigger (scales past 8 organs on the
                fixed 360px header without truncating labels). */}
            <button
              type="button"
              ref={navTriggerRef}
              className="organs-navtrigger"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              aria-label="Choose organ"
              onClick={() => setMenuOpen((v) => !v)}
            >
              <span className="organs-navtrigger-section">{sectionOf(active)}</span>
              <span className="organs-navtrigger-name">{labelOf(active)}</span>
              <span className="organs-navtrigger-caret" aria-hidden="true">▾</span>
            </button>
            <button
              type="button"
              className="organs-close"
              aria-label="Collapse organs dock"
              onClick={close}
            >
              ×
            </button>
          </header>

          {menuOpen && (
            <nav ref={menuRef} className="organs-menu" role="menu" aria-label="Organ ports">
              {NAV.map((group) => (
                <div className="organs-menu-group" key={group.section}>
                  <p className="organs-menu-eyebrow">{group.section}</p>
                  {group.items.map((it) => (
                    <button
                      key={it.id}
                      type="button"
                      role="menuitemradio"
                      aria-checked={active === it.id}
                      className={`organs-menu-item${active === it.id ? ' is-active' : ''}`}
                      onClick={() => pickTab(it.id)}
                    >
                      <span className="organs-menu-pip" aria-hidden="true" />
                      {it.label}
                    </button>
                  ))}
                </div>
              ))}
            </nav>
          )}

          <div className="organs-body">
            {active === 'autonomy' ? (
              <AutonomyLedgerPort />
            ) : active === 'curriculum' ? (
              <CurriculumPort />
            ) : active === 'skills' ? (
              <SkillsPort />
            ) : active === 'proposals' ? (
              <ProposalsPort />
            ) : active === 'memory' ? (
              <MemorySearchPort />
            ) : active === 'plan' ? (
              <PlanPort />
            ) : active === 'zone' ? (
              <ZoneProbePort />
            ) : (
              <ModelsPort />
            )}
          </div>
          <i className="glass-grain" aria-hidden="true" />
        </section>
      )}
    </div>
  );

  return createPortal(dock, document.body);
}
