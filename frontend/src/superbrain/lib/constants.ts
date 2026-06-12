// ---------------------------------------------------------------------------
// constants.ts – Central configuration for the 3D spatial workspace
// ---------------------------------------------------------------------------
// Every magic number lives here so the rest of the codebase stays clean.
// All colours are provided as hex strings *and* normalised RGB triples so
// they can be fed directly into THREE.Color or custom shaders.
// ---------------------------------------------------------------------------

// ── Colour palette ─────────────────────────────────────────────────────────

export const COLORS = {
  // Panel surface
  obsidian: '#080a14',
  obsidianRGB: [0.03, 0.04, 0.08],

  // Accent colours
  violet: '#7c3aed',
  violetRGB: [0.49, 0.23, 0.93],
  cyan: '#06b6d4',
  cyanRGB: [0.02, 0.71, 0.83],
  magenta: '#d946ef',
  indigo: '#6366f1',
  purple: '#a78bfa',

  // UI text
  textPrimary: '#e2e8f0',
  textSecondary: '#94a3b8',
  textMuted: '#475569',

  // State-driven colours (mapped to AIState values)
  idle: '#06b6d4',
  waiting: '#06b6d4',
  generating: '#a78bfa',
  error: '#ef4444',

  // Environment
  voidBg: '#050510',
  particleBase: '#261a59',
};

// ── Panel spatial layout & Context summoning ───────────────────────────────────
// Positions & rotations are in world-space units (≈ metres).
// `domSize` is the CSS-pixel size fed into Html overlays.

export enum LayoutContext {
  CONVERSATIONAL = 'Conversational',
  FRONTEND = 'Frontend Dev',
  BACKEND = 'Backend Dev',
  FULLSTACK = 'Full Stack',
  COGNITIVE_AGENT = 'Cognitive Agent',
}

export interface PanelConfig {
  visible: boolean;
  position: [number, number, number];
  rotation: [number, number, number];
  size: [number, number];
  domSize: { width: number; height: number };
  scale?: [number, number, number];
}

export const LAYOUT_CONFIGS: Record<LayoutContext, Record<string, PanelConfig>> = {
  [LayoutContext.CONVERSATIONAL]: {
    chat: { visible: true, position: [0.00, 0.23, -2.50], rotation: [0, 0, 0], size: [7.47, 6.90], domSize: { width: 747, height: 690 } },
    editor: { visible: false, position: [-5.20, 0.20, -12.00], rotation: [0, 0.35, 0], size: [7.13, 6.44], domSize: { width: 713, height: 644 } },
    terminal: { visible: false, position: [0.00, -3.15, -12.00], rotation: [0, 0, 0], size: [7.13, 2.53], domSize: { width: 713, height: 253 } },
    preview: { visible: false, position: [5.20, 1.25, -12.00], rotation: [0, -0.35, 0], size: [7.13, 6.44], domSize: { width: 713, height: 644 } },
    api: { visible: false, position: [5.30, -2.10, -12.00], rotation: [0, -0.35, 0], size: [7.13, 2.53], domSize: { width: 713, height: 253 } },
    database: { visible: false, position: [-5.30, -2.10, -12.00], rotation: [0, 0.35, 0], size: [6.32, 2.53], domSize: { width: 633, height: 253 } },
    git: { visible: false, position: [-5.30, 0.20, -12.00], rotation: [0, 0.35, 0], size: [7.13, 6.44], domSize: { width: 713, height: 644 } },
    cognition: { visible: false, position: [-5.30, 0.20, -12.00], rotation: [0, 0.35, 0], size: [7.13, 6.44], domSize: { width: 713, height: 644 } },
    security: { visible: false, position: [5.30, 0.20, -12.00], rotation: [0, -0.35, 0], size: [7.13, 6.44], domSize: { width: 713, height: 644 } },
  },
  [LayoutContext.FRONTEND]: {
    chat: { visible: true, position: [11.50, -1.88, -4.50], rotation: [0, -0.40, 0], size: [7.13, 3.68], domSize: { width: 713, height: 368 } },
    editor: { visible: true, position: [-8.50, 0.23, -3.50], rotation: [0, 0.25, 0], size: [7.13, 7.59], domSize: { width: 713, height: 759 } },
    preview: { visible: true, position: [10.50, 3.88, -5.50], rotation: [0, -0.35, 0], size: [7.13, 3.68], domSize: { width: 713, height: 368 } },
    git: { visible: true, position: [0.00, -7.47, -6.50], rotation: [-0.15, 0, 0], size: [14.49, 2.07], domSize: { width: 1449, height: 207 } },
    terminal: { visible: false, position: [0.00, -3.15, -12.00], rotation: [0, 0, 0], size: [7.13, 2.53], domSize: { width: 713, height: 253 } },
    api: { visible: false, position: [5.30, -2.10, -12.00], rotation: [0, 0, 0], size: [7.13, 2.53], domSize: { width: 713, height: 253 } },
    database: { visible: false, position: [-5.30, -2.10, -12.00], rotation: [0, 0, 0], size: [6.32, 2.53], domSize: { width: 633, height: 253 } },
    cognition: { visible: false, position: [-5.30, 0.20, -12.00], rotation: [0, 0, 0], size: [7.13, 6.44], domSize: { width: 713, height: 644 } },
    security: { visible: false, position: [5.30, 0.20, -12.00], rotation: [0, 0, 0], size: [7.13, 6.44], domSize: { width: 713, height: 644 } },
  },
  [LayoutContext.BACKEND]: {
    chat: { visible: true, position: [13.00, -1.00, -4.50], rotation: [0, -0.45, 0], size: [7.13, 6.00], domSize: { width: 713, height: 600 } },
    editor: { visible: true, position: [-13.00, -1.00, -4.50], rotation: [0, 0.45, 0], size: [7.13, 6.00], domSize: { width: 713, height: 600 } },
    terminal: { visible: true, position: [0.00, -4.00, -3.50], rotation: [0, 0, 0], size: [10.00, 3.50], domSize: { width: 1000, height: 350 } },
    api: { visible: true, position: [0.00, 1.50, -3.50], rotation: [0, 0, 0], size: [10.00, 5.00], domSize: { width: 1000, height: 500 } },
    security: { visible: true, position: [0.00, 7.00, -5.50], rotation: [0.10, 0, 0], size: [14.00, 2.50], domSize: { width: 1400, height: 250 } },
    preview: { visible: false, position: [3.30, 1.90, -12.00], rotation: [0, 0, 0], size: [7.13, 3.68], domSize: { width: 713, height: 368 } },
    database: { visible: false, position: [-3.30, -2.10, -12.00], rotation: [0, 0, 0], size: [6.32, 2.53], domSize: { width: 633, height: 253 } },
    git: { visible: false, position: [-3.30, 0.20, -12.00], rotation: [0, 0, 0], size: [7.13, 6.44], domSize: { width: 713, height: 644 } },
    cognition: { visible: false, position: [-3.30, 0.20, -12.00], rotation: [0, 0, 0], size: [7.13, 6.44], domSize: { width: 713, height: 644 } },
  },
  [LayoutContext.FULLSTACK]: {
    chat: { visible: true, position: [11.50, -2.88, -4.50], rotation: [0, -0.40, 0], size: [6.32, 6.67], domSize: { width: 633, height: 667 } },
    editor: { visible: true, position: [-11.50, 1.38, -4.50], rotation: [0, 0.40, 0], size: [6.32, 5.75], domSize: { width: 633, height: 575 } },
    database: { visible: true, position: [-11.50, -4.02, -4.50], rotation: [0, 0.40, 0], size: [6.32, 2.53], domSize: { width: 633, height: 253 } },
    preview: { visible: true, position: [0.00, 3.53, -6.50], rotation: [0.10, 0, 0], size: [6.90, 4.37], domSize: { width: 690, height: 437 } },
    terminal: { visible: true, position: [0.00, -7.47, -5.50], rotation: [-0.15, 0, 0], size: [6.90, 2.99], domSize: { width: 690, height: 299 } },
    cognition: { visible: true, position: [11.50, 4.02, -4.50], rotation: [0, -0.40, 0], size: [6.32, 4.37], domSize: { width: 633, height: 437 } },
    api: { visible: false, position: [5.30, -2.10, -12.00], rotation: [0, 0, 0], size: [7.13, 2.53], domSize: { width: 713, height: 253 } },
    git: { visible: false, position: [-5.30, 0.20, -12.00], rotation: [0, 0, 0], size: [7.13, 6.44], domSize: { width: 713, height: 644 } },
    security: { visible: false, position: [5.30, 0.20, -12.00], rotation: [0, 0, 0], size: [7.13, 6.44], domSize: { width: 713, height: 644 } },
  },
  [LayoutContext.COGNITIVE_AGENT]: {
    chat: { visible: true, position: [0.00, 1.00, -2.50], rotation: [0, 0, 0], size: [7.00, 6.50], domSize: { width: 700, height: 650 } },
    cognition: { visible: true, position: [-11.00, 1.00, -3.50], rotation: [0, 0.55, 0], size: [8.00, 7.50], domSize: { width: 800, height: 750 } },
    security: { visible: true, position: [11.00, 1.00, -3.50], rotation: [0, -0.55, 0], size: [8.00, 7.50], domSize: { width: 800, height: 750 } },
    api: { visible: true, position: [0.00, -5.50, -3.50], rotation: [-0.15, 0, 0], size: [14.00, 3.50], domSize: { width: 1400, height: 350 } },
    editor: { visible: false, position: [-5.20, 0.20, -12.00], rotation: [0, 0, 0], size: [7.13, 6.44], domSize: { width: 713, height: 644 } },
    terminal: { visible: false, position: [0.00, -3.15, -12.00], rotation: [0, 0, 0], size: [7.13, 2.53], domSize: { width: 713, height: 253 } },
    preview: { visible: false, position: [5.20, 1.25, -12.00], rotation: [0, 0, 0], size: [7.13, 6.44], domSize: { width: 713, height: 644 } },
    database: { visible: false, position: [-5.30, -2.10, -12.00], rotation: [0, 0, 0], size: [6.32, 2.53], domSize: { width: 633, height: 253 } },
    git: { visible: false, position: [-5.30, 0.20, -12.00], rotation: [0, 0, 0], size: [7.13, 6.44], domSize: { width: 713, height: 644 } },
  },
};

// ── Spring physics configs (react-spring) ──────────────────────────────────

export const SPRING_CONFIGS = {
  parallax: { mass: 2, tension: 120, friction: 40 },
  panelDrag: { mass: 5, tension: 200, friction: 50 },
  magneticSnap: { mass: 3, tension: 300, friction: 35 },
  buttonPress: { mass: 1, tension: 400, friction: 20 },
  lightTransition: { mass: 1, tension: 80, friction: 30 },
};

// ── AI state enum ──────────────────────────────────────────────────────────
// Numeric values double as shader uniforms (0 → idle, 0.5 → waiting, 1 → gen)

export enum AIState {
  IDLE = 0,
  WAITING = 0.5,
  GENERATING = 1.0,
}

// ── Timing constants ───────────────────────────────────────────────────────

export const TIMING = {
  borderRotationSpeed: 0.3,
  breathingFrequency: 1.0,
  pulseFrequency: 4.0,
  kineticTextStagger: 20, // ms between characters
  kineticTextCycles: 3,
  kineticTextCycleDuration: 40, // ms per cycle
  activityDecayTime: 2000, // ms
};

// ── Camera ─────────────────────────────────────────────────────────────────

export const CAMERA = {
  position: [0.00, 0.00, 12.00] as [number, number, number],
  fov: 45,
  near: 0.1,
  far: 100,
};

// ── Lighting ───────────────────────────────────────────────────────────────

export const LIGHTS = {
  ambient: { intensity: 0.15, color: '#1a1a2e' },
  rimViolet: {
    position: [-9.20, 5.75, 1.00] as [number, number, number],
    intensity: 0.6,
    color: '#7c3aed',
  },
  rimCyan: {
    position: [9.20, -3.45, 3.00] as [number, number, number],
    intensity: 0.4,
    color: '#06b6d4',
  },
  aiPoint: {
    position: [4.37, 0.34, 1.00] as [number, number, number],
    intensity: 0.8,
    color: '#a78bfa',
  },
};

// ── Post-processing ────────────────────────────────────────────────────────
// SINGLE SOURCE OF TRUTH for the cinematic grade. PostFX.tsx wires every
// value below into the effect chain (and WorkspaceCanvas.tsx reads
// toneMappingExposure) — tune HERE, not in the components.

export const POST_FX = {
  // Consumed by the AgX ToneMapping effect (three uploads it to every
  // program). Tuning range 1.4-1.9: the brain crown must show rose
  // GRADATION, not a flat clipped plateau.
  toneMappingExposure: 1.45,

  // Intensity boosted and threshold set to 1.0 so ONLY the ultra-bright neon mesh and lobes glow.
  bloom: { intensity: 2.5, luminanceThreshold: 1.0, luminanceSmoothing: 0.9 },

  chromaticAberration: { offset: [0.00055, 0.00055] as [number, number] },

  // FilmGrade custom effects (PostFX.tsx):
  //   GradePre  — BEFORE AgX, scene-referred log-space contrast.
  //   GradePost — AFTER AgX, display-referred split-tone + vibrance.
  // No lift control by design — soft-light preserves true black.
  grade: {
    contrast: 1.06, // log-space contrast around the mid-grey pivot
    shadowTint: [0.42, 0.52, 0.55] as [number, number, number], // teal — binds canvas shadows to the HUD cyan
    highTint: [0.55, 0.53, 0.47] as [number, number, number], // amber — turns the muddy nebula golden
    balance: -0.08, // shifts the split point; keeps the bright rose brain clean of orange
    vibrance: 0.21, // restores AgX-flattened nebula chroma; (1-sat) protects saturated filaments
  },

  // Darkness eased 0.7 -> 0.62: the grade now carries the cinema; the
  // heavier vignette was crushing corner text.
  vignette: { offset: 0.28, darkness: 0.62 },

  noise: { opacity: 0.025 },
};

// ── Parallax ───────────────────────────────────────────────────────────────

export const PARALLAX = {
  maxRotation: 0.052, // radians (~3 degrees)
  sensitivity: 1.0,
};

// ── Drag physics ───────────────────────────────────────────────────────────

export const DRAG = {
  snapThreshold: 1.5, // world units – distance at which magnetic snap activates
  snapStrength: 0.15, // 0-1, how strong the snap pull is
  inertia: 0.92, // velocity damping factor
};
