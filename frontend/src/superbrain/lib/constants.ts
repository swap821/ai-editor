// ---------------------------------------------------------------------------
// constants.ts – Post-processing + camera constants for the 3D spatial workspace
// ---------------------------------------------------------------------------
// P3-1 cleanup: removed dead COLORS / LAYOUT_CONFIGS / SPRING_CONFIGS / AIState /
// TIMING / LIGHTS / PARALLAX / DRAG exports. The live canvas only consumes
// POST_FX and CAMERA; palette/lights live in the canon CSS/token layer.
// ---------------------------------------------------------------------------

// ── Camera ─────────────────────────────────────────────────────────────────

export const CAMERA = {
  position: [0.00, 0.00, 12.00] as [number, number, number],
  fov: 45,
  near: 0.1,
  far: 100,
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

  // Point-field (?being=points) rides the SAME Bloom pass but gentler: the per-point
  // radial sprite already carries the glow, so a low intensity keeps the halo hugging
  // the body instead of bleeding a wide haze into the clean void. PostFX picks this
  // block in points mode; mesh mode keeps `bloom` above byte-for-byte.
  bloomPoints: { intensity: 0.72, luminanceThreshold: 1.08, luminanceSmoothing: 0.28 },

  chromaticAberration: { offset: [0.00055, 0.00055] as [number, number] },

  // FilmGrade custom effects (PostFX.tsx):
  //   GradePre  — BEFORE AgX, scene-referred log-space contrast.
  //   GradePost — AFTER AgX, display-referred split-tone + vibrance.
  // No lift control by design — soft-light preserves true black.
  grade: {
    contrast: 1.06, // log-space contrast around the mid-grey pivot
    shadowTint: [0.42, 0.52, 0.55] as [number, number, number], // teal — binds canvas shadows to the HUD cyan
    // Amber — turns the muddy nebula golden. Luma-neutral (Rec.709 0.4999,
    // like the shadow side): soft-light then shifts CHROMA only, so the
    // split-tone never re-brightens the crown's path back to a plateau.
    highTint: [0.52, 0.5, 0.44] as [number, number, number],
    balance: -0.08, // shifts the split point; keeps the bright rose brain clean of orange
    vibrance: 0.21, // restores AgX-flattened nebula chroma; (1-sat) protects saturated filaments
  },

  // Darkness eased 0.7 -> 0.62: the grade now carries the cinema; the
  // heavier vignette was crushing corner text.
  vignette: { offset: 0.28, darkness: 0.62 },
  // Points being frames the void a touch more strongly to read as a "home".
  vignettePoints: { offset: 0.32, darkness: 0.76 },

  noise: { opacity: 0.025 },
};
