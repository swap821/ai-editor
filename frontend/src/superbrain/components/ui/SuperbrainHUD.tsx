'use client';

import { FormEvent, RefObject, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion } from 'motion/react';
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

/** Route a REAL dispatched tool to the card that owns that kind of work. */
function agentRowForTool(tool: string): number {
  const t = tool.toLowerCase();
  if (/plan|orchestr|skill|recall|memory|lesson/.test(t)) return 0; // Planner
  if (/read|search|list|web|fetch|grep|inspect/.test(t)) return 1; // Researcher
  return 2; // Builder — create/edit/execute/verify
}

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
  /* The sparkline is REAL history (one sample per adapter poll, 0..99 →
   * scaled into the 28px viewBox band) once at least two samples exist;
   * before that — or offline forever — the imagination's static hills. */
  const realHistory = useMetricHistory(metricKey);
  const { line, area, lastPoint } = useMemo(() => {
    if (realHistory.length >= 2) {
      const scaled = realHistory.map((v) => 4 + (Math.max(0, Math.min(99, v)) / 99) * 22);
      const paths = buildSparkPaths(scaled);
      return { ...paths, lastPoint: scaled[scaled.length - 1] };
    }
    const canned = SPARKLINES[index];
    return { ...SPARK_PATHS[index], lastPoint: canned[canned.length - 1] };
  }, [realHistory, index]);
  /* Endpoint dot: track has 3px top padding, svg maps viewBox y 1:1 onto its
   * 28px height; center the 3px dot on the LAST point of this row's data. */
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
  forcedDetail = null,
}: {
  name: string;
  icon: AgentIconKind;
  index: number;
  forcedState: AgentState | null;
  /** Real work detail (e.g. "running create_file") — outranks the cycle. */
  forcedDetail?: string | null;
}) {
  const { state, detail: cycledDetail } = useCyclingAgent(name, index, forcedState);
  const detail = forcedDetail ?? cycledDetail;
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
        <small>{detail}</small>
      </span>
      <button type="button" tabIndex={-1} className="ghost-plus ghost-plus--small" aria-label={`Inspect ${name}`}>
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
  const magnetRef = useRef<HTMLSpanElement>(null);
  useMagneticPull(magnetRef);
  const { baseTier, generating, setTier } = useQualityTier();
  const sourceMeshLabel = useCyclingLabel(SOURCE_MESH_LABELS, 6000);

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

  /* LATENCY: the measured trails+metrics round-trip, '--' when offline. */
  const latency = linkUp && telemetry ? telemetry.latencyMs : null;

  /* SOUND: sovereign like its siblings — silent until the operator's own
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
      // Private mode etc. — the session still gets the choice.
    }
  }, []);

  /* CURRENT OBJECTIVE: while a turn streams, progress follows REAL dispatched
   * steps; idle, it is the verified share of the live pheromone map. */
  const objectivePct = generating
    ? Math.min(95, 35 + engagedLive * 12)
    : telemetry && telemetry.trails > 0
      ? Math.round((100 * telemetry.verified) / telemetry.trails)
      : Math.round(60 + activity * 19);

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
          // Mastery is the loudest line the terminal has.
          appendTermLine(
            `Acquired · ${label} (+${event.detail ?? 'trace'})`,
            label.startsWith('SKILL MASTERED'),
          );
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
          // A new turn begins: the live work counters start from zero.
          turnToolsRef.current = new Set();
          setEngagedLive(0);
          setRecentSteps([]);
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
            setTelemetry(data as unknown as AiosTelemetry);
            // A quiet real heartbeat every few polls — telemetry owns the
            // idle channel while the link is alive.
            heartbeatCountRef.current += 1;
            if (heartbeatCountRef.current % 3 === 1) {
              const t = data as unknown as AiosTelemetry;
              appendTermLine(
                `Telemetry · ${t.trails} trail(s) · ${t.verified} verified · ${t.latencyMs}ms`,
              );
            }
          }
          break;
        }
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
      if (toolPulseTimerRef.current !== null) {
        window.clearTimeout(toolPulseTimerRef.current);
        toolPulseTimerRef.current = null;
      }
    };
  }, [appendTermLine]);

  /* ----- idle ticker: imagination lore ONLY while the link is down -----
   * Online, real telemetry heartbeats own the quiet channel — lore would
   * dilute telemetry with fiction. */
  useEffect(() => {
    let timeoutId: number;
    let step = 0;
    const tick = () => {
      if (!getLinkState()) {
        appendTermLine(IDLE_LORE[step % IDLE_LORE.length]);
        step += 1;
      }
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
              transition: 'transform 200ms var(--ease-out-quart)',
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
              {/* The dot tells the truth: green only while the adapter's
                  last poll genuinely reached the AI-OS. */}
              <span role="status">
                <i className={`status-dot ${linkUp ? 'status-dot--live' : 'status-dot--down'}`} />{' '}
                {linkUp ? 'CORE ONLINE' : 'LINK OFFLINE'}
              </span>
              <span className="topbar-divider" />
              {/* Measured trails+metrics round-trip, never invented. */}
              <span>
                LATENCY <strong>{latency !== null ? `${latency}ms` : '--'}</strong>
              </span>
              {/* AUTONOMY: appears only once the brain has EARNED the right to act
                  on a class without a human (by repeated verified success).
                  Additive — invisible until that growth is real, so the canon idle
                  frame is untouched. */}
              {telemetry && telemetry.earnedAutonomy.earned > 0 ? (
                <>
                  <span className="topbar-divider" />
                  <span
                    role="status"
                    title="Action classes the brain earned the right to do autonomously, by repeated verified success"
                  >
                    AUTONOMY <strong>{`⚡${telemetry.earnedAutonomy.earned}`}</strong>
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
                title="Visual fidelity — yours alone; click to cycle high/medium/low"
                onClick={() =>
                  setTier(baseTier === 'high' ? 'medium' : baseTier === 'medium' ? 'low' : 'high')
                }
              >
                FIDELITY <strong>{baseTier.toUpperCase()}</strong>
                {generating ? <em className="fidelity-thinking"> · thinking</em> : null}
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
                    title="Sky — voyage (moving field) or layered (field + nebula dome behind)"
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
                    title="Cortex surface — web (canon energy shell) or organ (your painted flesh under the web)"
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
                title="Sound — breath hum, recall ticks, approval chords; synthesized, your click only"
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
              aria-live="polite"
              title={
                telemetry?.chainValid === true
                  ? `Audit hash-chain intact · ${telemetry.chainEntries} entries`
                  : telemetry?.chainValid === false
                    ? 'AUDIT CHAIN BROKEN — inspect the ledger'
                    : 'Supervised core — audit chain not yet verified'
              }
            >
              <ShieldIcon />{' '}
              {telemetry?.chainValid === false
                ? 'TAMPER'
                : approvalHold
                  ? 'HOLD'
                  : 'Supervised'}
            </button>
          </header>

          <section className="core-readout" aria-label="Core status">
            <h2>
              SUPERMIND <span>/ {currentMode.num}</span>
            </h2>
            <p className="core-sub">
              COGNITIVE SYNTHESIS CORE — {linkUp ? 'ACTIVE' : 'OFFLINE · IMAGINATION'}
            </p>
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
                whileTap={prefersReducedMotion() ? undefined : { scale: 0.97 }}
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
                  aria-pressed={mode === item.id}
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
                {/* The sub-steps are the REAL last dispatched tools of the
                    current turn; em-dashes before any turn has run. */}
                <p>{recentSteps[recentSteps.length - 2] ?? '—'}</p>
                <p>{recentSteps[recentSteps.length - 1] ?? '—'}</p>
              </div>
            </div>
            <i className="glass-grain" aria-hidden />
            <i className="console-glow" aria-hidden />
          </aside>
          <span className="console-surge" aria-hidden="true" />
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
                <h3>
                  {linkUp && telemetry
                    ? `Pheromone map · ${telemetry.trails} trail(s) · ${telemetry.verified} verified`
                    : intakeLabel}
                </h3>
              </div>
              <button type="button" tabIndex={-1} className="ghost-plus" aria-label="Add knowledge source">
                +
              </button>
            </div>

            <div className="source-list">
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
              {/* Real numbers: distinct tools dispatched this turn over the
                  distinct tools this session has seen. Zero before the first
                  real turn — honest, not decorative. */}
              <strong>
                {engagedLive} / {knownTools} engaged
                {telemetry ? ` · avg ${telemetry.avgToolCalls.toFixed(1)}/turn` : ''}
              </strong>
            </div>
            <div className="agent-list">
              {AGENT_DEFS.map((agent, index) => (
                <AgentCard
                  key={agent.name}
                  name={agent.name}
                  icon={agent.icon}
                  index={index}
                  // Priority: a REAL dispatched tool owns its card; the
                  // directive surge choreography fills the first 5s; idle
                  // keeps the ambient cycle.
                  forcedState={
                    toolPulse?.row === index
                      ? 'processing'
                      : directiveSurge
                        ? FORCED_ON_DIRECTIVE[agent.name] ?? null
                        : null
                  }
                  forcedDetail={toolPulse?.row === index ? toolPulse.detail : null}
                />
              ))}
            </div>
            <i className="glass-grain" aria-hidden />
            <i className="console-glow" aria-hidden />
          </aside>
          <span className="console-surge console-surge--reverse" aria-hidden="true" />
        </div>
      </Html>
    </>
  );
}
