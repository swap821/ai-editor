import { describe, expect, it } from 'vitest';
import { deriveMaterializedSurfaceSkin } from './materializedSurfaceSkin';
import type { OutcomeImprintSnapshot } from './outcomeImprint';
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

describe('materializedSurfaceSkin', () => {
  it('keeps the brainstem input readable instead of applying waiting dimming', () => {
    const skin = deriveMaterializedSurfaceSkin({
      kind: 'input',
      focused: false,
      waitingIndex: 4,
    });

    expect(skin.bodyLiveOpacity).toBe(0.82);
    expect(skin.plateOpacity).toBe(0.82);
    expect(skin.actionOpacity).toBe(1);
  });

  it('dims parked workspace membranes without changing their visual grammar', () => {
    const focused = deriveMaterializedSurfaceSkin({
      kind: 'content',
      focused: true,
    });
    const waiting = deriveMaterializedSurfaceSkin({
      kind: 'content',
      focused: false,
      waitingIndex: 0,
    });
    const deeperWaiting = deriveMaterializedSurfaceSkin({
      kind: 'content',
      focused: false,
      waitingIndex: 2,
    });

    expect(waiting.bodyLiveOpacity).toBeLessThan(focused.bodyLiveOpacity);
    expect(waiting.veinOpacity).toBeLessThan(focused.veinOpacity);
    expect(deeperWaiting.bodyLiveOpacity).toBeLessThan(waiting.bodyLiveOpacity);
    expect(deeperWaiting.nodeOpacity).toBeLessThan(waiting.nodeOpacity);
  });

  it('keeps approval chrome dimmer than content chrome so the decision text leads', () => {
    const content = deriveMaterializedSurfaceSkin({
      kind: 'content',
      focused: true,
    });
    const approval = deriveMaterializedSurfaceSkin({
      kind: 'approval',
      focused: true,
    });

    expect(approval.frameLiveOpacity).toBeLessThan(content.frameLiveOpacity);
    expect(approval.emissiveIntensity).toBeLessThan(content.emissiveIntensity);
    expect(approval.actionOpacity).toBeGreaterThan(0.7);
  });

  it('raises focused membrane metabolism without brightening parked surfaces equally', () => {
    const focusedRest = deriveMaterializedSurfaceSkin({
      kind: 'content',
      focused: true,
    });
    const focusedWorking = deriveMaterializedSurfaceSkin({
      kind: 'content',
      focused: true,
      metabolism: workingMetabolism,
    });
    const waitingWorking = deriveMaterializedSurfaceSkin({
      kind: 'content',
      focused: false,
      waitingIndex: 0,
      metabolism: workingMetabolism,
    });

    expect(focusedWorking.bodyLiveOpacity).toBeGreaterThan(focusedRest.bodyLiveOpacity);
    expect(focusedWorking.veinOpacity).toBeGreaterThan(focusedRest.veinOpacity);
    expect(waitingWorking.bodyLiveOpacity).toBeLessThan(focusedWorking.bodyLiveOpacity);
  });

  it('routes verification imprint mostly into signal layers instead of full body fill', () => {
    const focusedRest = deriveMaterializedSurfaceSkin({
      kind: 'content',
      focused: true,
    });
    const focusedVerified = deriveMaterializedSurfaceSkin({
      kind: 'content',
      focused: true,
      outcome: verifiedImprint,
    });
    const waitingVerified = deriveMaterializedSurfaceSkin({
      kind: 'content',
      focused: false,
      waitingIndex: 0,
      outcome: verifiedImprint,
    });

    const bodyDelta = focusedVerified.bodyLiveOpacity - focusedRest.bodyLiveOpacity;
    const veinDelta = focusedVerified.veinOpacity - focusedRest.veinOpacity;

    expect(focusedVerified.frameLiveOpacity).toBeGreaterThan(focusedRest.frameLiveOpacity);
    expect(focusedVerified.veinOpacity).toBeGreaterThan(focusedRest.veinOpacity);
    expect(veinDelta).toBeGreaterThan(bodyDelta);
    expect(waitingVerified.veinOpacity).toBeLessThan(focusedVerified.veinOpacity);
  });
});
