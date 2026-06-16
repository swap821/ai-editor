import { Text } from '@react-three/drei';
import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { approvePendingApproval, rejectPendingApproval } from '@/lib/aiosAdapter';
import { formatMaterializedTextPreview } from '@/lib/materializedTextPreview';
import type { MaterializedApprovalSurface, MaterializedTabKind, MaterializedTabRecord } from '@/lib/tabStore';
import {
  clearMaterializedTab,
  setMaterializedTabLifecycle,
} from '@/lib/tabStore';

const REACH_DURATION_MS = 900;
const UNFURL_DURATION_MS = 520;
const RETRACT_DURATION_MS = 380;
const BASE_TUBE_RADIUS = 0.012;
const UMBILICAL_SEGMENTS = 32;
const UMBILICAL_RADIAL_SEGMENTS = 10;
const BEAD_COUNT = 4;
const CONTENT_PREVIEW_LINES = 24;
const CONTENT_PREVIEW_CHARS = 52;
const APPROVAL_PREVIEW_LINES = 12;
const APPROVAL_PREVIEW_CHARS = 56;

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
    width: 1.08,
    height: 0.9,
    radius: 0.065,
    thickness: 0.028,
    htmlWidth: 0,
    htmlHeight: 0,
    tilt: [0.02, 0.34, 0.02],
  },
  input: {
    width: 0.98,
    height: 0.28,
    radius: 0.075,
    thickness: 0.04,
    htmlWidth: 760,
    htmlHeight: 176,
    tilt: [0.05, 0, 0],
  },
  approval: {
    width: 1.02,
    height: 0.78,
    radius: 0.06,
    thickness: 0.024,
    htmlWidth: 0,
    htmlHeight: 0,
    tilt: [0.03, 0.26, 0.02],
  },
};

const SURFACE_THEME: Record<
  MaterializedTabKind,
  {
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
  }
> = {
  content: {
    reach: new THREE.Color('#79ebff'),
    live: new THREE.Color('#ffbe78'),
    frame: new THREE.Color('#1f3d46'),
    body: '#060d14',
    header: '#5e8c95',
    accent: '#4d7784',
    outline: '#08111b',
    plate: '#07111a',
    text: '#a9fff3',
    muted: '#5f98a6',
  },
  input: {
    reach: new THREE.Color('#6ef0ff'),
    live: new THREE.Color('#9af7ff'),
    frame: new THREE.Color('#1d3943'),
    body: '#06111a',
    header: '#5d919f',
    accent: '#4f7f8b',
    outline: '#04131b',
    plate: '#07151e',
    text: '#c6fcff',
    muted: '#5e99a8',
  },
  approval: {
    reach: new THREE.Color('#ffc36e'),
    live: new THREE.Color('#ff9c62'),
    frame: new THREE.Color('#433324'),
    body: '#130d08',
    header: '#b79268',
    accent: '#8c6b49',
    outline: '#120902',
    plate: '#17110c',
    text: '#ffe7c3',
    muted: '#b99062',
  },
};

function clamp01(value: number): number {
  return THREE.MathUtils.clamp(value, 0, 1);
}

function easing(value: number): number {
  return value * value * (3 - 2 * value);
}

function makeRoundedRectShape(width: number, height: number, radius: number): THREE.Shape {
  const halfW = width * 0.5;
  const halfH = height * 0.5;
  const r = Math.min(radius, halfW, halfH);
  const shape = new THREE.Shape();
  shape.moveTo(-halfW + r, -halfH);
  shape.lineTo(halfW - r, -halfH);
  shape.quadraticCurveTo(halfW, -halfH, halfW, -halfH + r);
  shape.lineTo(halfW, halfH - r);
  shape.quadraticCurveTo(halfW, halfH, halfW - r, halfH);
  shape.lineTo(-halfW + r, halfH);
  shape.quadraticCurveTo(-halfW, halfH, -halfW, halfH - r);
  shape.lineTo(-halfW, -halfH + r);
  shape.quadraticCurveTo(-halfW, -halfH, -halfW + r, -halfH);
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
  if (tab.kind === 'content') return tab.content?.language ?? 'text';
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
        <boxGeometry args={[0.28, 0.09, 0.022]} />
        <meshStandardMaterial
          color={fill}
          emissive={fill}
          emissiveIntensity={disabled ? 0.08 : hovered ? 0.46 : 0.24}
          roughness={0.2}
          metalness={0.18}
          transparent
          opacity={disabled ? 0.32 : 0.92}
        />
      </mesh>
      <mesh position={[0, 0, 0.012]} renderOrder={12}>
        <planeGeometry args={[0.31, 0.11]} />
        <meshBasicMaterial color={outline} transparent opacity={disabled ? 0.16 : 0.2} />
      </mesh>
      <Text
        position={[0, 0, 0.014]}
        color="#f9fbff"
        fontSize={0.03}
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

export default function MaterializedTab({
  tab,
  reducedMotion,
}: {
  tab: MaterializedTabRecord;
  reducedMotion: boolean;
}) {
  const camera = useThree((state) => state.camera);
  const [approvalBusy, setApprovalBusy] = useState(false);
  const orientationRef = useRef<THREE.Group>(null);
  const slabRef = useRef<THREE.Group>(null);
  const tubeRef = useRef<THREE.Mesh>(null);
  const bodyRef = useRef<THREE.Mesh>(null);
  const frameRef = useRef<THREE.LineSegments>(null);
  const labelRef = useRef<THREE.Object3D>(null);
  const beadRefs = useRef<THREE.Mesh[]>([]);

  const dimensions = SURFACE_DIMENSIONS[tab.kind];
  const theme = SURFACE_THEME[tab.kind];
  const tubeRadius = tab.kind === 'input' ? BASE_TUBE_RADIUS * 0.8 : BASE_TUBE_RADIUS;
  const facesCamera = tab.kind === 'input';

  const curve = useMemo(() => {
    const origin = new THREE.Vector3(...tab.originLocal);
    const target = new THREE.Vector3(...tab.targetLocal);
    const delta = target.clone().sub(origin);

    if (tab.kind === 'input') {
      const midA = origin.clone().add(delta.clone().multiplyScalar(0.34)).add(new THREE.Vector3(0, 0.08, 0.03));
      const midB = origin.clone().add(delta.clone().multiplyScalar(0.76)).add(new THREE.Vector3(0.02, 0.04, 0.02));
      return new THREE.CatmullRomCurve3([origin, midA, midB, target]);
    }

    const midA = origin.clone().add(delta.clone().multiplyScalar(0.3)).add(new THREE.Vector3(0.05, 0.01, 0.02));
    const midB = origin.clone().add(delta.clone().multiplyScalar(0.78)).add(new THREE.Vector3(0.02, 0.01, 0.01));
    return new THREE.CatmullRomCurve3([origin, midA, midB, target]);
  }, [tab.kind, tab.originLocal, tab.targetLocal]);

  const tubeGeometry = useMemo(
    () => new THREE.TubeGeometry(curve, UMBILICAL_SEGMENTS, tubeRadius, UMBILICAL_RADIAL_SEGMENTS, false),
    [curve, tubeRadius],
  );
  const slabShape = useMemo(
    () => makeRoundedRectShape(dimensions.width, dimensions.height, dimensions.radius),
    [dimensions.height, dimensions.radius, dimensions.width],
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
      slabBodyGeometry.dispose();
      slabShapeGeometry.dispose();
      slabFrameGeometry.dispose();
    };
  }, [slabBodyGeometry, slabFrameGeometry, slabShapeGeometry, tubeGeometry]);

  useEffect(() => {
    if (tab.kind !== 'approval') {
      setApprovalBusy(false);
    }
  }, [tab.kind, tab.approval?.token]);

  useFrame((state) => {
    const now = performance.now();

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
        const retractProgress = clamp01(elapsed / RETRACT_DURATION_MS);
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
      mat.color.copy(theme.reach).lerp(theme.live, liveProgress);
      mat.emissive.copy(theme.reach).lerp(theme.live, liveProgress);
      mat.emissiveIntensity = tab.kind === 'input' ? 1.1 : 0.86 + liveProgress * 0.64;
      mat.opacity = 0.3 + Math.max(reachProgress, slabProgress) * 0.64;
    }

    if (facesCamera && orientationRef.current) {
      orientationRef.current.lookAt(camera.position);
    }

    const slabT =
      tab.lifecycle === 'reaching' || tab.lifecycle === 'retracting'
        ? clamp01(Math.max(reachProgress, 0.04))
        : 1;

    if (slabRef.current) {
      const eased = easing(slabProgress);
      slabRef.current.scale.set(
        0.74 + eased * 0.26,
        Math.max(0.01, eased),
        0.7 + eased * 0.3,
      );
      slabRef.current.position.copy(curve.getPointAt(slabT));
    }

    if (bodyRef.current) {
      const mat = bodyRef.current.material as THREE.MeshStandardMaterial;
      mat.opacity = 0.14 + slabProgress * 0.8;
      mat.emissive.copy(theme.reach).lerp(theme.live, liveProgress * 0.9);
      mat.emissiveIntensity = tab.kind === 'input' ? 0.18 + slabProgress * 0.18 : 0.1 + slabProgress * 0.16;
    }

    if (frameRef.current) {
      const mat = frameRef.current.material as THREE.LineBasicMaterial;
      mat.color.copy(theme.frame);
      mat.opacity = 0.08 + slabProgress * 0.24;
    }

    if (labelRef.current) {
      labelRef.current.scale.setScalar(0.96 + slabProgress * 0.04);
    }

    const beadTravel = (state.clock.elapsedTime * 0.28) % 1;
    beadRefs.current.forEach((bead, index) => {
      if (!bead) return;
      const t = clamp01((beadTravel + index * 0.19) % 1);
      const pathT = clamp01(0.08 + t * 0.84 * Math.max(reachProgress, 0.24));
      bead.position.copy(curve.getPointAt(pathT));
      bead.scale.setScalar(tab.kind === 'input' ? 0.38 + liveProgress * 0.5 : 0.45 + liveProgress * 0.7);
      const mat = bead.material as THREE.MeshBasicMaterial;
      mat.color.copy(theme.reach).lerp(theme.live, liveProgress);
      mat.opacity = 0.24 + liveProgress * 0.68;
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
    <group>
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
                emissive={theme.accent}
                emissiveIntensity={0.18}
                roughness={0.26}
                metalness={0.34}
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

            {tab.kind === 'input' ? (
              <>
                <mesh position={[0, 0, dimensions.thickness + 0.006]} renderOrder={9}>
                  <planeGeometry args={[dimensions.width * 0.84, dimensions.height * 0.56]} />
                  <meshBasicMaterial color={theme.plate} transparent opacity={0.94} />
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
                <mesh position={[0, -0.01, dimensions.thickness + 0.006]} renderOrder={9}>
                  <planeGeometry args={[dimensions.width * 0.88, dimensions.height * 0.72]} />
                  <meshBasicMaterial color={theme.plate} transparent opacity={0.96} />
                </mesh>
                <mesh position={[0, dimensions.height * 0.31, dimensions.thickness + 0.008]} renderOrder={9}>
                  <planeGeometry args={[dimensions.width * 0.78, dimensions.height * 0.1]} />
                  <meshBasicMaterial color="#0e2331" transparent opacity={0.78} />
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
                {contentPreview.lines.map((line, index) => (
                  <Text
                    key={`content-line-${tab.id}-${index}`}
                    position={[
                      -dimensions.width * 0.38,
                      dimensions.height * 0.165 - index * 0.028,
                      dimensions.thickness + 0.02,
                    ]}
                    color={theme.text}
                    fontSize={0.0195}
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
                  outlineWidth={0.0016}
                  outlineColor={theme.outline}
                  renderOrder={10}
                >
                  {contentOverflowLabel}
                </Text>
              </>
            ) : (
              <>
                <mesh position={[0, 0, dimensions.thickness + 0.006]} renderOrder={9}>
                  <planeGeometry args={[dimensions.width * 0.86, dimensions.height * 0.62]} />
                  <meshBasicMaterial color={theme.plate} transparent opacity={0.95} />
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
                      position={[-0.2, -dimensions.height * 0.62, dimensions.thickness + 0.048]}
                      fill="#2d8f79"
                      outline="#75f2d0"
                      disabled={buttonDisabled}
                      onActivate={() => {
                        void handleApprove();
                      }}
                    />
                    <ApprovalActionButton
                      label={approvalBusy ? 'WAIT' : 'REJECT'}
                      position={[0.2, -dimensions.height * 0.62, dimensions.thickness + 0.048]}
                      fill="#9d4257"
                      outline="#ff8aa2"
                      disabled={buttonDisabled}
                      onActivate={() => {
                        void handleReject();
                      }}
                    />
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
