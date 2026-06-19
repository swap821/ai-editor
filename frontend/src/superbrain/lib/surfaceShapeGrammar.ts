import type { OrganMaterialRole } from './organMaterialState';
import type { MaterializedTabKind, TabLifecycle } from './tabStore';

export type SurfaceShapeClass = 'intake' | 'decision' | 'work' | 'correction' | 'memory' | 'waiting';
export type SurfaceShapeAttachmentKind = 'brainstem-inferior' | 'vertebra-left' | 'vertebra-right' | 'bilateral-roots';
export type SurfaceShapeEdge = 'top' | 'right' | 'bottom' | 'left';
export type SurfaceGripSource = 'stem' | 'root';

export interface SurfaceShapeDimensions {
  width: number;
  height: number;
  radius: number;
  thickness: number;
}

export interface SurfaceGripMark {
  edge: SurfaceShapeEdge;
  source: SurfaceGripSource;
  u: number;
  indentPx: number;
  indentScene: number;
  radiusScene: number;
  intensity: number;
}

export interface SurfaceShapeGrammarInput {
  kind: MaterializedTabKind;
  lifecycle?: TabLifecycle;
  focused: boolean;
  waitingIndex?: number;
  role?: OrganMaterialRole;
  originLocal: readonly [number, number, number];
  targetLocal: readonly [number, number, number];
  dimensions: SurfaceShapeDimensions;
  rootGripCount?: number;
  actuator?: {
    tension?: number;
    stiffness?: number;
    textureMix?: number;
    role?: string;
  } | null;
}

export interface SurfaceShapeGrammar {
  surfaceClass: SurfaceShapeClass;
  attachment: {
    kind: SurfaceShapeAttachmentKind;
    edges: readonly SurfaceShapeEdge[];
    freeEdges: readonly SurfaceShapeEdge[];
    sideSign: -1 | 0 | 1;
  };
  rules: {
    membraneAttachment: boolean;
    tensionCurve: boolean;
    thicknessGradient: boolean;
    punctaField: boolean;
    rootGripMarks: boolean;
    satisfiedCount: number;
  };
  tension: {
    controlOffsetPx: number;
    sceneOffset: number;
    topCurve: number;
    bottomCurve: number;
    sideCurve: number;
    cornerLift: number;
  };
  thickness: {
    attachmentPx: number;
    freePx: number;
    attachmentDepth: number;
    freeDepth: number;
    opacity: number;
  };
  puncta: {
    count: number;
    attachmentDensity: number;
    freeDensity: number;
    falloffPower: number;
    disruption: number;
  };
  gripMarks: readonly SurfaceGripMark[];
  contour: {
    waist: number;
    freeBulge: number;
    attachmentPinch: number;
    scarDisruption: number;
  };
}

export const SURFACE_SHAPE_DIMENSIONS: Record<MaterializedTabKind, SurfaceShapeDimensions> = {
  content: {
    width: 1.18,
    height: 0.94,
    radius: 0.065,
    thickness: 0.028,
  },
  input: {
    width: 0.98,
    height: 0.28,
    radius: 0.075,
    thickness: 0.04,
  },
  approval: {
    width: 1.02,
    height: 0.78,
    radius: 0.06,
    thickness: 0.024,
  },
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function round4(value: number): number {
  return Math.round(value * 10000) / 10000;
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

function classifySurface(kind: MaterializedTabKind, role: OrganMaterialRole | undefined): SurfaceShapeClass {
  if (kind === 'input') return 'intake';
  if (role === 'scar') return 'correction';
  if (role === 'memory') return 'memory';
  if (role === 'waiting') return 'waiting';
  if (kind === 'approval') return 'decision';
  return 'work';
}

function attachmentFor(input: SurfaceShapeGrammarInput): SurfaceShapeGrammar['attachment'] {
  if (input.kind === 'input') {
    return {
      kind: 'brainstem-inferior',
      edges: ['top'],
      freeEdges: ['bottom'],
      sideSign: 0,
    };
  }

  if (input.kind === 'approval') {
    return {
      kind: 'bilateral-roots',
      edges: ['left', 'right'],
      freeEdges: ['top', 'bottom'],
      sideSign: 0,
    };
  }

  const sideSign = input.targetLocal[0] >= input.originLocal[0] ? 1 : -1;
  return {
    kind: sideSign > 0 ? 'vertebra-left' : 'vertebra-right',
    edges: [sideSign > 0 ? 'left' : 'right'],
    freeEdges: [sideSign > 0 ? 'right' : 'left'],
    sideSign,
  };
}

function gripUsFor(edge: SurfaceShapeEdge, kind: MaterializedTabKind): readonly number[] {
  if (kind === 'input' && edge === 'top') return [0.42, 0.58];
  if (kind === 'approval') return [0.24, 0.76];
  return [0.16, 0.34, 0.66, 0.84];
}

function makeGripMarks(
  input: SurfaceShapeGrammarInput,
  attachment: SurfaceShapeGrammar['attachment'],
  surfaceClass: SurfaceShapeClass,
): SurfaceGripMark[] {
  const tension = clamp(input.actuator?.tension ?? (input.focused ? 0.58 : 0.28), 0, 1);
  const stiffness = clamp(input.actuator?.stiffness ?? 0.42, 0, 1);
  const waitingDimming = input.focused || input.kind === 'input' ? 1 : clamp(0.72 - (input.waitingIndex ?? 0) * 0.08, 0.44, 0.72);
  const scarBoost = surfaceClass === 'correction' ? 0.72 : 0;
  const baseIndentPx = clamp(2.1 + tension * 2.7 + stiffness * 0.8 + scarBoost, 2, 6);
  const source: SurfaceGripSource = input.kind === 'input' ? 'stem' : 'root';
  const edgeScale = Math.min(input.dimensions.width, input.dimensions.height);

  return attachment.edges.flatMap((edge) =>
    gripUsFor(edge, input.kind).map((u) => {
      const edgeWeight = edge === 'top' || edge === 'bottom' ? input.dimensions.height : input.dimensions.width;
      const indentPx = round2(baseIndentPx * waitingDimming);
      return {
        edge,
        source,
        u,
        indentPx,
        indentScene: round4(edgeWeight * (indentPx / 180)),
        radiusScene: round4(edgeScale * (0.024 + tension * 0.014)),
        intensity: round4(clamp((0.52 + tension * 0.42 + scarBoost * 0.22) * waitingDimming, 0.22, 1.15)),
      };
    }),
  );
}

export function deriveSurfaceShapeGrammar(input: SurfaceShapeGrammarInput): SurfaceShapeGrammar {
  const surfaceClass = classifySurface(input.kind, input.role);
  const attachment = attachmentFor(input);
  const activity = clamp(
    Math.max(
      input.actuator?.tension ?? 0,
      input.lifecycle === 'reaching' || input.lifecycle === 'unfurling' ? 0.42 : 0,
      input.lifecycle === 'retracting' ? 0.62 : 0,
      surfaceClass === 'correction' ? 0.72 : 0,
    ),
    0,
    1,
  );
  const focusedScale = input.kind === 'input' || input.focused ? 1 : clamp(0.64 - (input.waitingIndex ?? 0) * 0.07, 0.4, 0.64);
  const controlOffsetPx = round2(
    clamp(
      (input.kind === 'approval' ? 18.5 : input.kind === 'input' ? 16 : 14.5) + activity * 5.2,
      8,
      24,
    ),
  );
  const sceneOffset = round4(Math.min(input.dimensions.width, input.dimensions.height) * (controlOffsetPx / 210));
  const gripMarks = makeGripMarks(input, attachment, surfaceClass);
  const nearPx = round2(clamp(2 + activity * 0.64 + focusedScale * 0.28, 2, 3.1));
  const freePx = round2(clamp(0.5 + (1 - focusedScale) * 0.1, 0.5, 0.7));
  const rootGripMarks = gripMarks.length > 0;
  const rules = {
    membraneAttachment: attachment.edges.length > 0,
    tensionCurve: controlOffsetPx >= 8 && controlOffsetPx <= 24,
    thicknessGradient: nearPx > freePx,
    punctaField: true,
    rootGripMarks,
  };

  return {
    surfaceClass,
    attachment,
    rules: {
      ...rules,
      satisfiedCount: Object.values(rules).filter(Boolean).length,
    },
    tension: {
      controlOffsetPx,
      sceneOffset,
      topCurve: round4((input.kind === 'input' ? -0.4 : 0.72) * sceneOffset),
      bottomCurve: round4((input.kind === 'input' ? 0.9 : -0.66) * sceneOffset),
      sideCurve: round4((attachment.sideSign || 1) * sceneOffset * (input.kind === 'approval' ? 0.18 : 0.52)),
      cornerLift: round4(sceneOffset * (input.kind === 'input' ? 0.72 : 0.36)),
    },
    thickness: {
      attachmentPx: nearPx,
      freePx,
      attachmentDepth: round4(input.dimensions.thickness * (1.28 + activity * 0.42)),
      freeDepth: round4(input.dimensions.thickness * 0.32),
      opacity: round4(clamp(0.16 + focusedScale * 0.16 + activity * 0.1, 0.12, 0.42)),
    },
    puncta: {
      count: Math.round((input.kind === 'input' ? 18 : input.kind === 'approval' ? 28 : 34) * (0.76 + focusedScale * 0.24)),
      attachmentDensity: round4(clamp(0.62 + activity * 0.22, 0.5, 0.88)),
      freeDensity: round4(clamp(0.18 + (1 - focusedScale) * 0.08, 0.12, 0.28)),
      falloffPower: round4(clamp(1.65 + activity * 0.44, 1.4, 2.3)),
      disruption: round4(surfaceClass === 'correction' ? clamp(0.34 + activity * 0.36, 0.34, 0.78) : 0),
    },
    gripMarks,
    contour: {
      waist: round4(clamp(0.012 + activity * 0.016, 0.01, 0.034)),
      freeBulge: round4(clamp(sceneOffset * (input.kind === 'approval' ? 0.36 : 0.62), 0.006, 0.045)),
      attachmentPinch: round4(clamp(sceneOffset * (0.52 + activity * 0.3), 0.006, 0.052)),
      scarDisruption: round4(surfaceClass === 'correction' ? clamp(0.012 + activity * 0.018, 0.012, 0.034) : 0),
    },
  };
}
