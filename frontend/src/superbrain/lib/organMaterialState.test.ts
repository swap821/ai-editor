import { describe, expect, it } from 'vitest';
import { ORGAN_ASSET_SOURCE_PROVENANCE, deriveOrganMaterialState } from './organMaterialState';
import type { OutcomeImprintSnapshot } from './outcomeImprint';
import type { SpinalRootActuator } from './spinalRootActuator';
import type { TurnMetabolismSnapshot } from './turnMetabolism';

const workingMetabolism: TurnMetabolismSnapshot = {
  phase: 'working',
  intensity: 1,
  surfaceExcitation: 0.55,
  rootExcitation: 0.7,
  breathGain: 0.32,
  tint: '#ffbe78',
  held: false,
  changedAt: 1000,
};

const errorMetabolism: TurnMetabolismSnapshot = {
  phase: 'error',
  intensity: 0.92,
  surfaceExcitation: 0.66,
  rootExcitation: 0.51,
  breathGain: 0.2,
  tint: '#ff5f7a',
  held: false,
  changedAt: 1200,
};

const verifiedImprint: OutcomeImprintSnapshot = {
  kind: 'verified',
  intensity: 1,
  ringOpacity: 0.36,
  scarOpacity: 0.12,
  rootGlow: 0.76,
  surfaceGlow: 0.22,
  tint: '#8dffd1',
  label: 'VERIFICATION GREEN',
  detail: 'passed',
  changedAt: 2000,
};

const scarImprint: OutcomeImprintSnapshot = {
  ...verifiedImprint,
  kind: 'scar',
  tint: '#ff5f7a',
  label: 'VERIFICATION RED',
};

const conductingActuator: Pick<SpinalRootActuator, 'role' | 'tension' | 'textureMix' | 'tint' | 'secondaryTint'> = {
  role: 'conducting',
  tension: 0.76,
  textureMix: 0.52,
  tint: '#9affee',
  secondaryTint: '#d5c6ff',
};

describe('organMaterialState', () => {
  it('records asset-source as reference provenance, not browser runtime input', () => {
    expect(ORGAN_ASSET_SOURCE_PROVENANCE.roots).toContain('GAG demo/assets-source/UE_5.8');
    expect(ORGAN_ASSET_SOURCE_PROVENANCE.roots).toContain('GAG demo/assets-source/Twinmotion2026.1');
    expect(ORGAN_ASSET_SOURCE_PROVENANCE.roots).toContain('GAG demo/assets-source/RealityScan_2.1');
    expect(ORGAN_ASSET_SOURCE_PROVENANCE.runtimePolicy).toBe('reference-only');
    expect(ORGAN_ASSET_SOURCE_PROVENANCE.rejectedRuntimeSources).toContain('.uasset');
    expect(ORGAN_ASSET_SOURCE_PROVENANCE.rejectedRuntimeSources).toContain('.dll');
    expect(ORGAN_ASSET_SOURCE_PROVENANCE.acceptedRuntimeExports).toContain('.glb');
  });

  it('keeps all materialized surfaces in the same dark body family', () => {
    const content = deriveOrganMaterialState({
      kind: 'content',
      lifecycle: 'live',
      focused: true,
      metabolism: workingMetabolism,
      actuator: conductingActuator,
    });
    const approval = deriveOrganMaterialState({
      kind: 'approval',
      lifecycle: 'live',
      focused: true,
      metabolism: { ...workingMetabolism, phase: 'approval', held: true },
      actuator: { ...conductingActuator, role: 'holding', tint: '#ffb06e' },
    });

    expect(content.palette.body).toBe('#02070d');
    expect(approval.palette.body).toBe(content.palette.body);
    expect(approval.palette.plate).not.toBe('#ffffff');
    expect(approval.tissue.plateOpacityScale).toBeLessThan(content.tissue.plateOpacityScale);
    expect(approval.tissue.frameOpacityScale).toBeLessThan(content.tissue.frameOpacityScale);
  });

  it('uses root actuator texture as the source for point-field tissue intensity', () => {
    const calm = deriveOrganMaterialState({
      kind: 'content',
      lifecycle: 'live',
      focused: true,
      actuator: { ...conductingActuator, tension: 0.2, textureMix: 0.18 },
    });
    const active = deriveOrganMaterialState({
      kind: 'content',
      lifecycle: 'live',
      focused: true,
      metabolism: workingMetabolism,
      actuator: conductingActuator,
    });

    expect(active.tissue.sourceTextureMix).toBeGreaterThan(calm.tissue.sourceTextureMix);
    expect(active.tissue.pointFieldOpacity).toBeGreaterThan(calm.tissue.pointFieldOpacity);
    expect(active.tissue.rootGripGain).toBeGreaterThan(calm.tissue.rootGripGain);
  });

  it('moves red failures into scar material without turning the whole body into alarm chrome', () => {
    const scar = deriveOrganMaterialState({
      kind: 'content',
      lifecycle: 'live',
      focused: true,
      metabolism: errorMetabolism,
      outcome: scarImprint,
      actuator: { ...conductingActuator, role: 'error', tint: '#ff5f7a' },
    });

    expect(scar.role).toBe('scar');
    expect(scar.palette.live).toBe('#ff5f7a');
    expect(scar.palette.body).toBe('#02070d');
    expect(scar.tissue.bodyOpacityScale).toBeLessThan(0.9);
    expect(scar.tissue.signalOpacityScale).toBeGreaterThan(scar.tissue.bodyOpacityScale);
  });

  it('makes green completion become memory material for reabsorption', () => {
    const memory = deriveOrganMaterialState({
      kind: 'content',
      lifecycle: 'retracting',
      focused: true,
      outcome: verifiedImprint,
      actuator: { ...conductingActuator, role: 'reabsorbing', tint: '#a9fff3' },
    });

    expect(memory.role).toBe('memory');
    expect(memory.palette.text).toBe('#d8fff7');
    expect(memory.tissue.pointFieldOpacity).toBeGreaterThan(0.2);
  });

  it('keeps retracting completion memory readable after focus leaves', () => {
    const memory = deriveOrganMaterialState({
      kind: 'content',
      lifecycle: 'retracting',
      focused: false,
      outcome: verifiedImprint,
      actuator: { ...conductingActuator, role: 'reabsorbing', tint: '#a9fff3' },
    });

    expect(memory.role).toBe('memory');
    expect(memory.tissue.bodyOpacityScale).toBeGreaterThan(0.65);
    expect(memory.tissue.pointFieldOpacity).toBeGreaterThan(0.2);
    expect(memory.tissue.signalOpacityScale).toBeGreaterThan(memory.tissue.bodyOpacityScale);
  });

  it('keeps waiting work subordinate while preserving the same material grammar', () => {
    const focused = deriveOrganMaterialState({
      kind: 'content',
      lifecycle: 'live',
      focused: true,
      actuator: conductingActuator,
    });
    const waiting = deriveOrganMaterialState({
      kind: 'content',
      lifecycle: 'live',
      focused: false,
      waitingIndex: 2,
      actuator: conductingActuator,
    });

    expect(waiting.role).toBe('waiting');
    expect(waiting.palette.body).toBe(focused.palette.body);
    expect(waiting.tissue.pointFieldOpacity).toBeLessThan(focused.tissue.pointFieldOpacity);
    expect(waiting.tissue.frameOpacityScale).toBeLessThan(focused.tissue.frameOpacityScale);
  });
});
