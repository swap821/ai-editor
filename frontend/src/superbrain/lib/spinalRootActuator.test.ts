import { describe, expect, it } from 'vitest';
import { deriveSpinalRootActuator } from './spinalRootActuator';
import type { OutcomeImprintSnapshot } from './outcomeImprint';
import type { TurnMetabolismSnapshot } from './turnMetabolism';

const working: TurnMetabolismSnapshot = {
  phase: 'working',
  intensity: 1,
  surfaceExcitation: 0.55,
  rootExcitation: 0.7,
  breathGain: 0.32,
  tint: '#ffbe78',
  held: false,
  changedAt: 1000,
};

const approval: TurnMetabolismSnapshot = {
  phase: 'approval',
  intensity: 1,
  surfaceExcitation: 0.68,
  rootExcitation: 0.78,
  breathGain: -0.18,
  tint: '#ffc36e',
  held: true,
  changedAt: 1200,
};

const scar: OutcomeImprintSnapshot = {
  kind: 'scar',
  intensity: 1,
  ringOpacity: 0.1,
  scarOpacity: 0.46,
  rootGlow: 0.7,
  surfaceGlow: 0.12,
  tint: '#ff5f7a',
  label: 'VERIFICATION RED',
  detail: 'failed',
  changedAt: 1600,
};

describe('spinalRootActuator', () => {
  it('keeps brainstem input roots at rest', () => {
    const actuator = deriveSpinalRootActuator({
      kind: 'input',
      lifecycle: 'live',
      focused: true,
    });

    expect(actuator.role).toBe('resting');
    expect(actuator.flow).toBe('none');
    expect(actuator.opacityGain).toBe(0);
  });

  it('turns waiting workspaces into low-tension sensing roots', () => {
    const near = deriveSpinalRootActuator({
      kind: 'content',
      lifecycle: 'live',
      focused: false,
      waitingIndex: 0,
    });
    const far = deriveSpinalRootActuator({
      kind: 'content',
      lifecycle: 'live',
      focused: false,
      waitingIndex: 3,
    });

    expect(near.role).toBe('sensing');
    expect(near.flow).toBe('bidirectional');
    expect(far.tension).toBeLessThan(near.tension);
    expect(far.opacityGain).toBeLessThan(near.opacityGain);
  });

  it('uses outbound conducting flow for focused live work', () => {
    const idleGrip = deriveSpinalRootActuator({
      kind: 'content',
      lifecycle: 'live',
      focused: true,
    });
    const conducting = deriveSpinalRootActuator({
      kind: 'content',
      lifecycle: 'live',
      focused: true,
      metabolism: working,
    });

    expect(conducting.role).toBe('conducting');
    expect(conducting.flow).toBe('outbound');
    expect(conducting.tension).toBeGreaterThan(idleGrip.tension);
    expect(conducting.beadSpeed).toBeGreaterThan(idleGrip.beadSpeed);
  });

  it('locks approval work into a high-stiffness holding clamp', () => {
    const actuator = deriveSpinalRootActuator({
      kind: 'approval',
      lifecycle: 'live',
      focused: true,
      metabolism: approval,
    });

    expect(actuator.role).toBe('holding');
    expect(actuator.flow).toBe('bidirectional');
    expect(actuator.stiffness).toBeGreaterThan(0.9);
    expect(actuator.tint).toBe('#ffb06e');
  });

  it('returns signal toward the spine for errors and reabsorption', () => {
    const errored = deriveSpinalRootActuator({
      kind: 'content',
      lifecycle: 'live',
      focused: true,
      outcome: scar,
    });
    const reabsorbing = deriveSpinalRootActuator({
      kind: 'content',
      lifecycle: 'retracting',
      focused: false,
    });

    expect(errored.role).toBe('error');
    expect(errored.flow).toBe('return');
    expect(errored.tint).toBe('#ff5f7a');
    expect(reabsorbing.role).toBe('reabsorbing');
    expect(reabsorbing.flow).toBe('return');
  });
});
