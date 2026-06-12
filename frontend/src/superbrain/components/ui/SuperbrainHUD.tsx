'use client';

import { FormEvent, RefObject, useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion } from 'motion/react';
import { Html } from '@react-three/drei';
import { publishCognition, subscribeCognition } from '@/lib/cognitionBus';
import { useMetric, type MetricKey } from '@/lib/metricsStore';
import { getPendingApproval, type PendingApproval } from '@/lib/aiosAdapter';
import { useQualityTier } from '@/components/QualityTierProvider';
import ApprovalPanel from './ApprovalPanel';

export type CognitiveMode = 'observe' | 'synthesize' | 'orchestrate';

interface SuperbrainHUDProps {
  mode: CognitiveMode;
  activity: number;
  lastDirective: string;
  onModeChange: (mode: CognitiveMode) => void;
  onDirective: (directive: string) => void;
}

const modeCopy: Record<CognitiveMode, { title: string; detail: string }> = {
  observe: {
    title: 'Observing knowledge horizon',
    detail: 'Indexing live signals and mapping relationships.',
  },
  synthesize: {
    title: 'Synthesizing directive',
    detail: 'Specialist agents converging on one execution model.',
  },
  orchestrate: {
    title: 'Orchestrating agent mesh',
    detail: 'Plans validated, delegated, and monitored in real time.',
  },
};

/* ---------- Mode rail ---------- */
const MODE_RAIL: { id: CognitiveMode; num: string; label: string; sub: string }[] = [
  { id: 'observe', num: '01', label: 'OBSERVE', sub: 'Map and orient' },
  { id: 'synthesize', num: '02', label: 'SYNTHESIZE', sub: 'Reason and create' },
  { id: 'orchestrate', num: '03', label: 'ORCHESTRATE', sub: 'Delegate and deliver' },
];

/* ---------- Intake channels — values come from metricsStore (single source of truth) ---------- */
const SOURCE_CHANNELS: { key: MetricKey; name: string; detail: string }[] = [
  { key: 'research', name: 'Research', detail: 'deep archive scan' },
  { key: 'memory', name: 'Memory', detail: 'episodic lattice' },
  { key: 'tools', name: 'Tools', detail: 'runtime mesh' },
  { key: 'signals', name: 'Signals', detail: 'ambient telemetry' },
];

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

/* ---------- Precomputed sparkline hills (deterministic, low-frequency) ---------- */
const SPARKLINES: number[][] = [
  [6, 13, 22, 25, 18, 23, 15, 20],
  [9, 18, 24, 16, 21, 26, 19, 23],
  [5, 11, 19, 24, 17, 13, 21, 16],
  [12, 20, 25, 18, 14, 22, 10, 17],
];

function buildSparkPaths(points: number[], width = 100, height = 28) {
  const step = width / (points.length - 1);
  const xy = points.map((p, i) => [i * step, height - p] as const);
  let line = `M ${xy[0][0]} ${xy[0][1]}`;
  for (let i = 1; i < xy.length; i += 1) {
    const [x0, y0] = xy[i - 1];
    const [x1, y1] = xy[i];
    const mx = (x0 + x1) / 2;
    line += ` C ${mx} ${y0}, ${mx} ${y1}, ${x1} ${y1}`;
  }
  const area = `${line} L ${width} ${height} L 0 ${height} Z`;
  return { line, area };
}

const SPARK_PATHS = SPARKLINES.map((points) => buildSparkPaths(points));

/* ---------- Living agent states ---------- */
type AgentIconKind = 'compass' | 'magnifier' | 'hammer';
type AgentState = (typeof AGENT_STATES)[number];

const AGENT_DEFS: { name: string; icon: AgentIconKind }[] = [
  { name: 'Planner', icon: 'compass' },
  { name: 'Researcher', icon: 'magnifier' },
  { name: 'Builder', icon: 'hammer' },
];

const AGENT_STATES = ['active', 'processing', 'standby'] as const;
const AGENT_DETAILS: Record<string, string[]> = {
  Planner: [
    'Decomposing objective into tasks',
    'Mapping task dependencies',
    'Sequencing execution paths',
    'Validating plan constraints',
  ],
  Researcher: [
    'Scanning archive strata',
    'Cross-validating sources',
    'Indexing intake signals',
    'Correlating entropy patterns',
  ],
  Builder: [
    'Compiling artifact scaffolds',
    'Binding module interfaces',
    'Deploying lattice modules',
    'Verifying build integrity',
  ],
};

/* On a directive the mesh visibly snaps to attention: the Planner leads, the
 * Researcher digs. Builder keeps its own rhythm so the reaction reads
 * orchestrated, not scripted. */
const FORCED_ON_DIRECTIVE: Record<string, AgentState> = {
  Planner: 'active',
  Researcher: 'processing',
};

/* ---------- Rotating knowledge intake labels ---------- */
const SOURCE_MESH_LABELS = [
  'Live source mesh',
  'Semantic knowledge graph',
  'Causal inference web',
  'Temporal signal lattice',
  'Distributed consensus',
  'Long-horizon context weave',
];

/* ---------- Living terminal log ---------- */
interface TermLine {
  id: number;
  time: string;
  text: string;
  /** Seed lines render static; live lines flash bright then dim via CSS. */
  fresh: boolean;
  bright?: boolean;
}

/* Deterministic seed buffer so SSR and first client render agree. */
const SEED_TERM_LINES: TermLine[] = [
  { id: -4, time: '00:00', text: 'Cognition core initialized', fresh: false },
  { id: -3, time: '00:01', text: 'Agent mesh handshake complete', fresh: false },
  { id: -2, time: '00:02', text: 'Knowledge intake channels open', fresh: false },
  { id: -1, time: '00:03', text: 'Synthesis cycle nominal', fresh: false },
];

const TERM_BUFFER_MAX = 4;

/* Quiet idle chatter between cognition events — the OS never sits silent. */
const IDLE_LORE = [
  'Indexing semantic clusters',
  'Drift correction 0.0021',
  'Archive checksum verified',
  'Horizon scan clean',
  'Tether integrity 99.97%',
  'Entropy gradient within bounds',
];

/* Staggered 6-9s cadence (deterministic cycle, no unseeded randomness). */
const IDLE_DELAYS = [6400, 8800, 7200, 6000, 9000, 7600];

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

const SearchIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <circle cx="11" cy="11" r="6" />
    <path d="m15.6 15.6 4.4 4.4" />
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

/* ---------- Utility: jittered value with smooth transitions ---------- */
function useJitteredValue(base: number, range: number, intervalMs: number, min = 0, max = 100) {
  const [value, setValue] = useState(base);
  useEffect(() => {
    const id = setInterval(() => {
      const jitter = (Math.random() - 0.5) * 2 * range;
      setValue(Math.max(min, Math.min(max, base + jitter)));
    }, intervalMs);
    return () => clearInterval(id);
  }, [base, range, intervalMs, min, max]);
  return Math.round(value);
}

/* ---------- Utility: cycling agent state (staggered per agent so state words never align) ---------- */
function useCyclingAgent(name: string, index: number, forcedState: AgentState | null) {
  const [stateIndex, setStateIndex] = useState(index % AGENT_STATES.length);
  const [detailIndex, setDetailIndex] = useState(index);
  const details = AGENT_DETAILS[name] || [name];

  useEffect(() => {
    const interval = 4000 + index * 1300;
    const id = setInterval(() => {
      setStateIndex((prev) => (prev + 1) % AGENT_STATES.length);
      setDetailIndex((prev) => (prev + 1) % details.length);
    }, interval);
    return () => clearInterval(id);
  }, [details.length, index]);

  return {
    state: forcedState ?? AGENT_STATES[stateIndex],
    detail: details[detailIndex % details.length],
  };
}

/* ---------- Utility: prefers-reduced-motion (checked at interaction time) ---------- */
function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/* ---------- Utility: tweened metric ----------
 * 350ms cubic ease-out rAF tween between store values so numbers glide
 * instead of snapping. Plain React state, cancelled on unmount; collapses to
 * instant under prefers-reduced-motion. NO odometer theatrics. */
function useTweenedMetric(target: number) {
  const [display, setDisplay] = useState(target);
  const displayRef = useRef(target);

  useEffect(() => {
    if (displayRef.current === target) return;
    /* Reduced motion: jump to the target on the next frame (no tween). */
    const duration = prefersReducedMotion() ? 0 : 350;
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
  }, [target]);

  return display;
}

/* ---------- Utility: restrained hover decode ----------
 * ~400ms scramble-reveal over a tight charset. A module-level lock keeps it
 * to ONE decoding element at a time; glyph choice is time-derived, never
 * Math.random in a render path. The real name stays in aria-label. */
const DECODE_GLYPHS = '01:/%·';
let decodeActive = false;

function useDecodeOnHover(text: string) {
  const [display, setDisplay] = useState(text);
  const rafRef = useRef(0);
  const holdingRef = useRef(false);

  const release = useCallback(() => {
    if (holdingRef.current) {
      decodeActive = false;
      holdingRef.current = false;
    }
  }, []);

  const start = useCallback(() => {
    if (decodeActive || prefersReducedMotion()) return;
    decodeActive = true;
    holdingRef.current = true;
    const began = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - began) / 400);
      const settled = Math.floor(t * text.length);
      let next = text.slice(0, settled);
      for (let i = settled; i < text.length; i += 1) {
        next += DECODE_GLYPHS[(i * 5 + (now >> 6)) % DECODE_GLYPHS.length];
      }
      if (t < 1) {
        setDisplay(next);
        rafRef.current = requestAnimationFrame(tick);
      } else {
        setDisplay(text);
        release();
      }
    };
    rafRef.current = requestAnimationFrame(tick);
  }, [text, release]);

  useEffect(
    () => () => {
      cancelAnimationFrame(rafRef.current);
      release();
    },
    [release],
  );

  return { display, start };
}

/* ---------- Utility: magnetic pull (Execute ONLY) ----------
 * rAF lerp toward (cursor - center) * 0.3 while the cursor is inside a
 * radius of buttonWidth * 0.7; lerp factor 0.1; ~400ms power3-out snap-back
 * on leave. Transforms are written straight to the wrapper ref — zero React
 * state per frame. Disabled under prefers-reduced-motion. */
function useMagneticPull(ref: RefObject<HTMLSpanElement | null>) {
  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion()) return;

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
      if (Math.hypot(dx, dy) < rect.width * 0.7) {
        targetX = dx * 0.3;
        targetY = dy * 0.3;
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
  }, [ref]);
}

/* ---------- Utility: cycling label ---------- */
function useCyclingLabel(labels: string[], intervalMs: number) {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    const id = setInterval(() => {
      setIndex((prev) => (prev + 1) % labels.length);
    }, intervalMs);
    return () => clearInterval(id);
  }, [labels, intervalMs]);
  return labels[index];
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
  index,
  pulse,
}: {
  metricKey: MetricKey;
  name: string;
  detail: string;
  index: number;
  pulse: SourcePulse | null;
}) {
  const value = useTweenedMetric(useMetric(metricKey));
  const { line, area } = SPARK_PATHS[index];
  /* Endpoint dot: track has 3px top padding, svg maps viewBox y 1:1 onto its
   * 28px height; center the 3px dot on the LAST point of this row's data. */
  const lastPoint = SPARKLINES[index][SPARKLINES[index].length - 1];
  const dotTop = 3 + (28 - lastPoint) - 1.5;

  return (
    <div className="source-block">
      <div className="source-row">
        <span key={pulse ? pulse.id : 'idle'} className={`source-orb${pulse ? ' source-orb--flash' : ''}`} />
        <span className="source-name">
          <strong>{name}</strong>
          <small>{detail}</small>
        </span>
        <span className="source-value">{value}%</span>
      </div>
      <div className="source-spark-track">
        <svg className="source-spark" viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <linearGradient id={`spark-fill-${index}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#5ce1e6" stopOpacity="0.16" />
              <stop offset="100%" stopColor="#5ce1e6" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={area} fill={`url(#spark-fill-${index})`} />
          <path
            d={line}
            fill="none"
            stroke="#5ce1e6"
            strokeOpacity="0.8"
            strokeWidth="1.25"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
        <span className="spark-dot" style={{ top: `${dotTop}px` }} aria-hidden="true" />
      </div>
    </div>
  );
}

/* ---------- Animated agent card ---------- */
function AgentCard({
  name,
  icon,
  index,
  forcedState,
}: {
  name: string;
  icon: AgentIconKind;
  index: number;
  forcedState: AgentState | null;
}) {
  const { state, detail } = useCyclingAgent(name, index, forcedState);
  const { display: decodedName, start: startDecode } = useDecodeOnHover(name);
  return (
    <div className="agent-card">
      <span className="agent-avatar">
        <AgentIcon kind={icon} />
      </span>
      <span className="agent-info">
        <strong>
          <span className="agent-name" aria-label={name} onMouseEnter={startDecode}>
            {decodedName}
          </span>
          <em className={`agent-state agent-state--${state}`}>{state}</em>
        </strong>
        <small style={{ transition: 'opacity 0.3s var(--ease-out-quart)' }}>{detail}</small>
      </span>
      <button type="button" className="ghost-plus ghost-plus--small" aria-label={`Inspect ${name}`}>
        +
      </button>
    </div>
  );
}

export default function SuperbrainHUD({
  mode,
  activity,
  lastDirective,
  onModeChange,
  onDirective,
}: SuperbrainHUDProps) {
  const [directive, setDirective] = useState('');
  const [approvalHold, setApprovalHold] = useState(false);
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null);
  const refreshPendingApproval = useCallback(() => {
    setPendingApproval(getPendingApproval());
  }, []);
  const magnetRef = useRef<HTMLSpanElement>(null);
  useMagneticPull(magnetRef);
  const latency = useJitteredValue(21, 5, 1200);
  const { baseTier, generating, setTier } = useQualityTier();
  const sourceMeshLabel = useCyclingLabel(SOURCE_MESH_LABELS, 6000);
  const engaged = useJitteredValue(9, 1, 5000, 8, 11);
  const objectivePct = Math.round(60 + activity * 19);

  /* ----- living terminal buffer ----- */
  const [termLines, setTermLines] = useState<TermLine[]>(SEED_TERM_LINES);
  const termIdRef = useRef(0);
  const termEpochRef = useRef<number | null>(null);

  const appendTermLine = useCallback((text: string, bright = false) => {
    if (termEpochRef.current === null) termEpochRef.current = performance.now();
    /* Mono clock: mm:ss since HUD ignition, continuing past the seed stamps. */
    const totalSeconds = Math.floor((performance.now() - termEpochRef.current) / 1000) + 4;
    const mm = String(Math.floor(totalSeconds / 60) % 100).padStart(2, '0');
    const ss = String(totalSeconds % 60).padStart(2, '0');
    const id = termIdRef.current;
    termIdRef.current += 1;
    setTermLines((prev) =>
      [...prev, { id, time: `${mm}:${ss}`, text, fresh: true, bright }].slice(-TERM_BUFFER_MAX),
    );
  }, []);

  /* ----- knowledge intake + agent mesh reactions ----- */
  const [sourcePulse, setSourcePulse] = useState<SourcePulse | null>(null);
  const pulseIdRef = useRef(0);
  const rotateRef = useRef(0);
  const [directiveSurge, setDirectiveSurge] = useState(false);
  const surgeTimeoutRef = useRef<number | null>(null);

  /* ----- nervous system: the HUD reacts to the same events as the 3D scene ----- */
  useEffect(() => {
    const unsubscribe = subscribeCognition((event) => {
      switch (event.type) {
        case 'knowledge-acquired': {
          const label = event.label ?? 'signal shard';
          appendTermLine(`Acquired · ${label} (+${event.detail ?? 'trace'})`);
          pulseIdRef.current += 1;
          setSourcePulse({
            id: pulseIdRef.current,
            row: matchSourceRow(label, rotateRef),
          });
          break;
        }
        case 'burst':
          // A labeled burst is a RECALL — the brain touching a real trail.
          appendTermLine(
            event.label
              ? `Recall · ${event.label}${event.detail ? ` (${event.detail})` : ''}`
              : 'Cortical burst · resonance nominal',
          );
          break;
        case 'directive': {
          appendTermLine(`Directive received · ${event.label ?? 'unspecified'}`, true);
          setApprovalHold(false);
          setDirectiveSurge(true);
          if (surgeTimeoutRef.current !== null) window.clearTimeout(surgeTimeoutRef.current);
          surgeTimeoutRef.current = window.setTimeout(() => {
            setDirectiveSurge(false);
            surgeTimeoutRef.current = null;
          }, 5000);
          break;
        }
        case 'agent-dispatch':
          appendTermLine(`Mesh · ${event.label ?? 'agent dispatched'}`);
          break;
        case 'synthesis':
          appendTermLine(`Synthesis · ${event.detail ?? event.label ?? 'cycle complete'}`);
          setApprovalHold(false);
          break;
        case 'approval-required':
          // The supervised mind defers to its operator — loudest line we have.
          appendTermLine(`HOLD · ${event.detail ?? 'operator approval required'}`, true);
          setApprovalHold(true);
          setPendingApproval(getPendingApproval());
          break;
        case 'approval-resolved':
          appendTermLine(`Resume · ${event.label ?? 'operator decision received'}`, true);
          setApprovalHold(false);
          setPendingApproval(getPendingApproval());
          break;
      }
    });
    return () => {
      unsubscribe();
      if (surgeTimeoutRef.current !== null) {
        window.clearTimeout(surgeTimeoutRef.current);
        surgeTimeoutRef.current = null;
      }
    };
  }, [appendTermLine]);

  /* ----- idle ticker: quiet lines on a staggered 6-9s cadence ----- */
  useEffect(() => {
    let timeoutId: number;
    let step = 0;
    const tick = () => {
      appendTermLine(IDLE_LORE[step % IDLE_LORE.length]);
      step += 1;
      timeoutId = window.setTimeout(tick, IDLE_DELAYS[step % IDLE_DELAYS.length]);
    };
    timeoutId = window.setTimeout(tick, IDLE_DELAYS[0]);
    return () => window.clearTimeout(timeoutId);
  }, [appendTermLine]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextDirective = directive.trim();
    if (!nextDirective) return;
    /* Broadcast on the cognition bus FIRST so the whole organism (terminal,
     * agents, 3D scene) reacts to the directive, then hand off upstream. */
    publishCognition({ type: 'directive', label: nextDirective, intensity: 1, source: 'hud' });
    onDirective(nextDirective);
    setDirective('');
  };

  const currentMode = MODE_RAIL.find((m) => m.id === mode) || MODE_RAIL[0];
  const intakeLabel = sourceMeshLabel;

  return (
    <>
      <Html>
        {createPortal(
          <div className="hud-shell">
          {/* Skip link for accessibility */}
          <a
            href="#directive"
            className="skip-link"
            style={{
              position: 'absolute',
              left: '16px',
              zIndex: 9999,
              background: '#8b5cf6',
              color: '#ffffff',
              padding: '8px 12px',
              borderRadius: '6px',
              fontWeight: 'bold',
              fontSize: '12px',
              textDecoration: 'none',
              transform: 'translateY(-150%)',
              transition: 'transform 0.2s',
            }}
            onFocus={(e) => e.currentTarget.style.transform = 'translateY(16px)'}
            onBlur={(e) => e.currentTarget.style.transform = 'translateY(-150%)'}
          >
            Skip to HUD controls
          </a>

          <div className="bottom-scrim" aria-hidden="true" />

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
              <span>
                <i className="status-dot status-dot--live" /> CORE ONLINE
              </span>
              <span className="topbar-divider" />
              <span>
                LATENCY <strong>{latency}ms</strong>
              </span>
              <span className="topbar-divider" />
              {/* FIDELITY IS SACRED: only this click ever changes the tier
                  (cycles high -> medium -> low -> high). The governor may
                  whisper advice in the terminal; it cannot act. */}
              <button
                className="fidelity-button"
                type="button"
                title="Visual fidelity — yours alone; click to cycle high/medium/low"
                onClick={() =>
                  setTier(baseTier === 'high' ? 'medium' : baseTier === 'medium' ? 'low' : 'high')
                }
              >
                FIDELITY <strong>{baseTier.toUpperCase()}</strong>
                {generating ? <em className="fidelity-thinking"> · thinking</em> : null}
              </button>
            </div>

            <button className="secure-button" type="button">
              <ShieldIcon /> Secured
            </button>
          </header>

          <section className="core-readout" aria-label="Core status">
            <h2>
              SUPERMIND <span>/ {currentMode.num}</span>
            </h2>
            <p className="core-sub">COGNITIVE SYNTHESIS CORE — ACTIVE</p>
          </section>

          <div className="terminal-log" aria-live="polite" aria-atomic="false">
            <span>TERMINAL LOG</span>
            {termLines.map((termLine) => (
              <p
                key={termLine.id}
                className={`${termLine.fresh ? 'term-fresh' : ''}${termLine.bright ? ' is-bright' : ''}`}
              >
                <em>{termLine.time}</em> {termLine.text}
              </p>
            ))}
          </div>

          {pendingApproval ? (
            <ApprovalPanel pending={pendingApproval} onSettled={refreshPendingApproval} />
          ) : null}

          <form
            className={`command-bar${approvalHold ? ' is-approval-hold' : ''}`}
            onSubmit={handleSubmit}
          >
            <span className="command-chip" aria-hidden="true">
              &gt;_
            </span>
            <div className="command-field">
              <label htmlFor="directive">DIRECT THE SUPERMIND</label>
              <input
                id="directive"
                value={directive}
                onChange={(event) => setDirective(event.target.value)}
                placeholder="Ask the Supermind..."
                autoComplete="off"
              />
            </div>
            <span className="command-search" aria-hidden="true">
              <SearchIcon />
            </span>
            <span className="execute-wrap" ref={magnetRef}>
              <motion.button
                className="execute-button"
                whileTap={{ scale: 0.97 }}
                transition={{ duration: 0.12 }}
                type="submit"
              >
                Execute
                <span className="execute-return" aria-hidden="true">
                  ⏎
                </span>
              </motion.button>
            </span>
            <i className="glass-grain" aria-hidden />
          </form>

          <div className="hud-footer" aria-hidden="true">
            GAGOS v2.6 — autonomous core
          </div>
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
          <aside className="left-console glass-surface" aria-label="Cognitive state">
            <div className="eyebrow">
              <span /> ACTIVE COGNITION
            </div>
            <h1>{modeCopy[mode].title}</h1>
            <p className="cognition-detail">{modeCopy[mode].detail}</p>

            <div className="mode-rail" role="group" aria-label="Cognitive mode">
              {MODE_RAIL.map((item) => (
                <button
                  key={item.id}
                  className={`mode-button ${mode === item.id ? 'is-active' : ''}`}
                  onClick={() => onModeChange(item.id)}
                  type="button"
                >
                  <span className="mode-num">{item.num}</span>
                  <span className="mode-copy">
                    <strong>{item.label}</strong>
                    <small>{item.sub}</small>
                  </span>
                  <i className="mode-dot" />
                </button>
              ))}
            </div>

            <div className="objective-card" aria-live="polite" aria-atomic="true">
              <div className="objective-head">
                <span>CURRENT OBJECTIVE</span>
                <strong>{objectivePct}%</strong>
              </div>
              <div className="objective-bar">
                <i style={{ width: `${objectivePct}%` }} />
              </div>
              <div className="objective-tree">
                <p className="is-lead">{lastDirective}</p>
                <p>Identifying semantic clusters in intake signals</p>
                <p>Evaluating entropy across archive deltas</p>
              </div>
            </div>
            <i className="glass-grain" aria-hidden />
          </aside>
        </div>
      </Html>

      <Html position={[4.8, -1.5, 0.0]} zIndexRange={[100, 0]}>
        <div style={{ transform: 'translate(-50%, -100%)' }}>
          <aside className="right-console glass-surface" aria-label="System status">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">
                  <span /> KNOWLEDGE INTAKE
                </span>
                <h3 style={{ transition: 'opacity 0.6s var(--ease-out-quart)' }}>{intakeLabel}</h3>
              </div>
              <button type="button" className="ghost-plus" aria-label="Add knowledge source">
                +
              </button>
            </div>

            <div className="source-list" aria-live="polite" aria-atomic="false">
              {SOURCE_CHANNELS.map((channel, index) => (
                <SourceRow
                  key={channel.key}
                  metricKey={channel.key}
                  name={channel.name}
                  detail={channel.detail}
                  index={index}
                  pulse={sourcePulse && sourcePulse.row === index ? sourcePulse : null}
                />
              ))}
            </div>

            <div className="agent-heading" aria-live="polite" aria-atomic="true">
              <span>AGENT MESH</span>
              <strong>{engaged} / 15 engaged</strong>
            </div>
            <div className="agent-list">
              {AGENT_DEFS.map((agent, index) => (
                <AgentCard
                  key={agent.name}
                  name={agent.name}
                  icon={agent.icon}
                  index={index}
                  forcedState={directiveSurge ? FORCED_ON_DIRECTIVE[agent.name] ?? null : null}
                />
              ))}
            </div>
            <i className="glass-grain" aria-hidden />
          </aside>
        </div>
      </Html>
    </>
  );
}
