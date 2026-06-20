import { Text } from '@react-three/drei';
import { readBeingMode } from '@/lib/beingMode';

// In the point-field being the spine is welded into the brain cloud at
// spineScale (1/BRAIN_SCALE ≈ 0.33); surface ANCHORS are fused (correct
// position), but the slab geometry is authored for the old mesh-spine scale, so
// counter-scale the slab body/content to match the fused being. Mesh = 1.
const POINTS = readBeingMode() === 'points';
const POINTS_SLAB_SCALE = POINTS ? 0.66 : 1; // poster phase 4: the born tab is a brain-sized peer, not a tiny panel
import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { approvePendingApproval, rejectPendingApproval } from '@/lib/aiosAdapter';
import { deriveMaterializedSurfacePose } from '@/lib/materializedSurfacePose';
import { deriveMaterializedSurfaceSkin, type MaterializedSurfaceSkin } from '@/lib/materializedSurfaceSkin';
import { deriveOrganMaterialState, type OrganMaterialState } from '@/lib/organMaterialState';
import { formatMaterializedTextPreview } from '@/lib/materializedTextPreview';
import { REST_OUTCOME_IMPRINT, type OutcomeImprintSnapshot } from '@/lib/outcomeImprint';
import {
  deriveSurfaceShapeGrammar,
  SURFACE_SHAPE_DIMENSIONS,
  type SurfaceGripMark,
  type SurfaceShapeEdge,
  type SurfaceShapeGrammar,
} from '@/lib/surfaceShapeGrammar';
import type { MaterializedApprovalSurface, MaterializedTabKind, MaterializedTabRecord } from '@/lib/tabStore';
import { REST_TURN_METABOLISM, type TurnMetabolismSnapshot } from '@/lib/turnMetabolism';
import { deriveVertebraConductorRoots } from '@/lib/vertebraConductorRoots';
import { BODY_POSTURES, postureColor01, POSTURE_DIAL, type BodyPosture } from '@/lib/bodyPosture';
import {
  beginRetractingMaterializedTab,
  clearMaterializedTab,
  focusMaterializedTab,
  REPLY_FILEPATH,
  setMaterializedTabLifecycle,
} from '@/lib/tabStore';

const REACH_DURATION_MS = 900;
const UNFURL_DURATION_MS = 520;
const RETRACT_DURATION_MS = 380;
const BASE_TUBE_RADIUS = 0.012;
const UMBILICAL_SEGMENTS = 32;
const UMBILICAL_RADIAL_SEGMENTS = 10;
const BEAD_COUNT = 4;
const CONDUCTOR_BEAD_COUNT = 4;
const CONDUCTOR_PUNCTA_PER_ROOT = 6;
const CONDUCTOR_SEGMENTS = 22;
const CONDUCTOR_RADIAL_SEGMENTS = 7;
const CONTENT_PREVIEW_LINES = 16;
const CONTENT_PREVIEW_CHARS = 44;
const APPROVAL_PREVIEW_LINES = 12;
const APPROVAL_PREVIEW_CHARS = 56;
const TAU = Math.PI * 2;

const SURFACE_DIMENSIONS: Record<
  MaterializedTabKind,
  {
    width: number;
    height: number;
    radius: number;
    thickness: number;
    htmlWidth: number;
    htmlHeight: number;
    tilt: [number, number, number];
  }
> = {
  content: {
    ...SURFACE_SHAPE_DIMENSIONS.content,
    htmlWidth: 0,
    htmlHeight: 0,
    tilt: [0.02, 0.34, 0.02],
  },
  input: {
    ...SURFACE_SHAPE_DIMENSIONS.input,
    htmlWidth: 760,
    htmlHeight: 176,
    tilt: [0.05, 0, 0],
  },
  approval: {
    ...SURFACE_SHAPE_DIMENSIONS.approval,
    htmlWidth: 0,
    htmlHeight: 0,
    tilt: [0.03, 0.26, 0.02],
  },
};

type SurfaceDimensions = (typeof SURFACE_DIMENSIONS)[MaterializedTabKind];
type SurfaceTheme = {
  reach: THREE.Color;
  live: THREE.Color;
  frame: THREE.Color;
  body: string;
  header: string;
  accent: string;
  outline: string;
  plate: string;
  text: string;
  muted: string;
  point: string;
};

function toSurfaceTheme(material: OrganMaterialState): SurfaceTheme {
  return {
    reach: new THREE.Color(material.palette.reach),
    live: new THREE.Color(material.palette.live),
    frame: new THREE.Color(material.palette.frame),
    body: material.palette.body,
    header: material.palette.header,
    accent: material.palette.accent,
    outline: material.palette.outline,
    plate: material.palette.plate,
    text: material.palette.text,
    muted: material.palette.muted,
    point: material.palette.point,
  };
}

function clamp01(value: number): number {
  return THREE.MathUtils.clamp(value, 0, 1);
}

function easing(value: number): number {
  return value * value * (3 - 2 * value);
}

function marksForEdge(grammar: SurfaceShapeGrammar, edge: SurfaceShapeEdge, descending = false): SurfaceGripMark[] {
  const marks = grammar.gripMarks.filter((mark) => mark.edge === edge);
  return marks.sort((a, b) => (descending ? b.u - a.u : a.u - b.u));
}

function makeAnatomicalSurfaceShape(
  width: number,
  height: number,
  radius: number,
  grammar: SurfaceShapeGrammar,
): THREE.Shape {
  const halfW = width * 0.5;
  const halfH = height * 0.5;
  const r = Math.min(radius, halfW, halfH);
  const topY = halfH;
  const rightX = halfW;
  const bottomY = -halfH;
  const leftX = -halfW;
  const topMarks = marksForEdge(grammar, 'top', true);
  const rightMarks = marksForEdge(grammar, 'right');
  const bottomMarks = marksForEdge(grammar, 'bottom');
  const leftMarks = marksForEdge(grammar, 'left', true);
  const scar = grammar.contour.scarDisruption;
  const shape = new THREE.Shape();

  shape.moveTo(leftX + r, bottomY + grammar.tension.cornerLift);

  if (bottomMarks.length === 0) {
    shape.quadraticCurveTo(0, bottomY + grammar.tension.bottomCurve - scar * 0.4, rightX - r, bottomY + grammar.tension.cornerLift * 0.6);
  } else {
    bottomMarks.forEach((mark) => {
      const x = leftX + width * mark.u;
      shape.lineTo(x - mark.radiusScene, bottomY);
      shape.quadraticCurveTo(x, bottomY + mark.indentScene, x + mark.radiusScene, bottomY);
    });
    shape.lineTo(rightX - r, bottomY + grammar.tension.cornerLift * 0.6);
  }

  shape.quadraticCurveTo(rightX + grammar.contour.freeBulge * 0.3, bottomY, rightX, bottomY + r);

  if (rightMarks.length === 0) {
    const sideBulge = grammar.attachment.edges.includes('right') ? -grammar.contour.attachmentPinch : grammar.contour.freeBulge;
    shape.quadraticCurveTo(rightX + sideBulge, 0, rightX, topY - r);
  } else {
    rightMarks.forEach((mark) => {
      const y = bottomY + height * mark.u;
      shape.lineTo(rightX, y - mark.radiusScene);
      shape.quadraticCurveTo(rightX - mark.indentScene, y, rightX, y + mark.radiusScene);
    });
    shape.lineTo(rightX, topY - r);
  }

  shape.quadraticCurveTo(rightX, topY, rightX - r, topY + grammar.tension.cornerLift * 0.4);

  if (topMarks.length === 0) {
    shape.quadraticCurveTo(0, topY + grammar.tension.topCurve + scar * 0.35, leftX + r, topY + grammar.tension.cornerLift * 0.4);
  } else {
    topMarks.forEach((mark) => {
      const x = leftX + width * mark.u;
      shape.lineTo(x + mark.radiusScene, topY);
      shape.quadraticCurveTo(x, topY - mark.indentScene, x - mark.radiusScene, topY);
    });
    shape.lineTo(leftX + r, topY + grammar.tension.cornerLift * 0.4);
  }

  shape.quadraticCurveTo(leftX, topY, leftX, topY - r);

  if (leftMarks.length === 0) {
    const sideBulge = grammar.attachment.edges.includes('left') ? grammar.contour.attachmentPinch : -grammar.contour.freeBulge;
    shape.quadraticCurveTo(leftX + sideBulge, 0, leftX, bottomY + r);
  } else {
    leftMarks.forEach((mark) => {
      const y = bottomY + height * mark.u;
      shape.lineTo(leftX, y + mark.radiusScene);
      shape.quadraticCurveTo(leftX + mark.indentScene, y, leftX, y - mark.radiusScene);
    });
    shape.lineTo(leftX, bottomY + r);
  }

  shape.quadraticCurveTo(leftX, bottomY, leftX + r, bottomY + grammar.tension.cornerLift);
  return shape;
}

function baseName(path: string): string {
  return String(path).split(/[\\/]/).pop() || path;
}

function toUiLabel(value: string): string {
  return String(value || 'other')
    .replace(/[_-]/g, ' ')
    .trim()
    .toUpperCase();
}

function getSurfaceHeader(tab: MaterializedTabRecord): string {
  if (tab.kind === 'content') {
    if (tab.content?.filepath === REPLY_FILEPATH) return 'GAGOS';
    return tab.content?.filepath ? baseName(tab.content.filepath) : 'materialized tab';
  }
  if (tab.kind === 'input') {
    return 'brainstem intake';
  }
  const approval = tab.approval;
  if (!approval) return 'approval required';
  return approval.filepath ? baseName(approval.filepath) : approval.command ? 'command approval' : 'approval required';
}

function getSurfaceFooter(tab: MaterializedTabRecord): string {
  if (tab.kind === 'content') {
    if (tab.content?.filepath === REPLY_FILEPATH) return '';
    return tab.content?.language ?? 'text';
  }
  if (tab.kind === 'input') return 'press enter to send';
  if (!tab.approval) return 'human review';
  const token = tab.approval.token ? tab.approval.token.slice(0, 10) : 'pending';
  return `${toUiLabel(tab.approval.kindLabel)} ${token}`;
}

function getApprovalBody(approval: MaterializedApprovalSurface | null): string {
  if (!approval) return '';
  return String(approval.diff || approval.content || approval.command || approval.explanation || approval.summary || '');
}

function ApprovalActionButton({
  label,
  position,
  fill,
  outline,
  disabled,
  onActivate,
}: {
  label: string;
  position: [number, number, number];
  fill: string;
  outline: string;
  disabled: boolean;
  onActivate: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <group
      position={position}
      scale={hovered && !disabled ? 1.04 : 1}
      onPointerOver={(event) => {
        event.stopPropagation();
        if (!disabled) setHovered(true);
      }}
      onPointerOut={(event) => {
        event.stopPropagation();
        setHovered(false);
      }}
      onClick={(event) => {
        event.stopPropagation();
        if (!disabled) onActivate();
      }}
    >
      <mesh renderOrder={11}>
        <sphereGeometry args={[0.052, 20, 14]} />
        <meshStandardMaterial
          color={fill}
          emissive={fill}
          emissiveIntensity={disabled ? 0.05 : hovered ? 0.7 : 0.32}
          roughness={0.24}
          metalness={0.06}
          transparent
          opacity={disabled ? 0.24 : hovered ? 0.95 : 0.78}
        />
      </mesh>
      <mesh rotation={[Math.PI / 2, 0, 0]} renderOrder={12}>
        <torusGeometry args={[0.078, 0.004, 8, 36]} />
        <meshBasicMaterial
          color={outline}
          transparent
          opacity={disabled ? 0.12 : hovered ? 0.52 : 0.28}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      <Text
        position={[0, 0, 0.064]}
        color="#f9fbff"
        fontSize={0.017}
        maxWidth={0.11}
        anchorX="center"
        anchorY="middle"
        outlineWidth={0.002}
        outlineColor="#04070c"
        renderOrder={13}
      >
        {label}
      </Text>
    </group>
  );
}

function makeMembraneVeinGeometry(width: number, height: number, kind: MaterializedTabKind): THREE.BufferGeometry {
  const halfW = width * 0.5;
  const halfH = height * 0.5;
  const centerYOffset = kind === 'input' ? 0 : kind === 'approval' ? -height * 0.03 : height * 0.02;
  const cy = centerYOffset;
  const z = 0;
  const points = [
    -halfW * 0.82,
    halfH * 0.68,
    z,
    -halfW * 0.22,
    halfH * 0.28 + cy,
    z,
    halfW * 0.82,
    halfH * 0.66,
    z,
    halfW * 0.22,
    halfH * 0.26 + cy,
    z,
    -halfW * 0.84,
    -halfH * 0.62,
    z,
    -halfW * 0.18,
    -halfH * 0.3 + cy,
    z,
    halfW * 0.84,
    -halfH * 0.6,
    z,
    halfW * 0.18,
    -halfH * 0.32 + cy,
    z,
    -halfW * 0.7,
    halfH * 0.18,
    z,
    halfW * 0.72,
    halfH * 0.1,
    z,
    -halfW * 0.64,
    -halfH * 0.16,
    z,
    halfW * 0.66,
    -halfH * 0.24,
    z,
  ];
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
  return geometry;
}

function LivingMembraneSkin({
  dimensions,
  kind,
  material,
  metabolism,
  outcome,
  shapeGrammar,
  skin,
  surfaceGeometry,
  theme,
}: {
  dimensions: SurfaceDimensions;
  kind: MaterializedTabKind;
  material: OrganMaterialState;
  metabolism: TurnMetabolismSnapshot;
  outcome: OutcomeImprintSnapshot;
  shapeGrammar: SurfaceShapeGrammar;
  skin: MaterializedSurfaceSkin;
  surfaceGeometry: THREE.ShapeGeometry;
  theme: SurfaceTheme;
}) {
  const metabolismColor = useMemo(() => new THREE.Color(metabolism.tint), [metabolism.tint]);
  const outcomeColor = useMemo(() => new THREE.Color(outcome.tint), [outcome.tint]);
  const membraneColor = useMemo(
    () =>
      theme.frame
        .clone()
        .lerp(metabolismColor, Math.min(0.28, metabolism.surfaceExcitation * 0.6))
        .lerp(outcomeColor, Math.min(0.18, outcome.surfaceGlow * 0.54)),
    [metabolism.surfaceExcitation, metabolismColor, outcome.surfaceGlow, outcomeColor, theme.frame],
  );
  const veinColor = useMemo(
    () =>
      theme.reach
        .clone()
        .lerp(metabolismColor, Math.min(0.68, metabolism.surfaceExcitation * 1.15))
        .lerp(outcomeColor, Math.min(0.62, outcome.rootGlow * 0.92)),
    [metabolism.surfaceExcitation, metabolismColor, outcome.rootGlow, outcomeColor, theme.reach],
  );
  const veinGeometry = useMemo(
    () => makeMembraneVeinGeometry(dimensions.width, dimensions.height, kind),
    [dimensions.height, dimensions.width, kind],
  );
  const nodePositions = useMemo(
    () => [
      [-dimensions.width * 0.43, dimensions.height * 0.38, dimensions.thickness + 0.019],
      [dimensions.width * 0.43, dimensions.height * 0.37, dimensions.thickness + 0.019],
      [-dimensions.width * 0.44, -dimensions.height * 0.36, dimensions.thickness + 0.019],
      [dimensions.width * 0.44, -dimensions.height * 0.35, dimensions.thickness + 0.019],
      [-dimensions.width * 0.46, 0, dimensions.thickness + 0.019],
      [dimensions.width * 0.46, -dimensions.height * 0.02, dimensions.thickness + 0.019],
    ] as [number, number, number][],
    [dimensions.height, dimensions.thickness, dimensions.width],
  );

  useEffect(() => {
    return () => veinGeometry.dispose();
  }, [veinGeometry]);

  return (
    <>
      <mesh position={[0, 0, dimensions.thickness + 0.004]} scale={[1.025, 1.025, 1]} renderOrder={9}>
        <primitive object={surfaceGeometry} attach="geometry" />
        <meshBasicMaterial
          color={membraneColor}
          transparent
          opacity={skin.membraneOpacity * material.tissue.membraneOpacityScale}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      <SurfaceThicknessGradientSkin dimensions={dimensions} material={material} shapeGrammar={shapeGrammar} theme={theme} />
      <RootGripDeformationSkin dimensions={dimensions} material={material} shapeGrammar={shapeGrammar} skin={skin} theme={theme} />
      <lineSegments geometry={veinGeometry} position={[0, 0, dimensions.thickness + 0.022]} renderOrder={10}>
        <lineBasicMaterial color={veinColor} transparent opacity={skin.veinOpacity * material.tissue.signalOpacityScale} />
      </lineSegments>
      {nodePositions.map((position, index) => (
        <mesh key={`membrane-node-${kind}-${index}`} position={position} renderOrder={10}>
          <sphereGeometry args={[0.0095, 10, 8]} />
          <meshBasicMaterial
            color={veinColor}
            transparent
            opacity={skin.nodeOpacity * material.tissue.signalOpacityScale}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      ))}
    </>
  );
}

function gripMarkLocalPosition(mark: SurfaceGripMark, dimensions: SurfaceDimensions, z: number): [number, number, number] {
  const halfW = dimensions.width * 0.5;
  const halfH = dimensions.height * 0.5;
  if (mark.edge === 'left') return [-halfW + mark.indentScene * 0.52, -halfH + dimensions.height * mark.u, z];
  if (mark.edge === 'right') return [halfW - mark.indentScene * 0.52, -halfH + dimensions.height * mark.u, z];
  if (mark.edge === 'top') return [-halfW + dimensions.width * mark.u, halfH - mark.indentScene * 0.52, z];
  return [-halfW + dimensions.width * mark.u, -halfH + mark.indentScene * 0.52, z];
}

function SurfaceThicknessGradientSkin({
  dimensions,
  material,
  shapeGrammar,
  theme,
}: {
  dimensions: SurfaceDimensions;
  material: OrganMaterialState;
  shapeGrammar: SurfaceShapeGrammar;
  theme: SurfaceTheme;
}) {
  const bands = [
    ...shapeGrammar.attachment.edges.map((edge) => ({
      edge,
      depth: shapeGrammar.thickness.attachmentDepth,
      opacity: shapeGrammar.thickness.opacity * material.tissue.membraneOpacityScale,
      key: `attachment-${edge}`,
    })),
    ...shapeGrammar.attachment.freeEdges.map((edge) => ({
      edge,
      depth: shapeGrammar.thickness.freeDepth,
      opacity: shapeGrammar.thickness.opacity * 0.36 * material.tissue.membraneOpacityScale,
      key: `free-${edge}`,
    })),
  ];
  const halfW = dimensions.width * 0.5;
  const halfH = dimensions.height * 0.5;
  return (
    <>
      {bands.map((band) => {
        const horizontal = band.edge === 'top' || band.edge === 'bottom';
        const position: [number, number, number] =
          band.edge === 'left'
            ? [-halfW + band.depth * 0.5, 0, dimensions.thickness + 0.012]
            : band.edge === 'right'
              ? [halfW - band.depth * 0.5, 0, dimensions.thickness + 0.012]
              : band.edge === 'top'
                ? [0, halfH - band.depth * 0.5, dimensions.thickness + 0.012]
                : [0, -halfH + band.depth * 0.5, dimensions.thickness + 0.012];
        return (
          <mesh key={band.key} position={position} renderOrder={10}>
            <planeGeometry args={horizontal ? [dimensions.width * 0.82, band.depth] : [band.depth, dimensions.height * 0.86]} />
            <meshBasicMaterial
              color={theme.frame}
              transparent
              opacity={band.opacity}
              blending={THREE.AdditiveBlending}
              depthWrite={false}
            />
          </mesh>
        );
      })}
    </>
  );
}

function RootGripDeformationSkin({
  dimensions,
  material,
  shapeGrammar,
  skin,
  theme,
}: {
  dimensions: SurfaceDimensions;
  material: OrganMaterialState;
  shapeGrammar: SurfaceShapeGrammar;
  skin: MaterializedSurfaceSkin;
  theme: SurfaceTheme;
}) {
  const gripColor = useMemo(() => new THREE.Color(theme.point), [theme.point]);
  const coreColor = useMemo(() => new THREE.Color(theme.outline), [theme.outline]);
  return (
    <>
      {shapeGrammar.gripMarks.map((mark, index) => {
        const position = gripMarkLocalPosition(mark, dimensions, dimensions.thickness + 0.026);
        const horizontal = mark.edge === 'top' || mark.edge === 'bottom';
        const scarBoost = shapeGrammar.surfaceClass === 'correction' ? 1.28 : 1;
        return (
          <group key={`shape-grip-${mark.edge}-${index}`} position={position} renderOrder={12}>
            <mesh scale={horizontal ? [mark.radiusScene * 1.25, mark.indentScene * 2.8, 0.16] : [mark.indentScene * 2.8, mark.radiusScene * 1.25, 0.16]}>
              <sphereGeometry args={[1, 14, 8]} />
              <meshBasicMaterial
                color={coreColor}
                transparent
                opacity={Math.min(0.56, skin.nodeOpacity * material.tissue.rootGripGain * mark.intensity * 1.2)}
                depthWrite={false}
              />
            </mesh>
            <mesh
              scale={
                horizontal
                  ? [mark.radiusScene * 0.64, mark.indentScene * 1.08, 0.12]
                  : [mark.indentScene * 1.08, mark.radiusScene * 0.64, 0.12]
              }
            >
              <sphereGeometry args={[1, 12, 8]} />
              <meshBasicMaterial
                color={gripColor}
                transparent
                opacity={Math.min(0.48, material.tissue.pointFieldOpacity * mark.intensity * scarBoost * 1.8)}
                blending={THREE.AdditiveBlending}
                depthWrite={false}
              />
            </mesh>
          </group>
        );
      })}
    </>
  );
}

function deterministic01(value: number): number {
  const base = Math.sin(value) * 43758.5453;
  return base - Math.floor(base);
}

function makePointFieldPositions(dimensions: SurfaceDimensions, kind: MaterializedTabKind, shapeGrammar: SurfaceShapeGrammar) {
  const count = shapeGrammar.puncta.count;
  // POSTER (phase 4): the tab is BUILT FROM POINTS — a dotted-particle border on
  // ALL FOUR edges + a sparse interior grain (not just the attachment edge). ~70%
  // of puncta ring the border, ~30% sprinkle the interior so the face reads as one
  // point-field organism, not flat glass. Deterministic (seeded) so it's stable.
  const BORDER_EDGES = ['top', 'right', 'bottom', 'left'] as const;
  const interiorStart = Math.floor(count * 0.7);
  const halfW = dimensions.width * 0.5;
  const halfH = dimensions.height * 0.5;
  return Array.from({ length: count }, (_, index) => {
    const n = index + 1;
    const xNorm = deterministic01(n * 12.9898);
    const yNorm = deterministic01(n * 78.233);
    const disruption =
      shapeGrammar.puncta.disruption > 0
        ? Math.sin(n * 3.41) * shapeGrammar.puncta.disruption * Math.min(dimensions.width, dimensions.height) * 0.08
        : 0;
    let x: number;
    let y: number;
    let isBorder: boolean;
    let density: number;
    if (index < interiorStart) {
      // BORDER ring — distribute evenly across all four edges.
      const edge = BORDER_EDGES[index % BORDER_EDGES.length];
      const t = deterministic01(n * 41.17); // position along the edge 0..1
      const inset = 0.06;
      if (edge === 'top') {
        x = (t - 0.5) * dimensions.width * (1 - inset * 2);
        y = halfH - dimensions.height * inset + disruption;
      } else if (edge === 'bottom') {
        x = (t - 0.5) * dimensions.width * (1 - inset * 2);
        y = -halfH + dimensions.height * inset + disruption;
      } else if (edge === 'left') {
        x = -halfW + dimensions.width * inset + disruption;
        y = (t - 0.5) * dimensions.height * (1 - inset * 2);
      } else {
        x = halfW - dimensions.width * inset + disruption;
        y = (t - 0.5) * dimensions.height * (1 - inset * 2);
      }
      isBorder = true;
      density = shapeGrammar.puncta.freeDensity;
    } else {
      // INTERIOR sparse grain across the face.
      x = (xNorm - 0.5) * dimensions.width * 0.88;
      y = (yNorm - 0.5) * dimensions.height * 0.88;
      isBorder = false;
      density = shapeGrammar.puncta.attachmentDensity * 0.6;
    }
    return {
      key: `organ-point-${kind}-${index}`,
      position: [Number(x.toFixed(4)), Number(y.toFixed(4)), dimensions.thickness + 0.03] as [number, number, number],
      scale: Number((0.72 + ((index * 37) % 11) / 30).toFixed(4)),
      phase: Number((index * 0.47).toFixed(4)),
      edge: isBorder, // border puncta read brighter than interior grain (see OrganPointFieldSkin)
      density: Number(density.toFixed(4)),
    };
  });
}

function OrganPointFieldSkin({
  dimensions,
  focused,
  kind,
  material,
  reducedMotion,
  shapeGrammar,
  skin,
}: {
  dimensions: SurfaceDimensions;
  focused: boolean;
  kind: MaterializedTabKind;
  material: OrganMaterialState;
  reducedMotion: boolean;
  shapeGrammar: SurfaceShapeGrammar;
  skin: MaterializedSurfaceSkin;
}) {
  const pointRefs = useRef<THREE.Mesh[]>([]);
  const points = useMemo(() => makePointFieldPositions(dimensions, kind, shapeGrammar), [dimensions, kind, shapeGrammar]);
  const pointColor = useMemo(() => new THREE.Color(material.palette.point), [material.palette.point]);
  const liveColor = useMemo(() => new THREE.Color(material.palette.live), [material.palette.live]);

  useFrame((state) => {
    const baseOpacity = material.tissue.pointFieldOpacity * (0.48 + skin.nodeOpacity * 0.9) * (focused ? 1 : 0.78);
    pointRefs.current.forEach((point, index) => {
      if (!point) return;
      const spec = points[index];
      if (!spec) return;
      const pulse = reducedMotion ? 0.76 : 0.68 + 0.32 * (0.5 + 0.5 * Math.sin(state.clock.elapsedTime * 1.35 + spec.phase));
      const mat = point.material as THREE.MeshBasicMaterial;
      mat.color.copy(pointColor).lerp(liveColor, spec.edge ? 0.22 : 0.38);
      mat.opacity = Math.min(0.52, baseOpacity * pulse * (spec.edge ? 1.16 : 0.86) * (0.72 + spec.density));
      point.scale.setScalar(material.tissue.pointFieldScale * spec.scale * (0.72 + pulse * 0.24));
    });
  });

  return (
    <>
      {points.map((point, index) => (
        <mesh
          key={point.key}
          ref={(mesh) => {
            if (mesh) pointRefs.current[index] = mesh;
          }}
          position={point.position}
          renderOrder={11}
        >
          <sphereGeometry args={[0.0048, 8, 6]} />
          <meshBasicMaterial
            color={pointColor}
            transparent
            opacity={0}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      ))}
    </>
  );
}

function ReabsorbNode({
  position,
  color,
  disabled,
  onActivate,
}: {
  position: [number, number, number];
  color: string;
  disabled: boolean;
  onActivate: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <group
      position={position}
      scale={hovered && !disabled ? 1.16 : 1}
      onPointerOver={(event) => {
        event.stopPropagation();
        if (!disabled) setHovered(true);
      }}
      onPointerOut={(event) => {
        event.stopPropagation();
        setHovered(false);
      }}
      onClick={(event) => {
        event.stopPropagation();
        if (!disabled) onActivate();
      }}
    >
      <mesh renderOrder={15}>
        <sphereGeometry args={[0.027, 16, 12]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={disabled ? 0.18 : hovered ? 0.86 : 0.5}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      <mesh rotation={[Math.PI / 2, 0, 0]} renderOrder={14}>
        <torusGeometry args={[0.042, 0.0035, 8, 36]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={disabled ? 0.12 : hovered ? 0.48 : 0.24}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}

function makeOutcomeScarGeometry(width: number, height: number): THREE.BufferGeometry {
  const halfW = width * 0.5;
  const halfH = height * 0.5;
  const z = 0;
  const points = [
    -halfW * 0.38,
    halfH * 0.31,
    z,
    -halfW * 0.16,
    halfH * 0.1,
    z,
    halfW * 0.18,
    halfH * 0.22,
    z,
    halfW * 0.42,
    halfH * 0.02,
    z,
    -halfW * 0.34,
    -halfH * 0.16,
    z,
    -halfW * 0.08,
    -halfH * 0.36,
    z,
    halfW * 0.04,
    -halfH * 0.31,
    z,
    halfW * 0.35,
    -halfH * 0.15,
    z,
  ];
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
  return geometry;
}

function OutcomeImprintSkin({
  dimensions,
  focused,
  outcome,
  reducedMotion,
}: {
  dimensions: SurfaceDimensions;
  focused: boolean;
  outcome: OutcomeImprintSnapshot;
  reducedMotion: boolean;
}) {
  const haloRef = useRef<THREE.Mesh>(null);
  const scarRef = useRef<THREE.LineSegments>(null);
  const nodeRefs = useRef<THREE.Mesh[]>([]);
  const imprintColor = useMemo(() => new THREE.Color(outcome.tint), [outcome.tint]);
  const scarGeometry = useMemo(
    () => makeOutcomeScarGeometry(dimensions.width, dimensions.height),
    [dimensions.height, dimensions.width],
  );
  const nodePositions = useMemo(
    () =>
      [
        [-dimensions.width * 0.38, dimensions.height * 0.32, dimensions.thickness + 0.047],
        [dimensions.width * 0.39, dimensions.height * 0.28, dimensions.thickness + 0.047],
        [-dimensions.width * 0.34, -dimensions.height * 0.34, dimensions.thickness + 0.047],
        [dimensions.width * 0.36, -dimensions.height * 0.31, dimensions.thickness + 0.047],
      ] as [number, number, number][],
    [dimensions.height, dimensions.thickness, dimensions.width],
  );

  useEffect(() => {
    return () => scarGeometry.dispose();
  }, [scarGeometry]);

  useFrame((state) => {
    const focusWeight = focused ? 1 : 0.26;
    const phaseRate = outcome.kind === 'scar' ? 6.2 : outcome.kind === 'verified' ? 2.4 : 1.6;
    const wave = reducedMotion ? 0.72 : 0.72 + 0.28 * (0.5 + 0.5 * Math.sin(state.clock.elapsedTime * phaseRate));
    const live = outcome.intensity * focusWeight * wave;

    if (haloRef.current) {
      const mat = haloRef.current.material as THREE.MeshBasicMaterial;
      mat.color.copy(imprintColor);
      mat.opacity = Math.min(0.42, outcome.ringOpacity * live);
      const scalePulse = reducedMotion ? 1 : 1 + live * (outcome.kind === 'scar' ? 0.05 : 0.09);
      haloRef.current.scale.set(scalePulse * 1.16, scalePulse * 0.74, 1);
    }

    if (scarRef.current) {
      const mat = scarRef.current.material as THREE.LineBasicMaterial;
      mat.color.copy(imprintColor);
      mat.opacity = Math.min(0.56, outcome.scarOpacity * live);
    }

    nodeRefs.current.forEach((node, index) => {
      if (!node) return;
      const mat = node.material as THREE.MeshBasicMaterial;
      const stagger = reducedMotion ? 0.85 : 0.7 + 0.3 * (0.5 + 0.5 * Math.sin(state.clock.elapsedTime * phaseRate + index));
      mat.color.copy(imprintColor);
      mat.opacity = Math.min(0.62, Math.max(outcome.ringOpacity, outcome.scarOpacity) * live * stagger);
      node.scale.setScalar(outcome.kind === 'scar' ? 0.75 + live * 0.3 : 0.68 + live * 0.42);
    });
  });

  if (outcome.kind === 'none' || outcome.intensity <= 0.001) return null;

  return (
    <>
      <mesh ref={haloRef} position={[0, 0, dimensions.thickness + 0.048]} renderOrder={11}>
        <torusGeometry args={[Math.min(dimensions.width, dimensions.height) * 0.32, 0.004, 8, 76]} />
        <meshBasicMaterial
          color={imprintColor}
          transparent
          opacity={0}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      <lineSegments ref={scarRef} geometry={scarGeometry} position={[0, 0, dimensions.thickness + 0.052]} renderOrder={12}>
        <lineBasicMaterial color={imprintColor} transparent opacity={0} />
      </lineSegments>
      {nodePositions.map((position, index) => (
        <mesh
          key={`outcome-imprint-node-${index}`}
          ref={(node) => {
            if (node) nodeRefs.current[index] = node;
          }}
          position={position}
          renderOrder={12}
        >
          <sphereGeometry args={[0.0105, 10, 8]} />
          <meshBasicMaterial
            color={imprintColor}
            transparent
            opacity={0}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      ))}
    </>
  );
}

export default function MaterializedTab({
  tab,
  reducedMotion,
  focused = true,
  metabolism = REST_TURN_METABOLISM,
  outcome = REST_OUTCOME_IMPRINT,
  waitingIndex = 0,
  posture = BODY_POSTURES.rest,
}: {
  tab: MaterializedTabRecord;
  reducedMotion: boolean;
  focused?: boolean;
  metabolism?: TurnMetabolismSnapshot;
  outcome?: OutcomeImprintSnapshot;
  waitingIndex?: number;
  posture?: BodyPosture;
}) {
  const camera = useThree((state) => state.camera);
  const viewportWidth = useThree((state) => state.size.width);
  const viewportHeight = useThree((state) => state.size.height);
  const [approvalBusy, setApprovalBusy] = useState(false);
  const [revealedCount, setRevealedCount] = useState(0);
  const revealedCountRef = useRef(0);
  const revealTabIdRef = useRef<string | null>(null);
  const orientationRef = useRef<THREE.Group>(null);
  const slabRef = useRef<THREE.Group>(null);
  const tubeRef = useRef<THREE.Mesh>(null);
  const conductorCoreRefs = useRef<THREE.Mesh[]>([]);
  const conductorRefs = useRef<THREE.Mesh[]>([]);
  const rootNodeRef = useRef<THREE.Mesh>(null);
  const gripNodeRefs = useRef<THREE.Mesh[]>([]);
  const conductorBeadRefs = useRef<THREE.Mesh[]>([]);
  const conductorPunctaRefs = useRef<THREE.Mesh[]>([]);
  const bodyRef = useRef<THREE.Mesh>(null);
  const frameRef = useRef<THREE.LineSegments>(null);
  const labelRef = useRef<THREE.Object3D>(null);
  const beadRefs = useRef<THREE.Mesh[]>([]);

  const dimensions = SURFACE_DIMENSIONS[tab.kind];
  const metabolismColor = useMemo(() => new THREE.Color(metabolism.tint), [metabolism.tint]);
  const outcomeColor = useMemo(() => new THREE.Color(outcome.tint), [outcome.tint]);
  // Posture (spectral-v1): the surface tissue settles into the body's current hue,
  // blended OVER the canon palette as the TERMINAL step (after metabolism/outcome
  // transients). The luminous code <Text> stays canon for legibility.
  const postureColor = useMemo(() => {
    const [r, g, b] = postureColor01(posture.color);
    return new THREE.Color(r, g, b);
  }, [posture.color]);
  const bodyPostureTint = Math.min(
    0.8,
    posture.tint * POSTURE_DIAL.surfaceScale * (tab.kind === 'input' ? POSTURE_DIAL.inputBoost : 1),
  );
  // Points being (poster phase 4): the umbilical is a THIN glowing nerve FIBER
  // (the poster's delicate fiber-optic look), NOT a fat opaque pipe — the bright
  // traveling bead/packet carries the "fed by nerves" read, not tube bulk.
  const tubeRadius =
    tab.kind === 'input' ? BASE_TUBE_RADIUS * 0.8 : BASE_TUBE_RADIUS * (POINTS ? 0.4 : 0.52);
  // Points: the FOCUSED/attended tab faces the camera so the code you're reading
  // stays legible from any orbit angle (still anchored at its position by the
  // umbilical); waiting/orchestration tabs stay seated in-world. (operator option #2)
  const facesCamera = tab.kind === 'input' || (POINTS && focused);
  const isFocused = tab.kind === 'input' || focused;
  const pose = useMemo(
    () =>
      deriveMaterializedSurfacePose({
        kind: tab.kind,
        focused: isFocused,
        targetLocal: tab.targetLocal,
        waitingIndex,
        viewportWidth,
        viewportHeight,
        points: POINTS,
      }),
    [isFocused, tab.kind, tab.targetLocal, viewportHeight, viewportWidth, waitingIndex],
  );
  const skin = useMemo(
    () =>
      deriveMaterializedSurfaceSkin({
        kind: tab.kind,
        focused: isFocused,
        waitingIndex,
        metabolism,
        outcome,
      }),
    [isFocused, metabolism, outcome, tab.kind, waitingIndex],
  );
  const conductor = useMemo(
    () =>
      deriveVertebraConductorRoots({
        kind: tab.kind,
        lifecycle: tab.lifecycle,
        focused: isFocused,
        waitingIndex,
        originLocal: tab.originLocal,
        targetLocal: pose.targetLocal,
        surfaceWidth: dimensions.width,
        surfaceHeight: dimensions.height,
        metabolism,
        outcome,
      }),
    [
      dimensions.height,
      dimensions.width,
      isFocused,
      metabolism,
      outcome,
      pose.targetLocal,
      tab.lifecycle,
      tab.kind,
      tab.originLocal,
      waitingIndex,
    ],
  );
  const organMaterial = useMemo(
    () =>
      deriveOrganMaterialState({
        kind: tab.kind,
        lifecycle: tab.lifecycle,
        focused: isFocused,
        waitingIndex,
        metabolism,
        outcome,
        actuator: conductor.actuator,
      }),
    [conductor.actuator, isFocused, metabolism, outcome, tab.kind, tab.lifecycle, waitingIndex],
  );
  const shapeGrammar = useMemo(
    () =>
      deriveSurfaceShapeGrammar({
        kind: tab.kind,
        lifecycle: tab.lifecycle,
        focused: isFocused,
        waitingIndex,
        role: organMaterial.role,
        originLocal: tab.originLocal,
        targetLocal: pose.targetLocal,
        dimensions,
        rootGripCount: conductor.gripNodes.length,
        actuator: conductor.actuator,
      }),
    [
      conductor.actuator,
      conductor.gripNodes.length,
      dimensions,
      isFocused,
      organMaterial.role,
      pose.targetLocal,
      tab.kind,
      tab.lifecycle,
      tab.originLocal,
      waitingIndex,
    ],
  );
  const theme = useMemo(() => toSurfaceTheme(organMaterial), [organMaterial]);
  const rootCoreColor = useMemo(() => new THREE.Color('#010308'), []);
  const conductorTint = useMemo(() => new THREE.Color(conductor.actuator.tint), [conductor.actuator.tint]);
  const conductorSecondaryTint = useMemo(
    () => new THREE.Color(conductor.actuator.secondaryTint),
    [conductor.actuator.secondaryTint],
  );

  const curve = useMemo(() => {
    const origin = new THREE.Vector3(...tab.originLocal);
    const target = new THREE.Vector3(...pose.targetLocal);
    const delta = target.clone().sub(origin);

    if (tab.kind === 'input') {
      const midA = origin.clone().add(delta.clone().multiplyScalar(0.34)).add(new THREE.Vector3(0, 0.08, 0.03));
      const midB = origin.clone().add(delta.clone().multiplyScalar(0.76)).add(new THREE.Vector3(0.02, 0.04, 0.02));
      return new THREE.CatmullRomCurve3([origin, midA, midB, target]);
    }

    const midA = origin.clone().add(delta.clone().multiplyScalar(0.3)).add(new THREE.Vector3(0.05, 0.01, 0.02));
    const midB = origin.clone().add(delta.clone().multiplyScalar(0.78)).add(new THREE.Vector3(0.02, 0.01, 0.01));
    return new THREE.CatmullRomCurve3([origin, midA, midB, target]);
  }, [pose.targetLocal, tab.kind, tab.originLocal]);

  const tubeGeometry = useMemo(
    () => new THREE.TubeGeometry(curve, UMBILICAL_SEGMENTS, tubeRadius, UMBILICAL_RADIAL_SEGMENTS, false),
    [curve, tubeRadius],
  );
  const conductorCurves = useMemo(
    () =>
      conductor.roots.map(
        (root) =>
          new THREE.CatmullRomCurve3([
            new THREE.Vector3(...root.start),
            new THREE.Vector3(...root.midA),
            new THREE.Vector3(...root.midB),
            new THREE.Vector3(...root.end),
          ]),
      ),
    [conductor.roots],
  );
  const conductorGeometries = useMemo(
    () =>
      conductorCurves.map(
        (rootCurve, index) =>
          new THREE.TubeGeometry(
            rootCurve,
            CONDUCTOR_SEGMENTS,
            conductor.roots[index]?.radius ?? 0.003,
            CONDUCTOR_RADIAL_SEGMENTS,
            false,
          ),
      ),
    [conductor.roots, conductorCurves],
  );
  const slabShape = useMemo(
    () => makeAnatomicalSurfaceShape(dimensions.width, dimensions.height, dimensions.radius, shapeGrammar),
    [dimensions.height, dimensions.radius, dimensions.width, shapeGrammar],
  );
  const slabShapeGeometry = useMemo(() => new THREE.ShapeGeometry(slabShape, 24), [slabShape]);
  const slabBodyGeometry = useMemo(
    () => new THREE.ExtrudeGeometry(slabShape, { depth: dimensions.thickness, bevelEnabled: false, steps: 1 }),
    [dimensions.thickness, slabShape],
  );
  const slabFrameGeometry = useMemo(() => new THREE.EdgesGeometry(slabShapeGeometry), [slabShapeGeometry]);

  useEffect(() => {
    return () => {
      tubeGeometry.dispose();
      conductorGeometries.forEach((geometry) => geometry.dispose());
      slabBodyGeometry.dispose();
      slabShapeGeometry.dispose();
      slabFrameGeometry.dispose();
    };
  }, [conductorGeometries, slabBodyGeometry, slabFrameGeometry, slabShapeGeometry, tubeGeometry]);

  useEffect(() => {
    if (tab.kind !== 'approval') {
      setApprovalBusy(false);
    }
  }, [tab.kind, tab.approval?.token]);

  useFrame((state) => {
    const now = performance.now();
    const phaseRate =
      metabolism.phase === 'error'
        ? 7.2
        : metabolism.phase === 'working'
          ? 4.4
          : metabolism.phase === 'thinking'
            ? 2.8
            : metabolism.phase === 'approval'
              ? 1.2
              : 1.8;
    const phaseWave = reducedMotion ? 0.42 : 0.78 + 0.22 * (0.5 + 0.5 * Math.sin(state.clock.elapsedTime * phaseRate));
    const surfaceExcitation = metabolism.surfaceExcitation * (isFocused ? 1 : 0.35) * phaseWave;
    const rootExcitation = metabolism.rootExcitation * (isFocused ? 1 : 0.34) * phaseWave;
    const imprintWave =
      reducedMotion || outcome.kind === 'none'
        ? 0.72
        : 0.7 +
          0.3 *
            (0.5 +
              0.5 *
                Math.sin(state.clock.elapsedTime * (outcome.kind === 'scar' ? 6.2 : outcome.kind === 'verified' ? 2.4 : 1.6)));
    const imprintFocus = tab.kind === 'input' ? 0 : isFocused ? 1 : 0.28;
    const outcomeSurfaceExcitation = outcome.surfaceGlow * imprintFocus * imprintWave;
    const outcomeRootExcitation = outcome.rootGlow * imprintFocus * imprintWave;
    const bodyMetabolismMix = organMaterial.role === 'scar' ? 0.06 : 0.2;
    const bodyOutcomeMix = organMaterial.role === 'scar' ? 0.045 : 0.14;
    const actuator = conductor.actuator;
    const actuatorPulse =
      reducedMotion || actuator.role === 'resting'
        ? 0.78
        : 0.68 + 0.32 * (0.5 + 0.5 * Math.sin(state.clock.elapsedTime * actuator.pulseRate + actuator.tension * 2.1));
    const actuatorTintMix = clamp01(
      0.34 + actuator.tension * 0.28 + rootExcitation * 0.22 + outcomeRootExcitation * 0.32,
    );

    if (reducedMotion) {
      if (tab.lifecycle === 'retracting') {
        clearMaterializedTab(tab.id);
        return;
      }
      if (tab.lifecycle !== 'live') {
        setMaterializedTabLifecycle(tab.id, 'live', now);
      }
    }

    let reachProgress = 1;
    let slabProgress = 1;
    let liveProgress = 1;

    if (!reducedMotion) {
      const elapsed = now - tab.phaseStartedAt;
      if (tab.lifecycle === 'reaching') {
        reachProgress = clamp01(elapsed / REACH_DURATION_MS);
        slabProgress = 0;
        liveProgress = 0;
        if (reachProgress >= 1) {
          setMaterializedTabLifecycle(tab.id, 'unfurling', now);
        }
      } else if (tab.lifecycle === 'unfurling') {
        reachProgress = 1;
        slabProgress = clamp01(elapsed / UNFURL_DURATION_MS);
        liveProgress = slabProgress;
        if (slabProgress >= 1) {
          setMaterializedTabLifecycle(tab.id, 'live', now);
        }
      } else if (tab.lifecycle === 'retracting') {
        // Points being: a slower retract so the slab visibly dissolves while the
        // reabsorption motes stream up the spine (poster phase 7).
        const retractProgress = clamp01(elapsed / (POINTS ? 1300 : RETRACT_DURATION_MS));
        reachProgress = 1 - retractProgress;
        slabProgress = 1 - retractProgress;
        liveProgress = 1 - retractProgress;
        if (retractProgress >= 1) {
          clearMaterializedTab(tab.id);
          return;
        }
      }
    }

    if (tubeRef.current) {
      const geometry = tubeRef.current.geometry;
      const drawCount = geometry.getIndex()?.count ?? geometry.getAttribute('position').count;
      geometry.setDrawRange(0, Math.max(2, Math.floor(drawCount * Math.max(reachProgress, 0.03))));
      const mat = tubeRef.current.material as THREE.MeshStandardMaterial;
      mat.color.copy(theme.reach).lerp(theme.live, liveProgress).lerp(metabolismColor, surfaceExcitation * 0.28);
      mat.emissive.copy(theme.reach).lerp(theme.live, liveProgress).lerp(metabolismColor, surfaceExcitation * 0.44);
      // Points being: brighten the umbilical so it reads as a bright cord (poster).
      const workspaceFeed = tab.kind === 'input' ? 1 : POINTS ? 0.72 : 0.38;
      mat.color.lerp(outcomeColor, outcomeSurfaceExcitation * 0.26);
      mat.emissive.lerp(outcomeColor, outcomeSurfaceExcitation * 0.36);
      mat.color.lerp(postureColor, bodyPostureTint);
      mat.emissive.lerp(postureColor, bodyPostureTint);
      mat.emissiveIntensity =
        (tab.kind === 'input' ? 1.1 : 0.64 + liveProgress * 0.38) *
        pose.tubeOpacity *
        workspaceFeed *
        (1 + surfaceExcitation * 0.62 + outcomeSurfaceExcitation * 0.42);
      mat.opacity = Math.min(
        0.98,
        (0.3 + Math.max(reachProgress, slabProgress) * 0.64) *
          pose.tubeOpacity *
          workspaceFeed *
          (1 + surfaceExcitation * 0.28 + outcomeSurfaceExcitation * 0.22),
      );
    }

    conductorRefs.current.forEach((mesh, index) => {
      if (!mesh) return;
      const root = conductor.roots[index];
      if (!root) return;
      const geometry = mesh.geometry;
      const drawCount = geometry.getIndex()?.count ?? geometry.getAttribute('position').count;
      geometry.setDrawRange(0, Math.max(2, Math.floor(drawCount * Math.max(reachProgress, 0.03))));
      const mat = mesh.material as THREE.MeshBasicMaterial;
      mat.color
        .copy(theme.reach)
        .lerp(conductorSecondaryTint, root.textureMix)
        .lerp(conductorTint, actuatorTintMix)
        .lerp(metabolismColor, rootExcitation * 0.28);
      mat.color.lerp(outcomeColor, outcomeRootExcitation * 0.72);
      mat.opacity = Math.min(
        0.48,
        root.opacity *
          pose.tubeOpacity *
          organMaterial.tissue.rootGripGain *
          (0.24 + Math.max(reachProgress, slabProgress) * 0.76) *
          (0.86 + actuatorPulse * 0.24 + rootExcitation * 0.45 + outcomeRootExcitation * 0.42),
      );
    });

    conductorCoreRefs.current.forEach((mesh, index) => {
      if (!mesh) return;
      const root = conductor.roots[index];
      if (!root) return;
      const geometry = mesh.geometry;
      const drawCount = geometry.getIndex()?.count ?? geometry.getAttribute('position').count;
      geometry.setDrawRange(0, Math.max(2, Math.floor(drawCount * Math.max(reachProgress, 0.03))));
      const mat = mesh.material as THREE.MeshStandardMaterial;
      mat.color.copy(rootCoreColor).lerp(conductorTint, 0.08 + root.textureMix * 0.18);
      mat.emissive.copy(conductorSecondaryTint).lerp(conductorTint, 0.62);
      mat.emissiveIntensity =
        Math.min(0.72, 0.1 + root.tension * 0.24 + rootExcitation * 0.32 + outcomeRootExcitation * 0.28) *
        organMaterial.tissue.rootGripGain *
        pose.tubeOpacity *
        (0.74 + actuatorPulse * 0.26);
      mat.opacity = Math.min(
        0.36,
        root.opacity *
          pose.tubeOpacity *
          (0.44 + Math.max(reachProgress, slabProgress) * 0.42) *
          (0.8 + root.stiffness * 0.22),
      );
    });

    if (rootNodeRef.current) {
      const mat = rootNodeRef.current.material as THREE.MeshBasicMaterial;
      mat.color.copy(conductorTint).lerp(conductorSecondaryTint, 0.16);
      mat.opacity = Math.min(
        0.52,
        conductor.nodeOpacity * pose.tubeOpacity * organMaterial.tissue.rootGripGain * (0.74 + actuatorPulse * 0.32),
      );
      rootNodeRef.current.scale.setScalar(0.76 + actuator.tension * 0.36 + actuatorPulse * 0.1);
    }

    gripNodeRefs.current.forEach((node, index) => {
      if (!node) return;
      const root = conductor.roots[index];
      if (!root) return;
      const mat = node.material as THREE.MeshBasicMaterial;
      mat.color.copy(conductorTint).lerp(conductorSecondaryTint, root.textureMix * 0.38);
      mat.opacity = Math.min(
        0.58,
        conductor.nodeOpacity * pose.tubeOpacity * organMaterial.tissue.rootGripGain * 0.86 * (0.72 + actuatorPulse * 0.36),
      );
      node.scale.setScalar(root.clampScale * (0.84 + actuatorPulse * 0.08));
    });

    const slabT =
      tab.lifecycle === 'reaching' || tab.lifecycle === 'retracting'
        ? clamp01(Math.max(reachProgress, 0.04))
        : 1;

    // orientationRef carries the slab POSITION *and* the optional camera-facing, so
    // the tab rotates IN PLACE at the umbilical endpoint. (Facing the camera by
    // rotating a group parked at the origin swung the offset slab OFF the nerve —
    // the visible gap.) No scale on this node = no shear; slabRef does scale only.
    // The umbilical ends at the same point, so the nerve stays plugged in as the
    // tab turns to face you.
    if (orientationRef.current) {
      orientationRef.current.position.copy(curve.getPointAt(slabT));
      if (facesCamera) orientationRef.current.lookAt(camera.position);
    }

    if (slabRef.current) {
      const eased = easing(slabProgress);
      slabRef.current.scale.set(
        (0.74 + eased * 0.26) * pose.scale * POINTS_SLAB_SCALE,
        Math.max(0.01, eased) * pose.scale * POINTS_SLAB_SCALE,
        (0.7 + eased * 0.3) * pose.scale * POINTS_SLAB_SCALE,
      );
    }

    if (bodyRef.current) {
      const mat = bodyRef.current.material as THREE.MeshStandardMaterial;
      mat.opacity =
        (skin.bodyBaseOpacity + slabProgress * (skin.bodyLiveOpacity - skin.bodyBaseOpacity)) *
        pose.opacity *
        organMaterial.tissue.bodyOpacityScale;
      mat.roughness = organMaterial.tissue.roughness;
      mat.metalness = organMaterial.tissue.metalness;
      if (tab.kind === 'approval') {
        mat.emissive.copy(theme.frame).lerp(metabolismColor, surfaceExcitation * 0.18);
        mat.emissive.lerp(outcomeColor, outcomeSurfaceExcitation * (organMaterial.role === 'scar' ? 0.04 : 0.12));
        mat.emissive.lerp(postureColor, bodyPostureTint);
        mat.emissiveIntensity =
          skin.emissiveIntensity *
          (0.55 + slabProgress * 0.45) *
          pose.opacity *
          organMaterial.tissue.emissiveGain *
          (1 + surfaceExcitation * 0.14 + outcomeSurfaceExcitation * 0.12);
      } else {
        if (tab.kind === 'input') {
          mat.emissive.copy(theme.reach).lerp(theme.live, liveProgress * 0.9).lerp(metabolismColor, surfaceExcitation * 0.18);
        } else {
          mat.emissive.copy(theme.frame).lerp(metabolismColor, surfaceExcitation * bodyMetabolismMix);
        }
        mat.emissive.lerp(outcomeColor, outcomeSurfaceExcitation * bodyOutcomeMix);
        mat.emissive.lerp(postureColor, bodyPostureTint);
        mat.emissiveIntensity =
          skin.emissiveIntensity *
          (0.55 + slabProgress * 0.45) *
          pose.opacity *
          organMaterial.tissue.emissiveGain *
          (1 + surfaceExcitation * 0.14 + outcomeSurfaceExcitation * 0.12);
      }
      // Points being: read as DARK near-black GLASS (not a heavy teal fill).
      if (POINTS) {
        mat.opacity *= 0.42;
        mat.emissiveIntensity *= 0.22;
        mat.roughness = 0.12;
        mat.metalness = 0.3;
      }
    }

    if (frameRef.current) {
      const mat = frameRef.current.material as THREE.LineBasicMaterial;
      mat.color.copy(theme.frame).lerp(metabolismColor, surfaceExcitation * 0.22);
      mat.color.lerp(outcomeColor, outcomeSurfaceExcitation * 0.42);
      mat.opacity =
        (skin.frameBaseOpacity + slabProgress * (skin.frameLiveOpacity - skin.frameBaseOpacity)) *
        organMaterial.tissue.frameOpacityScale *
        pose.opacity *
        (1 + surfaceExcitation * 0.42 + outcomeSurfaceExcitation * 0.46);
      // Points being: a THIN glowing neon edge (spectral cyan).
      if (POINTS) {
        mat.color.set('#36d6ff');
        mat.opacity = Math.min(0.95, mat.opacity * 3.2 + 0.4);
      }
    }

    if (labelRef.current) {
      labelRef.current.scale.setScalar(0.96 + slabProgress * 0.04);
    }

    // WORKING (poster phase 6): "live state flows through the nerves" — the
    // umbilical beads RACE faster while the being works (surfaceExcitation is the
    // metabolic working signal), accentuated on the single points-mode cord.
    const beadFlowSpeed = 0.28 + surfaceExcitation * (POINTS ? 0.7 : 0.4);
    const beadTravel = (state.clock.elapsedTime * beadFlowSpeed) % 1;
    beadRefs.current.forEach((bead, index) => {
      if (!bead) return;
      const t = clamp01((beadTravel + index * 0.19) % 1);
      const pathT = clamp01(0.08 + t * 0.84 * Math.max(reachProgress, 0.24));
      bead.position.copy(curve.getPointAt(pathT));
      bead.scale.setScalar(tab.kind === 'input' ? 0.38 + liveProgress * 0.5 : 0.28 + liveProgress * 0.34);
      const mat = bead.material as THREE.MeshBasicMaterial;
      mat.color.copy(theme.reach).lerp(theme.live, liveProgress).lerp(metabolismColor, surfaceExcitation * 0.45);
      mat.color.lerp(outcomeColor, outcomeSurfaceExcitation * 0.42);
      mat.opacity = Math.min(
        0.96,
        (0.24 + liveProgress * 0.68) *
          pose.tubeOpacity *
          (tab.kind === 'input' ? 1 : POINTS ? 0.7 : 0.46) *
          (1 + surfaceExcitation * 0.5 + outcomeSurfaceExcitation * 0.42),
      );
    });

    conductorBeadRefs.current.forEach((bead, index) => {
      if (!bead || conductorCurves.length === 0) return;
      const rootIndex = index % conductorCurves.length;
      const root = conductor.roots[rootIndex];
      const rootCurve = conductorCurves[rootIndex];
      if (!root || !rootCurve) return;
      const t = reducedMotion ? 0.86 : (state.clock.elapsedTime * Math.max(root.beadSpeed, 0.03) + root.beadOffset) % 1;
      const flowT =
        root.flow === 'return'
          ? 1 - t
          : root.flow === 'bidirectional'
            ? 0.5 + 0.46 * Math.sin(t * TAU + root.beadOffset * TAU)
            : t;
      const pathT = clamp01(0.08 + clamp01(flowT) * 0.84 * Math.max(reachProgress, 0.25));
      bead.position.copy(rootCurve.getPointAt(pathT));
      bead.scale.setScalar((0.3 + root.tension * 0.16 + liveProgress * (isFocused ? 0.5 : 0.22)) * (0.88 + actuatorPulse * 0.16));
      const mat = bead.material as THREE.MeshBasicMaterial;
      mat.color
        .copy(theme.reach)
        .lerp(conductorSecondaryTint, root.textureMix * 0.8)
        .lerp(conductorTint, 0.54 + root.tension * 0.28)
        .lerp(metabolismColor, rootExcitation * 0.32);
      mat.color.lerp(outcomeColor, outcomeRootExcitation * 0.76);
      mat.opacity = Math.min(
        0.62,
        root.opacity *
          pose.tubeOpacity *
          organMaterial.tissue.rootGripGain *
          (0.42 + liveProgress * 0.36) *
          (0.86 + actuatorPulse * 0.28 + rootExcitation * 0.55 + outcomeRootExcitation * 0.5),
      );
    });

    conductorPunctaRefs.current.forEach((punctum, index) => {
      if (!punctum || conductorCurves.length === 0) return;
      const rootIndex = Math.floor(index / CONDUCTOR_PUNCTA_PER_ROOT);
      const punctaIndex = index % CONDUCTOR_PUNCTA_PER_ROOT;
      const root = conductor.roots[rootIndex];
      const rootCurve = conductorCurves[rootIndex];
      if (!root || !rootCurve) return;

      const base = (punctaIndex + 1) / (CONDUCTOR_PUNCTA_PER_ROOT + 1);
      const drift =
        reducedMotion || root.role === 'holding'
          ? 0
          : Math.sin(state.clock.elapsedTime * (root.beadSpeed * 2.3 + 0.18) + root.beadOffset * TAU + punctaIndex) * 0.045;
      const direction = root.flow === 'return' ? -1 : 1;
      const pathT = clamp01(0.08 + clamp01(base + drift * direction) * 0.84 * Math.max(reachProgress, 0.25));
      punctum.position.copy(rootCurve.getPointAt(pathT));
      punctum.scale.setScalar(
        (0.36 + root.textureMix * 0.58 + root.tension * 0.28) *
          (0.78 + actuatorPulse * 0.26) *
          (root.role === 'sensing' ? 0.72 : 1),
      );
      const mat = punctum.material as THREE.MeshBasicMaterial;
      mat.color
        .copy(theme.reach)
        .lerp(conductorSecondaryTint, root.textureMix)
        .lerp(conductorTint, 0.46 + root.tension * 0.26)
        .lerp(metabolismColor, rootExcitation * 0.24)
        .lerp(outcomeColor, outcomeRootExcitation * 0.62);
      mat.opacity = Math.min(
        root.role === 'sensing' ? 0.32 : 0.58,
        root.opacity *
          pose.tubeOpacity *
          organMaterial.tissue.rootGripGain *
          (0.64 + actuatorPulse * 0.34) *
          (0.82 + root.tension * 0.22 + rootExcitation * 0.4 + outcomeRootExcitation * 0.38),
      );
    });
  });

  const interactive = tab.lifecycle === 'live';
  const headerLabel = getSurfaceHeader(tab);
  const footerLabel = getSurfaceFooter(tab);
  const code = tab.content?.code ?? '';
  const inputText = tab.input?.text?.trim() ?? '';
  const approvalText = getApprovalBody(tab.approval);
  const buttonDisabled = !interactive || approvalBusy;
  const inputDisplay = inputText ? `${inputText}▌` : '▌';
  const contentPreview = useMemo(
    () => formatMaterializedTextPreview(code, { maxLines: CONTENT_PREVIEW_LINES, maxCharsPerLine: CONTENT_PREVIEW_CHARS }),
    [code],
  );
  const approvalPreview = useMemo(
    () =>
      formatMaterializedTextPreview(approvalText, {
        maxLines: APPROVAL_PREVIEW_LINES,
        maxCharsPerLine: APPROVAL_PREVIEW_CHARS,
      }),
    [approvalText],
  );
  const contentOverflowLabel =
    contentPreview.hiddenLines > 0 ? `+${contentPreview.hiddenLines} more lines` : footerLabel;
  const approvalOverflowLabel =
    approvalPreview.hiddenLines > 0 ? `+${approvalPreview.hiddenLines} more lines` : footerLabel;

  // Keep revealedCountRef in sync so the reveal effect can read current count
  // without depending on the state value (which would cause re-fires).
  useEffect(() => { revealedCountRef.current = revealedCount; }, [revealedCount]);

  // Work-streaming (demoplan "Showing Work"): the content code reveals LINE BY LINE
  // as the being writes it, with a cursor on the active line. Reduced motion shows
  // it whole. On a new surface (different tab.id) the reveal starts from line 1;
  // when the SAME surface grows (streaming chunks), we continue from the current
  // revealed position — no per-chunk snap-back to line 1.
  useEffect(() => {
    const total = contentPreview.lines.length;
    if (tab.kind !== 'content' || total === 0) {
      setRevealedCount(0);
      revealTabIdRef.current = null;
      return undefined;
    }
    if (reducedMotion) {
      setRevealedCount(total);
      revealTabIdRef.current = tab.id;
      return undefined;
    }
    // New surface (different tab.id) → start from top.
    // Same surface that grew (streaming) → continue from where we are.
    const isNewSurface = revealTabIdRef.current !== tab.id;
    let n = isNewSurface
      ? 1
      : Math.min(Math.max(revealedCountRef.current, 1), total);
    revealTabIdRef.current = tab.id;
    setRevealedCount(n);
    if (n >= total) return undefined;
    const id = window.setInterval(() => {
      n += 1;
      setRevealedCount(n);
      if (n >= total) window.clearInterval(id);
    }, 90);
    return () => window.clearInterval(id);
  }, [contentPreview.lines.length, tab.id, tab.kind, reducedMotion]);

  const handleApprove = async () => {
    if (buttonDisabled) return;
    setApprovalBusy(true);
    try {
      await approvePendingApproval();
    } finally {
      setApprovalBusy(false);
    }
  };

  const handleReject = async () => {
    if (buttonDisabled) return;
    setApprovalBusy(true);
    try {
      await rejectPendingApproval();
    } finally {
      setApprovalBusy(false);
    }
  };

  return (
    <group
      onClick={(event) => {
        if (tab.kind === 'input') return;
        event.stopPropagation();
        focusMaterializedTab(tab.id);
      }}
    >
      <mesh ref={tubeRef} geometry={tubeGeometry} renderOrder={6} frustumCulled={false}>
        <meshStandardMaterial
          color={theme.reach.clone()}
          emissive={theme.reach.clone()}
          emissiveIntensity={1.02}
          roughness={0.18}
          metalness={0.22}
          transparent
          opacity={0.92}
        />
      </mesh>

      {/* Points being: keep ONLY the main umbilical (tubeRef above); drop the
          per-root tube fan + all the node/bead/puncta dots so the nerve reads
          as one clean filament (poster look). */}
      {!POINTS && (
      <>
      {conductorGeometries.map((geometry, index) => (
        <mesh
          key={`vertebra-conductor-core-${tab.id}-${conductor.roots[index]?.id ?? index}`}
          ref={(mesh) => {
            if (mesh) conductorCoreRefs.current[index] = mesh;
          }}
          geometry={geometry}
          renderOrder={4}
          frustumCulled={false}
        >
          <meshStandardMaterial
            color="#010308"
            emissive={conductor.actuator.secondaryTint}
            emissiveIntensity={0.18}
            roughness={0.24}
            metalness={0.12}
            transparent
            opacity={Math.min(0.28, (conductor.roots[index]?.opacity ?? 0) * 0.72)}
            depthWrite={false}
          />
        </mesh>
      ))}

      {conductorGeometries.map((geometry, index) => (
        <mesh
          key={`vertebra-conductor-${tab.id}-${conductor.roots[index]?.id ?? index}`}
          ref={(mesh) => {
            if (mesh) conductorRefs.current[index] = mesh;
          }}
          geometry={geometry}
          renderOrder={5}
          frustumCulled={false}
        >
          <meshBasicMaterial
            color={theme.reach.clone()}
            transparent
            opacity={conductor.roots[index]?.opacity ?? 0}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      ))}

      {conductor.rootNode ? (
        <mesh ref={rootNodeRef} position={conductor.rootNode} renderOrder={6}>
          <sphereGeometry args={[0.018, 12, 10]} />
          <meshBasicMaterial
            color={conductor.actuator.tint}
            transparent
            opacity={conductor.nodeOpacity * pose.tubeOpacity}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      ) : null}

      {conductor.gripNodes.map((position, index) => (
        <mesh
          key={`vertebra-grip-${tab.id}-${index}`}
          ref={(mesh) => {
            if (mesh) gripNodeRefs.current[index] = mesh;
          }}
          position={position}
          renderOrder={6}
        >
          <sphereGeometry args={[0.013, 10, 8]} />
          <meshBasicMaterial
            color={conductor.roots[index]?.tint ?? conductor.actuator.tint}
            transparent
            opacity={conductor.nodeOpacity * pose.tubeOpacity * 0.86}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      ))}

      {Array.from({ length: Math.min(CONDUCTOR_BEAD_COUNT, conductor.roots.length) }, (_, index) => (
        <mesh
          key={`vertebra-conductor-bead-${tab.id}-${index}`}
          ref={(mesh) => {
            if (mesh) conductorBeadRefs.current[index] = mesh;
          }}
          renderOrder={7}
        >
          <sphereGeometry args={[0.0105, 10, 8]} />
          <meshBasicMaterial
            color={conductor.roots[index]?.tint ?? conductor.actuator.tint}
            transparent
            opacity={(conductor.roots[index]?.opacity ?? 0) * pose.tubeOpacity}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      ))}

      {conductor.roots.flatMap((root, rootIndex) =>
        Array.from({ length: CONDUCTOR_PUNCTA_PER_ROOT }, (_, punctaIndex) => {
          const index = rootIndex * CONDUCTOR_PUNCTA_PER_ROOT + punctaIndex;
          return (
            <mesh
              key={`vertebra-root-puncta-${tab.id}-${root.id}-${punctaIndex}`}
              ref={(mesh) => {
                if (mesh) conductorPunctaRefs.current[index] = mesh;
              }}
              renderOrder={7}
            >
              <sphereGeometry args={[0.0085, 8, 6]} />
              <meshBasicMaterial
                color={root.tint}
                transparent
                opacity={0}
                blending={THREE.AdditiveBlending}
                depthWrite={false}
              />
            </mesh>
          );
        }),
      )}
      </>
      )}

      {Array.from({ length: BEAD_COUNT }, (_, index) => (
        <mesh
          key={`materialized-bead-${tab.id}-${index}`}
          ref={(mesh) => {
            if (mesh) beadRefs.current[index] = mesh;
          }}
          renderOrder={7}
        >
          <sphereGeometry args={[0.015, 12, 12]} />
          <meshBasicMaterial color={theme.reach.clone()} transparent opacity={0.76} />
        </mesh>
      ))}

      <group ref={orientationRef}>
        <group ref={slabRef}>
          <group rotation={dimensions.tilt}>
            <mesh ref={bodyRef} renderOrder={8}>
              <primitive object={slabBodyGeometry} attach="geometry" />
              <meshStandardMaterial
                color={theme.body}
                emissive={theme.outline}
                emissiveIntensity={0.08}
                roughness={organMaterial.tissue.roughness}
                metalness={organMaterial.tissue.metalness}
                transparent
                opacity={0.92}
              />
            </mesh>
            <lineSegments
              ref={frameRef}
              geometry={slabFrameGeometry}
              position={[0, 0, dimensions.thickness + 0.001]}
              renderOrder={9}
            >
              <lineBasicMaterial color={theme.frame.clone()} transparent opacity={0.7} />
            </lineSegments>
            {/* Points being: drop the membrane veins/dots + surface point-field
                dots so the slab reads as clean dark glass (poster look). */}
            {!POINTS && (
              <>
                <LivingMembraneSkin
                  dimensions={dimensions}
                  kind={tab.kind}
                  material={organMaterial}
                  metabolism={metabolism}
                  outcome={outcome}
                  shapeGrammar={shapeGrammar}
                  skin={skin}
                  surfaceGeometry={slabShapeGeometry}
                  theme={theme}
                />
                <OrganPointFieldSkin
                  dimensions={dimensions}
                  focused={isFocused}
                  kind={tab.kind}
                  material={organMaterial}
                  reducedMotion={reducedMotion}
                  shapeGrammar={shapeGrammar}
                  skin={skin}
                />
              </>
            )}
            {/* Points being (poster phase 4): the tab is BUILT FROM POINTS — render
                the point-field skin (dotted-particle border on all 4 edges + sparse
                interior grain) so the slab reads as one organism with the brain.
                Body stays dark glass so the puncta dominate. */}
            {POINTS && tab.kind !== 'input' && (
              <OrganPointFieldSkin
                dimensions={dimensions}
                focused={isFocused}
                kind={tab.kind}
                material={organMaterial}
                reducedMotion={reducedMotion}
                shapeGrammar={shapeGrammar}
                skin={skin}
              />
            )}
            {tab.kind !== 'input' ? (
              <OutcomeImprintSkin
                dimensions={dimensions}
                focused={isFocused}
                outcome={outcome}
                reducedMotion={reducedMotion}
              />
            ) : null}

            {tab.kind === 'input' ? (
              <>
                <mesh position={[0, 0, dimensions.thickness + 0.006]} scale={[0.84, 0.56, 1]} renderOrder={9}>
                  <primitive object={slabShapeGeometry} attach="geometry" />
                  <meshBasicMaterial color={theme.plate} transparent opacity={skin.plateOpacity * organMaterial.tissue.plateOpacityScale} />
                </mesh>
                <Text
                  ref={labelRef}
                  position={[0, dimensions.height * 0.34, dimensions.thickness + 0.02]}
                  color={theme.header}
                  fontSize={0.036}
                  maxWidth={dimensions.width * 0.76}
                  anchorX="center"
                  anchorY="middle"
                  outlineWidth={0.003}
                  outlineColor={theme.outline}
                  renderOrder={10}
                >
                  {headerLabel}
                </Text>
                <Text
                  position={[-dimensions.width * 0.36, 0, dimensions.thickness + 0.022]}
                  color={theme.text}
                  fontSize={0.07}
                  maxWidth={dimensions.width * 0.72}
                  lineHeight={1.14}
                  anchorX="left"
                  anchorY="middle"
                  textAlign="left"
                  outlineWidth={0.004}
                  outlineColor={theme.outline}
                  renderOrder={10}
                >
                  {inputDisplay}
                </Text>
                <Text
                  position={[0, -dimensions.height * 0.34, dimensions.thickness + 0.02]}
                  color={theme.accent}
                  fontSize={0.03}
                  anchorX="center"
                  anchorY="middle"
                  outlineWidth={0.002}
                  outlineColor={theme.outline}
                  renderOrder={10}
                >
                  {footerLabel}
                </Text>
              </>
            ) : tab.kind === 'content' ? (
              <>
                <mesh position={[0, -0.01, dimensions.thickness + 0.006]} scale={[0.88, 0.72, 1]} renderOrder={9}>
                  <primitive object={slabShapeGeometry} attach="geometry" />
                  {/* Points: a solid dark backing so the luminous code READS (the
                      dark-glass body alone let the starfield bleed through). */}
                  <meshBasicMaterial color={theme.plate} transparent opacity={POINTS ? 0.82 : skin.plateOpacity * organMaterial.tissue.plateOpacityScale} />
                </mesh>
                <mesh position={[0, dimensions.height * 0.31, dimensions.thickness + 0.008]} renderOrder={9}>
                  <planeGeometry args={[dimensions.width * 0.78, dimensions.height * 0.1]} />
                  <meshBasicMaterial
                    color={theme.frame}
                    transparent
                    opacity={skin.headerBandOpacity * organMaterial.tissue.headerOpacityScale}
                  />
                </mesh>
                <Text
                  ref={labelRef}
                  position={[0, dimensions.height * 0.38, dimensions.thickness + 0.014]}
                  color={theme.header}
                  fontSize={0.048}
                  maxWidth={dimensions.width * 0.78}
                  anchorX="center"
                  anchorY="middle"
                  outlineWidth={0.003}
                  outlineColor={theme.outline}
                  renderOrder={10}
                >
                  {headerLabel}
                </Text>
                <Text
                  position={[-dimensions.width * 0.38, dimensions.height * 0.22, dimensions.thickness + 0.02]}
                  color={theme.accent}
                  fontSize={0.022}
                  anchorX="left"
                  anchorY="middle"
                  outlineWidth={0.002}
                  outlineColor={theme.outline}
                  renderOrder={10}
                >
                  {footerLabel}
                </Text>
                {contentPreview.lines.slice(0, revealedCount).map((line, index, shown) => (
                  <Text
                    key={`content-line-${tab.id}-${index}`}
                    position={[
                      -dimensions.width * 0.38,
                      dimensions.height * 0.16 - index * (POINTS ? 0.046 : 0.035),
                      dimensions.thickness + 0.02,
                    ]}
                    color={POINTS ? theme.header : theme.text}
                    fontSize={POINTS ? 0.034 : 0.025}
                    anchorX="left"
                    anchorY="middle"
                    outlineWidth={0.0016}
                    outlineColor={theme.outline}
                    renderOrder={10}
                  >
                    {(line || ' ') +
                      (index === shown.length - 1 && revealedCount < contentPreview.lines.length
                        ? '▌'
                        : '')}
                  </Text>
                ))}
                <Text
                  position={[0, -dimensions.height * 0.42, dimensions.thickness + 0.014]}
                  color={theme.muted}
                  fontSize={0.024}
                  anchorX="center"
                  anchorY="middle"
                  outlineWidth={0.0016}
                  outlineColor={theme.outline}
                  renderOrder={10}
                >
                  {contentOverflowLabel}
                </Text>
                {!POINTS && (
                  <ReabsorbNode
                    position={[dimensions.width * 0.45, dimensions.height * 0.4, dimensions.thickness + 0.04]}
                    color={theme.text}
                    disabled={!interactive}
                    onActivate={() => beginRetractingMaterializedTab(tab.id)}
                  />
                )}
              </>
            ) : (
              <>
                <mesh position={[0, 0, dimensions.thickness + 0.006]} scale={[0.86, 0.62, 1]} renderOrder={9}>
                  <primitive object={slabShapeGeometry} attach="geometry" />
                  <meshBasicMaterial color={theme.plate} transparent opacity={skin.plateOpacity * organMaterial.tissue.plateOpacityScale} />
                </mesh>
                <Text
                  ref={labelRef}
                  position={[0, dimensions.height * 0.38, dimensions.thickness + 0.014]}
                  color={theme.header}
                  fontSize={0.048}
                  maxWidth={dimensions.width * 0.78}
                  anchorX="center"
                  anchorY="middle"
                  outlineWidth={0.003}
                  outlineColor={theme.outline}
                  renderOrder={10}
                >
                  {headerLabel}
                </Text>
                <Text
                  position={[-dimensions.width * 0.36, dimensions.height * 0.21, dimensions.thickness + 0.02]}
                  color={theme.text}
                  fontSize={0.033}
                  maxWidth={dimensions.width * 0.68}
                  lineHeight={1.18}
                  anchorX="left"
                  anchorY="middle"
                  textAlign="left"
                  outlineWidth={0.0024}
                  outlineColor={theme.outline}
                  renderOrder={10}
                >
                  {tab.approval?.summary || 'Approval required'}
                </Text>
                {tab.approval?.explanation ? (
                  <Text
                    position={[-dimensions.width * 0.36, dimensions.height * 0.12, dimensions.thickness + 0.02]}
                    color={theme.accent}
                    fontSize={0.021}
                    maxWidth={dimensions.width * 0.68}
                    lineHeight={1.25}
                    anchorX="left"
                    anchorY="middle"
                    textAlign="left"
                    outlineWidth={0.0016}
                    outlineColor={theme.outline}
                    renderOrder={10}
                  >
                    {tab.approval.explanation}
                  </Text>
                ) : null}
                {approvalPreview.lines.map((line, index) => (
                  <Text
                    key={`approval-line-${tab.id}-${index}`}
                    position={[
                      -dimensions.width * 0.36,
                      dimensions.height * 0.01 - index * 0.031,
                      dimensions.thickness + 0.02,
                    ]}
                    color={theme.text}
                    fontSize={0.02}
                    anchorX="left"
                    anchorY="middle"
                    outlineWidth={0.0016}
                    outlineColor={theme.outline}
                    renderOrder={10}
                  >
                    {line || ' '}
                  </Text>
                ))}
                <Text
                  position={[0, -dimensions.height * 0.42, dimensions.thickness + 0.014]}
                  color={theme.muted}
                  fontSize={0.024}
                  anchorX="center"
                  anchorY="middle"
                  outlineWidth={0.0014}
                  outlineColor={theme.outline}
                  renderOrder={10}
                >
                  {approvalOverflowLabel}
                </Text>
                {tab.kind === 'approval' ? (
                  <>
                    <ApprovalActionButton
                      label={approvalBusy ? 'WORKING' : 'APPROVE'}
                      position={[-0.32, -dimensions.height * 0.36, dimensions.thickness + 0.048]}
                      fill="#2d8f79"
                      outline="#75f2d0"
                      disabled={buttonDisabled}
                      onActivate={() => {
                        void handleApprove();
                      }}
                    />
                    <ApprovalActionButton
                      label={approvalBusy ? 'WAIT' : 'REJECT'}
                      position={[0.32, -dimensions.height * 0.36, dimensions.thickness + 0.048]}
                      fill="#9d4257"
                      outline="#ff8aa2"
                      disabled={buttonDisabled}
                      onActivate={() => {
                        void handleReject();
                      }}
                    />
                    {!POINTS && (
                      <ReabsorbNode
                        position={[dimensions.width * 0.45, dimensions.height * 0.4, dimensions.thickness + 0.04]}
                        color={theme.text}
                        disabled={!interactive || approvalBusy}
                        onActivate={() => beginRetractingMaterializedTab(tab.id)}
                      />
                    )}
                  </>
                ) : null}
              </>
            )}
          </group>
        </group>
      </group>
    </group>
  );
}
