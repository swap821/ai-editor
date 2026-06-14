'use client';

import { FormEvent, RefObject, useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion, useReducedMotion } from 'motion/react';
import { Html } from '@react-three/drei';
import { publishCognition, subscribeCognition } from '@/lib/cognitionBus';
import { useMetric, useMetricHistory, type MetricKey } from '@/lib/metricsStore';
import { isSoundOn, startSound, stopSound } from '@/lib/soundEngine';
import {
  getLastTelemetry,
  getLinkState,
  getPendingApproval,
  type AiosTelemetry,
  type PendingApproval,
} from '@/lib/aiosAdapter';
import { useQualityTier } from '@/components/QualityTierProvider';
import ApprovalPanel from './ApprovalPanel';

export type CognitiveMode = 'observe' | 'synthesize' | 'orchestrate';

/* The live turn phase the HUD actually shows. REST is a first-class phase
 * (honest standby), not the absence of one. It is DERIVED from the cognition
 * bus (no phase event exists; see the reducer in the component), never from an
 * operator toggle. The operator's mode prop is a manual lens override only. */
export type Phase = 'rest' | 'observe' | 'synthesize' | 'orchestrate';

interface SuperbrainHUDProps {
  mode: CognitiveMode;
  activity: number;
  lastDirective: string;
  onModeChange: (mode: CognitiveMode) => void;
  onDirective: (directive: string) => void;
  /** Operator's sky choice (voyage = canon default; layered adds his
   *  photographic dome BEHIND the moving field). Persisted by the click. */
  skyMode?: 'voyage' | 'layered';
  onSkyModeChange?: (sky: 'voyage' | 'layered') => void;
  /** Operator's cortex surface (web = canon shell; organ = his painted
   *  flesh under the same living layers). Persisted by the click. */
  surface?: 'web' | 'organ';
  onSurfaceChange?: (surface: 'web' | 'organ') => void;
}

/* ---------- Phase copy ----------
 * Describes the REAL derived phase truthfully. REST has honest standby copy;
 * the work phases describe what the brain is actually doing this turn. No
 * em-dashes; the middle dot ( · ) is the codebase prose convention. */
const PHASE_COPY: Record<Phase, { title: string; detail: string }> = {
  rest: {
    title: 'Holding at the knowledge horizon',
    detail: 'Standby. No directive in flight.',
  },
  observe: {
    title: 'Observing the knowledge horizon',
    detail: 'Recalling trails and mapping relationships.',
  },
  synthesize: {
    title: 'Synthesizing the directive',
    detail: 'Model reasoning toward one execution.',
  },
  orchestrate: {
    /* Honest for BOTH triggers of this phase: the brief directive-snap (the mesh
     * coming to attention, before any tool has fired) AND a live tool dispatch.
     * The old copy ('Dispatching ... real tools') over-claimed during the snap. */
    title: 'Orchestrating the agent mesh',
    detail: 'Engaging the mesh and dispatching tools.',
  },
};

/* One-word phase label for the dispatch-cadence PHASE row. REST reads STANDBY
 * (honest dormancy), the work phases read their verb. */
const PHASE_LABEL: Record<Phase, string> = {
  rest: 'STANDBY',
  observe: 'OBSERVE',
  synthesize: 'SYNTHESIZE',
  orchestrate: 'ORCHESTRATE',
};

/* ---------- Live-phase derivation (pure, unit-tested in src/test/livePhase.test.ts) ----------
 * No phase event exists on the bus, so the live phase is DERIVED from the
 * timestamps of the events that DO exist plus the real `generating` flag.
 * Precedence (a stale event never pins a false phase, hence the windows):
 *   fresh tool dispatch (<4s)  -> ORCHESTRATE (dispatching real tools)
 *   else generating            -> SYNTHESIZE  (model producing text)
 *   else fresh recall (<4s)    -> OBSERVE     (mapping/recalling knowledge)
 *   else the directive snap (<2s) -> ORCHESTRATE (mesh snapped to attention)
 *   else                        -> REST        (honest standby) */
export interface PhaseStamps {
  tool: number;
  burst: number;
  directive: number;
}

export function derivePhaseFrom(now: number, ts: PhaseStamps, generating: boolean): Phase {
  if (now - ts.tool < 4000) return 'orchestrate';
  if (generating) return 'synthesize';
  if (now - ts.burst < 4000) return 'observe';
  if (now - ts.directive < 2000) return 'orchestrate';
  return 'rest';
}

/* ---------- Mode rail (operator's manual lens override) ----------
 * The rail's active item DEFAULTS to follow the derived livePhase; a click
 * pins the operator's lens (a small `pinned` marker shows he is steering). */
const MODE_RAIL: { id: CognitiveMode; num: string; label: string; sub: string }[] = [
  { id: 'observe', num: '01', label: 'OBSERVE', sub: 'Map and orient' },
  { id: 'synthesize', num: '02', label: 'SYNTHESIZE', sub: 'Reason and create' },
  { id: 'orchestrate', num: '03', label: 'ORCHESTRATE', sub: 'Delegate and deliver' },
];

/* ---------- Intake channels · values come from metricsStore (single source of truth) ---------- */
const SOURCE_CHANNELS: { key: MetricKey; name: string; detail: string }[] = [
  { key: 'research', name: 'Research', detail: 'deep archive scan' },
  { key: 'memory', name: 'Memory', detail: 'episodic lattice' },
  { key: 'tools', name: 'Tools', detail: 'runtime mesh' },
  { key: 'signals', name: 'Signals', detail: 'ambient telemetry' },
];

/* ---------- Center port labels (over the brain) ----------
 * Four flat 2D channel labels in the #hud-portal-root portal layer (NEVER
 * scene-pinned Html · the frozen-scene contract). Each label reads ONE real
 * metricsStore value (the SAME number the right-console intake row shows, the
 * single source of truth) and pulses cyan for one beat ONLY when a real bus
 * event touches that channel: a real `tool engaged:` dispatch, or a real
 * `knowledge-acquired` packet. No invented progress, no timer theatre. */
const PORT_CHANNELS: { key: MetricKey; label: string }[] = [
  { key: 'tools', label: 'TOOLS' },
  { key: 'research', label: 'RESEARCH' },
  { key: 'signals', label: 'SIGNALS' },
  { key: 'memory', label: 'MEMORY' },
];

/* Route a REAL dispatched tool to the metric channel that owns that work, so a
 * tool firing pulses the matching port. Same keyword semantics the metricsStore
 * and the intake rows already use (one mapping language across the HUD). */
function toolChannelForPort(tool: string): MetricKey {
  const t = tool.toLowerCase();
  if (/read|search|list|web|fetch|grep|inspect|archive|scan/.test(t)) return 'research';
  if (/recall|memory|episodic|lesson|skill|remember/.test(t)) return 'memory';
  if (/signal|telemetry|ambient|monitor|observe/.test(t)) return 'signals';
  return 'tools'; // plan/create/edit/execute/verify/orchestrate -> runtime mesh
}

/* ---------- Knowledge-acquired -> intake row routing (dot flash only) ---------- */
/* Keyword matchers checked in order; fall back to a rotating index so every
 * row eventually breathes even for unrecognized labels. */
const SOURCE_MATCH_ORDER: { row: number; pattern: RegExp }[] = [
  { row: 3, pattern: /signal|telemetry|ambient/i },
  { row: 1, pattern: /memory|episodic/i },
  { row: 0, pattern: /research|archive|causal|graph|scan/i },
  { row: 2, pattern: /tool|runtime|lattice|mesh|semantic/i },
];

function matchSourceRow(label: string, rotateRef: { current: number }): number {
  for (const { row, pattern } of SOURCE_MATCH_ORDER) {
    if (pattern.test(label)) return row;
  }
  rotateRef.current = (rotateRef.current + 1) % SOURCE_CHANNELS.length;
  return rotateRef.current;
}

/* ---------- Agent mesh ----------
 * A card has exactly three HONEST states, each tied to a real signal (no timer
 * churn, no canned detail strings): `processing` when a REAL tool dispatch owns
 * the card, `active` when the directive surge snaps it to attention for the
 * first ~5s of a real turn, else `standby` (honest idle, no invented detail). */
type AgentIconKind = 'compass' | 'magnifier' | 'hammer';
type AgentState = 'active' | 'processing' | 'standby';

const AGENT_DEFS: { name: string; icon: AgentIconKind }[] = [
  { name: 'Planner', icon: 'compass' },
  { name: 'Researcher', icon: 'magnifier' },
  { name: 'Builder', icon: 'hammer' },
];

/* On a real `directive` the mesh visibly snaps to attention for ~5s: the Planner
 * leads, the Researcher digs (keyed to a real event, not a free-running timer).
 * The Builder waits for a real tool dispatch to own its card. */
const FORCED_ON_DIRECTIVE: Record<string, AgentState> = {
  Planner: 'active',
  Researcher: 'active',
};

/** Route a REAL dispatched tool to the card that owns that kind of work. */
function agentRowForTool(tool: string): number {
  const t = tool.toLowerCase();
  if (/plan|orchestr|skill|recall|memory|lesson/.test(t)) return 0; // Planner
  if (/read|search|list|web|fetch|grep|inspect/.test(t)) return 1; // Researcher
  return 2; // Builder · create/edit/execute/verify
}

/* ---------- Living terminal log ----------
 * The causality ledger: the superbrain's real working stream. Every line is a
 * TRUE bus fact (recall / dispatch / verdict / route), never decorative filler.
 * Two real, optional columns ride alongside the text:
 *   verdict  the REAL verifier outcome for the line (the adapter emits the
 *            label 'VERIFICATION GREEN'|'VERIFICATION RED'); null otherwise.
 *   delta    the REAL gain in verified trails this telemetry poll surfaced
 *            (>0 only); null otherwise. Computed from prevVerifiedRef, never
 *            invented. A real hash-chain growth = the one accent moment. */
type TermVerdict = 'pass' | 'fail' | null;

interface TermLine {
  id: number;
  time: string;
  text: string;
  /** Seed lines render static; live lines flash bright then dim via CSS. */
  fresh: boolean;
  bright?: boolean;
  /** REAL verifier outcome for this line (null = not a verdict line). */
  verdict?: TermVerdict;
  /** REAL verified-trail gain this line surfaced (>0 only; null otherwise). */
  delta?: number | null;
}

/* Deterministic seed buffer so SSR and first client render agree. ONE honest
 * static standby line · NOT four event-shaped facts with invented mm:ss stamps
 * (those painted a working history the backend never emitted, which the honest-
 * dormancy law forbids everywhere else in this file). The empty time string
 * renders an empty timestamp cell · this line is a rest state, not a logged
 * event, so it carries no clock and no verdict. Real lines replace it the
 * instant the bus emits its first true fact. */
const SEED_TERM_LINES: TermLine[] = [
  { id: -1, time: '', text: 'Awaiting first directive. Terminal at rest.', fresh: false },
];

const TERM_BUFFER_MAX = 4;

/* ---------- Inline icon set (one deliberate geometric family) ----------
 * These five marks (HexMark brand glyph, ShieldIcon, and the three AgentIcon
 * kinds: compass / magnifier / hammer) are drawn inline ON PURPOSE, not by
 * default. The skill's no-hand-rolled-icons rule has a documented exception for
 * "a single, simple geometric mark"; here the whole set is treated as that one
 * family because a CONSTRAINT forbids a library: this lab tree may not add new
 * imports/dependencies (the port-to-frontend manifest copies an explicit file
 * list, and the product `frontend` tree must build from that port with no extra
 * package). So instead of a per-icon library, the set is unified into one hand:
 * every glyph is a 24x24 viewBox, fill:none, with a single shared stroke family
 * (width 1.6, round caps + joins) applied in globals.css (.brand-mark/.secure-
 * button/.agent-avatar svg). If the dependency constraint is ever lifted, swap
 * the whole set for one icon family (e.g. Phosphor Shield / Compass /
 * MagnifyingGlass / Hammer) in a single commit · do not mix sources. */
const HexMark = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M12 3 4.5 7.2v9.6L12 21l7.5-4.2V7.2L12 3Zm0 4.2 3.8 2.1v5.4L12 16.8l-3.8-2.1V9.3L12 7.2Z" />
  </svg>
);

const ShieldIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M12 3 5 6v5c0 4.6 2.8 7.8 7 10 4.2-2.2 7-5.4 7-10V6l-7-3Z" />
  </svg>
);

const AgentIcon = ({ kind }: { kind: AgentIconKind }) => {
  if (kind === 'compass') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="8" />
        <path d="m9.2 14.8 1.9-4.4 4.4-1.9-1.9 4.4-4.4 1.9Z" />
      </svg>
    );
  }
  if (kind === 'magnifier') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="11" cy="11" r="5.5" />
        <path d="m15.2 15.2 4.3 4.3" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M13.2 5.4 18.6 10.8 16 13.4 10.6 8 13.2 5.4Z" />
      <path d="M10.6 10.6 5.4 15.8l2.8 2.8 5.2-5.2" />
    </svg>
  );
};

/* Reduced motion is read via the REACTIVE `useReducedMotion` hook from
 * motion/react wherever it is needed (component body + the metric/magnetic
 * hooks), so a runtime system-preference change is honored without a remount.
 * The former synchronous `prefersReducedMotion()` matchMedia helper was removed:
 * it was not reactive (issue: a runtime toggle would not re-evaluate). */

/* ---------- Utility: tweened metric ----------
 * 350ms cubic ease-out rAF tween between store values so numbers glide
 * instead of snapping. Plain React state, cancelled on unmount; collapses to
 * instant under prefers-reduced-motion. NO odometer theatrics.
 * Reduced motion is read via the REACTIVE `useReducedMotion` hook (motion/react)
 * so a runtime system-preference change is honored without a remount. */
function useTweenedMetric(target: number) {
  const [display, setDisplay] = useState(target);
  const displayRef = useRef(target);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    if (displayRef.current === target) return;
    /* Reduced motion: jump to the target on the next frame (no tween). */
    const duration = reducedMotion ? 0 : 350;
    const from = displayRef.current;
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const t = duration === 0 ? 1 : Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - t) ** 3; /* cubic ease-out */
      const value = Math.round(from + (target - from) * eased);
      displayRef.current = value;
      setDisplay(value);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, reducedMotion]);

  return display;
}

/* ---------- Utility: magnetic pull (Execute ONLY) ----------
 * Reduced to a SUBTLE, cockpit-appropriate response (the COMMAND panel
 * renovation): a faint rAF lerp toward (cursor - center) * 0.14, clamped so the
 * key never displaces more than 5px (a precise instrument nudge, not a toy
 * magnet), engaged only inside a tight radius of buttonWidth * 0.55; lerp
 * factor 0.1; ~400ms power3-out snap-back on leave. Transforms are written
 * straight to the wrapper ref · zero React state per frame. Disabled under
 * prefers-reduced-motion. */
function useMagneticPull(ref: RefObject<HTMLSpanElement | null>) {
  /* Reactive reduced-motion (motion/react) so a runtime toggle re-runs this
   * effect and tears the listener down (vs a one-time synchronous check). */
  const reducedMotion = useReducedMotion();
  useEffect(() => {
    const el = ref.current;
    if (!el || reducedMotion) return;

    let raf = 0;
    let running = false;
    let engaged = false;
    let x = 0;
    let y = 0;
    let targetX = 0;
    let targetY = 0;
    let snapStart = 0;
    let snapFromX = 0;
    let snapFromY = 0;

    const apply = () => {
      el.style.transform = `translate3d(${x.toFixed(2)}px, ${y.toFixed(2)}px, 0)`;
    };

    const frame = (now: number) => {
      if (engaged) {
        x += (targetX - x) * 0.1;
        y += (targetY - y) * 0.1;
        if (Math.abs(targetX - x) < 0.05 && Math.abs(targetY - y) < 0.05) {
          x = targetX;
          y = targetY;
          apply();
          running = false;
          return;
        }
        apply();
        raf = requestAnimationFrame(frame);
        return;
      }
      const t = Math.min(1, (now - snapStart) / 400);
      const eased = 1 - (1 - t) ** 3; /* power3.out */
      x = snapFromX * (1 - eased);
      y = snapFromY * (1 - eased);
      apply();
      if (t < 1) {
        raf = requestAnimationFrame(frame);
      } else {
        running = false;
      }
    };

    const ensureLoop = () => {
      if (!running) {
        running = true;
        raf = requestAnimationFrame(frame);
      }
    };

    const onPointerMove = (event: PointerEvent) => {
      const rect = el.getBoundingClientRect();
      const dx = event.clientX - (rect.left + rect.width / 2);
      const dy = event.clientY - (rect.top + rect.height / 2);
      if (Math.hypot(dx, dy) < rect.width * 0.55) {
        /* Subtle pull, clamped to a 5px instrument nudge (cockpit-appropriate). */
        const clamp = (v: number) => Math.max(-5, Math.min(5, v));
        targetX = clamp(dx * 0.14);
        targetY = clamp(dy * 0.14);
        engaged = true;
        ensureLoop();
      } else if (engaged) {
        engaged = false;
        snapStart = performance.now();
        snapFromX = x;
        snapFromY = y;
        ensureLoop();
      }
    };

    window.addEventListener('pointermove', onPointerMove, { passive: true });
    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      cancelAnimationFrame(raf);
      el.style.transform = '';
    };
  }, [ref, reducedMotion]);
}

/* ---------- Intake row: value bound to metricsStore, accent dot-flash on acquisition ---------- */
interface SourcePulse {
  id: number;
  row: number;
}

function SourceRow({
  metricKey,
  name,
  detail,
  pulse,
  linkUp,
}: {
  metricKey: MetricKey;
  name: string;
  detail: string;
  pulse: SourcePulse | null;
  /** Honest dormancy: offline there is no real intake value, so the % and the
   *  beacon go to a dormant '--' / floor state rather than show the store's
   *  offline demo drift (which would be fabricated data). */
  linkUp: boolean;
}) {
  const raw = useMetric(metricKey);
  const value = useTweenedMetric(raw);
  /* Beacon line (replaces the canned sparkline hills, P9): a 1px hairline whose
   * opacity maps the REAL metric value, clamped to a faint floor so it never
   * goes fully dark and never invents a shape. With fewer than two real samples
   * it sits at the honest baseline floor (no fabricated trend before data
   * exists). The opacity tween rides --dur-tick / instant under reduced motion. */
  const samples = useMetricHistory(metricKey).length;
  /* HONEST DORMANCY (the rubric's real-data law): the metricsStore keeps a
   * gentle demo drift around its lore bases while the link is DOWN. Showing that
   * here would be fabricated intake right next to a heading that already admits
   * 'intake paused'. So offline (or before any real sample exists) we render a
   * dormant '--' and rest the beacon at its floor · the number only ever shows
   * a REAL value once the link is up and the store carries real samples. */
  const hasRealValue = linkUp && samples >= 1;
  const beaconOpacity =
    hasRealValue && samples >= 2 ? Math.max(0.2, Math.min(0.95, value / 100)) : 0.2;

  return (
    <div className={`source-block${hasRealValue ? '' : ' is-dormant'}`}>
      <div className="source-row">
        {/* state, not decoration: flashes accent for one beat only when a real
            knowledge packet lands on this channel (keyed by sourcePulse). */}
        <span key={pulse ? pulse.id : 'idle'} className={`source-orb${pulse ? ' source-orb--flash' : ''}`} />
        <span className="source-name">
          <strong>{name}</strong>
          <small>{detail}</small>
        </span>
        {/* Real % only when the link is up and a real sample exists; '--'
            otherwise (never the store's offline drift). */}
        <span className="source-value tabnum">{hasRealValue ? `${value}%` : '--'}</span>
      </div>
      {/* The beacon is a NON-BLURRED child; only its opacity (a real metric)
          tweens, never paint on the blurred glass parent. */}
      <div className="source-beacon-track" aria-hidden="true">
        <i className="source-beacon" style={{ opacity: beaconOpacity }} />
      </div>
    </div>
  );
}

/* ---------- Agent card ----------
 * Honest state only (no timer churn, no scramble): `processing` + a real
 * `running <tool>` line when a real dispatch owns this card; `active` during the
 * directive surge (first ~5s of a real turn); else `standby` with NO invented
 * detail line. The 2px left edge-bar lights on the active/processing card. */
function AgentCard({
  name,
  icon,
  state,
  detail = null,
}: {
  name: string;
  icon: AgentIconKind;
  state: AgentState;
  /** Real work detail (e.g. "running create_file"); null = honest standby. */
  detail?: string | null;
}) {
  const isLive = state !== 'standby';
  return (
    <div className={`agent-card${isLive ? ' agent-card--live' : ''}`}>
      {/* state, not decoration: the 2px left bar lights only when a real signal
          (a tool dispatch or the directive surge) owns this card. */}
      <i className="agent-edge" aria-hidden="true" />
      <span className="agent-avatar">
        <AgentIcon kind={icon} />
      </span>
      <span className="agent-info">
        <strong>
          <span className="agent-name">{name}</span>
          <em className={`agent-state agent-state--${state}`}>{state}</em>
        </strong>
        {detail ? <small>{detail}</small> : null}
      </span>
      {/* Decorative affordance only · it carries no behavior, so it is NOT a
          control: marking it aria-hidden (vs a focusable no-op button) avoids
          advertising a phantom action to assistive tech and keyboard users. */}
      <span className="ghost-plus ghost-plus--small" aria-hidden="true">
        +
      </span>
    </div>
  );
}

/* ---------- Center port label (flat, over the brain) ----------
 * A single channel readout floating in the portal layer above the brain. It
 * reads ONE real metricsStore value (the SAME number the right-console intake
 * row shows) and lights cyan for one beat when `firing` is true (a real bus
 * event touched this channel). Idle: neutral hairline glyph + the live number,
 * no motion. The flare rides a NON-BLURRED child overlay (paint-trap law). */
function PortLabel({
  metricKey,
  label,
  firing,
  fireSeq,
  linkUp,
}: {
  metricKey: MetricKey;
  label: string;
  /** True for one beat when a real event touched this channel. */
  firing: boolean;
  /** Monotonic id so the one-shot flare re-keys (re-fires) on every real event. */
  fireSeq: number;
  /** Honest dormancy: offline the port shows '--', never the store's demo drift. */
  linkUp: boolean;
}) {
  const samples = useMetricHistory(metricKey).length;
  const value = useTweenedMetric(useMetric(metricKey));
  /* HONEST DORMANCY (same law as the intake rows): only show a REAL value when
   * the link is up and a real sample exists; never the offline demo drift. */
  const hasRealValue = linkUp && samples >= 1;
  return (
    <div className={`port-label${firing ? ' is-firing' : ''}${hasRealValue ? '' : ' is-dormant'}`}>
      {/* state, not decoration: the dot lights only while a real event is
          pulsing this channel; the one-shot flare re-keys on fireSeq. */}
      <i className="port-dot" aria-hidden="true" />
      <span className="port-name">{label}</span>
      <span className="port-value tabnum">{hasRealValue ? `${value}%` : '--'}</span>
      {/* The flare is a NON-BLURRED sibling; only transform/opacity animate,
          never paint on a blurred ancestor. Re-keyed per real event. */}
      <i key={fireSeq} className={`port-flare${firing ? ' port-flare--fire' : ''}`} aria-hidden="true" />
    </div>
  );
}

export default function SuperbrainHUD({
  mode,
  lastDirective,
  onModeChange,
  onDirective,
  skyMode = 'voyage',
  onSkyModeChange,
  surface = 'web',
  onSurfaceChange,
}: SuperbrainHUDProps) {
  const [directive, setDirective] = useState('');
  // Seed from the adapter, not from blank: the adapter outlives this component,
  // so a HUD remount (e.g. GPU context-loss recovery) must not drop a hold the
  // operator hasn't ruled on yet.
  const [approvalHold, setApprovalHold] = useState(() => getPendingApproval() !== null);
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(() =>
    getPendingApproval(),
  );
  const refreshPendingApproval = useCallback(() => {
    setPendingApproval(getPendingApproval());
  }, []);
  /* The approval surface is the most consequential safety gate in the product.
   * When it APPEARS (absent -> present), move keyboard focus to its first action
   * (AUTHORIZE) so a keyboard / screen-reader operator is taken straight to the
   * decision rather than having to Tab through the whole HUD to find it. Done at
   * the mount site (ApprovalPanel itself is not in this change's edit scope). */
  const approvalMountRef = useRef<HTMLDivElement>(null);
  const hadApprovalRef = useRef(false);
  useEffect(() => {
    const present = pendingApproval !== null;
    if (present && !hadApprovalRef.current) {
      const focusTarget = approvalMountRef.current?.querySelector<HTMLButtonElement>(
        '.approval-authorize',
      );
      focusTarget?.focus();
    }
    hadApprovalRef.current = present;
  }, [pendingApproval]);
  const magnetRef = useRef<HTMLSpanElement>(null);
  useMagneticPull(magnetRef);
  const { baseTier, generating, setTier } = useQualityTier();

  /* Reactive reduced-motion (motion/react): a React hook that updates on a
   * runtime system-preference change, replacing the synchronous one-shot
   * matchMedia reads in render/effects. The phase/elapsed effects list it in
   * their deps so a runtime toggle re-runs them (no stale interval). */
  const reducedMotion = useReducedMotion();

  /* ----- real system truth (adapter telemetry; seeded for remount safety) ----- */
  const [linkUp, setLinkUp] = useState(() => getLinkState());
  const [telemetry, setTelemetry] = useState<AiosTelemetry | null>(() => getLastTelemetry());
  const heartbeatCountRef = useRef(0);
  /* Real work this turn: distinct tools dispatched (and ever, this session). */
  const turnToolsRef = useRef<Set<string>>(new Set());
  const sessionToolsRef = useRef<Set<string>>(new Set());
  const [engagedLive, setEngagedLive] = useState(0);
  const [knownTools, setKnownTools] = useState(0);
  /* The last two REAL dispatches become the objective sub-steps. */
  const [recentSteps, setRecentSteps] = useState<string[]>([]);
  /* A real tool pulse routes to the card that owns that kind of work. */
  const [toolPulse, setToolPulse] = useState<{ row: number; detail: string } | null>(null);
  const toolPulseTimerRef = useRef<number | null>(null);
  /* Bumped on every REAL tool dispatch so the one-shot heartbeat pulse re-fires
   * via its React key (the pulse asserts a real dispatch, never idle theatre). */
  const [dispatchSeq, setDispatchSeq] = useState(0);

  /* ----- COMMAND BAR turn-state (the pilot vessel) -----
   * HONEST state only, never a fabricated completion %. The Execute label and
   * the indeterminate working arc are driven by the REAL `generating` flag and
   * the REAL `synthesis` event:
   *   generating === true              -> 'streaming' (the model is producing)
   *   synthesis event (cycle complete) -> 'done' for ~1.6s, then -> 'idle'
   *   otherwise                        -> 'idle' (Execute, ready)
   * No timer-theatre: the working arc is INDETERMINATE (it asserts "working",
   * not a false fraction); it spins only while a real turn is in flight. */
  const [turnState, setTurnState] = useState<'idle' | 'streaming' | 'done' | 'error'>('idle');
  const doneTimerRef = useRef<number | null>(null);
  /* A REAL, detectable submit failure: the operator dispatched while the link
   * to the AI-OS was down (getLinkState() false). Honest · it is a true offline
   * condition, never a fabricated error. Clears on the next focus/submit. */
  const [submitError, setSubmitError] = useState<string | null>(null);
  const errorTimerRef = useRef<number | null>(null);
  /* The directive echo (last directive's gist) clears the instant the operator
   * focuses the field to type the next one (a live, honest input affordance). */
  const [inputFocused, setInputFocused] = useState(false);
  /* Monotonic id re-keying the one-shot submit sweep so it re-fires on every
   * real submit and never loops. 0 = never submitted (no sweep at idle). */
  const [submitSeq, setSubmitSeq] = useState(0);

  /* ----- LIVE PHASE (the soul's spine) -----
   * No phase event exists on the bus, so the phase is DERIVED deterministically
   * from the events that DO exist (directive / burst / agent-dispatch / the real
   * `generating` flag / synthesis). Timestamps decay so a stale event never pins
   * a false phase. REST is the honest standby when nothing is in flight. */
  const phaseTsRef = useRef({ tool: 0, burst: 0, directive: 0 });
  const [livePhase, setLivePhase] = useState<Phase>('rest');
  /* Operator's manual lens pin (a click on the rail). null = follow livePhase. */
  const [pinnedLens, setPinnedLens] = useState<CognitiveMode | null>(null);
  /* Elapsed time of the live turn, shown only while the model is producing. */
  const [elapsedLabel, setElapsedLabel] = useState('');
  /* `generating` mirrored into a ref so the once-mounted bus subscriber derives
   * the phase against the CURRENT flag without re-subscribing each turn. The
   * mirror is written in an effect (never during render). */
  const generatingRef = useRef(generating);
  useEffect(() => {
    generatingRef.current = generating;
  }, [generating]);

  /* Derivation bound to the live refs (so it stays stable for the once-mounted
   * subscriber/interval). Delegates to the pure, unit-tested `derivePhaseFrom`
   * (src/test/livePhase.test.ts · precedence + decay windows covered). */
  const derivePhase = useCallback(
    (now: number): Phase => derivePhaseFrom(now, phaseTsRef.current, generatingRef.current),
    [],
  );

  /* Recompute on `generating` change (a real model-producing transition) and
   * tick a low-frequency decay so a phase relaxes back to REST honestly even
   * when no further event fires. The setState lives inside async callbacks
   * (rAF / interval), never synchronously in the effect body. */
  useEffect(() => {
    const recompute = () => setLivePhase(derivePhase(performance.now()));
    const raf = requestAnimationFrame(recompute);
    if (reducedMotion) {
      return () => cancelAnimationFrame(raf); /* still recomputes on each event */
    }
    const id = window.setInterval(recompute, 500);
    return () => {
      cancelAnimationFrame(raf);
      window.clearInterval(id);
    };
  }, [generating, derivePhase, reducedMotion]);

  /* Elapsed counter: runs ONLY while the model is producing (real signal), 1s
   * step, gated on reduced motion (no interval; the last static value holds).
   * When not producing the JSX hides it, so no reset setState is needed here. */
  useEffect(() => {
    if (!generating) return;
    const started = performance.now();
    const fmt = (ms: number) => {
      const s = Math.floor(ms / 1000);
      return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
    };
    const raf = requestAnimationFrame(() => setElapsedLabel(fmt(0)));
    if (reducedMotion) {
      return () => cancelAnimationFrame(raf);
    }
    const id = window.setInterval(() => setElapsedLabel(fmt(performance.now() - started)), 1000);
    return () => {
      cancelAnimationFrame(raf);
      window.clearInterval(id);
    };
  }, [generating, reducedMotion]);

  /* COMMAND BAR turn-state from the REAL `generating` flag: the Execute button
   * reads 'Streaming...' and the indeterminate working arc spins while the model
   * is producing. A 'done' state is set by the synthesis event (the bus
   * subscriber); when generating clears WITHOUT a synthesis we relax straight to
   * idle. No fabricated %; the arc only asserts that real work is in flight. The
   * setState is deferred through rAF (never synchronously in the effect body, the
   * same discipline as the livePhase recompute above). */
  useEffect(() => {
    const apply = () => {
      if (generating) {
        if (doneTimerRef.current !== null) {
          window.clearTimeout(doneTimerRef.current);
          doneTimerRef.current = null;
        }
        setTurnState('streaming');
        return;
      }
      /* Generating flipped false. If a synthesis already moved us to 'done',
       * leave that brief acknowledgement to its own timer; else relax to idle. */
      setTurnState((prev) => (prev === 'done' ? prev : 'idle'));
    };
    const raf = requestAnimationFrame(apply);
    return () => cancelAnimationFrame(raf);
  }, [generating]);

  /* LATENCY: the measured trails+metrics round-trip, '--' when offline. */
  const latency = linkUp && telemetry ? telemetry.latencyMs : null;

  /* SOUND: sovereign like its siblings · silent until the operator's own
   * click (the click doubles as WebAudio's required gesture). A stored ON
   * re-arms on the first gesture of the next session. */
  const [soundOn, setSoundOn] = useState(() => isSoundOn());
  useEffect(() => {
    try {
      if (window.localStorage.getItem('gag-sound-v1') !== 'on' || isSoundOn()) return;
    } catch {
      return;
    }
    const arm = () => {
      startSound();
      setSoundOn(true);
    };
    window.addEventListener('pointerdown', arm, { once: true });
    window.addEventListener('keydown', arm, { once: true });
    return () => {
      window.removeEventListener('pointerdown', arm);
      window.removeEventListener('keydown', arm);
    };
  }, []);
  const toggleSound = useCallback(() => {
    const next = !isSoundOn();
    if (next) startSound();
    else stopSound();
    setSoundOn(next);
    try {
      window.localStorage.setItem('gag-sound-v1', next ? 'on' : 'off');
    } catch {
      // Private mode etc. · the session still gets the choice.
    }
  }, []);

  /* VERIFIED SHARE: a REAL metric (verified trails over total trails), never a
   * task-completion estimate. Null when there are no trails or the link is down:
   * honest dormancy, never a fabricated number. */
  const verifiedShare =
    linkUp && telemetry && telemetry.trails > 0
      ? Math.round((100 * telemetry.verified) / telemetry.trails)
      : null;

  /* ----- living terminal buffer ----- */
  const [termLines, setTermLines] = useState<TermLine[]>(SEED_TERM_LINES);
  const termIdRef = useRef(0);
  const termEpochRef = useRef<number | null>(null);
  /* The last verified-trail count we logged, so a telemetry poll can surface
   * the REAL delta (gain) it represents and never re-count or invent one. */
  const prevVerifiedRef = useRef<number | null>(null);

  /* Optional real columns on a line: a verifier verdict and/or a verified-trail
   * delta, both derived from real signals (see the bus subscriber). The verdict
   * paints PASS (accent) / FAIL (canon busy amber); the delta paints +N accent
   * only when a real hash-chain growth occurred (N > 0). */
  const appendTermLine = useCallback(
    (
      text: string,
      bright = false,
      extra?: { verdict?: TermVerdict; delta?: number | null },
    ) => {
      if (termEpochRef.current === null) termEpochRef.current = performance.now();
      /* Mono clock: mm:ss since the FIRST real line (the seed standby line carries
       * no clock, so the ledger's first true fact starts honestly near 00:00). */
      const totalSeconds = Math.floor((performance.now() - termEpochRef.current) / 1000);
      const mm = String(Math.floor(totalSeconds / 60) % 100).padStart(2, '0');
      const ss = String(totalSeconds % 60).padStart(2, '0');
      const id = termIdRef.current;
      termIdRef.current += 1;
      setTermLines((prev) =>
        [
          ...prev,
          {
            id,
            time: `${mm}:${ss}`,
            text,
            fresh: true,
            bright,
            verdict: extra?.verdict ?? null,
            delta: extra?.delta ?? null,
          },
        ].slice(-TERM_BUFFER_MAX),
      );
    },
    [],
  );

  /* ----- knowledge intake + agent mesh reactions ----- */
  const [sourcePulse, setSourcePulse] = useState<SourcePulse | null>(null);
  /* The center port that a real event just touched. Carries the metric channel
   * + a monotonic id so the one-shot port pulse re-fires via its React key on
   * EVERY real event (a stale event never re-lights a port). Null at idle. */
  const [portPulse, setPortPulse] = useState<{ key: MetricKey; id: number } | null>(null);
  const portPulseIdRef = useRef(0);
  const portPulseTimerRef = useRef<number | null>(null);
  const pulseIdRef = useRef(0);
  const rotateRef = useRef(0);
  const [directiveSurge, setDirectiveSurge] = useState(false);
  const surgeTimeoutRef = useRef<number | null>(null);
  /* ----- the active brain for the live turn (from the `route` event) ----- */
  const [activeBrain, setActiveBrain] = useState<{
    provider: string;
    model: string;
    privacy: string;
    task?: string;
    auto?: boolean;
  } | null>(null);

  /* ----- nervous system: the HUD reacts to the same events as the 3D scene ----- */
  useEffect(() => {
    /* Recompute the derived phase the instant a real event stamps a timestamp,
     * so the headline/rail/cadence move ONLY on real bus activity. */
    const refreshPhase = () => setLivePhase(derivePhase(performance.now()));
    /* Light a center port for one beat on a real event touching its channel.
     * One-shot: a monotonic id re-keys the pulse so a fresh event always re-fires,
     * and a timer clears it back to the honest idle (unlit) state. */
    const firePort = (key: MetricKey) => {
      portPulseIdRef.current += 1;
      setPortPulse({ key, id: portPulseIdRef.current });
      if (portPulseTimerRef.current !== null) window.clearTimeout(portPulseTimerRef.current);
      portPulseTimerRef.current = window.setTimeout(() => {
        setPortPulse(null);
        portPulseTimerRef.current = null;
      }, 1200);
    };
    const unsubscribe = subscribeCognition((event) => {
      switch (event.type) {
        case 'knowledge-acquired': {
          const label = event.label ?? 'signal shard';
          // A REAL verifier verdict: the adapter emits these exact labels when a
          // tool result is a [VERIFY PASS]/[VERIFY FAIL]. The terminal carries
          // the outcome in its own column (PASS accent / FAIL canon amber); no
          // verdict is fabricated for any other acquisition line.
          const verdict: TermVerdict =
            label === 'VERIFICATION GREEN'
              ? 'pass'
              : label === 'VERIFICATION RED'
                ? 'fail'
                : null;
          // Mastery is the loudest line the terminal has.
          appendTermLine(
            `Acquired · ${label} (+${event.detail ?? 'trace'})`,
            label.startsWith('SKILL MASTERED'),
            { verdict },
          );
          pulseIdRef.current += 1;
          const sourceRow = matchSourceRow(label, rotateRef);
          setSourcePulse({ id: pulseIdRef.current, row: sourceRow });
          // The same real packet pulses the matching center port (one source of
          // truth: SOURCE_CHANNELS[row].key is the metric channel it landed on).
          firePort(SOURCE_CHANNELS[sourceRow].key);
          break;
        }
        case 'burst':
          // A labeled burst is a RECALL · the brain touching a real trail.
          appendTermLine(
            event.label
              ? `Recall · ${event.label}${event.detail ? ` (${event.detail})` : ''}`
              : 'Cortical burst · resonance nominal',
          );
          // A real recall maps the knowledge horizon -> OBSERVE (decays in ~4s).
          phaseTsRef.current.burst = performance.now();
          refreshPhase();
          break;
        case 'directive': {
          appendTermLine(`Directive received · ${event.label ?? 'unspecified'}`, true);
          setApprovalHold(false);
          // A new turn begins: the live work counters start from zero.
          turnToolsRef.current = new Set();
          setEngagedLive(0);
          setRecentSteps([]);
          setActiveBrain(null); // the new turn re-announces its brain via `route`
          // The mesh snaps to attention -> a brief ORCHESTRATE (decays in ~2s).
          phaseTsRef.current.directive = performance.now();
          refreshPhase();
          setDirectiveSurge(true);
          if (surgeTimeoutRef.current !== null) window.clearTimeout(surgeTimeoutRef.current);
          surgeTimeoutRef.current = window.setTimeout(() => {
            setDirectiveSurge(false);
            surgeTimeoutRef.current = null;
          }, 5000);
          break;
        }
        case 'agent-dispatch': {
          appendTermLine(`Mesh · ${event.label ?? 'agent dispatched'}`);
          // Real tool dispatches (adapter marks them 'tool engaged: <name>')
          // drive the mesh truthfully: engaged counts, objective sub-steps,
          // and a processing pulse on the card that owns that work.
          const detail = event.detail ?? '';
          if (detail.startsWith('tool engaged: ')) {
            const tool = detail.slice('tool engaged: '.length).trim();
            turnToolsRef.current.add(tool);
            sessionToolsRef.current.add(tool);
            setEngagedLive(turnToolsRef.current.size);
            setKnownTools(sessionToolsRef.current.size);
            setRecentSteps((prev) => [...prev.slice(-1), tool.replace(/_/g, ' ')]);
            setToolPulse({ row: agentRowForTool(tool), detail: `running ${tool}` });
            // The real tool firing pulses the center port that owns that work.
            firePort(toolChannelForPort(tool));
            // A real dispatch -> ORCHESTRATE (decays in ~4s) and re-fires the
            // one-shot heartbeat pulse via its React key.
            phaseTsRef.current.tool = performance.now();
            refreshPhase();
            setDispatchSeq((seq) => seq + 1);
            if (toolPulseTimerRef.current !== null) window.clearTimeout(toolPulseTimerRef.current);
            toolPulseTimerRef.current = window.setTimeout(() => {
              setToolPulse(null);
              toolPulseTimerRef.current = null;
            }, 4000);
          }
          break;
        }
        case 'telemetry': {
          const data = (event.data ?? {}) as Record<string, unknown>;
          if (data.link === false) {
            setLinkUp(false);
          } else {
            setLinkUp(true);
            const t = data as unknown as AiosTelemetry;
            setTelemetry(t);
            // The REAL verified-trail delta this poll surfaced: a non-negative
            // gain over the last count we logged (the first live poll just
            // seeds the baseline, never claiming a delta). A growth is a real
            // hash-chain entry, so it earns the accent +N column.
            const prev = prevVerifiedRef.current;
            const delta = prev !== null && t.verified > prev ? t.verified - prev : null;
            prevVerifiedRef.current = t.verified;
            // A quiet real heartbeat every few polls · telemetry owns the
            // idle channel while the link is alive. A real verified gain is
            // surfaced the instant it happens, regardless of the cadence.
            heartbeatCountRef.current += 1;
            if (delta !== null || heartbeatCountRef.current % 3 === 1) {
              // One middle-dot per line (the metadata-strip ration): the three
              // figures read as compact mono columns (Nt / Nv / Nms), so the
              // line keeps a single separator instead of three.
              appendTermLine(
                `Telemetry · ${t.trails}t ${t.verified}v ${t.latencyMs}ms`,
                false,
                { delta },
              );
            }
          }
          break;
        }
        case 'synthesis':
          appendTermLine(`Synthesis · ${event.detail ?? event.label ?? 'cycle complete'}`);
          setApprovalHold(false);
          // The cycle completed. Phase relaxes back to REST once the tool/burst
          // windows lapse and generating clears (the decay tick handles it).
          refreshPhase();
          // The command bar acknowledges the REAL completion: Execute reads
          // 'Done' for a beat, then relaxes to idle. A real event, not a timer
          // theatre · it fires only when a synthesis cycle truly completes.
          setTurnState('done');
          if (doneTimerRef.current !== null) window.clearTimeout(doneTimerRef.current);
          doneTimerRef.current = window.setTimeout(() => {
            setTurnState('idle');
            doneTimerRef.current = null;
          }, 1600);
          break;
        case 'approval-required':
          // The supervised mind defers to its operator · loudest line we have.
          appendTermLine(`HOLD · ${event.detail ?? 'operator approval required'}`, true);
          setApprovalHold(true);
          setPendingApproval(getPendingApproval());
          break;
        case 'approval-resolved':
          appendTermLine(`Resume · ${event.label ?? 'operator decision received'}`, true);
          setApprovalHold(false);
          setPendingApproval(getPendingApproval());
          break;
        case 'route': {
          // The active brain for this turn · which provider/model served it and
          // whether it stayed local (a policy-permitted cloud escalation reads CLOUD).
          const d = (event.data ?? {}) as Record<string, unknown>;
          if (typeof d.model === 'string' && d.model) {
            setActiveBrain({
              provider: String(d.provider ?? ''),
              model: d.model,
              privacy: String(d.privacy ?? ''),
              task: typeof d.task === 'string' ? d.task : undefined,
              auto: typeof d.auto === 'boolean' ? d.auto : undefined,
            });
            appendTermLine(`Brain · ${d.model} (${String(d.privacy ?? '?')})`);
          }
          break;
        }
      }
    });
    return () => {
      unsubscribe();
      if (surgeTimeoutRef.current !== null) {
        window.clearTimeout(surgeTimeoutRef.current);
        surgeTimeoutRef.current = null;
      }
      if (toolPulseTimerRef.current !== null) {
        window.clearTimeout(toolPulseTimerRef.current);
        toolPulseTimerRef.current = null;
      }
      if (portPulseTimerRef.current !== null) {
        window.clearTimeout(portPulseTimerRef.current);
        portPulseTimerRef.current = null;
      }
      if (doneTimerRef.current !== null) {
        window.clearTimeout(doneTimerRef.current);
        doneTimerRef.current = null;
      }
    };
  }, [appendTermLine, derivePhase]);

  /* No offline ticker: while the link is down the terminal sits SILENT rather
   * than inventing precision lines (P10 purge). A silent terminal is the honest
   * idle state; real telemetry heartbeats own the channel while the link lives. */

  /* Clear the offline-submit error timer on unmount (it is started outside the
   * bus-subscriber effect, in handleSubmit). */
  useEffect(
    () => () => {
      if (errorTimerRef.current !== null) window.clearTimeout(errorTimerRef.current);
    },
    [],
  );

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    /* A turn is already in flight. The Execute button uses aria-disabled (not the
     * native `disabled` attribute) so it stays in the focus order and keeps its
     * accessible name for AT; this guard is what actually prevents a second
     * dispatch (native `disabled` would remove it from the a11y tree, so we do
     * not use it · see the button below). */
    if (turnState === 'streaming') return;
    const nextDirective = directive.trim();
    if (!nextDirective) return;
    /* HONEST failure path: if the link to the AI-OS is genuinely down at submit
     * time the directive cannot be served. This is a real, detectable condition
     * (getLinkState()), not a fabricated error · surface it on the bar with an
     * assertive announcement and DO NOT pretend a turn began. */
    if (!getLinkState()) {
      setSubmitError('Link offline. The directive was not dispatched.');
      setTurnState('error');
      if (errorTimerRef.current !== null) window.clearTimeout(errorTimerRef.current);
      errorTimerRef.current = window.setTimeout(() => {
        setSubmitError(null);
        setTurnState((prev) => (prev === 'error' ? 'idle' : prev));
        errorTimerRef.current = null;
      }, 4000);
      return;
    }
    /* Broadcast on the cognition bus FIRST so the whole organism (terminal,
     * agents, 3D scene) reacts to the directive, then hand off upstream. */
    publishCognition({ type: 'directive', label: nextDirective, intensity: 1, source: 'hud' });
    onDirective(nextDirective);
    setDirective('');
    setSubmitError(null);
    /* One-shot submit sweep: re-key the cyan line so it re-fires on every real
     * submit (it never loops). Blur is released so the directive echo can read. */
    setSubmitSeq((seq) => seq + 1);
    setInputFocused(false);
  };

  /* The operator's `mode` prop stays part of the public contract: the PARENT
   * owns it and feeds it to the real 3D brain (MODE_EMISSIVE / AURA_MODE_COLORS),
   * while this HUD now derives its own honest livePhase and exposes the manual
   * lens via `onModeChange`/`pinnedLens`. Its former topbar reader (the fake
   * "/ NN" build-tag) is purged, so acknowledge the prop without re-deriving any
   * rail state from it (that would alter the preserved ACTIVE COGNITION panel). */
  void mode;

  /* The rail's active lens: the operator's pin if he steered, else it FOLLOWS
   * the derived livePhase. REST highlights no rail item (honest: no work lens is
   * lit at standby). The pin is the operator's manual override (§2). */
  const pinned = pinnedLens !== null;
  const activeRailId: CognitiveMode | null = pinned
    ? pinnedLens
    : livePhase === 'rest'
      ? null
      : livePhase;
  const handleLensPin = useCallback(
    (id: CognitiveMode) => {
      // A click pins the operator's lens (toggle off if he re-clicks the pin).
      setPinnedLens((prev) => (prev === id ? null : id));
      onModeChange(id);
    },
    [onModeChange],
  );

  /* DIRECTIVE ECHO: an honest gist of the LAST real directive (the one the brain
   * is acting on), shown under the field when the operator is not editing. It is
   * the real `lastDirective` prop (the parent's record of what was dispatched),
   * trimmed to a 40-char gist plus its real word count. Cleared while typing the
   * next one (inputFocused) so it never competes with the live input. */
  const directiveEchoGist = lastDirective.trim();
  const directiveEchoWords = directiveEchoGist ? directiveEchoGist.split(/\s+/).length : 0;
  const directiveEchoShort =
    directiveEchoGist.length > 40 ? `${directiveEchoGist.slice(0, 40).trimEnd()}…` : directiveEchoGist;
  const showDirectiveEcho = !inputFocused && !directive && directiveEchoGist.length > 0;

  /* COMMAND BAR Execute copy from the HONEST turn-state (no fabricated %). */
  const executeLabel =
    turnState === 'streaming'
      ? 'Streaming…'
      : turnState === 'done'
        ? 'Done'
        : turnState === 'error'
          ? 'Offline'
          : 'Execute';

  return (
    <>
      <Html>
        {createPortal(
          <div className="hud-shell">
          {/* Skip link for accessibility. Canon accent-surface treatment (bg
              = the one accent, dark ink) · the off-canon purple it used to carry
              was a fourth hue with no state meaning (one-accent law). */}
          <a
            href="#directive"
            className="skip-link"
            style={{
              position: 'absolute',
              left: '16px',
              zIndex: 9999,
              background: 'var(--accent)',
              color: '#04181a',
              padding: '8px 12px',
              borderRadius: '8px',
              fontWeight: 600,
              fontSize: '12px',
              boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.35)',
              textDecoration: 'none',
              transform: 'translateY(-150%)',
              transition: 'transform 200ms var(--ease-out-quart)',
            }}
            onFocus={(e) => (e.currentTarget.style.transform = 'translateY(16px)')}
            onBlur={(e) => (e.currentTarget.style.transform = 'translateY(-150%)')}
          >
            Skip to HUD controls
          </a>

          <div className="bottom-scrim" aria-hidden="true" />

          {/* CENTER PORTS · the four cognition channels over the brain. FLAT 2D
              in the portal layer (NOT scene-pinned Html · frozen-scene contract).
              pointer-events:none so the brain keeps its orbit/drag. Each label
              reads a real metricsStore value and pulses cyan only when a real
              bus event (tool firing / knowledge packet) touched its channel. */}
          <div className="center-ports" aria-hidden="true">
            {PORT_CHANNELS.map((port) => (
              <PortLabel
                key={port.key}
                metricKey={port.key}
                label={port.label}
                firing={portPulse?.key === port.key}
                fireSeq={portPulse?.key === port.key ? portPulse.id : 0}
                linkUp={linkUp}
              />
            ))}
          </div>

          <header className="topbar">
            <div className="brand-lockup">
              <span className="brand-mark">
                <HexMark />
              </span>
              <span className="brand-wordmark">
                GAG<span>OS</span>
              </span>
              <span className="build-tag">AUTONOMOUS CORE</span>
            </div>

            <div className="system-summary">
              {/* The dot tells the truth: green only while the adapter's
                  last poll genuinely reached the AI-OS. */}
              <span role="status">
                <i className={`status-dot ${linkUp ? 'status-dot--live' : 'status-dot--down'}`} />{' '}
                {linkUp ? 'CORE ONLINE' : 'LINK OFFLINE'}
              </span>
              <span className="topbar-divider" />
              {/* Measured trails+metrics round-trip, never invented. The value
                  micro-breathes (opacity only) on a REAL change via its React
                  key: a moving number reads as a working, polling link. */}
              <span>
                LATENCY{' '}
                <strong key={`lat-${latency ?? 'na'}`} className="val-tick tabnum">
                  {latency !== null ? `${latency}ms` : '--'}
                </strong>
              </span>
              {/* AUTONOMY: appears only once the brain has EARNED the right to act
                  on a class without a human (by repeated verified success).
                  Additive · invisible until that growth is real, so the canon idle
                  frame is untouched. */}
              {telemetry && telemetry.earnedAutonomy.earned > 0 ? (
                <>
                  <span className="topbar-divider" />
                  <span
                    role="status"
                    title="Action classes the brain earned the right to do autonomously, by repeated verified success"
                  >
                    {/* state, not decoration: the real earned count drives this.
                        No emoji; the label carries the meaning (P4 purge). */}
                    AUTONOMY <strong className="tabnum">{telemetry.earnedAutonomy.earned}</strong>
                  </span>
                </>
              ) : null}
              {/* BRAIN: which provider/model serves the live turn + a privacy dot
                  (green = stayed local, amber = a policy-permitted cloud escalation).
                  Additive · invisible until a turn announces its brain, so the canon
                  idle frame is untouched. */}
              {activeBrain ? (
                <>
                  <span className="topbar-divider" />
                  <span
                    role="status"
                    title={`Active brain: ${activeBrain.provider} · ${activeBrain.model} (${activeBrain.privacy}${activeBrain.auto ? ', auto-routed' : ''})`}
                  >
                    BRAIN{' '}
                    {/* state, not decoration: privacy dot encodes the real
                        route privacy (local green / cloud amber). */}
                    <i
                      className={`status-dot brain-dot ${
                        activeBrain.privacy === 'local' ? 'brain-dot--local' : 'brain-dot--cloud'
                      }`}
                    />{' '}
                    {/* The privacy dot is color-only; a visually-hidden word makes
                        the route privacy non-color-dependent for AT / low-vision
                        (color-not-only), matching the terminal-brain readout. */}
                    <span className="sr-only">
                      {activeBrain.privacy === 'local' ? 'local route' : 'cloud route'}
                    </span>
                    {/* Micro-breathes on a REAL route change (keyed) so a new
                        active brain reads as a live hand-off, not a static tag. */}
                    <strong key={`brain-${activeBrain.model}`} className="val-tick">
                      {activeBrain.model}
                    </strong>
                    {/* hairline divider (NOT a middle-dot): matches the topbar's
                        separator rhythm · the · is rationed elsewhere. */}
                    <span className="topbar-divider" />
                    {activeBrain.privacy === 'local' ? 'LOCAL' : 'CLOUD'}
                  </span>
                </>
              ) : null}
              <span className="topbar-divider" />
              {/* FIDELITY IS SACRED: only this click ever changes the tier
                  (cycles high -> medium -> low -> high). The governor may
                  whisper advice in the terminal; it cannot act. */}
              <button
                className="fidelity-button"
                type="button"
                aria-label={`Visual fidelity: ${baseTier}. Click to cycle high, medium, low.`}
                title="Visual fidelity · yours alone; click to cycle high/medium/low"
                onClick={() =>
                  setTier(baseTier === 'high' ? 'medium' : baseTier === 'medium' ? 'low' : 'high')
                }
              >
                FIDELITY <strong>{baseTier.toUpperCase()}</strong>
                {/* The 'thinking' suffix uses the SAME hairline separator the rest
                    of the topbar uses (span.topbar-divider), not a middle-dot, so
                    the bar keeps one separator language throughout. */}
                {generating ? (
                  <>
                    <span className="topbar-divider" />
                    <em className="fidelity-thinking">thinking</em>
                  </>
                ) : null}
              </button>
              {onSkyModeChange ? (
                <>
                  <span className="topbar-divider" />
                  {/* The sky is the operator's canon: voyage (his moving field,
                      default) or layered (his photographic dome deep behind it).
                      Only this click chooses; the choice persists. */}
                  <button
                    className="fidelity-button"
                    type="button"
                    aria-label={`Sky: ${skyMode}. Click to switch between voyage and layered.`}
                    title="Sky · voyage (moving field) or layered (field + nebula dome behind)"
                    onClick={() => onSkyModeChange(skyMode === 'voyage' ? 'layered' : 'voyage')}
                  >
                    SKY <strong>{skyMode.toUpperCase()}</strong>
                  </button>
                </>
              ) : null}
              {onSurfaceChange ? (
                <>
                  <span className="topbar-divider" />
                  {/* The cortex itself: canon web shell, or the flesh he
                      painted into the GLB. His click, his brain. */}
                  <button
                    className="fidelity-button"
                    type="button"
                    aria-label={`Cortex surface: ${surface}. Click to switch between web and organ.`}
                    title="Cortex surface · web (canon energy shell) or organ (your painted flesh under the web)"
                    onClick={() => onSurfaceChange(surface === 'web' ? 'organ' : 'web')}
                  >
                    SURFACE <strong>{surface.toUpperCase()}</strong>
                  </button>
                </>
              ) : null}
              <span className="topbar-divider" />
              {/* The organism's voice: synthesized, whisper-quiet, and bound
                  to the same real bus events the visuals react to. */}
              <button
                className="fidelity-button"
                type="button"
                aria-label={`Sound ${soundOn ? 'on' : 'off'}. Breath hum, recall ticks, approval chords.`}
                title="Sound · breath hum, recall ticks, approval chords; synthesized, your click only"
                onClick={toggleSound}
                aria-pressed={soundOn}
              >
                SOUND <strong>{soundOn ? 'ON' : 'OFF'}</strong>
              </button>
            </div>

            {/* The shield asserts only what is computed: amber while a real
                approval holds; red if the audit hash-chain ever breaks;
                otherwise the supervised posture with real ledger size. */}
            <button
              className={`secure-button${approvalHold ? ' secure-button--hold' : ''}${
                telemetry?.chainValid === false ? ' secure-button--tamper' : ''
              }`}
              type="button"
              /* aria-live is NOT on this <button>: NVDA/JAWS ignore aria-live on
                 focusable elements (behaviour is undefined on VoiceOver), so the
                 autonomous label flip is announced by a dedicated sr-only live
                 region below, not the control itself. */
              /* State-varying accessible NAME (not just the title tooltip, which AT
                 announces unreliably): the shield's visible text ('Supervised' /
                 'HOLD' / 'TAMPER') is a state word, not its purpose, so the
                 aria-label spells out what the control reports. */
              aria-label={
                telemetry?.chainValid === false
                  ? 'Security: audit chain broken. Inspect the ledger.'
                  : approvalHold
                    ? 'Security: operator approval is on hold.'
                    : telemetry?.chainValid === true
                      ? `Security: supervised core, audit hash-chain intact, ${telemetry.chainEntries} entries.`
                      : 'Security: supervised core, audit chain not yet verified.'
              }
              title={
                telemetry?.chainValid === true
                  ? `Audit hash-chain intact · ${telemetry.chainEntries} entries`
                  : telemetry?.chainValid === false
                    ? 'AUDIT CHAIN BROKEN · inspect the ledger'
                    : 'Supervised core · audit chain not yet verified'
              }
            >
              <ShieldIcon />{' '}
              {telemetry?.chainValid === false
                ? 'TAMPER'
                : approvalHold
                  ? 'HOLD'
                  : 'Supervised'}
            </button>
            {/* Dedicated live region for the shield's autonomous state changes:
                a non-interactive sr-only span that mirrors the current security
                posture, so a flip to HOLD/TAMPER is announced reliably (aria-live
                on the focusable button itself is not honoured by NVDA/JAWS). */}
            <span className="sr-only" role="status" aria-live="polite">
              {telemetry?.chainValid === false
                ? 'Security: audit chain broken'
                : approvalHold
                  ? 'Security: operator approval on hold'
                  : 'Security: supervised, audit chain intact'}
            </span>
          </header>

          <section className="core-readout" aria-label="Core status">
            {/* SUPERMIND is the literal product name (claims nothing falsifiable),
                so it stays. The fake "/ NN" build-tag is purged (P2): the only
                live sub-readout is the REAL derived phase + honest link state. */}
            <h2>SUPERMIND</h2>
            {/* aria-live sits on THIS line only (not the section): the static h2
                must not re-announce on every 500ms phase tick · only the changed
                phase + link words speak. */}
            <p className="core-sub" aria-live="polite">
              {/* state, not decoration: the derived livePhase word + the real
                  link truth. STANDBY / OBSERVE / SYNTHESIZE / ORCHESTRATE. */}
              <span key={`phaselabel-${livePhase}`} className="core-phase">
                {PHASE_LABEL[livePhase]}
              </span>
              <span className="topbar-divider" />
              {/* Offline reads a plain, functional status (no poetic "IMAGINATION"
                  tell): an offline core is simply on standby, matching the topbar's
                  own honest 'LINK OFFLINE' wording. */}
              {linkUp ? 'CORE ONLINE' : 'LINK OFFLINE · STANDBY'}
            </p>
          </section>

          {/* TERMINAL LOG · the causality ledger: the superbrain's real working
              stream. Each row is a 4-col grid [ts][fact][verdict][delta]; the
              verdict + delta columns appear ONLY on real signals (a verifier
              verdict, a verified-trail gain). No decorative filler. */}
          <div className="terminal-log" aria-live="polite" aria-atomic="false">
            <span className="terminal-heading">
              TERMINAL LOG
              {/* The real brain serving the live turn (model + privacy). Honest
                  dormancy: nothing until a turn announces its brain via `route`. */}
              {activeBrain ? (
                <em
                  className="terminal-brain"
                  title={`Active brain: ${activeBrain.provider} · ${activeBrain.model} (${activeBrain.privacy})`}
                >
                  {/* state, not decoration: privacy dot encodes the real route
                      privacy (local green / cloud amber). */}
                  <i
                    className={`status-dot brain-dot ${
                      activeBrain.privacy === 'local' ? 'brain-dot--local' : 'brain-dot--cloud'
                    }`}
                  />
                  {/* The privacy dot is color-only; a visually-hidden word makes
                      the route privacy non-color-dependent for AT / low-vision. */}
                  <span className="sr-only">
                    {activeBrain.privacy === 'local' ? 'local route' : 'cloud route'}
                  </span>
                  {activeBrain.model}
                </em>
              ) : null}
            </span>
            {termLines.map((termLine) => (
              <p
                key={termLine.id}
                className={`term-row${termLine.fresh ? ' term-fresh term-mount' : ''}${
                  termLine.bright ? ' is-bright' : ''
                }`}
              >
                <em className="term-ts">{termLine.time}</em>
                <span className="term-text">{termLine.text}</span>
                {/* Verdict column: REAL verifier outcome only (PASS accent /
                    FAIL canon amber); empty cell otherwise (no fabrication). */}
                {termLine.verdict ? (
                  <b className={`term-verdict term-verdict--${termLine.verdict}`}>
                    {termLine.verdict === 'pass' ? 'PASS' : 'FAIL'}
                  </b>
                ) : (
                  <b className="term-verdict" aria-hidden="true" />
                )}
                {/* Delta column: a REAL verified-trail gain (+N accent) only; the
                    cell stays empty when there was no real growth this line. */}
                {termLine.delta && termLine.delta > 0 ? (
                  <i className="term-delta term-delta--earned tabnum">+{termLine.delta}</i>
                ) : (
                  <i className="term-delta" aria-hidden="true" />
                )}
              </p>
            ))}
          </div>

          {pendingApproval ? (
            <div ref={approvalMountRef}>
              <ApprovalPanel pending={pendingApproval} onSettled={refreshPendingApproval} />
            </div>
          ) : null}

          {/* COMMAND BAR · DIRECT THE SUPERMIND · the pilot vessel. Every readout
              is HONEST: the Execute label + the indeterminate working arc reflect
              the REAL turn-state (generating / synthesis), never a fabricated %;
              the brain chip + engaged counter read real `route`/`agent-dispatch`
              signals; the directive echo is the real last directive; the submit
              sweep is a one-shot keyed to a real submit. */}
          <form
            className={`command-bar command-bar--state-${turnState}${
              approvalHold ? ' is-approval-hold' : ''
            }`}
            onSubmit={handleSubmit}
          >
            {/* The command prompt glyph · an affordance, not decoration (this is
                the directive input). */}
            <span className="command-chip" aria-hidden="true">
              &gt;_
            </span>
            <div className="command-field">
              <label htmlFor="directive">DIRECT THE SUPERMIND</label>
              <input
                id="directive"
                value={directive}
                onChange={(event) => setDirective(event.target.value)}
                onFocus={() => {
                  setInputFocused(true);
                  if (submitError) {
                    setSubmitError(null);
                    setTurnState((prev) => (prev === 'error' ? 'idle' : prev));
                  }
                }}
                onBlur={() => setInputFocused(false)}
                placeholder="Ask the Supermind..."
                autoComplete="off"
                aria-invalid={turnState === 'error'}
                aria-errormessage={turnState === 'error' ? 'command-error' : undefined}
              />
              {/* DIRECTIVE ECHO · the real last directive's gist + word count;
                  hidden while the operator is editing the next one. Honest
                  dormancy: nothing until a real directive has been dispatched. */}
              {showDirectiveEcho ? (
                <span className="command-echo" aria-live="polite">
                  <span className="command-echo-gist">{directiveEchoShort}</span>
                  <span className="command-echo-words tabnum">
                    {directiveEchoWords}w
                  </span>
                </span>
              ) : null}
              {/* SUBMIT SWEEP · a one-shot 1px cyan line, a NON-BLURRED child
                  (never paint on the blurred bar). Re-keyed per real submit so it
                  re-fires and never loops; absent until the first real submit. */}
              {submitSeq > 0 ? (
                <i key={submitSeq} className="command-sweep" aria-hidden="true" />
              ) : null}
              {/* ERROR · a REAL offline-submit failure (link genuinely down).
                  role=alert + assertive so AT announces it immediately; amber
                  (the canon busy/fail state hue, not a 2nd accent). Referenced
                  by the input's aria-errormessage. */}
              {submitError ? (
                <span
                  id="command-error"
                  className="command-error"
                  role="alert"
                  aria-live="assertive"
                >
                  {submitError}
                </span>
              ) : null}
            </div>

            {/* STATUS CLUSTER · real readouts (replaces the decorative magnifier).
                Honest dormancy: the brain chip appears only once a turn announces
                its brain via `route`; the counter only once a tool has engaged. */}
            <div className="command-status" aria-hidden={!activeBrain && engagedLive === 0}>
              {activeBrain ? (
                <span
                  className="command-brain"
                  title={`Active brain: ${activeBrain.provider} · ${activeBrain.model} (${activeBrain.privacy}${
                    activeBrain.auto ? ', auto-routed' : ''
                  })`}
                >
                  {/* state, not decoration: privacy dot encodes the real route
                      privacy (local green / cloud amber). */}
                  <i
                    className={`status-dot brain-dot ${
                      activeBrain.privacy === 'local' ? 'brain-dot--local' : 'brain-dot--cloud'
                    }`}
                  />
                  {/* The privacy dot is color-only; a visually-hidden word makes
                      the route privacy non-color-dependent for AT / low-vision
                      (color-not-only), matching the terminal-brain readout. */}
                  <span className="sr-only">
                    {activeBrain.privacy === 'local' ? 'local route' : 'cloud route'}
                  </span>
                  <strong key={`cmd-brain-${activeBrain.model}`} className="command-brain-model">
                    {activeBrain.model}
                  </strong>
                </span>
              ) : null}
              {knownTools > 0 ? (
                <span
                  className="command-engaged"
                  title="Distinct tools engaged this turn · this session"
                >
                  {/* The +1 pulse re-keys on a real tool dispatch (dispatchSeq),
                      so the accent count pulses ONLY when a real tool engages. */}
                  <strong key={`cmd-eng-${dispatchSeq}`} className="command-engaged-n tabnum">
                    {engagedLive}
                  </strong>
                  <small className="tabnum">/ {knownTools}</small>
                </span>
              ) : null}
            </div>

            <span className="execute-wrap" ref={magnetRef}>
              <motion.button
                className={`execute-button${turnState !== 'idle' ? ' is-working' : ''}`}
                whileTap={reducedMotion ? undefined : { scale: 0.97 }}
                transition={{ duration: 0.12 }}
                type="submit"
                /* aria-disabled ONLY (no native `disabled`): native disabled
                   removes the button from the accessibility tree, so AT would
                   never see aria-disabled and the control would drop out of the
                   focus order mid-turn. Keeping it focusable + announced, the
                   actual second-dispatch block lives in handleSubmit. */
                aria-disabled={turnState === 'streaming'}
                title={turnState === 'streaming' ? 'A turn is in flight' : undefined}
              >
                {/* Indeterminate working arc · a NON-BLURRED SVG child that spins
                    only while a real turn is in flight (it asserts "working", not
                    a false completion fraction). Reduced motion freezes it. */}
                <span className="execute-arc" aria-hidden="true">
                  <svg viewBox="0 0 16 16">
                    <circle className="execute-arc-track" cx="8" cy="8" r="6.2" />
                    <circle className="execute-arc-spin" cx="8" cy="8" r="6.2" />
                  </svg>
                </span>
                <span className="execute-label">{executeLabel}</span>
                {/* state, not decoration: a keyboard affordance hint (Enter
                    submits), hidden while a turn is working. */}
                <span className="execute-return" aria-hidden="true">
                  ⏎
                </span>
              </motion.button>
            </span>
            {/* Screen-reader turn-state announcement. aria-live on the <button>
                itself is unreliable for interactive elements, so the live region
                is a dedicated visually-hidden span that mirrors the turn-state
                (Ready / Streaming / Done) and is announced politely on change. */}
            <span className="sr-only" aria-live="polite" aria-atomic="true">
              {turnState === 'streaming'
                ? 'Directive streaming'
                : turnState === 'done'
                  ? 'Directive complete'
                  : 'Ready for a directive'}
            </span>
            <i className="glass-grain" aria-hidden />
          </form>
        </div>,
        document.getElementById('hud-portal-root') || document.body
      )}
      </Html>

      {/* 
        By omitting `transform`, the Html wrapper is simply a 2D DOM element pinned to the 3D projection of [-5.8, -1.7, 0].
        This completely skips React Three Fiber's complex matrix scaling, guaranteeing 100% pixel-perfect CSS sizing.
        We then manually apply `translate(-50%, -100%)` to align the bottom-center of the panel exactly to the wire point,
        and add `perspective` and `rotateY` to achieve the true 3D look while pivoting around the wire connection!
      */}
      <Html position={[-4.8, -1.7, 0.0]} zIndexRange={[100, 0]}>
        <div style={{ transform: 'translate(-50%, -100%)' }}>
          <aside className="left-console glass-surface" aria-label="Active cognition">
            {/* The uppercase mono eyebrow stands on its own · the former leading
                dot was a neutral decoration with no semantic state (the §3.1 rule:
                a kept dot must encode a real value), so it is removed. */}
            <div className="eyebrow">ACTIVE COGNITION</div>

            {/* HONEST live phase, derived from the bus, not an operator toggle.
                Cross-fades only on a REAL phase transition (keyed). */}
            <h1 key={`phase-${livePhase}`}>{PHASE_COPY[livePhase].title}</h1>
            <p className="cognition-detail">{PHASE_COPY[livePhase].detail}</p>

            {/* Mode rail = the operator's manual lens override; DEFAULTS to follow
                the derived livePhase, and a `pinned` marker shows when he steers. */}
            <div className="mode-rail" role="group" aria-label="Cognitive lens">
              {MODE_RAIL.map((item) => (
                <button
                  key={item.id}
                  className={`mode-button ${activeRailId === item.id ? 'is-active' : ''}`}
                  onClick={() => handleLensPin(item.id)}
                  type="button"
                  aria-pressed={activeRailId === item.id}
                  /* The visual 'pinned' marker sits outside the buttons, so AT
                     cannot associate it with the active lens. When the operator
                     has pinned THIS lens, fold the pin into the button's
                     accessible name so a screen reader hears 'OBSERVE, pinned'. */
                  aria-label={
                    pinned && pinnedLens === item.id
                      ? `${item.label}, ${item.sub}, pinned lens`
                      : `${item.label}, ${item.sub}`
                  }
                >
                  <span className="mode-num">{item.num}</span>
                  <span className="mode-copy">
                    <strong>{item.label}</strong>
                    <small>{item.sub}</small>
                  </span>
                  {/* state, not decoration: lit only on the active (live or pinned) lens */}
                  <i className="mode-dot" />
                </button>
              ))}
              {/* Visual-only marker: the pin state is already carried in the
                  active button's aria-label (above), so this is aria-hidden to
                  avoid AT announcing 'pinned' twice. */}
              {pinned ? (
                <span className="lens-pinned" aria-hidden="true">
                  pinned
                </span>
              ) : null}
            </div>

            {/* DISPATCH CADENCE: the live heartbeat of REAL work; replaces the
                fabricated objective %. Honest zeros/dashes/flat hairline at rest.
                aria-atomic is false: a busy turn dispatches many tools, so only
                the changed child node should announce, not the whole PHASE / TOOLS
                / last-tool / VERIFIED SHARE block re-read in full each dispatch. */}
            <div className="dispatch-cadence" aria-live="polite" aria-atomic="false">
              <div className="cad-row">
                <span>PHASE</span>
                <strong>{PHASE_LABEL[livePhase]}</strong>
              </div>
              <div className="cad-row">
                <span>TOOLS THIS TURN</span>
                <strong className="tabnum">
                  {engagedLive} / {knownTools}
                </strong>
              </div>

              {/* heartbeat: a flat hairline + a NON-BLURRED sibling pulse that
                  re-fires (via React key on dispatchSeq) only on a real dispatch. */}
              <div className="cad-beat" aria-hidden="true">
                <i className="cad-beat-line" />
                <i
                  key={toolPulse ? `${toolPulse.row}-${dispatchSeq}` : 'idle'}
                  className={`dispatch-pulse${toolPulse ? ' dispatch-pulse--fire' : ''}`}
                />
              </div>

              <div className="cad-row cad-row--sub">
                <span className="cad-last">{recentSteps[recentSteps.length - 1] ?? '--'}</span>
                <span className="cad-elapsed tabnum">{generating ? elapsedLabel : ''}</span>
              </div>

              {/* honest, optional: a REAL metric, only when trails exist; never
                  presented as "objective %". Hidden at idle/offline. */}
              {verifiedShare !== null ? (
                <div className="cad-row cad-row--share">
                  <span>VERIFIED SHARE</span>
                  <strong className="tabnum">{verifiedShare}%</strong>
                </div>
              ) : null}

              <div className="objective-tree">
                <p className="is-lead">{lastDirective || '--'}</p>
                {/* The sub-steps are the REAL last dispatched tools of the
                    current turn; honest -- placeholders before any turn runs. */}
                <p key={`step-a-${recentSteps.length}`}>
                  {recentSteps[recentSteps.length - 2] ?? '--'}
                </p>
                <p key={`step-b-${recentSteps.length}`}>
                  {recentSteps[recentSteps.length - 1] ?? '--'}
                </p>
              </div>
            </div>
            <i className="glass-grain" aria-hidden />
            {/* Static single-accent foot sheen (was the rainbow wire-glow loop;
                see globals.css · de-rainbowed, de-blurred, de-animated). */}
            <i className="console-glow" aria-hidden />
          </aside>
        </div>
      </Html>

      <Html position={[4.8, -1.5, 0.0]} zIndexRange={[100, 0]}>
        <div style={{ transform: 'translate(-50%, -100%)' }}>
          <aside className="right-console glass-surface" aria-label="System status">
            <div className="panel-heading">
              <div>
                {/* No leading decoration dot (see the left-console eyebrow):
                    the mono uppercase label carries the role on its own. */}
                <span className="eyebrow">KNOWLEDGE INTAKE</span>
                {/* Online: the REAL trail/verified counts. Offline: an honest
                    static status (no rotating carousel, P7 purge). Fabricating
                    motion during an outage is the dishonesty the soul forbids. */}
                <h3 className={linkUp && telemetry ? '' : 'is-offline'}>
                  {linkUp && telemetry
                    ? `Pheromone map · ${telemetry.trails} trail(s) · ${telemetry.verified} verified`
                    : 'LINK OFFLINE · intake paused'}
                </h3>
              </div>
              {/* Decorative affordance only (no behavior): aria-hidden, not a
                  focusable no-op control. */}
              <span className="ghost-plus" aria-hidden="true">
                +
              </span>
            </div>

            <div className="source-list">
              {SOURCE_CHANNELS.map((channel, index) => (
                <SourceRow
                  key={channel.key}
                  metricKey={channel.key}
                  name={channel.name}
                  detail={channel.detail}
                  pulse={sourcePulse && sourcePulse.row === index ? sourcePulse : null}
                  linkUp={linkUp}
                />
              ))}
            </div>

            {/* aria-atomic false (same reason as the dispatch cadence): only the
                changed engaged/avg figure announces, not the whole heading re-read
                on every tool dispatch during a busy turn. */}
            <div className="agent-heading" aria-live="polite" aria-atomic="false">
              <span>AGENT MESH</span>
              {/* Real numbers: distinct tools dispatched this turn over the
                  distinct tools this session has seen. Zero before the first
                  real turn · honest, not decorative. */}
              <strong>
                {engagedLive} / {knownTools} engaged
                {telemetry ? ` · avg ${telemetry.avgToolCalls.toFixed(1)}/turn` : ''}
              </strong>
            </div>
            <div className="agent-list">
              {AGENT_DEFS.map((agent, index) => {
                // Honest state from REAL signals only (no timer cycle): a real
                // tool dispatch owns its card (`processing` + the running tool),
                // else the real directive surge snaps it `active` for ~5s, else
                // `standby` with no invented detail line.
                const isProcessing = toolPulse?.row === index;
                const state: AgentState = isProcessing
                  ? 'processing'
                  : directiveSurge
                    ? FORCED_ON_DIRECTIVE[agent.name] ?? 'standby'
                    : 'standby';
                return (
                  <AgentCard
                    key={agent.name}
                    name={agent.name}
                    icon={agent.icon}
                    state={state}
                    detail={isProcessing ? toolPulse?.detail ?? null : null}
                  />
                );
              })}
            </div>
            <i className="glass-grain" aria-hidden />
            {/* Static single-accent foot sheen (was the rainbow wire-glow loop;
                see globals.css · de-rainbowed, de-blurred, de-animated). */}
            <i className="console-glow" aria-hidden />
          </aside>
        </div>
      </Html>
    </>
  );
}
