import type { OutcomeImprintSnapshot } from './outcomeImprint';
import type { SpinalRootActuator } from './spinalRootActuator';
import type { MaterializedTabKind, TabLifecycle } from './tabStore';
import type { TurnMetabolismSnapshot } from './turnMetabolism';

export type OrganMaterialRole = 'intake' | 'work' | 'decision' | 'scar' | 'memory' | 'waiting';

export interface OrganAssetSourceProvenance {
  roots: readonly string[];
  runtimePolicy: 'reference-only';
  acceptedRuntimeExports: readonly string[];
  rejectedRuntimeSources: readonly string[];
  influence: readonly string[];
}

export interface OrganMaterialStateInput {
  kind: MaterializedTabKind;
  lifecycle?: TabLifecycle;
  focused: boolean;
  waitingIndex?: number;
  metabolism?: TurnMetabolismSnapshot | null;
  outcome?: OutcomeImprintSnapshot | null;
  actuator?: Pick<SpinalRootActuator, 'role' | 'tension' | 'textureMix' | 'tint' | 'secondaryTint'> | null;
}

export interface OrganMaterialPalette {
  body: string;
  plate: string;
  outline: string;
  frame: string;
  reach: string;
  live: string;
  header: string;
  accent: string;
  text: string;
  muted: string;
  point: string;
}

export interface OrganMaterialTissue {
  bodyOpacityScale: number;
  plateOpacityScale: number;
  frameOpacityScale: number;
  headerOpacityScale: number;
  membraneOpacityScale: number;
  signalOpacityScale: number;
  pointFieldOpacity: number;
  pointFieldScale: number;
  sourceTextureMix: number;
  rootGripGain: number;
  emissiveGain: number;
  roughness: number;
  metalness: number;
}

export interface OrganMaterialState {
  role: OrganMaterialRole;
  sourceProvenance: string;
  palette: OrganMaterialPalette;
  tissue: OrganMaterialTissue;
}

export const ORGAN_ASSET_SOURCE_PROVENANCE: OrganAssetSourceProvenance = {
  roots: [
    'GAG demo/assets-source/UE_5.8',
    'GAG demo/assets-source/Twinmotion2026.1',
    'GAG demo/assets-source/RealityScan_2.1',
  ],
  runtimePolicy: 'reference-only',
  acceptedRuntimeExports: ['.glb', '.gltf', '.ktx2', '.webp', '.png', '.jpg', '.jpeg', '.hdr', '.exr'],
  rejectedRuntimeSources: ['.uasset', '.umap', '.dll', '.exe', '.pak', '.lib', '.obj'],
  influence: [
    'UE_5.8 sets cinematic tissue material intent',
    'Twinmotion sets environmental light and atmosphere intent',
    'RealityScan sets micro-surface and scan-detail intent',
  ],
};

const SOURCE_PROVENANCE = ORGAN_ASSET_SOURCE_PROVENANCE.roots
  .map((root) => root.split('/').pop() ?? root)
  .join('+');

const BODY_CORE = {
  body: '#02070d',
  plate: '#04101a',
  outline: '#010409',
  frame: '#132f38',
  muted: '#5f98a6',
};

const ROLE_PALETTE: Record<
  OrganMaterialRole,
  Pick<OrganMaterialPalette, 'reach' | 'live' | 'header' | 'accent' | 'text' | 'point'>
> = {
  intake: {
    reach: '#6ef0ff',
    live: '#9af7ff',
    header: '#67a9b5',
    accent: '#5c8d9a',
    text: '#c6fcff',
    point: '#b9fff8',
  },
  work: {
    reach: '#79ebff',
    live: '#ffbe78',
    header: '#6f9da7',
    accent: '#5d8792',
    text: '#a9fff3',
    point: '#d7fff5',
  },
  decision: {
    reach: '#ffc36e',
    live: '#ff9c62',
    header: '#b68a62',
    accent: '#6d4d35',
    text: '#ffe7c3',
    point: '#ffe0a9',
  },
  scar: {
    reach: '#ff7a90',
    live: '#ff5f7a',
    header: '#b85b6f',
    accent: '#733042',
    text: '#ffd9e1',
    point: '#ff9ead',
  },
  memory: {
    reach: '#a9fff3',
    live: '#8dffd1',
    header: '#7bc6b7',
    accent: '#5a9187',
    text: '#d8fff7',
    point: '#d5fff8',
  },
  waiting: {
    reach: '#79ebff',
    live: '#b9b6ff',
    header: '#547b89',
    accent: '#426875',
    text: '#9fe8e3',
    point: '#bdd8ff',
  },
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function round4(value: number): number {
  return Math.round(value * 10000) / 10000;
}

function roleFor(input: OrganMaterialStateInput): OrganMaterialRole {
  if (input.kind === 'input') return 'intake';
  if (input.lifecycle === 'retracting' || input.outcome?.kind === 'verified') return 'memory';
  if (input.outcome?.kind === 'scar' || input.metabolism?.phase === 'error') return 'scar';
  if (input.kind === 'approval') return 'decision';
  if (!input.focused) return 'waiting';
  return 'work';
}

function attentionFor(input: OrganMaterialStateInput): number {
  if (input.kind === 'input' || input.focused) return 1;
  if (input.lifecycle === 'retracting' || input.outcome?.kind === 'verified') return 0.88;
  const index = Math.max(0, input.waitingIndex ?? 0);
  return clamp(0.62 - index * 0.08, 0.36, 0.62);
}

function activityFor(input: OrganMaterialStateInput): number {
  return clamp(
    Math.max(
      input.metabolism?.intensity ?? 0,
      input.outcome?.intensity ?? 0,
      input.actuator?.tension ?? 0,
      input.lifecycle === 'reaching' || input.lifecycle === 'unfurling' ? 0.44 : 0,
      input.lifecycle === 'retracting' ? 0.68 : 0,
    ),
    0,
    1,
  );
}

function surfaceRolePlate(role: OrganMaterialRole): string {
  if (role === 'decision') return '#070604';
  if (role === 'scar') return '#08050a';
  return BODY_CORE.plate;
}

function frameFor(role: OrganMaterialRole): string {
  if (role === 'decision') return '#251b13';
  if (role === 'scar') return '#221018';
  if (role === 'waiting') return '#10242d';
  return BODY_CORE.frame;
}

export function deriveOrganMaterialState(input: OrganMaterialStateInput): OrganMaterialState {
  const role = roleFor(input);
  const rolePalette = ROLE_PALETTE[role];
  const attention = attentionFor(input);
  const activity = activityFor(input);
  const actuatorTexture = input.actuator?.textureMix ?? 0.28;
  const sourceTextureMix = clamp(0.34 + actuatorTexture * 0.52 + activity * 0.12, 0.34, 0.86);
  const bodyBaseScale = role === 'scar' ? 0.48 : role === 'intake' ? 0.94 : 0.82;
  const plateBaseScale = role === 'scar' ? 0.42 : role === 'intake' ? 0.9 : role === 'decision' ? 0.72 : 0.78;
  const decisionDimming = role === 'decision' ? 0.9 : 1;
  const scarTightening = role === 'scar' ? 1.12 : 1;

  return {
    role,
    sourceProvenance: SOURCE_PROVENANCE,
    palette: {
      body: BODY_CORE.body,
      plate: surfaceRolePlate(role),
      outline: BODY_CORE.outline,
      frame: frameFor(role),
      reach: input.actuator?.role === 'error' ? ROLE_PALETTE.scar.reach : rolePalette.reach,
      live: input.actuator?.tint ?? rolePalette.live,
      header: rolePalette.header,
      accent: rolePalette.accent,
      text: rolePalette.text,
      muted: role === 'decision' ? '#8d6f4d' : BODY_CORE.muted,
      point: input.actuator?.secondaryTint ?? rolePalette.point,
    },
    tissue: {
      bodyOpacityScale: round4(clamp(bodyBaseScale * attention * decisionDimming, 0.24, 0.96)),
      plateOpacityScale: round4(clamp(plateBaseScale * attention, 0.18, 0.92)),
      frameOpacityScale: round4(clamp((role === 'decision' ? 0.7 : 0.78) * attention * scarTightening, 0.22, 0.92)),
      headerOpacityScale: round4(clamp((role === 'intake' ? 0.74 : 0.58) * attention, 0.2, 0.78)),
      membraneOpacityScale: round4(clamp((1 + sourceTextureMix * 0.18 + activity * 0.08) * attention, 0.44, 1.22)),
      signalOpacityScale: round4(clamp((1 + sourceTextureMix * 0.36 + activity * 0.2) * attention, 0.52, 1.38)),
      pointFieldOpacity: round4(clamp((0.09 + sourceTextureMix * 0.22 + activity * 0.12) * attention, 0.035, 0.42)),
      pointFieldScale: round4(clamp(0.72 + sourceTextureMix * 0.56 + activity * 0.18, 0.72, 1.36)),
      sourceTextureMix: round4(sourceTextureMix),
      rootGripGain: round4(clamp((0.88 + sourceTextureMix * 0.24 + activity * 0.22) * attention, 0.56, 1.32)),
      emissiveGain: round4(clamp((0.86 + activity * 0.22) * (role === 'intake' ? 1.08 : 1), 0.68, 1.18)),
      roughness: round4(clamp(0.74 - sourceTextureMix * 0.16, 0.56, 0.74)),
      metalness: round4(clamp(0.05 + sourceTextureMix * 0.08, 0.05, 0.12)),
    },
  };
}
