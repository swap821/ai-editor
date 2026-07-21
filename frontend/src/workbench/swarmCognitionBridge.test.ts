import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { subscribeCognition, type CognitionEvent } from '../superbrain/lib/cognitionBus';
import {
  endSwarmCaste,
  markSwarmCloudSubtask,
  resetSwarmHUD,
  startSwarmCaste,
  startSwarmPlan,
} from '../superbrain/lib/swarmHUDStore';
import { initSwarmCognitionBridge } from './swarmCognitionBridge';

describe('swarmCognitionBridge', () => {
  let events: CognitionEvent[] = [];
  let unsubBus: () => void = () => {};
  let unsubBridge: () => void = () => {};

  beforeEach(() => {
    resetSwarmHUD();
    events = [];
    unsubBridge = initSwarmCognitionBridge();
    unsubBus = subscribeCognition((event) => {
      if (event.source === 'swarm') events.push(event);
    });
  });

  afterEach(() => {
    unsubBus();
    unsubBridge();
    resetSwarmHUD();
  });

  it('publishes nothing for the initial subscribe replay', () => {
    expect(events).toHaveLength(0);
  });

  it('narrates a plan arrival as one agent-dispatch event', () => {
    startSwarmPlan(['read the config', 'write the test']);
    const planEvents = events.filter((e) => e.label === 'SWARM DECOMPOSED');
    expect(planEvents).toHaveLength(1);
    expect(planEvents[0].type).toBe('agent-dispatch');
    expect(planEvents[0].detail).toContain('2 subtask(s)');
  });

  it('narrates caste start and end transitions', () => {
    startSwarmPlan(['one job']);
    startSwarmCaste('decomposer');
    endSwarmCaste('decomposer');
    expect(events.some((e) => e.label === 'CASTE DECOMPOSER')).toBe(true);
    expect(events.some((e) => e.label === 'CASTE DECOMPOSER DONE')).toBe(true);
  });

  it('narrates each cloud-routed subtask exactly once', () => {
    startSwarmPlan(['a', 'b']);
    markSwarmCloudSubtask(1);
    markSwarmCloudSubtask(1); // duplicate mark is a no-op upstream
    const bursts = events.filter((e) => e.label === 'SWARM CLOUD BURST');
    expect(bursts).toHaveLength(1);
    expect(bursts[0].detail).toContain('subtask 2');
  });

  it('stops narrating after unsubscribe', () => {
    unsubBridge();
    startSwarmPlan(['silent']);
    expect(events).toHaveLength(0);
  });
});
